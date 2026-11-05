"""Filtro estricto de averías y estado del coche en título + descripción.

- Texto normalizado: minúsculas, sin tildes, signos -> espacios.
- Patrones con raíces de palabra (p. ej. "averi\\w*" cubre avería, averiado, averías).
- Negaciones: si en las palabras anteriores (ventana corta, sin cruzar un punto) aparece "nunca", "sin", "no",
  "ningun(a)", "cero", "libre de", "jamas"… el término no cuenta. Ej.: "nunca ha tenido averías", "sin golpes",
  "no consume aceite". Hay patrones que YA llevan la negación ("sin itv", "no arranca") y no se anulan.
- Ambiguos -> "revisar" (no descarta): "detalles", "algún arañazo", "se vende así", y no mencionar la ITV.
Cada descarte registra la expresión exacta que lo provocó.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import strip_accents

# (categoría, regex sobre texto normalizado). Las raíces usan \w* para cubrir variantes.
DESCARTE = [
    ("para piezas", r"\b(para|solo|ideal para)\s+(piezas|despiece|desguace|recambios)\b|\bdespiece\b"),
    ("no arranca", r"\bno\s+(arranca|enciende)\b|\b(coche|motor|vehiculo|turismo)\s+(ya\s+)?no\s+(funciona|anda|tira|camina)\b"),
    ("averia", r"\baveri\w*\b"),
    ("motor tocado/gripado", r"\bmotor\s+(tocad\w*|gripad\w*|rot\w*|roto|fundid\w*|petad\w*|reventad\w*)\b|\bgripad\w*\b"),
    ("junta de culata", r"\bjunta\s+(de\s+)?culata\b|\bculata\s+(tocad\w*|rajad\w*|fisurad\w*)\b"),
    ("caja de cambios", r"\b(caja|cambio)\s+(de\s+cambios\s+)?(rot\w*|tocad\w*|averiad\w*|mal)\b|\bsincronizad\w*\s+(tocad\w*|mal)\b"),
    ("embrague", r"\bembrague\s+(patin\w*|tocad\w*|quemad\w*|rot\w*|a cambiar|para cambiar)\b"
                 r"|\b(necesita|falta|hay que cambiar|cambiar el|pide)\s+(un\s+|el\s+)?embrague\b|\bpatina\s+(el\s+)?embrague\b"),
    ("ruido", r"\bruid\w*\s+(de|en|del|en el|en la|de la)\s+(motor|caja|cambio|embrague|transmision|diferencial|turbo|distribucion|cadena)\b"
              r"|\b(motor|caja|cambio)\s+(hace|tiene|con)\s+(un\s+)?ruid\w*\b"),
    ("humo", r"\b(echa|hecha|saca|tira|suelta|con)\s+(algo\s+de\s+|un\s+poco\s+de\s+|mucho\s+)?humo\b|\bhumo\s+(azul|blanco|negro)\b"),
    ("consume aceite", r"\b(consume|gasta|quema|pierde|come)\s+(algo\s+de\s+|un\s+poco\s+de\s+)?aceite\b|\bconsumo\s+de\s+aceite\b"),
    ("testigo encendido", r"\b(testigo|chivato|luz|piloto)\w*\s+((de|del|de la)\s+\w+\s+)?(encendid\w*|activad\w*|se enciende|iluminad\w*)\b"
                          r"|\b(sale|salta|se enciende)\s+(el\s+)?(testigo|chivato)\b"),
    ("fallo inyeccion/turbo/egr/fap", r"\b(fallo|averia|problema|error)\w*\s+(de\s+|del\s+|en\s+(el\s+|la\s+)?)?"
                                       r"(inyeccion|inyector\w*|turbo|egr|fap|dpf|filtro de particulas|centralita|bomba)\b"
                                       r"|\b(turbo|egr|fap|dpf|inyector\w*)\s+(tocad\w*|rot\w*|averiad\w*|mal|a cambiar)\b"),
    ("a reparar", r"\b(se\s+vende\s+)?para\s+(su\s+)?(reparar|arreglar|reparacion)\b(?!\s+(el|la|los|las)\s+(cable|faro|retrovisor|tapiceria|asiento|maneta|cierre|elevalunas))"
                  r"|\b(necesita|hay que|a)\s+(reparar|arreglar)\s+(el\s+|la\s+)?(motor|caja|cambio|embrague|turbo|culata|distribucion|inyector\w*)\b"
                  r"|\breparacion\s+pendiente\s+(de\s+)?(motor|caja|cambio|embrague)\b"),
    ("siniestro", r"\bsiniestr\w*\b|\bgolpe\s+(estructural|fuerte|grave)\b|\bdanos?\s+estructural\w*\b|\bchasis\s+(tocad\w*|dañad\w*|danad\w*)\b"),
    ("inundado/dana", r"\binundad\w*\b|\bdana\b|\briada\b"),
    ("sin itv / itv desfavorable", r"\bsin\s+itv\b|\bitv\s+(caducad\w*|vencid\w*|desfavorable|negativa|suspendid\w*|pendiente)\b"
                                    r"|\b(no\s+pasa|no\s+pasaria|no\s+tiene)\s+(la\s+)?itv\b"),
    ("sin papeles", r"\bsin\s+(papeles|documentacion|permiso de circulacion)\b"),
    ("embargo", r"\bembarg\w*\b|\bprecintad\w*\b"),
    ("reserva de dominio", r"\breserva\s+de\s+dominio\b"),
    ("baja temporal", r"\bbaja\s+(temporal|definitiva)\b|\bdad[oa]\s+de\s+baja\b"),
    ("importacion pendiente", r"\bimportacion\s+(pendiente|sin\s+terminar|a\s+medias)\b|\bsin\s+matricular\b|\bmatricula\s+extranjera\b"),
]
# Patrones que contienen su propia negación: no se anulan por una negación anterior
CON_NEGACION_PROPIA = {"no arranca", "sin itv / itv desfavorable", "sin papeles"}

REVISAR = [
    ("detalles", r"\b(tiene\s+|con\s+)?(algun|algunos|pequenos|unos)?\s*detalles?\b(?!\s+(del|de la|tecnicos|del vehiculo))"),
    ("arañazos", r"\b(algun|algunos|pequenos|unos)\s+(aranazo|aranazos|rayon|rayones|roce|roces|bollo|bollos|toque|toques)\b"),
    ("se vende así", r"\bse\s+vende\s+(asi|tal\s+cual|como\s+esta)\b|\btal\s+cual\b"),
]

NEG = r"(nunca|jamas|sin|no|ningun|ninguna|ninguno|cero|libre\s+de|exento\s+de|nada\s+de|ni)"
# Contexto que no describe un defecto del coche: "garantía contra averías", "seguro de averías", "cubre averías"
BENIGNO = r"(garantia\w*|seguro\w*|cobertura\w*|cubre|cubiert\w*|asistencia|prevenir|evitar|contra|plan|pack|servicio|caso|sustitucion)"


def normalize(text: str) -> str:
    t = strip_accents((text or "").lower())
    t = re.sub(r"[^\w\s\.\n]", " ", t)
    return re.sub(r"[ \t]+", " ", t)


def _prev_words(t: str, start: int, window: int) -> str:
    prev = re.split(r"[\.\n]", t[max(0, start - 100):start])[-1]
    return " ".join(prev.split()[-window:])


def _negated(t: str, start: int, window: int = 5) -> bool:
    """¿Hay una negación (o un contexto de garantía/seguro) en las palabras anteriores, sin cruzar un punto?"""
    pw = _prev_words(t, start, window)
    return bool(re.search(rf"\b{NEG}\b", pw) or re.search(rf"\b{BENIGNO}\b", _prev_words(t, start, 4)))


@dataclass
class Resultado:
    descartes: list = field(default_factory=list)   # [(categoría, expresión encontrada)]
    revisar: list = field(default_factory=list)


REPARADO = r"(nuev\w*|cambiad\w*|hech\w*|sustituid\w*|reparad\w*|recien|arreglad\w*|revisad\w*|solucionad\w*)"
PIEZA_DE = r"\b(del|de la|de|protector|cubre\w*|soporte|tapa|bajos)\s*$"   # "protector del motor roto": no es el motor


CARROCERIA = r"\b(parachoques|paragolpes|faro\w*|piloto\w*|retrovisor\w*|aleta|puerta|capo|maletero|luna|cristal|llanta\w*|pintura|chapa|tapiceria|asiento\w*|moldura\w*)\b"


def _benign_after(t: str, end: int, words: int = 2) -> bool:
    """¿Alguna de las `words` palabras siguientes indica reparación ya hecha ('nueva', 'reparada')?"""
    nxt = re.split(r"[\.\n]", t[end:end + 80])[0].split()[:words + 1]
    return any(re.fullmatch(REPARADO, w) for w in nxt)


def analizar(titulo: str, descripcion: str, check_itv: bool = True) -> Resultado:
    t = normalize(f"{titulo}\n{descripcion}")
    res = Resultado()
    for cat, pat in DESCARTE:
        for m in re.finditer(pat, t):
            if cat not in CON_NEGACION_PROPIA and _negated(t, m.start()):
                continue
            if cat in ("junta de culata", "embrague", "caja de cambios", "fallo inyeccion/turbo/egr/fap", "motor tocado/gripado",
                       "averia") and _benign_after(t, m.end(), 6 if cat == "averia" else 2):
                continue   # "junta de culata nueva", "embrague cambiado": reparación hecha, no avería
            if cat == "motor tocado/gripado" and re.search(PIEZA_DE, t[max(0, m.start() - 25):m.start()]):
                continue
            if cat == "a reparar" and re.search(CARROCERIA, _prev_words(t, m.start(), 4)):
                res.revisar.append(("carrocería a reparar", m.group(0).strip()))
                continue   # "parachoques para reparar": chapa, no avería mecánica
            res.descartes.append((cat, m.group(0).strip()))
            break
    for cat, pat in REVISAR:
        m = re.search(pat, t)
        if m and not _negated(t, m.start()):
            res.revisar.append((cat, m.group(0).strip()))
    if check_itv and not re.search(r"\bitv\b|\binspeccion tecnica\b", t):
        res.revisar.append(("no menciona la ITV", ""))
    return res
