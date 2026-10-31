"""Filtros de fraude / problemas y filtros de búsqueda."""
from __future__ import annotations

from .models import Listing
from .normalize import norm_text, strip_accents


def keyword_flags(l: Listing, palabras: list[str]) -> list[str]:
    t = norm_text(f"{l.titulo} {l.descripcion}")
    hits = []
    for p in palabras:
        pn = strip_accents(p.lower())
        if pn in t:
            # "sin itv" no debe saltar por "sin itv pendiente" negada tipo "no está sin itv": se acepta el falso positivo.
            hits.append(f"texto:'{p}'")
    return hits


def search_filter_reasons(l: Listing, cfg: dict, motores_fiables: set[str]) -> list[str]:
    """Motivos por los que el anuncio no cumple los filtros de búsqueda del config."""
    f, p = cfg["filtros"], cfg["presupuesto"]
    r = []
    if l.precio is None:
        r.append("sin precio")
    elif l.precio > p["precio_anuncio_max_eur"]:
        r.append(f"precio {l.precio:.0f} > {p['precio_anuncio_max_eur']}")
    elif l.precio < p.get("precio_anuncio_min_eur", 0):
        r.append(f"precio {l.precio:.0f} < mínimo {p['precio_anuncio_min_eur']}")
    if l.anio is None or l.anio < f["anio_min"]:
        r.append(f"año {l.anio}")
    if l.km is None or l.km > f["km_max"]:
        r.append(f"km {l.km}")
    radio = cfg["ubicacion"]["radio_km"]
    if l.distancia_km is not None and l.distancia_km > radio:
        r.append(f"a {l.distancia_km:.0f} km (> {radio} km)")
    if l.carroceria not in f["carrocerias"]:
        r.append(f"carrocería {l.carroceria or 'desconocida'}")
    comb = l.combustible
    if comb == "diesel":
        d = f["diesel"]
        if not d["permitido"]:
            r.append("diésel no permitido")
        else:
            orden = ["A", "B", "C", "ECO", "CERO"]
            if l.etiqueta_dgt not in orden or orden.index(l.etiqueta_dgt) < orden.index(d["etiqueta_min"]):
                r.append(f"diésel con etiqueta {l.etiqueta_dgt}")
            if d.get("requiere_motor_fiable") and l.motor_key not in motores_fiables:
                r.append(f"diésel con motor no marcado como fiable ({l.motor_key})")
    elif comb not in f["combustibles"]:
        r.append(f"combustible {comb or 'desconocido'}")
    return r


def fraud_reasons(l: Listing, mediana: float | None, cfg: dict) -> list[str]:
    fr = cfg["limpieza"]["fraude"]
    r = keyword_flags(l, fr["palabras"])
    if l.num_fotos is not None and l.num_fotos < fr.get("min_fotos", 1):
        r.append("sin fotos")
    if mediana and l.precio and l.precio < mediana * (1 - fr["descuento_max_vs_mediana"]):
        r.append(f"precio {l.precio:.0f} >{fr['descuento_max_vs_mediana']:.0%} por debajo de la mediana {mediana:.0f}")
    return r
