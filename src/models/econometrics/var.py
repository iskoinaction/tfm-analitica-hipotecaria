"""VAR en primeras diferencias con constante y regresores deterministas (dummies estacionales,
impulsos). Estimación MCO propia (para poder remuestrear) y selección de retardos sobre
muestra común. Las IRF en niveles se obtienen acumulando las de las diferencias."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import linalg


def _design(dy: np.ndarray, p: int, exog: np.ndarray | None, start: int):
    T = dy.shape[0]
    Y = dy[start:]
    X = [np.ones((T - start, 1))]
    for i in range(1, p + 1):
        X.append(dy[start - i:T - i])
    if exog is not None:
        X.append(exog[start:])
    return Y, np.hstack(X)


class VARdiff:
    def __init__(self, dy, p=1, exog=None, names=None, start=None):
        self.dy = np.asarray(dy, float)
        self.n = self.dy.shape[1]
        self.p = p
        self.exog = None if exog is None else np.asarray(exog, float)
        self.names = names or [f"y{i}" for i in range(self.n)]
        self.start = p if start is None else start
        Y, X = _design(self.dy, p, self.exog, self.start)
        B, *_ = linalg.lstsq(X, Y)
        self.B, self.X, self.Y = B, X, Y
        self.resid = Y - X @ B
        self.T = Y.shape[0]
        self.sigma = self.resid.T @ self.resid / self.T
        self.A = [B[1 + i * self.n:1 + (i + 1) * self.n].T for i in range(p)]

    def ma_rep(self, H=20):
        n = self.n
        Phi = [np.eye(n)]
        for h in range(1, H + 1):
            Phi.append(sum(self.A[j - 1] @ Phi[h - j] for j in range(1, min(h, self.p) + 1)))
        return np.array(Phi)

    def roots(self):
        n, p = self.n, self.p
        Cm = np.zeros((n * p, n * p))
        Cm[:n] = np.hstack(self.A)
        if p > 1:
            Cm[n:, :-n] = np.eye(n * (p - 1))
        return np.sort(np.abs(linalg.eigvals(Cm)))[::-1]

    def info_criteria(self):
        k = self.X.shape[1] * self.n
        ld = np.log(linalg.det(self.sigma))
        T = self.T
        return {"aic": ld + 2 * k / T, "bic": ld + np.log(T) * k / T, "hqic": ld + 2 * np.log(np.log(T)) * k / T}

    def resample(self, rng):
        u = self.resid - self.resid.mean(0)
        e = u[rng.integers(0, self.T, self.T)]
        dy = self.dy.copy()
        for t in range(self.T):
            tt = self.start + t
            x = [1.0] + [v for i in range(1, self.p + 1) for v in dy[tt - i]]
            if self.exog is not None:
                x.extend(self.exog[tt])
            dy[tt] = np.asarray(x) @ self.B + e[t]
        return VARdiff(dy, self.p, self.exog, self.names, self.start)


def select_lags(dy, exog=None, maxlags=6):
    """Selección por AIC/BIC/HQ con la MISMA muestra (se descartan los primeros ``maxlags``)."""
    res = {}
    for p in range(1, maxlags + 1):
        res[p] = VARdiff(dy, p, exog, start=maxlags).info_criteria()
    df = pd.DataFrame(res).T
    return {c: int(df[c].idxmin()) for c in df.columns}, df
