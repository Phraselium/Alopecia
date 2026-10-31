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
