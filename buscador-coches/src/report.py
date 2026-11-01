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
             "estado": f["estado_mant"]["score"], "coste_uso": f["coste_uso"]["score"], "seguridad_compra": f["seguridad"]["score"],
             "seguridad_vial": f["seguridad_vial"]["score"], "estetica": f["estetica"]["score"], "reventa": f["reventa"]["score"],
             "color": f["color"]["score"]}
    best = sorted(parts, key=lambda k: -parts[k] * w[k])[:3]
    labels = {"fiabilidad": "fiabilidad", "precio": "precio", "km_edad": "km y edad", "estado": "estado y mantenimiento",
              "coste_uso": "coste de uso", "seguridad_compra": "seguridad de compra", "seguridad_vial": "seguridad (NCAP/ESP)",
              "estetica": "estética", "reventa": "reventa", "color": "color"}
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
        risks.append("Venta entre particulares: no hay garantía legal de conformidad (solo vicios ocultos del Código Civil). "
                     "Pedir informe DGT, historial de ITV y revisión precompra.")
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


FUENTE_TXT = {"DGT": "fichero oficial de la DGT por matrícula", "anuncio": "publicada en el anuncio",
             "regla": "deducida por combustible y fecha de primera matriculación"}


def _etiqueta_md(f: dict, p) -> str:
    l = f["listing"]
    txt = f"**Etiqueta DGT: {l.etiqueta_dgt or '?'}** ({FUENTE_TXT.get(l.etiqueta_fuente, 'sin fuente')}"
    if l.etiqueta_fuente == "DGT":
        txt += f", matrícula {l.matricula}"
    txt += ")."
    if l.etiqueta_incoherente:
        txt += f" ⚠️ **Anuncio incoherente**: el anuncio dice {l.etiqueta_incoherente}; por combustible y fecha corresponde {l.etiqueta_dgt}."
    if l.etiqueta_dudosa:
        txt += (f" ⚠️ **Dudosa** (posibles: {l.etiqueta_opciones}): se puntúa la peor; confirmar la etiqueta con la DGT antes de comprar.")
    z = p.zbe["zbe_valencia"]
    if l.etiqueta_dgt == "B":
        txt += (" ZBE de València: la ordenanza (pendiente de aprobación definitiva; calendario previsto) solo restringe la etiqueta A; "
                "los B pueden circular y no hay fecha prevista para restringirlos, aunque serían el siguiente escalón lógico "
                "si la ZBE se endurece: tenlo en cuenta si piensas quedarte el coche muchos años.")
    elif l.etiqueta_dgt == "A":
        txt += (" ZBE de València: calendario previsto para los A → fuera de la provincia ya restringidos; desde el 1-1-2027 "
                "todos los de fuera del municipio; desde el 1-1-2028 también los de vecinos de València (ordenanza pendiente de "
                "aprobación definitiva).")
    return txt


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
    out += ["", "**Filtros principales** (anuncios que caen en cada filtro / solo por ese filtro)", "",
            head.replace("Etapa", "Filtro"), sep]
    for g, todos, solo in e.get("principales") or []:
        out.append(f"| {g} | " + " | ".join(f"{todos[p]} / {solo[p]}" for p in plats) + f" | {todos['total']} / {solo['total']} |")
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


def _resumen_tabla(fs: list[dict]) -> list[str]:
    out = ["| # | Coche | Año | Km | Coste total | € a negociar | Puntos | Etiqueta (fuente) | Color | Euro NCAP | Garantía | "
           "Vendedor | Enlace | Riesgo principal |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, f in enumerate(fs, 1):
        l = f["listing"]
        risks, _ = _risks(f, None)
        prob = [h["problema"] for h in f["fiabilidad"]["problemas"] if h.get("ajuste", 0) < 0]
        riesgo = (prob[0] if prob else (risks[0] if risks else "sin riesgos documentados con fuente"))[:110]
        gar = f["seguridad"]["garantia_meses"]
        out.append(f"| {i} | {l.titulo} | {l.anio} | {n(l.km)} | {n(f['coste']['total'])} € | "
                   f"{n(f['coste']['exceso']) + ' €' if f['coste']['exceso'] else '—'} | {f['total']:.1f} | "
                   f"{l.etiqueta_dgt or '?'}{' (dudosa: ' + l.etiqueta_opciones + ')' if l.etiqueta_dudosa else ''} ({l.etiqueta_fuente}) | "
                   f"{l.color or (l.color_raw or 'sin dato')} | {('%g★' % l.ncap_estrellas) if l.ncap_estrellas else 'PENDIENTE'} | "
                   f"{(str(gar) + ' meses' + (' (legal)' if f['seguridad']['minimo_legal'] else '')) if gar else 'no'} | "
                   f"{l.vendedor} | [anuncio]({l.url}) | {riesgo} |")
    return out + [""]


def _ficha(f: dict, p: Params) -> list[str]:
    l = f["listing"]
    risks, checks = _risks(f, p.rel)
    est = f["estetica"]
    lines = [
        f"### {f['rank']}. {l.titulo} — {n(l.precio)} € ({n(f['coste']['total'])} € en total)"
        + (f" — **por encima del presupuesto: negociar {n(f['coste']['exceso'])} €**" if f.get("estado") == "negociar" else ""),
        "", f"**Puntuación {f['total']:.1f}/100** · {l.plataforma} · {l.ubicacion or 'ubicación sin dato'} · "
            f"{l.vendedor or 'vendedor sin dato'} · {'automático' if l.cambio == 'automatico' else 'manual' if l.cambio else 'cambio sin dato'} · "
            f"etiqueta {l.etiqueta_dgt or '?'} · color {l.color or 'sin dato'} · [ver anuncio]({l.url})", "",
        f"Coste: {n(l.precio)} € al contado + gastos {n(f['coste'].get('gastos', 0))} € + ITP {n(f['coste']['itp'])} € + tasa {n(f['coste']['tasa'], 2)} € + informe {n(f['coste']['informe'], 2)} € = **{n(f['coste']['total'])} €**; "
        f"con el seguro estimado ({n(f['coste_uso']['seguro'] or 0)} €/año, aproximado) el primer año sale por **{n(f['coste']['primer_anio'])} €**."
        + (f" **Coste real estimado** (con reserva de puesta a punto, informativo): {n(f['coste']['real_estimado'])} €."
           if f["coste"].get("real_estimado") else ""), "",
        _etiqueta_md(f, p), "",
        f"Estética: modelo {est['puntos_modelo']}/5 ({est['ref'] or 'por segmento'}) · atributos {est['s_atributos']:.0f}/100"
        + (f" ({', '.join(x for x in [l.at_acabado and 'acabado ' + l.at_acabado, l.at_llantas and 'llantas ' + l.at_llantas, l.at_faros and 'xenón/LED', l.at_tintados and 'tintados'] if x)})" if any([l.at_acabado, l.at_llantas, l.at_faros, l.at_tintados]) else "")
        + f" · Euro NCAP {('%g estrellas' % l.ncap_estrellas) if l.ncap_estrellas else 'PENDIENTE'} · ESP {l.esp or 'sin dato'}"
        + " · consumo estimado " + (f"{f['coste_uso']['consumo']:.1f} l/100 km (aprox.)" if f['coste_uso'].get('consumo') else "PENDIENTE"), "",
        "**Por qué destaca**", *[f"- {x}" for x in _why(f, p)], "",
        "**Riesgos de este modelo y motor**", *([f"- {x}" for x in risks] or ["- Sin problemas documentados con fuente para este modelo/motor (eso no significa que no los tenga)."]), "",
        "**Qué revisar en la visita**", *[f"- {x}" for x in checks + GENERIC_CHECKS], "",
        "**Qué preguntar al vendedor**", *[f"- {x}" for x in _questions(l) + GENERIC_QUESTIONS], "",
    ]
    if l.duplicados:
        lines += ["_También publicado en: " + "; ".join(l.duplicados) + "_", ""]
    av = [a for a in (f.get("avisos") or "").split("; ") if a]
    if av:
        lines += ["**Avisos**", *[f"- {a}" for a in av], ""]
    if f["coste"]["avisos"]:
        lines += ["_Avisos de coste: " + "; ".join(f["coste"]["avisos"]) + "_", ""]
    return lines


def write_report(path: Path, filas: list[dict], p: Params, top_n: int, stats: dict) -> None:
    ranked = sorted((f for f in filas if f.get("rank")), key=lambda f: f["rank"])
    top = [f for f in ranked if f["listing"].vendedor == "profesional"][:top_n]
    part = [f for f in ranked if f["listing"].vendedor == "particular"][:5]
    pr = p.cfg["presupuesto"]
    lines = [f"# Mejores coches de segunda mano (Valencia, objetivo ≤ {n(pr['total_max_eur'])} € en total, techo {n(pr['techo_eur'])} €)",
             "", f"Generado el {time.strftime('%Y-%m-%d %H:%M')}. Anuncios limpios: {stats.get('limpios')}, "
                 f"descartados: {stats.get('descartados')}. Plataformas: {stats.get('plataformas')}.", "",
             "> Los datos de fiabilidad, seguridad, fiscalidad y ZBE marcados como *probable* o *PENDIENTE* en la hoja "
             "Supuestos deben verificarse en la fuente antes de decidir. El coste total incluye ITP (cuota fija de la "
             "Comunitat Valenciana o tipo porcentual) o los gastos del profesional, la tasa de transferencia y el informe DGT. "
             f"Entre {n(pr['total_max_eur'])} y {n(pr['techo_eur'])} € se restan {pr['penal_por_100_eur']} puntos por cada 100 € y se marca «negociar».", ""]
    lines += [f"## Top {top_n} de profesionales", ""] + (_resumen_tabla(top) if top else ["_Ninguno._", ""])
    lines += ["## Top 5 de particulares (solo modelos de estetica.yaml con 4-5 puntos)", "",
              "> Particular sin garantía: pedir informe DGT, historial ITV y revisión precompra.", ""] + \
             (_resumen_tabla(part) if part else ["_Ninguno._", ""])
    if stats.get("fuentes"):
        lines += ["**Estado de las fuentes en la última ejecución**", ""]
        for plat, est, det in stats["fuentes"]:
            lines.append(f"- {plat}: {est}" + (f" — {det}" if det else ""))
        if stats.get("desactivadas"):
            lines.append(f"- Desactivadas por bloqueo antibots (ver RECONOCIMIENTO.md): {', '.join(stats['desactivadas'])}")
        lines.append("")
    e = stats.get("etiquetas") or {}
    if e:
        fu = e.get("fuente", {})
        lines += [f"**Etiqueta DGT de los {stats.get('limpios')} anuncios limpios**: confirmada en el fichero oficial de la DGT "
                  f"{fu.get('DGT', 0)}, según el anuncio {fu.get('anuncio', 0)}, deducida por regla {fu.get('regla', 0)} "
                  f"(de ellas dudosas: {e.get('dudosas', 0)}). Descartados por etiqueta: {e.get('descartadas', 0)} "
                  f"(no confirmada {e.get('no_confirmada', 0)}, dudosa {e.get('dudosas_fuera', 0)}, menor que la mínima {e.get('menor_que_minima', 0)}).", ""]
    z = p.zbe["zbe_valencia"]
    lines += ["> **ZBE de València**: la ordenanza está **pendiente de aprobación definitiva** (aprobación inicial 25-02-2025; "
              f"comprobado en valencia.es el {z['consultado']}). Su calendario es **previsto**, no vigente: restringe solo la "
              "etiqueta A (fuera de la provincia desde 12-2025; desde 1-1-2027 todos los de fuera del municipio; desde 1-1-2028 "
              "también los de vecinos). Los B no tienen restricción ni fecha prevista. Detalle y fuentes en zbe.yaml.", ""]
    ex = p.cfg["filtros"]
    lines += [f"> **Excluidos siempre**: {', '.join(ex.get('modelos_excluidos') or []) or 'ninguno'}"
              + ("; caja Multitronic de Audi" if ex.get("excluir_multitronic") else "")
              + ("; cajas robotizadas" if ex.get("excluir_cajas_robotizadas") else "")
              + (f"; colores {', '.join(ex['color']['excluidos'])}" if (ex.get("color") or {}).get("excluir_activo") else "") + ".", ""]
    lines += _embudo_md(stats)
    lines += _ventas_md(stats.get("ventas") or [])
    lines += [f"## Fichas: top {top_n} de profesionales", ""]
    for f in top:
        lines += _ficha(f, p)
    lines += ["## Fichas: top 5 de particulares", ""]
    for f in part:
        lines += _ficha(f, p)
    path.write_text("\n".join(lines), encoding="utf-8")
