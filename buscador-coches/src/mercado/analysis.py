"""Análisis del perfil mercado: limpieza, coste total, calidad, precios, depreciación, oferta, liquidez, primas,
frontera eficiente, top calidad/coste e infravalorados. Todo se calcula aquí; src/mercado/excel.py lo vuelca al Excel
(las columnas por anuncio como fórmulas que replican este código)."""
from __future__ import annotations

import math
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

from ..averias import analizar
from ..etiqueta import norm_label, opciones_regla, rank
from ..normalize import norm_brand, norm_engine, norm_gearbox, norm_model, norm_text
from . import model as M
from .stats import coef, frontera, ols, pct

ETQ_ORDEN = ["A", "B", "C", "ECO", "CERO"]


def _load(base: Path, name: str) -> dict:
    p = base / name
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def q(v, p):
    v = sorted(v)
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    return st.quantiles(v, n=4, method="inclusive")[{25: 0, 75: 2}[p]]


def franja(precio: float, cortes: list[float]) -> str:
    for lo, hi in zip(cortes[:-1], cortes[1:]):
        if lo <= precio < hi:
            return f"{int(lo)}-{int(hi)}" if hi < 1e8 else f">{int(lo)}"
    return f">{int(cortes[-2])}"


FRANJA_TXT = {"0-5000": "hasta 5.000 €", "5000-10000": "5.000–10.000 €", "10000-15000": "10.000–15.000 €",
              "15000-25000": "15.000–25.000 €", ">25000": "más de 25.000 €"}


# ------------------------------------------------------------------ fiabilidad y seguridad (tablas)
def franja_tuv(edad: float) -> str:
    for hasta, f in ((3, "2-3"), (5, "4-5"), (7, "6-7"), (9, "8-9"), (11, "10-11")):
        if edad <= hasta:
            return f
    return "12-13"


def nk(x: str) -> str:
    """Clave normalizada para cruzar nombres de modelo/marca de distintas fuentes ('Mazda Cx-30' = 'Mazda CX-30')."""
    import re as _re
    t = norm_text(x or "").replace("mercedes benz", "mercedes-benz").replace("ds automobiles", "ds")
    return _re.sub(r"[^a-z0-9]", "", t)


def indices(rel: dict, rec: dict) -> dict:
    ocu = {nk(k): v for k, v in ((rel.get("marcas_ocu_2026") or {}).get("valores") or {}).items()}
    ocu.update({nk(k): v for k, v in (rec.get("ocu_2026_marcas") or {}).items()})
    return {"tuv": {nk(k): v for k, v in ((rec.get("tuv_2026") or {}).get("modelos") or {}).items()},
            "ocu": ocu,
            "ncap": [dict(e, _k=nk(e["modelo"])) for e in (rec.get("euroncap_recientes") or []) + (rel.get("euroncap") or [])]}


def fiabilidad(a: dict, rel: dict, rec: dict, neutro: float, ix: dict | None = None) -> tuple[float, str]:
    """Media de las fuentes que aplican a la GENERACIÓN/EDAD del anuncio + ajustes por motor documentados."""
    from ..scoring import engine_adjust
    from ..models import Listing
    ix = ix or indices(rel, rec)
    vals, src = [], []
    tuv = (rec.get("tuv_2026") or {})
    mods = ix["tuv"].get(nk(a["modelo_key"])) or {}
    fr = franja_tuv(a["edad"])
    if fr in mods and (tuv.get("medias") or {}).get(fr):
        avg = tuv["medias"][fr]
        vals.append(M.clamp(50 + 100 * (avg - mods[fr]) / avg))
        src.append(f"TÜV 2026 {fr} años")
    m_old = (rel.get("modelos") or {}).get(a["modelo_key"]) or {}
    if m_old.get("tuv_mq") is not None and a["edad"] >= 10:
        avg = m_old.get("tuv_media_propia") or (rel.get("medias_tuv_2026") or {}).get(m_old.get("tuv_franja"), {}).get("valor")
        if avg:
            vals.append(M.clamp(50 + 100 * (avg - m_old["tuv_mq"]) / avg))
            src.append("TÜV (reliability.yaml)")
    if nk(a["marca"]) in ix["ocu"]:
        vals.append(float(ix["ocu"][nk(a["marca"])]))
        src.append("OCU 2026 marca")
    base = sum(vals) / len(vals) if vals else neutro
    li = Listing(plataforma="", id_externo="", url="", titulo="", marca=a["marca"], anio=a["anio"], combustible=a["combustible"])
    li.motor_key = a.get("motor_key")
    adj, hits = engine_adjust(li, rel)
    return M.clamp(base + adj), (" + ".join(src) or "PENDIENTE (neutro)") + (f"; ajuste motor/combustible {adj:+.0f}" if adj else "")


def ncap(a: dict, rel: dict, rec: dict, anio_actual: int, ix: dict | None = None):
    ix = ix or indices(rel, rec)
    k = nk(a["modelo_key"])
    for e in ix["ncap"]:
        if e["_k"] == k and a["anio"] and e["desde"] <= a["anio"] <= e["hasta"] and e.get("estrellas") is not None:
            ens = e.get("ensayo") or e["desde"]
            vig = ("vigente" if e["vigente"] else "caducada") if "vigente" in e else ("vigente" if anio_actual - ens <= 6 else "caducada (> 6 años)")
            return float(e["estrellas"]), vig, f"Euro NCAP {ens}: {e['estrellas']}★ ({vig}); asistencia {e.get('asistencia', '?')} %; {e.get('fuente', '')}", e.get("asistencia")
    return None, "", "", None


def esp(a: dict, rel: dict, cfg: dict) -> str | None:
    if a["anio"] and a["anio"] >= cfg["calidad"]["seguridad_vial"]["esp_obligatorio_desde"]:
        return "sí"
    for e in rel.get("euroncap") or []:
        if e.get("modelo") == a["modelo_key"] and a["anio"] and e["desde"] <= a["anio"] <= e["hasta"]:
            return {"sí": "sí", "no": "no"}.get(e.get("esp_serie"))
    return None


# ------------------------------------------------------------------ análisis principal
def run_analysis(rows: list[dict], cfg: dict, base: Path) -> dict:
    sup = _load(base, "mercado_supuestos.yaml")
    rec = _load(base, "mercado_fiabilidad.yaml")
    fiscal, rel, zbe = _load(base, "fiscal.yaml"), _load(base, "reliability.yaml"), _load(base, "zbe.yaml")
    perso = _load(base, "config.yaml")
    anio_actual = fiscal["anio_actual"]
    neutro = cfg["calidad"]["neutro"]
    descartes = Counter()

    # 1. normalización
    ads = []
    for r in rows:
        a = dict(r)
        if not a.get("precio") or a["precio"] < cfg["filtros"]["precio_min_creible"]:
            descartes["precio no creíble o sin precio"] += 1
            continue
        if not a.get("anio"):
            descartes["sin año"] += 1
            continue
        a["marca"] = norm_brand(a.get("marca"), a.get("titulo") or "") or (a.get("marca") or "").title()
        mod, _ = norm_model(a["marca"], a.get("modelo"), a.get("titulo") or "")
        a["modelo"] = mod or (a.get("modelo") or "").strip()
        a["modelo_key"] = f"{a['marca']} {a['modelo']}".strip()
        a["combustible"] = M.norm_fuel_m(a.get("combustible"), a.get("titulo") or "")
        txt = f"{a.get('cambio') or ''} {a.get('titulo') or ''} {a.get('version') or ''}"
        cam = norm_gearbox(a.get("cambio"), a.get("titulo") or "", a.get("version") or "")
        if not cam and norm_text(a.get("cambio")) in ("auto", "automatico", "automatica"):
            cam = "automatico"
        if not cam and a["combustible"] == "electrico":
            cam = "automatico"
        a["cambio"] = cam
        a["segmento"] = M.segmento(a["marca"], a["modelo"], a.get("titulo") or "", a.get("carroceria_raw"), sup) or "otros"
        a["tipo_m"] = M.tipo_anuncio(a, cfg, anio_actual)
        a["edad"] = max(0, anio_actual - a["anio"])
        if a["tipo_m"] in ("nuevo",):
            a["km"] = 0
        a["km"] = a.get("km") or 0
        a["motor_key"] = norm_engine(a.get("version"), a.get("titulo"))
        lab = norm_label(a.get("etiqueta"))
        if lab:
            a["etiqueta"], a["etiqueta_fuente"] = lab, "anuncio"
        else:
            fuel = a["combustible"]
            if fuel in ("hibrido", "glp", "gnc", "phev"):
                a["etiqueta"] = "ECO"
            elif fuel == "electrico":
                a["etiqueta"] = "CERO"
            else:
                ops = opciones_regla(fuel, a["anio"], None, zbe)
                a["etiqueta"] = ops[0] if ops else None
            a["etiqueta_fuente"] = "regla" if a["etiqueta"] else None
        res = analizar(a.get("titulo") or "", "", False)
        if res.descartes:
            descartes[f"avería/estado: {res.descartes[0][0]}"] += 1
            continue
        if any(w in norm_text(a.get("titulo")) for w in cfg["filtros"]["fraude"]["palabras"]):
            descartes["fraude: texto"] += 1
            continue
        ads.append(a)
    # 2. duplicados entre plataformas (mismo coche publicado en varias): misma marca/modelo/año/km/precio
    seen, uniq = {}, []
    for a in sorted(ads, key=lambda x: {"autoscout24": 0, "ocasionplus": 1, "flexicar": 2, "cochesnet": 3}.get(x["plataforma"], 9)):
        k = (a["zona"], a["modelo_key"], a["anio"], a["km"], a["precio"]) if a["km"] else None
        if k and k in seen:
            descartes["duplicado entre plataformas"] += 1
            continue
        if k:
            seen[k] = a["uid"]
        uniq.append(a)
    ads = uniq
    # 3. medianas de mercado (todas las zonas) y fraude por precio anómalo
    mn = cfg["analisis"]["min_anuncios_grupo"]
    g1, g2, g3 = defaultdict(list), defaultdict(list), defaultdict(list)
    for a in ads:
        kb = int(a["km"] // 25000) * 25000
        g1[(a["modelo_key"], a["anio"], kb)].append(a["precio"])
        g2[(a["modelo_key"], a["anio"])].append(a["precio"])
        g3[(a["modelo_key"], a["anio"] // 3 * 3)].append(a["precio"])
    limpios = []
    for a in ads:
        kb = int(a["km"] // 25000) * 25000
        med, niv, n = None, "", 0
        for g, k, nv in ((g1, (a["modelo_key"], a["anio"], kb), "modelo+año+km"), (g2, (a["modelo_key"], a["anio"]), "modelo+año"),
                         (g3, (a["modelo_key"], a["anio"] // 3 * 3), "modelo+tramo de 3 años")):
            if len(g[k]) >= mn:
                med, niv, n = st.median(g[k]), nv, len(g[k])
                break
        a["mediana"], a["nivel_mediana"], a["n_mediana"] = med, niv, n
        if med and a["precio"] < med * (1 - cfg["filtros"]["fraude"]["descuento_max_vs_mediana"]) and niv != "modelo+tramo de 3 años":
            descartes["fraude: precio > 45 % bajo la mediana"] += 1
            continue
        limpios.append(a)
    ads = limpios

    # 4. depreciación (efectos fijos por modelo): log p = FE(modelo) + b_edad·edad + b_km·km/10.000
    uso = cfg["uso"]
    dep, curvas_seg, curvas_marca = {}, [], []

    def fit(sub, nombre):
        if len(sub) < 150 or len({a["modelo_key"] for a in sub}) < 5:
            return None
        y = [math.log(a["precio"]) for a in sub]
        X = [[a["edad"], a["km"] / 10000] for a in sub]
        r = ols(y, X, ["edad", "km10k"], [a["modelo_key"] for a in sub])
        be, bk = float(r["beta"][0]), float(r["beta"][1])
        f5 = math.exp(uso["anios"] * be + uso["anios"] * uso["km_anio"] / 10000 * bk)
        return {"grupo": nombre, "n": r["n"], "modelos": r["grupos"], "b_edad": be, "se_edad": float(r["se"][0]), "b_km10k": bk,
                "se_km10k": float(r["se"][1]), "r2_within": r["r2_within"], "factor5": f5,
                "anual_pct": math.exp(be + uso["km_anio"] / 10000 * bk) - 1}
    pool = [a for a in ads if a["edad"] <= 25]
    dep["*|*"] = fit(pool, "todos") or {"grupo": "por defecto (sin datos suficientes)", "n": 0, "modelos": 0, "b_edad": 0.0,
                                         "se_edad": 0.0, "b_km10k": 0.0, "se_km10k": 0.0, "r2_within": 0.0,
                                         "factor5": cfg["analisis"].get("dep_factor5_defecto", 0.6), "anual_pct": 0.0}
    for seg in sorted({a["segmento"] for a in pool}):
        r = fit([a for a in pool if a["segmento"] == seg], f"segmento {seg}")
        if r:
            dep[f"{seg}|*"] = r
            curvas_seg.append(r)
        for fu in sorted({a["combustible"] for a in pool if a["combustible"]}):
            r = fit([a for a in pool if a["segmento"] == seg and a["combustible"] == fu], f"{seg} · {fu}")
            if r:
                dep[f"{seg}|{fu}"] = r
    for fu in sorted({a["combustible"] for a in pool if a["combustible"]}):
        r = fit([a for a in pool if a["combustible"] == fu], f"combustible {fu}")
        if r:
            curvas_seg.append(r)
    for mk, n in Counter(a["marca"] for a in pool).most_common():
        r = fit([a for a in pool if a["marca"] == mk], f"marca {mk}")
        if r:
            curvas_marca.append(r)

    # 5. coste total de propiedad y calidad
    ix = indices(rel, rec)
    n_mod = Counter(a["modelo_key"] for a in ads)
    for a in ads:
        a["cc_est"], a["cc_fuente"] = M.cc_estimada(a, sup, a["segmento"])
        a["cvf"] = M.cvf(a["cc_est"], a.get("cv"), a["combustible"])
        a["consumo"] = M.consumo(a, a["segmento"], a["combustible"], sup)
        a["dep_clave"] = next(k for k in (f"{a['segmento']}|{a['combustible']}", f"{a['segmento']}|*", "*|*") if dep.get(k))
        t = M.tco(a, a["segmento"], a["combustible"], a["edad"], a["cc_est"], a["cvf"], a["consumo"], sup, fiscal,
                  {k: v for k, v in dep.items() if v}, uso)
        a.update(t)
        a["fiab"], a["fiab_fuente"] = fiabilidad(a, rel, rec, neutro, ix)
        a["ncap"], a["ncap_vigencia"], a["ncap_ref"], a["ncap_asist"] = ncap(a, rel, rec, anio_actual, ix)
        a["esp"] = esp(a, rel, cfg)
        a["n_modelo"] = n_mod[a["modelo_key"]]
    usos = sorted(a["uso_anual"] for a in ads)
    refs = {"USO_MIN": usos[int(0.1 * (len(usos) - 1))], "USO_MAX": usos[int(0.9 * (len(usos) - 1))],
            "RV_N_FULL": float(sorted(n_mod.values())[int(0.9 * (len(n_mod) - 1))])}
    glob, intr = M.pesos(cfg)
    qc = cfg["calidad"]
    etq_pts = perso["scoring"]["etiqueta"]["puntos"]
    for a in ads:
        s = {}
        s["fiabilidad"] = a["fiab"]
        s["precio"] = 50.0 if not a["mediana"] else M.clamp(50 + (a["mediana"] - a["precio"]) / a["mediana"] * qc["precio"]["pendiente"])
        s["estado"] = 100.0 if a["tipo_m"] in ("nuevo", "km0") else float(neutro)
        s["seguridad_vial"] = qc["seguridad_vial"]["peso_ncap"] * (neutro if a["ncap"] is None else a["ncap"] / 5 * 100) + \
            qc["seguridad_vial"]["peso_esp"] * (100.0 if a["esp"] == "sí" else (0.0 if a["esp"] == "no" else neutro))
        gar = a.get("garantia_meses") or (36 if a["tipo_m"] in ("nuevo", "km0") else
                                           (qc["seguridad_compra"]["minimo_legal_profesional_meses"] if a["vendedor"] == "profesional" else 0))
        a["garantia_ef"] = gar
        s["seguridad_compra"] = 100 * min(1, gar / qc["seguridad_compra"]["garantia_meses_full"])
        s["coste_uso"] = M.clamp(100 * (refs["USO_MAX"] - a["uso_anual"]) / (refs["USO_MAX"] - refs["USO_MIN"]))
        s["km_edad"] = M.s_km_edad(a["km"], a["edad"], a["anio"], qc, anio_actual)
        s["reventa"] = 0.5 * M.clamp(100 * a["n_modelo"] / refs["RV_N_FULL"]) + 0.5 * float(etq_pts.get(a["etiqueta"], 0) if a["etiqueta"] else 0)
        a["s"] = s
        a["calidad"] = sum(glob[k] * s[k] for k in glob)
        a["calidad_intr"] = sum(intr[k] * s[k] for k in intr)
        a["ratio"] = a["calidad_intr"] / (a["coste_anual"] / 1000) if a["coste_anual"] > 0 else 0
        a["franja"] = franja(a["precio"], cfg["analisis"]["franjas_precio"])

    # 6. precios por modelo
    precios = []

    def bloque(nivel, keyf, sub):
        g = defaultdict(list)
        for a in sub:
            g[keyf(a)].append(a["precio"])
        for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
            if len(v) >= mn:
                precios.append({"nivel": nivel, "grupo": k, "n": len(v), "mediana": st.median(v), "p25": q(v, 25), "p75": q(v, 75)})
    val = [a for a in ads if a["zona"] == "valencia"]
    bloque("modelo", lambda a: a["modelo_key"], val)
    bloque("modelo · generación (AutoScout24)", lambda a: f"{a['modelo_key']} · gen {a['generacion']}", [a for a in val if a.get("generacion")])
    bloque("modelo · año", lambda a: f"{a['modelo_key']} · {a['anio']}", val)
    bloque("modelo · año · km", lambda a: f"{a['modelo_key']} · {a['anio']} · {int(a['km'] // 25000) * 25}-{int(a['km'] // 25000) * 25 + 25} mil km", val)
    bloque("modelo (Madrid, referencia)", lambda a: a["modelo_key"], [a for a in ads if a["zona"] == "madrid"])
    bloque("modelo (Barcelona, referencia)", lambda a: a["modelo_key"], [a for a in ads if a["zona"] == "barcelona"])

    # 7. oferta
    oferta = {}
    for dim in ("segmento", "combustible", "etiqueta", "franja", "tipo_m", "zona", "plataforma"):
        oferta[dim] = Counter((a.get(dim) or "sin dato") for a in ads)
    med_seg = {}
    for dim in ("segmento", "combustible"):
        g = defaultdict(list)
        for a in val:
            g[a.get(dim) or "sin dato"].append(a["precio"])
        med_seg[dim] = {k: (len(v), st.median(v)) for k, v in g.items()}

    # 8. liquidez (anuncios desaparecidos)
    liq = defaultdict(list)
    for r in rows:
        if r.get("gone_at") and r.get("first_seen"):
            from datetime import datetime
            d = (datetime.fromisoformat(r["gone_at"]) - datetime.fromisoformat(r["first_seen"])).total_seconds() / 86400
            liq["todos"].append(d)

    # 9. primas: etiqueta (C vs B, ECO vs C) y cambio automático (log-precio con FE de modelo)
    primas = {}
    sub = [a for a in ads if a["tipo_m"] in ("ocasion", "seminuevo") and a["etiqueta"] in ETQ_ORDEN and a["cambio"]
           and a["combustible"] and a["km"] > 0]
    if len(sub) > 200:
        anios = sorted({a["anio"] for a in sub})[1:]
        fuels = sorted({a["combustible"] for a in sub})[1:]
        zonas = sorted({a["zona"] for a in sub})[1:]
        names = ["km10k", "km10k2", "auto", "etq_A", "etq_C", "etq_ECO", "etq_CERO"] + [f"anio_{y}" for y in anios] + \
                [f"fuel_{f}" for f in fuels] + [f"zona_{z}" for z in zonas]
        X, y = [], []
        for a in sub:
            k = a["km"] / 10000
            X.append([k, k * k, a["cambio"] == "automatico"] + [a["etiqueta"] == e for e in ("A", "C", "ECO", "CERO")] +
                     [a["anio"] == yy for yy in anios] + [a["combustible"] == f for f in fuels] + [a["zona"] == z for z in zonas])
            y.append(math.log(a["precio"]))
        keep = [j for j in range(len(names)) if any(row[j] for row in X)]
        X = [[row[j] for j in keep] for row in X]
        names = [names[j] for j in keep]
        r = ols(y, X, names, [a["modelo_key"] for a in sub])
        Xa = np.asarray(X, dtype=float)
        primas["modelo"] = {"n": r["n"], "modelos": r["grupos"], "r2_within": r["r2_within"], "k": r["k"],
                            "especificacion": "log(precio) = FE(modelo) + FE(año) + km + km² + automático + etiqueta (base B) "
                                              "+ combustible + zona; MCO con efectos fijos por modelo (within) y errores HC1"}
        for nm, lab in (("auto", "Cambio automático frente a manual"), ("etq_C", "Etiqueta C frente a B")):
            if nm in names:
                b, s, lo, hi = coef(r, nm)
                primas[lab] = {"b": b, "se": s, "pct": pct(b), "lo": pct(lo), "hi": pct(hi), "n_con": int(Xa[:, names.index(nm)].sum())}
        if "etq_ECO" in names and "etq_C" in names:
            # ECO frente a C = b_ECO - b_C, con su varianza (necesita la covarianza: se recalcula con la misma matriz)
            i, j = names.index("etq_ECO"), names.index("etq_C")
            V = _vcov(y, X, [a["modelo_key"] for a in sub])
            d = float(r["beta"][i] - r["beta"][j])
            sd = math.sqrt(max(V[i, i] + V[j, j] - 2 * V[i, j], 0))
            primas["Etiqueta ECO frente a C"] = {"b": d, "se": sd, "pct": pct(d), "lo": pct(d - 1.96 * sd), "hi": pct(d + 1.96 * sd),
                                                 "n_con": int(Xa[:, i].sum())}

    # 10. frontera eficiente, top y infravalorados (zona base: Valencia)
    cortes = cfg["analisis"]["franjas_precio"]
    fr_tags = [franja(lo, cortes) for lo in cortes[:-1]]
    base_ads = [a for a in ads if a["zona"] == "valencia"]
    efic = set(frontera([(a["coste_anual"], a["calidad_intr"], a["uid"]) for a in base_ads]))
    front = {"global": [a for a in base_ads if a["uid"] in efic]}
    for f in fr_tags:
        sub_f = [a for a in base_ads if a["franja"] == f]
        ids = set(frontera([(a["coste_anual"], a["calidad_intr"], a["uid"]) for a in sub_f]))
        front[f] = sorted([a for a in sub_f if a["uid"] in ids], key=lambda a: a["coste_anual"])
    top_fr = {f: sorted([a for a in base_ads if a["franja"] == f], key=lambda a: -a["ratio"])[:5] for f in fr_tags}
    top_seg = {s_: sorted([a for a in base_ads if a["segmento"] == s_], key=lambda a: -a["ratio"])[:5] for s_ in cfg["analisis"]["segmentos_top"]}
    # infravalorados: log precio frente a calidad intrínseca + edad + km + segmento + combustible + tipo (sin FE de modelo)
    segs = sorted({a["segmento"] for a in base_ads})[1:]
    fus = sorted({a["combustible"] or "sin" for a in base_ads})[1:]
    tps = sorted({a["tipo_m"] for a in base_ads})[1:]
    names_i = ["const", "calidad_intr", "edad", "edad2", "km10k"] + [f"seg_{s_}" for s_ in segs] + [f"fuel_{f}" for f in fus] + [f"tipo_{t}" for t in tps]
    Xi = [[1, a["calidad_intr"], a["edad"], a["edad"] ** 2, a["km"] / 10000] + [a["segmento"] == s_ for s_ in segs] +
          [(a["combustible"] or "sin") == f for f in fus] + [a["tipo_m"] == t for t in tps] for a in base_ads]
    yi = [math.log(a["precio"]) for a in base_ads]
    ri = ols(yi, Xi, names_i)
    for a, e in zip(base_ads, ri["resid"]):
        a["resid_valor"] = float(e)
    gm = defaultdict(list)
    for a in base_ads:
        gm[a["modelo_key"]].append(a)
    infra = []
    for mk, lst in gm.items():
        if len(lst) >= mn:
            med_r = st.median(x["resid_valor"] for x in lst)
            infra.append({"modelo": mk, "n": len(lst), "resid": med_r, "pct": math.exp(med_r) - 1,
                          "calidad_intr": st.median(x["calidad_intr"] for x in lst), "precio_mediano": st.median(x["precio"] for x in lst),
                          "segmento": Counter(x["segmento"] for x in lst).most_common(1)[0][0]})
    infra.sort(key=lambda d: d["resid"])
    b_q = coef(ri, "calidad_intr")
    reg_infra = {"n": ri["n"], "k": ri["k"], "r2": ri["r2"], "b_calidad": b_q,
                 "especificacion": "log(precio) = a + b·calidad intrínseca + edad + edad² + km + segmento + combustible + tipo; MCO con errores HC1"}

    resumen = (f"anuncios={len(rows)} limpios={len(ads)} valencia={len(base_ads)} "
               f"descartados={sum(descartes.values())}")
    return {"cfg": cfg, "sup": sup, "rec": rec, "fiscal": fiscal, "anio_actual": anio_actual, "ads": ads, "descartes": descartes,
            "dep": {k: v for k, v in dep.items() if v}, "curvas_seg": curvas_seg, "curvas_marca": curvas_marca,
            "precios": precios, "oferta": oferta, "med_seg": med_seg, "liquidez": liq, "primas": primas,
            "frontera": front, "top_franja": top_fr, "top_segmento": top_seg, "infravalorados": infra, "reg_infra": reg_infra,
            "refs": refs, "pesos": (glob, intr), "resumen": resumen, "n_total": len(rows), "etq_pts": etq_pts}


def _vcov(y, X, groups):
    """Matriz de covarianzas HC1 del modelo within (para contrastes entre coeficientes)."""
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    idx = {}
    gid = np.array([idx.setdefault(x, len(idx)) for x in groups])
    g = len(idx)
    for Mx in (y[:, None], X):
        sums = np.zeros((g, Mx.shape[1]))
        np.add.at(sums, gid, Mx)
        cnt = np.bincount(gid, minlength=g)[:, None]
        Mx -= (sums / cnt)[gid]
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    n, k = X.shape
    meat = (X * (e ** 2)[:, None]).T @ X
    return XtX_inv @ meat @ XtX_inv * (n / max(n - k - g, 1))
