"""Coches.net (Adevinta).

Método (ver RECONOCIMIENTO.md): robots.txt prohíbe todos los filtros por parámetro y pg>=7. Se recorren
las rutas permitidas /{marca}/{modelo}/segunda-mano/valencia/?pg=N (N<=6, 35 por página, provincia 46)
con los datos en window.__INITIAL_PROPS__, se filtra aquí precio/año/km y se abre la ficha
(…-covo.aspx, permitida) de los candidatos para descripción, garantía y vendedor.
Cobertura: si un modelo tiene más de 6 páginas en Valencia, el resto no es accesible (se registra).
"""
from __future__ import annotations

import logging
import re
from typing import Iterator, Optional

import requests

from ..models import Listing
from ..normalize import MODELS, norm_text
from .base import Source
from .common import js_json_parse, to_int

log = logging.getLogger("cochesnet")
BASE = "https://www.coches.net"
MAX_PG = 6


def model_slug(marca: str, modelo: str) -> tuple[str, str]:
    mk = norm_text(marca).replace(" ", "-")
    md = norm_text(modelo).replace("!", "").replace("'", "").replace(" ", "-")
    if mk == "mazda" and md.isdigit():
        md = f"mazda{md}"
    return mk, md


class CochesNet(Source):
    name = "cochesnet"
    metodo = "window.__INITIAL_PROPS__ por ruta marca/modelo/provincia"
    estado = "ok"
    coverage: list[str] = []

    def _route(self, path: str, seen: set, check_model: bool) -> Iterator[Listing]:
        """Recorre una ruta permitida hasta pg=6. Devuelve los candidatos; registra el resto como mercado."""
        f = self.cfg["filtros"]
        pmax = self.cfg["presupuesto"]["precio_anuncio_max_eur"]
        for pg in range(1, min(MAX_PG, self.src_cfg.get("max_paginas", MAX_PG)) + 1):
            url = f"{BASE}{path}" + (f"?pg={pg}" if pg > 1 else "")
            try:
                r = self.client.get(self.name, url)
            except requests.HTTPError as e:
                log.info("cochesnet: %s no existe (%s)", path, e.response.status_code if e.response is not None else e)
                return
            except requests.RequestException as e:
                log.warning("cochesnet: error de red en %s (%s); se salta esta ruta", url, e)
                self.coverage.append(f"{path}: error de red, omitida")
                return
            p = js_json_parse(r["text"], "window.__INITIAL_PROPS__") or {}
            s, res = p.get("initialSearch") or {}, p.get("initialResults") or {}
            if check_model:
                veh = (s.get("vehicles") or [{}])[0] if s.get("vehicles") else {}
                if not veh or not (veh.get("model") or {}).get("id"):
                    log.info("cochesnet: la ruta %s no filtra por modelo; se omite", path)
                    return
            if pg == 1 and (res.get("totalPages") or 0) > MAX_PG:
                self.coverage.append(f"{path}: {res.get('totalResults')} anuncios en {res.get('totalPages')} páginas; accesibles {MAX_PG}")
            for it in res.get("items") or []:
                if it["id"] in seen:
                    continue
                seen.add(it["id"])
                price, year, km = it.get("price"), it.get("year"), it.get("km")
                self.observe(it["id"], it.get("make"), it.get("model"), it.get("title"), year, km, price)
                if not price or price > pmax or (year and year < f["anio_min"]) or (km and km > f["km_max"]):
                    continue
                loc = it.get("location") or {}
                yield Listing(
                    plataforma=self.name, id_externo=str(it["id"]), url=BASE + it["url"], titulo=it.get("title") or "",
                    precio=float(price), precio_contado=price, precio_financiado=it.get("financedPrice"),
                    marca=it.get("make"), modelo=it.get("model"), combustible=it.get("fuelType"),
                    anio=year, km=km, vendedor="profesional" if it.get("isProfessional") else "particular",
                    garantia=bool(it.get("hasWarranty")) if it.get("hasWarranty") is not None else None,
                    garantia_meses=it.get("warrantyMonths"), km_certificados=True if it.get("isCertified") else None,
                    ubicacion=loc.get("cityLiteral"), num_fotos=len(it.get("photos") or []) or None,
                    etiqueta_dgt=it.get("environmentalLabel"), fecha_publicacion=it.get("publicationDate"),
                    fuente_dato=url, raw_ref=r["cache_file"])
            if pg >= (res.get("totalPages") or 1):
                return

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        from ..fraud import segmentos_admitidos
        segs = segmentos_admitidos(self.cfg)
        seen: set[str] = set()
        self.coverage = []
        for prov in self.cfg["ubicacion"].get("provincias_cochesnet", ["valencia"]):
            for marca, models in MODELS.items():
                if not any(seg in segs for seg, _a in models.values()):
                    continue
                mk = model_slug(marca, "x")[0]
                # 1) ruta por marca (otro orden de relevancia: añade anuncios de modelos con más de 6 páginas)
                yield from self._route(f"/{mk}/segunda-mano/{prov}/", seen, check_model=False)
                # 2) rutas por modelo
                for modelo, (seg, _aliases) in models.items():
                    if seg not in segs:
                        continue
                    _, md = model_slug(marca, modelo)
                    yield from self._route(f"/{mk}/{md}/segunda-mano/{prov}/", seen, check_model=True)
        self.vistos_ids = seen

    def needs_detail(self, l: Listing) -> bool:
        return True

    def detail(self, l: Listing) -> Listing:
        r = self.client.get(self.name, l.url)
        p = js_json_parse(r["text"], "window.__INITIAL_PROPS__") or {}
        ad, seller = p.get("ad") or {}, p.get("seller") or {}
        if not ad:
            return l
        l.raw_ref = r["cache_file"]
        l.fuente_dato = f"{l.url} (window.__INITIAL_PROPS__.ad)"
        l.descripcion = ad.get("description") or ""
        l.version = ad.get("version") or l.version
        l.cambio = {"COMMON.TRANSMISSION_MANUAL": "manual", "COMMON.TRANSMISSION_AUTOMATIC": "automatico"}.get(
            ad.get("transmissionType"), l.cambio)
        l.anio = ad.get("year") or l.anio
        l.km = ad.get("km") or l.km
        l.precio_financiado = ad.get("financedPrice") or l.precio_financiado
        if ad.get("warrantyMonths"):
            l.garantia_meses = ad["warrantyMonths"]
            l.garantia = True
        if seller.get("isDealer") is not None:
            l.vendedor = "profesional" if seller.get("isDealer") else "particular"
        dl = ((seller.get("dealer") or {}).get("location") or {})
        city = dl.get("city") or l.ubicacion
        if dl.get("city"):
            l.ubicacion = f"{(seller.get('dealer') or {}).get('name') or ''} {dl.get('city')}".strip()
        if (p.get("vehicleHistory") or {}).get("hasReport"):
            l.libro_mantenimiento = l.libro_mantenimiento or None
        feats = [x if isinstance(x, str) else x.get("title", "") for x in (p.get("vehicleCertification") or {}).get("features") or []]
        if any(re.search(r"kil[oó]metr|km", f, re.I) for f in feats):
            l.km_certificados = True
        from ..geo import coords
        c = coords(None, city, "Valencia")
        if c:
            l.lat, l.lon = c
        l.num_fotos = len(ad.get("photos") or []) or l.num_fotos
        return l
