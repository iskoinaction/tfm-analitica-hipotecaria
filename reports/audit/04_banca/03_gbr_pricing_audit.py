"""Auditoría 04 (Banca) - Script 03. Auditoría del GBR de pricing (app.py::_train_ml_pricing_model).
1) Observaciones efectivas (target nacional replicado en 52 provincias).
2) Reproduce el RMSE_CV de la app (TimeSeriesSplit sobre datos ordenados por provincia => fuga) y el CV-5 del notebook 5.
3) Validación correcta: origen móvil por trimestre (entrena con trimestres < t, predice t) a nivel nacional.
4) Baselines: persistencia (spread del trimestre anterior), media histórica, OLS spread~Euribor expandente.
5) Dispersión provincial espuria: mismo trimestre, misma realidad nacional, 52 predicciones distintas.
6) Error del GBR de la app en 2023-2025 frente al APRC-Euríbor observado.
Salida: out/gbr_audit.json
"""
import json, os
import numpy as np, pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import TimeSeriesSplit, KFold, cross_validate
from sklearn.metrics import mean_squared_error, mean_absolute_error, make_scorer
from sklearn.linear_model import LinearRegression

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
OUT = os.path.join(os.path.dirname(__file__), 'out')
df = pd.read_csv(os.path.join(ROOT, 'notebooks acabados', 'dataset_final_tfm.csv'))
F = ['Euribor', 'IPC', 'Tasa_Paro', 'Precio_m2', 'PIB_pc', 'tasa_ahorro']; T = 'Spread_Hipotecas'
rmse = lambda a, b: float(np.sqrt(mean_squared_error(a, b)))
GBR = lambda: GradientBoostingRegressor(n_estimators=100, max_depth=3, learning_rate=0.06, min_samples_leaf=5, random_state=42)
res = {}

d = df[F + [T, 'Provincia', 'Trimestre']].dropna()          # igual que la app (sin ordenar)
res['n_filas_entrenamiento'] = int(len(d))
res['n_trimestres_unicos'] = int(d['Trimestre'].nunique())
res['rango_trimestres'] = [d['Trimestre'].min(), d['Trimestre'].max()]
res['n_valores_unicos_target'] = int(d[T].round(10).nunique())
res['n_valores_unicos_por_variable_y_trimestre'] = {f: float(d.groupby('Trimestre')[f].nunique().mean()) for f in F + [T]}
res['orden_filas_trimestre_monotono'] = bool(pd.to_datetime(d['Trimestre']).is_monotonic_increasing); res['primeras_filas_provincia'] = d['Provincia'].iloc[[0, 79, 80]].tolist()

X, y = d[F].values, d[T].values
pipe = Pipeline([('s', StandardScaler()), ('m', GBR())])
sc = {'rmse': make_scorer(rmse, greater_is_better=False), 'mae': make_scorer(mean_absolute_error, greater_is_better=False)}
cv_app = cross_validate(pipe, X, y, cv=TimeSeriesSplit(5), scoring=sc)
res['app_TimeSeriesSplit_sobre_orden_provincial'] = {'rmse_cv': float(-cv_app['test_rmse'].mean()), 'mae_cv': float(-cv_app['test_mae'].mean())}
cv_nb = cross_validate(pipe, X, y, cv=5, scoring=sc)   # notebook 5 celda 15 (KFold sin barajar)
res['notebook_cv5_KFold'] = {'rmse_cv': float(-cv_nb['test_rmse'].mean())}
# Solo variables nacionales (identifican el trimestre) en el mismo CV con fuga
cv_nat = cross_validate(Pipeline([('s', StandardScaler()), ('m', GBR())]), d[['Euribor', 'tasa_ahorro']].values, y, cv=TimeSeriesSplit(5), scoring=sc)
res['app_cv_con_solo_Euribor_y_tasa_ahorro'] = {'rmse_cv': float(-cv_nat['test_rmse'].mean())}
# Model en train completo (como la app)
pipe.fit(X, y); res['r2_train_app'] = float(1 - ((y - pipe.predict(X))**2).sum() / ((y - y.mean())**2).sum())

# --- 3/4) Validación por origen móvil a nivel nacional (target nacional) ---
d['Q'] = pd.PeriodIndex(pd.to_datetime(d['Trimestre']), freq='Q')
qs = sorted(d['Q'].unique())
nat = df.assign(Q=pd.PeriodIndex(pd.to_datetime(df['Trimestre']), freq='Q')).groupby('Q')[[T, 'Euribor']].first()
start = qs.index(pd.Period('2013Q1', 'Q'))
rows = []
for i in range(start, len(qs)):
    q = qs[i]; tr = d[d['Q'] < q]; te = d[d['Q'] == q]
    m = Pipeline([('s', StandardScaler()), ('m', GBR())]).fit(tr[F].values, tr[T].values)
    p_prov = m.predict(te[F].values)
    y_true = float(te[T].iloc[0])
    prev = float(nat.loc[qs[i - 1], T])
    ntr = nat.loc[[x for x in qs if x < q]]
    ols = LinearRegression().fit(ntr[['Euribor']].values, ntr[T].values)
    rows.append({'Q': str(q), 'y': y_true, 'gbr_media_prov': float(p_prov.mean()), 'gbr_min_prov': float(p_prov.min()), 'gbr_max_prov': float(p_prov.max()),
                 'persistencia': prev, 'media_hist': float(ntr[T].mean()), 'ols_euribor': float(ols.predict([[nat.loc[q, 'Euribor']]])[0])})
bt = pd.DataFrame(rows); bt.to_csv(os.path.join(OUT, 'gbr_backtest_origen_movil.csv'), index=False)
res['backtest_origen_movil'] = {
    'periodo': [rows[0]['Q'], rows[-1]['Q']], 'n_trimestres_test': len(rows),
    'rmse_gbr_media_52_provincias': rmse(np.repeat(bt['y'].values, 1), bt['gbr_media_prov']),
    'rmse_persistencia_t_1': rmse(bt['y'], bt['persistencia']),
    'rmse_media_historica': rmse(bt['y'], bt['media_hist']),
    'rmse_ols_spread_euribor': rmse(bt['y'], bt['ols_euribor']),
    'rango_medio_entre_provincias_pp': float((bt['gbr_max_prov'] - bt['gbr_min_prov']).mean()),
}
# --- 5) Dispersión provincial espuria en train completo, trimestre 2024Q4 ---
last = d[d['Q'] == pd.Period('2024Q4', 'Q')]
pp = pipe.predict(last[F].values)
res['dispersion_provincial_2024Q4_modelo_app'] = {'spread_real_nacional': float(last[T].iloc[0]), 'pred_min': float(pp.min()), 'pred_max': float(pp.max()),
                                                   'prov_min': last['Provincia'].iloc[pp.argmin()], 'prov_max': last['Provincia'].iloc[pp.argmax()]}
# --- 6) Error 2023-2025 con inputs anuales (como la app) ---
tip = pd.read_csv(os.path.join(ROOT, 'Web', 'static', 'tipos_hipotecas.csv')); tip['y'] = tip['TIME_PERIOD'].str[:4]
ann = tip.groupby('y')[['APRC_VALUE', 'EURIBOR_VALUE', 'Diferencia']].mean()
out6 = {}
for yr in ['2023', '2024', '2025']:
    yd = df[df['Trimestre'].str.startswith(yr)]
    out6[yr] = {'aprc_menos_euribor_obs': round(float(ann.loc[yr, 'APRC_VALUE'] - ann.loc[yr, 'EURIBOR_VALUE']), 3),
                'en_entrenamiento': bool(yr in set(d['Trimestre'].str[:4]))}
res['anios_check'] = out6
json.dump(res, open(os.path.join(OUT, 'gbr_audit.json'), 'w'), indent=1, ensure_ascii=False, default=str)
print(json.dumps(res, indent=1, ensure_ascii=False, default=str))
