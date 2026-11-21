"""Econometría de panel (provincias × trimestres).

* CD de Pesaran (2015) y CIPS de Pesaran (2007) con valores críticos simulados.
* Efectos fijos con errores Driscoll-Kraay (linearmodels, kernel Bartlett).
* MG y PMG (Pesaran, Shin & Smith 1999) para un ARDL(1,1) en forma ECM, con datos brutos
  o centrados transversalmente (control simple de factores comunes); Hausman MG vs PMG.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import optimize, stats


def wide(df: pd.DataFrame, col: str) -> pd.DataFrame:
    return df.pivot(index="period", columns="prov_code", values=col).sort_index()


def cd_test(W: pd.DataFrame) -> dict:
    X = W.dropna(how="all").values
    T, N = X.shape
    Cm = pd.DataFrame(X).corr().values
    iu = np.triu_indices(N, 1)
    cd = float(np.sqrt(2 * T / (N * (N - 1))) * np.nansum(Cm[iu]))
    return {"CD": cd, "p": float(2 * (1 - stats.norm.cdf(abs(cd)))), "rho_medio": float(np.nanmean(Cm[iu]))}


def _cadf_t(y, ybar, trend=False):
    dy, dyb = np.diff(y), np.diff(ybar)
    Y = dy[1:]
    X = [np.ones(len(Y)), y[1:-1], ybar[1:-1], dyb[1:], dy[:-1], dyb[:-1]]
    if trend:
        X.append(np.arange(len(Y)))
    X = np.column_stack(X)
    b, *_ = np.linalg.lstsq(X, Y, rcond=None)
    e = Y - X @ b
    se = np.sqrt(e @ e / (len(Y) - X.shape[1]) * np.linalg.inv(X.T @ X)[1, 1])
    return np.clip(b[1] / se, -7.0 if trend else -6.42, 1.70 if trend else 2.61)


def cips(M: np.ndarray, trend=False) -> float:
    ybar = M.mean(1)
    return float(np.mean([_cadf_t(M[:, i], ybar, trend) for i in range(M.shape[1])]))


def cips_critical(T, N, reps=300, seed=0):
    rng = np.random.default_rng(seed)
    out = {}
    for tr in (False, True):
        sims = [cips(np.cumsum(rng.standard_normal((T, N)), 0), tr) for _ in range(reps)]
        out["ct" if tr else "c"] = np.percentile(sims, [1, 5, 10]).tolist()
    return out


def fe_driscoll_kraay(df: pd.DataFrame, y: str, xs: list[str], seasonal=True, diff=False, bandwidth=4) -> dict:
    from linearmodels.panel import PanelOLS
    d = df.set_index(["prov_code", "period"]).sort_index()[[y] + xs].copy()
    d.index = d.index.set_levels(d.index.levels[1].to_timestamp(), level=1)
    if diff:
        d = d.groupby(level=0).diff()
    if seasonal:
        q = d.index.get_level_values(1).quarter
        for k in (2, 3, 4):
            d[f"Q{k}"] = (q == k).astype(float)
    d = d.dropna()
    X = d[[c for c in d.columns if c != y]]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        m = PanelOLS(d[y], X, entity_effects=True).fit(cov_type="kernel", kernel="bartlett", bandwidth=bandwidth)
    out = {x: {"coef": float(m.params[x]), "se_DK": float(m.std_errors[x]), "p": float(m.pvalues[x])} for x in xs}
    res = m.resids.unstack(0)
    return {"coef": out, "nobs": int(m.nobs), "CD_residuos": cd_test(res), "diferencias": diff}


def _unit(Wy, WX, i, demean):
    y = Wy.iloc[:, i].values.copy()
    X = np.column_stack([w.iloc[:, i].values for w in WX])
    if demean:
        y = y - Wy.values.mean(1)
        X = X - np.column_stack([w.values.mean(1) for w in WX])
    q = np.asarray(Wy.index.quarter)
    dy, dX = np.diff(y), np.diff(X, axis=0)
    Y = dy[1:]
    S = np.column_stack([(q[2:] == k).astype(float) for k in (2, 3, 4)])
    W = np.column_stack([np.ones(len(Y)), dX[1:], dy[:-1], S])
    return Y, y[1:-1], X[1:-1], W


def mg_pmg(df: pd.DataFrame, y: str, xs: list[str], demean: bool) -> dict:
    Wy = wide(df, y)
    WX = [wide(df, x).reindex(columns=Wy.columns) for x in xs]
    N = Wy.shape[1]
    data = [_unit(Wy, WX, i, demean) for i in range(N)]
    th, ph = [], []
    for Y, yl, Xl, W in data:
        Z = np.column_stack([yl, Xl, W])
        b, *_ = np.linalg.lstsq(Z, Y, rcond=None)
        ph.append(b[0]); th.append(-b[1:1 + len(xs)] / b[0])
    th = np.array(th)
    mg_mean, mg_se = th.mean(0), th.std(0, ddof=1) / np.sqrt(N)

    def negll(theta):
        ll = 0.0
        for Y, yl, Xl, W in data:
            Z = np.column_stack([yl - Xl @ theta, W])
            b, *_ = np.linalg.lstsq(Z, Y, rcond=None)
            e = Y - Z @ b
            ll += -len(Y) / 2 * np.log(e @ e / len(Y))
        return -ll

    t0 = np.clip(np.median(th, 0), -5, 5)
    nm = optimize.minimize(negll, t0, method="Nelder-Mead", options={"xatol": 1e-7, "fatol": 1e-8, "maxiter": 4000})
    opt = optimize.minimize(negll, nm.x, method="BFGS")
    t = opt.x if opt.fun <= nm.fun else nm.x
    gnorm = float(np.max(np.abs(optimize.approx_fprime(t, negll, 1e-6))))
    k, h = len(t), 1e-4
    Hm = np.zeros((k, k))
    for a in range(k):
        for b_ in range(k):
            ea, eb = np.eye(k)[a] * h, np.eye(k)[b_] * h
            Hm[a, b_] = (negll(t + ea + eb) - negll(t + ea - eb) - negll(t - ea + eb) + negll(t - ea - eb)) / (4 * h * h)
    se = np.sqrt(np.diag(np.linalg.inv(Hm)))
    phis = []
    for Y, yl, Xl, W in data:
        b, *_ = np.linalg.lstsq(np.column_stack([yl - Xl @ t, W]), Y, rcond=None)
        phis.append(b[0])
    phis = np.array(phis)
    d = t - mg_mean
    Vd = np.diag(mg_se ** 2 - se ** 2)
    hs = float(d @ np.linalg.pinv(Vd) @ d)
    hp = float(1 - stats.chi2.cdf(hs, len(xs))) if hs >= 0 else None
    if hs < 0:
        hs = None  # Var(MG) - Var(PMG) no semidefinida positiva: contraste no definido
    return {"variables": xs, "demeaned": demean, "N": N, "T": int(Wy.shape[0]),
            "MG": {x: {"coef": float(a), "se": float(s)} for x, a, s in zip(xs, mg_mean, mg_se)},
            "MG_phi_medio": float(np.mean(ph)),
            "PMG": {x: {"coef": float(a), "se": float(s)} for x, a, s in zip(xs, t, se)},
            "PMG_phi_medio": float(phis.mean()), "PMG_phi_se": float(phis.std(ddof=1) / np.sqrt(N)),
            "PMG_phi_negativos": int((phis < 0).sum()), "PMG_gradiente_max": gnorm, "PMG_converge": bool(gnorm < 5e-2),
            "Hausman_MG_vs_PMG": {"stat": hs, "df": len(xs), "p": hp}}
