"""Distintivo ambiental oficial de la DGT por matrícula.

Fuente: «Microdatos de distintivo ambiental de vehículos (diarios)», DGT en Cifras
(catálogo: https://datos.gob.es/es/catalogo/e00130502-microdatos-de-distintivo-ambiental-de-vehiculos-diarios),
fichero https://www.dgt.es/microdatos/salida/distintivoAmbiental/export_dist_ambiental.zip
(robots.txt de dgt.es lo permite). Unos 106 MB comprimido / 600 MB de texto, unos 38,7 millones de matrículas:
`MATRICULA|TIPO DE ETIQUETA`.

Se descarga como mucho una vez al día y se indexa en SQLite (data/dgt/distintivos.sqlite). No se hacen
consultas al buscador web de la sede de la DGT.

Códigos del fichero diario (sin diccionario publicado para este fichero): 16TB, 16TC, 16TE, 16T0 (turismos y
otros) y 16MB, 16MC, 16ME, 16M0 (motos), más "SIN DISTINTIVO". La equivalencia de la última letra
(B, C, E = ECO, 0 = CERO) se ha verificado cruzando matrículas con la etiqueta que publica OcasionPlus
(ver tools/dgt_check.py y zbe.yaml).
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("dgt")
URL = "https://www.dgt.es/microdatos/salida/distintivoAmbiental/export_dist_ambiental.zip"
CODES = {"B": "B", "C": "C", "E": "ECO", "0": "CERO"}
PLATE_RE = re.compile(r"\b(\d{4})\s?-?\s?([BCDFGHJKLMNPRSTVWXYZ]{3})\b")   # formato actual (desde 2000)
OLD_RE = re.compile(r"\b([A-Z]{1,2})\s?-?\s?(\d{4})\s?-?\s?([A-Z]{1,2})\b")  # provincial (V-1234-AB)


def label_from_code(code: str) -> Optional[str]:
    code = (code or "").strip().upper()
    if code == "SIN DISTINTIVO":
        return "A"
    m = re.fullmatch(r"16[TM]([BCE0])", code)
    return CODES[m.group(1)] if m else None


def normalize_plate(s: str) -> Optional[str]:
    t = (s or "").upper()
    m = PLATE_RE.search(t)
    if m:
        return m.group(1) + m.group(2)
    m = OLD_RE.search(t)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    return None


def find_plate(*texts: Optional[str]) -> Optional[str]:
    for t in texts:
        p = normalize_plate(str(t)) if t else None
        if p:
            return p
    return None


class DGTIndex:
    def __init__(self, base: Path, max_age_h: float = 24, url: str = URL):
        self.dir = base / "data" / "dgt"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.zip = self.dir / "export_dist_ambiental.zip"
        self.db_path = self.dir / "distintivos.sqlite"
        self.max_age = max_age_h * 3600
        self.url = url
        self.db: Optional[sqlite3.Connection] = None

    def _stale(self, p: Path) -> bool:
        return not p.exists() or time.time() - p.stat().st_mtime > self.max_age

    def ensure(self, user_agent: str, allow_download: bool = True) -> bool:
        """Descarga (como mucho una vez al día) e indexa. Devuelve si hay índice utilizable."""
        if allow_download and self._stale(self.zip):
            try:
                log.info("Descargando fichero de distintivos de la DGT…")
                with requests.get(self.url, headers={"User-Agent": user_agent}, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    tmp = self.zip.with_suffix(".part")
                    with open(tmp, "wb") as fh:
                        for chunk in r.iter_content(1 << 20):
                            fh.write(chunk)
                    tmp.replace(self.zip)
            except requests.RequestException as e:
                log.warning("No se pudo descargar el fichero de la DGT (%s); se usa el índice anterior si existe", e)
        if self.zip.exists() and (not self.db_path.exists() or self.db_path.stat().st_mtime < self.zip.stat().st_mtime):
            self.build(self.zip)
        if self.db_path.exists():
            self.db = sqlite3.connect(self.db_path)
            return True
        return False

    def build(self, zpath: Path) -> int:
        log.info("Indexando %s en SQLite…", zpath.name)
        tmp = self.db_path.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)
        db = sqlite3.connect(tmp)
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("CREATE TABLE d (m TEXT PRIMARY KEY, c TEXT) WITHOUT ROWID")
        n = 0
        with zipfile.ZipFile(zpath) as z, z.open(z.namelist()[0]) as f:
            f.readline()
            batch = []
            for line in f:
                m, _, c = line.decode("latin-1").rstrip("\r\n").partition("|")
                batch.append((m, c))
                if len(batch) >= 200000:
                    db.executemany("INSERT OR REPLACE INTO d VALUES (?,?)", batch)
                    n += len(batch)
                    batch = []
            db.executemany("INSERT OR REPLACE INTO d VALUES (?,?)", batch)
            n += len(batch)
        db.execute("CREATE TABLE meta (k TEXT, v TEXT)")
        db.executemany("INSERT INTO meta VALUES (?,?)", [("fuente", self.url), ("filas", str(n)),
                                                        ("zip_mtime", time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(zpath.stat().st_mtime)))])
        db.commit()
        db.close()
        tmp.replace(self.db_path)
        log.info("Índice DGT: %d matrículas", n)
        return n

    def lookup(self, plate: Optional[str]) -> Optional[tuple[str, str]]:
        """(etiqueta, código DGT) o None si la matrícula no está."""
        if not plate or self.db is None:
            return None
        r = self.db.execute("SELECT c FROM d WHERE m=?", (plate,)).fetchone()
        if not r:
            return None
        lab = label_from_code(r[0])
        return (lab, r[0]) if lab else None

    def meta(self) -> dict:
        if self.db is None:
            return {}
        return dict(self.db.execute("SELECT k, v FROM meta").fetchall())
