"""Atributos estéticos, color, equipamiento de seguridad y señales de mantenimiento de cada anuncio.

Dos fuentes:
- from_raw(l): datos ESTRUCTURADOS de la ficha guardada en raw/ (color, equipamiento, ITV, dueños...). Se llama al
  recoger (run.collect) y con tools/backfill_atributos.py para las fichas ya guardadas. No hace peticiones.
- from_text(l, est): título + versión + descripción + equipamiento. Se llama en cada procesado (barato).

Las listas de palabras y la tabla de colores están en estetica.yaml (editables).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .models import Listing
from .normalize import norm_text

# Colores estructurados de Coches.net: 'COMMON.COLOR_GRAY' -> 'gray'
_EN = {"white": "blanco", "gray": "gris", "grey": "gris", "silver": "plata", "black": "negro", "blue": "azul", "red": "rojo",
       "green": "verde", "beige": "beige", "brown": "marron", "yellow": "amarillo", "orange": "naranja", "gold": "dorado",
       "purple": "morado", "violet": "morado", "pink": "rosa", "bordeaux": "granate", "maroon": "granate", "garnet": "granate"}


def norm_color(raw: Optional[str], est: dict) -> Optional[str]:
    """Texto libre de color -> categoría de estetica.yaml (colores.alias). None si no se reconoce."""
    if not raw:
        return None
    t = norm_text(str(raw).replace("COMMON.COLOR_", "").replace("_", " "))
    t = " ".join(_EN.get(w, w) for w in t.split())
    alias = (est.get("colores") or {}).get("alias") or {}
    # alias más largos primero ('azul marino' antes que 'azul', 'gris oscuro' antes que 'gris')
    for pat in sorted(alias, key=len, reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(norm_text(pat))}(?![a-z])", t):
            return alias[pat]
    return None


_COLOR_CTX = r"(?:color|pintura|carroceria)\s*(?:exterior\s*)?(?:es\s*|:\s*|en\s*)?([a-z]+(?:\s+(?:oscuro|claro|marino|metalizado|perla|nacarado|plata|plateado|medio|grafito))?)"


def color_from_text(titulo: str, descripcion: str, est: dict) -> Optional[str]:
    """Solo con contexto explícito ('color blanco', 'pintura gris'): 'interior negro' o 'llantas negras' no cuentan."""
    t = norm_text(f"{titulo}. {descripcion}")
    for m in re.finditer(_COLOR_CTX, t):
        c = norm_color(m.group(1), est)
        if c:
            return m.group(0)
    return None


def _flat(x) -> str:
    out = []
    if isinstance(x, dict):
        for v in x.values():
            out.append(_flat(v))
    elif isinstance(x, list):
        for v in x:
            out.append(_flat(v))
    elif isinstance(x, str):
        out.append(x)
    return " | ".join(o for o in out if o)


def from_raw(l: Listing) -> Listing:
    """Rellena color_raw, equipamiento, itv_hasta, propietarios, libro, correa (si la ficha estructurada lo trae).
    Nunca lanza: una ficha con formato inesperado se queda sin estos datos."""
    try:
        return _from_raw(l)
    except Exception:  # noqa: BLE001
        return l


def _from_raw(l: Listing) -> Listing:
    try:
        t = json.loads(open(l.raw_ref, encoding="utf-8").read())["text"]
    except Exception:  # noqa: BLE001 - sin copia en raw/ no hay nada que leer
        return l
    from .sources.common import js_json_parse, next_data, objects_after, rsc_payload
    p = l.plataforma
    if p == "ocasionplus":
        v = next((o for o in objects_after(rsc_payload(t), r'"vehicle":\{') if "kms" in o), None) or {}
        if v.get("color"):
            l.color_raw, l.color_fuente = v["color"], "OcasionPlus (vehicle.color)"
        eq = [_flat(v.get("serie")), " | ".join(e.get("description", "") for e in (v.get("extras") or []) if isinstance(e, dict))]
        l.equipamiento = " | ".join(x for x in eq if x)[:4000] or l.equipamiento
        itv = (v.get("itv") or {}).get("validDate") if isinstance(v.get("itv"), dict) else None
        if itv:
            l.itv_hasta = str(itv)[:16]
            l.itv_vigor = True if l.itv_vigor is None else l.itv_vigor
        if v.get("maintenanceBook") and l.libro_mantenimiento is None:
            l.libro_mantenimiento = True
    elif p == "autoscout24":
        v = (((next_data(t) or {}).get("props", {}).get("pageProps", {}) or {}).get("listingDetails") or {}).get("vehicle") or {}
        c = v.get("bodyColorOriginal") or v.get("bodyColor")
        if c:
            l.color_raw = f"{c} {v.get('paintType') or ''}".strip()
            l.color_fuente = "AutoScout24 (vehicle.bodyColor)"
        eq = v.get("equipment") or {}
        l.equipamiento = " | ".join(e.get("id", "") for lst in eq.values() if isinstance(lst, list) for e in lst if isinstance(e, dict))[:4000] or l.equipamiento
        if v.get("noOfPreviousOwners") and l.num_propietarios is None:
            try:
                l.num_propietarios = int(v["noOfPreviousOwners"])
            except (TypeError, ValueError):
                pass
        if v.get("hasFullServiceHistory") is True and l.libro_mantenimiento is None:
            l.libro_mantenimiento = True
        if v.get("lastBeltServiceDate"):
            l.correa_cambiada, l.correa_detalle = True, True
        if not l.color_raw:
            m = re.search(r'"color":"([^"]{2,30})"', t)
            if m:
                l.color_raw, l.color_fuente = m.group(1), "AutoScout24 (JSON-LD color)"
    elif p == "cochesnet":
        ad = (js_json_parse(t, "window.__INITIAL_PROPS__") or {}).get("ad") or {}
        if ad.get("color"):
            l.color_raw, l.color_fuente = ad["color"], "Coches.net (ad.color)"
    return l


def _rx(pats: list[str]) -> str:
    return "|".join(f"(?:{p})" for p in pats)


def from_text(l: Listing, est: dict) -> Listing:
    """Atributos estéticos, ESP y señales de mantenimiento a partir del texto. Idempotente."""
    a = est.get("atributos") or {}
    base = f"{l.titulo} {l.version or ''}"
    txt = norm_text(f"{base}. {l.descripcion or ''}. {l.equipamiento or ''}")
    # color
    if not l.color_raw:
        c = color_from_text(l.titulo, l.descripcion or "", est)
        if c:
            l.color_raw, l.color_fuente = c, "texto del anuncio"
    l.color = norm_color(l.color_raw, est)
    # acabado alto o deportivo: en título/versión (en la descripción aparece en frases como "aspecto sport")
    m = re.search(rf"(?<![a-z0-9])({_rx(a.get('acabados') or [])})(?![a-z0-9])", norm_text(base))
    l.at_acabado = m.group(1) if m else None
    # llantas
    if re.search(_rx(a.get("chapa") or []), txt):
        l.at_llantas = "chapa"
    elif re.search(r"llantas?[^.|]{0,40}?(?<!\d)(1[6-9]|2[0-2])\s*(\"|''|”|pulg|pulgadas|\b)", txt) or \
            re.search(r"(?<!\d)(1[6-9]|2[0-2])\s*(\"|''|”|pulgadas|pulg)[^.|]{0,15}llanta", txt):
        l.at_llantas = "16+"
    elif re.search(_rx(a.get("llantas") or []), txt):
        l.at_llantas = "sí"
    else:
        l.at_llantas = None
    l.at_faros = True if re.search(_rx(a.get("faros") or []), txt) else None
    l.at_tintados = True if re.search(_rx(a.get("tintados") or []), txt) else None
    # ESP / ESC: en el texto original en mayúsculas (ESP, ESC) o con el nombre completo
    raw = f"{base} {l.descripcion or ''} {l.equipamiento or ''}"
    if re.search(r"\b(ESP|ESC|DSC|VSC|VDC|VSA|DSTC)\b", raw) or \
            re.search(r"control\s*(electronico\s*)?(de\s*)?estabilidad|programa\s*electronico\s*de\s*estabilidad", txt):
        if not re.search(r"sin\s*(esp|control\s*de\s*estabilidad)", txt):
            l.esp, l.esp_fuente = "sí", "anuncio/equipamiento"
    # mantenimiento
    if l.correa_cambiada and re.search(
            r"(correa|distribucion|kit)[^.]{0,60}?(\d{2,3}[. ]?\d{3}\s*(km|kms|kilometros)|\d{2,3}\s*mil\s*(km|kms)?|a\s*los\s*\d+"
            r"|(en|hace|del?)\s*(20\d\d|\d+\s*(mes|meses|ano|anos))|\d{1,2}/20\d\d)", txt):
        l.correa_detalle = True
    if re.search(r"(?<!sin )\bfacturas?\b", txt) and not re.search(r"sin\s*facturas", txt):
        l.facturas = True
    if re.search(r"(neumaticos|ruedas|gomas|cubiertas)\s*(nuev|recien|cambiad|a estrenar)|(4|cuatro)\s*(neumaticos|ruedas|gomas)\s*nuev", txt):
        l.neumaticos_nuevos = True
    return l


def estetica_modelo(l: Listing, est: dict) -> tuple[int, Optional[str]]:
    """(puntos 1-5, referencia). La lista de estetica.yaml manda; si no casa, puntos por defecto del segmento."""
    for e in est.get("modelos") or []:
        if l.modelo_key != e["modelo"] or not l.anio or not (e["desde"] <= l.anio <= e["hasta"]):
            continue
        if e.get("combustible") and l.combustible != e["combustible"]:
            continue
        mot = (l.motor_key or "").split(" ")[0]
        if e.get("motores") and mot not in [str(x) for x in e["motores"]]:
            continue
        ref = f"{e['modelo']} {e.get('generacion', '')} {'/'.join(map(str, e.get('motores') or [])) or 'todos'} {e['desde']}-{e['hasta']}"
        return int(e["puntos"]), " ".join(ref.split())
    d = est.get("puntos_por_defecto") or {}
    return int(d.get(l.carroceria, d.get("otros", 3))), None


def s_atributos(l: Listing, est: dict) -> float:
    """Puntos de atributos (0-100) con los pesos de estetica.yaml -> puntos_atributos."""
    pa = est.get("puntos_atributos") or {}
    s = pa.get("base", 40)
    s += pa.get("acabado", 0) * (l.at_acabado is not None)
    s += pa.get("llantas_16", 0) if l.at_llantas == "16+" else (pa.get("llantas", 0) if l.at_llantas == "sí" else 0)
    s += pa.get("faros", 0) * (l.at_faros is True)
    s += pa.get("tintados", 0) * (l.at_tintados is True)
    s -= pa.get("chapa", 0) * (l.at_llantas == "chapa")
    return max(0.0, min(100.0, float(s)))
