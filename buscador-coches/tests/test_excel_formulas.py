"""Recalcula ranking.xlsx con LibreOffice y comprueba que las fórmulas dan lo mismo que src/scoring.py.

Usa anuncios SINTÉTICOS de prueba (no son datos reales y nunca se escriben en las salidas del proyecto).
"""
import random
import shutil
import subprocess

import pytest
from openpyxl import load_workbook

from src.excel import COL, write_workbook
from src.models import Listing
from src.pipeline import process
from src.scoring import Params

pytestmark = pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice no instalado")


def synthetic(n=40, seed=1):
    rnd = random.Random(seed)
    modelos = [("Toyota", "Yaris", "1.33 VVT-i"), ("Peugeot", "208", "1.2 PureTech"), ("Seat", "Ibiza", "1.4 MPI"),
               ("Renault", "Clio", "1.2 TCe"), ("Volkswagen", "Golf", "1.4 TSI"), ("Ford", "Focus", "1.6 TDCi diésel"),
               ("Kia", "Rio", "1.2 CVVT")]
    out = []
    for i in range(n):
        marca, modelo, motor = modelos[i % len(modelos)]
        anio = rnd.randint(2008, 2018)
        out.append(Listing(
            plataforma="TEST", id_externo=str(i), url=f"https://example.invalid/{i}",
            titulo=f"{marca} {modelo} {motor}", marca=marca, modelo=modelo, version=motor,
            anio=anio, km=rnd.randint(40000, 210000), precio=float(rnd.randint(2500, 4600)),
            vendedor=rnd.choice(["particular", "profesional", None]), num_fotos=rnd.randint(1, 15),
            descripcion=rnd.choice(["ITV en vigor, libro de mantenimiento", "único propietario, correa cambiada", "buen estado"])))
    return out


def test_formulas_match_python(tmp_path, cfg, fiscal, rel):
    p = Params(cfg, fiscal, rel)
    res = process(synthetic(), p, set())
    assert res.filas, "deberían quedar anuncios limpios"
    src = tmp_path / "r.xlsx"
    write_workbook(src, [f["listing"] for f in res.filas], res.avisos, p)
    outdir = tmp_path / "calc"
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(outdir), str(src)],
                   check=True, capture_output=True, timeout=180)
    wb = load_workbook(outdir / "r.xlsx", data_only=True)
    ws = wb["Anuncios"]
    hdr = {ws.cell(1, c).column_letter: c for c in range(1, ws.max_column + 1)}
    # ningún error de fórmula en ninguna hoja
    for sh in wb.worksheets:
        for row in sh.iter_rows():
            for c in row:
                assert not (isinstance(c.value, str) and c.value.startswith(("#", "Err:"))), f"{sh.title}!{c.coordinate}={c.value}"
    for r, f in enumerate(res.filas, 2):
        def v(key):
            return ws.cell(r, hdr[COL[key]]).value
        assert v("uid") == f["listing"].uid
        assert v("mediana") == pytest.approx(f["mediana"]), f["listing"].uid
        assert v("s_fiab") == pytest.approx(f["fiabilidad"]["score"])
        assert v("s_precio") == pytest.approx(f["precio"]["score"])
        assert v("s_kmedad") == pytest.approx(f["km_edad"]["score"])
        assert v("s_anuncio") == pytest.approx(f["anuncio"]["score"])
        assert v("s_uso") == pytest.approx(f["coste_uso"]["score"])
        assert v("itp") == pytest.approx(f["coste"]["itp"]), f["listing"].uid
        assert v("coste_total") == pytest.approx(f["coste"]["total"])
        assert v("total") == pytest.approx(f["total"])
        assert (v("rank") or None) == f.get("rank")
    top = wb["Top20"]
    best = min((f for f in res.filas if f.get("rank")), key=lambda f: f["rank"])
    assert top["D2"].value == best["listing"].titulo
    for sh in wb.worksheets:
        assert sh.freeze_panes is None
