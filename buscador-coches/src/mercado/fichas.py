"""Revisión de fichas de los mejores candidatos del perfil mercado.

El análisis compara anuncios a nivel de listado (sin descripción). Para que el Top y la frontera no recomienden coches con
problemas declarados, se abre la ficha (rutas permitidas por robots.txt, con las pausas y la caché del cliente educado) de los
mejores candidatos de cada franja y se lee: disponibilidad, descripción y equipamiento. Resultado en data/mercado_fichas.json:
- descartar: anuncio retirado/vendido, avería declarada (src/averias.py, con negaciones), sin aire acondicionado.
- aviso: ITV caducada o pendiente, fuera de la provincia de Valencia, carrocería a reparar, otros puntos a revisar.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

import requests

from ..averias import analizar
from ..normalize import norm_text
from ..sources.common import js_json_parse, next_data

SIN_AC = [r"\bsin (el )?(aire|a/?a|a/c|aire acondicionado|climatizador|clima)\b",
          r"\bno (tiene|lleva|dispone de) (el )?(aire|a/?a|a/c|aire acondicionado|climatizador)\b",
          r"\b(aire|a/?a|a/c|climatizador|clima)( acondicionado)? no (funciona|enfria|va)\b",
          r"\b(necesita|falta|le falta) (una )?(carga de )?(gas|aire)\b"]
ITV_MAL = [r"\b(sin|no tiene|no lleva|no tiene la) itv\b", r"\bitv (caducada|vencida|pendiente|desfavorable|negativa)\b",
           r"\bno tiene (la )?itv en vigor\b", r"\bitv (no )?pasada\b(?! hasta)"]


def _texto(s: str) -> str:
    return norm_text(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))


def leer(client, a: dict) -> dict:
    """Lee la ficha del anuncio. Devuelve {estado, descripcion, equipamiento, provincia}."""
    url, pl = a.get("url") or "", a.get("plataforma")
    try:
        r = client.get(pl, url, use_cache=False)
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 0
        return {"estado": "retirado" if code in (404, 410) else f"error HTTP {code}", "descripcion": "", "equipamiento": "", "provincia": None}
    except Exception as e:   # robots.txt, red...
        return {"estado": f"no revisado ({type(e).__name__})", "descripcion": "", "equipamiento": "", "provincia": None}
    t, final = r["text"], (r.get("url") or url)
    out = {"estado": "disponible", "descripcion": "", "equipamiento": "", "provincia": None}
    if pl == "cochesnet":
        ad = (js_json_parse(t, "window.__INITIAL_PROPS__") or {}).get("ad") or {}
        if not ad or "covo.aspx" not in final:
            out["estado"] = "retirado"
            return out
        out.update(descripcion=ad.get("description") or "", provincia=ad.get("province"))
    elif pl == "autoscout24":
        ld = (next_data(t) or {}).get("props", {}).get("pageProps", {}).get("listingDetails") or {}
        stt = re.search(r'"status"\s*:\s*"(\w+)"', t)
        if not ld or not stt or stt.group(1).lower() != "active":
            out["estado"] = "retirado"
            return out
        eq = ld.get("vehicle", {}).get("equipment") or {}
        out.update(descripcion=ld.get("description") or "", provincia=(ld.get("location") or {}).get("city"),
                   equipamiento=" · ".join(x.get("id", "") for v in eq.values() for x in v if isinstance(x, dict)))
        if (ld.get("location") or {}).get("countryCode") not in (None, "ES"):
            out["provincia"] = "extranjero"
        zipc = str((ld.get("location") or {}).get("zip") or "")
        if zipc and not zipc.startswith("46"):
            out["provincia"] = f"CP {zipc} ({(ld.get('location') or {}).get('city')})"
        elif zipc:
            out["provincia"] = "Valencia"
    elif pl == "wallapop":
        it = (next_data(t) or {}).get("props", {}).get("pageProps", {}).get("item") or {}
        if not it or it.get("flags", {}).get("sold") or it.get("flags", {}).get("reserved"):
            out["estado"] = "retirado"
            return out
        out["descripcion"] = (it.get("description") or {}).get("original") or ""
    else:
        if final.rstrip("/") != url.rstrip("/") and "?" not in url:
            out["estado"] = "retirado"
            return out
        out["descripcion"] = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S))[:20000]
    return out


def evaluar(a: dict, f: dict) -> dict:
    """Aplica los criterios a la ficha leída: {descartar: bool, motivos: [...], avisos: [...]}."""
    motivos, avisos = [], []
    if f["estado"] == "retirado":
        motivos.append("anuncio retirado o vendido")
    elif f["estado"] != "disponible":
        avisos.append(f["estado"])
    desc = _texto(f.get("descripcion"))
    texto = f"{_texto(a.get('titulo'))} {desc}"
    eqt = _texto(f.get("equipamiento"))
    tiene_ac = bool(re.search(r"aire acondicionado|climatizador|\ba/?a\b|\ba/c\b", eqt + " " + _texto(a.get("titulo"))))
    for p in SIN_AC:
        m = re.search(p, texto)
        if m and not tiene_ac:
            motivos.append(f"sin aire acondicionado («{m.group(0)}»)")
            break
    res = analizar(a.get("titulo") or "", desc, False)
    for cat, frase in res.descartes:
        if "itv" in cat:          # sin ITV en vigor: puede pasarla; aviso, no descarte
            avisos.append(f"{cat} («{frase}»)")
        else:
            motivos.append(f"avería declarada: {cat} («{frase}»)")
    for cat, frase in res.revisar:
        avisos.append(f"{cat}" + (f" («{frase}»)" if frase else ""))
    for p in ITV_MAL:
        m = re.search(p, texto)
        if m:
            avisos.append(f"ITV: «{m.group(0)}»")
            break
    M = r"(primera|segunda|tercera|cuarta|quinta|sexta|marcha atras|marchas?)"
    if re.search(M + r".{0,40}(cuesta|rasca|no entra|dificil|salta)|(cuesta|rasca|dificultad).{0,40}(entr|meter).{0,30}" + M +
                 r"|problema.{0,25}" + M, texto):
        motivos.append("problema de cambio declarado (una marcha que cuesta o rasca)")
    prov = f.get("provincia")
    if prov and norm_text(prov) not in ("valencia", "valencia/valencia"):
        avisos.append(f"el coche está fuera de la provincia de Valencia ({prov})")
    return {"descartar": bool(motivos), "motivos": motivos, "avisos": avisos}


def cargar(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def guardar(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def candidatos(res: dict, n: int) -> list[dict]:
    """Los n mejores (calidad experta / coste) de cada franja y de cada segmento del Top, más los de la frontera."""
    vistos, out = set(), []
    pool = [a for a in res["base_ads"] if not a.get("descartado_ficha")]
    grupos = {}
    for a in pool:
        grupos.setdefault(("f", a["franja"]), []).append(a)
        grupos.setdefault(("s", a["segmento"]), []).append(a)
        # coches polivalentes (no urbanos de 2 plazas ni eléctricos de < 200 km, con ensayo Euro NCAP y con distintivo)
        if a.get("e_uso", 0) >= 10 and not (a["combustible"] == "electrico" and (a.get("autonomia") or 0) < 200) \
                and a.get("ncap") is not None and a.get("etiqueta") not in (None, "A"):
            grupos.setdefault(("p", a["franja"]), []).append(a)
    for (tipo, g), lst in grupos.items():
        if tipo == "s" and g not in res["cfg"]["analisis"]["segmentos_top"]:
            continue
        for a in sorted(lst, key=lambda x: -x["ratio"])[:n]:
            if a["uid"] not in vistos:
                vistos.add(a["uid"]); out.append(a)
    for f, lst in res["frontera"].items():
        if f == "global":
            continue
        for a in lst[:n]:
            if a["uid"] not in vistos:
                vistos.add(a["uid"]); out.append(a)
    return out


def revisar(client, res: dict, path: Path, n: int = 8, max_horas: float = 20) -> int:
    """Abre las fichas de los candidatos que no se hayan revisado en las últimas max_horas. Devuelve cuántas ha leído."""
    data = cargar(path)
    ahora = datetime.now()
    leidas = 0
    for a in candidatos(res, n):
        prev = data.get(a["uid"])
        if prev and (ahora - datetime.fromisoformat(prev["fecha"])).total_seconds() < max_horas * 3600:
            continue
        f = leer(client, a)
        ev = evaluar(a, f)
        data[a["uid"]] = {"fecha": ahora.isoformat(timespec="seconds"), "url": a.get("url"), "titulo": a.get("titulo"),
                          "estado": f["estado"], "provincia": f.get("provincia"), **ev,
                          "descripcion": (f.get("descripcion") or "")[:3000], "equipamiento": (f.get("equipamiento") or "")[:2000]}
        leidas += 1
        guardar(path, data)
    return leidas


def reevaluar(path: Path) -> int:
    """Vuelve a aplicar los criterios actuales a las fichas guardadas (sin pedir nada a la red)."""
    data = cargar(path)
    for uid, v in data.items():
        f = {"estado": v["estado"], "descripcion": v.get("descripcion") or "", "equipamiento": v.get("equipamiento") or "",
             "provincia": v.get("provincia")}
        v.update(evaluar({"titulo": v.get("titulo"), "uid": uid}, f))
    guardar(path, data)
    return len(data)
