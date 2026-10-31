"""Rellena matrícula, fecha de primera matriculación y etiqueta del anuncio en las fichas ya guardadas,
leyendo su copia en raw/ (sin peticiones). Uso: python tools/backfill_etiqueta.py"""
import json, sqlite3, sys
from collections import Counter
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from src.sources.common import js_json_parse, next_data, objects_after, rsc_payload

db = sqlite3.connect(BASE / "data" / "listings.sqlite")
stats = Counter()
for uid, data in db.execute("SELECT uid, data FROM listings").fetchall():
    d = json.loads(data)
    try:
        t = json.loads(open(d["raw_ref"]).read())["text"]
    except Exception:
        stats["sin raw"] += 1
        continue
    p = d["plataforma"]
    if p == "ocasionplus":
        v = next((o for o in objects_after(rsc_payload(t), r'"vehicle":\{') if "kms" in o), None) or {}
        d["matricula"] = v.get("carPlate") if isinstance(v.get("carPlate"), str) else d.get("matricula")
        d["etiqueta_anuncio"] = v.get("environmentalLabel") or d.get("etiqueta_anuncio")
        d["fecha_matriculacion"] = (v.get("registrationDate") or "")[:10] or d.get("fecha_matriculacion")
    elif p == "autoscout24":
        v = (((next_data(t) or {}).get("props", {}).get("pageProps", {}) or {}).get("listingDetails") or {}).get("vehicle") or {}
        d["fecha_matriculacion"] = (v.get("firstRegistrationDateRaw") or "")[:7] or d.get("fecha_matriculacion")
        d["matricula"] = v.get("licensePlate") or d.get("matricula")
    elif p == "cochesnet":
        ad = (js_json_parse(t, "window.__INITIAL_PROPS__") or {}).get("ad") or {}
        d["etiqueta_anuncio"] = ad.get("environmentalLabel") or d.get("etiqueta_dgt") or d.get("etiqueta_anuncio")
        d["fecha_matriculacion"] = ad.get("plateRegistrationDate") or (str(d["anio"]) if d.get("anio") else None)
    elif p == "wallapop":
        d["fecha_matriculacion"] = str(d["anio"]) if d.get("anio") else None
    for k in ("matricula", "etiqueta_anuncio", "fecha_matriculacion"):
        stats[f"{p}:{k}"] += bool(d.get(k))
    db.execute("UPDATE listings SET data=? WHERE uid=?", (json.dumps(d, ensure_ascii=False), uid))
db.commit()
print(dict(sorted(stats.items())))
