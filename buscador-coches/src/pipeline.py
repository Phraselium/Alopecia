"""Enriquecimiento, limpieza, coste y scoring de los anuncios."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from .costs import coste_total
from .dedupe import dedupe
from .extract import extract_pro_signals, extract_signals
from .fraud import fraud_reasons, search_filter_reasons
from .models import Listing
from .normalize import (body_from_text, norm_text, norm_brand, norm_engine, norm_fuel, norm_gearbox, norm_model, norm_seller,
                        potencia_cv)
from .geo import distance_from
from .scoring import Params, etiqueta, market_medians, medians, score_all

# Modelos en los que 'cross/stepway' indica una versión SUV real (en el resto puede ser parte del nombre)
SUV_SENSIBLE = {"Dacia Sandero", "Citroën C3", "Volkswagen Polo", "Toyota Yaris", "Kia Ceed", "Fiat Panda", "Suzuki Swift"}

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
    body = body_from_text(f"{l.titulo} {l.version or ''}")
    if body and not (body == "suv" and seg in ("utilitario", "compacto") and l.modelo_key not in SUV_SENSIBLE):
        l.carroceria = body
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
    embudo: dict | None = None


def _categoria(motivo: str) -> str:
    """Agrupa los motivos de descarte en categorías estables para el embudo."""
    m = motivo
    if "por debajo de la mediana" in m:
        return "fraude: precio anómalo (> 35 % bajo la mediana)"
    for pref, cat in (("precio ", "precio fuera de rango"), ("sin precio", "sin precio"), ("año ", "año < mínimo"),
                      ("km ", "km > máximo"), ("a ", "distancia > radio"), ("combustible desconocido", "combustible desconocido"),
                      ("combustible ", "combustible excluido"), ("diésel con etiqueta", "diésel sin etiqueta B"),
                      ("diésel sin fuente", "diésel sin fuente (modo excluir)")):
        if m.startswith(pref):
            return cat
    if m.startswith("km no creíbles"):
        return "km no creíbles (error del anuncio)"
    if m.startswith("carrocería"):
        return "carrocería " + m.split(" ", 1)[1]
    if m.startswith("texto:"):
        return "fraude: texto sospechoso"
    if "por debajo de la mediana" in m:
        return "fraude: precio anómalo"
    return m


def embudo(listings, descartados, deduplicados, filas) -> dict:
    plats = sorted({l.plataforma for l in listings})
    def row(name, items):
        c = {p: 0 for p in plats}
        for l in items:
            c[l.plataforma] += 1
        c["total"] = sum(c.values())
        return (name, c)
    rows = [row("recogidos (fichas guardadas)", listings)]
    filt = [(l, [x[len("filtro: "):] for x in m if x.startswith("filtro: ")]) for l, m in descartados]
    frau = [(l, [x[len("fraude/problema: "):] for x in m if x.startswith("fraude/problema: ")]) for l, m in descartados]
    cats: dict[str, list] = {}
    excl: dict[str, list] = {}
    for l, ms in filt + frau:
        cs = sorted({_categoria(m) for m in ms})
        for c in cs:
            cats.setdefault(c, []).append(l)
        if len(cs) == 1:
            excl.setdefault(cs[0], []).append(l)
    detalle = []
    for c in sorted(cats, key=lambda k: -len(cats[k])):
        n, ex = row(c, cats[c]), row(c, excl.get(c, []))
        detalle.append((c, n[1], ex[1]))
    pasan_filtros = [l for l in listings if l.uid not in {x.uid for x, m in filt if m}]
    rows.append(row("pasan los filtros", pasan_filtros))
    rows.append(row("fusionados como duplicados", deduplicados))
    rows.append(row("limpios (sin fraude)", [f["listing"] for f in filas]))
    rows.append(row("dentro de presupuesto", [f["listing"] for f in filas if f.get("estado") == "sí"]))
    rows.append(row("caben negociando", [f["listing"] for f in filas if f.get("estado") == "negociar"]))
    rows.append(row("fuera de presupuesto (> margen)", [f["listing"] for f in filas if f.get("estado") == "no"]))
    return {"plataformas": plats, "etapas": rows, "motivos": detalle}


def process(listings: list[Listing], p: Params, motores_fiables: set[str], market: Optional[list] = None) -> Result:
    global CENTER
    CENTER = (p.cfg["ubicacion"]["lat"], p.cfg["ubicacion"]["lon"])
    p.cfg["_anio_actual"] = p.anio_actual
    descartados = []
    candidatos = []
    for l in listings:
        enrich(l)
        l.etiqueta_dgt = etiqueta(l, p.fiscal)
        r = search_filter_reasons(l, p.cfg, p.rel)
        if r:
            descartados.append((l, ["filtro: " + x for x in r]))
        else:
            candidatos.append(l)
    antes = list(candidatos)
    candidatos = dedupe(candidatos, p.cfg)
    keep = {l.uid for l in candidatos}
    deduplicados = [l for l in antes if l.uid not in keep]
    meds = medians(candidatos, p.cfg)
    mkt = market_medians(candidatos, market or [], p.cfg)
    limpios = []
    for l in candidatos:
        med = meds[l.uid][0]
        # Para el filtro de fraude solo vale una mediana del mismo tramo de años con muestras suficientes
        if meds[l.uid][2] < p.cfg["segmentos"]["min_muestras"] or meds[l.uid][1] == "modelo":
            med = None
        if mkt[l.uid][0] is not None:   # preferente: mediana de mercado (sin el sesgo de solo mirar baratos)
            med = mkt[l.uid][0]
        r = fraud_reasons(l, med, p.cfg)
        if r:
            descartados.append((l, ["fraude/problema: " + x for x in r]))
        else:
            limpios.append(l)
    costes = {l.uid: coste_total(l, p.fiscal, p.anio_actual) for l in limpios}
    filas = score_all(limpios, p, costes, mkt)
    avisos = {}
    for f in filas:
        a = list(f["coste"]["avisos"])
        if f.get("estado") == "negociar":
            a.insert(0, f"por encima del presupuesto ({f['coste']['total']:.0f} €), negociar")
        if f["fiabilidad"].get("diesel_pendiente"):
            a.append("diésel: motor sin fuente de fiabilidad (fiabilidad limitada a neutra)")
        if f.get("penalizacion"):
            a.append(f"carrocería {f['listing'].carroceria}: -{f['penalizacion']:.0f} puntos")
        if f["listing"].distancia_km is None:
            a.append("distancia no verificable (el anuncio solo indica la provincia): confirmar que está a <= "
                     f"{p.cfg['ubicacion']['radio_km']} km")
        if f["fiabilidad"]["pendiente"]:
            a.append("fiabilidad del modelo PENDIENTE de fuente (puntuación neutra)")
        if f["n_mediana"] < p.cfg["segmentos"]["min_muestras"] and not str(f["nivel_mediana"]).startswith("mercado"):
            a.append(f"mediana con solo {f['n_mediana']} anuncio(s)")
        avisos[f["listing"].uid] = "; ".join(a)
    log.info("Anuncios: %d entrada, %d limpios, %d descartados", len(listings), len(limpios), len(descartados))
    return Result(limpios, descartados, filas, avisos, embudo(listings, descartados, deduplicados, filas))
