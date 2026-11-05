"""Distintivo ambiental de cada anuncio, por orden de fiabilidad:

1. DGT: matrícula del anuncio buscada en el fichero oficial (src/dgt.py).
2. anuncio: etiqueta que publica la plataforma (p. ej. Coches.net, OcasionPlus).
3. regla: combustible + FECHA DE PRIMERA MATRICULACIÓN según los criterios de la DGT (zbe.yaml).
   Años frontera sin mes conocido -> etiqueta "dudosa" = la peor de las posibles.

La misma regla se escribe como fórmula en el Excel (src/excel.py); esta es la réplica en Python.
"""
from __future__ import annotations

import re
from typing import Optional

from .models import Listing

ORDEN = ["A", "B", "C", "ECO", "CERO"]
ALIAS = {"0": "CERO", "0_EMISIONES": "CERO", "CERO": "CERO", "ZERO": "CERO", "ECO": "ECO", "C": "C", "B": "B", "A": "A",
         "SIN": "A", "SIN DISTINTIVO": "A", "SIN ETIQUETA": "A"}


def norm_label(x) -> Optional[str]:
    if x is None:
        return None
    t = str(x).strip().upper().replace("ETIQUETA", "").replace("DISTINTIVO", "").strip()
    return ALIAS.get(t)


def rank(lab: Optional[str]) -> int:
    return ORDEN.index(lab) if lab in ORDEN else -1


def parse_fecha(s) -> tuple[Optional[int], Optional[int]]:
    """'2009-09-01', '09/2009', '2009-09', '12-2018' -> (año, mes). '2009' -> (2009, None)."""
    if s is None:
        return None, None
    t = str(s).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^(\d{1,2})[/-](\d{4})$", t)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.match(r"^(\d{4})$", t)
    if m:
        return int(m.group(1)), None
    return None, None


def _ym(y: int, m: int) -> int:
    return y * 100 + m


def label_at(fuel: Optional[str], y: int, m: int, crit: dict) -> Optional[str]:
    if fuel in ("hibrido", "glp", "gnc", "phev"):
        return "ECO"          # PHEV: sin autonomía conocida se asume < 40 km (ECO), lo conservador
    if fuel == "electrico":
        return "CERO"
    c = crit.get({"gasolina": "gasolina", "diesel": "diesel"}.get(fuel or "", ""))
    if not c:
        return None
    v = _ym(y, m)
    if v >= _ym(*c["C_desde"]):
        return "C"
    if v >= _ym(*c["B_desde"]):
        return "B"
    return "A"


def is_frontier(fuel: Optional[str], y: Optional[int], crit_fr: dict) -> bool:
    return y is not None and y in (crit_fr.get(fuel or "") or [])


def label_rule(fuel: Optional[str], y: Optional[int], m: Optional[int], zbe: dict) -> tuple[Optional[str], bool]:
    """(etiqueta, dudosa). Sin mes: si el año es frontera, la peor del par de años frontera (dudosa)."""
    crit = zbe["criterios_etiqueta"]
    fr = crit.get("fronteras") or {}
    if y is None:
        return None, False
    if m:
        return label_at(fuel, y, m, crit), False
    if is_frontier(fuel, y, fr):
        yy = y - 1 if is_frontier(fuel, y - 1, fr) else y
        return label_at(fuel, yy, 1, crit), True
    return label_at(fuel, y, 1, crit), False


def opciones_regla(fuel: Optional[str], y: Optional[int], m: Optional[int], zbe: dict) -> list[str]:
    """Etiquetas posibles según la regla con CUALQUIER fecha posible: con mes, una sola; sin mes, enero y diciembre
    del año y, si es año frontera, también la del año frontera anterior (la de label_rule). Ordenadas de peor a mejor."""
    crit = zbe["criterios_etiqueta"]
    if y is None:
        return []
    if m:
        lab = label_at(fuel, y, m, crit)
        return [lab] if lab else []
    worst, _ = label_rule(fuel, y, None, zbe)
    ops = {x for x in (worst, label_at(fuel, y, 1, crit), label_at(fuel, y, 12, crit)) if x}
    return sorted(ops, key=rank)


def asignar(l: Listing, zbe: dict, dgt=None) -> Listing:
    """Rellena etiqueta_dgt (final = PEOR opción posible), etiqueta_fuente, etiqueta_dudosa, etiqueta_opciones,
    etiqueta_incoherente y etiqueta_codigo_dgt.

    - DGT (matrícula en el fichero oficial): una sola opción, confirmada.
    - Anuncio: vale si es una de las opciones de la regla; si la contradice (p. ej. C en un gasolina de 2004),
      se usa la regla y se marca "anuncio incoherente".
    - Regla: todas las opciones posibles con cualquier fecha del año (y del año que diga la URL/título).
    """
    l.etiqueta_codigo_dgt = None
    l.etiqueta_incoherente = None
    if dgt is not None and l.matricula:
        r = dgt.lookup(l.matricula)
        if r:
            l.etiqueta_dgt, l.etiqueta_codigo_dgt = r
            l.etiqueta_fuente, l.etiqueta_dudosa, l.etiqueta_dudosa_anio = "DGT", False, False
            l.etiqueta_opciones = r[0]
            return l
    l.etiqueta_dudosa_anio = False
    y, m = parse_fecha(l.fecha_matriculacion)
    if y is None:
        y, m = l.anio, None
    ops = opciones_regla(l.combustible, y, m, zbe)
    lab = norm_label(l.etiqueta_anuncio)
    if lab and ops and lab not in ops:
        l.etiqueta_incoherente = lab          # el anuncio contradice la regla: se usa la regla
        lab = None
    if lab:
        l.etiqueta_dgt, l.etiqueta_fuente, l.etiqueta_dudosa = lab, "anuncio", False
        opciones = [lab]
    else:
        rl, dud = label_rule(l.combustible, y, m, zbe)
        l.etiqueta_dgt, l.etiqueta_fuente = rl, "regla" if rl else None
        l.etiqueta_dudosa = dud or len(ops) > 1
        opciones = ops or ([rl] if rl else [])
    # Año a confirmar: si el año de la URL o del título daría otra etiqueta, se toma la peor y se marca dudosa
    if l.anio_alternativo and l.etiqueta_dgt:
        alt = opciones_regla(l.combustible, l.anio_alternativo, None, zbe)
        if alt and set(alt) - set(opciones):
            opciones = sorted(set(opciones) | set(alt), key=rank)
            l.etiqueta_dgt = opciones[0]
            l.etiqueta_dudosa = True
            l.etiqueta_dudosa_anio = True
    l.etiqueta_opciones = "/".join(opciones) if opciones else None
    return l
