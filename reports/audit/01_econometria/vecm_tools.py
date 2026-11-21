"""Herramientas VECM propias (sobre johansen.Johansen): estimación con rango r,
contrastes LR sobre β y α, IRF/FEVD (Cholesky y generalizadas), bootstrap,
diagnósticos multivariantes."""
from __future__ import annotations

import itertools

import numpy as np
from scipy import linalg, stats

from johansen import Johansen


class VECMfit:
    def __init__(self, y, k_ar_diff=1, case=3, exog=None, r=1, norm_idx=None, names=None):
        self.y = np.asarray(y, float)
        self.n = self.y.shape[1]
        self.k, self.case, self.r, self.exog = k_ar_diff, case, r, exog
        self.names = names or [f"y{i}" for i in range(self.n)]
        self.J = J = Johansen(self.y, k_ar_diff, case, exog)
        b = J.beta(r).copy()
        if norm_idx is not None:  # normalización sobre una variable (solo r=1)
            b = b / b[norm_idx, 0]
        self.beta = b                    # (n[+1]) x r
        ect = J.Z1 @ b
        X = np.hstack([ect, J.Z2])
        coef, *_ = linalg.lstsq(X, J.Z0)
        self.coef = coef
        self.alpha = coef[:r].T          # n x r
        self.G = coef[r:]                # coef de Z2
        self.resid = J.Z0 - X @ coef
        self.T = J.T
        npar = X.shape[1]
        self.sigma_ml = self.resid.T @ self.resid / self.T
        self.sigma = self.resid.T @ self.resid / (self.T - npar)
        XtXi = linalg.inv(X.T @ X)
        self.se_coef = np.sqrt(np.outer(np.diag(XtXi), np.diag(self.sigma)))
        self.se_alpha = self.se_coef[:r].T
        self.t_alpha = self.alpha / self.se_alpha
        self.p_alpha = 2 * (1 - stats.norm.cdf(np.abs(self.t_alpha)))
        self.X = X
        # Γ_i
        n, k = self.n, self.k
        self.Gamma = [self.G[i * n:(i + 1) * n].T for i in range(k)]

    # ----- representación VAR en niveles -----
    def var_rep(self):
        n, k = self.n, self.k
        Pi = self.alpha @ self.beta[:n].T
        A = []
        G = self.Gamma
        if k == 0:
            return [np.eye(n) + Pi]
        A.append(np.eye(n) + Pi + G[0])
        for i in range(1, k):
            A.append(G[i] - G[i - 1])
        A.append(-G[k - 1])
        return A

    def ma_rep(self, H=20):
        A = self.var_rep()
        p = len(A)
        n = self.n
        Phi = [np.eye(n)]
        for h in range(1, H + 1):
            M = np.zeros((n, n))
            for j in range(1, min(h, p) + 1):
                M += A[j - 1] @ Phi[h - j]
            Phi.append(M)
        return np.array(Phi)

    def roots(self):
        A = self.var_rep()
        n, p = self.n, len(A)
        C = np.zeros((n * p, n * p))
        C[:n] = np.hstack(A)
        if p > 1:
            C[n:, :-n] = np.eye(n * (p - 1))
        return np.sort(np.abs(linalg.eigvals(C)))[::-1]

    # ----- IRF / FEVD -----
    def orth_irf(self, H=20, order=None, sigma=None):
        S = self.sigma_ml if sigma is None else sigma
        Phi = self.ma_rep(H)
        n = self.n
        order = list(range(n)) if order is None else list(order)
        Pm = np.eye(n)[order]           # permutación
        Sp = Pm @ S @ Pm.T
        Lp = linalg.cholesky(Sp, lower=True)
        L = Pm.T @ Lp                   # impacto en orden original; columnas = shocks en orden 'order'
        # Reordenar columnas para que shock j corresponda a la variable j
        Lc = np.zeros_like(L)
        for pos, var in enumerate(order):
            Lc[:, var] = L[:, pos]
        return np.einsum("hij,jk->hik", Phi, Lc)

    def fevd(self, H=20, order=None):
        th = self.orth_irf(H - 1, order)
        cum = np.cumsum(th ** 2, axis=0)
        return cum / cum.sum(axis=2, keepdims=True)  # [h-1, resp, shock]

    def girf(self, H=20):
        S = self.sigma_ml
        Phi = self.ma_rep(H)
        return np.einsum("hij,jk->hik", Phi, S) / np.sqrt(np.diag(S))[None, None, :]

    def gfevd(self, H=20):
        S = self.sigma_ml
        Phi = self.ma_rep(H - 1)
        num = np.cumsum(np.einsum("hij,jk->hik", Phi, S) ** 2, axis=0) / np.diag(S)[None, None, :]
        den = np.cumsum(np.einsum("hij,jk,hlk->hil", Phi, S, Phi), axis=0)
        den = np.array([np.diag(d) for d in den])[:, :, None]
        g = num / den
        return g / g.sum(axis=2, keepdims=True)  # normalizado (Diebold-Yilmaz)

    # ----- simulación para bootstrap -----
    def simulate(self, eps):
        y = self.y.copy()
        n, k, case = self.n, self.k, self.case
        T = self.T
        dy = list(np.diff(y[:k + 1], axis=0))
        ex = None
        if self.exog is not None:
            ex = np.asarray(self.exog, float)
            ex = ex[:, None] if ex.ndim == 1 else ex
            ex = ex[-T:]
        for t in range(T):
            tt = t + k + 1
            ylag = y[tt - 1]
            z1 = ylag
            tr = float(k + 1 + t)
            if case == 2:
                z1 = np.append(ylag, 1.0)
            elif case == 4:
                z1 = np.append(ylag, tr)
            z2 = []
            for i in range(k):
                z2.extend(dy[-i - 1])
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


def lr_beta_restriction(J: Johansen, H: np.ndarray, r=1):
    """H0: β = H φ. Devuelve (LR, df, p)."""
    S00, S01, S11 = J.S00, J.S01, J.S11
    S10 = S01.T
    M = H.T @ S10 @ linalg.solve(S00, S01) @ H
    lam = np.sort(linalg.eigh(M, H.T @ S11 @ H, eigvals_only=True))[::-1][:r]
    lam = np.clip(lam, 0, 1 - 1e-12)
    LR = J.T * np.sum(np.log((1 - lam) / (1 - J.eig[:r])))
    df = r * (H.shape[0] - H.shape[1])
    return LR, df, 1 - stats.chi2.cdf(LR, df)


def lr_weak_exog(J: Johansen, idx, r=1):
    """H0: α_j = 0 para j en idx (exogeneidad débil respecto a β)."""
    n = J.n
    idx = list(np.atleast_1d(idx))
    keep = [i for i in range(n) if i not in idx]
    R0, R1 = J.R0, J.R1
    Ra, Rb = R0[:, keep], R0[:, idx]
    Pb = Rb @ linalg.lstsq(Rb, np.hstack([Ra, R1]))[0]
    E = np.hstack([Ra, R1]) - Pb
    Ea, E1 = E[:, :len(keep)], E[:, len(keep):]
    T = J.T
    Saa, Sa1, S11 = Ea.T @ Ea / T, Ea.T @ E1 / T, E1.T @ E1 / T
    M = Sa1.T @ linalg.solve(Saa, Sa1)
    lam = np.sort(linalg.eigh(M, S11, eigvals_only=True))[::-1][:r]
    lam = np.clip(lam, 0, 1 - 1e-12)
    LR = T * np.sum(np.log((1 - lam) / (1 - J.eig[:r])))
    df = r * len(idx)
    return LR, df, 1 - stats.chi2.cdf(LR, df)


def lm_autocorr(fit: VECMfit, h=1):
    """Contraste LM multivariante de autocorrelación (Breusch-Godfrey) con
    aproximación F de Edgerton-Shukur (Rao)."""
    u = fit.resid
    T, K = u.shape
    X = fit.X
    lags = [np.vstack([np.zeros((i, K)), u[:-i]]) for i in range(1, h + 1)]
    Z = np.hstack([X] + lags)
    e = u - Z @ linalg.lstsq(Z, u)[0]
    Su = u.T @ u / T
    Se = e.T @ e / T
    LM = T * (K - np.trace(linalg.solve(Su, Se)))
    df = h * K * K
    p_chi = 1 - stats.chi2.cdf(LM, df)
    # Rao F
    m = K * h
    q = 0.5 * K * m - 1
    nx = X.shape[1]
    N = T - nx - m - 0.5 * (K - m + 1)
    s = np.sqrt((K ** 2 * m ** 2 - 4) / (K ** 2 + m ** 2 - 5)) if (K ** 2 + m ** 2 - 5) > 0 else 1
    ratio = (linalg.det(Su) / linalg.det(Se)) ** (1 / s)
    F = (ratio - 1) * (N * s - q) / (K * m)
    p_F = 1 - stats.f.cdf(F, K * m, N * s - q)
    return LM, df, p_chi, F, p_F


def arch_lm(u, lags=4):
    from statsmodels.stats.diagnostic import het_arch
    return [het_arch(u[:, j], nlags=lags)[1] for j in range(u.shape[1])]


def normality_dh(u):
    """Jarque-Bera univariante por ecuación y Lütkepohl multivariante (residuos estandarizados por Cholesky)."""
    T, K = u.shape
    uc = u - u.mean(0)
    S = uc.T @ uc / T
    P = linalg.cholesky(S, lower=True)
    w = linalg.solve(P, uc.T).T
    b1 = (w ** 3).mean(0)
    b2 = (w ** 4).mean(0)
    l1 = T * b1 @ b1 / 6
    l2 = T * (b2 - 3) @ (b2 - 3) / 24
    lam = l1 + l2
    p = 1 - stats.chi2.cdf(lam, 2 * K)
    jb_eq = [stats.jarque_bera(u[:, j]).pvalue for j in range(K)]
    return lam, p, jb_eq


def permutation_fevd(fit: VECMfit, resp_idx, H=20):
    out = []
    for order in itertools.permutations(range(fit.n)):
        fv = fit.fevd(H, order)[H - 1, resp_idx, :]
        out.append((order, fv))
    return out


def bootstrap_irf(fit: VECMfit, B=299, H=20, resp_idx=0, order=None, seed=7, norm_idx=None):
    rng = np.random.default_rng(seed)
    u = fit.resid - fit.resid.mean(0)
    T = fit.T
    irfs, fevds, girfs, betas = [], [], [], []
    for _ in range(B):
        idx = rng.integers(0, T, T)
        ys = fit.simulate(u[idx])
        try:
            fb = VECMfit(ys, fit.k, fit.case, fit.exog, fit.r, norm_idx=norm_idx)
        except Exception:
            continue
        irfs.append(fb.orth_irf(H, order)[:, resp_idx, :])
        fevds.append(fb.fevd(H, order)[H - 1, resp_idx, :])
        girfs.append(fb.girf(H)[:, resp_idx, :])
        betas.append(fb.beta[:fit.n, 0])
    return np.array(irfs), np.array(fevds), np.array(girfs), np.array(betas)
