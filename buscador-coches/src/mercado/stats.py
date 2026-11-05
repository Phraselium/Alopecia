"""Estadística del perfil mercado sin dependencias externas (solo numpy).

- ols(): MCO con errores estándar robustos a heterocedasticidad HC1 (White con corrección n/(n-k)) o, si se pasa
  `cluster`, errores agrupados CR1 (Liang-Zeger con la corrección de Stata G/(G-1)·(n-1)/(n-k)). Si se pasan grupos,
  efectos fijos por grupo eliminados con la transformación "within" (se restan las medias de cada grupo; con HC1 los
  grados de libertad descuentan los grupos; con CR1 no, porque los efectos fijos están anidados en los clústeres, como
  hace `xtreg, fe vce(cluster)`).
- frontera(): conjunto eficiente de Pareto (menor coste anual, mayor calidad).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np


def ols(y, X, names: list[str], groups: Optional[list] = None, cluster: Optional[list] = None) -> dict:
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
    if cluster is None:
        meat = (X * (e ** 2)[:, None]).T @ X
        V = XtX_inv @ meat @ XtX_inv * (n / max(dof, 1))
        n_cl = None
    else:
        cidx = {}
        cid = np.array([cidx.setdefault(c, len(cidx)) for c in cluster])
        n_cl = len(cidx)
        S = np.zeros((n_cl, k))
        np.add.at(S, cid, X * e[:, None])
        meat = S.T @ S
        V = XtX_inv @ meat @ XtX_inv * (n_cl / max(n_cl - 1, 1)) * ((n - 1) / max(n - k, 1))
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    ss_res = float(e @ e)
    ss_tot = float(((y - y.mean()) @ (y - y.mean())))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"names": names, "beta": beta, "se": se, "n": n, "k": k, "grupos": g, "r2_within" if groups is not None else "r2": r2,
            "resid": e, "dof": dof, "V": V, "clusters": n_cl, "errores": "CR1 agrupados" if cluster is not None else "HC1"}


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
