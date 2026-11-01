"""Geolocalización por código postal o municipio con GeoNames (ES.txt, licencia CC BY 4.0).

Fuente: https://download.geonames.org/export/zip/ES.zip . Se descarga una vez a data/geo/.
"""
from __future__ import annotations

import io
import logging
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

import requests

from .normalize import norm_text
from .sources.common import haversine_km

log = logging.getLogger("geo")
URL = "https://download.geonames.org/export/zip/ES.zip"
BASE = Path(__file__).resolve().parents[1]
PATH = BASE / "data" / "geo" / "ES.txt"


def _ensure() -> Optional[Path]:
    if PATH.exists():
        return PATH
    try:
        r = requests.get(URL, timeout=60)
        r.raise_for_status()
        PATH.parent.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(r.content)).extract("ES.txt", PATH.parent)
        return PATH
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo descargar GeoNames (%s): no se filtrará por distancia", e)
        return None


@lru_cache(maxsize=1)
def _tables():
    zips, places = {}, {}
    p = _ensure()
    if not p:
        return zips, places
    for line in p.read_text(encoding="utf-8").splitlines():
        f = line.split("\t")
        if len(f) < 11:
            continue
        cp, place, prov, lat, lon = f[1], f[2], f[5], float(f[9]), float(f[10])
        zips.setdefault(cp, (lat, lon))
        places.setdefault((norm_text(place), norm_text(prov)), (lat, lon))
        places.setdefault((norm_text(place), ""), (lat, lon))
    return zips, places


def coords(cp: Optional[str] = None, municipio: Optional[str] = None,
           provincia: Optional[str] = None) -> Optional[tuple[float, float]]:
    zips, places = _tables()
    if cp:
        cp = str(cp).strip().zfill(5)
        if cp in zips:
            return zips[cp]
    if municipio:
        m = norm_text(municipio.split("(")[0].split("/")[0])
        for key in ((m, norm_text(provincia or "")), (m, "")):
            if key in places:
                return places[key]
    return None


def distance_from(center: tuple[float, float], cp=None, municipio=None, provincia=None,
                  lat=None, lon=None) -> Optional[float]:
    if lat is None or lon is None:
        c = coords(cp, municipio, provincia)
        if not c:
            return None
        lat, lon = c
    return round(haversine_km(center[0], center[1], lat, lon), 1)
