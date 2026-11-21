"""Paso 6 (exploratorio): econometría de panel con 52 provincias, 2005Q1-2024Q4.

* CD de Pesaran (2015) — dependencia transversal.
* CIPS de Pesaran (2007) con valores críticos simulados (N=52, T=80).
* FE con errores Driscoll-Kraay (linearmodels) en niveles y en diferencias.
* MG y PMG (Pesaran, Shin & Smith 1999) para un ARDL(1,1) en forma ECM,
  con datos brutos y con datos demeaned transversalmente (control simple de factores comunes).
* Contraste tipo Westerlund (2007) Gt (media de t de φ_i) con nulo simulado.
"""
import json
import warnings

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS
from scipy import optimize, stats

from common import OUT, load_panel

warnings.filterwarnings("ignore")
rng = np.random.default_rng(99)
res = {}

df = load_panel()
df = df[df.Trimestre <= "2024-10-01"].copy()
df["lh"] = np.log(df.Hipotecas_Total)
df["lp"] = np.log(df.Precio_m2)
df["ly"] = np.log(df.PIB_pc)
df["lm"] = np.log(df.Indice_Materiales)
df["eu"] = df.Euribor
df["q"] = df.Trimestre.dt.quarter
assert df[["lh", "lp", "ly", "lm", "eu"]].notna().all().all()
provs = sorted(df.Provincia.unique())
N, T = len(provs), df.Trimestre.nunique()
res["N_T"] = [N, T]
wide = {v: df.pivot(index="Trimestre", columns="Provincia", values=v)[provs] for v in ["lh", "lp", "ly", "lm", "eu"]}


# ---------------- CD test ----------------
def cd_test(W):
    W = W.dropna(how="all")
    X = W.values
    Tn, Nn = X.shape
    C = pd.DataFrame(X).corr().values
    iu = np.triu_indices(Nn, 1)
    cd = np.sqrt(2 * Tn / (Nn * (Nn - 1))) * C[iu].sum()
    return cd, 2 * (1 - stats.norm.cdf(abs(cd))), C[iu].mean()


for v in ("lh", "lp"):
    d = wide[v].diff()
    cd, p, rho = cd_test(d)
    res[f"CD_Pesaran_D{v}"] = [round(cd, 2), p, round(rho, 3)]


# ---------------- CIPS ----------------
def cadf_t(y, ybar, trend=False):
    dy = np.diff(y); dyb = np.diff(ybar)
    Y = dy[1:]
    X = [np.ones(len(Y)), y[1:-1], ybar[1:-1], dyb[1:], dy[:-1], dyb[:-1]]
    if trend:
        X.append(np.arange(len(Y)))
    X = np.column_stack(X)
    b, *_ = np.linalg.lstsq(X, Y, rcond=None)
    e = Y - X @ b
    s2 = e @ e / (len(Y) - X.shape[1])
    se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    return np.clip(b[1] / se, -6.42 if not trend else -7.0, 2.61 if not trend else 1.70)


def cips(M, trend=False):
    ybar = M.mean(1)
    return np.mean([cadf_t(M[:, i], ybar, trend) for i in range(M.shape[1])])


cv = {}
for trend in (False, True):
    sims = [cips(np.cumsum(rng.standard_normal((T, N)), 0), trend) for _ in range(300)]
    cv[trend] = np.percentile(sims, [1, 5, 10])
res["CIPS_cv_simulados_(1,5,10%)"] = {"c": np.round(cv[False], 3).tolist(), "ct": np.round(cv[True], 3).tolist()}
for v in ("lh", "lp", "ly"):
    M = wide[v].values
    res[f"CIPS_{v}"] = {"nivel_c": round(cips(M), 3), "nivel_ct": round(cips(M, True), 3),
                        "dif_c": round(cips(np.diff(M, axis=0)), 3)}

# ---------------- FE Driscoll-Kraay ----------------
pdf = df.set_index(["Provincia", "Trimestre"]).sort_index()
pdf = pdf.join(pd.get_dummies(pdf.q, prefix="Q", drop_first=True).astype(float))
X = pdf[["lp", "ly", "eu", "lm", "Q_2", "Q_3", "Q_4"]]
fe = PanelOLS(pdf.lh, X, entity_effects=True).fit(cov_type="kernel", kernel="bartlett", bandwidth=4)
res["FE_niveles_DK"] = {k: [round(fe.params[k], 4), round(fe.std_errors[k], 4), round(fe.pvalues[k], 4)] for k in ["lp", "ly", "eu", "lm"]}
fe_cl = PanelOLS(pdf.lh, X, entity_effects=True).fit(cov_type="clustered", cluster_entity=True)
res["FE_niveles_cluster_prov_SE"] = {k: round(fe_cl.std_errors[k], 4) for k in ["lp", "ly", "eu", "lm"]}
cd_fe, p_fe, rho_fe = cd_test(fe.resids.unstack(0))
res["CD_residuos_FE"] = [round(cd_fe, 2), p_fe, round(rho_fe, 3)]
# primeras diferencias
g = pdf.groupby(level=0)
D = pd.DataFrame({c: g[c].diff() for c in ["lh", "lp", "ly", "eu", "lm"]}).join(pdf[["Q_2", "Q_3", "Q_4"]]).dropna()
fd = PanelOLS(D.lh, D[["lp", "ly", "eu", "lm", "Q_2", "Q_3", "Q_4"]], entity_effects=True).fit(cov_type="kernel", kernel="bartlett", bandwidth=4)
res["FE_primeras_dif_DK"] = {k: [round(fd.params[k], 4), round(fd.std_errors[k], 4), round(fd.pvalues[k], 4)] for k in ["lp", "ly", "eu", "lm"]}


# ---------------- MG / PMG ----------------
def unit_data(i, xs, demean):
    y = wide["lh"].iloc[:, i].values.copy()
    X = np.column_stack([wide[v].iloc[:, i].values for v in xs])
    if demean:
        y = y - wide["lh"].values.mean(1)
        X = X - np.column_stack([wide[v].values.mean(1) for v in xs])
    q = wide["lh"].index.quarter.values
    dy = np.diff(y); dX = np.diff(X, axis=0)
    Yt = dy[1:]
    ylag = y[1:-1]; Xlag = X[1:-1]
    S = np.column_stack([(q[2:] == k).astype(float) for k in (2, 3, 4)])
    W = np.column_stack([np.ones(len(Yt)), dX[1:], dy[:-1], S])  # Δx_t, Δy_{t-1}, estacionales
    return Yt, ylag, Xlag, W


def mg(xs, demean):
    th, ph, tph = [], [], []
    for i in range(N):
        Y, yl, Xl, W = unit_data(i, xs, demean)
        Z = np.column_stack([yl, Xl, W])
        b, *_ = np.linalg.lstsq(Z, Y, rcond=None)
        e = Y - Z @ b
        s2 = e @ e / (len(Y) - Z.shape[1])
        se_phi = np.sqrt(s2 * np.linalg.inv(Z.T @ Z)[0, 0])
        ph.append(b[0]); tph.append(b[0] / se_phi)
        th.append(-b[1:1 + len(xs)] / b[0])
    th = np.array(th)
    med = np.median(th, 0)
    return th.mean(0), th.std(0, ddof=1) / np.sqrt(N), med, np.array(ph), np.array(tph)


def pmg(xs, demean, theta0):
    data = [unit_data(i, xs, demean) for i in range(N)]

    def negll(theta):
        ll = 0
        for Y, yl, Xl, W in data:
            ect = yl - Xl @ theta
            Z = np.column_stack([ect, W])
            b, *_ = np.linalg.lstsq(Z, Y, rcond=None)
            e = Y - Z @ b
            ll += -len(Y) / 2 * np.log(e @ e / len(Y))
        return -ll

    opt = optimize.minimize(negll, theta0, method="BFGS")
    th = opt.x
    # SE por hessiano numérico del log-lik concentrado
    k = len(th); h = 1e-4; Hm = np.zeros((k, k))
    for a in range(k):
        for b_ in range(k):
            ea = np.eye(k)[a] * h; eb = np.eye(k)[b_] * h
            Hm[a, b_] = (negll(th + ea + eb) - negll(th + ea - eb) - negll(th - ea + eb) + negll(th - ea - eb)) / (4 * h * h)
    se = np.sqrt(np.diag(np.linalg.inv(Hm)))
    phis = []
    for Y, yl, Xl, W in data:
        Z = np.column_stack([yl - Xl @ th, W])
        b, *_ = np.linalg.lstsq(Z, Y, rcond=None)
        phis.append(b[0])
    return th, se, np.array(phis)


for label, xs, demean in (("bruto[lp,ly,eu,lm]", ["lp", "ly", "eu", "lm"], False),
                          ("demeaned[lp,ly]", ["lp", "ly"], True)):
    m_mean, m_se, m_med, phi_i, tphi = mg(xs, demean)
    th, se, phis = pmg(xs, demean, np.clip(m_med, -5, 5))
    d = th - m_mean
    # Hausman (MG eficiente bajo H1; PMG bajo H0)
    Vm = np.diag(m_se ** 2); Vp = np.diag(se ** 2)
    Vd = Vm - Vp
    try:
        hs = float(d @ np.linalg.pinv(Vd) @ d)
        hp = 1 - stats.chi2.cdf(hs, len(xs))
    except Exception:
        hs, hp = np.nan, np.nan
    res[f"MG_{label}"] = {x: [round(a, 3), round(b, 3), round(c, 3)] for x, a, b, c in zip(xs, m_mean, m_se, m_med)}
    res[f"MG_{label}_phi_media"] = [round(phi_i.mean(), 3), round(phi_i.std(ddof=1) / np.sqrt(N), 3)]
    res[f"PMG_{label}"] = {x: [round(a, 3), round(b, 3)] for x, a, b in zip(xs, th, se)}
    res[f"PMG_{label}_phi_media"] = [round(phis.mean(), 3), round(phis.std(ddof=1) / np.sqrt(N), 3), int((phis < 0).sum())]
    res[f"Hausman_MG_vs_PMG_{label}"] = [round(hs, 2), round(hp, 4)]
    # Westerlund-type Gt = media de t(φ_i); nulo simulado (paseos aleatorios independientes)
    Gt = tphi.mean()
    sims = []
    for _ in range(199):
        ys = np.cumsum(rng.standard_normal((T, N)), 0)
        xs_sim = [np.cumsum(rng.standard_normal((T, N)), 0) for _ in xs]
        tt = []
        for i in range(N):
            y = ys[:, i]; Xm = np.column_stack([x[:, i] for x in xs_sim])
            dy = np.diff(y); dX = np.diff(Xm, axis=0)
            Y = dy[1:]
            Z = np.column_stack([y[1:-1], Xm[1:-1], np.ones(len(Y)), dX[1:], dy[:-1]])
            b, *_ = np.linalg.lstsq(Z, Y, rcond=None)
            e = Y - Z @ b
            s2 = e @ e / (len(Y) - Z.shape[1])
            tt.append(b[0] / np.sqrt(s2 * np.linalg.inv(Z.T @ Z)[0, 0]))
        sims.append(np.mean(tt))
    res[f"Westerlund_Gt_{label}"] = {"Gt": round(Gt, 3), "cv_sim_1_5_10": np.round(np.percentile(sims, [1, 5, 10]), 3).tolist(),
                                     "p_sim": float(np.mean(np.array(sims) <= Gt))}
    print(label, "done", flush=True)

with open(OUT / "06_panel.json", "w") as f:
    json.dump(res, f, indent=1, default=float, ensure_ascii=False)
for k, v in res.items():
    print(k, "->", v)
