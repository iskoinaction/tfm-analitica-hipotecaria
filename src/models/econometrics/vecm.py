"""VECM de rango reducido sobre la implementación propia de Johansen.

Incluye: estimación con normalización elegida, errores estándar de β (vía statsmodels con la
misma especificación), contrastes LR de exclusión / exogeneidad débil / homogeneidad,
diagnósticos multivariantes (LM Edgerton-Shukur, ARCH, normalidad), raíces, β recursivo
y remuestreo para bandas bootstrap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import linalg, stats

from .cointegration import Johansen


class VECMfit:
    def __init__(self, y, k_ar_diff=1, case=3, exog=None, r=1, norm_idx=None, names=None):
        self.y = np.asarray(y, float)
        self.n = self.y.shape[1]
        self.k, self.case, self.r, self.norm_idx = k_ar_diff, case, r, norm_idx
        self.exog = None if exog is None else np.asarray(exog, float)
        self.names = list(names) if names is not None else [f"y{i}" for i in range(self.n)]
        self.J = J = Johansen(self.y, k_ar_diff, case, self.exog)
        b = J.beta(r).copy()
        if norm_idx is not None:
            b = b / b[norm_idx, 0]
        self.beta = b
        X = np.hstack([J.Z1 @ b, J.Z2])
        coef, *_ = linalg.lstsq(X, J.Z0)
        self.X, self.coef = X, coef
        self.alpha = coef[:r].T
        self.G = coef[r:]
        self.resid = J.Z0 - X @ coef
        self.T = J.T
        self.sigma = self.resid.T @ self.resid / self.T
        dof = self.T - X.shape[1]
        s_u = self.resid.T @ self.resid / dof
        XtXi = linalg.inv(X.T @ X)
        self.se_alpha = np.sqrt(np.outer(np.diag(XtXi), np.diag(s_u)))[:r].T
        self.p_alpha = 2 * (1 - stats.norm.cdf(np.abs(self.alpha / self.se_alpha)))
        n = self.n
        self.Gamma = [self.G[i * n:(i + 1) * n].T for i in range(k_ar_diff)]

    # -------- representación en niveles
    def var_rep(self):
        n, k = self.n, self.k
        Pi = self.alpha @ self.beta[:n].T
        if k == 0:
            return [np.eye(n) + Pi]
        A = [np.eye(n) + Pi + self.Gamma[0]]
        for i in range(1, k):
            A.append(self.Gamma[i] - self.Gamma[i - 1])
        A.append(-self.Gamma[k - 1])
        return A

    def ma_rep(self, H=20):
        A = self.var_rep()
        p, n = len(A), self.n
        Phi = [np.eye(n)]
        for h in range(1, H + 1):
            Phi.append(sum(A[j - 1] @ Phi[h - j] for j in range(1, min(h, p) + 1)))
        return np.array(Phi)

    def roots(self):
        A = self.var_rep()
        n, p = self.n, len(A)
        Cm = np.zeros((n * p, n * p))
        Cm[:n] = np.hstack(A)
        if p > 1:
            Cm[n:, :-n] = np.eye(n * (p - 1))
        return np.sort(np.abs(linalg.eigvals(Cm)))[::-1]

    # -------- simulación / remuestreo
    def simulate(self, eps):
        y = self.y.copy()
        n, k, case, T = self.n, self.k, self.case, self.T
        dy = list(np.diff(y[:k + 1], axis=0))
        ex = None if self.exog is None else (self.exog[:, None] if self.exog.ndim == 1 else self.exog)[-T:]
        for t in range(T):
            tt = t + k + 1
            ylag = y[tt - 1]
            tr = float(k + 1 + t)
            z1 = np.append(ylag, 1.0) if case == 2 else (np.append(ylag, tr) if case == 4 else ylag)
            z2 = [v for i in range(k) for v in dy[-i - 1]]
            if case in (3, 4, 5):
                z2.append(1.0)
            if case == 5:
                z2.append(tr)
            if ex is not None:
                z2.extend(ex[t])
            d = self.alpha @ (self.beta.T @ z1) + np.asarray(z2) @ self.G + eps[t]
            y[tt] = ylag + d
            dy.append(d)
        return y

    def resample(self, rng):
        u = self.resid - self.resid.mean(0)
        ys = self.simulate(u[rng.integers(0, self.T, self.T)])
        return VECMfit(ys, self.k, self.case, self.exog, self.r, self.norm_idx, self.names)

    @property
    def beta_alpha(self):
        return float((self.beta[:self.n].T @ self.alpha).item())


# --------------------------------------------------------------------------- inferencia sobre β
def beta_inference(Y: pd.DataFrame, exog, k_ar_diff, case, norm_var):
    """β normalizado sobre ``norm_var`` con SE y p (statsmodels VECM, misma especificación)."""
    from statsmodels.tsa.vector_ar.vecm import VECM
    order = [norm_var] + [c for c in Y.columns if c != norm_var]
    det = {2: "ci", 3: "co", 4: "colo"}[case]
    m = VECM(Y[order], exog=exog, k_ar_diff=k_ar_diff, coint_rank=1, deterministic=det).fit()
    out = {}
    for i, v in enumerate(order):
        if v == norm_var:
            continue
        out[v] = {"coef_LP": float(-m.beta[i, 0]), "se": float(m.stderr_beta[i, 0]), "p": float(m.pvalues_beta[i, 0])}
    alpha = {v: {"alpha": float(m.alpha[i, 0]), "se": float(m.stderr_alpha[i, 0]), "p": float(m.pvalues_alpha[i, 0])}
             for i, v in enumerate(order)}
    return out, alpha


def lr_beta_restriction(J: Johansen, H: np.ndarray, r=1):
    """H0: β = Hφ. LR = T Σ log((1-λ*)/(1-λ)) ~ χ²(r(p1-s))."""
    M = H.T @ J.S01.T @ linalg.solve(J.S00, J.S01) @ H
    lam = np.clip(np.sort(linalg.eigh(M, H.T @ J.S11 @ H, eigvals_only=True))[::-1][:r], 0, 1 - 1e-12)
    LR = float(J.T * np.sum(np.log((1 - lam) / (1 - J.eig[:r]))))
    df = r * (H.shape[0] - H.shape[1])
    return {"LR": LR, "df": df, "p": float(1 - stats.chi2.cdf(LR, df))}


def lr_weak_exog(J: Johansen, idx, r=1):
    """H0: α_j = 0 (exogeneidad débil respecto a β) para j en idx."""
    idx = list(np.atleast_1d(idx))
    keep = [i for i in range(J.n) if i not in idx]
    Ra, Rb = J.R0[:, keep], J.R0[:, idx]
    W = np.hstack([Ra, J.R1])
    E = W - Rb @ linalg.lstsq(Rb, W)[0]
    Ea, E1 = E[:, :len(keep)], E[:, len(keep):]
    T = J.T
    Saa, Sa1, S11 = Ea.T @ Ea / T, Ea.T @ E1 / T, E1.T @ E1 / T
    lam = np.clip(np.sort(linalg.eigh(Sa1.T @ linalg.solve(Saa, Sa1), S11, eigvals_only=True))[::-1][:r], 0, 1 - 1e-12)
    LR = float(T * np.sum(np.log((1 - lam) / (1 - J.eig[:r]))))
    df = r * len(idx)
    return {"LR": LR, "df": df, "p": float(1 - stats.chi2.cdf(LR, df))}


def exclusion_matrix(j, p1):
    return np.delete(np.eye(p1), j, axis=1)


def linear_restriction_matrix(R: np.ndarray):
    from scipy.linalg import null_space
    return null_space(R)


# --------------------------------------------------------------------------- diagnósticos
def lm_autocorr(resid, X, h=1):
    u = resid
    T, K = u.shape
    lags = [np.vstack([np.zeros((i, K)), u[:-i]]) for i in range(1, h + 1)]
    Z = np.hstack([X] + lags)
    e = u - Z @ linalg.lstsq(Z, u)[0]
    Su, Se = u.T @ u / T, e.T @ e / T
    LM = float(T * (K - np.trace(linalg.solve(Su, Se))))
    m = K * h
    q = 0.5 * K * m - 1
    N = T - X.shape[1] - m - 0.5 * (K - m + 1)
    s = np.sqrt((K ** 2 * m ** 2 - 4) / (K ** 2 + m ** 2 - 5)) if (K ** 2 + m ** 2 - 5) > 0 else 1
    F = float(((linalg.det(Su) / linalg.det(Se)) ** (1 / s) - 1) * (N * s - q) / (K * m))
    return {"LM": LM, "df": h * K * K, "p_chi2": float(1 - stats.chi2.cdf(LM, h * K * K)),
            "F_rao": F, "p_F": float(1 - stats.f.cdf(F, K * m, N * s - q))}


def arch_lm(resid, lags=4):
    from statsmodels.stats.diagnostic import het_arch
    return [float(het_arch(resid[:, j], nlags=lags)[1]) for j in range(resid.shape[1])]


def normality(resid):
    T, K = resid.shape
    uc = resid - resid.mean(0)
    P = linalg.cholesky(uc.T @ uc / T, lower=True)
    w = linalg.solve(P, uc.T).T
    b1, b2 = (w ** 3).mean(0), (w ** 4).mean(0)
    lam = float(T * b1 @ b1 / 6 + T * (b2 - 3) @ (b2 - 3) / 24)
    return {"stat": lam, "df": 2 * K, "p": float(1 - stats.chi2.cdf(lam, 2 * K)),
            "jb_p_por_ecuacion": [float(stats.jarque_bera(resid[:, j]).pvalue) for j in range(K)]}


def diagnostics(fit):
    return {"LM_h1": lm_autocorr(fit.resid, fit.X, 1), "LM_h4": lm_autocorr(fit.resid, fit.X, 4),
            "ARCH4_p": dict(zip(fit.names, arch_lm(fit.resid))), "normalidad": normality(fit.resid),
            "raices_modulo": [float(x) for x in fit.roots()[:fit.n + 3]]}


def recursive_beta(Y: pd.DataFrame, exog, k, case, norm_idx, min_obs=44, window=None):
    rows = []
    n = len(Y)
    starts_ends = [(0, e) for e in range(min_obs, n + 1)] if window is None else [(s, s + window) for s in range(0, n - window + 1)]
    for s, e in starts_ends:
        ex = None if exog is None else np.asarray(exog)[s:e]
        f = VECMfit(Y.values[s:e], k, case, ex, 1, norm_idx=norm_idx)
        b = -f.beta[:Y.shape[1], 0]
        rows.append({"fin": str(Y.index[e - 1]), "tipo": "recursivo" if window is None else f"movil{window}",
                     **{c: float(b[i]) for i, c in enumerate(Y.columns)}, "alpha_norm": float(f.alpha[norm_idx, 0]),
                     "trace_r0": float(f.J.trace[0]), "trace_r1": float(f.J.trace[1])})
    return pd.DataFrame(rows)
