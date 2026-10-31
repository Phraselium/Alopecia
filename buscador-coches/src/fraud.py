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


def segmentos_admitidos(cfg: dict) -> set[str]:
    f = cfg["filtros"]
    return set(f["carrocerias"]) | set(f.get("carrocerias_penalizadas") or [])


def motor_documentado(l: Listing, rel: dict) -> bool:
    """¿Hay una entrada en reliability.yaml → motores para este motor (marca o '(todas)') y año?"""
    from .scoring import engine_match
    return any(engine_match(e, l) for e in rel.get("motores") or [])


def search_filter_reasons(l: Listing, cfg: dict, rel: dict | None = None) -> list[str]:
    """Motivos de EXCLUSIÓN (filtros duros). Lo que solo penaliza se trata en scoring."""
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
    elif l.anio and l.km < f.get("km_min_creible", 1000) and (cfg.get("_anio_actual", 2026) - l.anio) > 2:
        r.append(f"km no creíbles ({l.km} km en un coche de {l.anio}): probable error del anuncio")
    radio = cfg["ubicacion"]["radio_km"]
    if l.distancia_km is not None and l.distancia_km > radio:
        r.append(f"a {l.distancia_km:.0f} km (> {radio} km)")
    if l.carroceria not in segmentos_admitidos(cfg):
        r.append(f"carrocería {l.carroceria or 'desconocida'}")
    comb = l.combustible
    if comb is None:
        r.append("combustible desconocido")
    elif comb in f.get("combustibles_excluidos", []):
        r.append(f"combustible {comb}")
    elif comb == "diesel":
        d = f["diesel"]
        if d.get("excluir_si_penalizacion_motor", True):
            from .scoring import engine_match
            pen = [e for e in (rel or {}).get("motores") or [] if engine_match(e, l) and e["ajuste"] < 0]
            if pen:
                r.append(f"diésel con penalización de motor conocida ({l.motor_key}: {pen[0]['ajuste']})")
        if d.get("sin_fuente") == "excluir" and not motor_documentado(l, rel or {}):
            r.append(f"diésel sin fuente de fiabilidad del motor ({l.motor_key})")
    # Distintivo ambiental. La etiqueta final es la PEOR de las posibles (etiqueta.asignar):
    #   dudosa o deducida por regla -> solo descarta si alguna opción queda por debajo de la mínima.
    from .etiqueta import rank
    minima = f.get("etiqueta_minima", "B")
    modo_dud = f.get("etiqueta_dudosa", "si_todas_cumplen")      # no | si_todas_cumplen
    modo_regla = f.get("etiqueta_regla", "si_todas_cumplen")     # no | si_todas_cumplen
    if l.etiqueta_dgt is None:
        r.append("etiqueta desconocida")
    elif rank(l.etiqueta_dgt) < rank(minima):
        tipo = "dudosa" if l.etiqueta_dudosa else ("regla" if l.etiqueta_fuente == "regla" else l.etiqueta_fuente)
        r.append(f"etiqueta {l.etiqueta_dgt} < {minima} ({tipo}; opciones {l.etiqueta_opciones or l.etiqueta_dgt})")
    else:
        if l.etiqueta_dudosa and modo_dud == "no":
            r.append(f"etiqueta dudosa ({l.etiqueta_opciones}, {l.etiqueta_fuente})")
        elif l.etiqueta_fuente == "regla" and modo_regla == "no":
            r.append(f"etiqueta no confirmada (deducida por regla)")
    # Modelos y cajas excluidos
    if l.modelo_key in (f.get("modelos_excluidos") or []):
        r.append(f"modelo excluido ({l.modelo_key})")
    if f.get("excluir_multitronic", True) and l.multitronic == "sí":
        r.append("caja Multitronic (Audi CVT) excluida")
    if f.get("excluir_cajas_robotizadas", True) and l.caja_robotizada:
        r.append(f"caja robotizada ({l.caja_robotizada}) excluida")
    # Vendedor: particulares solo para los modelos de estetica.yaml con puntos >= particulares.min_estetica
    if f.get("solo_profesionales") and l.vendedor != "profesional":
        pa = f.get("particulares") or {}
        if not (pa.get("admitir_modelos_estetica", True) and l.vendedor == "particular"
                and (l.estetica_modelo or 0) >= pa.get("min_estetica", 4) and l.estetica_ref):
            r.append(f"vendedor {l.vendedor or 'desconocido'} (solo profesionales"
                     + (", salvo modelos prioritarios de estetica.yaml)" if pa.get("admitir_modelos_estetica", True) else ")"))
    # Color excluido (negro, marrón oscuro por defecto)
    col = f.get("color") or {}
    if col.get("excluir_activo", True) and l.color in (col.get("excluidos") or []):
        r.append(f"color {l.color} excluido")
    # Averías y estado (filtro estricto con negaciones)
    av = f.get("averias") or {}
    if av.get("activo", True):
        from .averias import analizar
        res = analizar(l.titulo or "", l.descripcion or "", av.get("revisar_si_no_menciona_itv", True))
        for cat, expr in res.descartes:
            r.append(f"avería/estado: {cat} «{expr}»")
        l.revisar = [f"{c}" + (f" «{e}»" if e else "") for c, e in res.revisar]
    return r


def fraud_reasons(l: Listing, mediana: float | None, cfg: dict) -> list[str]:
    fr = cfg["limpieza"]["fraude"]
    r = keyword_flags(l, fr["palabras"])
    if l.num_fotos is not None and l.num_fotos < fr.get("min_fotos", 1):
        r.append("sin fotos")
    if mediana and l.precio and l.precio < mediana * (1 - fr["descuento_max_vs_mediana"]):
        r.append(f"precio {l.precio:.0f} >{fr['descuento_max_vs_mediana']:.0%} por debajo de la mediana {mediana:.0f}")
    return r
