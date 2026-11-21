"""Auditoría de las proyecciones 2026-2030 (notebook 5, celdas 26, 31, 46, 49, 50, 51).

Reproduce las tablas del README "Fase 7" y comprueba:
  - estructura de predicciones_provinciales_2026_2030.csv
  - PIB_pc: serie anual replicada -> la 'estacionalidad' del SARIMA es un artefacto; guardrail CAGR
  - Tasa_Paro: sistema de 3 niveles seleccionado con el mismo test que se reporta; suelo 8,5 %
  - Precio_m2: HW amortiguado vs seasonal naive por provincia (README: "HW gana en el 79 %")
  - Euribor / IPC: valores usados frente a fuentes (BCE dic-2025, API BCE)
Salida: reports/audit/02_ds/out/03_projections_audit.json
"""
import json
import warnings

import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from common import ROOT, load_raw, OUT

warnings.filterwarnings("ignore")
res = {}
df = load_raw()
PROVS = sorted(df["Provincia"].unique())
pred = pd.read_csv(ROOT / "notebooks acabados" / "predicciones_provinciales_2026_2030.csv")

# ------------------------------------------------------------------ 0. estructura del CSV
res["csv_rows"] = int(len(pred))
res["csv_rows_by_var"] = pred.groupby("variable").size().to_dict()
res["csv_periodos_by_var"] = pred.groupby("variable")["trimestre"].agg(lambda s: f"{s.min()}..{s.max()} ({s.nunique()})").to_dict()

# ------------------------------------------------------------------ 1. PIB_pc
d = df.dropna(subset=["PIB_pc"]).assign(year=lambda x: x.Trimestre.dt.year)
res["PIB_pc_valores_unicos_por_prov_anio_max"] = int(d.groupby(["Provincia", "year"])["PIB_pc"].nunique().max())
nat_pib = df.groupby("Trimestre")["PIB_pc"].mean().dropna()
q = nat_pib.index.quarter
dq = nat_pib.diff()
res["PIB_pc_nacional_diff_trimestral_no_nula_por_trimestre"] = {int(k): int((dq[q == k].abs() > 1e-9).sum()) for k in (1, 2, 3, 4)}
# proyecciones PIB del CSV: ¿constante dentro del año?
pp = pred[pred.variable == "PIB_pc"].copy()
pp["year"] = pp.trimestre.str[:4]
res["CSV_PIB_pc_valores_unicos_por_prov_anio_max"] = int(pp.groupby(["provincia", "year"])["valor"].nunique().max())
res["CSV_PIB_pc_valores_unicos_por_prov_anio_mediana"] = float(pp[pp.year >= "2026"].groupby(["provincia", "year"])["valor"].nunique().median())

# Re-ejecución de la celda 49 (PIB): cuántas provincias tienen el guardrail activo
cap_activo, cagr_list, sarima_vs_cap, nb_match = 0, [], [], []
for prov in PROVS:
    s = df[df.Provincia == prov].sort_values("Trimestre")["PIB_pc"].dropna()
    s.index = pd.RangeIndex(len(s))
    m = sm.tsa.SARIMAX(s, order=(1, 1, 0), seasonal_order=(1, 1, 0, 4)).fit(disp=False)
    fc24 = np.asarray(m.get_forecast(24).predicted_mean)  # pasos 1..24 desde 2024Q4 => 2025Q1..2030Q4
    # Réplica literal de la celda 49: get_future() fecha el primer paso en last_date+3m = 2026Q1
    # (last_date = 2025Q4 del panel aunque PIB_pc 2025 sea NaN) => desfase de un año.
    lastv = float(s.iloc[-1])
    cg0 = min((lastv / float(s.iloc[0])) ** (1 / (len(s) / 4)) - 1, 0.04)
    nb_vals = np.minimum(fc24[:20], np.array([lastv * (1 + cg0) ** ((i // 4) + 1) for i in range(20)]))
    csv_vals = pp[(pp.provincia == prov) & (pp.year >= "2026")].sort_values("trimestre")["valor"].values
    nb_match.append(bool(len(csv_vals) == 20 and np.allclose(nb_vals, csv_vals, rtol=1e-4)))
    raw = fc24[4:24]  # 2026Q1..2030Q4 correctamente fechados
    last = float(s.iloc[-1])
    cagr = (last / float(s.iloc[0])) ** (1 / (len(s) / 4)) - 1
    capc = min(cagr, 0.04)
    cap = np.array([last * (1 + capc) ** ((i // 4) + 1) for i in range(20)])
    final = np.minimum(raw, cap)
    cap_activo += int((cap < raw).mean() > 0.5)
    cagr_list.append(cagr)
    sarima_vs_cap.append({"prov": prov, "cagr_hist": cagr, "frac_trimestres_cap_activo": float((cap < raw).mean()),
                          "crec_anual_SARIMA_2030": float((raw[-1] / last) ** (1 / 6) - 1),
                          "crec_anual_final_2030": float((final[-1] / last) ** (1 / 6) - 1)})
sv = pd.DataFrame(sarima_vs_cap)
res["PIB_CSV_coincide_con_replica_desfasada_un_anio_pct_prov"] = float(np.mean(nb_match) * 100)
# PIB_pc 2030 del CSV frente a 2024 observado: años de crecimiento implícitos
last24 = df[df.Trimestre == "2024-10-01"].set_index("Provincia")["PIB_pc"]
csv30 = pp[pp.trimestre == "2030-10"].set_index("provincia")["valor"]
res["PIB_CSV2030_sobre_2024_mediana"] = float((csv30 / last24.reindex(csv30.index)).median())
res["PIB_cap_activo_en_mayoria_trimestres_n_prov"] = cap_activo
res["PIB_cagr_hist_min_med_max"] = [float(np.min(cagr_list)), float(np.median(cagr_list)), float(np.max(cagr_list))]
res["PIB_cagr_hist_n_prov_mayor_4pct"] = int(np.sum(np.array(cagr_list) > 0.04))
res["PIB_crec_anual_SARIMA_sin_cap_mediana"] = float(sv.crec_anual_SARIMA_2030.median())
res["PIB_crec_anual_final_mediana"] = float(sv.crec_anual_final_2030.median())
# Nota: el exponente usa len(s)/4 = 20 años aunque 2005->2024 son 19 intervalos anuales
res["PIB_cagr_exponente_anios_usados"] = float(len(df[df.Provincia == PROVS[0]]["PIB_pc"].dropna()) / 4)

# Backtest PIB (celda 51): test 8 trimestres = 2 valores anuales (2023, 2024)
rows = []
for prov in PROVS:
    s = df[df.Provincia == prov].sort_values("Trimestre")["PIB_pc"].dropna()
    s.index = pd.RangeIndex(len(s))
    tr, te = s.iloc[:-8], s.iloc[-8:]
    m = sm.tsa.SARIMAX(tr, order=(1, 1, 0), seasonal_order=(1, 1, 0, 4)).fit(disp=False)
    raw = np.asarray(m.get_forecast(8).predicted_mean)
    lr = float(tr.iloc[-1])
    cg = min((lr / float(tr.iloc[0])) ** (1 / (len(tr) / 4)) - 1, 0.04)
    cap = np.array([lr * (1 + cg) ** ((i // 4) + 1) for i in range(8)])
    p = np.minimum(raw, cap)
    naive = np.full(8, lr)
    # benchmark anual: random walk con deriva sobre la serie ANUAL (deriva = media de crecimientos anuales del train)
    ann = tr.iloc[::4].values  # un valor por año
    g = np.mean(np.diff(np.log(ann)))
    drift = np.repeat([lr * np.exp(g * k) for k in (1, 2)], 4)
    mape = lambda a, b: float(np.mean(np.abs((a - b) / a)) * 100)
    u2 = lambda a, b: float(np.sqrt(np.sum((a - b) ** 2) / np.sum((a - naive) ** 2)))
    rows.append({"prov": prov, "MAPE": mape(te.values, p), "U2": u2(te.values, p), "MAPE_sincap": mape(te.values, raw),
                 "MAPE_naive": mape(te.values, naive), "MAPE_drift_anual": mape(te.values, drift),
                 "U2_drift_anual": u2(te.values, drift), "n_valores_test_distintos": int(te.nunique())})
bp = pd.DataFrame(rows)
res["PIB_backtest"] = {"MAPE_mediana": float(bp.MAPE.median()), "U2_mediana": float(bp.U2.median()),
                       "MAPE_sin_cap_mediana": float(bp.MAPE_sincap.median()), "MAPE_naive_mediana": float(bp.MAPE_naive.median()),
                       "MAPE_drift_anual_mediana": float(bp.MAPE_drift_anual.median()),
                       "U2_drift_anual_mediana": float(bp.U2_drift_anual.median()),
                       "n_valores_distintos_test_max": int(bp.n_valores_test_distintos.max()),
                       "pct_prov_drift_anual_mejor_que_SARIMA": float((bp.MAPE_drift_anual < bp.MAPE).mean() * 100)}

# ------------------------------------------------------------------ 2. Tasa_Paro
PROV_SARIMA_DUMMY = {"Badajoz": {"order": (1, 1, 0), "seasonal": (1, 1, 0, 4)},
                     "Girona": {"order": (1, 1, 0), "seasonal": (0, 0, 1, 4)}}
PROV_ARIMA_DUMMY = {"Castellón", "Ciudad Real", "Granada", "Islas Baleares", "Jaén", "La Rioja", "León", "Málaga", "Palencia",
                    "Pontevedra", "Región de Murcia", "Santa Cruz de Tenerife", "Tarragona", "Valladolid", "Vizcaya", "Zamora", "Zaragoza"}


def cdummy(t, nf):
    return ((t >= "2020-01-01") & (t <= "2021-12-31")).astype(float).values.reshape(-1, 1), np.zeros((nf, 1))


def mu(r, p, n):
    return float(np.mean(np.abs((r - p) / r)) * 100), float(np.sqrt(np.sum((r - p) ** 2) / np.sum((r - n) ** 2)))


rows = []
for prov in PROVS:
    sf = df[df.Provincia == prov].sort_values("Trimestre")[["Trimestre", "Tasa_Paro"]].dropna().reset_index(drop=True)
    tr, te = sf.iloc[:-16], sf.iloc[-16:]
    s_tr, s_te = tr["Tasa_Paro"], te["Tasa_Paro"].values
    naive = np.full(16, float(s_tr.iloc[-1]))
    c_tr, c_te = cdummy(tr["Trimestre"], 16)
    out = {"prov": prov, "tier": "SARIMA+dummy" if prov in PROV_SARIMA_DUMMY else ("ARIMA+dummy" if prov in PROV_ARIMA_DUMMY else "ARIMA")}
    fits = {}
    try:
        fits["ARIMA"] = np.asarray(sm.tsa.ARIMA(s_tr, order=(3, 1, 2)).fit().get_forecast(16).predicted_mean)
    except Exception:
        pass
    try:
        fits["ARIMA+dummy"] = np.asarray(sm.tsa.SARIMAX(s_tr, order=(3, 1, 2), exog=c_tr).fit(disp=False).get_forecast(16, exog=c_te).predicted_mean)
    except Exception:
        pass
    if prov in PROV_SARIMA_DUMMY:
        cfg = PROV_SARIMA_DUMMY[prov]
        fits["SARIMA+dummy"] = np.asarray(sm.tsa.SARIMAX(s_tr, order=cfg["order"], seasonal_order=cfg["seasonal"], exog=c_tr)
                                          .fit(disp=False).get_forecast(16, exog=c_te).predicted_mean)
    for k, v in fits.items():
        m1, u1 = mu(s_te, np.clip(v, 8.5, None), naive)
        m0, u0 = mu(s_te, v, naive)
        out[f"MAPE_{k}"], out[f"U2_{k}"] = m1, u1
        out[f"MAPE_{k}_sinsuelo"] = m0
    out["MAPE_naive"] = mu(s_te, naive, naive)[0]
    out["paro_min_test"] = float(s_te.min())
    out["n_trim_test_bajo_8.5"] = int((s_te < 8.5).sum())
    rows.append(out)
pdx = pd.DataFrame(rows)
pdx["MAPE_asignado"] = pdx.apply(lambda r: r[f"MAPE_{r.tier}"], axis=1)
pdx["U2_asignado"] = pdx.apply(lambda r: r[f"U2_{r.tier}"], axis=1)
tiers = {}
for t, g in pdx.groupby("tier"):
    tiers[t] = {"n": int(len(g)), "MAPE_mediana": float(g.MAPE_asignado.median()), "U2_mediana": float(g.U2_asignado.median())}
res["Paro_tiers_reproducidos"] = tiers
res["Paro_global"] = {"MAPE_mediana": float(pdx.MAPE_asignado.median()), "U2_mediana": float(pdx.U2_asignado.median()),
                      "n_prov_U2_mayor_1": int((pdx.U2_asignado > 1).sum()),
                      "MAPE_naive_mediana": float(pdx.MAPE_naive.median())}
# optimismo por selección: el nivel se eligió mirando el mismo test
pdx["MAPE_min_arima_vs_dummy"] = pdx[["MAPE_ARIMA", "MAPE_ARIMA+dummy"]].min(axis=1)
res["Paro_seleccion"] = {
    "MAPE_mediana_regla_fija_ARIMA": float(pdx["MAPE_ARIMA"].median()),
    "MAPE_mediana_regla_fija_ARIMA+dummy": float(pdx["MAPE_ARIMA+dummy"].median()),
    "MAPE_mediana_oraculo_min(ARIMA,ARIMA+dummy)": float(pdx["MAPE_min_arima_vs_dummy"].median()),
    "n_prov_donde_dummy_es_mejor_en_test": int((pdx["MAPE_ARIMA+dummy"] < pdx["MAPE_ARIMA"]).sum()),
    "n_prov_asignadas_dummy_y_dummy_mejor": int(((pdx["MAPE_ARIMA+dummy"] < pdx["MAPE_ARIMA"]) & pdx.tier.ne("ARIMA")).sum()),
    "n_prov_asignadas_sin_dummy_y_dummy_mejor": int(((pdx["MAPE_ARIMA+dummy"] < pdx["MAPE_ARIMA"]) & pdx.tier.eq("ARIMA")).sum()),
}
res["Paro_suelo"] = {
    "n_prov_con_algun_trim_test(2022-25)_bajo_8.5": int((pdx["n_trim_test_bajo_8.5"] > 0).sum()),
    "MAPE_mediana_asignado_sin_suelo": float(pdx.apply(lambda r: r[f"MAPE_{r.tier}_sinsuelo"], axis=1).median()),
}
# Paro observado 2025
p25 = df[df.Trimestre.dt.year == 2025].groupby("Provincia")["Tasa_Paro"]
res["Paro_2025_obs"] = {"n_prov_media2025_bajo_8.5": int((p25.mean() < 8.5).sum()),
                        "n_prov_2025Q4_bajo_8.5": int((df[df.Trimestre == "2025-10-01"].set_index("Provincia")["Tasa_Paro"] < 8.5).sum()),
                        "n_prov_algun_trim2025_bajo_8.5": int((p25.min() < 8.5).sum()),
                        "min_2025Q4": float(df[df.Trimestre == "2025-10-01"]["Tasa_Paro"].min())}
cp = pred[(pred.variable == "Tasa_Paro") & (pred.trimestre >= "2026")]
res["CSV_paro_n_prov_con_algun_trim_en_suelo_8.5"] = int(cp.groupby("provincia")["valor"].min().le(8.5 + 1e-6).sum())
res["CSV_paro_n_filas_en_suelo"] = int((cp.valor <= 8.5 + 1e-6).sum())
# salto 2025Q4 (observado) -> 2026Q1 (proyección) en provincias con paro bajo
obs4 = df[df.Trimestre == "2025-10-01"].set_index("Provincia")["Tasa_Paro"]
p26 = cp[cp.trimestre == "2026-01"].set_index("provincia")["valor"]
jump = (p26 - obs4.reindex(p26.index)).dropna()
low = obs4[obs4 < 8.5].index
res["Paro_salto_2025Q4_a_2026Q1_prov_bajo_suelo"] = {k: round(float(v), 2) for k, v in jump.reindex(low).items()}
pdx.to_csv(OUT / "03_paro_backtest_por_provincia.csv", index=False)

# ------------------------------------------------------------------ 3. Precio_m2: HW vs seasonal naive por provincia
rows = []
for prov in PROVS:
    s = df[df.Provincia == prov].sort_values("Trimestre")["Precio_m2"].dropna()
    s.index = pd.RangeIndex(len(s))
    tr, te = s.iloc[:-8], s.iloc[-8:]
    naive = np.full(8, float(tr.iloc[-1]))
    hw = ExponentialSmoothing(tr, trend="add", damped_trend=True, seasonal="add", seasonal_periods=4).fit(optimized=True)
    phw = np.asarray(hw.forecast(8))
    sn = np.resize(np.tile(tr.iloc[-4:].values, 3), 8)
    m_hw, u_hw = mu(te.values, phw, naive)
    m_sn, u_sn = mu(te.values, sn, naive)
    rows.append({"prov": prov, "MAPE_HW": m_hw, "U2_HW": u_hw, "MAPE_SN": m_sn, "MAPE_naive": mu(te.values, naive, naive)[0],
                 "phi": float(hw.params.get("damping_trend", np.nan))})
ph = pd.DataFrame(rows)
res["Precio_HW"] = {"MAPE_mediana": float(ph.MAPE_HW.median()), "U2_mediana": float(ph.U2_HW.median()),
                    "pct_prov_HW_mejor_que_SN": float((ph.MAPE_HW < ph.MAPE_SN).mean() * 100),
                    "pct_prov_HW_mejor_que_naive": float((ph.MAPE_HW < ph.MAPE_naive).mean() * 100),
                    "MAPE_SN_mediana": float(ph.MAPE_SN.median()), "MAPE_naive_mediana": float(ph.MAPE_naive.median()),
                    "phi_mediana": float(ph.phi.median())}
# Duelo nacional de la celda 46 (origen del "79 %")
s = df.groupby("Trimestre")["Precio_m2"].mean().sort_index().dropna()
s.index = pd.DatetimeIndex(s.index, freq="QS-JAN")
tr, te = s.iloc[:-8], s.iloc[-8:]
hw = ExponentialSmoothing(tr, trend="add", seasonal="add", seasonal_periods=4).fit(optimized=True)
sn = np.resize(np.tile(tr.iloc[-4:].values, 3), 8)
m_hw = float(np.mean(np.abs((te.values - hw.forecast(8).values) / te.values)) * 100)
m_sn = float(np.mean(np.abs((te.values - sn) / te.values)) * 100)
res["Precio_duelo_nacional_celda46"] = {"MAPE_HW": m_hw, "MAPE_SN": m_sn, "mejora_pct": (m_sn - m_hw) / m_sn * 100}

# ------------------------------------------------------------------ 4. Euribor / IPC
res["Euribor_usado"] = {"2025(csv)": 2.50, "2026": 2.00, "2027": 2.10, "2028": 2.30, "2029": 2.15, "2030": 2.15}
res["IPC_usado"] = {"2025(csv)": 2.80, "2026": 1.88, "2027": 2.10, "2028": 2.00, "2029": 2.00, "2030": 2.00}
res["BCE_dic2025_supuestos_EURIBOR3M"] = {"2025": 2.2, "2026": 2.0, "2027": 2.1, "2028": 2.3,
                                           "fuente": "https://www.ecb.europa.eu/press/projections/html/ecb.projections202512_eurosystemstaff~12ead61977.en.html"}
res["BCE_dic2025_HICP_zona_euro"] = {"2025": 2.1, "2026": 1.9, "2027": 1.8, "2028": 2.0}
try:
    eur = {}
    for k in ["EURIBOR1YD_", "EURIBOR3MD_"]:
        url = f"https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.{k}.HSTA?startPeriod=2005-01&endPeriod=2025-12&format=csvdata"
        t = pd.read_csv(pd.io.common.StringIO(requests.get(url, timeout=60).text))
        t["d"] = pd.PeriodIndex(t["TIME_PERIOD"], freq="M").to_timestamp()
        eur[k] = t.set_index("d")["OBS_VALUE"].resample("QS").mean()
    ds_e = df.groupby("Trimestre")["Euribor"].mean()
    res["Euribor_dataset_vs_BCE"] = {
        "MAE_vs_12M": float((ds_e - eur["EURIBOR1YD_"].reindex(ds_e.index)).abs().mean()),
        "MAE_vs_3M": float((ds_e - eur["EURIBOR3MD_"].reindex(ds_e.index)).abs().mean()),
        "media_2025_12M_BCE": float(eur["EURIBOR1YD_"]["2025"].mean()),
        "media_2025_3M_BCE": float(eur["EURIBOR3MD_"]["2025"].mean()),
        "media_2025_dataset": float(ds_e["2025"].mean()),
        "fuente": "data-api.ecb.europa.eu FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA / EURIBOR3MD_.HSTA"}
except Exception as e:
    res["Euribor_dataset_vs_BCE"] = f"error: {e}"
res["IPC_dataset_media_2025"] = float(df[df.Trimestre.dt.year == 2025]["IPC"].mean())
res["Euribor_dataset_media_2025"] = float(df[df.Trimestre.dt.year == 2025]["Euribor"].mean())

# 2025 en el CSV: valores 'ffill' del último dato disponible en los 4 trimestres
c25 = pred[pred.trimestre.str.startswith("2025")]
obs = df[df.Trimestre.dt.year == 2025]
chk = []
for var in ["Tasa_Paro", "Precio_m2"]:
    a = c25[c25.variable == var].pivot(index="provincia", columns="trimestre", values="valor")
    o = obs.pivot(index="Provincia", columns="Trimestre", values=var)
    chk.append({"var": var, "csv_constante_en_2025_pct_prov": float((a.nunique(axis=1) == 1).mean() * 100),
                "csv_2025Q1_igual_obs_2025Q4_pct": float((np.isclose(a["2025-01"], o[pd.Timestamp("2025-10-01")].reindex(a.index))).mean() * 100),
                "MAPE_csv_2025Q1_vs_obs_2025Q1": float(np.mean(np.abs(a["2025-01"] - o[pd.Timestamp("2025-01-01")].reindex(a.index)) / o[pd.Timestamp("2025-01-01")].reindex(a.index)) * 100)})
res["CSV_2025_ffill"] = chk

(OUT / "03_projections_audit.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
