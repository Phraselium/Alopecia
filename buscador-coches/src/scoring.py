"""Scoring 0-100. Réplica exacta en Python de las fórmulas que escribe src/excel.py.

El Excel es la fuente de verdad visible (fórmulas); esta réplica sirve para el informe.md
y para verificar el Excel recalculado (tests/test_excel_formulas.py).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from .models import Listing


def clamp(x: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, x))


@dataclass
class Params:
    cfg: dict
    fiscal: dict
    rel: dict

    @property
    def anio_actual(self) -> int:
        return self.fiscal["anio_actual"]

    @property
    def neutro(self) -> float:
        return self.cfg["scoring"]["coste_uso"]["neutro_si_pendiente"]


# ---------- etiqueta DGT ----------
def etiqueta(l: Listing, fiscal: dict) -> Optional[str]:
    e = fiscal["etiqueta_dgt"]
    c, a = l.combustible, l.anio
    if c in ("hibrido", "glp"):
        return "ECO"
    if c == "electrico":
        return "CERO"
    if a is None:
        return None
    if c == "gasolina":
        return "C" if a >= e["gasolina_C_desde"] else "B" if a >= e["gasolina_B_desde"] else "A"
    if c == "diesel":
        return "C" if a >= e["diesel_C_desde"] else "B" if a >= e["diesel_B_desde"] else "A"
    return None


# ---------- segmentos y medianas ----------
def seg_keys(l: Listing, cfg: dict) -> tuple[str, str, str]:
    s = cfg["segmentos"]
    k1 = l.modelo_key or ""
    ta = int((l.anio or 0) / s["anio_tramo"]) * s["anio_tramo"]
    tk = int((l.km or 0) / s["km_tramo"]) * s["km_tramo"]
    k2 = f"{k1}|{ta}"
    return k1, k2, f"{k2}|{tk}"


def medians(listings: list[Listing], cfg: dict) -> dict[str, tuple[Optional[float], str, int]]:
    """uid -> (mediana, nivel, n) con la misma jerarquía que la fórmula del Excel."""
    min_n = cfg["segmentos"]["min_muestras"]
    groups: dict[tuple[int, str], list[float]] = {}
    keys = {}
    for l in listings:
        ks = seg_keys(l, cfg)
        keys[l.uid] = ks
        if l.precio is not None:
            for i, k in enumerate(ks):
                groups.setdefault((i, k), []).append(l.precio)
    out = {}
    names = ["modelo", "modelo+año", "modelo+año+km"]
    for l in listings:
        k1, k2, k3 = keys[l.uid]
        for i, k in ((2, k3), (1, k2), (0, k1)):
            vals = groups.get((i, k), [])
            if len(vals) >= min_n or i == 0:
                out[l.uid] = (statistics.median(vals) if vals else None, names[i], len(vals))
                break
    return out


# ---------- fiabilidad ----------
def tuv_score(m: dict, medias: dict) -> Optional[float]:
    if m.get("tuv_mq") is None:
        return None
    avg = m.get("tuv_media_propia") or medias[m["tuv_franja"]]["valor"]
    return clamp(50 + 100 * (avg - m["tuv_mq"]) / avg)


def model_score(modelo_key: str, marca: str, p: Params) -> tuple[float, bool]:
    """(puntuación base, pendiente?)"""
    rel = p.rel
    ocu = (rel.get("marcas_ocu_2026") or {}).get("valores") or {}
    m = (rel.get("modelos") or {}).get(modelo_key)
    if m is not None:
        vals = [v for v in (tuv_score(m, rel["medias_tuv_2026"]), ocu.get(marca)) if v is not None]
        if vals:
            return sum(vals) / len(vals), False
        return p.neutro, True
    if marca in ocu:
        return float(ocu[marca]), False
    return p.neutro, True


def engine_adjust(l: Listing, rel: dict) -> tuple[float, list[dict]]:
    total, hits = 0.0, []
    for e in rel.get("motores") or []:
        if e["motor"] == l.motor_key and e["marca"] in ("(todas)", l.marca) and \
                l.anio is not None and e["anio_desde"] <= l.anio <= e["anio_hasta"]:
            total += e["ajuste"]
            hits.append(e)
    for c in rel.get("combustibles") or []:
        if c["combustible"] == l.combustible:
            total += c["ajuste"]
            hits.append(c)
    return total, hits


# ---------- subpuntuaciones ----------
def s_fiabilidad(l: Listing, p: Params) -> dict:
    base, pend = model_score(l.modelo_key or "", l.marca or "", p)
    adj, hits = engine_adjust(l, p.rel)
    return {"base": base, "pendiente": pend, "ajuste": adj, "problemas": hits, "score": clamp(base + adj)}


def s_precio(l: Listing, mediana: Optional[float], cfg: dict) -> dict:
    if not mediana or l.precio is None:
        return {"descuento": None, "score": 50.0}
    d = (mediana - l.precio) / mediana
    return {"descuento": d, "score": clamp(50 + d * cfg["scoring"]["precio"]["pendiente"])}


def s_km_edad(l: Listing, p: Params) -> dict:
    k = p.cfg["scoring"]["km_edad"]
    f = p.cfg["filtros"]
    edad = max(p.anio_actual - (l.anio or p.anio_actual), 0)
    kma = (l.km or 0) / max(edad, 0.5)
    s_tot = max(0.0, 100 * (1 - (l.km or 0) / f["km_max"]))
    if kma < k["km_anio_sospechoso"]:
        s_kma = 100.0 if l.km_justificados else float(k["penaliza_sospechoso"])
    elif kma <= k["km_anio_ideal_max"]:
        s_kma = 100.0
    else:
        s_kma = max(0.0, 100 * (k["km_anio_cero"] - kma) / (k["km_anio_cero"] - k["km_anio_ideal_max"]))
    s_edad = clamp(100 * ((l.anio or f["anio_min"]) - f["anio_min"]) / (p.anio_actual - f["anio_min"]))
    score = k["peso_km_total"] * s_tot + k["peso_km_anio"] * s_kma + k["peso_edad"] * s_edad
    return {"edad": edad, "km_anio": kma, "s_km_total": s_tot, "s_km_anio": s_kma, "s_edad": s_edad, "score": score}


def s_anuncio(l: Listing, cfg: dict) -> dict:
    a = cfg["scoring"]["anuncio"]
    score = (a["itv"] * (l.itv_vigor is True) + a["libro"] * (l.libro_mantenimiento is True)
             + a["correa"] * (l.correa_cambiada is True) + a["propietario_unico"] * (l.num_propietarios == 1)
             + a["garantia"] * (l.garantia is True) + a["fotos"] * min(1, (l.num_fotos or 0) / a["fotos_objetivo"]))
    return {"score": float(score)}


def s_coste_uso(l: Listing, p: Params) -> dict:
    c = p.cfg["scoring"]["coste_uso"]
    et = etiqueta(l, p.fiscal)
    s_et = float(c["puntos_etiqueta"].get(et, p.neutro)) if et else p.neutro
    s_cons = p.neutro   # consumo: PENDIENTE de fuente
    s_seg = p.neutro    # seguro: PENDIENTE de fuente
    score = c["peso_etiqueta"] * s_et + c["peso_consumo"] * s_cons + c["peso_seguro"] * s_seg
    return {"etiqueta": et, "s_etiqueta": s_et, "score": score}


def score_all(listings: list[Listing], p: Params, costes: dict[str, dict]) -> list[dict]:
    meds = medians(listings, p.cfg)
    w = p.cfg["scoring"]["pesos"]
    rows = []
    for l in listings:
        med, nivel, n = meds[l.uid]
        f = s_fiabilidad(l, p)
        pr = s_precio(l, med, p.cfg)
        ke = s_km_edad(l, p)
        an = s_anuncio(l, p.cfg)
        us = s_coste_uso(l, p)
        total = (w["fiabilidad"] * f["score"] + w["precio"] * pr["score"] + w["km_edad"] * ke["score"]
                 + w["anuncio"] * an["score"] + w["coste_uso"] * us["score"])
        c = costes[l.uid]
        rows.append({"listing": l, "mediana": med, "nivel_mediana": nivel, "n_mediana": n,
                     "fiabilidad": f, "precio": pr, "km_edad": ke, "anuncio": an, "coste_uso": us,
                     "total": total, "coste": c,
                     "apto": c["total"] <= p.cfg["presupuesto"]["total_max_eur"]})
    aptos = sorted((r for r in rows if r["apto"]), key=lambda r: -r["total"])
    # mismo desempate que la fórmula del Excel: orden de fila
    order = {id(r): i for i, r in enumerate(rows)}
    aptos.sort(key=lambda r: (-round(r["total"], 9), order[id(r)]))
    for i, r in enumerate(aptos, 1):
        r["rank"] = i
    return rows
