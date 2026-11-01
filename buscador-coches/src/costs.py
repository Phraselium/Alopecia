"""Coste total de compra: precio + ITP + tasa de transferencia DGT + informe DGT.

Todos los parámetros vienen de fiscal.yaml (con su fuente). Si un dato está PENDIENTE,
el cálculo lo indica en 'avisos' en lugar de inventarlo.
"""
from __future__ import annotations

from typing import Optional

from .models import Listing


def cilindrada_efectiva(l: Listing) -> Optional[int]:
    if l.cilindrada_cc:
        return l.cilindrada_cc
    if l.motor_key:
        try:
            return int(round(float(l.motor_key.split()[0]) * 1000))
        except ValueError:
            return None
    return None


def coef_antiguedad(tabla: list[dict], edad: float) -> Optional[float]:
    """tabla: [{'hasta_anios': 1, 'pct': 100}, ...]; el último puede tener hasta_anios: null."""
    for row in tabla:
        if row.get("hasta_anios") is None or edad <= row["hasta_anios"]:
            return row["pct"] / 100
    return None


def valor_referencia(l: Listing, fiscal: dict, anio_actual: int) -> tuple[Optional[float], list[str]]:
    avisos = []
    pm = (fiscal.get("precios_medios") or {}).get("valores") or {}
    nuevo = pm.get(f"{l.modelo_key}|{l.motor_key}") or pm.get(l.modelo_key or "")
    if not nuevo:
        avisos.append("valor fiscal (precio medio Hacienda) PENDIENTE: base ITP = precio del anuncio")
        return None, avisos
    edad = max(anio_actual - (l.anio or anio_actual), 0)
    coef = coef_antiguedad(fiscal["tabla_depreciacion"]["tramos"], edad)
    if coef is None:
        avisos.append("coeficiente de antigüedad PENDIENTE")
        return None, avisos
    return nuevo * coef, avisos


def itp(l: Listing, fiscal: dict, anio_actual: int) -> tuple[float, list[str]]:
    cfg = fiscal["itp"]
    if l.vendedor == "profesional" and cfg.get("exento_si_profesional", True):
        return 0.0, ["vendedor profesional: sin ITP (operación con IVA/REBU, confirmar en factura)"]
    avisos = []
    if l.vendedor is None:
        avisos.append("tipo de vendedor desconocido: se asume particular (con ITP)")
    edad = max(anio_actual - (l.anio or anio_actual), 0)
    cc = cilindrada_efectiva(l)
    if cc is None:
        avisos.append("cilindrada desconocida: se aplica el tramo de cuota fija más alto")
    # Las reglas se evalúan en orden; la primera que encaja gana (poner antes las de más antigüedad)
    if (l.precio or 0) < cfg.get("cuota_fija_valor_max_eur", 0):
        for regla in cfg.get("cuotas_fijas") or []:
            if edad > regla["antiguedad_mas_de_anios"] and \
                    (cc is None and regla.get("cc_max") is None or
                     cc is not None and regla.get("cc_min", 0) <= cc <= (regla.get("cc_max") or 99999)):
                if edad == regla["antiguedad_mas_de_anios"] + 1:
                    avisos.append("antigüedad en el límite del tramo: depende de la fecha exacta de matriculación")
                return float(regla["cuota_eur"]), avisos + [f"cuota fija ITP: {regla.get('descripcion', '')}"]
    tipo = cfg.get("tipo")
    if tipo is None:
        return 0.0, avisos + ["tipo de ITP PENDIENTE"]
    vr, a2 = valor_referencia(l, fiscal, anio_actual)
    base = max(l.precio or 0, vr or 0)
    return round(base * tipo, 2), avisos + a2


def coste_total(l: Listing, fiscal: dict, anio_actual: int) -> dict:
    """Particular: precio + ITP + tasa DGT + informe DGT.
    Profesional: precio al contado + gastos de gestión del vendedor + (tasa DGT si los gastos no la
    incluyen o no constan) + informe DGT. Sin ITP."""
    imp, avisos = itp(l, fiscal, anio_actual)
    tasa_dgt = fiscal["dgt"]["tasa_transferencia_eur"] or 0
    inf = fiscal["dgt"]["informe_vehiculo_eur"] or 0
    for k, v in (("tasa transferencia", fiscal["dgt"]["tasa_transferencia_eur"]),
                 ("informe DGT", fiscal["dgt"]["informe_vehiculo_eur"])):
        if v is None:
            avisos.append(f"{k} PENDIENTE")
    gastos = 0.0
    tasa = tasa_dgt
    if l.vendedor == "profesional":
        if l.gastos_gestion_eur is not None:
            gastos = float(l.gastos_gestion_eur)
            if l.gastos_incluyen_transferencia:
                tasa = 0.0
            else:
                avisos.append("gastos del vendedor sin indicar si incluyen la transferencia: se suma la tasa DGT")
        else:
            avisos.append("gastos de gestión del vendedor no indicados: se suma la tasa DGT; preguntar el precio final")
        if l.solo_financiando:
            avisos.append(f"el precio anunciado ({l.precio_financiado:,.0f} €) solo vale financiando; se usa el precio al contado".replace(",", "."))
    total = (l.precio or 0) + gastos + imp + tasa + inf
    return {"itp": imp, "gastos": gastos, "tasa": tasa, "informe": inf, "total": round(total, 2), "avisos": avisos}
