"""Filtro de averías: términos, negaciones, contexto de garantía, reparaciones hechas y ambiguos."""
import pytest

from src.averias import analizar


def cats(t):
    return [c for c, _ in analizar("", t).descartes]


@pytest.mark.parametrize("txt,cat", [
    ("Se vende para piezas", "para piezas"), ("El coche no arranca desde ayer", "no arranca"),
    ("Coche averiado", "averia"), ("Tiene una avería en el turbo", "averia"), ("motor gripado", "motor tocado/gripado"),
    ("Junta de culata tocada", "junta de culata"), ("caja de cambios rota", "caja de cambios"),
    ("el embrague patina", "embrague"), ("necesita embrague", "embrague"), ("ruido en la caja", "ruido"),
    ("echa humo azul", "humo"), ("consume aceite", "consume aceite"), ("testigo del motor encendido", "testigo encendido"),
    ("fallo de inyección", "fallo inyeccion/turbo/egr/fap"), ("FAP tocado", "fallo inyeccion/turbo/egr/fap"),
    ("se vende para reparar", "a reparar"), ("hay que arreglar el motor", "a reparar"), ("siniestro total", "siniestro"),
    ("golpe estructural", "siniestro"), ("coche inundado en la DANA", "inundado/dana"), ("SIN ITV", "sin itv / itv desfavorable"),
    ("ITV desfavorable", "sin itv / itv desfavorable"), ("sin papeles", "sin papeles"), ("tiene un embargo", "embargo"),
    ("reserva de dominio", "reserva de dominio"), ("dado de baja temporal", "baja temporal"),
    ("importación pendiente", "importacion pendiente"),
])
def test_descarta(txt, cat):
    assert cat in cats(txt)


@pytest.mark.parametrize("txt", [
    "Nunca ha tenido averías", "Sin golpes ni averías", "No consume aceite", "no echa humo",
    "Garantía de 12 meses contra averías", "vehículo de sustitución en caso de avería", "Seguro de averías incluido",
    "Junta de culata nueva y embrague cambiado", "avería del cambio reparada en concesionario oficial",
    "El aire acondicionado no funciona", "protector inferior del motor roto", "parachoques delantero para reparar",
    "ITV en vigor hasta 2027, sin testigos encendidos", "jamás ha tenido ningún siniestro",
])
def test_no_descarta(txt):
    assert cats(txt) == [], analizar("", txt).descartes


def test_revisar_y_registro():
    r = analizar("Seat Ibiza", "Tiene algún arañazo y unos detalles. Se vende así.")
    assert {c for c, _ in r.revisar} >= {"arañazos", "detalles", "se vende así", "no menciona la ITV"}
    r = analizar("Peugeot 207", "Vendo para reparar. ITV hasta mayo")
    assert r.descartes == [("a reparar", "para reparar")]           # registra la expresión exacta
    assert "no menciona la ITV" not in {c for c, _ in r.revisar}
