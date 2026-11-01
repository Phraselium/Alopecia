"""Normalización, calidad y coste total de propiedad (5 años) de cada anuncio del perfil mercado.

Réplica exacta en Python de las fórmulas que escribe src/mercado/excel.py en la hoja Anuncios (las pruebas recalculan el
Excel con LibreOffice y comparan celda a celda). Los supuestos con su fuente están en mercado_supuestos.yaml.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from ..normalize import norm_brand, norm_engine, norm_gearbox, norm_model, norm_text, parse_displacement


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


# ------------------------------------------------------------------ normalización
FUEL_PAT = [(r"enchufable|plug.?in|phev|\be-?hybrid\b.*enchuf", "phev"),
            (r"el[eé]ctric|electro(?!/)|\bev\b|\bbev\b", "electrico"),
            (r"h[ií]brid|hybrid|mhev|electro/", "hibrido"),
            (r"glp|gas licuado|lpg|autogas", "glp"),
            (r"gnc|gas natural|cng|tgi", "gnc"),
            (r"di[eé]sel|gas[oó]leo|tdi|hdi|dci|crdi|cdti|tdci", "diesel"),
            (r"gasolina|benzin|petrol|nafta", "gasolina")]


def norm_fuel_m(raw: Optional[str], titulo: str = "") -> Optional[str]:
    for cand in (raw, titulo):
        t = norm_text(cand)
        if not t:
            continue
        for pat, lab in FUEL_PAT:
            if re.search(pat, t):
                return lab
    return None


# carrocería de las plataformas -> segmento del análisis
CN_BODY = {"1": "berlina", "2": "coupe", "3": "cabrio", "4": "familiar", "5": "monovolumen", "6": "suv", "7": "pickup",
           "8": "furgoneta", "9": "furgoneta", "10": "furgoneta"}
OP_BODY = {"TODOTERRENO": "suv", "SUV": "suv", "BERLINA": "berlina", "COMPACTO": "compacto", "FAMILIAR": "familiar",
           "MONOVOLUMEN": "monovolumen", "UTILITARIO": "utilitario", "CABRIO": "cabrio", "COUPE": "coupe",
           "FURGONETA": "furgoneta", "PICK UP": "pickup", "PICKUP": "pickup"}
SEG_PERSONAL = {"utilitario": "utilitario", "compacto": "compacto", "berlina": "berlina", "berlina_d": "berlina",
                "familiar": "familiar", "monovolumen": "monovolumen", "monovolumen_pequeno": "monovolumen", "suv": "suv",
                "cabrio": "cabrio", "furgoneta": "furgoneta"}


def segmento(marca, modelo, titulo, carroceria_raw, sup) -> Optional[str]:
    t = norm_text(f"{titulo}")
    if re.search(r"\b(sw|st|break|touring|avant|wagon|tourer|sportswagen|sports tourer|estate|kombi|combi|variant|familiar)\b", t):
        return "familiar"
    extra = (sup.get("segmentos_modelo") or {}).get(f"{marca} {modelo}")
    if extra:
        return extra
    _, seg = norm_model(marca, modelo, titulo or "")
    if seg:
        return SEG_PERSONAL.get(seg, seg)
    raw = carroceria_raw or ""
    if raw.startswith("op:"):
        return OP_BODY.get(raw[3:].upper())
    if raw.startswith("cn:"):
        return CN_BODY.get(raw[3:])
    return None


def tipo_anuncio(a: dict, cfg: dict, anio_actual: int) -> str:
    t = a.get("tipo") or "ocasion"
    cl = cfg["clasificacion"]
    if t == "ocasion" and a.get("anio") and anio_actual - a["anio"] <= cl["seminuevo_max_anios"] and \
            (a.get("km") or 0) <= cl["seminuevo_max_km"]:
        return "seminuevo"
    return t


def cc_estimada(a: dict, sup: dict, seg: Optional[str]) -> tuple[Optional[int], str]:
    if a.get("cc"):
        return int(a["cc"]), "anuncio"
    d = parse_displacement(f"{a.get('titulo') or ''} {a.get('version') or ''}")
    if d:
        return int(round(d * 1000)), "título (cilindrada en litros)"
    v = (sup.get("cc_por_defecto") or {}).get(seg or "otros")
    return (int(v), "supuesto por segmento") if v else (None, "")


# ------------------------------------------------------------------ coste total de propiedad
def n_cilindros(cc: float) -> int:
    return 3 if cc < 1100 else (4 if cc < 2600 else (6 if cc < 3600 else 8))


def cvf(cc: Optional[float], cv: Optional[float], fuel: Optional[str]) -> Optional[float]:
    """Caballos fiscales (RGV, RD 2822/1998, Anexo V): CVF = 0,08 · (0,785·D²·R)^0,6 · N. Como 0,785·D²·R es la cilindrada
    de un cilindro, CVF = 0,08 · (cc/N)^0,6 · N (N estimado por la cilindrada). Eléctricos: CVF = kW / 5,152."""
    if fuel == "electrico":
        return (cv or 0) * 0.7355 / 5.152 if cv else None
    if not cc:
        return None
    n = n_cilindros(cc)
    return 0.08 * (cc / n) ** 0.6 * n


def ivtm(cv_f: Optional[float], fuel: Optional[str], sup: dict) -> float:
    t = sup["ivtm"]
    if cv_f is None:
        cuota = t["cuota_sin_dato"]
    else:
        cuota = next(c for hasta, c in t["tramos"] if cv_f < hasta)
    bon = (t.get("bonificacion") or {}).get(fuel or "", 0)
    return cuota * (1 - bon)


def consumo(a: dict, seg: Optional[str], fuel: Optional[str], sup: dict) -> Optional[float]:
    """l/100 km (kWh/100 km en eléctricos) en uso real: WLTP del anuncio × (1 + desfase real) o valor por defecto."""
    if a.get("consumo_wltp") and fuel != "electrico":
        return a["consumo_wltp"] * (1 + sup["desfase_wltp_real"].get(fuel, 0))
    return (sup["consumo_por_defecto"].get(fuel or "") or {}).get(seg or "otros") or \
        (sup["consumo_por_defecto"].get(fuel or "") or {}).get("otros")


def itp(a: dict, edad: float, cc: Optional[float], fiscal: dict) -> float:
    """ITP en compra a particular (Comunitat Valenciana): cuota fija si > 12 años y valor < 20.000 €; si no, 6 %."""
    if a.get("vendedor") != "particular" or a.get("tipo_m") in ("nuevo", "km0"):
        return 0.0
    i = fiscal["itp"]
    if edad > 12 and a["precio"] < i["cuota_fija_valor_max_eur"]:
        ccv = cc or 99999
        for cf in i["cuotas_fijas"]:
            if cf["antiguedad_mas_de_anios"] == 12 and cf["cc_min"] <= ccv <= (cf["cc_max"] or 99999):
                return float(cf["cuota_eur"])
    return a["precio"] * i["tipo"]


def seguro(seg: Optional[str], edad: float, sup: dict) -> float:
    s = sup["seguro"]
    tabla = s["todo_riesgo"] if edad <= s["todo_riesgo_hasta_anios"] else s["terceros_ampliado"]
    return float(tabla.get(seg or "otros", tabla["otros"]))


def dep_factor(seg: Optional[str], fuel: Optional[str], dep: dict) -> float:
    """Valor que conserva el coche dentro de 5 años (con 5 × km_anio más): exp(5·b_edad + 5·km_anio·b_km)."""
    k = dep.get(f"{seg}|{fuel}") or dep.get(f"{seg}|*") or dep["*|*"]
    return k["factor5"]


def tco(a: dict, seg, fuel, edad, cc, cv_f, cons, sup, fiscal, dep, uso) -> dict:
    anios, km = uso["anios"], uso["km_anio"]
    energia = (cons or 0) * km / 100 * sup["precio_energia"].get(fuel or "", sup["precio_energia"]["gasolina"])
    seg_e = seguro(seg, edad, sup)
    mant = float(sup["mantenimiento_anual"].get(fuel or "", sup["mantenimiento_anual"]["gasolina"]))
    neum = km / sup["neumaticos"]["duracion_km"] * sup["neumaticos"]["juego"].get(seg or "otros", sup["neumaticos"]["juego"]["otros"])
    imp_circ = ivtm(cv_f, fuel, sup)
    i_tp = itp(a, edad, cc, fiscal)
    tasa = 0.0 if a.get("tipo_m") in ("nuevo", "km0") else float(fiscal["dgt"]["tasa_transferencia_eur"])
    impuestos = i_tp + tasa
    fac = dep_factor(seg, fuel, dep)
    deprec = a["precio"] * (1 - fac)
    uso_anual = energia + seg_e + mant + neum + imp_circ
    total = impuestos + deprec + anios * uso_anual
    return {"itp": i_tp, "tasa": tasa, "energia": energia, "seguro": seg_e, "mant": mant, "neum": neum, "ivtm": imp_circ, "impuestos": impuestos,
            "dep_factor": fac, "depreciacion": deprec, "uso_anual": uso_anual, "tco": total, "coste_anual": total / anios}


# ------------------------------------------------------------------ calidad
def s_km_edad(km, edad, anio, q, anio_actual):
    k = q["km_edad"]
    kma = (km or 0) / max(edad, 0.5)
    s_tot = max(0.0, 100 * (1 - (km or 0) / k["km_max"]))
    s_kma = 100.0 if kma <= k["km_anio_ideal_max"] else max(0.0, 100 * (k["km_anio_cero"] - kma) / (k["km_anio_cero"] - k["km_anio_ideal_max"]))
    s_edad = clamp(100 * ((anio or k["anio_min"]) - k["anio_min"]) / (anio_actual - k["anio_min"]))
    return k["peso_km_total"] * s_tot + k["peso_km_anio"] * s_kma + k["peso_edad"] * s_edad


def pesos(cfg: dict) -> tuple[dict, dict]:
    q = cfg["calidad"]
    w = q["pesos_origen"]
    tot = sum(w.values())
    glob = {k: v / tot for k, v in w.items()}
    wi = {k: v for k, v in w.items() if k not in q["intrinseca_excluye"]}
    ti = sum(wi.values())
    intr = {k: v / ti for k, v in wi.items()}
    return glob, intr
