"""AutoScout24 España.

Método (ver RECONOCIMIENTO.md): robots.txt prohíbe /lst?... pero permite /lst/{marca}?filtros&page=N.
Los resultados vienen en __NEXT_DATA__ (pageProps.listings, 20 por página) con filtros aplicados en el
servidor (CP + radio, precio, año, km). La ficha /anuncios/... trae descripción, garantía y datos técnicos.
"""
from __future__ import annotations

import logging
from typing import Iterator, Optional
from urllib.parse import urlencode

from ..models import Listing
from ..normalize import MODELS, norm_text
from .base import Source
from .common import next_data, to_int

log = logging.getLogger("autoscout24")
BASE = "https://www.autoscout24.es"
SLUGS = {"Citroën": "citroen", "Volkswagen": "volkswagen", "Mercedes-Benz": "mercedes-benz"}
FUEL = {"B": "gasolina", "D": "diesel", "L": "glp", "2": "hibrido", "E": "electrico", "C": "gnc", "O": None}


class AutoScout24(Source):
    name = "autoscout24"
    metodo = "__NEXT_DATA__ por marca con filtros en la URL"
    estado = "ok"

    def _params(self, page: int) -> dict:
        f, u = self.cfg["filtros"], self.cfg["ubicacion"]
        p = {"atype": "C", "cy": "E", "ustate": "U", "damaged_listing": "exclude",
             "priceto": self.cfg["presupuesto"]["precio_anuncio_max_eur"], "fregfrom": f["anio_min"],
             "kmto": f["km_max"], "zip": "46001", "zipr": u["radio_km"], "sort": "age", "desc": 1}
        if page > 1:
            p["page"] = page
        return p

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        for marca in MODELS:
            slug = SLUGS.get(marca, norm_text(marca).replace(" ", "-"))
            for page in range(1, self.src_cfg.get("max_paginas", 10) + 1):
                url = f"{BASE}/lst/{slug}?{urlencode(self._params(page))}"
                r = self.client.get(self.name, url)
                pp = (next_data(r["text"]) or {}).get("props", {}).get("pageProps", {})
                items = pp.get("listings") or []
                if page == 1:
                    log.info("autoscout24 %s: %s resultados", marca, pp.get("numberOfResults"))
                for it in items:
                    if it.get("searchResultType") not in (None, "Organic"):
                        continue
                    v, loc, sel = it.get("vehicle") or {}, it.get("location") or {}, it.get("seller") or {}
                    reg = (it.get("tracking") or {}).get("firstRegistration") or ""
                    self.observe(it["id"], v.get("make"), v.get("model"), it.get("title"), to_int(reg[-4:]),
                                 to_int(v.get("mileageInKm")), (it.get("price") or {}).get("priceRaw"))
                    yield Listing(
                        plataforma=self.name, id_externo=it["id"], url=BASE + it["url"],
                        titulo=f"{v.get('make')} {v.get('model')} {v.get('modelVersionInput') or ''}".strip(),
                        precio=float((it.get("price") or {}).get("priceRaw") or 0) or None,
                        marca=v.get("make"), modelo=v.get("model"),
                        version=" ".join(x for x in (v.get("modelVersionInput"), v.get("motorTypeName")) if x),
                        combustible=v.get("fuel"), anio=to_int(reg[-4:]), km=to_int(v.get("mileageInKm")),
                        fecha_matriculacion=reg or None,
                        cambio=v.get("transmission"), cilindrada_cc=to_int(v.get("engineDisplacementInCCM")),
                        vendedor="profesional" if sel.get("type") == "Dealer" else "particular",
                        ubicacion=f"{loc.get('city')} ({loc.get('zip')})", num_fotos=len(it.get("images") or []),
                        fuente_dato=url, raw_ref=r["cache_file"])
                if page >= (pp.get("numberOfPages") or 1) or not items:
                    break

    def needs_detail(self, l: Listing) -> bool:
        return True

    def detail(self, l: Listing) -> Listing:
        r = self.client.get(self.name, l.url)
        det = ((next_data(r["text"]) or {}).get("props", {}).get("pageProps", {}) or {}).get("listingDetails") or {}
        if not det:
            return l
        v, sel, loc = det.get("vehicle") or {}, det.get("seller") or {}, det.get("location") or {}
        l.raw_ref = r["cache_file"]
        l.fuente_dato = f"{l.url} (__NEXT_DATA__ listingDetails)"
        l.descripcion = det.get("description") or ""
        l.km = v.get("mileageInKmRaw") or l.km
        fr = v.get("firstRegistrationDateRaw") or ""
        l.fecha_matriculacion = fr[:7] or l.fecha_matriculacion   # AS24 guarda mes/año (día = 01)
        l.matricula = v.get("licensePlate") or l.matricula
        l.anio = to_int(fr[:4]) or l.anio
        l.cilindrada_cc = v.get("rawDisplacementInCCM") or l.cilindrada_cc
        l.potencia_cv = v.get("rawPowerInHp") or l.potencia_cv
        l.cambio = v.get("transmissionType") or l.cambio
        fuel = ((v.get("fuelCategory") or {}).get("raw"))
        l.combustible = FUEL.get(fuel, l.combustible) or l.combustible
        l.vendedor = "profesional" if sel.get("isDealer") else "particular"
        if sel.get("companyName"):
            l.ubicacion = f"{sel['companyName']} — {loc.get('city')} ({loc.get('zip')})"
        if loc.get("latitude") and loc.get("longitude"):
            l.lat, l.lon = loc["latitude"], loc["longitude"]
        else:
            from ..geo import coords
            c = coords(loc.get("zip"), loc.get("city"))
            if c:
                l.lat, l.lon = c
        l.num_fotos = len(det.get("images") or []) or l.num_fotos
        w = det.get("warranty")
        if det.get("warrantyExists") or w:
            l.garantia = True
            months = to_int(w.get("duration") if isinstance(w, dict) else w)
            l.garantia_meses = months if months and months < 121 else l.garantia_meses
        return l
