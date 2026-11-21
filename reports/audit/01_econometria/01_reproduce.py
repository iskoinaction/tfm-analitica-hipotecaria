"""Paso 1: reproducción literal de las cifras documentadas (notebooks 4 y 4.2, app)."""
import json
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen

from common import OUT, build_original, load_panel

warnings.filterwarnings("ignore")
res = {}

Y = build_original()
V = list(Y.columns)
hip = V.index("Log_Hipotecas")
res["muestra"] = [str(Y.index[0].date()), str(Y.index[-1].date()), len(Y)]

# ---------------- VECM 4.2 ----------------
fit = VECM(Y, k_ar_diff=1, coint_rank=1, deterministic="co").fit()
b = fit.beta[:, 0]
bn = b / b[hip]
res["beta_norm (beta'Y=0, normalizado hip=1)"] = dict(zip(V, np.round(bn, 4)))
res["ecuacion_LP (log H = ...)"] = {v: round(-bn[i], 4) for i, v in enumerate(V) if i != hip}
a = fit.alpha[:, 0]
res["alpha"] = dict(zip(V, np.round(a, 4)))
res["alpha_p"] = dict(zip(V, np.round(fit.pvalues_alpha[:, 0], 4)))
res["alpha_reescalada_a_beta_norm"] = dict(zip(V, np.round(a * b[hip], 4)))
res["semivida_trim"] = dict(zip(V, np.round(np.log(.5) / np.log(1 + a * b[hip]), 1)))

# ECT tal y como lo calcula el notebook (sin constante) y su ADF
ect = Y.values @ b
st, p, *_ = adfuller(ect, maxlag=4, autolag="AIC")
res["ADF_ECT_notebook"] = [round(st, 3), round(p, 4)]

# IRF ortogonal
irf = fit.irf(20).orth_irfs
res["IRF_orth_nivel_h20_sobre_hip"] = dict(zip(V, np.round(irf[20, hip, :], 4)))
res["IRF_orth_suma_acum_h20 (lo que imprime el nb)"] = dict(zip(V, np.round(irf[:21, hip, :].sum(0), 4)))
res["IRF_orth_nivel_h1..h20 precio"] = np.round(irf[1:21, hip, V.index("Log_Precio_m2")], 3).tolist()
res["IRF_orth_nivel_h1..h20 materiales"] = np.round(irf[1:21, hip, V.index("Log_Materiales")], 3).tolist()

# FEVD manual (código del notebook)
ma = fit.orth_ma_rep(maxn=20)
cum = np.cumsum(ma ** 2, axis=0)
fevd = cum / cum.sum(axis=2, keepdims=True)
res["FEVD_hip_h20 (indice 19 del nb)"] = dict(zip(V, np.round(fevd[19, hip, :] * 100, 1)))
res["FEVD_hip_h1"] = dict(zip(V, np.round(fevd[0, hip, :] * 100, 1)))

# Diagnósticos del notebook
w = fit.test_whiteness(nlags=8)
n = fit.test_normality()
res["Portmanteau_8"] = [round(w.test_statistic, 1), round(w.pvalue, 3)]
res["Normalidad_JB"] = [round(n.test_statistic, 1), round(n.pvalue, 4)]

# ---------------- Notebook 4 celda 45: Johansen + select_order --------------
YJ = Y[["Log_Hipotecas", "Log_PIB_pc", "Log_Precio_m2", "Euribor", "Log_Materiales"]]
sel = VAR(YJ).select_order(maxlags=6)
res["select_order_maxlags6"] = sel.selected_orders
j = coint_johansen(YJ, det_order=0, k_ar_diff=1)
res["Johansen_nb4_det0_k1"] = {
    "traza": np.round(j.lr1, 2).tolist(), "cv95_traza": np.round(j.cvt[:, 1], 2).tolist(),
    "maxeig": np.round(j.lr2, 2).tolist(), "cv95_maxeig": np.round(j.cvm[:, 1], 2).tolist()}

# Johansen 4 variables (celda 44, sin precio)
df = load_panel()
for c in ["tasa_ahorro", "Indice_Mano_Obra", "Indice_Materiales", "IPC", "PIB_pc", "Pob_Ext"]:
    df[c] = df.groupby("Provincia")[c].transform(lambda x: x.ffill().bfill())
nac = df.groupby("Trimestre").agg({"Hipotecas_Total": "sum", "PIB_pc": "mean",
                                   "Euribor": "mean", "Indice_Materiales": "mean"})
Y4 = pd.DataFrame({"h": np.log(nac.Hipotecas_Total), "y": np.log(nac.PIB_pc),
                   "e": nac.Euribor, "m": np.log(nac.Indice_Materiales)})
j4 = coint_johansen(Y4, det_order=0, k_ar_diff=1)
res["Johansen_nb4_celda44_4vars"] = {"traza": np.round(j4.lr1, 2).tolist(),
                                     "cv95": np.round(j4.cvt[:, 1], 2).tolist()}

# ---------------- Notebook 4 celda 49: VAR mixto y FEVD ----------------------
df = load_panel()
cf = ["tasa_ahorro", "Indice_Mano_Obra", "Indice_Materiales", "IPC", "PIB_pc"]
df[cf] = df.groupby("Provincia")[cf].ffill().bfill()   # (bfill NO agrupado: réplica literal)
df = df.dropna().reset_index(drop=True)
nac = df.groupby("Trimestre").agg({"Hipotecas_Total": "sum", "Euribor": "mean",
                                   "Precio_m2": "mean", "Tasa_Paro": "mean", "PIB_pc": "mean"})
dv = pd.DataFrame(index=nac.index)
dv["Crec_PIB"] = np.log(nac.PIB_pc).diff()
dv["Tasa_Paro"] = nac.Tasa_Paro
dv["Log_Precio_m2"] = np.log(nac.Precio_m2)
dv["Shock_Euribor"] = nac.Euribor.diff()
dv["Crec_Hipotecas"] = np.log(nac.Hipotecas_Total).diff()
dv = dv.dropna()
rv = VAR(dv).fit(4)
fe = rv.fevd(12).decomp[dv.columns.get_loc("Crec_Hipotecas")]
res["VAR_nb4_celda49_FEVD_CrecHip_h12"] = dict(zip(dv.columns, np.round(fe[-1] * 100, 1)))
res["VAR_nb4_celda49_FEVD_CrecHip_h4"] = dict(zip(dv.columns, np.round(fe[3] * 100, 1)))
res["VAR_nb4_celda49_obs"] = len(dv)
res["VAR_nb4_celda49_estable"] = bool(rv.is_stable())
res["VAR_nb4_celda49_raiz_max_modulo"] = round(float(np.max(np.abs(1 / rv.roots))), 4)

# VAR 4 variables en diferencias (descrito en la app: Δlog H, Δlog P, ΔE, Δlog PIB)
Yd = Y[["Log_Hipotecas", "Log_Precio_m2", "Euribor", "Log_PIB_pc"]].diff().dropna()
for p in (1, 2, 4):
    r4 = VAR(Yd).fit(p)
    f4 = r4.fevd(12).decomp[0][-1] * 100
    res[f"VAR4_diff_p{p}_FEVD_dlogH_h12"] = dict(zip(Yd.columns, np.round(f4, 1)))

with open(OUT / "01_reproduce.json", "w") as f:
    json.dump(res, f, indent=1, default=str, ensure_ascii=False)
for k, v in res.items():
    print(k, "->", v)
