"""Información independiente real por variable en dataset_final_tfm.csv y efectos
de la replicación (nacional->provincias, CCAA->provincias, anual->trimestral).

Métricas por variable:
 - n_no_nulos, n_valores_distintos (global), celdas_independientes (nivel real de
   variación: T, CCAA×T, prov×año, prov×T) y ratio sobre 4.368.
 - eta2_trim: R² de efectos fijos de trimestre (proporción de varianza que es común
   a todas las provincias en cada trimestre) = ICC por clúster temporal.
 - eta2_prov_año: R² de efectos fijos provincia-año (=1 => varianza intra-año nula).
 - deff/N_eff por clúster-trimestre (Kish: 1+(m-1)ρ, m=52).
Demostraciones: (a) error estándar OLS ingenuo vs. cluster-robusto por trimestre
y Driscoll-Kraay; (b) réplica de la validación cruzada del notebook 5 (Spread ~
macro) con particiones ingenuas vs. honestas; (c) R² pooled de un ingenuo y_t=y_{t-1}
para Hipotecas_Total (escala transversal).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *  # noqa
import statsmodels.formula.api as smf

ds = pd.read_csv(DATASET)
N = len(ds)
ds["year"] = ds.Trimestre.str[:4]
ccaa_of_legacy = {p.legacy_name: geo.PROVINCES[c].ccaa_code for c, p in geo.PROVINCES.items()}
ds["ccaa"] = ds.Provincia.map(ccaa_of_legacy)
vars_ = [c for c in ds.columns if c not in ("Provincia", "Trimestre", "year", "ccaa")]

def eta2(y, g):
    y = y.astype(float); ok = y.notna()
    y, g = y[ok], g[ok]
    tot = ((y - y.mean()) ** 2).sum()
    within = ((y - y.groupby(g).transform("mean")) ** 2).sum()
    return 1 - within / tot if tot > 0 else np.nan

rows = []
for v in vars_:
    s = ds[v]; nn = s.notna()
    d = ds[nn]
    per_q = d.groupby("Trimestre")[v].nunique()
    per_py = d.groupby(["Provincia", "year"])[v].nunique()
    per_cq = d.groupby(["ccaa", "Trimestre"])[v].nunique()
    if per_q.max() == 1:
        nivel, cells = "nacional (T)", d.Trimestre.nunique()
    elif per_cq.max() == 1:
        nivel, cells = "CCAA×T", d.groupby(["ccaa", "Trimestre"]).ngroups
    elif per_py.max() == 1:
        nivel, cells = "provincia×año", d.groupby(["Provincia", "year"]).ngroups
    else:
        nivel, cells = "provincia×T", len(d)
    rho = eta2(d[v], d.Trimestre)
    m = 52
    deff = 1 + (m - 1) * rho
    rows.append(dict(variable=v, n_no_nulos=int(nn.sum()), valores_distintos=int(s.nunique()),
                     nivel_real=nivel, celdas_independientes=cells, ratio_vs_4368=round(cells / N, 3),
                     distintos_por_trim_med=float(per_q.median()), eta2_trim=round(rho, 3),
                     eta2_prov=round(eta2(d[v], d.Provincia), 3),
                     eta2_prov_año=round(eta2(d[v], d.Provincia + d.year), 3),
                     deff_trim=round(deff, 1), N_eff_trim=round(nn.sum() / deff)))
tab = pd.DataFrame(rows)
tab.to_csv(OUT / "02_informacion_efectiva.csv", index=False)
print(tab.to_string(index=False))

# CCAA: provincias que comparten IPC
print("\nIPC: nº de valores distintos por trimestre (min/med/max):",
      ds.groupby("Trimestre").IPC.nunique().agg(["min", "median", "max"]).to_dict())
print("Provincias que reciben un IPC autonómico compartido:",
      int(ds.groupby("ccaa").Provincia.nunique().loc[lambda s: s > 1].sum()), "de 52")

# Varianza intra-año nula: proporción de variación trimestral (Δ trimestre a trimestre) que es 0
print("\nProporción de Δ trimestrales exactamente 0 (por provincia):")
for v in ["PIB_pc", "Poblacion", "Edad_Media", "Pob_Ext", "Tasa_Paro", "Precio_m2", "Hipotecas_Total", "Transmisiones_Total"]:
    dd = ds.sort_values(["Provincia", "Trimestre"]).groupby("Provincia")[v].diff()
    q1 = ds.sort_values(["Provincia", "Trimestre"]).Trimestre.str[5:7] == "01"
    print(f"  {v:20s} Δ=0: {(dd == 0).mean():.3f} | salto concentrado en Q1: "
          f"{(dd[q1].abs().sum() / dd.abs().sum()) if dd.abs().sum() > 0 else float('nan'):.3f}")

# (a) Errores estándar: OLS ingenuo vs cluster por trimestre vs Driscoll-Kraay
print("\n(a) Regresión ilustrativa log(Hipotecas_Total) ~ Euribor + tasa_ahorro + Spread + C(Provincia)")
d = ds.dropna(subset=["Hipotecas_Total", "Euribor", "tasa_ahorro", "Spread_Hipotecas"]).copy()
d = d[d.Hipotecas_Total > 0]
d["ly"] = np.log(d.Hipotecas_Total)
d["t"] = d.Trimestre.astype("category").cat.codes
f = "ly ~ Euribor + tasa_ahorro + Spread_Hipotecas + C(Provincia)"
r0 = smf.ols(f, d).fit()
r1 = smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": d["t"]})
r2 = smf.ols(f, d).fit(cov_type="cluster", cov_kwds={"groups": d["Provincia"].astype("category").cat.codes})
# Driscoll-Kraay (HAC sobre series de momentos agregadas por periodo), lags=4
r3 = smf.ols(f, d.sort_values(["t"])).fit(cov_type="hac-groupsum", cov_kwds={"time": d.sort_values(["t"])["t"].values, "maxlags": 4})
nat = d.groupby("Trimestre")[["ly", "Euribor", "tasa_ahorro", "Spread_Hipotecas"]].mean()
r4 = smf.ols("ly ~ Euribor + tasa_ahorro + Spread_Hipotecas", nat).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
se = pd.DataFrame({"coef": r0.params, "SE_OLS": r0.bse, "SE_cluster_trim": r1.bse, "SE_cluster_prov": r2.bse,
                   "SE_DriscollKraay": r3.bse}).loc[["Euribor", "tasa_ahorro", "Spread_Hipotecas"]]
se["ratio_DK/OLS"] = se.SE_DriscollKraay / se.SE_OLS
se["t_OLS"] = se.coef / se.SE_OLS
se["t_DK"] = se.coef / se.SE_DriscollKraay
print(se.round(4).to_string())
print("  Regresión equivalente con 84 medias nacionales (HAC): coef/SE")
print(pd.DataFrame({"coef": r4.params, "SE_HAC": r4.bse}).round(4).to_string())
print(f"  N declarado={len(d)}; nº de valores distintos de cada regresor = {d.Euribor.nunique()}")

# (b) Réplica de la CV del notebook 5 (Spread_Hipotecas ~ macro), n_jobs<=2
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, GroupKFold, TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
FE = ["Euribor", "IPC", "Tasa_Paro", "Precio_m2", "PIB_pc", "tasa_ahorro"]
dd = ds.sort_values(["Provincia", "Trimestre"]).dropna(subset=FE + ["Spread_Hipotecas"]).reset_index(drop=True)
X, y = dd[FE].values, dd.Spread_Hipotecas.values
rf = make_pipeline(StandardScaler(), RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=2))
lr = make_pipeline(StandardScaler(), LinearRegression())
print(f"\n(b) Spread_Hipotecas (nacional, {dd.Trimestre.nunique()} valores distintos) replicado en {len(dd)} filas")
res = {}
for name, cv, groups in [("KFold(5) sin barajar, orden prov-trim (= notebook 5 celda 15)", KFold(5), None),
                         ("TimeSeriesSplit(5) sobre filas ordenadas por provincia (= nb5 celda 37)", TimeSeriesSplit(5), None),
                         ("GroupKFold(5) por trimestre (honesto: trimestres no compartidos)", GroupKFold(5), dd.Trimestre)]:
    for mn, mdl in [("RF", rf), ("Lineal", lr)]:
        sc = cross_val_score(mdl, X, y, cv=cv, groups=groups, scoring="r2", n_jobs=1)
        res[(name, mn)] = sc.mean()
        print(f"  {mn:6s} {name}: R² medio = {sc.mean():.4f}")
# Partición temporal real: train <= 2018, test 2019-2024 (fila por provincia)
tr = dd.Trimestre < "2019-01-01"; te = (dd.Trimestre >= "2019-01-01") & (dd.Trimestre < "2025-01-01")
from sklearn.metrics import r2_score
for mn, mdl in [("RF", rf), ("Lineal", lr)]:
    mdl.fit(X[tr], y[tr]); p = mdl.predict(X[te])
    print(f"  {mn:6s} Temporal real (train≤2018, test 2019-2024): R² = {r2_score(y[te], p):.4f}")
# memorización: Euribor sólo identifica el trimestre
print("  Pares (Euribor) distintos =", dd.Euribor.nunique(), "= nº trimestres ->", "Euribor actúa como ID de trimestre")

# (c) R² pooled de un ingenuo para Hipotecas_Total (escala transversal)
h = ds.sort_values(["Provincia", "Trimestre"]).copy()
h["lag1"] = h.groupby("Provincia").Hipotecas_Total.shift(1)
h["lag4"] = h.groupby("Provincia").Hipotecas_Total.shift(4)
test = h[h.Trimestre >= sorted(h.Trimestre.unique())[-8]].dropna(subset=["lag1", "lag4"])
print("\n(c) Hipotecas_Total, test = últimos 8 trimestres (como notebook 4):")
print(f"  R² pooled ingenuo y=lag1: {r2_score(test.Hipotecas_Total, test.lag1):.4f}; y=lag4: {r2_score(test.Hipotecas_Total, test.lag4):.4f}")
w = test.assign(yc=test.Hipotecas_Total - test.groupby('Provincia').Hipotecas_Total.transform('mean'),
                pc=test.lag1 - test.groupby('Provincia').Hipotecas_Total.transform('mean'))
print(f"  R² 'within' (desviaciones respecto a la media provincial) del ingenuo lag1: {r2_score(w.yc, w.pc):.4f}")
print("  Proporción de varianza total explicada por la provincia (eta² prov, test):",
      round(eta2(test.Hipotecas_Total, test.Provincia), 3))
nt = test.groupby("Trimestre")[["Hipotecas_Total", "lag1"]].sum()
print(f"  Agregado nacional del ingenuo lag1: R² = {r2_score(nt.Hipotecas_Total, nt.lag1):.4f}")

# (d) Importancia espuria: una variable "nacional" de RUIDO PURO (un valor aleatorio por
# trimestre replicado en las 52 provincias) frente a la misma variable sin replicar.
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split
rng = np.random.default_rng(0)
h = ds.dropna(subset=["Hipotecas_Total", "Precio_m2", "Tasa_Paro", "Poblacion"]).copy()
h["ly"] = np.log(h.Hipotecas_Total)
qnoise = pd.Series(rng.normal(size=h.Trimestre.nunique()), index=sorted(h.Trimestre.unique()))
h["ruido_nacional"] = h.Trimestre.map(qnoise)
h["ruido_iid"] = rng.normal(size=len(h))
FE2 = ["Precio_m2", "Tasa_Paro", "Poblacion", "ruido_nacional", "ruido_iid"]
Xtr, Xte, ytr, yte = train_test_split(h[FE2], h.ly, test_size=0.2, random_state=0, shuffle=True)
rfm = RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=0, n_jobs=2).fit(Xtr, ytr)
pi = permutation_importance(rfm, Xte, yte, n_repeats=5, random_state=0, n_jobs=1)
print("\n(d) RF log(Hipotecas) con partición aleatoria de filas; importancia por permutación (caída de R²):")
for f, m_, s_ in zip(FE2, pi.importances_mean, pi.importances_std):
    print(f"  {f:15s} {m_:.4f} ± {s_:.4f}   (impureza: {rfm.feature_importances_[FE2.index(f)]:.3f})")
rfm2 = RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=0, n_jobs=2).fit(Xtr[FE2[:3]], ytr)
print(f"  R² test con ruido_nacional: {rfm.score(Xte, yte):.4f} | sin variables de ruido: {rfm2.score(Xte[FE2[:3]], yte):.4f}")
