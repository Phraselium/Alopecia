"""Genera muestras.md: hasta N anuncios reales por plataforma (validación de cada fuente)."""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
db = sqlite3.connect(BASE / "data" / "listings.sqlite")
by = defaultdict(list)
for (d,) in db.execute("SELECT data FROM listings ORDER BY first_seen"):
    d = json.loads(d)
    by[d["plataforma"]].append(d)


def yn(v):
    return "" if v is None else ("sí" if v else "no")


out = ["# Muestras de anuncios reales por plataforma", "",
       "Datos tal como se guardan en `data/listings.sqlite` tras la extracción y normalización, antes de los filtros "
       "y del scoring. Sirve para comprobar que cada fuente extrae bien los campos.", ""]
for plat, rows in by.items():
    out += [f"## {plat} — {len(rows)} anuncios guardados (muestra de {min(N, len(rows))})", "",
            "| Título | Precio | Contado / financiado | Año | Km | Combustible | Cambio | Vendedor | Ubicación | Fotos | Garantía (meses) | Gastos (€) | ITV / Libro / Correa / Prop. | Enlace |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in rows[:N]:
        cf = f"{d.get('precio_contado') or ''} / {d.get('precio_financiado') or ''}" if d.get("precio_contado") or d.get("precio_financiado") else ""
        sig = f"{yn(d.get('itv_vigor'))} / {yn(d.get('libro_mantenimiento'))} / {yn(d.get('correa_cambiada'))} / {d.get('num_propietarios') or ''}"
        out.append(f"| {(d.get('titulo') or '')[:45]} | {d.get('precio') or ''} | {cf} | {d.get('anio') or ''} | {d.get('km') or ''} | "
                   f"{d.get('combustible') or ''} | {d.get('cambio') or ''} | {d.get('vendedor') or ''} | {(d.get('ubicacion') or '')[:35]} | "
                   f"{d.get('num_fotos') or ''} | {d.get('garantia_meses') or yn(d.get('garantia'))} | {d.get('gastos_gestion_eur') if d.get('gastos_gestion_eur') is not None else ''} | "
                   f"{sig} | [ver]({d['url']}) |")
    out.append("")
(BASE / "muestras.md").write_text("\n".join(out), encoding="utf-8")
print({k: len(v) for k, v in by.items()})
