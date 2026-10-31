"""Enriquecimiento, limpieza, coste y scoring de los anuncios."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .costs import coste_total
from .dedupe import dedupe
from .extract import extract_pro_signals, extract_signals
from .fraud import fraud_reasons, search_filter_reasons
from .models import Listing
from .normalize import (norm_text, norm_brand, norm_engine, norm_fuel, norm_gearbox, norm_model, norm_seller,
                        potencia_cv)
from .geo import distance_from
from .scoring import Params, etiqueta, medians, score_all

CENTER = (39.4699, -0.3763)  # se sobrescribe con config en process()

log = logging.getLogger("pipeline")


def enrich(l: Listing) -> Listing:
    """Normaliza campos y extrae señales del texto. Idempotente."""
    txt = f"{l.titulo} {l.version or ''}"
    l.marca = norm_brand(l.marca, l.titulo)
    modelo, seg = norm_model(l.marca, l.modelo, l.titulo)
    l.modelo = modelo
    # El segmento sale de la tabla de modelos; si el modelo no está, se conserva lo que diga la plataforma
    l.carroceria = seg or l.carroceria
    if re.search(r"\b(cc|cabrio\w*|coup[eé]|roadster|descapotable)\b", norm_text(f"{l.titulo} {l.version or ''}")):
        l.carroceria = "cabrio"
    l.modelo_key = f"{l.marca} {l.modelo}" if l.marca and l.modelo else None
    l.motor_key = norm_engine(l.version, l.titulo, f"{l.cilindrada_cc}cc" if l.cilindrada_cc else None)
    l.combustible = norm_fuel(l.combustible, txt, l.descripcion[:500])
    l.cambio = norm_gearbox(l.cambio, txt)
    l.vendedor = norm_seller(l.vendedor) or l.vendedor
    l.potencia_cv = l.potencia_cv or potencia_cv(txt)
    if l.lat is not None and l.lon is not None and l.distancia_km is None:
        l.distancia_km = distance_from(CENTER, lat=l.lat, lon=l.lon)
    for k, v in extract_signals(l.titulo, l.descripcion).items():
        if getattr(l, k) is None:
            setattr(l, k, v)
    if l.vendedor == "profesional":
        for k, v in extract_pro_signals(f"{l.titulo}\n{l.descripcion}").items():
            if getattr(l, k) is None:
                setattr(l, k, v)
        # Precio real = precio al contado. Si el anunciado es menor, solo vale financiando.
        if l.precio_contado and l.precio and l.precio_contado > l.precio + 1:
            l.precio_financiado = l.precio_financiado or l.precio
            l.solo_financiando = True
            l.precio = float(l.precio_contado)
    return l


@dataclass
class Result:
    limpios: list[Listing]
    descartados: list[tuple[Listing, list[str]]]
    filas: list[dict]
    avisos: dict[str, str]


def process(listings: list[Listing], p: Params, motores_fiables: set[str]) -> Result:
    global CENTER
    CENTER = (p.cfg["ubicacion"]["lat"], p.cfg["ubicacion"]["lon"])
    descartados = []
    candidatos = []
    for l in listings:
        enrich(l)
        l.etiqueta_dgt = etiqueta(l, p.fiscal)
        r = search_filter_reasons(l, p.cfg, motores_fiables)
        if r:
            descartados.append((l, ["filtro: " + x for x in r]))
        else:
            candidatos.append(l)
    candidatos = dedupe(candidatos, p.cfg)
    meds = medians(candidatos, p.cfg)
    limpios = []
    for l in candidatos:
        med = meds[l.uid][0]
        # La mediana de un segmento de 1 anuncio es su propio precio: solo se usa si hay muestras suficientes
        if meds[l.uid][2] < p.cfg["segmentos"]["min_muestras"]:
            med = None
        r = fraud_reasons(l, med, p.cfg)
        if r:
            descartados.append((l, ["fraude/problema: " + x for x in r]))
        else:
            limpios.append(l)
    costes = {l.uid: coste_total(l, p.fiscal, p.anio_actual) for l in limpios}
    filas = score_all(limpios, p, costes)
    avisos = {}
    for f in filas:
        a = list(f["coste"]["avisos"])
        if f["fiabilidad"]["pendiente"]:
            a.append("fiabilidad del modelo PENDIENTE de fuente (puntuación neutra)")
        if f["n_mediana"] < p.cfg["segmentos"]["min_muestras"]:
            a.append(f"mediana con solo {f['n_mediana']} anuncio(s)")
        avisos[f["listing"].uid] = "; ".join(a)
    log.info("Anuncios: %d entrada, %d limpios, %d descartados", len(listings), len(limpios), len(descartados))
    return Result(limpios, descartados, filas, avisos)
