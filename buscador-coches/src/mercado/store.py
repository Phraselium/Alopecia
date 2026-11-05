"""Base de datos propia del perfil mercado (data/mercado.sqlite). No comparte tablas con el perfil personal."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

COLS = ["uid", "plataforma", "zona", "tipo", "marca", "modelo", "version", "titulo", "anio", "mes", "km", "precio",
        "precio_financiado", "combustible", "cambio", "cv", "cc", "carroceria_raw", "etiqueta", "vendedor", "garantia_meses",
        "ubicacion", "cp", "url", "generacion", "consumo_wltp", "co2", "descripcion", "raw_ref"]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class MercadoStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=120)
        cols = ", ".join(f"{c} {'TEXT PRIMARY KEY' if c == 'uid' else ''}" for c in COLS)
        self.db.execute(f"CREATE TABLE IF NOT EXISTS anuncios ({cols}, first_seen TEXT, last_seen TEXT, gone_at TEXT, "
                        f"missed INTEGER DEFAULT 0)")
        self.db.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, "
                        "fuente TEXT, zona TEXT, estado TEXT, vistos INTEGER, peticiones INTEGER, detalle TEXT)")
        self.db.commit()

    def upsert(self, ads: list[dict]) -> int:
        now, nuevos = _now(), 0
        for a in ads:
            row = self.db.execute("SELECT uid FROM anuncios WHERE uid=?", (a["uid"],)).fetchone()
            vals = [a.get(c) for c in COLS]
            if row:
                sets = ", ".join(f"{c}=?" for c in COLS[1:])
                self.db.execute(f"UPDATE anuncios SET {sets}, last_seen=?, gone_at=NULL, missed=0 WHERE uid=?",
                                vals[1:] + [now, a["uid"]])
            else:
                nuevos += 1
                self.db.execute(f"INSERT INTO anuncios ({', '.join(COLS)}, first_seen, last_seen) VALUES "
                                f"({', '.join('?' * len(COLS))}, ?, ?)", vals + [now, now])
        self.db.commit()
        return nuevos

    def mark_missing(self, fuente: str, zona: str, vistos: set[str], umbral: int = 2) -> int:
        """Solo para recorridos completos: suma un 'missed' a los no vistos; con 'umbral' seguidos fija gone_at."""
        n = 0
        for (uid,) in self.db.execute("SELECT uid FROM anuncios WHERE plataforma=? AND zona=? AND gone_at IS NULL",
                                      (fuente, zona)).fetchall():
            if uid in vistos:
                continue
            self.db.execute("UPDATE anuncios SET missed = missed + 1 WHERE uid=?", (uid,))
            self.db.execute("UPDATE anuncios SET gone_at=? WHERE uid=? AND missed >= ?", (_now(), uid, umbral))
            n += 1
        self.db.commit()
        return n

    def log_run(self, started, fuente, zona, estado, vistos, peticiones, detalle=""):
        self.db.execute("INSERT INTO runs (started, finished, fuente, zona, estado, vistos, peticiones, detalle) VALUES (?,?,?,?,?,?,?,?)",
                        (started, _now(), fuente, zona, estado, vistos, peticiones, detalle))
        self.db.commit()

    def all(self) -> list[dict]:
        cur = self.db.execute("SELECT * FROM anuncios")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur]
