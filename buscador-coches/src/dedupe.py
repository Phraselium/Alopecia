"""Deduplicación del mismo coche publicado en varias plataformas (o repetido en la misma)."""
from __future__ import annotations

from rapidfuzz import fuzz

from .models import Listing
from .normalize import norm_text


def _completeness(l: Listing) -> int:
    return sum(v is not None and v != "" for v in (
        l.version, l.cilindrada_cc, l.potencia_cv, l.cambio, l.vendedor, l.fecha_publicacion,
        l.itv_vigor, l.libro_mantenimiento, l.correa_cambiada, l.num_propietarios)) + min(l.num_fotos or 0, 20) // 4 \
        + min(len(l.descripcion or ""), 1500) // 300


def is_duplicate(a: Listing, b: Listing, cfg: dict) -> bool:
    d = cfg["limpieza"]["dedupe"]
    if not (a.modelo_key and a.modelo_key == b.modelo_key and a.anio == b.anio):
        return False
    if not (a.km and b.km and a.precio and b.precio):
        return False
    if abs(a.km - b.km) > d["km_tolerancia"] * max(a.km, b.km):
        return False
    if abs(a.precio - b.precio) > d["precio_tolerancia"] * max(a.precio, b.precio):
        return False
    ta, tb = norm_text(a.descripcion), norm_text(b.descripcion)
    if not ta or not tb:
        # sin texto en alguno: basta con que coincidan exactamente km o el combustible/motor
        return a.km == b.km or (a.motor_key is not None and a.motor_key == b.motor_key)
    return fuzz.token_set_ratio(ta, tb) >= d["similitud_texto_min"]


def dedupe(listings: list[Listing], cfg: dict) -> list[Listing]:
    """Agrupa duplicados; conserva el anuncio más completo y guarda los uid del resto en .duplicados."""
    groups: list[list[Listing]] = []
    for l in listings:
        for g in groups:
            if any(is_duplicate(l, x, cfg) for x in g):
                g.append(l)
                break
        else:
            groups.append([l])
    out = []
    for g in groups:
        g.sort(key=lambda x: (_completeness(x), -(x.precio or 0)), reverse=True)
        keep = g[0]
        keep.duplicados = [f"{x.uid} ({x.url})" for x in g[1:]]
        out.append(keep)
    return out
