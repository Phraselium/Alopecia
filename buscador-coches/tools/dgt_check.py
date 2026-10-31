"""Valida la equivalencia de códigos del fichero diario de la DGT cruzando matrícula + etiqueta publicadas por
OcasionPlus (caché de raw/ocasionplus). Imprime la matriz código DGT × etiqueta del anuncio."""
import collections, glob, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.dgt import DGTIndex, label_from_code
from src.sources.common import rsc_payload, objects_after
BASE = Path(__file__).resolve().parents[1]
ix = DGTIndex(BASE); ix.ensure("x", allow_download=False)
pairs = {}
for f in glob.glob(str(BASE / "raw/ocasionplus/*.json")):
    t = json.loads(open(f).read())["text"]
    r = rsc_payload(t)
    vs = list(objects_after(r, r'"vehicle":\{'))
    for vl in objects_after(r, r'"vehicleList":\{'):
        vs += [x for x in vl.get("data") or [] if isinstance(x, dict)]
    for v in vs:
        if isinstance(v.get("characteristics"), dict):
            v = {**v, **v["characteristics"]}
        if isinstance(v.get("carPlate"), str) and v.get("environmentalLabel"):
            pairs[v["carPlate"]] = (v["environmentalLabel"], (v.get("engine") or {}).get("fuel") if isinstance(v.get("engine"), dict) else None)
mat = collections.Counter(); miss = 0
for plate, (lab, fuel) in pairs.items():
    r = ix.db.execute("SELECT c FROM d WHERE m=?", (plate,)).fetchone()
    if not r:
        miss += 1; continue
    mat[(r[0], lab)] += 1
print(f"matrículas con etiqueta en OcasionPlus: {len(pairs)}; no encontradas en el fichero DGT: {miss}")
ok = sum(n for (c, lab), n in mat.items() if label_from_code(c) == {"0": "CERO"}.get(lab, lab))
print(f"coinciden con la equivalencia: {ok} de {sum(mat.values())}")
for (c, lab), n in sorted(mat.items()): print(f"  DGT {c:15s} anuncio {lab:5s} -> {n}")
fuels = collections.Counter((label_from_code(ix.db.execute("SELECT c FROM d WHERE m=?", (p,)).fetchone()[0]), f)
                           for p, (lab, f) in pairs.items() if ix.db.execute("SELECT 1 FROM d WHERE m=?", (p,)).fetchone())
print("etiqueta DGT × combustible del anuncio:", dict(fuels))
