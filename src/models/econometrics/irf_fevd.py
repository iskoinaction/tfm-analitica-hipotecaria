"""IRF y FEVD a partir de la representación MA (Φ_h) y de Σ.

* Cholesky con un orden dado y rango sobre TODAS las ordenaciones (n! = 120 para n = 5).
* IRF generalizadas de Pesaran-Shin (1998) y GFEVD normalizada (Diebold-Yilmaz).
* Bandas bootstrap: el modelo aporta ``resample(rng)`` que devuelve un modelo re-estimado.

Convención de arrays: ``irf[h, i, j]`` = respuesta de la variable i en el horizonte h
a un shock en la variable j (columna j asociada a la variable j, sea cual sea el orden).
"""
from __future__ import annotations

import itertools

import numpy as np
from scipy import linalg


def chol_impact(Sigma: np.ndarray, order=None) -> np.ndarray:
    n = Sigma.shape[0]
    order = list(range(n)) if order is None else list(order)
    P = np.eye(n)[order]
    L = P.T @ linalg.cholesky(P @ Sigma @ P.T, lower=True)
    out = np.zeros_like(L)
    for pos, var in enumerate(order):
        out[:, var] = L[:, pos]
    return out


def orth_irf(Phi, Sigma, order=None):
    return np.einsum("hij,jk->hik", Phi, chol_impact(Sigma, order))


def fevd(Phi, Sigma, order=None):
    th = orth_irf(Phi, Sigma, order)
    cum = np.cumsum(th ** 2, axis=0)
    return cum / cum.sum(axis=2, keepdims=True)  # [h, resp, shock]; h=0 es el horizonte 1


def girf(Phi, Sigma):
    return np.einsum("hij,jk->hik", Phi, Sigma) / np.sqrt(np.diag(Sigma))[None, None, :]


def gfevd(Phi, Sigma, normalize=True):
    num = np.cumsum(np.einsum("hij,jk->hik", Phi, Sigma) ** 2, axis=0) / np.diag(Sigma)[None, None, :]
    den = np.cumsum(np.einsum("hij,jk,hlk->hil", Phi, Sigma, Phi), axis=0)
    den = np.array([np.diag(d) for d in den])[:, :, None]
    g = num / den
    return g / g.sum(axis=2, keepdims=True) if normalize else g


def fevd_order_range(Phi, Sigma, resp: int, h: int):
    """Cuotas FEVD de ``resp`` a horizonte h (1-based) en todas las ordenaciones de Cholesky."""
    n = Sigma.shape[0]
    shares = np.array([fevd(Phi[:h], Sigma, order)[h - 1, resp, :] for order in itertools.permutations(range(n))])
    return {"min": shares.min(0), "median": np.median(shares, 0), "max": shares.max(0), "n_orders": len(shares)}


def bootstrap_bands(model, B: int, H: int, resp: int, order=None, seed: int = 0, band=(5, 95), level_from_diff=False):
    """Bandas percentiles para IRF ortogonal, GIRF y FEVD/GFEVD de la variable ``resp``.

    ``model`` debe exponer ``ma_rep(H)``, ``sigma`` y ``resample(rng)``. Si ``level_from_diff`` las
    respuestas se acumulan (VAR en diferencias -> respuesta en niveles).
    """
    rng = np.random.default_rng(seed)
    oi, gi, fv, gf = [], [], [], []
    for _ in range(B):
        try:
            m = model.resample(rng)
            Phi = m.ma_rep(H)
            if level_from_diff:
                Phi = np.cumsum(Phi, axis=0)
            S = m.sigma
            oi.append(orth_irf(Phi, S, order)[:, resp, :])
            gi.append(girf(Phi, S)[:, resp, :])
            fv.append(fevd(Phi[:H], S, order)[:, resp, :])
            gf.append(gfevd(Phi[:H], S)[:, resp, :])
        except (np.linalg.LinAlgError, ValueError):
            continue
    oi, gi, fv, gf = map(np.array, (oi, gi, fv, gf))
    lo, hi = band
    pct = lambda a: (np.percentile(a, lo, axis=0), np.percentile(a, hi, axis=0))
    return {"B_valid": len(oi), "orth_irf": pct(oi), "girf": pct(gi), "fevd": pct(fv), "gfevd": pct(gf)}
