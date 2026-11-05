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
    zbe: Optional[dict] = None
    estetica: Optional[dict] = None

    def __post_init__(self):
        import yaml
        from pathlib import Path
        base = Path(__file__).resolve().parents[1]
        if self.zbe is None:
            self.zbe = yaml.safe_load((base / "zbe.yaml").read_text(encoding="utf-8"))
        if self.estetica is None:
            self.estetica = yaml.safe_load((base / "estetica.yaml").read_text(encoding="utf-8"))

    @property
    def anio_actual(self) -> int:
        return self.fiscal["anio_actual"]

    @property
    def neutro(self) -> float:
        return self.cfg["scoring"]["coste_uso"]["neutro_si_pendiente"]


# ---------- etiqueta DGT ----------
def etiqueta(l: Listing, fiscal: dict = None) -> Optional[str]:
    """Etiqueta final ya asignada por src/etiqueta.asignar (DGT > anuncio > regla)."""
    return l.etiqueta_dgt


def s_etiqueta(l: Listing, p: Params) -> dict:
    """'Etiqueta y ZBE': B base, C +, ECO/CERO ++; penalización si es dudosa o solo de la regla."""
    e = p.cfg["scoring"]["etiqueta"]
    base = float(e["puntos"].get(l.etiqueta_dgt, 0)) if l.etiqueta_dgt else 0.0
    pen = e["penal_dudosa"] if l.etiqueta_dudosa else (e["penal_regla"] if l.etiqueta_fuente == "regla" else 0)
    return {"etiqueta": l.etiqueta_dgt, "fuente": l.etiqueta_fuente, "dudosa": bool(l.etiqueta_dudosa),
            "base": base, "penal": pen, "score": clamp(base - pen)}


# ---------- segmentos y medianas ----------
def seg_keys(l: Listing, cfg: dict) -> tuple[str, str, str]:
    s = cfg["segmentos"]
    k1 = l.modelo_key or ""
    ta = int((l.anio or 0) / s["anio_tramo"]) * s["anio_tramo"]
    tk = int((l.km or 0) / s["km_tramo"]) * s["km_tramo"]
    k2 = f"{k1}|{ta}"
    return k1, k2, f"{k2}|{tk}"


def market_medians(listings: list[Listing], market: list[dict], cfg: dict) -> dict[str, tuple[Optional[float], str, int]]:
    """Mediana de mercado por segmento con TODOS los anuncios vistos en los listados (incluidos los de
    precio > máximo). Misma jerarquía de segmentos; si ni a nivel modelo hay MIN_N, devuelve (None, '', n)."""
    from .normalize import norm_brand, norm_model
    min_n = cfg["segmentos"]["min_muestras"]
    groups: dict[tuple[int, str], list[float]] = {}
    for m in market:
        marca = norm_brand(m.get("marca"), m.get("titulo") or "")
        modelo, _ = norm_model(marca, m.get("modelo"), m.get("titulo") or "")
        if not (marca and modelo):
            continue
        fake = Listing(plataforma="", id_externo="", url="", titulo="", anio=m["anio"], km=m.get("km") or 0)
        fake.modelo_key = f"{marca} {modelo}"
        for i, k in enumerate(seg_keys(fake, cfg)):
            groups.setdefault((i, k), []).append(m["precio"])
    names = ["modelo", "modelo+año", "modelo+año+km"]
    out = {}
    for l in listings:
        ks = seg_keys(l, cfg)
        res = (None, "", 0)
        for i in (2, 1):   # nunca a nivel "todo el modelo": mezclaría coches de 2008 con los de 2024
            vals = groups.get((i, ks[i]), [])
            if len(vals) >= min_n:
                res = (statistics.median(vals), names[i], len(vals))
                break
        out[l.uid] = res
    return out


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


def adac_score(m: dict, rel: dict) -> Optional[float]:
    tbl = (rel.get("adac_2025") or {}).get("pkz_2015") or {}
    pkz = tbl.get(m.get("adac")) if m.get("adac") else None
    if pkz is None:
        return None
    ref = statistics.median(tbl.values())
    return clamp(50 + 100 * (ref - pkz) / ref)


def model_score(modelo_key: str, marca: str, p: Params) -> tuple[float, bool]:
    """(puntuación base, pendiente?). Si el modelo no tiene dato y su gemelo de plataforma sí, hereda el del gemelo."""
    base, pend, _ = model_score_ex(modelo_key, marca, p)
    return base, pend


def model_score_ex(modelo_key: str, marca: str, p: Params) -> tuple[float, bool, Optional[str]]:
    rel = p.rel
    m = (rel.get("modelos") or {}).get(modelo_key)
    own, pend = _own_model_score(modelo_key, marca, p)
    if pend and m and m.get("gemelo"):
        g = m["gemelo"]
        gs, gpend = _own_model_score(g, g.split(" ")[0], p)
        if not gpend:
            return gs, False, g
    return own, pend, None


def _own_model_score(modelo_key: str, marca: str, p: Params) -> tuple[float, bool]:
    rel = p.rel
    ocu = (rel.get("marcas_ocu_2026") or {}).get("valores") or {}
    m = (rel.get("modelos") or {}).get(modelo_key)
    if m is not None:
        vals = [v for v in (tuv_score(m, rel["medias_tuv_2026"]), adac_score(m, rel), ocu.get(marca)) if v is not None]
        if vals:
            return sum(vals) / len(vals), False
        return p.neutro, True
    if marca in ocu:
        return float(ocu[marca]), False
    return p.neutro, True


def engine_match(e: dict, l: Listing) -> bool:
    """Motor y marca ('(todas)' = cualquier marca; motor '(cualquiera)' = cualquier motor de esa marca) y año."""
    return ((e["motor"] == l.motor_key and e["marca"] in ("(todas)", l.marca)) or
            (e["motor"] == "(cualquiera)" and e["marca"] == l.marca)) and \
        l.anio is not None and e["anio_desde"] <= l.anio <= e["anio_hasta"]


def engine_adjust(l: Listing, rel: dict) -> tuple[float, list[dict]]:
    total, hits = 0.0, []
    for e in rel.get("motores") or []:
        if engine_match(e, l):
            total += e["ajuste"]
            hits.append(e)
    for c in rel.get("combustibles") or []:
        if c["combustible"] == l.combustible:
            total += c["ajuste"]
            hits.append(c)
    return total, hits


# ---------- subpuntuaciones ----------
def motor_doc(l: Listing, rel: dict) -> bool:
    return any(engine_match(e, l) for e in rel.get("motores") or [])


def s_fiabilidad(l: Listing, p: Params) -> dict:
    base, pend, gemelo = model_score_ex(l.modelo_key or "", l.marca or "", p)
    diesel_pend = l.combustible == "diesel" and not motor_doc(l, p.rel)
    base_ef = min(base, p.neutro) if diesel_pend else base
    adj, hits = engine_adjust(l, p.rel)
    rob = float((p.cfg["scoring"].get("penalizaciones") or {}).get("caja_robotizada", 0)) if l.caja_robotizada else 0.0
    return {"base": base, "base_ef": base_ef, "pendiente": pend, "diesel_pendiente": diesel_pend, "gemelo": gemelo,
            "ajuste": adj, "robotizada": rob, "problemas": hits, "score": clamp(base_ef + adj - rob)}


def penal_carroceria(l: Listing, cfg: dict) -> float:
    return float((cfg["scoring"].get("penalizaciones") or {}).get("carroceria", {}).get(l.carroceria, 0))


def estado_presupuesto(total: float, cfg: dict) -> str:
    """sí (<= objetivo) · negociar (objetivo < coste <= techo) · no (> techo: excluido)."""
    pr = cfg["presupuesto"]
    if total <= pr["total_max_eur"]:
        return "sí"
    if total <= pr.get("techo_eur", pr["total_max_eur"] + pr.get("margen_negociacion_eur", 0)):
        return "negociar"
    return "no"


def penal_presupuesto(total: float, cfg: dict) -> float:
    """Puntos que se restan a la puntuación: penal_por_100_eur por cada 100 € (proporcional) sobre el objetivo."""
    pr = cfg["presupuesto"]
    return max(0.0, total - pr["total_max_eur"]) / 100 * pr.get("penal_por_100_eur", 0)


def km_tope(l: Listing, cfg: dict) -> float:
    pc = cfg["scoring"]["precio"]
    return 100 - max(0, (l.km or 0) - pc.get("km_tope_desde", 10 ** 9)) / 1000 * pc.get("km_tope_puntos_1000", 0)


def s_precio(l: Listing, mediana: Optional[float], cfg: dict) -> dict:
    """50 + descuento·k, con un tope que baja por encima de km_tope_desde (un precio bajo no compensa muchos km)."""
    tope = km_tope(l, cfg)
    if not mediana or l.precio is None:
        return {"descuento": None, "tope": tope, "score": clamp(min(50.0, tope))}
    d = (mediana - l.precio) / mediana
    return {"descuento": d, "tope": tope, "score": clamp(min(50 + d * cfg["scoring"]["precio"]["pendiente"], tope))}


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


def distribucion(l: Listing, rel: dict) -> Optional[str]:
    """'cadena' | 'correa' | None según reliability.yaml -> mantenimiento.distribucion (marca|motor)."""
    tbl = ((rel.get("mantenimiento") or {}).get("distribucion") or {})
    v = tbl.get(f"{l.marca}|{l.motor_key}")
    return v.get("tipo") if isinstance(v, dict) else v


def s_estado(l: Listing, p: Params) -> dict:
    """'Estado y mantenimiento': ITV, libro, propietarios, correa (con fecha/km) y facturas."""
    a = p.cfg["scoring"]["estado"]
    dist = distribucion(l, p.rel)
    if dist == "cadena" or (l.correa_cambiada is True and l.correa_detalle is True):
        f_correa = 1.0
    elif l.correa_cambiada is True:
        f_correa = 0.5
    else:
        f_correa = 0.0
    f_prop = 1.0 if l.num_propietarios == 1 else (0.5 if l.num_propietarios == 2 else 0.0)
    score = (a["itv"] * (l.itv_vigor is True) + a["libro"] * (l.libro_mantenimiento is True)
             + a["propietario_unico"] * f_prop + a["correa"] * f_correa + a["facturas"] * (l.facturas is True))
    return {"distribucion": dist, "score": float(score)}


def garantia_efectiva(l: Listing, p: Params) -> tuple[int, bool]:
    """(meses, es_minimo_legal). Profesional sin garantía declarada -> mínimo legal (TRLGDCU art. 120)."""
    if l.garantia_meses:
        return int(l.garantia_meses), False
    if l.vendedor == "profesional" and p.cfg["scoring"]["seguridad_compra"].get("aplicar_minimo_legal_profesional", True):
        return int(p.fiscal["garantia_legal"]["minimo_meses_segunda_mano"]), True
    return 0, False


def s_compra(l: Listing, p: Params) -> dict:
    sg = p.cfg["scoring"]["seguridad_compra"]
    meses, legal = garantia_efectiva(l, p)
    score = (sg["garantia"] * min(1, meses / sg["garantia_meses_full"])
             + sg["ampliable"] * (l.garantia_ampliable is True)
             + sg["km_certificados"] * (l.km_certificados is True)
             + sg["revision"] * ((l.revision_puntos or 0) > 0)
             + sg["devolucion"] * min(1, (l.devolucion_dias or 0) / sg["devolucion_dias_full"])
             + sg["historial"] * (l.libro_mantenimiento is True))
    pen = float(sg.get("penal_particular_sin_garantia", 0)) if (l.vendedor == "particular" and meses == 0) else 0.0
    return {"garantia_meses": meses, "minimo_legal": legal, "penal_particular": pen, "score": clamp(float(score) - pen)}


def ncap(l: Listing, rel: dict) -> Optional[dict]:
    """Entrada de reliability.yaml -> euroncap para el modelo y año (generación), o None."""
    for e in rel.get("euroncap") or []:
        if e.get("modelo") == l.modelo_key and l.anio and e["desde"] <= l.anio <= e["hasta"] and e.get("estrellas") is not None:
            return e
    return None


def asignar_seguridad(l: Listing, p: Params) -> None:
    """Rellena ncap_estrellas/ncap_ref y esp/esp_fuente (anuncio > equipamiento de serie con fuente > obligatorio por año)."""
    e = ncap(l, p.rel)
    l.ncap_estrellas = float(e["estrellas"]) if e else None
    l.ncap_ref = (f"Euro NCAP {e.get('ensayo')}: {e['estrellas']} estrellas ({e.get('protocolo', '')}); {e.get('fuente', '')}"
                  if e else None)
    if l.esp == "sí":
        return
    sv = p.cfg["scoring"].get("seguridad_vial") or {}
    serie = (e or {}).get("esp_serie")
    if l.anio and l.anio >= sv.get("esp_obligatorio_desde", 9999):
        l.esp, l.esp_fuente = "sí", "obligatorio en turismos nuevos desde 1-11-2014 (Reglamento CE 661/2009)"
    elif serie in ("sí", "si"):
        l.esp, l.esp_fuente = "sí", f"de serie: {(e or {}).get('esp_fuente', '')}"
    elif serie == "no":
        l.esp, l.esp_fuente = "no", f"no disponible de serie: {(e or {}).get('esp_fuente', '')}"


def s_seguridad_vial(l: Listing, p: Params) -> dict:
    sv = p.cfg["scoring"]["seguridad_vial"]
    s_n = p.neutro if l.ncap_estrellas is None else clamp(l.ncap_estrellas / 5 * 100)
    s_e = 100.0 if l.esp == "sí" else (0.0 if l.esp == "no" else p.neutro)
    return {"s_ncap": s_n, "s_esp": s_e, "pendiente": l.ncap_estrellas is None,
            "score": sv["peso_ncap"] * s_n + sv["peso_esp"] * s_e}


def s_estetica(l: Listing, p: Params) -> dict:
    from .atributos import s_atributos
    est = p.estetica
    pts = l.estetica_modelo if l.estetica_modelo is not None else 3
    s_mod = (pts - 1) / 4 * 100
    s_atr = s_atributos(l, est)
    return {"puntos_modelo": pts, "s_modelo": s_mod, "s_atributos": s_atr, "ref": l.estetica_ref,
            "score": est["peso_modelo"] * s_mod + est["peso_atributos"] * s_atr}


def s_color(l: Listing, p: Params) -> dict:
    col = p.estetica["colores"]
    grupo = col["grupos"].get(l.color) if l.color else None
    pts = col["puntos"].get(grupo) if grupo in col["puntos"] else None
    return {"color": l.color, "grupo": grupo, "score": float(pts) if pts is not None else p.neutro}





def seguro_estimado(l: Listing, fiscal: dict):
    s = (fiscal.get("seguro_estimado") or {}).get("segmentos") or {}
    return float(s[l.carroceria]["central"]) if l.carroceria in s else None


def consumo_estimado(l: Listing, fiscal: dict):
    """l/100 km de gasolina: por modelo y, si no hay, por segmento. Otros combustibles: None (neutro)."""
    ce = fiscal.get("consumo_estimado") or {}
    if l.combustible != "gasolina":
        return None
    v = (ce.get("modelos") or {}).get(l.modelo_key) or (ce.get("segmentos") or {}).get(l.carroceria)
    return float(v["valor"]) if v and v.get("valor") is not None else None


def seguro_rango(fiscal: dict) -> tuple[float, float]:
    s = fiscal["seguro_estimado"]["segmentos"].values()
    return float(min(x["min"] for x in s)), float(max(x["max"] for x in s))


def s_coste_uso(l: Listing, p: Params) -> dict:
    c = p.cfg["scoring"]["coste_uso"]
    et = l.etiqueta_dgt
    s_et = 0.0  # desde 01-11-2026 la etiqueta tiene criterio propio (s_etiqueta); peso_etiqueta = 0
    cons = consumo_estimado(l, p.fiscal)
    ce = p.fiscal.get("consumo_estimado") or {}
    s_cons = p.neutro if cons is None else clamp(100 * (ce["ref_max"] - cons) / (ce["ref_max"] - ce["ref_min"]))
    seg = seguro_estimado(l, p.fiscal)
    rng = seguro_rango(p.fiscal)
    s_seg = p.neutro if seg is None else clamp(100 * (rng[1] - seg) / (rng[1] - rng[0]))
    mant = s_mantenimiento(l, p)
    score = c["peso_etiqueta"] * s_et + c["peso_consumo"] * s_cons + c["peso_seguro"] * s_seg + c.get("peso_mantenimiento", 0) * mant["score"]
    return {"etiqueta": et, "s_etiqueta": s_et, "seguro": seg, "consumo": cons, "s_cons": s_cons, "s_seg": s_seg,
            "mantenimiento": mant, "score": score}


def s_mantenimiento(l: Listing, p: Params) -> dict:
    """Media de: precio de recambios de la marca (0-100) y tipo de distribución (cadena / correa)."""
    m = p.rel.get("mantenimiento") or {}
    marca = (m.get("marcas") or {}).get(l.marca)
    s_marca = float(marca["puntos"]) if isinstance(marca, dict) and marca.get("puntos") is not None else p.neutro
    dist = distribucion(l, p.rel)
    s_dist = float((m.get("puntos_distribucion") or {}).get(dist, p.neutro)) if dist else p.neutro
    return {"s_marca": s_marca, "distribucion": dist, "s_dist": s_dist, "score": (s_marca + s_dist) / 2}


def s_reventa(l: Listing, p: Params, liq: dict) -> dict:
    """Liquidez (anuncios del modelo en el mercado), días hasta desaparecer y etiqueta (C por encima de B)."""
    rv = p.cfg["scoring"]["reventa"]
    n = liq.get("n_modelo") or 0
    s_liq = clamp(100 * n / rv["liquidez_n_full"])
    d, nd = liq.get("dias"), liq.get("n_dias") or 0
    if d is None or nd < rv["dias_min_muestras"]:
        s_d = p.neutro
    else:
        s_d = clamp(100 * (rv["dias_cero"] - d) / (rv["dias_cero"] - rv["dias_full"]))
    et = s_etiqueta(l, p)
    return {"n_modelo": n, "dias": d, "n_dias": nd, "s_liquidez": s_liq, "s_dias": s_d, "s_etiqueta": et["score"],
            "etiqueta": et, "score": rv["peso_liquidez"] * s_liq + rv["peso_dias"] * s_d + rv["peso_etiqueta"] * et["score"]}


def liquidez(listings: list[Listing], market: list[dict], ventas: list[dict]) -> dict[str, dict]:
    """uid -> {n_modelo, dias, n_dias}: anuncios del modelo vistos en los listados y mediana de días hasta desaparecer."""
    from .normalize import norm_brand, norm_model

    def key(m):
        marca = norm_brand(m.get("marca"), m.get("titulo") or "")
        modelo, _ = norm_model(marca, m.get("modelo"), m.get("titulo") or "")
        return f"{marca} {modelo}" if marca and modelo else None
    cnt: dict[str, int] = {}
    for m in market or []:
        k = key(m)
        if k:
            cnt[k] = cnt.get(k, 0) + 1
    dias: dict[str, list[float]] = {}
    for v in ventas or []:
        k = key(v)
        if k and v.get("dias") is not None:
            dias.setdefault(k, []).append(float(v["dias"]))
    out = {}
    for l in listings:
        ds = dias.get(l.modelo_key or "", [])
        out[l.uid] = {"n_modelo": cnt.get(l.modelo_key or "", 0), "dias": statistics.median(ds) if ds else None, "n_dias": len(ds)}
    return out


def score_all(listings: list[Listing], p: Params, costes: dict[str, dict],
              mkt: Optional[dict] = None, liq: Optional[dict] = None) -> list[dict]:
    meds = medians(listings, p.cfg)
    mkt = mkt or {}
    liq = liq or {}
    w = p.cfg["scoring"]["pesos"]
    rows = []
    for l in listings:
        med, nivel, n = meds[l.uid]
        mm = mkt.get(l.uid)
        if mm and mm[0] is not None:
            med, nivel, n = mm[0], "mercado " + mm[1], mm[2]
        f = s_fiabilidad(l, p)
        pr = s_precio(l, med, p.cfg)
        ke = s_km_edad(l, p)
        es = s_estado(l, p)
        us = s_coste_uso(l, p)
        sc = s_compra(l, p)
        sv = s_seguridad_vial(l, p)
        et = s_estetica(l, p)
        co = s_color(l, p)
        rv = s_reventa(l, p, liq.get(l.uid) or {})
        c = dict(costes[l.uid])
        pen = penal_carroceria(l, p.cfg)
        pen_pres = penal_presupuesto(c["total"], p.cfg)
        total = (w["fiabilidad"] * f["score"] + w["precio"] * pr["score"] + w["km_edad"] * ke["score"]
                 + w["estado"] * es["score"] + w["coste_uso"] * us["score"] + w["seguridad_compra"] * sc["score"]
                 + w["seguridad_vial"] * sv["score"] + w["estetica"] * et["score"] + w["color"] * co["score"]
                 + w["reventa"] * rv["score"]) - pen - pen_pres
        c["primer_anio"] = c["total"] + (us["seguro"] or 0)
        c["exceso"] = max(0.0, c["total"] - p.cfg["presupuesto"]["total_max_eur"])
        c["real_estimado"] = coste_real_estimado(l, c["total"], es["distribucion"], p) if l.vendedor == "particular" else None
        estado = estado_presupuesto(c["total"], p.cfg)
        rows.append({"listing": l, "mediana": med, "nivel_mediana": nivel, "n_mediana": n, "mercado": mm,
                     "fiabilidad": f, "precio": pr, "km_edad": ke, "estado_mant": es, "coste_uso": us, "seguridad": sc,
                     "seguridad_vial": sv, "estetica": et, "color": co, "reventa": rv, "etiqueta": rv["etiqueta"],
                     "total": total, "coste": c, "penalizacion": pen, "penal_presupuesto": pen_pres,
                     "estado": estado, "apto": estado != "no"})
    aptos = sorted((r for r in rows if r["apto"]), key=lambda r: -r["total"])
    # mismo desempate que la fórmula del Excel: orden de fila
    order = {id(r): i for i, r in enumerate(rows)}
    aptos.sort(key=lambda r: (-round(r["total"], 9), order[id(r)]))
    for i, r in enumerate(aptos, 1):
        r["rank"] = i
    return rows


def coste_real_estimado(l: Listing, total: float, dist: Optional[str], p: Params) -> float:
    """Solo informativo (particulares): coste total + reserva de puesta a punto (correa si no consta, neumáticos)."""
    r = p.fiscal.get("reserva_puesta_a_punto") or {}
    extra = 0.0
    if dist != "cadena" and l.correa_cambiada is not True:
        extra += float(r.get("correa_eur", 0))
    if l.neumaticos_nuevos is not True and l.anio and (p.anio_actual - l.anio) >= r.get("neumaticos_edad_min", 0):
        extra += float(r.get("neumaticos_eur", 0))
    return total + extra
