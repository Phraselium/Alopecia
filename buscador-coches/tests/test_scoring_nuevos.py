"""Plataforma gemela, MINI Prince, cajas robotizadas, tope de precio por km y año a confirmar."""
import pytest
import yaml
from pathlib import Path

from src.etiqueta import asignar
from src.models import Listing
from src.pipeline import anio_alternativo, process
from src.scoring import Params, engine_adjust, model_score_ex, s_fiabilidad, s_precio

BASE = Path(__file__).resolve().parents[1]


@pytest.fixture
def p(cfg, fiscal, rel):
    return Params(cfg, fiscal, rel)


def test_gemelo_plataforma(p):
    aygo = model_score_ex("Toyota Aygo", "Toyota", p)
    for key, marca in (("Peugeot 107", "Peugeot"), ("Citroën C1", "Citroën")):
        base, pend, gem = model_score_ex(key, marca, p)
        assert gem == "Toyota Aygo" and not pend and base == pytest.approx(aygo[0])
    assert model_score_ex("Seat Córdoba", "Seat", p)[2] == "Seat Ibiza"
    assert model_score_ex("Seat Ibiza", "Seat", p)[2] is None          # con dato propio no hereda


def test_mini_prince(p):
    l = Listing(plataforma="t", id_externo="1", url="u", titulo="MINI One", marca="MINI", modelo_key="MINI MINI",
                motor_key="1.4", anio=2009)
    adj, hits = engine_adjust(l, p.rel)
    assert adj == -10 and "Prince" in hits[0]["problema"]
    l.anio = 2015
    assert engine_adjust(l, p.rel)[0] == 0


def test_caja_robotizada(p):
    ls = [Listing(plataforma="t", id_externo=str(i), url="u", titulo=t, marca=m, modelo=mo, precio=3500 + 100 * i, anio=2012,
                  km=100000 + 7000 * i, combustible="gasolina", vendedor="profesional", etiqueta_anuncio="C", descripcion="ITV al día")
          for i, (t, m, mo) in enumerate([("Opel Corsa 1.2 Easytronic", "Opel", "Corsa"), ("Fiat 500 1.2 Dualogic", "Fiat", "500"),
                                          ("Toyota Aygo 1.0 MMT", "Toyota", "Aygo"), ("Peugeot 208 1.2 ETG5", "Peugeot", "208"),
                                          ("Opel Corsa 1.2 MTA Enjoy", "Opel", "Corsa"), ("Opel Corsa 1.2 manual", "Opel", "Corsa")])]
    fuera = process(ls, p, set())          # por defecto: excluidas
    assert {l.titulo for l, m in fuera.descartados if any("caja robotizada" in x for x in m)} == \
        {l.titulo for l in ls if "manual" not in l.titulo}
    p.cfg["filtros"]["excluir_cajas_robotizadas"] = False
    res = process(ls, p, set())
    det = {f["listing"].titulo: f["listing"].caja_robotizada for f in res.filas}
    assert all(det[t] for t in det if "manual" not in t) and det["Opel Corsa 1.2 manual"] is None
    f = next(f for f in res.filas if "Easytronic" in f["listing"].titulo)
    assert f["fiabilidad"]["robotizada"] == p.cfg["scoring"]["penalizaciones"]["caja_robotizada"]


def test_tope_precio_km(cfg):
    l = Listing(plataforma="t", id_externo="1", url="u", titulo="t", precio=2000, km=220000)
    assert s_precio(l, 5000, cfg)["score"] == pytest.approx(20)        # 100 - 40·2
    l.km = 150000
    assert s_precio(l, 5000, cfg)["score"] == 100


def test_anio_a_confirmar(p):
    l = Listing(plataforma="t", id_externo="1", combustible="gasolina", anio=2007, fecha_matriculacion="2007",
                url="https://www.coches.net/ford-ka-16i-sportka-3p-gasolina-2005-en-valencia-71253044-covo.aspx",
                titulo="FORD Ka", etiqueta_anuncio="C")
    l.anio_alternativo = anio_alternativo(l)
    assert l.anio_alternativo == 2005
    asignar(l, p.zbe)
    assert l.etiqueta_dgt == "B" and l.etiqueta_dudosa and l.etiqueta_dudosa_anio   # 2005 gasolina = B: peor y dudosa
    l2 = Listing(plataforma="t", id_externo="2", combustible="gasolina", anio=2008, fecha_matriculacion="2008",
                 url="https://www.coches.net/x-gasolina-2007-en-valencia-1-covo.aspx", titulo="x", etiqueta_anuncio="C")
    l2.anio_alternativo = anio_alternativo(l2)
    asignar(l2, p.zbe)
    assert l2.anio_alternativo == 2007 and l2.etiqueta_dgt == "C" and not l2.etiqueta_dudosa   # no cambia la etiqueta
