"""Extracción de señales del texto del anuncio (ITV, libro, correa, propietarios, garantía)."""
from __future__ import annotations

import re
from typing import Optional

from .normalize import norm_text

_NEG = r"(sin|no tiene|no lleva|falta|pendiente de|caducad[ao])"

PATTERNS = {
    "itv_vigor": {
        "pos": [r"itv\s*(en vigor|al d[ií]a|recien pasada|reci[eé]n pasada|pasada|hasta|valida|v[aá]lida|nueva)",
                r"itv\s*\d{1,2}[/-]\d{2,4}", r"itv\s*(hasta|para)\s*\d{4}"],
        "neg": [r"sin\s*itv", r"itv\s*caducad", r"itv\s*(desfavorable|negativa)", r"no\s*(tiene|pasa)\s*(la\s*)?itv"],
    },
    "libro_mantenimiento": {
        "pos": [r"libro\s*(de\s*)?(mantenimiento|revisiones|servicio)", r"revisiones\s*(sellad|en\s*(el\s*)?(concesionari|oficial|casa))",
                r"mantenimiento\s*(oficial|en\s*concesionario|al\s*d[ií]a)", r"historial\s*(de\s*)?mantenimiento",
                r"facturas\s*de\s*(mantenimiento|revisiones|taller)"],
        "neg": [r"sin\s*libro", r"no\s*tiene\s*libro"],
    },
    "correa_cambiada": {
        "pos": [r"(correa|kit)\s*(de\s*)?(distribuci[oó]n)?\s*(cambiad|reci[eé]n cambiad|nuev|sustituid|hecha|realizad)",
                r"(cambiad[ao]|hecha|nueva)\s*(la\s*)?(correa|distribuci[oó]n)", r"distribuci[oó]n\s*(cambiad|nuev|hecha)",
                r"(lleva|motor de)\s*cadena", r"cadena\s*de\s*distribuci[oó]n\s*(cambiad|nuev)"],
        "neg": [r"(correa|distribuci[oó]n)\s*(sin\s*cambiar|por\s*cambiar|pendiente)", r"hay\s*que\s*cambiar\s*(la\s*)?correa"],
    },
    "garantia": {
        "pos": [r"garant[ií]a\s*(de\s*)?\d+\s*(mes|año|ano)", r"con\s*garant[ií]a", r"garant[ií]a\s*(incluida|oficial|mecanica|mec[aá]nica)"],
        "neg": [r"sin\s*garant[ií]a"],
    },
    "km_justificados": {
        "pos": [r"km\s*(certificad|justificad|demostrable|reales\s*con)", r"(itv|facturas)\s*que\s*(lo\s*)?(demuestran|acreditan)",
                r"kilometraje\s*(certificad|demostrable|justificad)", r"uso\s*(de\s*)?(fin de semana|ocasional|esporadico|espor[aá]dico)",
                r"(jubilad|persona mayor|abuel)"],
        "neg": [],
    },
}

_NUM_WORDS = {"un": 1, "uno": 1, "unico": 1, "único": 1, "dos": 2, "tres": 3, "cuatro": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def _match(t: str, pats: list[str]) -> bool:
    return any(re.search(p, t) for p in pats)


def tri_state(text: str, key: str) -> Optional[bool]:
    t = norm_text(text)
    p = PATTERNS[key]
    if _match(t, p["neg"]):
        return False
    if _match(t, p["pos"]):
        return True
    return None


def propietarios(text: str) -> Optional[int]:
    t = norm_text(text)
    if re.search(r"(un|1|unico|único)\s*(solo\s*)?(propietari|due[nñ]o)|propietari[oa]\s*[uú]nic|[uú]nico\s*(propietari|due[nñ]o)|de\s*primera\s*mano", t):
        return 1
    m = re.search(r"(\w+)\s+(propietarios|duen[oa]s|due[nñ]os)", t)
    if m and m.group(1) in _NUM_WORDS:
        return _NUM_WORDS[m.group(1)]
    return None


def extract_signals(titulo: str, descripcion: str) -> dict:
    txt = f"{titulo}\n{descripcion}"
    return {
        "itv_vigor": tri_state(txt, "itv_vigor"),
        "libro_mantenimiento": tri_state(txt, "libro_mantenimiento"),
        "correa_cambiada": tri_state(txt, "correa_cambiada"),
        "garantia": tri_state(txt, "garantia"),
        "km_justificados": tri_state(txt, "km_justificados"),
        "num_propietarios": propietarios(txt),
    }


# ---------------------------------------------------------------------------------------------
# Condiciones de compra a profesional (cualquier plataforma): se leen de la descripción del anuncio
# ---------------------------------------------------------------------------------------------
_EUR = r"(\d{1,3}(?:[.\s]\d{3})+|\d{3,6})(?:[.,]\d{2})?\s*(?:€|eur|euros)"


def _eur(s: str) -> float:
    return float(re.sub(r"[.\s]", "", s))


def extract_pro_signals(text: str) -> dict:
    """Devuelve solo las claves que encuentra (para no pisar datos estructurados de la plataforma)."""
    t = norm_text(text)
    out: dict = {}
    m = re.search(r"precio\s*(?:al\s*)?contado\s*(?:actual)?\s*(?:de|:)?\s*" + _EUR, t)
    if m:
        out["precio_contado"] = _eur(m.group(1))
    m = re.search(r"precio\s*(?:financiado|con financiaci[oó]n|financiando)\s*(?:de|:)?\s*" + _EUR, t)
    if m:
        out["precio_financiado"] = _eur(m.group(1))
    if re.search(r"(precio|oferta)[^.]{0,60}(financiando|con financiaci[oó]n|sujet[oa] a financiaci[oó]n|financiaci[oó]n obligatoria)", t):
        out["solo_financiando"] = True
    m = re.search(r"(?:gastos?\s*de\s*)?(?:gesti[oó]n|transferencia|preparaci[oó]n|tramitaci[oó]n)[^.]{0,50}?" + _EUR, t)
    if m and not re.search(r"(incluid[ao]s?|gratis)[^.]{0,20}$", t[max(0, m.start() - 30):m.start()]):
        out["gastos_gestion_eur"] = _eur(m.group(1))
        out["gastos_incluyen_transferencia"] = "transferencia" in m.group(0)
    if re.search(r"(transferencia|gastos de gesti[oó]n)\s*(incluid[ao]s?|gratis|gratuita)|(incluye|incluida)\s*(la\s*)?transferencia", t):
        out.setdefault("gastos_gestion_eur", 0.0)
        out["gastos_incluyen_transferencia"] = True
    m = re.search(r"garant[ií]a\s*(?:de\s*|mec[aá]nica\s*(?:de\s*)?|oficial\s*(?:de\s*)?)?(\d{1,2})\s*(mes|a[nñ]o)", t)
    if m:
        n = int(m.group(1))
        out["garantia_meses"] = n * 12 if m.group(2).startswith("a") else n
        out["garantia"] = True
    if re.search(r"(ampliable|ampliar|extender|extensi[oó]n de)\s*(la\s*)?garant[ií]a|garant[ií]a[^.]{0,30}(ampliable|extendida|premium)", t):
        out["garantia_ampliable"] = True
    m = re.search(r"(\d{2,3})\s*puntos\s*(de\s*(control|revisi[oó]n|inspecci[oó]n))?", t)
    if m and re.search(r"revis|inspecc|control|chequeo|certific", t[max(0, m.start() - 40):m.end() + 30]):
        out["revision_puntos"] = int(m.group(1))
    if re.search(r"(km|kilometraje|kil[oó]metros)\s*(reales\s*)?(certificad|garantizad)|certificad[oa]\s*(de\s*)?(km|kilometraje|kil[oó]metros)", t):
        out["km_certificados"] = True
    m = re.search(r"(\d{1,2})\s*d[ií]as\s*(de\s*)?(devoluci[oó]n|prueba|para devolver|o\s*1\.?000\s*km)", t) or \
        re.search(r"devoluci[oó]n\s*(?:en|de|durante)?\s*(\d{1,2})\s*d[ií]as", t)
    if m:
        out["devolucion_dias"] = int(m.group(1))
    return out
