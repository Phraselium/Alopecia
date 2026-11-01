"""Perfil mercado: coste total de propiedad, caballos fiscales, IVTM, ITP, frontera eficiente, regresión HC1 y paridad del
Excel (LibreOffice). Datos SINTÉTICOS (no se escriben en las salidas del proyecto)."""
import math
import random
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.mercado import model as M
from src.mercado.analysis import run_analysis
from src.mercado.stats import coef, frontera, ols

BASE = Path(__file__).resolve().parents[1]
L = lambda n: yaml.safe_load((BASE / n).read_text(encoding="utf-8"))  # noqa: E731


@pytest.fixture
def mcfg():
    return L("config_mercado.yaml")


@pytest.fixture
def sup():
    return L("mercado_supuestos.yaml")


def test_cvf_formula_oficial():
    # 1.6 de 4 cilindros (1.598 cc): 0,08 · (399,5)^0,6 · 4 ≈ 11,66 CVF; eléctrico de 100 kW: 100/5,152
    assert M.cvf(1598, None, "gasolina") == pytest.approx(0.08 * (1598 / 4) ** 0.6 * 4)
    assert M.cvf(1598, None, "gasolina") == pytest.approx(11.66, abs=0.02)
    assert M.n_cilindros(999) == 3 and M.n_cilindros(1998) == 4
    assert M.cvf(None, 136, "electrico") == pytest.approx(136 * 0.7355 / 5.152)
    assert M.cvf(None, None, "gasolina") is None


def test_ivtm_tramos_y_bonificacion(sup):
    assert M.ivtm(7.9, "gasolina", sup) == pytest.approx(21.20)
    assert M.ivtm(11.66, "gasolina", sup) == pytest.approx(58.87)
    assert M.ivtm(12.0, "diesel", sup) == pytest.approx(128.05)
    assert M.ivtm(25, "gasolina", sup) == pytest.approx(219.01)
    assert M.ivtm(19.4, "electrico", sup) == pytest.approx(167.27 * 0.25)
    assert M.ivtm(None, "gasolina", sup) == pytest.approx(sup["ivtm"]["cuota_sin_dato"])


def test_itp_particular_profesional_y_cuota_fija():
    fiscal = L("fiscal.yaml")
    base = {"precio": 10000, "vendedor": "particular", "tipo_m": "ocasion"}
    assert M.itp(base, 5, 1598, fiscal) == pytest.approx(600)
    assert M.itp(dict(base, vendedor="profesional"), 5, 1598, fiscal) == 0
    assert M.itp(dict(base, tipo_m="km0"), 0, 1598, fiscal) == 0
    viejo = M.itp(dict(base, precio=3000), 14, 1598, fiscal)
    assert viejo == pytest.approx(next(c["cuota_eur"] for c in fiscal["itp"]["cuotas_fijas"]
                                       if c["antiguedad_mas_de_anios"] == 12 and c["cc_min"] <= 1598 <= (c["cc_max"] or 99999)))


def test_coste_total_componentes(sup):
    fiscal = L("fiscal.yaml")
    uso = {"km_anio": 12000, "anios": 5}
    dep = {"*|*": {"factor5": 0.6}, "compacto|gasolina": {"factor5": 0.5}}
    a = {"precio": 15000, "vendedor": "profesional", "tipo_m": "ocasion", "consumo_wltp": 5.0}
    cons = M.consumo(a, "compacto", "gasolina", sup)
    assert cons == pytest.approx(5.0 * (1 + sup["desfase_wltp_real"]["gasolina"]))
    t = M.tco(a, "compacto", "gasolina", 4, 1498, M.cvf(1498, None, "gasolina"), cons, sup, fiscal, dep, uso)
    energia = cons * 12000 / 100 * sup["precio_energia"]["gasolina"]
    assert t["energia"] == pytest.approx(energia)
    assert t["depreciacion"] == pytest.approx(15000 * 0.5)
    assert t["seguro"] == sup["seguro"]["terceros_ampliado"]["compacto"]
    assert t["neum"] == pytest.approx(12000 / sup["neumaticos"]["duracion_km"] * sup["neumaticos"]["juego"]["compacto"])
    assert t["tco"] == pytest.approx(t["itp"] + t["tasa"] + t["depreciacion"] + 5 * t["uso_anual"])
    assert t["coste_anual"] == pytest.approx(t["tco"] / 5)
    # nuevo: sin tasa de transferencia y todo riesgo; eléctrico: consumo por defecto en kWh
    n = M.tco(dict(a, tipo_m="nuevo"), "compacto", "electrico", 0, None, M.cvf(None, 150, "electrico"),
              M.consumo({}, "compacto", "electrico", sup), sup, fiscal, dep, uso)
    assert n["tasa"] == 0 and n["seguro"] == sup["seguro"]["todo_riesgo"]["compacto"]
    assert n["energia"] == pytest.approx(sup["consumo_por_defecto"]["electrico"]["compacto"] * 120 * sup["precio_energia"]["electrico"])


def test_frontera_pareto():
    pts = [(1000, 50, "a"), (1200, 60, "b"), (1100, 40, "c"), (1500, 60, "d"), (900, 30, "e"), (2000, 80, "f")]
    assert frontera(pts) == ["e", "a", "b", "f"]


def test_ols_hc1_y_efectos_fijos():
    rnd = np.random.default_rng(1)
    n, g = 3000, 60
    grp = rnd.integers(0, g, n)
    fe = rnd.normal(0, 1, g)[grp]
    x1 = rnd.normal(0, 1, n) + 0.5 * fe        # correlacionado con el efecto fijo
    x2 = rnd.integers(0, 2, n)
    e = rnd.normal(0, 1, n) * (1 + np.abs(x1))  # heterocedástico
    y = 2.0 * x1 - 0.7 * x2 + 3 * fe + e
    r = ols(y, np.column_stack([x1, x2]), ["x1", "x2"], list(grp))
    b1, s1, lo, hi = coef(r, "x1")
    assert abs(b1 - 2.0) < 0.1 and lo < 2.0 < hi
    assert abs(coef(r, "x2")[0] + 0.7) < 0.15
    # HC1 a mano sobre los datos ya transformados
    X = np.column_stack([x1, x2]).astype(float)
    yy = y.astype(float).copy()
    for M_ in (yy[:, None], X):
        for k in range(g):
            M_[grp == k] -= M_[grp == k].mean(axis=0)
    XtXi = np.linalg.inv(X.T @ X)
    res = yy - X @ (XtXi @ X.T @ yy)
    V = XtXi @ (X * res[:, None] ** 2).T @ X @ XtXi * n / (n - 2 - g)
    assert s1 == pytest.approx(math.sqrt(V[0, 0]), rel=1e-6)


def synthetic(n=600, seed=3):
    rnd = random.Random(seed)
    modelos = [("Seat", "Ibiza", "utilitario"), ("Seat", "León", "compacto"), ("Toyota", "Corolla", "compacto"),
               ("Volkswagen", "Golf", "compacto"), ("Peugeot", "2008", "suv"), ("Dacia", "Sandero", "utilitario"),
               ("Kia", "Ceed", "compacto"), ("Renault", "Clio", "utilitario"), ("Hyundai", "Tucson", "suv"), ("Ford", "Focus", "compacto")]
    fuels = ["Gasolina", "Diésel", "Híbrido", "Eléctrico", "Híbrido enchufable"]
    out = []
    for i in range(n):
        mk, md, _s = modelos[i % len(modelos)]
        anio = rnd.randint(2008, 2026)
        fuel = rnd.choice(fuels)
        tipo = "nuevo" if anio == 2026 and rnd.random() < 0.5 else ("km0" if anio >= 2025 and rnd.random() < 0.3 else "ocasion")
        km = 0 if tipo == "nuevo" else rnd.randint(0 if tipo == "km0" else 5000, 50 if tipo == "km0" else 250000)
        base = 30000 * math.exp(-0.11 * (2026 - anio)) * (1 - km / 600000)
        out.append({"uid": f"TEST:{i}", "plataforma": rnd.choice(["autoscout24", "cochesnet"]),
                    "zona": rnd.choice(["valencia", "valencia", "valencia", "madrid"]), "tipo": tipo, "marca": mk, "modelo": md,
                    "version": rnd.choice(["1.0 TSI", "1.5", "2.0 TDI", None]), "titulo": f"{mk} {md} " + rnd.choice(["1.0 TSI", "1.6 DSG", "1.5 Hybrid aut.", "2.0"]),
                    "anio": anio, "mes": None, "km": km, "precio": round(base * rnd.uniform(0.85, 1.15)), "precio_financiado": None,
                    "combustible": fuel, "cambio": rnd.choice(["Manual", "Automático", None]), "cv": rnd.choice([None, 90, 130, 204]),
                    "cc": rnd.choice([None, 999, 1498, 1968]), "carroceria_raw": None, "etiqueta": rnd.choice([None, "C", "B", "ECO"]),
                    "vendedor": rnd.choice(["particular", "profesional"]), "garantia_meses": rnd.choice([None, 12, 24]),
                    "ubicacion": None, "cp": None, "url": f"https://example.invalid/{i}", "generacion": None,
                    "consumo_wltp": rnd.choice([None, 4.8, 6.1]), "co2": None, "descripcion": None, "raw_ref": None,
                    "first_seen": "2026-10-01T00:00:00", "gone_at": None})
    return out


def test_analisis_sintetico(mcfg):
    res = run_analysis(synthetic(), mcfg, BASE)
    assert res["ads"] and res["dep"]["*|*"]["b_edad"] < 0              # el valor cae con la edad
    assert "Cambio automático frente a manual" in res["primas"]
    for f, lst in res["frontera"].items():
        if f == "global":
            continue
        cal = [a["calidad_intr"] for a in lst]
        assert cal == sorted(cal) and len(set(a["uid"] for a in lst)) == len(lst)   # por coste creciente, calidad creciente
    for f, lst in res["top_franja"].items():
        assert [a["ratio"] for a in lst] == sorted([a["ratio"] for a in lst], reverse=True)


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice no instalado")
def test_excel_mercado_coincide_con_python(tmp_path, mcfg):
    import sys
    sys.path.insert(0, str(BASE / "tools"))
    from verify_mercado import verify
    from src.mercado.excel import write_workbook
    res = run_analysis(synthetic(), mcfg, BASE)
    p = tmp_path / "mercado.xlsx"
    write_workbook(p, res)
    errors, frozen, mism = verify(p, res)
    assert not errors and not frozen and not mism, (errors[:5], frozen, mism[:5])
