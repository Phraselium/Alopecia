"""Regla de etiqueta (fronteras), fichero DGT con matrícula de prueba y prioridad DGT > anuncio > regla."""
import zipfile
from pathlib import Path

import pytest
import yaml

from src.dgt import DGTIndex, find_plate, label_from_code
from src.etiqueta import asignar, label_rule
from src.models import Listing

BASE = Path(__file__).resolve().parents[1]


@pytest.fixture
def zbe():
    return yaml.safe_load((BASE / "zbe.yaml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fuel,y,m,exp", [
    ("gasolina", 2000, 12, ("A", False)), ("gasolina", 2001, 1, ("B", False)),
    ("gasolina", 2000, None, ("A", True)), ("gasolina", 2001, None, ("A", True)),      # frontera sin mes: la peor
    ("gasolina", 2005, 12, ("B", False)), ("gasolina", 2006, 1, ("C", False)), ("gasolina", 2006, None, ("C", False)),
    ("diesel", 2005, 12, ("A", False)), ("diesel", 2006, 1, ("B", False)),
    ("diesel", 2005, None, ("A", True)), ("diesel", 2006, None, ("A", True)),
    ("diesel", 2015, 8, ("B", False)), ("diesel", 2015, 9, ("C", False)), ("diesel", 2015, None, ("B", True)),
    ("diesel", 2016, None, ("C", False)), ("hibrido", 2009, None, ("ECO", False)), ("glp", 2012, 3, ("ECO", False)),
    ("electrico", 2014, None, ("CERO", False)),
])
def test_regla_fronteras(zbe, fuel, y, m, exp):
    assert label_rule(fuel, y, m, zbe) == exp


def _fake_dgt(tmp_path: Path) -> DGTIndex:
    d = tmp_path / "data" / "dgt"
    d.mkdir(parents=True)
    with zipfile.ZipFile(d / "export_dist_ambiental.zip", "w") as z:
        z.writestr("export_distintivo_ambiental.txt",
                   "MATRICULA|TIPO DE ETIQUETA\n1234BCD|16TC\n0000XYZ|SIN DISTINTIVO\n9876KLM|16TE\nV1234AB|16TB\n")
    ix = DGTIndex(tmp_path)
    assert ix.ensure("test", allow_download=False)
    return ix


def test_dgt_lookup(tmp_path):
    ix = _fake_dgt(tmp_path)
    assert ix.lookup("1234BCD") == ("C", "16TC")
    assert ix.lookup("0000XYZ") == ("A", "SIN DISTINTIVO")
    assert ix.lookup("9876KLM")[0] == "ECO"
    assert ix.lookup("V1234AB")[0] == "B"
    assert ix.lookup("1111ZZZ") is None
    assert label_from_code("16T0") == "CERO" and label_from_code("16MB") == "B"


def test_find_plate():
    assert find_plate("Seat Ibiza matrícula 1234-BCD, ITV al día") == "1234BCD"
    assert find_plate("Ford Focus V-1234-AB") == "V1234AB"
    assert find_plate("Año 2012, 145000 km") is None


def test_prioridad(tmp_path, zbe):
    ix = _fake_dgt(tmp_path)
    l = Listing(plataforma="p", id_externo="1", url="u", titulo="t", combustible="diesel", anio=2015,
                matricula="1234BCD", etiqueta_anuncio="B")
    assert (asignar(l, zbe, ix).etiqueta_dgt, l.etiqueta_fuente) == ("C", "DGT")
    l.matricula = None
    assert (asignar(l, zbe, ix).etiqueta_dgt, l.etiqueta_fuente) == ("B", "anuncio")
    l.etiqueta_anuncio = None
    assert (asignar(l, zbe, ix).etiqueta_dgt, l.etiqueta_fuente, l.etiqueta_dudosa) == ("B", "regla", True)


def test_informe_horizonte_B(zbe):
    from src.report import _etiqueta_md

    class P:
        pass
    p = P()
    p.zbe = zbe
    l = Listing(plataforma="p", id_externo="1", url="u", titulo="t", etiqueta_dgt="B", etiqueta_fuente="regla",
                etiqueta_dudosa=True)
    txt = _etiqueta_md({"listing": l}, p)
    assert "Dudosa" in txt and "solo restringe la etiqueta A" in txt and "no hay fecha prevista" in txt
