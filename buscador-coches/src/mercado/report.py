"""informe_mercado.md: resumen del mercado, frontera, top, infravalorados, primas y pendientes."""
from __future__ import annotations

import time
from pathlib import Path

from ..report import n

FR_TXT = {"0-5000": "hasta 5.000 €", "5000-10000": "5.000–10.000 €", "10000-15000": "10.000–15.000 €",
          "15000-25000": "15.000–25.000 €", ">25000": "más de 25.000 €"}


def _coche(a):
    return f"[{a.get('titulo') or a['modelo_key']}]({a.get('url')})"


def _tabla(lst):
    out = ["| # | Coche | Año | Km | Precio | Coste anual | Calidad intr. | Calidad/coste | Tipo | Combustible |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for i, a in enumerate(lst, 1):
        out.append(f"| {i} | {_coche(a)} | {a['anio']} | {n(a['km'])} | {n(a['precio'])} € | {n(a['coste_anual'])} € | "
                   f"{a['calidad_intr']:.1f} | {a['ratio']:.1f} | {a['tipo_m']} | {a['combustible'] or '?'} |")
    return out + [""]


def write_report(path: Path, res: dict, store) -> None:
    ads = res["ads"]
    val = [a for a in ads if a["zona"] == "valencia"]
    L = [f"# Mercado de coches: Valencia (base), Madrid y Barcelona (referencia)", "",
         f"Generado el {time.strftime('%Y-%m-%d %H:%M')}. Anuncios recogidos: {res['n_total']}; limpios: {len(ads)} "
         f"(Valencia {len(val)}). Descartados: " + ", ".join(f"{k} {v}" for k, v in res["descartes"].most_common()) + ".", "",
         "> Coste total a 5 años con uso estándar de " + f"{n(res['cfg']['uso']['km_anio'])} km/año. Supuestos y fuentes en la hoja Supuestos "
         "de mercado.xlsx y en mercado_supuestos.yaml. Calidad: criterios del perfil personal sin estética ni color.", ""]
    runs = store.db.execute("SELECT fuente, zona, estado, vistos, peticiones, detalle FROM runs WHERE id IN "
                            "(SELECT MAX(id) FROM runs GROUP BY fuente, zona)").fetchall()
    L += ["## Fuentes", "", "| Fuente | Zona | Estado | Anuncios | Peticiones |", "|---|---|---|---|---|"]
    L += [f"| {f} | {z} | {e} | {v} | {p} |" for f, z, e, v, p, _d in runs] + [""]
    L += ["## Oferta y precios (Valencia)", "", "| Segmento | Anuncios | Precio mediano |", "|---|---|---|"]
    for k, (cnt, med) in sorted(res["med_seg"]["segmento"].items(), key=lambda kv: -kv[1][0]):
        L.append(f"| {k} | {cnt} | {n(med)} € |")
    L += ["", "| Combustible | Anuncios | Precio mediano |", "|---|---|---|"]
    for k, (cnt, med) in sorted(res["med_seg"]["combustible"].items(), key=lambda kv: -kv[1][0]):
        L.append(f"| {k} | {cnt} | {n(med)} € |")
    L += ["", "## Depreciación (con los propios datos)", "", "| Grupo | Anuncios | Pérdida anual | Valor a 5 años |", "|---|---|---|---|"]
    for d in res["curvas_seg"]:
        L.append(f"| {d['grupo']} | {d['n']} | {-d['anual_pct']:.1%} | {d['factor5']:.0%} |")
    L += ["", "## Frontera eficiente por franja (Valencia)", ""]
    for f, lst in res["frontera"].items():
        if f == "global":
            continue
        L += [f"**{FR_TXT.get(f, f)}** — {len(lst)} coches eficientes", ""] + _tabla(lst[:12])
    L += ["## Top 5 calidad / coste anual por franja (Valencia)", ""]
    for f, lst in res["top_franja"].items():
        L += [f"**{FR_TXT.get(f, f)}**", ""] + _tabla(lst)
    L += ["## Top 5 por segmento (Valencia)", ""]
    for s_, lst in res["top_segmento"].items():
        L += [f"**{s_}**", ""] + _tabla(lst)
    L += ["## Modelos infravalorados", "", "| Modelo | Anuncios | Por debajo de lo previsto | Calidad intr. | Precio mediano |", "|---|---|---|---|---|"]
    for d in res["infravalorados"][:15]:
        L.append(f"| {d['modelo']} | {d['n']} | {-d['pct']:.0%} | {d['calidad_intr']:.1f} | {n(d['precio_mediano'])} € |")
    L += ["", "## Primas", ""]
    m = res["primas"].get("modelo") or {}
    L.append(f"{m.get('especificacion', '')} · n = {m.get('n')} · {m.get('modelos')} modelos · R² within {m.get('r2_within', 0):.3f}")
    L += ["", "| Prima | Estimación | IC 95 % |", "|---|---|---|"]
    for lab in ("Etiqueta C frente a B", "Etiqueta ECO frente a C", "Cambio automático frente a manual"):
        d = res["primas"].get(lab)
        if d:
            L.append(f"| {lab} | {d['pct']:+.1%} | {d['lo']:+.1%} a {d['hi']:+.1%} |")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
