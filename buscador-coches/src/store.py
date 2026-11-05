"""Histórico en SQLite para las ejecuciones incrementales."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .models import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  uid TEXT PRIMARY KEY,
  plataforma TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL,
  data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mercado (
  uid TEXT PRIMARY KEY, plataforma TEXT, marca TEXT, modelo TEXT, titulo TEXT,
  anio INTEGER, km INTEGER, precio REAL, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started TEXT, finished TEXT, plataforma TEXT, estado TEXT, nuevos INTEGER, vistos INTEGER, detalle TEXT
);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Columnas añadidas después de la primera versión (bases de datos existentes)."""
        for table, cols in {"listings": {"gone_at": "TEXT", "missed": "INTEGER DEFAULT 0", "alerted_at": "TEXT"},
                            "mercado": {"first_seen": "TEXT", "gone_at": "TEXT", "missed": "INTEGER DEFAULT 0"}}.items():
            have = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
            for c, typ in cols.items():
                if c not in have:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {c} {typ}")
        self.db.execute("UPDATE mercado SET first_seen = last_seen WHERE first_seen IS NULL")
        self.db.commit()

    def known(self, plataforma: str) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT uid FROM listings WHERE plataforma=?", (plataforma,))}

    def add_new(self, listings: list[Listing]) -> int:
        n = 0
        now = _now()
        for l in listings:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO listings(uid, plataforma, first_seen, last_seen, data) VALUES (?,?,?,?,?)",
                (l.uid, l.plataforma, now, now, json.dumps(l.to_dict(), ensure_ascii=False)))
            n += cur.rowcount
        self.db.commit()
        return n

    def touch(self, uids: list[str]) -> None:
        now = _now()
        self.db.executemany("UPDATE listings SET last_seen=? WHERE uid=?", [(now, u) for u in uids])
        self.db.commit()

    def add_market(self, rows: list[dict]) -> None:
        now = _now()
        self.db.executemany(
            "INSERT INTO mercado(uid, plataforma, marca, modelo, titulo, anio, km, precio, last_seen, first_seen, missed) "
            "VALUES (:uid, :plataforma, :marca, :modelo, :titulo, :anio, :km, :precio, :now, :now, 0) "
            "ON CONFLICT(uid) DO UPDATE SET precio=excluded.precio, km=excluded.km, last_seen=excluded.last_seen, "
            "missed=0, gone_at=NULL",
            [dict(r, now=now) for r in rows])
        self.db.commit()

    def mark_missing(self, plataforma: str, seen_listings: set[str], seen_market: set[str], runs_needed: int) -> dict:
        """Tras una ejecución correcta de la plataforma: lo que no se ha visto suma un 'fallo'; con
        runs_needed fallos seguidos se fija gone_at = última vez visto. Si reaparece, se borra."""
        out = {}
        for table, seen in (("listings", seen_listings), ("mercado", seen_market)):
            if not seen:
                continue  # sin observaciones (p. ej. fuente vacía): no se marca nada
            rows = self.db.execute(f"SELECT uid FROM {table} WHERE plataforma=? AND gone_at IS NULL", (plataforma,)).fetchall()
            missing = [(u,) for (u,) in rows if u not in seen]
            self.db.executemany(f"UPDATE {table} SET missed = COALESCE(missed,0) + 1 WHERE uid=?", missing)
            self.db.executemany(f"UPDATE {table} SET missed = 0, gone_at = NULL WHERE uid=?", [(u,) for u in seen])
            cur = self.db.execute(f"UPDATE {table} SET gone_at = last_seen WHERE plataforma=? AND gone_at IS NULL "
                                  f"AND missed >= ?", (plataforma, runs_needed))
            out[table] = cur.rowcount
        self.db.commit()
        return out

    def new_since(self, ts: str) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT uid FROM listings WHERE first_seen >= ?", (ts,))}

    def mark_alerted(self, uids: list[str]) -> None:
        now = _now()
        self.db.executemany("UPDATE listings SET alerted_at=? WHERE uid=?", [(now, u) for u in uids])
        self.db.commit()

    def alerted(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT uid FROM listings WHERE alerted_at IS NOT NULL")}

    def sale_times(self) -> list[dict]:
        """Anuncios desaparecidos (mercado y candidatos) con días publicados según nuestras observaciones."""
        cur = self.db.execute(
            "SELECT plataforma, marca, modelo, titulo, anio, km, precio, first_seen, gone_at, "
            "julianday(gone_at) - julianday(first_seen) AS dias FROM mercado WHERE gone_at IS NOT NULL")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur]

    def market(self, max_age_days: int = 60) -> list[dict]:
        cur = self.db.execute("SELECT uid, plataforma, marca, modelo, titulo, anio, km, precio FROM mercado "
                              "WHERE last_seen >= datetime('now', ?)", (f"-{max_age_days} days",))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur]

    def last_success(self, plataforma: str) -> str | None:
        r = self.db.execute("SELECT MAX(started) FROM runs WHERE plataforma=? AND estado='ok'", (plataforma,)).fetchone()
        return r[0] if r else None

    def log_run(self, plataforma: str, started: str, estado: str, nuevos: int, vistos: int, detalle: str = "") -> None:
        self.db.execute("INSERT INTO runs(started, finished, plataforma, estado, nuevos, vistos, detalle) VALUES (?,?,?,?,?,?,?)",
                        (started, _now(), plataforma, estado, nuevos, vistos, detalle))
        self.db.commit()

    def all(self, max_age_days: int | None = None) -> list[Listing]:
        q = "SELECT data FROM listings"
        args: tuple = ()
        if max_age_days:
            q += " WHERE last_seen >= datetime('now', ?)"
            args = (f"-{max_age_days} days",)
        return [Listing.from_dict(json.loads(r[0])) for r in self.db.execute(q, args)]
