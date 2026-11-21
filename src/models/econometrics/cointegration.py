"""Johansen (implementación propia) del procedimiento de Johansen (reduced-rank regression)
con los cinco casos deterministas, regresores exógenos no restringidos
(dummies estacionales centradas, impulsos), corrección de Reinsel-Ahn y
bootstrap salvaje de Cavaliere, Rahbek & Taylor (2012, Econometrica) para
el contraste de traza secuencial.

Casos (notación EViews / MacKinnon-Haug-Michelis 1999):
  1: sin deterministas
  2: constante restringida al espacio de cointegración
  3: constante no restringida (tendencia lineal en niveles, no en la RC)
  4: tendencia restringida + constante no restringida
  5: tendencia y constante no restringidas
"""
from __future__ import annotations

import numpy as np
from scipy import linalg

# Valores críticos asintóticos 95 % de MacKinnon, Haug & Michelis (1999)
# indexados por n-r = 1..5 (traza y máximo autovalor). Caso 3 y 4 coinciden
# con los que devuelve statsmodels (comprobado en 03_johansen.py); el caso 2 se
# contrasta por simulación en 03_johansen.py.
MHM_TRACE95 = {
    2: [9.164546, 20.26184, 35.19275, 54.07904, 76.97277],
    3: [3.841466, 15.49471, 29.79707, 47.85613, 69.81889],
    4: [12.32090, 25.87211, 42.91525, 63.87610, 88.80380],
}
MHM_MAX95 = {
    2: [9.164546, 15.89210, 22.29962, 28.58808, 34.80587],
    3: [3.841466, 14.26460, 21.13162, 27.58434, 33.87687],
    4: [12.32090, 19.38704, 25.82321, 32.11832, 38.33101],
}


def _lagmat(dy: np.ndarray, k: int) -> np.ndarray:
    T = dy.shape[0]
    if k == 0:
        return np.empty((T - k, 0))
    return np.hstack([dy[k - i - 1:T - i - 1] for i in range(k)])


def build_matrices(y: np.ndarray, k_ar_diff: int, case: int, exog: np.ndarray | None = None):
    """Devuelve Z0 (=Δy_t), Z1 (y_{t-1} [+1 / +t]), Z2 (Δy_{t-i}, deterministas no restringidos, exog)."""
    y = np.asarray(y, float)
    T_full, n = y.shape
    dy = np.diff(y, axis=0)
    k = k_ar_diff
    Z0 = dy[k:]
    T = Z0.shape[0]
    Z1 = y[k:-1]
    trend = np.arange(k + 1, k + 1 + T, dtype=float)
    Z2 = [_lagmat(dy, k)] if k > 0 else []
    if case == 2:
        Z1 = np.column_stack([Z1, np.ones(T)])
    elif case == 3:
        Z2.append(np.ones((T, 1)))
    elif case == 4:
        Z1 = np.column_stack([Z1, trend])
        Z2.append(np.ones((T, 1)))
    elif case == 5:
        Z2.append(np.ones((T, 1)))
        Z2.append(trend[:, None])
    if exog is not None:
        ex = np.asarray(exog, float)
        if ex.ndim == 1:
            ex = ex[:, None]
        Z2.append(ex[-T:])  # exog alineado con la muestra de y (mismo índice)
    Z2 = np.hstack(Z2) if Z2 else np.empty((T, 0))
    return Z0, Z1, Z2


def rrr(Z0, Z1, Z2):
    if Z2.shape[1] > 0:
        B0 = linalg.lstsq(Z2, Z0)[0]
        B1 = linalg.lstsq(Z2, Z1)[0]
        R0 = Z0 - Z2 @ B0
        R1 = Z1 - Z2 @ B1
    else:
        R0, R1 = Z0, Z1
    T = R0.shape[0]
    S00 = R0.T @ R0 / T
    S11 = R1.T @ R1 / T
    S01 = R0.T @ R1 / T
    S10 = S01.T
    M = S10 @ linalg.solve(S00, S01)
    eigval, eigvec = linalg.eigh(M, S11)
    idx = np.argsort(eigval)[::-1]
    eigval = np.clip(eigval[idx], 0, 1 - 1e-12)
    eigvec = eigvec[:, idx]
    return eigval, eigvec, S00, S01, S11, R0, R1


class Johansen:
    def __init__(self, y, k_ar_diff=1, case=3, exog=None):
        self.y = np.asarray(y, float)
        self.n = self.y.shape[1]
        self.k = k_ar_diff
        self.case = case
        self.exog = exog
        Z0, Z1, Z2 = build_matrices(self.y, k_ar_diff, case, exog)
        self.Z0, self.Z1, self.Z2 = Z0, Z1, Z2
        self.T = Z0.shape[0]
        (self.eig, self.evec, self.S00, self.S01, self.S11, self.R0, self.R1) = rrr(Z0, Z1, Z2)
        n = self.n
        self.eig = self.eig[:n]
        self.trace = np.array([-self.T * np.sum(np.log(1 - self.eig[r:])) for r in range(n)])
        self.maxeig = np.array([-self.T * np.log(1 - self.eig[r]) for r in range(n)])
        # Reinsel & Ahn (1992): factor (T - n*p)/T con p = orden del VAR en niveles
        p = k_ar_diff + 1
        self.ra = (self.T - n * p) / self.T
        self.trace_ra = self.trace * self.ra
        self.maxeig_ra = self.maxeig * self.ra

    def cv(self, kind="trace"):
        tab = MHM_TRACE95 if kind == "trace" else MHM_MAX95
        if self.case not in tab:
            return [np.nan] * self.n
        return [tab[self.case][self.n - r - 1] for r in range(self.n)]

    def beta(self, r):
        return self.evec[:, :r]

    def alpha(self, r):
        b = self.beta(r)
        return self.S01 @ b @ linalg.inv(b.T @ self.S11 @ b)

    def loglik(self, r):
        return -self.T / 2 * (np.log(linalg.det(self.S00)) + np.sum(np.log(1 - self.eig[:r])))

    def fit_restricted(self, r):
        """Parámetros del VECM con rango r (para bootstrap): α, β, Γ/Φ (coef. Z2), residuos."""
        b = self.beta(r)
        a = self.alpha(r)
        ect = self.Z1 @ b
        X = np.hstack([ect, self.Z2]) if self.Z2.shape[1] else ect
        coef = linalg.lstsq(X, self.Z0)[0]
        resid = self.Z0 - X @ coef
        G = coef[r:]  # coeficientes de Z2
        return a, b, G, resid


def wild_bootstrap_trace(y, k_ar_diff, case, exog=None, B=499, rmax=None, seed=12345):
    """Bootstrap salvaje (Rademacher) del contraste de traza, secuencial (CRT 2012).

    Para cada H0: rango = r se simula el VECM restringido estimado bajo H0
    con residuos remuestreados y se recalcula la traza. Devuelve p-valores.
    """
    rng = np.random.default_rng(seed)
    y = np.asarray(y, float)
    n = y.shape[1]
    rmax = n if rmax is None else rmax
    J = Johansen(y, k_ar_diff, case, exog)
    pvals = []
    for r in range(rmax):
        a, b, G, resid = J.fit_restricted(r) if r > 0 else (None, None, None, None)
        if r == 0:
            X = J.Z2
            coef = linalg.lstsq(X, J.Z0)[0] if X.shape[1] else np.zeros((0, n))
            resid = J.Z0 - X @ coef if X.shape[1] else J.Z0.copy()
            G = coef
        resid = resid - resid.mean(0)
        stats = np.empty(B)
        T = J.T
        k = k_ar_diff
        for bi in range(B):
            w = rng.choice([-1.0, 1.0], size=T)
            eps = resid * w[:, None]
            ys = np.empty_like(y)
            ys[:k + 1] = y[:k + 1]
            # reconstruir recursivamente: Δy_t = α β' Z1_t + G' Z2_t + e_t
            dys = np.diff(ys[:k + 1], axis=0)
            dys_list = list(dys)
            for t in range(T):
                tt = t + k + 1  # índice en niveles
                ylag = ys[tt - 1]
                z1 = ylag
                trend_t = float(k + 1 + t)
                if case == 2:
                    z1 = np.append(ylag, 1.0)
                elif case == 4:
                    z1 = np.append(ylag, trend_t)
                z2 = []
                if k > 0:
                    z2.extend(np.concatenate([dys_list[-i - 1] for i in range(k)]))
                if case in (3, 4, 5):
                    z2.append(1.0)
                if case == 5:
                    z2.append(trend_t)
                if exog is not None:
                    ex = np.asarray(exog, float)
                    ex = ex[:, None] if ex.ndim == 1 else ex
                    z2.extend(ex[-T:][t])
                z2 = np.asarray(z2)
                d = eps[t].copy()
                if r > 0:
                    d += a @ (b.T @ z1)
                if z2.size:
                    d += z2 @ G
                ys[tt] = ylag + d
                dys_list.append(d)
            Jb = Johansen(ys, k_ar_diff, case, exog)
            stats[bi] = Jb.trace[r]
        pvals.append(float(np.mean(stats >= J.trace[r])))
    return J, pvals


def rank_tests(y, k_ar_diff, case, exog=None, B=999, seed=12345, rmax=3):
    """Resumen de rango: traza, máx. autovalor, Reinsel-Ahn, VC asintóticos y p bootstrap."""
    J, pboot = wild_bootstrap_trace(y, k_ar_diff, case, exog, B=B, rmax=rmax, seed=seed)
    cvt, cvm = J.cv("trace"), J.cv("max")
    rows = []
    for r in range(J.n):
        rows.append({"H0": f"r<={r}", "eigenvalue": float(J.eig[r]), "trace": float(J.trace[r]),
                     "trace_reinsel_ahn": float(J.trace_ra[r]), "cv95_trace": float(cvt[r]),
                     "maxeig": float(J.maxeig[r]), "cv95_maxeig": float(cvm[r]),
                     "p_bootstrap_trace": float(pboot[r]) if r < len(pboot) else None})
    def first_nonreject(stat, cv):
        return next((r for r in range(J.n) if stat[r] < cv[r]), J.n)
    sel = {"asintotico_traza": first_nonreject(J.trace, cvt),
           "reinsel_ahn_traza": first_nonreject(J.trace_ra, cvt),
           "max_autovalor": first_nonreject(J.maxeig, cvm),
           "bootstrap_5pct": next((r for r, p in enumerate(pboot) if p >= 0.05), len(pboot)),
           "bootstrap_10pct": next((r for r, p in enumerate(pboot) if p >= 0.10), len(pboot))}
    return {"T_efectiva": int(J.T), "case": case, "k_ar_diff": k_ar_diff, "B": B, "tests": rows, "rango_seleccionado": sel}


def engle_granger(y_dep, X, maxlag=4):
    from statsmodels.tsa.stattools import coint
    s, p, cv = coint(y_dep, X, trend="c", maxlag=maxlag, autolag="aic")
    return {"stat": float(s), "p": float(p), "cv5": float(cv[1])}
