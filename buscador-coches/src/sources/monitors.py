"""Profesionales sin stock en el rango a 31-10-2026: vigilancia con el filtro de precio de cada web.

Cada una hace 1-2 peticiones por ejecución. Si aparece algo <= precio máximo, se recoge con los datos
del listado (precio al contado y financiado incluidos). Ver RECONOCIMIENTO.md.
"""
from __future__ import annotations

import logging
import re
from typing import Iterator, Optional

from bs4 import BeautifulSoup

from ..models import Listing
from .base import Source
from .common import js_json_parse, next_data, to_int

log = logging.getLogger("monitors")


def _pmax(cfg):
    return cfg["presupuesto"]["precio_anuncio_max_eur"]


class Flexicar(Source):
    name = "flexicar"
    metodo = "__NEXT_DATA__ con ?priceTo= (filtro del servidor)"
    estado = "ok"

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        pmax = _pmax(self.cfg)
        for page in range(1, 6):
            url = f"https://www.flexicar.es/coches-valencia/segunda-mano/?priceTo={pmax}" + (f"&page={page}" if page > 1 else "")
            r = self.client.get(self.name, url)
            pp = (next_data(r["text"]) or {}).get("props", {}).get("pageProps", {})
            vs = pp.get("initialVehicles") or []
            log.info("flexicar: %s coches <= %s € en Valencia (página %d)", pp.get("countVehicles"), pmax, page)
            if not vs:
                return
            for v in vs:
                cash, fin = v.get("cashPrice"), v.get("price")
                yield Listing(
                    plataforma=self.name, id_externo=str(v["id"]), url=f"https://www.flexicar.es/{v.get('slug')}/",
                    titulo=f"{v.get('brand')} {v.get('model')} {v.get('version') or ''}".strip(),
                    precio=float(cash or fin), precio_contado=cash, precio_financiado=fin,
                    solo_financiando=bool(cash and fin and fin < cash),
                    marca=v.get("brand"), modelo=v.get("model"), version=v.get("version"),
                    combustible=v.get("fuel"), anio=v.get("year"), km=v.get("km"), cambio=v.get("transmission"),
                    vendedor="profesional", ubicacion=f"Flexicar {v.get('carDealership')}",
                    num_fotos=len(v.get("images") or []) or None, fuente_dato=url, raw_ref=r["cache_file"])
            if len(vs) < 12:
                return

    def needs_detail(self, l):
        return False


class Clicars(Source):
    name = "clicars"
    metodo = "HTML (listado ordenado por precio ascendente)"
    estado = "ok"

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        pmax = _pmax(self.cfg)
        url = "https://www.clicars.com/coches-segunda-mano-ocasion?order=price.asc"
        r = self.client.get(self.name, url)
        soup = BeautifulSoup(r["text"], "html.parser")
        for a in soup.select("a[data-vehicle-web-id]"):
            parts = a.get_text(" | ", strip=True).split(" | ")
            # precios del coche (las cuotas "164€ /mes" se excluyen: < 1.000 €)
            prices = [x for x in (to_int(p) for p in parts if re.fullmatch(r"[\d\.]+€", p)) if x and x >= 1000]
            if not prices:
                continue
            cash, fin = prices[0], (prices[1] if len(prices) > 1 else None)
            if min(x for x in prices if x) > pmax:
                return  # ordenado por precio: el resto es más caro
            year = next((to_int(p) for p in parts if re.fullmatch(r"(19|20)\d\d", p)), None)
            km = next((to_int(p) for p in parts if p.endswith("km")), None)
            yield Listing(
                plataforma=self.name, id_externo=a["data-vehicle-web-id"], url=a["href"],
                titulo=a.get("data-analytics-vehicle-maker", "") + " " + a.get("data-analytics-vehicle-model", ""),
                marca=a.get("data-analytics-vehicle-maker"), modelo=a.get("data-analytics-vehicle-model"),
                precio=float(cash), precio_contado=cash, precio_financiado=fin, solo_financiando=bool(fin and fin < cash),
                anio=year, km=km, vendedor="profesional", ubicacion="Clicars (entrega a domicilio)",
                descripcion=" ".join(parts), fuente_dato=url, raw_ref=r["cache_file"])

    def needs_detail(self, l):
        return False


class Autohero(Source):
    name = "autohero"
    metodo = "__APOLLO_STATE__ con ?priceMax= y orden por precio"
    estado = "ok"

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        pmax = _pmax(self.cfg)
        url = f"https://www.autohero.com/es/search/?priceMax={pmax}&sort=PRICE_ASC"
        r = self.client.get(self.name, url)
        st = js_json_parse(r["text"], "window.__APOLLO_STATE__") or {}
        rq = st.get("ROOT_QUERY", {})
        res = next((v for k, v in rq.items() if k.startswith("searchAdV9AdsV2")), {}) or {}
        log.info("autohero: %s coches <= %s €", res.get("total"), pmax)
        for a in res.get("data") or []:
            cash = (a.get("offerPrice") or {}).get("amountMinorUnits")
            fin = (a.get("financedPrice") or {}).get("amountMinorUnits")
            cash = cash / 100 if cash else None
            fin = fin / 100 if fin else None
            yield Listing(
                plataforma=self.name, id_externo=a["id"], url=f"https://www.autohero.com/es/{a['id']}/",
                titulo=f"{a.get('manufacturer')} {a.get('model')} {a.get('subType') or ''}".strip(),
                marca=a.get("manufacturer"), modelo=a.get("model"), version=a.get("subType"),
                precio=cash, precio_contado=cash, precio_financiado=fin, solo_financiando=bool(fin and cash and fin < cash),
                anio=a.get("firstRegistrationYear") or a.get("builtYear"), km=(a.get("mileage") or {}).get("distance"),
                vendedor="profesional", ubicacion="Autohero (entrega a domicilio)", fuente_dato=url, raw_ref=r["cache_file"])

    def needs_detail(self, l):
        return False


class Renew(Source):
    name = "renew"
    metodo = "window.APP_STATE (facets con precio mínimo)"
    estado = "ok"

    def search(self, since: Optional[str] = None) -> Iterator[Listing]:
        pmax = _pmax(self.cfg)
        url = "https://es.renew.auto/vehiculos.html"
        r = self.client.get(self.name, url)
        st = js_json_parse(r["text"], "window.APP_STATE") or {}
        zone = next((z.get("data") for z in st.get("page", {}).get("data", {}).get("content", {})
                     .get("contentZone", {}).values() if isinstance(z, dict) and isinstance(z.get("data"), dict)
                     and "facets" in z["data"]), None) or {}
        facets = {f.get("name"): f for f in zone.get("facets") or []}
        pmin = ((facets.get("prices.customerDisplayPrice_min") or {}).get("min") or {}).get("value")
        log.info("renew: precio mínimo en España %s € (máx. buscado %s €)", pmin, pmax)
        if pmin is not None and pmin > pmax:
            return
        for v in zone.get("data") or []:
            price = ((v.get("prices") or [{}])[0]).get("customerDisplayPrice")
            if price is None or price > pmax:
                continue
            site = v.get("vehicleExhibitionSite") or {}
            geo = site.get("geolocalization") or {}
            yield Listing(
                plataforma=self.name, id_externo=v.get("identifier"), url="https://es.renew.auto/vehiculos.html",
                titulo=f"{(v.get('brand') or {}).get('label')} {(v.get('model') or {}).get('label')} {v.get('version', {}).get('label', '') if isinstance(v.get('version'), dict) else ''}",
                marca=(v.get("brand") or {}).get("label"), modelo=(v.get("model") or {}).get("label"),
                precio=float(price), precio_contado=price, km=v.get("mileage"), anio=to_int((v.get("firstRegistrationDate") or "")[:4]),
                vendedor="profesional", garantia_meses=(v.get("warrantyInfo") or {}).get("duration"),
                ubicacion=f"{site.get('name')} ({(site.get('address') or {}).get('locality')})",
                lat=geo.get("lat"), lon=geo.get("lon"), fuente_dato=url, raw_ref=r["cache_file"])

    def needs_detail(self, l):
        return False
