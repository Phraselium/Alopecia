"""Utilidades para extraer datos embebidos en páginas (JSON-LD, __NEXT_DATA__, RSC, estados JS)."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Iterator, Optional

_DEC = json.JSONDecoder()


def ld_json(html: str) -> list[dict]:
    out = []
    for blob in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(blob)
        except ValueError:
            continue
        for it in (d if isinstance(d, list) else d.get("@graph", [d])):
            if isinstance(it, dict):
                out.append(it)
    return out


def next_data(html: str) -> Optional[dict]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def rsc_payload(html: str) -> str:
    """Concatena los fragmentos self.__next_f.push([1,"..."]) de Next.js (App Router)."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def js_json_parse(html: str, var: str) -> Optional[Any]:
    """window.VAR = JSON.parse("...") o window.VAR = "..." (cadena JSON escapada) o window.VAR = {...}."""
    m = re.search(rf'{re.escape(var)}\s*=\s*JSON\.parse\(("(?:[^"\\]|\\.)*")\)', html, re.S) or \
        re.search(rf'{re.escape(var)}\s*=\s*("(?:[^"\\]|\\.)*")', html, re.S)
    if m:
        return json.loads(json.loads(m.group(1)))
    m = re.search(rf'{re.escape(var)}\s*=\s*\{{', html)
    if m:
        return _DEC.raw_decode(html, m.end() - 1)[0]
    return None


def objects_after(text: str, key_regex: str) -> Iterator[dict]:
    """Decodifica los objetos JSON que siguen a cada coincidencia de '"clave":{'."""
    for m in re.finditer(key_regex, text):
        try:
            v, _ = _DEC.raw_decode(text, m.end() - 1)
            if isinstance(v, dict):
                yield v
        except ValueError:
            continue


def to_int(x) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x)
    digits = re.sub(r"[^\d]", "", str(x))
    return int(digits) if digits else None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
