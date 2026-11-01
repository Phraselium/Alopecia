"""OcasionPlus (concesionario profesional de ocasión).

Método (ver RECONOCIMIENTO.md): robots.txt prohíbe los filtros por parámetro, así que se recorre
/coches-segunda-mano/valencia?page=N (JSON-LD ItemList, 20 por página) y solo se abre la ficha de los
coches que por precio/año/km pueden entrar. La ficha trae un objeto `vehicle` en el payload RSC.
"""
from __future__ import annotations

import logging
import re
from typing import Iterator, Optional

from bs4 import BeautifulSoup

from ..models import Listing
from .base import Source
from .common import ld_json, objects_after, rsc_payload, to_int

log = logging.getLogger("ocasionplus")
BASE = "https://www.ocasionplus.com"


class OcasionPlus(Source):
    name = "ocasionplus"
    metodo = "json-ld + payload RSC"
    estado = "ok"

    def _list_items(self, html: str) -> list[dict]:
        lists = [d for d in ld_json(html) if d.get("@type") == "ItemList"]
        if not lists:
            return []
        main = max(lists, key=lambda d: len(d.get("itemListElement", [])))
        return [e.get("item", e) for e in main.get("itemListElement", [])]

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        f = self.cfg["filtros"]
        pmax = self.cfg["presupuesto"]["precio_anuncio_max_eur"]
        seen: set[str] = set()
        for page in range(1, self.src_cfg.get("max_paginas", 60) + 1):
            url = f"{BASE}/coches-segunda-mano/valencia" + (f"?page={page}" if page > 1 else "")
            r = self.client.get(self.name, url)
            items = self._list_items(r["text"])
            new = [i for i in items if (i.get("offers") or {}).get("url") not in seen]
            if not new:
                break
            for it in new:
                off = it.get("offers") or {}
                link = off.get("url")
                seen.add(link)
                price = off.get("price")
                year = to_int((it.get("productionDate") or "")[:4])
                km = to_int((it.get("mileageFromOdometer") or {}).get("value"))
                if not link:
                    continue
                self.observe(link.rstrip("/").split("-")[-1], (it.get("brand") or {}).get("name"), None,
                             it.get("model") or it.get("name"), year, km, price)
                # Precio del listado = el más bajo (financiado). Si ni así entra, no se abre la ficha.
                if price is None or price > pmax or (year and year < f["anio_min"]) or (km and km > f["km_max"]):
                    continue
                slug = link.rstrip("/").split("/")[-1]
                yield Listing(
                    plataforma=self.name, id_externo=slug.split("-")[-1], url=link,
                    titulo=it.get("model") or it.get("name") or "", precio=float(price),
                    marca=(it.get("brand") or {}).get("name"), modelo=None, version=it.get("model"),
                    combustible=it.get("fuelType"), anio=year, km=km, cambio=it.get("vehicleTransmission"),
                    vendedor="profesional", fuente_dato=f"{url} (JSON-LD)", raw_ref=r["cache_file"])

    def needs_detail(self, l: Listing) -> bool:
        return True

    def detail(self, l: Listing) -> Listing:
        r = self.client.get(self.name, l.url)
        html = r["text"]
        rsc = rsc_payload(html)
        v = next((o for o in objects_after(rsc, r'"vehicle":\{') if "kms" in o and isinstance(o.get("engine"), dict)), None)
        dealer = next((o for o in objects_after(rsc, r'"dealer":\{') if o.get("name") and o.get("zip")), None)
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        l.raw_ref = r["cache_file"]
        l.fuente_dato = f"{l.url} (payload RSC 'vehicle')"
        if v:
            pr = v.get("price") or {}
            l.precio_contado = pr.get("cash") or pr.get("withoutFinancing")
            l.precio_financiado = pr.get("withFinancing")
            if l.precio_contado:
                l.precio = float(l.precio_contado)
            l.solo_financiando = bool(l.precio_financiado and l.precio_contado and l.precio_financiado < l.precio_contado)
            eng = v.get("engine") or {}
            l.cilindrada_cc = to_int(eng.get("cc"))
            l.potencia_cv = to_int(eng.get("cv"))
            l.combustible = eng.get("fuel") or l.combustible
            l.cambio = eng.get("transmission") or l.cambio
            l.km = to_int(v.get("kms")) or l.km
            reg = v.get("registrationDate") or ""
            l.fecha_matriculacion = reg[:10] or l.fecha_matriculacion
            l.matricula = v.get("carPlate") if isinstance(v.get("carPlate"), str) else l.matricula
            l.etiqueta_anuncio = v.get("environmentalLabel") or l.etiqueta_anuncio
            l.anio = to_int(reg[:4]) or l.anio
            l.marca = (v.get("brand") or {}).get("name") or l.marca
            l.modelo = (v.get("model") or {}).get("name")
            l.version = v.get("version") or l.version
            l.titulo = l.version or l.titulo
            l.num_propietarios = to_int(v.get("owners"))
            if v.get("maintenanceBook") is not None:
                l.libro_mantenimiento = bool(v.get("maintenanceBook"))
            itv = (v.get("itv") or {}).get("validDate") if isinstance(v.get("itv"), dict) else None
            if itv:
                l.itv_vigor = True
            w = v.get("warranty") if isinstance(v.get("warranty"), dict) else None
            if w:
                l.garantia_meses = to_int(w.get("dealer")) or to_int(w.get("official")) or None
                if w.get("price"):
                    l.garantia_ampliable = True
                    l.garantia_ampliacion_eur = float(w["price"])
                    l.garantia_ampliacion_meses = 12
            l.carroceria = {"COMPACTO": "compacto", "UTILITARIO": "utilitario"}.get((v.get("bodyStyle") or "").upper(), l.carroceria)
            desc = (v.get("description") or {}).get("long") or ""
            l.descripcion = desc
            l.fecha_publicacion = v.get("createdAt")
        if dealer:
            l.ubicacion = f"{dealer.get('name')} ({dealer.get('city')}, {dealer.get('zip')})"
            from ..geo import coords
            c = coords(dealer.get("zip"), dealer.get("city"), dealer.get("province"))
            if c:
                l.lat, l.lon = c
        m = re.search(r"Transferencia y preparaci[oó]n no incluida:\s*([\d\.]+)\s*€", text)
        if m:
            l.gastos_gestion_eur = float(m.group(1).replace(".", ""))
            l.gastos_incluyen_transferencia = True
        m = re.search(r"Revisi[oó]n de (\d+) puntos", text)
        l.revision_puntos = int(m.group(1)) if m else None
        l.km_certificados = True if re.search(r"Certificado kil[oó]metros reales", rsc) else None
        m = re.search(r"(\d+) d[ií]as o 1\.?000 ?km de prueba", text)
        l.devolucion_dias = int(m.group(1)) if m else None
        # cada foto aparece en varios tamaños: se cuenta el identificador (último segmento) único
        fotos = {u.rsplit("/", 1)[-1] for u in re.findall(r'https://img\.ocasionplus\.com/[^"\\ ]+', rsc)}
        l.num_fotos = len(fotos) or l.num_fotos
        l.garantia = True if (l.garantia_meses or 0) > 0 else l.garantia
        return l
