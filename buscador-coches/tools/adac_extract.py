"""Extrae de la ADAC Pannenstatistik (texto de pdftotext -layout) la Pannenkennziffer (averías por
1.000 vehículos) de la matriculación más antigua de cada tabla (EZ 2015 en la edición 2025).

Solo se acepta el último valor de una fila si termina en el borde derecho de su tabla (la columna del
año más antiguo); si no, el modelo queda sin dato. Uso: python tools/adac_extract.py adac.txt"""
import json, re, statistics, sys

lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
rows, cls, block = [], None, 0
for ln in lines:
    if re.search(r"Laufleistung(\s+20\d\d)+", ln):
        block += 1
        oldest = int(re.findall(r"20\d\d", ln)[-1])
        continue
    s = ln.strip()
    for k in ("Kleinstwagen", "Kleinwagen", "untere Mittelklasse", "obere Mittelklasse", "Mittelklasse"):
        if s.startswith(k) and len(s) < 60:
            cls = k
            break
    mm = re.match(r"^(\S.*?\S)\s{2,}(\d{1,2})\s{2,}(\d.*)$", ln)
    if not block or not mm:
        continue
    toks = list(re.finditer(r"\d{1,2}(?:,\d)?", ln[mm.start(3):]))
    if not toks:
        continue
    rows.append({"modelo": mm.group(1).strip(), "clase": cls, "bloque": block, "anio": oldest,
                 "n": len(toks), "fin": mm.start(3) + toks[-1].end(), "ultimo": float(toks[-1].group().replace(",", "."))})
out = {}
for b in {r["bloque"] for r in rows}:
    rb = [r for r in rows if r["bloque"] == b]
    full = [r["fin"] for r in rb if r["n"] >= 7]
    if not full:
        continue
    edge = statistics.median(full)
    for r in rb:
        if abs(r["fin"] - edge) <= 3:
            out[r["modelo"]] = {"clase": r["clase"], "anio_matriculacion": r["anio"], "pkz": r["ultimo"]}
json.dump(out, sys.stdout, ensure_ascii=False, indent=0)
