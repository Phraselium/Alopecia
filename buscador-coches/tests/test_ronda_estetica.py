"""Etiqueta dudosa que cumple el mínimo, anuncio incoherente, color, estética, particulares, presupuesto suave y seguridad."""
import pytest

from src.etiqueta import asignar, opciones_regla
from src.fraud import search_filter_reasons
from src.models import Listing
from src.pipeline import process
from src.scoring import Params, estado_presupuesto, penal_presupuesto


@pytest.fixture
def p(cfg, fiscal, rel):
    return Params(cfg, fiscal, rel)


def mk(i, titulo, marca, modelo, anio=2007, **kw):
    d = dict(plataforma="t", id_externo=str(i), url=f"u{i}", titulo=titulo, marca=marca, modelo=modelo,
             precio=2500 + 300 * i, anio=anio, km=90000 + 9000 * i, combustible="gasolina", vendedor="profesional",
             descripcion="ITV al día, libro de revisiones", num_fotos=10, color_raw="Blanco")
    d.update(kw)
    return Listing(**d)


# ---------- etiqueta ----------
def test_dudosa_que_cumple_minimo_pasa(p):
    # Diésel de 2015 sin mes: B o C (C desde 09-2015) -> dudosa, peor B >= B -> pasa; se puntúa B
    l = mk(1, "Seat Ibiza 1.2 TDI", "Seat", "Ibiza", anio=2015, combustible="diesel", fecha_matriculacion="2015")
    asignar(l, p.zbe)
    assert l.etiqueta_dudosa and l.etiqueta_opciones == "B/C" and l.etiqueta_dgt == "B"
    assert not [m for m in search_filter_reasons(l, p.cfg, p.rel) if m.startswith("etiqueta")]


def test_dudosa_con_opcion_A_descarta(p):
    l = mk(2, "Seat Ibiza 1.4", "Seat", "Ibiza", anio=2001, fecha_matriculacion="2001")
    asignar(l, p.zbe)
    assert l.etiqueta_dgt == "A" and "B" in l.etiqueta_opciones
    assert any(m.startswith("etiqueta A < B") for m in search_filter_reasons(l, p.cfg, p.rel))


def test_regla_gasolina_desde_2002_pasa(p):
    for anio in (2002, 2004, 2006, 2010):
        l = mk(anio, "Toyota Avensis 1.8", "Toyota", "Avensis", anio=anio, fecha_matriculacion=str(anio))
        asignar(l, p.zbe)
        assert l.etiqueta_fuente == "regla" and l.etiqueta_dgt in ("B", "C")
        assert not [m for m in search_filter_reasons(l, p.cfg, p.rel) if m.startswith("etiqueta")]
    assert opciones_regla("gasolina", 2005, None, p.zbe) == ["B"]
    assert opciones_regla("gasolina", 2006, None, p.zbe) == ["C"]


def test_anuncio_incoherente_usa_regla(p):
    l = mk(3, "Toyota Avensis 1.8 VVTi Sol", "Toyota", "Avensis", anio=2004, etiqueta_anuncio="C", fecha_matriculacion="2004")
    asignar(l, p.zbe)
    assert l.etiqueta_incoherente == "C" and l.etiqueta_dgt == "B" and l.etiqueta_fuente == "regla"
    res = process([mk(3, "Toyota Avensis 1.8 VVTi Sol", "Toyota", "Avensis", anio=2004, etiqueta_anuncio="C",
                      fecha_matriculacion="2004")], p, set())
    assert "anuncio incoherente" in res.avisos[res.filas[0]["listing"].uid]


def test_anuncio_coherente_se_respeta(p):
    l = mk(4, "Seat Ibiza 1.2 TDI", "Seat", "Ibiza", anio=2015, combustible="diesel", fecha_matriculacion="2015", etiqueta_anuncio="C")
    asignar(l, p.zbe)
    assert l.etiqueta_incoherente is None and l.etiqueta_dgt == "C" and l.etiqueta_fuente == "anuncio"


# ---------- color ----------
@pytest.mark.parametrize("raw,exp", [("Plateado", "plata"), ("Gris Antracita", "gris_oscuro"), ("Blanco nacarado", "blanco"),
                                     ("COMMON.COLOR_GRAY", "gris_medio"), ("Gris / Plata", "plata"), ("Azul marino", "azul_marino"),
                                     ("Marrón oscuro", "marron_oscuro"), ("Champán", "champan"), ("Verde lima", "verde_claro"),
                                     ("Negro metalizado", "negro"), ("xyz", None)])
def test_color_normalizado(p, raw, exp):
    from src.atributos import norm_color
    assert norm_color(raw, p.estetica) == exp


def test_color_puntos_y_exclusion(p):
    ls = [mk(1, "Seat León 1.6", "Seat", "León", color_raw="Plateado"), mk(2, "Seat León 1.6 Stylance", "Seat", "León", color_raw="Azul"),
          mk(3, "Seat León 1.6 Reference", "Seat", "León", color_raw="Beige"), mk(4, "Seat León 1.6 Style", "Seat", "León", color_raw=None),
          mk(5, "Seat León 1.6 Sport", "Seat", "León", color_raw="Negro")]
    res = process(ls, p, set())
    sc = {f["listing"].id_externo: f["color"]["score"] for f in res.filas}
    pts = p.estetica["colores"]["puntos"]
    assert sc["1"] == pts["maxima"] and sc["2"] == pts["media"] and sc["3"] == pts["resta"] and sc["4"] == p.neutro
    assert any("color negro excluido" in " ".join(m) for _l, m in res.descartados)


def test_color_solo_con_contexto(p):
    from src.atributos import from_text
    l = mk(1, "Seat León", "Seat", "León", color_raw=None, descripcion="Interior negro, llantas negras. Color exterior gris plata.")
    from_text(l, p.estetica)
    assert l.color == "plata"


# ---------- estética ----------
def test_estetica_modelo_y_atributos(p):
    ls = [mk(1, "Audi A3 1.6 Attraction", "Audi", "A3", anio=2006, descripcion="llantas de aleación de 17\", faros xenón, lunas tintadas"),
          mk(2, "Seat Ibiza 1.4 Reference", "Seat", "Ibiza", anio=2006, descripcion="tapacubos nuevos"),
          mk(3, "Seat León 1.6 FR", "Seat", "León", anio=2008)]
    res = process(ls, p, set())
    by = {f["listing"].id_externo: f for f in res.filas}
    a3, ib, le = by["1"], by["2"], by["3"]
    assert a3["listing"].estetica_modelo == 5 and a3["listing"].at_llantas == "16+" and a3["listing"].at_faros
    assert ib["listing"].estetica_modelo == 2 and ib["listing"].at_llantas == "chapa"
    assert le["listing"].at_acabado == "fr"
    pa = p.estetica["puntos_atributos"]
    assert a3["estetica"]["s_atributos"] == pa["base"] + pa["llantas_16"] + pa["faros"] + pa["tintados"]
    assert ib["estetica"]["s_atributos"] == pa["base"] - pa["chapa"]
    assert a3["estetica"]["score"] == pytest.approx(p.estetica["peso_modelo"] * 100 + p.estetica["peso_atributos"] * a3["estetica"]["s_atributos"])
    assert a3["estetica"]["score"] > le["estetica"]["score"] > ib["estetica"]["score"]


def test_particulares_solo_modelos_estetica(p):
    ls = [mk(1, "Audi A3 1.6", "Audi", "A3", anio=2006, vendedor="particular"),
          mk(2, "Seat Ibiza 1.4", "Seat", "Ibiza", anio=2008, vendedor="particular"),
          mk(3, "Mazda 6 2.0 Sportive", "Mazda", "6", anio=2005, vendedor="particular")]
    res = process(ls, p, set())
    dentro = {f["listing"].id_externo for f in res.filas}
    assert dentro == {"1", "3"}
    f = next(f for f in res.filas if f["listing"].id_externo == "1")
    assert "particular sin garantía: pedir informe DGT, historial ITV y revisión precompra" in res.avisos[f["listing"].uid]
    assert f["seguridad"]["penal_particular"] == p.cfg["scoring"]["seguridad_compra"]["penal_particular_sin_garantia"]
    assert f["coste"]["real_estimado"] > f["coste"]["total"]


# ---------- presupuesto suave ----------
def test_presupuesto_suave(cfg):
    assert estado_presupuesto(5000, cfg) == "sí" and penal_presupuesto(5000, cfg) == 0
    assert estado_presupuesto(5400, cfg) == "negociar" and penal_presupuesto(5400, cfg) == pytest.approx(8)
    assert estado_presupuesto(6000, cfg) == "negociar" and penal_presupuesto(6000, cfg) == pytest.approx(20)
    assert estado_presupuesto(6001, cfg) == "no"


def test_presupuesto_techo_excluye(p):
    ls = [mk(1, "Seat León 1.6", "Seat", "León", precio=4800), mk(2, "Seat León 1.6 Sport", "Seat", "León", precio=5800, km=120000),
          mk(3, "Seat León 1.6 Style", "Seat", "León", precio=5999, km=60000, gastos_gestion_eur=400.0)]
    res = process(ls, p, set())
    by = {f["listing"].id_externo: f for f in res.filas}
    assert by["2"]["estado"] == "negociar" and by["2"]["coste"]["exceso"] > 0 and by["2"]["penal_presupuesto"] > 0
    assert "3" not in by and any("presupuesto" in " ".join(m) for _l, m in res.descartados)


# ---------- seguridad ----------
def test_seguridad_ncap_y_esp(p):
    ls = [mk(1, "Seat León 1.6", "Seat", "León", anio=2008, descripcion="ESP, ABS, ITV al día"),
          mk(2, "Dacia Sandero 1.2", "Dacia", "Sandero", anio=2016),
          mk(3, "Marca Rara X", "Lada", "Niva", anio=2008)]
    res = process(ls, p, set())
    by = {f["listing"].id_externo: f for f in res.filas}
    leon = by["1"]
    assert leon["listing"].esp == "sí" and leon["seguridad_vial"]["s_esp"] == 100
    if leon["listing"].ncap_estrellas:
        assert leon["seguridad_vial"]["s_ncap"] == pytest.approx(leon["listing"].ncap_estrellas / 5 * 100)
    assert by["2"]["listing"].esp == "sí" and "Reglamento" in by["2"]["listing"].esp_fuente
    sv = p.cfg["scoring"]["seguridad_vial"]
    for f in res.filas:
        assert f["seguridad_vial"]["score"] == pytest.approx(sv["peso_ncap"] * f["seguridad_vial"]["s_ncap"] + sv["peso_esp"] * f["seguridad_vial"]["s_esp"])


def test_pesos_suman_1(cfg):
    w = cfg["scoring"]["pesos"]
    assert sum(w.values()) == pytest.approx(1.0)
    assert w == {"fiabilidad": 0.22, "precio": 0.15, "estado": 0.12, "estetica": 0.12, "seguridad_vial": 0.10,
                 "seguridad_compra": 0.10, "coste_uso": 0.09, "km_edad": 0.05, "reventa": 0.03, "color": 0.02}


def test_diesel_excluidos_por_defecto(p):
    l = mk(1, "Seat León 1.9 TDI", "Seat", "León", combustible="diesel", anio=2008)
    assert "diésel excluido (uso urbano)" in search_filter_reasons(l, p.cfg, p.rel)
    p.cfg["filtros"]["diesel"]["excluir_todos"] = False
    assert "diésel excluido (uso urbano)" not in search_filter_reasons(l, p.cfg, p.rel)
