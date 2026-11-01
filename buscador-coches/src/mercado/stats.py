"""Estadística del perfil mercado sin dependencias externas (solo numpy).

- ols(): MCO con errores estándar robustos a heterocedasticidad HC1 (White con corrección n/(n-k)) y, si se pasan grupos,
  efectos fijos por grupo eliminados con la transformación "within" (se restan las medias de cada grupo; los grados de
  libertad descuentan los grupos).
- frontera(): conjunto eficiente de Pareto (menor coste anual, mayor calidad).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np


def ols(y, X, names: list[str], groups: Optional[list] = None) -> dict:
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    n, k = X.shape
    g = 0
    if groups is not None:
        idx = {}
        gid = np.array([idx.setdefault(x, len(idx)) for x in groups])
        g = len(idx)
        for M in (y[:, None], X):
            sums = np.zeros((g, M.shape[1]))
            np.add.at(sums, gid, M)
            cnt = np.bincount(gid, minlength=g)[:, None]
            M -= (sums / cnt)[gid]
        y = y  # (modificado en el sitio)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    e = y - X @ beta
    dof = n - k - g
    meat = (X * (e ** 2)[:, None]).T @ X
    V = XtX_inv @ meat @ XtX_inv * (n / max(dof, 1))
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    ss_res = float(e @ e)
    ss_tot = float(((y - y.mean()) @ (y - y.mean())))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"names": names, "beta": beta, "se": se, "n": n, "k": k, "grupos": g, "r2_within" if groups is not None else "r2": r2,
            "resid": e, "dof": dof}


def coef(res: dict, name: str) -> tuple[float, float, float, float]:
    """(beta, se, IC95 inf, IC95 sup) de un coeficiente."""
    i = res["names"].index(name)
    b, s = float(res["beta"][i]), float(res["se"][i])
    return b, s, b - 1.96 * s, b + 1.96 * s


def pct(b: float) -> float:
    """Coeficiente de un modelo log-lineal -> efecto en % sobre el precio."""
    return math.exp(b) - 1


def frontera(puntos: list[tuple[float, float, object]]) -> list[object]:
    """puntos = [(coste, calidad, id)]. Devuelve los id eficientes: nadie tiene menor o igual coste con más calidad."""
    best = -math.inf
    out = []
    for c, q, i in sorted(puntos, key=lambda p: (p[0], -p[1])):
        if q > best:
            out.append(i)
            best = q
    return out
