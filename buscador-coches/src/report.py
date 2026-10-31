"""Genera informe.md con los N mejores del ranking."""
from __future__ import annotations

import time
from pathlib import Path

from .scoring import Params

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
             "anuncio": f["anuncio"]["score"], "coste_uso": f["coste_uso"]["score"]}
    best = sorted(parts, key=lambda k: -parts[k] * w[k])[:2]
    labels = {"fiabilidad": "fiabilidad", "precio": "precio", "km_edad": "km y edad", "anuncio": "anuncio", "coste_uso": "coste de uso"}
    out.append("Más aporta: " + ", ".join(f"{labels[k]} ({parts[k]:.0f}/100)" for k in best) + ".")
    d = f["precio"]["descuento"]
    if d is not None:
        out.append(f"Precio {l.precio:,.0f} € frente a una mediana de {f['mediana']:,.0f} € en su segmento "
                   f"({f['nivel_mediana']}, {f['n_mediana']} anuncios): {d:+.0%}.".replace(",", "."))
    ke = f["km_edad"]
    out.append(f"{l.km:,} km en {ke['edad']} años ({ke['km_anio']:,.0f} km/año).".replace(",", "."))
    sig = [n for n, v in (("ITV en vigor", l.itv_vigor), ("libro de mantenimiento", l.libro_mantenimiento),
                          ("distribución cambiada", l.correa_cambiada), ("garantía", l.garantia)) if v]
    if l.num_propietarios == 1:
        sig.append("un solo propietario")
    if sig:
        out.append("El anuncio menciona: " + ", ".join(sig) + ".")
    return out


def _risks(f: dict) -> tuple[list[str], list[str]]:
    l = f["listing"]
    risks, checks = [], []
    for h in f["fiabilidad"]["problemas"]:
        risks.append(f"{h['problema']} (fuente: {h['fuente']}; estado: {h['estado']})")
        checks.append(h["revisar"])
    if f["fiabilidad"]["pendiente"]:
        risks.append(f"No hay dato de fiabilidad con fuente para el {l.modelo_key}: PENDIENTE (se ha puntuado neutro).")
    if not l.motor_key or "?" in (l.motor_key or ""):
        risks.append("El anuncio no deja claro el motor: confirmar con la ficha técnica antes de valorar riesgos.")
    if l.cambio == "automatico":
        checks.append("Cambio automático: transiciones en frío y en caliente, tirones, historial de cambio de aceite de la caja.")
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
        q.append("¿Qué garantía da por escrito (mínimo legal 1 año para profesional) y qué cubre?")
    return q


def write_report(path: Path, filas: list[dict], p: Params, n: int, stats: dict) -> None:
    top = sorted((f for f in filas if f.get("rank")), key=lambda f: f["rank"])[:n]
    lines = [f"# Mejores {n} coches de segunda mano (Valencia, ≤ {p.cfg['presupuesto']['total_max_eur']:,} € en total)".replace(",", "."),
             "", f"Generado el {time.strftime('%Y-%m-%d %H:%M')}. Anuncios limpios: {stats.get('limpios')}, "
                 f"descartados: {stats.get('descartados')}. Plataformas: {stats.get('plataformas')}.", "",
             "> Los datos de fiabilidad, fiscalidad y ZBE marcados como *probable* o *PENDIENTE* en la hoja "
             "Supuestos deben verificarse en la fuente antes de decidir. El coste total incluye ITP (cuota fija de la "
             "Comunitat Valenciana o tipo porcentual), la tasa de transferencia y el informe DGT.", ""]
    if not top:
        lines.append("_No hay anuncios aptos todavía._")
    for f in top:
        l = f["listing"]
        risks, checks = _risks(f)
        lines += [
            f"## {f['rank']}. {l.titulo} — {l.precio:,.0f} € ({f['coste']['total']:,.0f} € en total)".replace(",", "."),
            "", f"**Puntuación {f['total']:.1f}/100** · {l.plataforma} · {l.ubicacion or 'ubicación sin dato'} · "
                f"{l.vendedor or 'vendedor sin dato'} · {'automático' if l.cambio == 'automatico' else 'manual' if l.cambio else 'cambio sin dato'} · "
                f"etiqueta {f['coste_uso']['etiqueta'] or '?'} · [ver anuncio]({l.url})", "",
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
