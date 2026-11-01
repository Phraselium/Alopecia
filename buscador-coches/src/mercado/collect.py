"""Recogida a nivel de LISTADO para el perfil mercado (sin pedir fichas: con las pausas obligatorias, abrir cada ficha
costaría ~20 h por ejecución). Mismas reglas que el perfil personal: robots.txt, pausas 2-5 s, una petición a la vez por
dominio, caché en raw/ y, si hay bloqueo, se registra y se sigue con lo demás (src/http.py).

Fuentes y rutas (todas comprobadas contra robots.txt el 01-11-2026; ver RECONOCIMIENTO.md):
- Coches.net: /segunda-mano/{prov}/, /{marca}/segunda-mano/{prov}/, /{marca}/{modelo}/segunda-mano/{prov}/ (pg <= 6),
  /km-0/{prov}/ y /nuevos/{prov}/ (esta última NO filtra por provincia: muestra nacional de 180 anuncios).
  Los filtros de precio por URL (MaxPrice/MinPrice) están prohibidos por robots.txt: por eso se trocea por marca y modelo.
- AutoScout24: /lst/{marca}?zip=&zipr=&ustate=N,U[&pricefrom=&priceto=] (troceado por precio si hay > 400).
- OcasionPlus: /coches-segunda-mano/valencia?page=N (vehicleList del payload RSC, con precio al contado).
- Flexicar: /coches-valencia/segunda-mano/?page=N (__NEXT_DATA__ initialVehicles, con precio al contado).
"""
from __future__ import annotations

import logging
import re
from typing import Iterator, Optional
from urllib.parse import urlencode

import requests

from ..http import BlockedError, DisallowedError, PoliteClient
from ..normalize import norm_text
from ..sources.common import js_json_parse, next_data, objects_after, rsc_payload, to_int

log = logging.getLogger("mercado")
CN = "https://www.coches.net"
AS = "https://www.autoscout24.es"
CN_OFFER = {0: "ocasion", 1: "nuevo", 2: "km0"}
AS_OFFER = {"U": "ocasion", "N": "nuevo", "D": "km0", "J": "seminuevo", "S": "ocasion", "O": "ocasion"}
AS_SLUGS = {"Citroën": "citroen", "Mercedes-Benz": "mercedes-benz"}


class Counter:
    def __init__(self, client: PoliteClient):
        self.client, self.n = client, 0

    def get(self, plat: str, url: str):
        r = self.client.get(plat, url)
        if not r.get("from_cache"):
            self.n += 1
        return r


def slug(x: str) -> str:
    t = norm_text(x).replace("!", "").replace("'", "").replace("&", "").replace("/", " ").replace(".", "")
    return re.sub(r"\s+", "-", t.strip())


# ------------------------------------------------------------------ Coches.net
def cn_item(it: dict, zona: str, raw_ref: str) -> Optional[dict]:
    if not it.get("id") or not it.get("price"):
        return None
    off = (it.get("offerType") or {}).get("id")
    loc = it.get("location") or {}
    return {"uid": f"cochesnet:{it['id']}", "plataforma": "cochesnet", "zona": zona, "tipo": CN_OFFER.get(off, "ocasion"),
            "marca": it.get("make"), "modelo": it.get("model"), "version": None, "titulo": it.get("title"),
            "anio": it.get("year"), "mes": None, "km": it.get("km") if off != 1 else 0, "precio": it.get("price"),
            "precio_financiado": it.get("financedPrice"), "combustible": it.get("fuelType"), "cambio": None,
            "cv": it.get("hp"), "cc": it.get("cubicCapacity"), "carroceria_raw": f"cn:{it.get('bodyTypeId')}",
            "etiqueta": it.get("environmentalLabel"), "vendedor": "profesional" if it.get("isProfessional") else "particular",
            "garantia_meses": it.get("warrantyMonths"), "ubicacion": loc.get("cityLiteral") or loc.get("regionLiteral"),
            "cp": None, "url": CN + (it.get("url") or ""), "generacion": None, "consumo_wltp": None, "co2": None,
            "descripcion": None, "raw_ref": raw_ref}


def cn_route(c: Counter, path: str, zona: str, max_pg: int, nivel: str = "") -> tuple[int, list[dict]]:
    """Devuelve (total de resultados de la ruta, anuncios de las páginas 1..max_pg).
    nivel = "marca" | "modelo": comprueba que la web ha aplicado el filtro (si no reconoce el slug devuelve el listado
    general, que no se debe contar como de esa marca/modelo)."""
    out, total = [], 0
    for pg in range(1, min(6, max_pg) + 1):
        url = f"{CN}{path}" + (f"?pg={pg}" if pg > 1 else "")
        try:
            r = c.get("cochesnet", url)
        except requests.HTTPError:
            return 0, out
        p = js_json_parse(r["text"], "window.__INITIAL_PROPS__") or {}
        res = p.get("initialResults") or {}
        if pg == 1 and nivel:
            veh = ((p.get("initialSearch") or {}).get("vehicles") or [{}])[0] if (p.get("initialSearch") or {}).get("vehicles") else {}
            if not veh.get("make") or (nivel == "modelo" and not (veh.get("model") or {}).get("id")):
                log.info("cochesnet: %s no aplica el filtro de %s; se omite", path, nivel)
                return 0, []
        total = res.get("totalResults") or total
        items = res.get("items") or []
        out += [a for a in (cn_item(it, zona, r["cache_file"]) for it in items) if a]
        if pg >= (res.get("totalPages") or 1) or not items:
            break
    return total, out


def cochesnet(c: Counter, cfg: dict, zona: str, z: dict) -> Iterator[dict]:
    sc = cfg["fuentes"]["cochesnet"]
    prov = z["provincia_cochesnet"]
    base = z["tipo"] == "base"
    maxpg = sc["paginas_marca"] if base else sc["paginas_referencia"]
    seen: set[str] = set()

    def emit(ads):
        for a in ads:
            if a["uid"] not in seen:
                seen.add(a["uid"])
                yield a
    total, ads = cn_route(c, f"/segunda-mano/{prov}/", zona, maxpg)
    log.info("cochesnet %s: %s anuncios de ocasión en la provincia", zona, total)
    yield from emit(ads)
    if base and sc.get("km0"):
        yield from emit(cn_route(c, f"/km-0/{prov}/", zona, 6)[1])
    if base and sc.get("nuevos"):
        yield from emit([dict(a, zona="nacional") for a in cn_route(c, f"/nuevos/{prov}/", "nacional", 6)[1]])
    for marca in cfg["marcas_cochesnet"]:
        n, ads = cn_route(c, f"/{marca}/segunda-mano/{prov}/", zona, maxpg, "marca")
        if not ads and "-" in marca:     # marcas compuestas: Coches.net puede usar guion bajo (alfa_romeo, land_rover...)
            marca = marca.replace("-", "_")
            n, ads = cn_route(c, f"/{marca}/segunda-mano/{prov}/", zona, maxpg, "marca")
        yield from emit(ads)
        if base and sc.get("rutas_modelo") and n > 180:
            mk = {a["marca"] for a in ads}
            modelos = sorted({a["modelo"] for a in ads if a.get("modelo")} | _modelos_conocidos(marca))
            for mod in modelos:
                m, more = cn_route(c, f"/{marca}/{slug(mod)}/segunda-mano/{prov}/", zona, 6, "modelo")
                yield from emit(more)
            log.info("cochesnet %s %s: %d en la marca; recorridos %d modelos", zona, marca, n, len(modelos))


def _modelos_conocidos(marca_slug: str) -> set[str]:
    from ..normalize import MODELS
    for marca, mods in MODELS.items():
        if slug(marca) == marca_slug:
            return set(mods)
    return set()


# ------------------------------------------------------------------ AutoScout24
def as_item(it: dict, zona: str, raw_ref: str) -> Optional[dict]:
    v, loc, sel, tr = it.get("vehicle") or {}, it.get("location") or {}, it.get("seller") or {}, it.get("tracking") or {}
    price = to_int((it.get("price") or {}).get("priceRaw") or tr.get("price"))
    if not price:
        return None
    reg = tr.get("firstRegistration") or ""
    det = {d.get("iconName"): d.get("data") for d in it.get("vehicleDetails") or []}
    cv = None
    m = re.search(r"\((\d+)\s*CV\)", det.get("speedometer") or "")
    if m:
        cv = int(m.group(1))
    gen = re.search(r"generation_id:(\d*)", tr.get("modelTaxonomy") or "")
    wl = {w.get("iconName") if isinstance(w, dict) else None: w for w in (it.get("wltpValues") or [])}
    cons, co2 = None, None
    for w in it.get("wltpValues") or []:
        txt = str(w.get("data") if isinstance(w, dict) else w)
        mm = re.search(r"([\d,\.]+)\s*l/100", txt)
        if mm:
            cons = float(mm.group(1).replace(",", "."))
        mm = re.search(r"(\d+)\s*g/km", txt)
        if mm:
            co2 = int(mm.group(1))
    return {"uid": f"autoscout24:{it.get('id')}", "plataforma": "autoscout24", "zona": zona,
            "tipo": AS_OFFER.get(v.get("offerType"), "ocasion"), "marca": v.get("make"), "modelo": v.get("model"),
            "version": v.get("modelVersionInput"), "titulo": f"{v.get('make')} {v.get('model')} {v.get('modelVersionInput') or ''}".strip(),
            "anio": to_int(reg[-4:]), "mes": to_int(reg[:2]) if "-" in reg else None, "km": to_int(tr.get("mileage")),
            "precio": price, "precio_financiado": None, "combustible": v.get("fuel"), "cambio": v.get("transmission"),
            "cv": cv, "cc": to_int(v.get("engineDisplacementInCCM")), "carroceria_raw": None, "etiqueta": None,
            "vendedor": "profesional" if sel.get("type") == "Dealer" else "particular", "garantia_meses": None,
            "ubicacion": loc.get("city"), "cp": loc.get("zip"), "url": AS + (it.get("url") or ""),
            "generacion": gen.group(1) if gen and gen.group(1) else None, "consumo_wltp": cons, "co2": co2,
            "descripcion": None, "raw_ref": raw_ref}


def as_query(c: Counter, marca_slug: str, params: dict, zona: str, maxpg: int) -> tuple[int, list[dict]]:
    out, total = [], 0
    for page in range(1, maxpg + 1):
        q = dict(params, page=page) if page > 1 else params
        r = c.get("autoscout24", f"{AS}/lst/{marca_slug}?{urlencode(q)}")
        pp = (next_data(r["text"]) or {}).get("props", {}).get("pageProps", {})
        total = pp.get("numberOfResults") or total
        items = [it for it in pp.get("listings") or [] if it.get("searchResultType") in (None, "Organic")]
        out += [a for a in (as_item(it, zona, r["cache_file"]) for it in items) if a]
        if page >= (pp.get("numberOfPages") or 1) or not items:
            break
    return total, out


def autoscout24(c: Counter, cfg: dict, zona: str, z: dict) -> Iterator[dict]:
    from ..normalize import MODELS
    sc = cfg["fuentes"]["autoscout24"]
    base = z["tipo"] == "base"
    maxpg = sc["paginas_max"] if base else sc["paginas_referencia"]
    marcas = sorted({AS_SLUGS.get(m, slug(m)) for m in MODELS} | set(cfg["marcas_cochesnet"]))
    seen: set[str] = set()
    desde = sc.get("desde_marca")
    for ms in marcas:
        if desde and ms < desde:
            continue
        try:
            yield from _as_marca(c, cfg, sc, z, zona, ms, base, maxpg, seen)
        except requests.HTTPError as e:      # un 502 puntual no debe cortar el resto de marcas
            log.warning("autoscout24 %s %s: %s; se salta la marca", zona, ms, e)


def _as_marca(c, cfg, sc, z, zona, ms, base, maxpg, seen):
    if True:
        params = {"atype": "C", "cy": "E", "ustate": "N,U", "zip": z["as24_zip"], "zipr": z["as24_radio_km"], "sort": "standard"}
        total, ads = as_query(c, ms, params, zona, 1)
        tramos = [(None, None)]
        if total > 400 and base:
            t = sc["tramos_precio"]
            tramos = list(zip(t[:-1], t[1:]))
        for lo, hi in tramos:
            q = dict(params)
            if lo is not None:
                q.update(pricefrom=lo, priceto=hi)
                _, ads = as_query(c, ms, q, zona, maxpg)
            elif maxpg > 1:
                _, ads = as_query(c, ms, q, zona, maxpg)
            for a in ads:
                # zona = provincia: el radio es amplio y se filtra por el prefijo del código postal
                if a["uid"] in seen or not str(a.get("cp") or "").startswith(z["cp_prefijo"]):
                    continue
                seen.add(a["uid"])
                yield a
        if total:
            log.info("autoscout24 %s %s: %d resultados en el radio", zona, ms, total)


# ------------------------------------------------------------------ OcasionPlus y Flexicar (solo Valencia)
def ocasionplus(c: Counter, cfg: dict, zona: str, z: dict) -> Iterator[dict]:
    if zona != "valencia":
        return
    seen: set[str] = set()
    for page in range(1, cfg["fuentes"]["ocasionplus"]["paginas_max"] + 1):
        url = "https://www.ocasionplus.com/coches-segunda-mano/valencia" + (f"?page={page}" if page > 1 else "")
        r = c.get("ocasionplus", url)
        vl = next(objects_after(rsc_payload(r["text"]), r'"vehicleList":\{'), None) or {}
        data = vl.get("data") or []
        new = [d for d in data if d.get("slug") not in seen]
        if not new:
            break
        for d in new:
            seen.add(d.get("slug"))
            ch, pr, dl = d.get("characteristics") or {}, d.get("price") or {}, d.get("dealer") or {}
            eng = ch.get("engine") or {}
            year = to_int(re.search(r"-(\d{4})-[a-z0-9]+$", d.get("slug") or "").group(1)) if re.search(r"-(\d{4})-[a-z0-9]+$", d.get("slug") or "") else None
            yield {"uid": f"ocasionplus:{(d.get('slug') or '').split('-')[-1]}", "plataforma": "ocasionplus", "zona": zona,
                   "tipo": "km0" if d.get("condition") == "KM0" else ("nuevo" if d.get("condition") == "NEW" else "ocasion"),
                   "marca": d.get("brand"), "modelo": d.get("model"), "version": (d.get("description") or {}).get("short"),
                   "titulo": (d.get("description") or {}).get("short") or f"{d.get('brand')} {d.get('model')}",
                   "anio": year, "mes": None, "km": ch.get("kms"), "precio": pr.get("cash") or pr.get("withoutFinancing"),
                   "precio_financiado": pr.get("withFinancing"), "combustible": eng.get("fuel"), "cambio": eng.get("transmission"),
                   "cv": eng.get("cv"), "cc": None, "carroceria_raw": f"op:{d.get('bodyStyle')}", "etiqueta": ch.get("environmentalLabel"),
                   "vendedor": "profesional", "garantia_meses": 12, "ubicacion": dl.get("city"), "cp": dl.get("zip"),
                   "url": f"https://www.ocasionplus.com/coches-segunda-mano/{d.get('slug')}", "generacion": None,
                   "consumo_wltp": None, "co2": None, "descripcion": None, "raw_ref": r["cache_file"]}


def flexicar(c: Counter, cfg: dict, zona: str, z: dict) -> Iterator[dict]:
    if zona != "valencia":
        return
    vistos_pag: set = set()
    for page in range(1, cfg["fuentes"]["flexicar"]["paginas_max"] + 1):
        url = "https://www.flexicar.es/coches-valencia/segunda-mano/" + (f"?page={page}" if page > 1 else "")
        r = c.get("flexicar", url)
        vs = ((next_data(r["text"]) or {}).get("props", {}).get("pageProps", {}) or {}).get("initialVehicles") or []
        # Flexicar ignora ?page= (el resto del listado se carga desde /api/, prohibido por robots.txt): solo la 1.ª página
        ids = tuple(v.get("id") for v in vs)
        if not vs or ids in vistos_pag:
            return
        vistos_pag.add(ids)
        for v in vs:
            yield {"uid": f"flexicar:{v.get('id')}", "plataforma": "flexicar", "zona": zona,
                   "tipo": "km0" if v.get("km") is not None and v.get("km") < 100 else "ocasion",
                   "marca": v.get("brand"), "modelo": v.get("model"), "version": v.get("version"),
                   "titulo": f"{v.get('brand')} {v.get('model')} {v.get('version') or ''}".strip(), "anio": v.get("year"),
                   "mes": None, "km": v.get("km"), "precio": v.get("cashPrice") or v.get("price"),
                   "precio_financiado": v.get("price"), "combustible": v.get("fuel"), "cambio": v.get("transmission"),
                   "cv": to_int(v.get("power") or v.get("hp")), "cc": None, "carroceria_raw": f"fx:{v.get('bodyType') or v.get('body')}",
                   "etiqueta": v.get("ecoSticker"), "vendedor": "profesional", "garantia_meses": 12,
                   "ubicacion": f"Flexicar {v.get('carDealership')}", "cp": None,
                   "url": f"https://www.flexicar.es/{v.get('slug')}/", "generacion": None, "consumo_wltp": None, "co2": None,
                   "descripcion": None, "raw_ref": r["cache_file"]}
        if len(vs) < 12:
            return


FUENTES = {"cochesnet": cochesnet, "autoscout24": autoscout24, "ocasionplus": ocasionplus, "flexicar": flexicar}


def collect_one(fuente: str, client: PoliteClient, cfg: dict, store, zonas: list[str]) -> dict:
    """Recoge una fuente en las zonas pedidas. Guarda por bloques para no perder datos si se corta."""
    import time
    res = {}
    for zona in zonas:
        z = cfg["zonas"][zona]
        started = time.strftime("%Y-%m-%dT%H:%M:%S")
        c = Counter(client)
        buf, vistos, estado, det = [], set(), "ok", ""
        try:
            for a in FUENTES[fuente](c, cfg, zona, z):
                buf.append(a)
                vistos.add(a["uid"])
                if len(buf) >= 200:
                    store.upsert(buf)
                    buf = []
        except BlockedError as e:
            estado, det = "bloqueado", str(e)
        except DisallowedError as e:
            estado, det = "robots", str(e)
        except Exception as e:  # noqa: BLE001
            estado, det = "error", repr(e)
            log.exception("mercado: error en %s %s", fuente, zona)
        store.upsert(buf)
        if estado == "ok" and z["tipo"] == "base":
            store.mark_missing(fuente, zona, vistos)
        store.log_run(started, fuente, zona, estado, len(vistos), c.n, det)
        res[zona] = (estado, len(vistos), c.n, det)
        log.info("mercado %s %s: %s, %d anuncios, %d peticiones", fuente, zona, estado, len(vistos), c.n)
    return res
