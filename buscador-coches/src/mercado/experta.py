"""Calidad experta e insesgada del perfil mercado (config_mercado.yaml → calidad_experta).

Cinco apartados, cada uno en percentil 0-100 respecto a los anuncios de la zona base (Valencia, sin comerciales):
- fiabilidad: la de analysis.fiabilidad (TÜV 2026 por edad, TÜV de la generación, OCU de la marca, ajustes de motor). Sin
  fuente → media de su segmento y tramo de edad (se marca como imputada).
- seguridad: estrellas Euro NCAP de la generación (−1 si el ensayo está caducado: protocolo antiguo) y año del modelo (la
  protección real mejora con el año: Folksam/SWOV), a partes iguales; sin ensayo, solo el año. Sin ESP: × 0,8.
- desgaste: vida útil restante (km y años, la que se agote antes; mercado_supuestos.yaml → vida_util).
- ambiente: distintivo DGT (escala ordinal) y CO2 del consumo real, a partes iguales.
- uso: espacio por clase de tamaño y carrocería, y autonomía real en eléctricos.
La calidad experta es la suma ponderada con la media de los pesos de tres esquemas (iguales, ADAC, Consumer Reports); esa
suma es la fórmula de la columna «Calidad experta» del Excel."""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from collections import defaultdict

from ..normalize import norm_text

APARTADOS = ("fiabilidad", "seguridad", "desgaste", "ambiente", "uso")


def pesos(ce: dict) -> dict:
    esq = ce["esquemas"]
    return {k: sum(e[k] for e in esq.values()) / len(esq) for k in APARTADOS}


def _pct_ref(vals: list, ref: list) -> list:
    """Percentil (0-100) de cada valor dentro de la distribución de referencia (empates al punto medio)."""
    r = sorted(x for x in ref if x is not None)
    n = len(r)
    out = []
    for v in vals:
        if v is None or not n:
            out.append(None)
            continue
        lo, hi = bisect_left(r, v), bisect_right(r, v)
        out.append(100.0 * ((lo + hi) / 2) / n)
    return out


def ncap_verificado(a: dict, rec: dict):
    for e in rec.get("euroncap_verificados") or []:
        if norm_text(e["modelo"]) != norm_text(a["modelo_key"]) or not (e["desde"] <= (a["anio"] or 0) <= e["hasta"]):
            continue
        t = norm_text(f"{a.get('titulo') or ''} {a.get('version') or ''}")
        if e.get("titulo_requiere") and e["titulo_requiere"] not in t:
            continue
        if e.get("titulo_excluye") and e["titulo_excluye"] in t:
            continue
        return e
    return None


def calcular(ads: list[dict], ref: list[dict], cfg: dict, sup: dict, rec: dict, anio_actual: int) -> dict:
    ce = cfg["calidad_experta"]
    # Euro NCAP verificado para los que no tienen ensayo en la base
    for a in ads:
        if a["ncap"] is None:
            e = ncap_verificado(a, rec)
            if e:
                vig = "vigente" if anio_actual - e["ensayo"] <= 6 else "caducada (> 6 años)"
                a["ncap"], a["ncap_vigencia"] = float(e["estrellas"]), vig
                a["ncap_ref"] = f"Euro NCAP {e['ensayo']}: {e['estrellas']}★ ({vig}); {e['fuente']}"
    # 1. fiabilidad (imputada por segmento y edad si no hay fuente)
    grp = defaultdict(list)
    for a in ref:
        if "PENDIENTE" not in (a.get("fiab_fuente") or ""):
            grp[(a["segmento"], min(a["edad"] // 4, 5))].append(a["fiab"])
    def fiab(a):
        if "PENDIENTE" not in (a.get("fiab_fuente") or ""):
            return a["fiab"]
        g = grp.get((a["segmento"], min(a["edad"] // 4, 5)))
        return sum(g) / len(g) if g else a["fiab"]
    # 2. seguridad
    s = ce["seguridad"]
    anios_ref = [a["anio"] for a in ref]
    p_anio = _pct_ref([a["anio"] for a in ads], anios_ref)
    def segur(a, pa):
        if a["ncap"] is None:
            v = pa
        else:
            est = max(0.0, a["ncap"] - (s["estrellas_menos_si_caducada"] if (a.get("ncap_vigencia") or "").startswith("caducada") else 0))
            v = s["peso_ncap"] * est / 5 * 100 + s["peso_anio"] * pa
        return v * (s["factor_sin_esp"] if a.get("esp") == "no" else 1)
    # 3. desgaste
    vida = sup["vida_util"]["tabla"]
    def desg(a):
        v = vida.get(a.get("vida_clave") or "*|*", vida["*|*"])
        return 100 * max(0.0, min(1 - (a["km"] or 0) / v["km"], 1 - a["edad"] / v["anios"]))
    # 4. ambiente
    am = ce["ambiente"]
    def co2(a):
        return (a["consumo"] or 0) * am["co2_kg_por_unidad"].get(a["combustible"] or "", 2.31) * 10 if a.get("consumo") else None
    p_co2 = _pct_ref([co2(a) for a in ads], [co2(a) for a in ref])
    def amb(a, pc):
        return am["peso_etiqueta"] * am["escala_etiqueta"].get(a.get("etiqueta"), 0) + (1 - am["peso_etiqueta"]) * (100 - pc if pc is not None else 50)
    # 5. uso
    u = ce["uso"]
    def uso(a):
        e = u["espacio_por_clase"].get(a.get("clase"), u["espacio_sin_clase"]) + u["extra_carroceria"].get(a.get("carroceria"), 0)
        if any(re.search(p, norm_text(a["modelo_key"])) for p in u["dos_plazas"]):
            e = 5
        au = 100.0
        if a["combustible"] == "electrico":
            au = min(100.0, 100 * (a.get("autonomia") or a.get("aut_nueva") or 0.6 * u["autonomia_plena_km"]) / u["autonomia_plena_km"])
        return u["peso_espacio"] * min(e, 100) + (1 - u["peso_espacio"]) * au
    raw = {"fiabilidad": [fiab(a) for a in ads], "seguridad": [segur(a, pa) for a, pa in zip(ads, p_anio)],
           "desgaste": [desg(a) for a in ads], "ambiente": [amb(a, pc) for a, pc in zip(ads, p_co2)], "uso": [uso(a) for a in ads]}
    idx = {id(a): i for i, a in enumerate(ads)}
    W = pesos(ce)
    for k in APARTADOS:
        refv = [raw[k][idx[id(a)]] for a in ref]
        for a, v in zip(ads, _pct_ref(raw[k], refv)):
            a[f"e_{k}"] = round(v, 6)
    for a in ads:
        a["calidad_exp"] = sum(W[k] * a[f"e_{k}"] for k in APARTADOS)
        a["fiab_imputada"] = "PENDIENTE" in (a.get("fiab_fuente") or "")
    return W
