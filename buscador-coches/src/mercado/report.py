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
    runs = store.db.execute("SELECT started, fuente, zona, estado, vistos, peticiones, detalle FROM runs ORDER BY id").fetchall()
    L += ["## Fuentes (todas las pasadas)", "", "| Inicio | Fuente | Zona | Estado | Anuncios | Peticiones | Detalle |", "|---|---|---|---|---|---|---|"]
    L += [f"| {st_} | {f} | {z} | {e} | {v} | {p} | {(d or '')[:90]} |" for st_, f, z, e, v, p, d in runs if v or e != "ok"] + [""]
    tot = store.db.execute("SELECT plataforma, zona, COUNT(*) FROM anuncios GROUP BY 1, 2").fetchall()
    L += ["Anuncios guardados por plataforma y zona: " + "; ".join(f"{p} {z} {n_}" for p, z, n_ in tot) + ".", ""]
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
    cov = lambda f: sum(1 for a in ads if f(a)) / max(len(ads), 1)  # noqa: E731
    L += ["", "## Cobertura de los datos y pendientes", "",
          f"- Euro NCAP de la generación: {cov(lambda a: a['ncap'] is not None):.0%} de los anuncios; "
          f"TÜV 2026 de su franja de edad: {cov(lambda a: 'TÜV 2026' in a['fiab_fuente']):.0%}; OCU 2026 de la marca: "
          f"{cov(lambda a: 'OCU' in a['fiab_fuente']):.0%}; consumo WLTP del anuncio: {cov(lambda a: bool(a.get('consumo_wltp'))):.0%} "
          "(los listados no lo traen: se usa el consumo real por defecto del segmento y combustible); "
          f"cambio conocido: {cov(lambda a: bool(a['cambio'])):.0%}.",
          "- Sin fuente o PENDIENTE: seguro por segmento con perfil estándar (supuesto calibrado con CHECK24/Kelisto); "
          "precio del juego de neumáticos (supuesto con precios de ensayos OCU); mantenimiento en € por motorización (OCU + "
          "proporciones de Solera); consumo real de eléctricos (sin OBFCM) y consumos por defecto salvo gasolina; ADAC 2026 por "
          "modelo y año (solo mejor/peor de su clase); Euro NCAP y TÜV de muchos premium (BMW, Audi Q, Citroën C5 Aircross…).",
          "- Ayudas a la conducción y equipamiento: los listados no los traen y no se abren fichas (coste de ~20 h por "
          "ejecución con las pausas obligatorias): se aproxima con el % de asistencia a la seguridad de Euro NCAP cuando hay ensayo.",
          "- Garantía restante: solo los meses que publica Coches.net; nuevos y km 0 = 36 meses legales; profesional = 12.",
          "- Liquidez: se mide con varias ejecuciones (python run_mercado.py --watch).",
          "- Nuevos: Coches.net solo deja ver 180 de ~7.300 (ruta nacional, pg <= 6); AutoScout24 no tiene nuevos en el radio.",
          "- Flexicar: 12 de ~1.183 (el resto se carga desde /api/, prohibido por robots.txt).", ""]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
