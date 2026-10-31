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

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        f = self.cfg["filtros"]
        pmax = self.cfg["presupuesto"]["precio_anuncio_max_eur"]
        seen: set[str] = set()
        for marca, models in MODELS.items():
            for modelo, (seg, _aliases) in models.items():
                if seg not in f["carrocerias"]:
                    continue
                mk, md = model_slug(marca, modelo)
                for pg in range(1, min(MAX_PG, self.src_cfg.get("max_paginas", MAX_PG)) + 1):
                    url = f"{BASE}/{mk}/{md}/segunda-mano/valencia/" + (f"?pg={pg}" if pg > 1 else "")
                    try:
                        r = self.client.get(self.name, url)
                    except requests.HTTPError as e:
                        log.info("cochesnet: %s %s no existe (%s)", marca, modelo, e.response.status_code if e.response is not None else e)
                        break
                    p = js_json_parse(r["text"], "window.__INITIAL_PROPS__") or {}
                    s, res = p.get("initialSearch") or {}, p.get("initialResults") or {}
                    veh = (s.get("vehicles") or [{}])[0] if s.get("vehicles") else {}
                    if not veh or not (veh.get("model") or {}).get("id"):
                        log.info("cochesnet: la ruta de %s %s no filtra por modelo; se omite", marca, modelo)
                        break
                    if pg == 1 and (res.get("totalPages") or 0) > MAX_PG:
                        msg = f"{marca} {modelo}: {res.get('totalResults')} anuncios en {res.get('totalPages')} páginas; solo accesibles {MAX_PG}"
                        log.warning("cochesnet cobertura parcial: %s", msg)
                        self.coverage.append(msg)
                    for it in res.get("items") or []:
                        if it["id"] in seen:
                            continue
                        seen.add(it["id"])
                        price, year, km = it.get("price"), it.get("year"), it.get("km")
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
                        break

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
