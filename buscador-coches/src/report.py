"""Genera informe.md con los N mejores del ranking."""
from __future__ import annotations

import time
from pathlib import Path

from .scoring import Params

def n(x, dec=0) -> str:
    """Número con formato español: 1.234 / 55,70."""
    if x is None:
        return "?"
    t = f"{x:,.{dec}f}"
    return t.replace(",", "X").replace(".", ",").replace("X", ".")


GENERIC_CHECKS = [
    "Pedir el informe DGT (con la matrícula) antes de la visita: cargas, embargos, titulares, ITV y km registrados.",
    "Comprobar que el número de bastidor del permiso coincide con el del coche (parabrisas y bastidor).",
    "Arranque en frío (motor sin calentar): ruidos, humo y testigos del cuadro.",
    "Prueba de al menos 20 minutos con autovía: embrague, cambio, dirección y frenos.",
    "Desgaste de neumáticos y discos, holguras de suspensión y fugas bajo el motor.",
    "Revisar el aire acondicionado: imprescindible en Valencia.",
]
GENERIC_QUESTIONS = [
    "¿Por qué lo vende y desde cuándo es suyo?",
    "¿Tiene facturas de mantenimiento? ¿Cuándo fue la última revisión y qué se hizo?",
    "¿Ha tenido algún golpe o reparación importante?",
    "¿Acepta que lo revise un mecánico de mi confianza o en un taller antes de cerrar?",
]


def _why(f: dict, p: Params) -> list[str]:
    l = f["listing"]
    w = p.cfg["scoring"]["pesos"]
    out = []
    parts = {"fiabilidad": f["fiabilidad"]["score"], "precio": f["precio"]["score"], "km_edad": f["km_edad"]["score"],
             "anuncio": f["anuncio"]["score"], "coste_uso": f["coste_uso"]["score"], "seguridad": f["seguridad"]["score"]}
    best = sorted(parts, key=lambda k: -parts[k] * w[k])[:2]
    labels = {"fiabilidad": "fiabilidad", "precio": "precio", "km_edad": "km y edad", "anuncio": "anuncio", "coste_uso": "coste de uso", "seguridad": "seguridad de compra"}
    out.append("Más aporta: " + ", ".join(f"{labels[k]} ({parts[k]:.0f}/100)" for k in best) + ".")
    d = f["precio"]["descuento"]
    if d is not None:
        out.append(f"Precio {n(l.precio)} € frente a una mediana de {n(f['mediana'])} € en su segmento "
                   f"({f['nivel_mediana']}, {f['n_mediana']} anuncios): {abs(d):.0%} {'por debajo' if d >= 0 else 'por encima'}.")
    ke = f["km_edad"]
    out.append(f"{n(l.km)} km en {ke['edad']} años ({n(ke['km_anio'])} km/año).")
    sig = [n for n, v in (("ITV en vigor", l.itv_vigor), ("libro de mantenimiento", l.libro_mantenimiento),
                          ("distribución cambiada", l.correa_cambiada), ("garantía", l.garantia)) if v]
    if l.num_propietarios == 1:
        sig.append("un solo propietario")
    if sig:
        out.append("El anuncio menciona: " + ", ".join(sig) + ".")
    sg = f["seguridad"]
    pro = [f"garantía {sg['garantia_meses']} meses" + (" (mínimo legal, no declarada en el anuncio)" if sg["minimo_legal"] else "")] if sg["garantia_meses"] else []
    if l.garantia_ampliable:
        pro.append("ampliable" + (f" por {l.garantia_ampliacion_eur:.0f} €" if l.garantia_ampliacion_eur else ""))
    if l.revision_puntos:
        pro.append(f"revisión de {l.revision_puntos} puntos")
    if l.km_certificados:
        pro.append("km certificados")
    if l.devolucion_dias:
        pro.append(f"{l.devolucion_dias} días de prueba/devolución")
    if pro:
        out.append("Seguridad de compra: " + ", ".join(pro) + ".")
    return out


def _risks(f: dict, rel: dict | None = None) -> tuple[list[str], list[str]]:
    import re as _re
    from .normalize import norm_text
    l = f["listing"]
    risks, checks = [], []
    txt = norm_text(f"{l.titulo} {l.version or ''} {l.descripcion[:400]}")
    for c in (rel or {}).get("cajas") or []:
        if _re.search(c["patron"], txt):
            risks.append(f"{c['nombre']}: {c['problema']} (fuente: {c['fuente']}; estado: {c['estado']}; no ajusta la puntuación)")
            checks.append(c["revisar"])
    for h in f["fiabilidad"]["problemas"]:
        risks.append(f"{h['problema']} (fuente: {h['fuente']}; estado: {h['estado']})")
        checks.append(h["revisar"])
    if f["fiabilidad"]["pendiente"]:
        risks.append(f"No hay dato de fiabilidad con fuente para el {l.modelo_key}: PENDIENTE (se ha puntuado neutro).")
    if not l.motor_key or "?" in (l.motor_key or ""):
        risks.append("El anuncio no deja claro el motor: confirmar con la ficha técnica antes de valorar riesgos.")
    if l.cambio == "automatico":
        checks.append("Cambio automático: transiciones en frío y en caliente, tirones, historial de cambio de aceite de la caja.")
    if l.solo_financiando:
        risks.append(f"El precio anunciado ({n((l.precio_financiado or 0))} €) solo vale financiando; el precio al contado es {n(l.precio)} € (el que se usa aquí).")
    if l.vendedor == "particular":
        risks.append("Venta entre particulares: no hay garantía legal de conformidad (solo vicios ocultos del Código Civil).")
    if l.km_justificados is False or (f["km_edad"]["km_anio"] < 4000 and not l.km_justificados):
        risks.append("Kilometraje anormalmente bajo y sin justificar: verificar en el informe DGT (lecturas de ITV).")
    return risks, checks


def _questions(l) -> list[str]:
    q = []
    if l.itv_vigor is None:
        q.append("¿Hasta cuándo tiene la ITV? ¿Pasó la última sin defectos?")
    if l.libro_mantenimiento is None:
        q.append("¿Tiene el libro de mantenimiento sellado?")
    if l.correa_cambiada is None:
        q.append("¿Cuándo y con cuántos km se cambió la distribución (correa o cadena)? ¿Tiene la factura?")
    if l.num_propietarios is None:
        q.append("¿Cuántos propietarios ha tenido?")
    if l.vendedor == "profesional":
        q.append("¿Qué garantía da por escrito y qué cubre? (mínimo legal 1 año en usados: TRLGDCU art. 120, RDL 7/2021)")
        q.append("¿Cuál es el precio final al contado con todos los gastos (gestión, preparación, transferencia)? ¿Exige financiar?")
    return q


def _embudo_md(stats: dict) -> list[str]:
    e = stats.get("embudo")
    if not e:
        return []
    plats = e["plataformas"]
    head = "| Etapa | " + " | ".join(plats) + " | Total |"
    sep = "|---|" + "---|" * (len(plats) + 1)
    out = ["## Embudo: dónde se pierde volumen", "",
           "Antes de guardar la ficha, cada fuente ya descarta en el listado lo que no cumple precio, año y km "
           "(fila «vistos en listados»). Las cifras de «motivos» cuentan cada anuncio en todos los filtros que no cumple; "
           "«solo por este motivo» son los que entrarían si se relajara únicamente ese filtro.", "", head, sep]
    merc = stats.get("mercado_por_plataforma") or {}
    if merc:
        out.append("| vistos en listados (mercado) | " + " | ".join(str(merc.get(p, 0)) for p in plats) + f" | {sum(merc.get(p, 0) for p in plats)} |")
    for name, c in e["etapas"]:
        out.append(f"| {name} | " + " | ".join(str(c[p]) for p in plats) + f" | {c['total']} |")
    out += ["", "**Motivos de descarte** (todos / solo por este motivo)", "", head.replace("Etapa", "Motivo"), sep]
    for cat, todos, solo in e["motivos"]:
        out.append(f"| {cat} | " + " | ".join(f"{todos[p]} / {solo[p]}" for p in plats) + f" | {todos['total']} / {solo['total']} |")
    return out + [""]


def _ventas_md(ventas: list[dict]) -> list[str]:
    out = ["## Tiempo hasta desaparecer del anuncio (estimación de venta)", ""]
    if not ventas:
        return out + ["_Aún no hay anuncios desaparecidos: hace falta que `run.py` se ejecute varias veces (p. ej. con `--watch`). "
                      "Un anuncio se da por desaparecido tras "
                      "`seguimiento.ejecuciones_para_desaparecido` ejecuciones correctas seguidas sin verlo; en fuentes con "
                      "cobertura parcial (Coches.net, Wallapop) puede ser que solo haya salido de las páginas accesibles._", ""]
    from collections import defaultdict
    from statistics import median
    g = defaultdict(list)
    for v in ventas:
        tramo = "≤ 3.000 €" if v["precio"] <= 3000 else ("3.001–5.000 €" if v["precio"] <= 5000 else "> 5.000 €")
        g[(f"{v['marca'] or ''} {v['modelo'] or ''}".strip(), tramo)].append(v["dias"] or 0)
    out += ["| Modelo | Tramo de precio | Anuncios desaparecidos | Mediana de días publicados |", "|---|---|---|---|"]
    for (mod, tr), d in sorted(g.items(), key=lambda kv: -len(kv[1]))[:30]:
        out.append(f"| {mod} | {tr} | {len(d)} | {median(d):.1f} |")
    return out + ["", "_Días contados desde que el buscador vio el anuncio por primera vez (no desde su publicación real)._", ""]


def write_report(path: Path, filas: list[dict], p: Params, top_n: int, stats: dict) -> None:
    top = sorted((f for f in filas if f.get("rank")), key=lambda f: f["rank"])[:top_n]
    lines = [f"# Mejores {top_n} coches de segunda mano (Valencia, ≤ {n(p.cfg['presupuesto']['total_max_eur'])} € en total)",
             "", f"Generado el {time.strftime('%Y-%m-%d %H:%M')}. Anuncios limpios: {stats.get('limpios')}, "
                 f"descartados: {stats.get('descartados')}. Plataformas: {stats.get('plataformas')}.", "",
             "> Los datos de fiabilidad, fiscalidad y ZBE marcados como *probable* o *PENDIENTE* en la hoja "
             "Supuestos deben verificarse en la fuente antes de decidir. El coste total incluye ITP (cuota fija de la "
             "Comunitat Valenciana o tipo porcentual), la tasa de transferencia y el informe DGT.", ""]
    if stats.get("fuentes"):
        lines += ["**Estado de las fuentes en la última ejecución**", ""]
        for plat, est, det in stats["fuentes"]:
            lines.append(f"- {plat}: {est}" + (f" — {det}" if det else ""))
        if stats.get("desactivadas"):
            lines.append(f"- Desactivadas por bloqueo antibots (ver RECONOCIMIENTO.md): {', '.join(stats['desactivadas'])}")
        lines.append("")
    lines += _embudo_md(stats)
    lines += _ventas_md(stats.get("ventas") or [])
    lines += ["## Los mejores", ""]
    if not top:
        lines.append("_No hay anuncios aptos todavía._")
    for f in top:
        l = f["listing"]
        risks, checks = _risks(f, p.rel)
        lines += [
            f"### {f['rank']}. {l.titulo} — {n(l.precio)} € ({n(f['coste']['total'])} € en total)"
            + (" — **por encima del presupuesto, negociar**" if f.get("estado") == "negociar" else ""),
            "", f"**Puntuación {f['total']:.1f}/100** · {l.plataforma} · {l.ubicacion or 'ubicación sin dato'} · "
                f"{l.vendedor or 'vendedor sin dato'} · {'automático' if l.cambio == 'automatico' else 'manual' if l.cambio else 'cambio sin dato'} · "
                f"etiqueta {f['coste_uso']['etiqueta'] or '?'} · [ver anuncio]({l.url})", "",
            f"Coste: {n(l.precio)} € al contado + gastos {n(f['coste'].get('gastos', 0))} € + ITP {n(f['coste']['itp'])} € + tasa {n(f['coste']['tasa'], 2)} € + informe {n(f['coste']['informe'], 2)} € = **{n(f['coste']['total'])} €**; "
            f"con el seguro estimado ({n(f['coste_uso']['seguro'] or 0)} €/año, aproximado) el primer año sale por **{n(f['coste']['primer_anio'])} €**.", "",
            "**Por qué destaca**", *[f"- {x}" for x in _why(f, p)], "",
            "**Riesgos de este modelo y motor**", *([f"- {x}" for x in risks] or ["- Sin problemas documentados con fuente para este modelo/motor (eso no significa que no los tenga)."]), "",
            "**Qué revisar en la visita**", *[f"- {x}" for x in checks + GENERIC_CHECKS], "",
            "**Qué preguntar al vendedor**", *[f"- {x}" for x in _questions(l) + GENERIC_QUESTIONS], "",
        ]
        if l.duplicados:
            lines += ["_También publicado en: " + "; ".join(l.duplicados) + "_", ""]
        if f["coste"]["avisos"]:
            lines += ["_Avisos de coste: " + "; ".join(f["coste"]["avisos"]) + "_", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
