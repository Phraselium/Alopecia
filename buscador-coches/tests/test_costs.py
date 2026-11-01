from src.costs import coste_total
from src.models import Listing


def _l(**kw):
    base = dict(plataforma="test", id_externo="1", url="u", titulo="t", precio=4000, anio=2015,
                motor_key="1.4", vendedor="particular")
    base.update(kw)
    return Listing(**base)


def test_cuota_fija_5_12(fiscal):
    c = coste_total(_l(anio=2016), fiscal, 2026)  # 10 años, 1.4 -> 120 €
    assert c["itp"] == 120
    assert c["total"] == 4000 + 120 + fiscal["dgt"]["tasa_transferencia_eur"] + fiscal["dgt"]["informe_vehiculo_eur"]


def test_cuota_fija_mas_12(fiscal):
    assert coste_total(_l(anio=2010, motor_key="1.6"), fiscal, 2026)["itp"] == 60


def test_cilindrada_desconocida_tramo_alto(fiscal):
    c = coste_total(_l(anio=2016, motor_key=None), fiscal, 2026)
    assert c["itp"] == 280 and any("cilindrada" in a for a in c["avisos"])


def test_reciente_tipo_porcentual(fiscal):
    assert coste_total(_l(anio=2022), fiscal, 2026)["itp"] == 4000 * fiscal["itp"]["tipo"]


def test_profesional_sin_itp(fiscal):
    assert coste_total(_l(vendedor="profesional"), fiscal, 2026)["itp"] == 0
