"""Rellena color, equipamiento, ITV, propietarios y libro en las fichas ya guardadas leyendo su copia en raw/
(sin peticiones). Uso: python tools/backfill_atributos.py"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.atributos import from_raw  # noqa: E402
from src.models import Listing  # noqa: E402

db = sqlite3.connect(BASE / "data" / "listings.sqlite")
stats = Counter()
for uid, data in db.execute("SELECT uid, data FROM listings").fetchall():
    l = Listing.from_dict(json.loads(data))
    from_raw(l)
    for k in ("color_raw", "equipamiento", "itv_hasta"):
        stats[f"{l.plataforma}:{k}"] += bool(getattr(l, k))
    stats[f"{l.plataforma}:total"] += 1
    d = l.to_dict()
    d.pop("uid", None)
    db.execute("UPDATE listings SET data=? WHERE uid=?", (json.dumps(d, ensure_ascii=False), uid))
db.commit()
print(dict(sorted(stats.items())))
