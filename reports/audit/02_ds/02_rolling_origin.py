"""Benchmark rolling-origin (walk-forward, ventana expansiva) de la demanda hipotecaria NACIONAL.

Serie: suma de Hipotecas_Total de las 52 provincias (notebooks acabados/dataset_final_tfm.csv), 2005Q1-2025Q4.
Orígenes: T = 2015Q4 ... 2025Q3 (40 orígenes). Horizontes h = 1,2,3,4,8 (se evalúan los objetivos T+h <= 2025Q4).
Información disponible en el origen T: y hasta T y macro hasta T (sin valores del trimestre objetivo).
Modelos:
  benchmarks: naive (y_T), seasonal naive (y_{T+h-4k}), media móvil 4T, drift
  estadísticos: AR(p) sobre log (p<=4 por AIC), ETS aditivo amortiguado+estacional sobre log, SARIMA(1,1,1)(1,0,0)4 sobre log
  ML (estrategia directa, objetivo = log(y_{T+h}/y_T), features con información <= T, escalado dentro del pipeline):
     ElasticNet, RF, GBM, XGB, LGBM
  RF_Nac (réplica literal del notebook, SOLO h=1, usa features del trimestre objetivo: Euribor, Accesibilidad...)
Métricas: MAE, RMSE, MAPE, sMAPE, MASE (escala = MAE in-sample del seasonal naive en el train de cada origen),
          U de Theil (RMSE modelo / RMSE naive en las mismas predicciones), Diebold-Mariano (HLN) vs mejor benchmark.
Salida: reports/audit/02_ds/out/02_rolling_*.csv / .json
"""
import json
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import ElasticNetCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.ar_model import ar_select_order, AutoReg
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import xgboost as xgb
import lightgbm as lgb

from common import load_raw, build_panel, build_national, mape, smape, mae, rmse, OUT

warnings.filterwarnings("ignore")
NJ = 2
HS = [1, 2, 3, 4, 8]

raw = load_raw()
w = raw["Poblacion"]
nat = pd.DataFrame({
    "y": raw.groupby("Trimestre")["Hipotecas_Total"].sum(),
    "trans": raw.groupby("Trimestre")["Transmisiones_Total"].sum(),
    "euribor": raw.groupby("Trimestre")["Euribor"].mean(),
    "spread": raw.groupby("Trimestre")["Spread_Hipotecas"].mean(),
    "precio": raw.assign(x=raw["Precio_m2"] * w).groupby("Trimestre")["x"].sum() / raw.groupby("Trimestre")["Poblacion"].sum(),
    "paro": raw.assign(x=raw["Tasa_Paro"] * w).groupby("Trimestre")["x"].sum() / raw.groupby("Trimestre")["Poblacion"].sum(),
}).sort_index()
nat.index = pd.DatetimeIndex(nat.index, freq="QS-JAN")
y = nat["y"]
ly = np.log(y)
dates = y.index
N = len(y)
pos = {d: i for i, d in enumerate(dates)}


def feat_at(i):
    """Features con información hasta el índice i (origen)."""
    return {
        "dly0": ly.iloc[i] - ly.iloc[i - 1], "dly1": ly.iloc[i - 1] - ly.iloc[i - 2],
        "dly2": ly.iloc[i - 2] - ly.iloc[i - 3], "dly3": ly.iloc[i - 3] - ly.iloc[i - 4],
        "d4ly": ly.iloc[i] - ly.iloc[i - 4], "d4ly_prev": ly.iloc[i - 1] - ly.iloc[i - 5],
        "ly_vs_ma4": ly.iloc[i] - np.log(y.iloc[i - 3:i + 1].mean()),
        "euribor": nat["euribor"].iloc[i], "d4eur": nat["euribor"].iloc[i] - nat["euribor"].iloc[i - 4],
        "spread": nat["spread"].iloc[i],
        "d4lprecio": np.log(nat["precio"].iloc[i] / nat["precio"].iloc[i - 4]),
        "paro": nat["paro"].iloc[i], "d4paro": nat["paro"].iloc[i] - nat["paro"].iloc[i - 4],
        "d4ltrans": np.log(nat["trans"].iloc[i] / nat["trans"].iloc[i - 4]),
        "l_hip_trans": np.log(y.iloc[i] / nat["trans"].iloc[i]),
    }


def ml_dataset(h, last_origin):
    rows, tgt = [], []
    for i in range(5, last_origin - h + 1):
        f = feat_at(i)
        q = dates[i + h].quarter
        for k in (1, 2, 3, 4):
            f[f"q{k}"] = int(q == k)
        rows.append(f)
        tgt.append(ly.iloc[i + h] - ly.iloc[i])
    return pd.DataFrame(rows), np.array(tgt)


def ml_models():
    return {
        "ElasticNet": make_pipeline(StandardScaler(), ElasticNetCV(l1_ratio=[0.1, 0.5, 0.9, 0.99], cv=3, max_iter=20000, random_state=0)),
        "RF": RandomForestRegressor(n_estimators=300, min_samples_leaf=3, max_features=0.5, random_state=0, n_jobs=NJ),
        "GBM": GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0),
        "XGB": xgb.XGBRegressor(n_estimators=300, max_depth=2, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                                reg_lambda=1.0, random_state=0, n_jobs=NJ, verbosity=0),
        "LGBM": lgb.LGBMRegressor(n_estimators=300, max_depth=3, num_leaves=7, learning_rate=0.05, min_child_samples=5,
                                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=0, n_jobs=NJ, verbose=-1),
    }


first_origin = pos[pd.Timestamp("2015-10-01")]
origins = list(range(first_origin, N - 1))  # hasta 2025Q3
recs = []  # (model, origin_idx, h, target_idx, y, yhat, scale)


def add(model, i, h, yhat, scale):
    j = i + h
    if j < N:
        recs.append({"model": model, "origin": dates[i], "h": h, "target": dates[j], "y": float(y.iloc[j]),
                     "yhat": float(yhat), "scale": scale})


# --- RF_Nac réplica (h=1, con features del trimestre objetivo)
panel = build_panel(raw, accesibilidad_contemporanea=True)
nacdf, Fn = build_national(panel)

for i in origins:
    tr = y.iloc[: i + 1]
    scale = float(np.mean(np.abs(tr.values[4:] - tr.values[:-4])))
    ltr = np.log(tr)
    # benchmarks
    for h in HS:
        add("Naive", i, h, tr.iloc[-1], scale)
        k = int(np.ceil(h / 4))
        add("SeasonalNaive", i, h, tr.values[len(tr) - 1 + h - 4 * k], scale)  # y_{T+h-4k}
        add("MA4", i, h, tr.iloc[-4:].mean(), scale)
        add("Drift", i, h, tr.iloc[-1] + h * (tr.iloc[-1] - tr.iloc[0]) / (len(tr) - 1), scale)
    # AR sobre log en diferencias estacionales? -> AR(p) sobre log niveles con constante
    try:
        sel = ar_select_order(ltr.values, maxlag=4, ic="aic", trend="c")
        lags = sel.ar_lags if sel.ar_lags else [1]
        arm = AutoReg(ltr.values, lags=lags, trend="c").fit()
        fc = arm.predict(start=len(ltr), end=len(ltr) + 7)
        for h in HS:
            add("AR", i, h, np.exp(fc[h - 1]), scale)
    except Exception as e:
        print("AR fail", e)
    try:
        ets = ExponentialSmoothing(ltr.values, trend="add", damped_trend=True, seasonal="add", seasonal_periods=4,
                                   initialization_method="estimated").fit()
        fc = ets.forecast(8)
        for h in HS:
            add("ETS", i, h, np.exp(fc[h - 1]), scale)
    except Exception as e:
        print("ETS fail", e)
    try:
        sar = sm.tsa.SARIMAX(ltr.values, order=(1, 1, 1), seasonal_order=(1, 0, 0, 4)).fit(disp=False)
        fc = sar.forecast(8)
        for h in HS:
            add("SARIMA", i, h, np.exp(fc[h - 1]), scale)
    except Exception as e:
        print("SARIMA fail", e)
    # ML directo
    for h in HS:
        if i + h >= N:
            continue
        X, t = ml_dataset(h, i)
        fx = feat_at(i)
        q = dates[i + h].quarter
        for k in (1, 2, 3, 4):
            fx[f"q{k}"] = int(q == k)
        xo = pd.DataFrame([fx])[X.columns]
        for nm, m in ml_models().items():
            m.fit(X, t)
            add(nm, i, h, np.exp(ly.iloc[i] + m.predict(xo)[0]), scale)
    # RF_Nac réplica h=1
    tgt = dates[i + 1]
    if tgt in nacdf.index:
        trn = nacdf[nacdf.index <= dates[i]]
        m = RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_leaf=3, max_features="sqrt", random_state=42, n_jobs=NJ)
        m.fit(trn[Fn], trn["Hipotecas_Total"])
        add("RF_Nac(replica,h1,info t)", i, 1, m.predict(nacdf.loc[[tgt], Fn])[0], scale)
    print(dates[i].date(), end=" ", flush=True)

df = pd.DataFrame(recs)
df.to_csv(OUT / "02_rolling_forecasts.csv", index=False)
print()


def dm_test(e1, e2, h, power=2):
    """Diebold-Mariano con corrección de Harvey-Leybourne-Newbold. e1 modelo, e2 benchmark.
    d = |e1|^p - |e2|^p ; DM<0 => el modelo es mejor."""
    d = np.abs(e1) ** power - np.abs(e2) ** power
    n = len(d)
    dbar = d.mean()
    gam = [np.sum((d[k:] - dbar) * (d[:n - k] - dbar)) / n for k in range(h)]
    v = gam[0] + 2 * sum(gam[1:])
    if v <= 0:
        v = gam[0]
    dm = dbar / np.sqrt(v / n)
    hln = dm * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    p = 2 * stats.t.sf(np.abs(hln), df=n - 1)
    return float(hln), float(p)


rows = []
for (mname, h), g in df.groupby(["model", "h"]):
    nv = df[(df.model == "Naive") & (df.h == h)].set_index("target").loc[g["target"]]
    e = g["y"].values - g["yhat"].values
    rows.append({"model": mname, "h": h, "n": len(g), "MAE": mae(g.y, g.yhat), "RMSE": rmse(g.y, g.yhat),
                 "MAPE": mape(g.y, g.yhat), "sMAPE": smape(g.y, g.yhat),
                 "MASE": float(np.mean(np.abs(e) / g["scale"].values)),
                 "TheilU_vs_naive": rmse(g.y, g.yhat) / rmse(nv.y, nv.yhat)})
met = pd.DataFrame(rows)
met.to_csv(OUT / "02_rolling_metrics.csv", index=False)

# DM: mejor modelo no-benchmark vs mejor benchmark por horizonte (por MAPE)
bench = ["Naive", "SeasonalNaive", "MA4", "Drift"]
dm_rows = []
for h in HS:
    mh = met[met.h == h]
    mh = mh[mh.n == mh.n.max()]
    bb = mh[mh.model.isin(bench)].sort_values("MAPE").iloc[0]["model"]
    for mod in mh[~mh.model.isin(bench)].sort_values("MAPE")["model"]:
        a = df[(df.model == mod) & (df.h == h)].set_index("target")
        b = df[(df.model == bb) & (df.h == h)].set_index("target").loc[a.index]
        e1, e2 = (a.y - a.yhat).values, (b.y - b.yhat).values
        s2, p2 = dm_test(e1, e2, h, 2)
        s1, p1 = dm_test(e1, e2, h, 1)
        dm_rows.append({"h": h, "model": mod, "benchmark": bb, "DM_sq": s2, "p_sq": p2, "DM_abs": s1, "p_abs": p1})
dmdf = pd.DataFrame(dm_rows)
dmdf.to_csv(OUT / "02_rolling_dm.csv", index=False)

# RF_Nac h=1 vs Naive h=1 (mismo conjunto de objetivos)
a = df[(df.model == "RF_Nac(replica,h1,info t)")].set_index("target")
b = df[(df.model == "Naive") & (df.h == 1)].set_index("target").loc[a.index]
rfn = {"n": len(a), "MAPE_RF_Nac": mape(a.y, a.yhat), "MAPE_Naive": mape(b.y, b.yhat),
       "DM_sq": dm_test((a.y - a.yhat).values, (b.y - b.yhat).values, 1, 2),
       "DM_abs": dm_test((a.y - a.yhat).values, (b.y - b.yhat).values, 1, 1)}

# Estabilidad por subperiodo (h=1 y h=4) y por ventanas de 8 trimestres
per = []
for h in [1, 4, 8]:
    for nm, (a0, a1) in {"2016-2019": ("2016-01-01", "2019-12-31"), "2020-2021": ("2020-01-01", "2021-12-31"),
                         "2022-2025": ("2022-01-01", "2025-12-31"), "2024-2025(test nb)": ("2024-01-01", "2025-12-31")}.items():
        g = df[(df.h == h) & (df.target >= a0) & (df.target <= a1)]
        for mname, gg in g.groupby("model"):
            per.append({"h": h, "periodo": nm, "model": mname, "n": len(gg), "MAPE": mape(gg.y, gg.yhat)})
perdf = pd.DataFrame(per)
perdf.to_csv(OUT / "02_rolling_periodos.csv", index=False)

# rango de MAPE en ventanas móviles de 8 objetivos (h=1): inestabilidad de un test de 8 puntos
win = []
for mname, g in df[df.h == 1].groupby("model"):
    g = g.sort_values("target")
    ape = (np.abs(g.y - g.yhat) / g.y * 100).values
    if len(ape) >= 8:
        m8 = [ape[k:k + 8].mean() for k in range(len(ape) - 7)]
        win.append({"model": mname, "MAPE8_min": min(m8), "MAPE8_med": float(np.median(m8)), "MAPE8_max": max(m8)})
windf = pd.DataFrame(win)
windf.to_csv(OUT / "02_rolling_ventanas8.csv", index=False)

summary = {"n_origins": len(origins), "first_origin": str(dates[origins[0]].date()), "last_origin": str(dates[origins[-1]].date()),
           "RF_Nac_vs_Naive_h1": rfn}
(OUT / "02_rolling_summary.json").write_text(json.dumps(summary, indent=2, default=str))
pd.set_option("display.width", 200)
for h in HS:
    print(f"\n=== h={h}")
    print(met[met.h == h].sort_values("MAPE").round(3).to_string(index=False))
print("\nDM:\n", dmdf.round(3).to_string(index=False))
print("\nRF_Nac h1:", rfn)
print("\nVentanas 8:\n", windf.round(2).to_string(index=False))
print("\nPeriodos h=1:\n", perdf[perdf.h == 1].pivot(index="model", columns="periodo", values="MAPE").round(2).to_string())
print("\nPeriodos h=4:\n", perdf[perdf.h == 4].pivot(index="model", columns="periodo", values="MAPE").round(2).to_string())
