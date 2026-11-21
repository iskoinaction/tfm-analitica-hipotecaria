"""Validación del modelo de Spread_Hipotecas (GBR) usado en Web/app.py (_train_ml_pricing_model) y notebook 5 (celda 45/51).

Comprueba: (a) Spread_Hipotecas es nacional (1 valor/trimestre) -> n efectivo = nº de trimestres;
(b) el TimeSeriesSplit de app.py se aplica sobre el CSV ordenado por Provincia -> los folds son bloques de provincias,
    no de tiempo, y el mismo trimestre (mismo target) aparece en train y test;
(c) validación correcta: rolling-origin por trimestres sobre la serie nacional (h=1 y h=4) frente a naive.
Salida: reports/audit/02_ds/out/04_spread_gbr.json
"""
import json
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from common import DATA, OUT

warnings.filterwarnings("ignore")
res = {}
df = pd.read_csv(DATA)  # mismo orden que lee app.py (Provincia, Trimestre)
F = ["Euribor", "IPC", "Tasa_Paro", "Precio_m2", "PIB_pc", "tasa_ahorro"]
T = "Spread_Hipotecas"
res["spread_valores_unicos_por_trimestre_max"] = int(df.groupby("Trimestre")[T].nunique().max())
dm = df[F + [T, "Trimestre", "Provincia"]].dropna()
res["n_filas_modelo_app"] = int(len(dm))
res["n_trimestres_distintos"] = int(dm.Trimestre.nunique())


def pipe():
    return Pipeline([("sc", StandardScaler()), ("m", GradientBoostingRegressor(n_estimators=100, max_depth=3, learning_rate=0.06,
                                                                               min_samples_leaf=5, random_state=42))])


rm = lambda a, b: float(np.sqrt(mean_squared_error(a, b)))
# (b) tal cual app.py
tscv = TimeSeriesSplit(n_splits=5)
folds = []
for tr, te in tscv.split(dm):
    a, b = dm.iloc[tr], dm.iloc[te]
    folds.append({"prov_test": f"{b.Provincia.iloc[0]}..{b.Provincia.iloc[-1]}",
                  "pct_trimestres_test_presentes_en_train": float(b.Trimestre.isin(a.Trimestre).mean() * 100)})
cv = cross_validate(pipe(), dm[F].values, dm[T].values, cv=tscv,
                    scoring={"rmse": "neg_root_mean_squared_error", "mae": "neg_mean_absolute_error"})
res["app_TimeSeriesSplit_sobre_orden_provincial"] = {"RMSE_cv": float(-cv["test_rmse"].mean()), "MAE_cv": float(-cv["test_mae"].mean()),
                                                     "folds": folds}
res["app_metricas_hardcodeadas_api"] = {"r2": 0.8492, "rmse": 0.1543, "mape": "3.2%", "nota": "Web/app.py ~l.1172, literales"}

# (b2) mismo esquema pero ordenado por tiempo (sigue habiendo cortes dentro de un trimestre)
dt = dm.sort_values(["Trimestre", "Provincia"])
cv2 = cross_validate(pipe(), dt[F].values, dt[T].values, cv=tscv, scoring={"rmse": "neg_root_mean_squared_error"})
res["TimeSeriesSplit_ordenado_por_tiempo_RMSE"] = float(-cv2["test_rmse"].mean())

# (c) rolling-origin trimestral (agregado nacional: medias simples de las provincias)
nat = dm.groupby("Trimestre")[F + [T]].mean().sort_index()
y = nat[T].values
out = {}
for h in (1, 4):
    e_m, e_n = [], []
    for i in range(40, len(nat) - h):
        Xtr, ytr = nat[F].values[: i + 1 - h], y[h: i + 1]  # features en t -> spread en t+h (directo)
        m = pipe().fit(Xtr, ytr)
        p = m.predict(nat[F].values[i: i + 1])[0]
        e_m.append(y[i + h] - p)
        e_n.append(y[i + h] - y[i])
    e_m, e_n = np.array(e_m), np.array(e_n)
    out[f"h{h}"] = {"n": int(len(e_m)), "RMSE_GBR": float(np.sqrt(np.mean(e_m ** 2))), "RMSE_naive": float(np.sqrt(np.mean(e_n ** 2))),
                    "MAE_GBR": float(np.mean(np.abs(e_m))), "MAE_naive": float(np.mean(np.abs(e_n)))}
# contemporáneo (como lo usa el asesor: macro del mismo trimestre -> spread del trimestre), validado por bloques temporales
e_c, e_n = [], []
for i in range(40, len(nat)):
    m = pipe().fit(nat[F].values[:i], y[:i])
    e_c.append(y[i] - m.predict(nat[F].values[i:i + 1])[0])
    e_n.append(y[i] - y[i - 1])
out["contemporaneo_h0"] = {"n": len(e_c), "RMSE_GBR": float(np.sqrt(np.mean(np.square(e_c)))), "RMSE_naive_t-1": float(np.sqrt(np.mean(np.square(e_n))))}
res["rolling_origin_nacional"] = out
res["periodo_evaluado_desde"] = str(nat.index[40])
(OUT / "04_spread_gbr.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
print(json.dumps(res, indent=2, ensure_ascii=False))
