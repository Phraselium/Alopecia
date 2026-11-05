"""Berlinas medianas: preferencia de estilo, Multitronic, EA888, Twincharger, modelos excluidos, consumo/seguro segmento D."""
import pytest

from src.models import Listing
from src.pipeline import process
from src.scoring import Params, consumo_estimado, engine_adjust, seguro_estimado


@pytest.fixture
def p(cfg, fiscal, rel):
    return Params(cfg, fiscal, rel)


def mk(i, titulo, marca, modelo, anio=2006, **kw):
    d = dict(plataforma="t", id_externo=str(i), url=f"u{i}", titulo=titulo, marca=marca, modelo=modelo,
             precio=3000 + 300 * i, anio=anio, km=100000 + 15000 * i, combustible="gasolina", vendedor="profesional",
             etiqueta_anuncio="C", descripcion="ITV al día, libro de revisiones", num_fotos=10)
    d.update(kw)
    return Listing(**d)


def test_prioritarios_por_estetica(p):
    ls = [mk(1, "Toyota Avensis 1.8 VVT-i Sol", "Toyota", "Avensis"),
          mk(2, "Audi A4 2.0 TFSI", "Audi", "A4", cambio="manual"),
          mk(4, "Seat Ibiza 1.4 16v", "Seat", "Ibiza", anio=2009),
          mk(5, "Honda Accord 2.4 i-VTEC", "Honda", "Accord")]
    res = process(ls, p, set())
    by = {f["listing"].titulo: f for f in res.filas}
    assert by["Toyota Avensis 1.8 VVT-i Sol"]["listing"].estetica_modelo == 4
    assert by["Audi A4 2.0 TFSI"]["listing"].estetica_modelo == 5
    ibiza = next(f for t, f in by.items() if "Ibiza" in t)
    assert ibiza["listing"].estetica_modelo == 2 and ibiza["listing"].estetica_ref is None
    accord = by["Honda Accord 2.4 i-VTEC"]
    assert accord["listing"].estetica_ref is None and accord["listing"].estetica_modelo == 3   # 2.4: no es el 2.0 de la lista


def test_modelos_excluidos_y_multitronic(p):
    ls = [mk(1, "Toyota Aygo 1.0", "Toyota", "Aygo", anio=2012),
          mk(2, "Peugeot 107 1.0", "Peugeot", "107", anio=2012),
          mk(3, "Citroën C1 1.0", "Citroën", "C1", anio=2012),
          mk(4, "Audi A4 2.0 Multitronic", "Audi", "A4"),
          mk(5, "Audi A4 1.8T automático", "Audi", "A4", cambio="automatico"),
          mk(6, "Audi A4 2.0 TFSI manual", "Audi", "A4", cambio="manual", anio=2007)]
    res = process(ls, p, set())
    fuera = {l.titulo: " | ".join(m) for l, m in res.descartados}
    for t in ("Toyota Aygo 1.0", "Peugeot 107 1.0", "Citroën C1 1.0"):
        assert "modelo excluido" in fuera[t]
    assert "Multitronic" in fuera["Audi A4 2.0 Multitronic"]
    dentro = {f["listing"].titulo: f["listing"] for f in res.filas}
    assert dentro["Audi A4 1.8T automático"].multitronic == "posible"
    assert "Multitronic" in res.avisos.get(dentro["Audi A4 1.8T automático"].uid, "")
    assert dentro["Audi A4 2.0 TFSI manual"].multitronic is None


def test_ea888_y_twincharger(p):
    b7 = Listing(plataforma="t", id_externo="1", url="u", titulo="A4", marca="Audi", modelo_key="Audi A4", motor_key="2.0 TFSI", anio=2006)
    b8 = Listing(plataforma="t", id_externo="2", url="u", titulo="A4", marca="Audi", modelo_key="Audi A4", motor_key="2.0 TFSI", anio=2010)
    exeo18 = Listing(plataforma="t", id_externo="3", url="u", titulo="Exeo", marca="Seat", modelo_key="Seat Exeo", motor_key="1.8 TSI", anio=2010)
    assert engine_adjust(b7, p.rel)[0] == 0          # EA113, no EA888
    assert engine_adjust(b8, p.rel)[0] == -20
    assert engine_adjust(exeo18, p.rel)[0] == -20
    ls = [mk(1, "Volkswagen Golf 1.4 TSI 170cv GT", "Volkswagen", "Golf", anio=2008, potencia_cv=170),
          mk(2, "Volkswagen Golf 1.4 TSI 122cv", "Volkswagen", "Golf", anio=2010, potencia_cv=122)]
    res = process(ls, p, set())
    mot = {f["listing"].titulo: f["listing"].motor_key for f in res.filas}
    assert mot["Volkswagen Golf 1.4 TSI 170cv GT"] == "1.4 TSI Twincharger"
    assert mot["Volkswagen Golf 1.4 TSI 122cv"] == "1.4 TSI"
    tw = next(f for f in res.filas if "170cv" in f["listing"].titulo)
    assert any("Twincharger" in h["motor"] for h in tw["fiabilidad"]["problemas"])


def test_consumo_y_seguro_segmento_d(p):
    avensis = Listing(plataforma="t", id_externo="1", url="u", titulo="Avensis", marca="Toyota", modelo_key="Toyota Avensis",
                      carroceria="berlina_d", combustible="gasolina")
    laguna = Listing(plataforma="t", id_externo="2", url="u", titulo="Laguna", marca="Renault", modelo_key="Renault Laguna",
                     carroceria="berlina_d", combustible="gasolina")
    ibiza = Listing(plataforma="t", id_externo="3", url="u", titulo="Ibiza", marca="Seat", modelo_key="Seat Ibiza",
                    carroceria="utilitario", combustible="gasolina")
    diesel = Listing(plataforma="t", id_externo="4", url="u", titulo="x", marca="Seat", modelo_key="Seat Ibiza",
                     carroceria="utilitario", combustible="diesel")
    assert consumo_estimado(avensis, p.fiscal) == 7.0
    assert consumo_estimado(laguna, p.fiscal) == 8.0
    assert consumo_estimado(ibiza, p.fiscal) < consumo_estimado(laguna, p.fiscal)
    assert consumo_estimado(diesel, p.fiscal) is None
    assert seguro_estimado(laguna, p.fiscal) > seguro_estimado(ibiza, p.fiscal)
