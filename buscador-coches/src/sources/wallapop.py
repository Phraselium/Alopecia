"""Wallapop (coches) — opción A: solo rutas permitidas por robots.txt.

robots.txt prohíbe /search y cualquier URL con '?'. Se usan las páginas de categoría por modelo y
ciudad /coches-segunda-mano/{marca}-{modelo}/valencia (__NEXT_DATA__ → seoLandingData.items, ~80
anuncios cercanos, sin paginación) y la ficha /item/{slug} (__NEXT_DATA__ → item, itemSeller).
No se usa la API interna api.wallapop.com (ver RECONOCIMIENTO.md).
"""
from __future__ import annotations

import logging
from typing import Iterator, Optional

import requests

from ..models import Listing
from ..normalize import MODELS, norm_text
from .base import Source
from .common import next_data, to_int

log = logging.getLogger("wallapop")
BASE = "https://es.wallapop.com"
FUEL = {"gasoline": "gasolina", "gasoil": "diesel", "hybrid": "hibrido", "electric": "electrico", "lpg": "glp", "others": None}
BODY = {"small_car": "utilitario", "compact": "compacto", "sedan": None, "family": None}


class Wallapop(Source):
    name = "wallapop"
    metodo = "__NEXT_DATA__ de páginas de categoría por modelo/ciudad + ficha /item/"
    estado = "ok"

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        f = self.cfg["filtros"]
        pmax = self.cfg["presupuesto"]["precio_anuncio_max_eur"]
        pmin = self.cfg["presupuesto"].get("precio_anuncio_min_eur", 0)
        seen: set[str] = set()
        for marca, models in MODELS.items():
            for modelo, (seg, _a) in models.items():
                if seg not in f["carrocerias"]:
                    continue
                md = norm_text(modelo).replace("!", "").replace(" ", "-")
                slug = f"{norm_text(marca).replace(' ', '-')}-{md}"
                url = f"{BASE}/coches-segunda-mano/{slug}/valencia"
                try:
                    r = self.client.get(self.name, url)
                except requests.HTTPError as e:
                    log.info("wallapop: %s no existe (%s)", url, e)
                    continue
                pp = (next_data(r["text"]) or {}).get("props", {}).get("pageProps", {})
                items = (pp.get("seoLandingData") or {}).get("items") or []
                for it in items:
                    if it.get("id") in seen or it.get("sold") or it.get("reserved"):
                        continue
                    seen.add(it.get("id"))
                    car = it.get("itemCar") or {}
                    price, year, km = it.get("price"), to_int(car.get("year")), to_int(car.get("km"))
                    if marca.lower() in norm_text(it.get("title", "")) or norm_text(modelo) in norm_text(it.get("title", "")):
                        self.observe(it["id"], marca, modelo, it.get("title"), year, km, price)
                    if not price or price > pmax or price < pmin or (year and year < f["anio_min"]) or (km and km > f["km_max"]):
                        continue
                    if marca.lower() not in norm_text(it.get("title", "")) and norm_text(modelo) not in norm_text(it.get("title", "")):
                        continue  # resultados "parecidos" de otras marcas
                    yield Listing(
                        plataforma=self.name, id_externo=str(it["id"]), url=f"{BASE}/item/{it['slugId']}",
                        titulo=it.get("title") or "", precio=float(price), anio=year, km=km,
                        combustible=car.get("engineLabel"), cambio=car.get("gearboxLabel"),
                        descripcion=it.get("description") or "", num_fotos=len(it.get("images") or []) or None,
                        garantia=True if it.get("hasWarranty") else None, fuente_dato=url, raw_ref=r["cache_file"])

    def needs_detail(self, l: Listing) -> bool:
        return True

    def detail(self, l: Listing) -> Listing:
        r = self.client.get(self.name, l.url)
        pp = (next_data(r["text"]) or {}).get("props", {}).get("pageProps", {})
        it, sel = pp.get("item") or {}, pp.get("itemSeller") or {}
        if not it:
            return l
        ci = it.get("carInfo") or {}

        def val(k):
            return (ci.get(k) or {}).get("value")
        l.raw_ref = r["cache_file"]
        l.fuente_dato = f"{l.url} (__NEXT_DATA__ item)"
        l.titulo = (it.get("title") or {}).get("original") or l.titulo
        l.descripcion = (it.get("description") or {}).get("original") or l.descripcion
        l.marca, l.modelo = it.get("brand") or l.marca, it.get("model") or l.modelo
        l.version = val("version") or l.version
        l.km = to_int(val("km")) or l.km
        l.anio = to_int(val("year")) or l.anio
        l.potencia_cv = to_int(val("horsePower")) or l.potencia_cv
        l.cambio = {"manual": "manual", "automatic": "automatico"}.get(val("gearBox"), l.cambio)
        l.combustible = FUEL.get(val("engine"), l.combustible) or l.combustible
        l.carroceria = BODY.get(val("bodyType"), l.carroceria)
        if (ci.get("warranty") or {}).get("value"):
            l.garantia = True
        price = ((it.get("price") or {}).get("cash") or {}).get("amount")
        l.precio = float(price) if price else l.precio
        loc = it.get("location") or {}
        l.lat, l.lon = loc.get("latitude"), loc.get("longitude")
        l.ubicacion = f"{loc.get('city')} ({loc.get('postalCode')})"
        l.vendedor = "profesional" if (sel.get("type") or "").lower() in ("professional", "pro", "featured") else "particular"
        md = it.get("modifiedDate")
        if md:
            import datetime as dt
            l.fecha_publicacion = dt.datetime.fromtimestamp(md / 1000).isoformat(timespec="seconds")
        l.num_fotos = len(it.get("images") or []) or l.num_fotos
        return l
