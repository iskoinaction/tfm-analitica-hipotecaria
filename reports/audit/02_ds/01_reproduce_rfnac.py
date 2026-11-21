"""Reproducción del benchmark de demanda del notebook 4 (celdas 7-20) y pruebas de leakage.

Salida: reports/audit/02_ds/out/01_reproduce_rfnac.json (+ impresión por consola)
Uso: python reports/audit/02_ds/01_reproduce_rfnac.py
"""
import json
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import ElasticNetCV
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import lightgbm as lgb

from common import load_raw, build_panel, features_ml, build_national, mape, rmse, mae, OUT

warnings.filterwarnings("ignore")
NJ = 2
res = {}

raw = load_raw()

# ----------------------------------------------------------------------------- A. réplica exacta
panel = build_panel(raw, accesibilidad_contemporanea=True)
F = features_ml(panel)
qs = sorted(panel["Trimestre"].unique())
test_start = qs[-8]
tr, te = panel[panel["Trimestre"] < test_start], panel[panel["Trimestre"] >= test_start]
res["panel_rows"] = int(len(panel))
res["n_features_prov"] = len(F)
res["prov_train_range"] = [str(tr["Trimestre"].min().date()), str(tr["Trimestre"].max().date())]
res["prov_test_range"] = [str(te["Trimestre"].min().date()), str(te["Trimestre"].max().date())]

# Modelos provinciales (hiperparámetros del notebook; n_jobs limitado)
prov_models = {
    "RF": RandomForestRegressor(n_estimators=300, max_depth=15, min_samples_leaf=5, max_features="sqrt", random_state=42, n_jobs=NJ),
    "XGB": xgb.XGBRegressor(n_estimators=500, learning_rate=0.05, max_depth=6, subsample=0.8, colsample_bytree=0.7,
                            reg_alpha=0.1, reg_lambda=1.0, random_state=42, verbosity=0, n_jobs=NJ),
    "LGBM": lgb.LGBMRegressor(n_estimators=500, learning_rate=0.05, max_depth=7, num_leaves=31, subsample=0.8,
                              colsample_bytree=0.7, reg_alpha=0.1, reg_lambda=1.0, random_state=42, verbose=-1, n_jobs=NJ),
    "GBM": GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=5, subsample=0.8, random_state=42),
}
prov = {}
for name, m in prov_models.items():
    m.fit(tr[F], tr["Hipotecas_Total"])
    p = m.predict(te[F])
    agg = pd.DataFrame({"T": te["Trimestre"].values, "y": te["Hipotecas_Total"].values, "p": p}).groupby("T").sum()
    prov[name] = {"MAPE_prov": mape(te["Hipotecas_Total"], p), "MAPE_nac_agregado": mape(agg["y"], agg["p"])}
sc = StandardScaler().fit(tr[F])
en = ElasticNetCV(l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.99], cv=5, random_state=42, max_iter=5000, n_jobs=NJ)
en.fit(sc.transform(tr[F]), tr["Hipotecas_Total"])
p = en.predict(sc.transform(te[F]))
agg = pd.DataFrame({"T": te["Trimestre"].values, "y": te["Hipotecas_Total"].values, "p": p}).groupby("T").sum()
prov["ElasticNet"] = {"MAPE_prov": mape(te["Hipotecas_Total"], p), "MAPE_nac_agregado": mape(agg["y"], agg["p"])}
# Theil U2 tal como lo calcula el notebook (naive = último valor del train repetido 8 trimestres)
last_tr = tr.groupby("Provincia")["Hipotecas_Total"].last()
naive_nb = te["Provincia"].map(last_tr).values
# Naive "justo" (1 paso, mismo conjunto de información que los modelos): y_{t-1}
naive_1 = te["Hipotecas_Total_lag1"].values
prov["_naive_multistep_notebook"] = {"MAPE_prov": mape(te["Hipotecas_Total"], naive_nb)}
prov["_naive_1paso_y_t-1"] = {"MAPE_prov": mape(te["Hipotecas_Total"], naive_1)}
prov["_snaive_1paso_y_t-4"] = {"MAPE_prov": mape(te["Hipotecas_Total"], te["Hipotecas_Total_lag4"].values)}
res["provincial"] = prov

# SARIMAX nacional (celda 17)
dn = panel.groupby("Trimestre").agg({"Hipotecas_Total": "sum", "Euribor": "mean", "Spread_Hipotecas_lag1": "mean",
                                    "Tasa_Paro_lag1": "mean"}).sort_index()
dn.index = pd.DatetimeIndex(dn.index, freq="QS-JAN")
ylog = np.log(dn["Hipotecas_Total"])
X = dn[["Euribor", "Spread_Hipotecas_lag1", "Tasa_Paro_lag1"]]
mod = sm.tsa.statespace.SARIMAX(ylog.iloc[:-8], exog=X.iloc[:-8], order=(1, 1, 1), seasonal_order=(1, 0, 0, 4),
                                enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
ps = np.exp(mod.get_forecast(8, exog=X.iloc[-8:]).predicted_mean)
res["SARIMAX_nac_MAPE"] = mape(np.exp(ylog.iloc[-8:]), ps)


# ----------------------------------------------------------------------------- B. RF_Nac (celdas 19-20)
def rfnac(panel_, seed=42, n_test=8):
    nac, Fn = build_national(panel_)
    Xtr, Xte = nac[Fn].iloc[:-n_test], nac[Fn].iloc[-n_test:]
    ytr, yte = nac["Hipotecas_Total"].iloc[:-n_test], nac["Hipotecas_Total"].iloc[-n_test:]
    m = RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_leaf=3, max_features="sqrt", random_state=seed, n_jobs=NJ)
    m.fit(Xtr, ytr)
    return nac, Fn, m, yte, m.predict(Xte)


nac, Fn, m_rf, yte, prf = rfnac(panel)
res["nac_rows"] = int(len(nac))
res["nac_n_features"] = len(Fn)
res["nac_features"] = Fn
res["nac_train_range"] = [str(nac.index[0].date()), str(nac.index[-9].date())]
res["nac_test_range"] = [str(nac.index[-8].date()), str(nac.index[-1].date())]
res["RF_Nac_MAPE_replica"] = mape(yte, prf)
res["RF_Nac_RMSE_replica"] = rmse(yte, prf)
res["RF_Nac_test_real"] = [float(v) for v in yte.values]
res["RF_Nac_test_pred"] = [float(v) for v in prf]
imp = pd.Series(m_rf.feature_importances_, index=Fn).sort_values(ascending=False)
res["RF_Nac_top10_importances"] = {k: round(float(v), 4) for k, v in imp.head(10).items()}

# Otros nacionales dedicados (celda 20)
Xtr, Xte = nac[Fn].iloc[:-8], nac[Fn].iloc[-8:]
ytr = nac["Hipotecas_Total"].iloc[:-8]
others = {
    "XGB_Nac": xgb.XGBRegressor(n_estimators=300, learning_rate=0.05, max_depth=4, subsample=0.8, colsample_bytree=0.7,
                                reg_alpha=1.0, reg_lambda=2.0, random_state=42, verbosity=0, n_jobs=NJ),
    "LGBM_Nac": lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, max_depth=5, num_leaves=15, subsample=0.8,
                                  colsample_bytree=0.7, reg_alpha=1.0, reg_lambda=2.0, random_state=42, verbose=-1, n_jobs=NJ),
}
for k, m in others.items():
    m.fit(Xtr, ytr)
    res[f"{k}_MAPE"] = mape(yte, m.predict(Xte))
scn = StandardScaler().fit(Xtr)
en = ElasticNetCV(l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.99], cv=3, random_state=42, max_iter=5000).fit(scn.transform(Xtr), ytr)
res["ElasticNet_Nac_MAPE"] = mape(yte, en.predict(scn.transform(Xte)))

# Benchmarks ingenuos sobre los MISMOS 8 trimestres (1 paso, información hasta t-1)
H = nac["Hipotecas_Total"]
full_H = raw.groupby("Trimestre")["Hipotecas_Total"].sum().sort_index()
idx = yte.index
naive1 = full_H.shift(1).loc[idx]
snaive = full_H.shift(4).loc[idx]
ma4 = full_H.shift(1).rolling(4).mean().loc[idx]
res["bench_same_test"] = {
    "naive_y(t-1)": mape(yte, naive1), "seasonal_naive_y(t-4)": mape(yte, snaive), "media_movil_4": mape(yte, ma4),
    "naive_multipaso_desde_2023Q4": mape(yte, np.repeat(full_H.loc[:idx[0]].iloc[-2], 8)),
}

# ----------------------------------------------------------------------------- C. sensibilidad a la semilla
seeds = list(range(50))
mp = []
for s in seeds:
    _, _, _, y_, p_ = rfnac(panel, seed=s)
    mp.append(mape(y_, p_))
mp = np.array(mp)
res["RF_Nac_seed_MAPE"] = {"min": float(mp.min()), "p25": float(np.percentile(mp, 25)), "median": float(np.median(mp)),
                           "p75": float(np.percentile(mp, 75)), "max": float(mp.max()),
                           "rank_seed42_pct": float((mp < mape(yte, prf)).mean() * 100)}

# ----------------------------------------------------------------------------- D. variantes de leakage
variants = {}
p_noacc = build_panel(raw, accesibilidad_contemporanea=False)
_, _, _, y_, p_ = rfnac(p_noacc)
variants["sin_Accesibilidad_contemporanea"] = mape(y_, p_)
p_noeur = build_panel(raw, accesibilidad_contemporanea=False, euribor_contemporaneo=False)
_, _, _, y_, p_ = rfnac(p_noeur)
variants["sin_Accesibilidad_ni_Euribor_contemporaneos"] = mape(y_, p_)
# media sobre semillas de cada variante
for nm, pnl in [("replica", panel), ("sin_acc", p_noacc), ("sin_acc_eur", p_noeur)]:
    v = [mape(*rfnac(pnl, seed=s)[3:5]) for s in range(20)]
    variants[f"{nm}_media_20_semillas"] = float(np.mean(v))
res["variantes_leakage"] = variants

# Cuántas features nacionales son contemporáneas (valor del trimestre objetivo)
contemp = [f for f in Fn if f in ("Euribor", "Euribor_change", "Euribor_x_Precio_nac", "Accesibilidad")]
res["features_nac_contemporaneas"] = contemp

# Comprobación: PIB_pc_lag1 en Q2-Q4 = PIB del año en curso (serie anual replicada)
r = raw.sort_values(["Provincia", "Trimestre"])
r["lag1"] = r.groupby("Provincia")["PIB_pc"].shift(1)
q = r["Trimestre"].dt.quarter
same = ((r["lag1"] == r["PIB_pc"]) | r["PIB_pc"].isna())[q.isin([2, 3, 4]) & r["lag1"].notna()]
res["PIB_pc_lag1_igual_PIB_mismo_anio_Q2Q4_pct"] = float(same.mean() * 100)

(OUT / "01_reproduce_rfnac.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
print(json.dumps(res, indent=2, ensure_ascii=False))
