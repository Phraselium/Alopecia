from src.extract import extract_signals
from src.normalize import norm_brand, norm_engine, norm_fuel, norm_gearbox, norm_model


def test_brand_aliases():
    assert norm_brand("VW", "") == "Volkswagen"
    assert norm_brand(None, "Citroen C3 1.4") == "Citroën"
    assert norm_brand(None, "Alfa Romeo Mito") == "Alfa Romeo"


def test_model_and_segment():
    assert norm_model("Seat", "leon", "") == ("León", "compacto")
    assert norm_model("Mazda", None, "Mazda 2 1.5 Skyactiv") == ("2", "utilitario")
    assert norm_model("Kia", "Cee'd", "") == ("Ceed", "compacto")


def test_engine():
    assert norm_engine("1.4 16v TSI 122cv") == "1.4 TSI"
    assert norm_engine("1,2 PureTech 82") == "1.2 PureTech"
    assert norm_engine("1.33 Dual VVT-i") == "1.33 VVT-i"
    assert norm_engine("1398cc") == "1.4"
    assert norm_engine("Opel Corsa 1.4 Turbo") == "1.4 Turbo"
    assert norm_engine(None) is None


def test_fuel_gearbox():
    assert norm_fuel(None, "Auris 1.8 Hybrid") == "hibrido"
    assert norm_fuel("Gasolina") == "gasolina"
    assert norm_fuel(None, "Golf 1.6 TDI") == "diesel"
    assert norm_gearbox(None, "Polo 1.2 TSI DSG") == "automatico"


def test_signals():
    s = extract_signals("Yaris", "ITV en vigor hasta 2027, libro de revisiones sellado, único propietario, correa recién cambiada")
    assert s["itv_vigor"] and s["libro_mantenimiento"] and s["correa_cambiada"]
    assert s["num_propietarios"] == 1
    s = extract_signals("Clio", "Se vende sin ITV. Dos propietarios.")
    assert s["itv_vigor"] is False and s["num_propietarios"] == 2
    assert extract_signals("x", "nada")["itv_vigor"] is None


def test_robots_rfc9309():
    from pathlib import Path
    from src.robots import Robots
    txt = """User-agent: *
Disallow: /*pg=7*
Disallow: /Detail/
Allow: /*.js
Disallow: /api/
Allow: /api/public
User-agent: BadBot
Disallow: /
"""
    r = Robots(txt)
    ua = "Mozilla/5.0 Chrome"
    assert r.can_fetch(ua, "https://x/segunda-mano/?MaxPrice=4600")
    assert not r.can_fetch(ua, "https://x/segunda-mano/?pg=7")
    assert not r.can_fetch(ua, "https://x/Detail/1")
    assert r.can_fetch(ua, "https://x/api/public/x")
    assert not r.can_fetch(ua, "https://x/api/x")
    assert not r.can_fetch("BadBot/1.0", "https://x/anything")


def test_pro_signals():
    from src.extract import extract_pro_signals
    s = extract_pro_signals("Precio al contado: 12990 euros. Garantía de 12 meses ampliable. Revisión de 150 puntos. "
                            "Kilómetros certificados. 15 días de devolución. Gastos de gestión: 290 €")
    assert s["precio_contado"] == 12990 and s["garantia_meses"] == 12 and s["garantia_ampliable"]
    assert s["revision_puntos"] == 150 and s["km_certificados"] and s["devolucion_dias"] == 15
    assert s["gastos_gestion_eur"] == 290
    assert extract_pro_signals("Transferencia incluida. Garantía 1 año")["gastos_incluyen_transferencia"]
    assert extract_pro_signals("Garantía 1 año")["garantia_meses"] == 12
