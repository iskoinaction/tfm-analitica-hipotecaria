import re
import unicodedata
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_percentage_error, r2_score
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

_ARTIFACTS = None

BCE_SCENARIOS = {
    "Euribor": {"2026": 2.00, "2027": 2.10, "2028": 2.30, "2029": 2.15, "2030": 2.15, "2031": 2.15},
    "IPC": {"2026": 1.88, "2027": 2.10, "2028": 2.00, "2029": 2.00, "2030": 2.00, "2031": 2.00},
}

LAG_COLS = [
    "Precio_m2", "Transmisiones_Total", "Spread_Hipotecas", "Tasa_Paro", "IPC",
    "Indice_Mano_Obra", "Indice_Materiales", "Hipotecas_Total", "Pob_Ext",
    "Poblacion", "PIB_pc", "tasa_ahorro", "Edad_Media",
]

ROLLING_COLS = ["Hipotecas_Total", "Precio_m2", "Transmisiones_Total", "Tasa_Paro", "PIB_pc"]
YOY_COLS = ["Hipotecas_Total", "Precio_m2", "Transmisiones_Total", "PIB_pc"]
DIFF_COLS = ["Hipotecas_Total", "Precio_m2", "Tasa_Paro", "Euribor"]

WEIGHTED_NAC_VARS = [
    "Precio_m2_lag1", "Precio_m2_lag2", "Precio_m2_lag4",
    "Tasa_Paro_lag1", "Tasa_Paro_lag4", "IPC_lag1", "PIB_pc_lag1",
    "PIB_pc_lag4", "Indice_Mano_Obra_lag1", "Indice_Materiales_lag1",
    "tasa_ahorro_lag1", "Edad_Media_lag1", "Spread_Hipotecas_lag1",
    "Spread_Hipotecas_lag2", "Precio_m2_rmean4", "Tasa_Paro_rmean4",
    "Precio_m2_yoy", "PIB_pc_yoy", "Precio_m2_diff1", "Tasa_Paro_diff1",
    "Accesibilidad",
]

SUM_NAC_VARS = {
    "Hipotecas_Total": "sum",
    "Transmisiones_Total_lag1": "sum",
    "Transmisiones_Total_lag4": "sum",
    "Hipotecas_Total_lag1": "sum",
    "Hipotecas_Total_lag4": "sum",
    "Pob_Ext_lag1": "sum",
    "Poblacion_lag1": "sum",
    "Hipotecas_Total_rmean4": "sum",
    "Transmisiones_Total_rmean4": "sum",
    "Hipotecas_Total_yoy": "mean",
    "Transmisiones_Total_yoy": "mean",
    "Hipotecas_Total_diff1": "sum",
}


def quarter_key(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    match = re.match(r"^(\d{4})-?Q([1-4])$", text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)}-Q{match.group(2)}"
    dt = pd.to_datetime(text, errors="coerce")
    if pd.isna(dt):
        return None
    return f"{dt.year}-Q{dt.quarter}"


def quarter_timestamp(key_or_year):
    key = quarter_key(key_or_year)
    if not key:
        return None
    year, q = key.split("-Q")
    return pd.Timestamp(year=int(year), month=(int(q) - 1) * 3 + 1, day=1)


def clean_key(value):
    text = "" if value is None else str(value).strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def resolve_province(province, available_provs):
    if not province:
        return ""
    by_clean = {clean_key(p): p for p in available_provs}
    key = clean_key(province)
    aliases = {
        "madrid": "comunidad de madrid",
        "asturias": "principado de asturias",
        "murcia": "region de murcia",
        "navarra": "comunidad foral de navarra",
        "baleares": "islas baleares",
        "illes balears": "islas baleares",
    }
    return by_clean.get(key) or by_clean.get(aliases.get(key, "")) or province


def bce_value(variable, ts):
    dates = pd.date_range("2026-01-01", "2030-12-31", freq="QS")
    annual = {int(k): v for k, v in BCE_SCENARIOS[variable].items()}
    annual_series = pd.Series({pd.Timestamp(f"{year}-01-01"): val for year, val in annual.items()})
    last_year = max(annual)
    annual_series.loc[pd.Timestamp(f"{last_year + 1}-01-01")] = annual_series.iloc[-1]
    quarterly = annual_series.sort_index().resample("QS").interpolate(method="linear").reindex(dates)
    key = pd.Timestamp(ts)
    if key in quarterly.index:
        return float(quarterly.loc[key])
    year_val = BCE_SCENARIOS[variable].get(str(key.year))
    return float(year_val if year_val is not None else annual_series.iloc[-1])


def _safe_last(values, n, default=np.nan):
    clean = pd.Series(values).dropna().values
    return float(clean[-n]) if len(clean) >= n else default


def _safe_window(values, n=4):
    return pd.Series(values).dropna().tail(n)


def _prepare_panel(raw_df, label_encoder=None, fit_encoder=False):
    dfp = raw_df.copy()
    dfp["Trimestre"] = pd.to_datetime(dfp["Trimestre"])
    dfp = dfp.sort_values(["Provincia", "Trimestre"]).reset_index(drop=True)

    for col in ["tasa_ahorro", "Indice_Mano_Obra", "Indice_Materiales", "IPC", "PIB_pc", "Transmisiones_Total", "Pob_Ext"]:
        if col in dfp.columns:
            dfp[col] = dfp.groupby("Provincia")[col].transform(lambda x: x.ffill().bfill())

    for col in LAG_COLS:
        if col in dfp.columns:
            dfp[f"{col}_lag1"] = dfp.groupby("Provincia")[col].shift(1)
            dfp[f"{col}_lag2"] = dfp.groupby("Provincia")[col].shift(2)
            dfp[f"{col}_lag4"] = dfp.groupby("Provincia")[col].shift(4)

    for col in ROLLING_COLS:
        if col in dfp.columns:
            shifted = dfp.groupby("Provincia")[col].shift(1)
            dfp[f"{col}_rmean4"] = shifted.rolling(4, min_periods=2).mean()
            dfp[f"{col}_rstd4"] = shifted.rolling(4, min_periods=2).std()
            dfp[f"{col}_rmin4"] = shifted.rolling(4, min_periods=2).min()
            dfp[f"{col}_rmax4"] = shifted.rolling(4, min_periods=2).max()

    for col in YOY_COLS:
        if col in dfp.columns:
            lag1 = dfp.groupby("Provincia")[col].shift(1)
            lag5 = dfp.groupby("Provincia")[col].shift(5)
            dfp[f"{col}_yoy"] = (lag1 - lag5) / lag5.abs().clip(lower=1)

    for col in DIFF_COLS:
        if col in dfp.columns:
            dfp[f"{col}_diff1"] = dfp.groupby("Provincia")[col].shift(1).diff()
            dfp[f"{col}_diff4"] = dfp.groupby("Provincia")[col].shift(1).diff(4)

    dfp["Euribor_ma4"] = dfp.groupby("Provincia")["Euribor"].transform(lambda x: x.shift(1).rolling(4).mean())
    dfp["Euribor_lag1"] = dfp.groupby("Provincia")["Euribor"].shift(1)
    dfp["Euribor_lag2"] = dfp.groupby("Provincia")["Euribor"].shift(2)
    dfp["Euribor_change"] = dfp["Euribor"] - dfp["Euribor_lag1"]

    dfp["Euribor_x_Precio"] = dfp["Euribor"] * dfp["Precio_m2_lag1"]
    dfp["Accesibilidad"] = (dfp["PIB_pc_lag1"] * (1 - dfp["Tasa_Paro_lag1"] / 100)) / dfp["Precio_m2_lag1"].clip(lower=1)
    dfp["Hip_per_cap"] = dfp["Hipotecas_Total_lag1"] / dfp["Poblacion_lag1"].clip(lower=1)
    dfp["Pob_Ext_ratio"] = dfp["Pob_Ext_lag1"] / dfp["Poblacion_lag1"].clip(lower=1)
    dfp["Precio_x_Paro"] = dfp["Precio_m2_lag1"] * dfp["Tasa_Paro_lag1"]
    dfp["Spread_x_Euribor"] = dfp["Spread_Hipotecas_lag1"] * dfp["Euribor"]
    dfp["Trans_per_cap"] = dfp["Transmisiones_Total_lag1"] / dfp["Poblacion_lag1"].clip(lower=1)
    dfp["Hip_trans_ratio"] = dfp["Hipotecas_Total_lag1"] / dfp["Transmisiones_Total_lag1"].clip(lower=1)
    dfp["Hip_lag1_vs_rmean"] = dfp["Hipotecas_Total_lag1"] / dfp["Hipotecas_Total_rmean4"].clip(lower=1)
    dfp["Precio_lag1_vs_rmean"] = dfp["Precio_m2_lag1"] / dfp["Precio_m2_rmean4"].clip(lower=1)

    dfp["Q"] = dfp["Trimestre"].dt.quarter
    dfp["Year"] = dfp["Trimestre"].dt.year
    dfp["Trend"] = dfp.groupby("Provincia").cumcount()
    for q in [1, 2, 3, 4]:
        dfp[f"Q{q}"] = (dfp["Q"] == q).astype(int)

    if fit_encoder or label_encoder is None:
        label_encoder = LabelEncoder()
        dfp["Prov_code"] = label_encoder.fit_transform(dfp["Provincia"])
    else:
        dfp["Prov_code"] = label_encoder.transform(dfp["Provincia"])

    dfp = dfp.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    features = [
        c for c in dfp.columns
        if any([
            c.endswith("_lag1"), c.endswith("_lag2"), c.endswith("_lag4"),
            c.endswith("_rmean4"), c.endswith("_rstd4"), c.endswith("_rmin4"), c.endswith("_rmax4"),
            c.endswith("_yoy"), c.endswith("_diff1"), c.endswith("_diff4"),
            c in [
                "Euribor", "Euribor_ma4", "Euribor_change", "Euribor_x_Precio",
                "Accesibilidad", "Hip_per_cap", "Pob_Ext_ratio", "Precio_x_Paro",
                "Spread_x_Euribor", "Trans_per_cap", "Hip_trans_ratio",
                "Hip_lag1_vs_rmean", "Precio_lag1_vs_rmean", "Q", "Q1", "Q2",
                "Q3", "Q4", "Year", "Trend", "Prov_code",
            ],
        ])
    ]
    return dfp, features, label_encoder


def _build_national_frame(panel_df):
    dfp = panel_df.copy()
    weights = dfp["Poblacion_lag1"].fillna(1)
    for var in WEIGHTED_NAC_VARS:
        if var in dfp.columns:
            dfp[f"{var}_pond"] = dfp[var] * weights

    sum_agg = {var: agg for var, agg in SUM_NAC_VARS.items() if var in dfp.columns}
    pond_agg = {f"{var}_pond": "sum" for var in WEIGHTED_NAC_VARS if f"{var}_pond" in dfp.columns}
    pond_agg["Poblacion_lag1"] = "sum"
    extra_agg = {"Euribor": "mean", "Q": "first", "Trend": "mean"}
    for col in ["Euribor_ma4", "Euribor_change", "Hipotecas_Total_rstd4"]:
        if col in dfp.columns:
            extra_agg[col] = "mean"

    df_nac = dfp.groupby("Trimestre").agg({**sum_agg, **pond_agg, **extra_agg}).sort_index()
    pop_total = df_nac["Poblacion_lag1"].replace(0, np.nan)
    for var in WEIGHTED_NAC_VARS:
        pcol = f"{var}_pond"
        if pcol in df_nac.columns:
            df_nac[var] = df_nac[pcol] / pop_total
            df_nac.drop(columns=[pcol], inplace=True)

    df_nac["Hip_total_lag1_nac"] = df_nac["Hipotecas_Total"].shift(1)
    df_nac["Hip_total_lag2_nac"] = df_nac["Hipotecas_Total"].shift(2)
    df_nac["Hip_total_lag4_nac"] = df_nac["Hipotecas_Total"].shift(4)
    df_nac["Hip_total_rmean4_nac"] = df_nac["Hipotecas_Total"].shift(1).rolling(4).mean()
    df_nac["Hip_yoy_nac"] = (df_nac["Hipotecas_Total"].shift(1) - df_nac["Hipotecas_Total"].shift(5)) / df_nac["Hipotecas_Total"].shift(5).abs().clip(lower=1)
    df_nac["Hip_momentum"] = df_nac["Hipotecas_Total"].shift(1) - df_nac["Hipotecas_Total"].shift(2)
    df_nac["Hip_vs_rmean"] = df_nac["Hip_total_lag1_nac"] / df_nac["Hip_total_rmean4_nac"].clip(lower=1)
    df_nac["Euribor_x_Precio_nac"] = df_nac["Euribor"] * df_nac["Precio_m2_lag1"]
    df_nac["Accesibilidad_nac"] = (df_nac["PIB_pc_lag1"] * (1 - df_nac["Tasa_Paro_lag1"] / 100)) / df_nac["Precio_m2_lag1"].clip(lower=1)
    df_nac["Hip_per_cap_nac"] = df_nac["Hip_total_lag1_nac"] / df_nac["Poblacion_lag1"].clip(lower=1)
    for q in [1, 2, 3, 4]:
        df_nac[f"Q{q}"] = (df_nac["Q"] == q).astype(int)

    df_nac = df_nac.replace([np.inf, -np.inf], np.nan).dropna()
    features = [c for c in df_nac.columns if c != "Hipotecas_Total"]
    return df_nac, features


def _prediction_lookup(df_prov_preds):
    if df_prov_preds is None or df_prov_preds.empty:
        return {}
    pred = df_prov_preds.copy()
    pred["quarter_key"] = pred["trimestre"].apply(quarter_key)
    lookup = {}
    for (prov, qkey), grp in pred.groupby(["provincia", "quarter_key"]):
        lookup[(prov, qkey)] = dict(zip(grp["variable"], grp["valor"]))
    return lookup


def _train_artifacts(df_hist, df_prov_preds):
    global _ARTIFACTS
    if _ARTIFACTS is not None:
        return _ARTIFACTS

    raw = df_hist.copy()
    raw["Trimestre"] = pd.to_datetime(raw["Trimestre"])
    raw = raw.sort_values(["Provincia", "Trimestre"]).reset_index(drop=True)

    panel, features_prov, label_encoder = _prepare_panel(raw, fit_encoder=True)
    quarters = sorted(panel["Trimestre"].unique())
    test_start = quarters[-8]
    df_train = panel[panel["Trimestre"] < test_start].copy()
    df_test = panel[panel["Trimestre"] >= test_start].copy()

    rf_prov_eval = RandomForestRegressor(
        n_estimators=300, max_depth=15, min_samples_leaf=5,
        max_features="sqrt", random_state=42, n_jobs=-1,
    )
    rf_prov_eval.fit(df_train[features_prov], df_train["Hipotecas_Total"])
    pred_prov = rf_prov_eval.predict(df_test[features_prov])

    rf_prov_final = RandomForestRegressor(
        n_estimators=300, max_depth=15, min_samples_leaf=5,
        max_features="sqrt", random_state=42, n_jobs=-1,
    )
    rf_prov_final.fit(panel[features_prov], panel["Hipotecas_Total"])

    prov_mape = round(mean_absolute_percentage_error(df_test["Hipotecas_Total"], pred_prov) * 100, 2)
    prov_mape_by_prov = {}
    for prov in sorted(panel["Provincia"].unique()):
        mask = df_test["Provincia"] == prov
        if mask.any():
            prov_mape_by_prov[prov] = round(mean_absolute_percentage_error(df_test.loc[mask, "Hipotecas_Total"], pred_prov[mask.values]) * 100, 2)

    nac_df, features_nac = _build_national_frame(panel)
    Xn, yn = nac_df[features_nac], nac_df["Hipotecas_Total"]
    rf_nac_eval = RandomForestRegressor(
        n_estimators=200, max_depth=10, min_samples_leaf=3,
        max_features="sqrt", random_state=42,
    )
    rf_nac_eval.fit(Xn.iloc[:-8], yn.iloc[:-8])
    pred_nac = rf_nac_eval.predict(Xn.iloc[-8:])

    rf_nac_final = RandomForestRegressor(
        n_estimators=200, max_depth=10, min_samples_leaf=3,
        max_features="sqrt", random_state=42,
    )
    rf_nac_final.fit(Xn, yn)

    raw_columns = raw.columns.tolist()
    _ARTIFACTS = {
        "raw": raw,
        "raw_columns": raw_columns,
        "panel": panel,
        "features_prov": features_prov,
        "features_nac": features_nac,
        "label_encoder": label_encoder,
        "rf_prov_final": rf_prov_final,
        "rf_nac_final": rf_nac_final,
        "prov_mape": prov_mape,
        "prov_mape_by_prov": prov_mape_by_prov,
        "prov_r2": round(float(r2_score(df_test["Hipotecas_Total"], pred_prov)), 4),
        "nac_df": nac_df,
        "nac_mape": round(mean_absolute_percentage_error(yn.iloc[-8:], pred_nac) * 100, 2),
        "nac_r2": round(float(r2_score(yn.iloc[-8:], pred_nac)), 4),
        "feature_medians": panel[features_prov].median(numeric_only=True),
        "nac_feature_medians": Xn.median(numeric_only=True),
        "available_provs": sorted(panel["Provincia"].unique().tolist()),
        "macro_lookup": _prediction_lookup(df_prov_preds),
    }
    return _ARTIFACTS


def _future_raw_rows(art, history, ts, euribor_override=None):
    qkey = quarter_key(ts)
    latest = history.sort_values("Trimestre").groupby("Provincia").tail(1).set_index("Provincia")
    rows = []
    for prov in art["available_provs"]:
        base = latest.loc[prov]
        row = {col: base[col] for col in art["raw_columns"] if col in base.index}
        row["Provincia"] = prov
        row["Trimestre"] = pd.Timestamp(ts)
        row["Hipotecas_Total"] = np.nan
        macro = art["macro_lookup"].get((prov, qkey), {})
        for col in art["raw_columns"]:
            if col in ["Provincia", "Trimestre", "Hipotecas_Total"]:
                continue
            if col in macro and pd.notna(macro[col]):
                row[col] = float(macro[col])
            elif col == "Euribor":
                row[col] = float(euribor_override if euribor_override is not None else bce_value("Euribor", ts))
            elif col == "IPC":
                row[col] = float(bce_value("IPC", ts))
            elif pd.isna(row.get(col)):
                row[col] = float(base[col])
        rows.append(row)
    return pd.DataFrame(rows, columns=art["raw_columns"])


def _future_feature_rows(art, history, raw_rows):
    rows = []
    history = history.sort_values(["Provincia", "Trimestre"])
    by_prov = {p: g.sort_values("Trimestre") for p, g in history.groupby("Provincia")}

    for _, raw_row in raw_rows.iterrows():
        prov = raw_row["Provincia"]
        hist = by_prov[prov]
        feat = raw_row.to_dict()
        for col in LAG_COLS:
            values = hist[col].values
            feat[f"{col}_lag1"] = _safe_last(values, 1)
            feat[f"{col}_lag2"] = _safe_last(values, 2)
            feat[f"{col}_lag4"] = _safe_last(values, 4)

        for col in ROLLING_COLS:
            window = _safe_window(hist[col].values, 4)
            feat[f"{col}_rmean4"] = float(window.mean()) if len(window) >= 2 else np.nan
            feat[f"{col}_rstd4"] = float(window.std(ddof=1)) if len(window) >= 2 else np.nan
            feat[f"{col}_rmin4"] = float(window.min()) if len(window) >= 2 else np.nan
            feat[f"{col}_rmax4"] = float(window.max()) if len(window) >= 2 else np.nan

        for col in YOY_COLS:
            lag1 = _safe_last(hist[col].values, 1)
            lag5 = _safe_last(hist[col].values, 5)
            feat[f"{col}_yoy"] = (lag1 - lag5) / max(abs(lag5), 1) if pd.notna(lag1) and pd.notna(lag5) else np.nan

        for col in DIFF_COLS:
            lag1 = _safe_last(hist[col].values, 1)
            lag2 = _safe_last(hist[col].values, 2)
            lag5 = _safe_last(hist[col].values, 5)
            feat[f"{col}_diff1"] = lag1 - lag2 if pd.notna(lag1) and pd.notna(lag2) else np.nan
            feat[f"{col}_diff4"] = lag1 - lag5 if pd.notna(lag1) and pd.notna(lag5) else np.nan

        eur_hist = pd.Series(hist["Euribor"].values).dropna()
        feat["Euribor_ma4"] = float(eur_hist.tail(4).mean())
        feat["Euribor_lag1"] = _safe_last(hist["Euribor"].values, 1)
        feat["Euribor_lag2"] = _safe_last(hist["Euribor"].values, 2)
        feat["Euribor_change"] = feat["Euribor"] - feat["Euribor_lag1"]
        feat["Euribor_x_Precio"] = feat["Euribor"] * feat["Precio_m2_lag1"]
        feat["Accesibilidad"] = (feat["PIB_pc_lag1"] * (1 - feat["Tasa_Paro_lag1"] / 100)) / max(feat["Precio_m2_lag1"], 1)
        feat["Hip_per_cap"] = feat["Hipotecas_Total_lag1"] / max(feat["Poblacion_lag1"], 1)
        feat["Pob_Ext_ratio"] = feat["Pob_Ext_lag1"] / max(feat["Poblacion_lag1"], 1)
        feat["Precio_x_Paro"] = feat["Precio_m2_lag1"] * feat["Tasa_Paro_lag1"]
        feat["Spread_x_Euribor"] = feat["Spread_Hipotecas_lag1"] * feat["Euribor"]
        feat["Trans_per_cap"] = feat["Transmisiones_Total_lag1"] / max(feat["Poblacion_lag1"], 1)
        feat["Hip_trans_ratio"] = feat["Hipotecas_Total_lag1"] / max(feat["Transmisiones_Total_lag1"], 1)
        feat["Hip_lag1_vs_rmean"] = feat["Hipotecas_Total_lag1"] / max(feat["Hipotecas_Total_rmean4"], 1)
        feat["Precio_lag1_vs_rmean"] = feat["Precio_m2_lag1"] / max(feat["Precio_m2_rmean4"], 1)
        feat["Q"] = pd.Timestamp(raw_row["Trimestre"]).quarter
        feat["Year"] = pd.Timestamp(raw_row["Trimestre"]).year
        feat["Trend"] = len(hist)
        for q in [1, 2, 3, 4]:
            feat[f"Q{q}"] = int(feat["Q"] == q)
        feat["Prov_code"] = int(art["label_encoder"].transform([prov])[0])
        rows.append(feat)

    feats = pd.DataFrame(rows)
    for col in art["features_prov"]:
        if col not in feats.columns:
            feats[col] = art["feature_medians"].get(col, 0.0)
    feats[art["features_prov"]] = feats[art["features_prov"]].replace([np.inf, -np.inf], np.nan).fillna(art["feature_medians"])
    return feats


def _national_future_row(art, feature_rows, national_history):
    row = {}
    weights = feature_rows["Poblacion_lag1"].replace(0, np.nan).fillna(1)
    pop_total = float(weights.sum())

    for var in WEIGHTED_NAC_VARS:
        if var in feature_rows.columns:
            row[var] = float((feature_rows[var] * weights).sum() / pop_total)

    for var, agg in SUM_NAC_VARS.items():
        if var == "Hipotecas_Total":
            continue
        if var in feature_rows.columns:
            row[var] = float(feature_rows[var].sum() if agg == "sum" else feature_rows[var].mean())

    row["Poblacion_lag1"] = float(feature_rows["Poblacion_lag1"].sum())
    row["Euribor"] = float(feature_rows["Euribor"].mean())
    row["Q"] = int(feature_rows["Q"].iloc[0])
    row["Trend"] = float(feature_rows["Trend"].mean())
    for col in ["Euribor_ma4", "Euribor_change", "Hipotecas_Total_rstd4"]:
        if col in feature_rows.columns:
            row[col] = float(feature_rows[col].mean())

    hist = list(national_history)
    row["Hip_total_lag1_nac"] = hist[-1]
    row["Hip_total_lag2_nac"] = hist[-2]
    row["Hip_total_lag4_nac"] = hist[-4]
    row["Hip_total_rmean4_nac"] = float(np.mean(hist[-4:]))
    row["Hip_yoy_nac"] = (hist[-1] - hist[-5]) / max(abs(hist[-5]), 1)
    row["Hip_momentum"] = hist[-1] - hist[-2]
    row["Hip_vs_rmean"] = row["Hip_total_lag1_nac"] / max(row["Hip_total_rmean4_nac"], 1)
    row["Euribor_x_Precio_nac"] = row["Euribor"] * row.get("Precio_m2_lag1", 0)
    row["Accesibilidad_nac"] = (row.get("PIB_pc_lag1", 0) * (1 - row.get("Tasa_Paro_lag1", 0) / 100)) / max(row.get("Precio_m2_lag1", 1), 1)
    row["Hip_per_cap_nac"] = row["Hip_total_lag1_nac"] / max(row.get("Poblacion_lag1", 1), 1)
    for q in [1, 2, 3, 4]:
        row[f"Q{q}"] = int(row["Q"] == q)

    out = pd.DataFrame([row])
    for col in art["features_nac"]:
        if col not in out.columns:
            out[col] = art["nac_feature_medians"].get(col, 0.0)
    out[art["features_nac"]] = out[art["features_nac"]].replace([np.inf, -np.inf], np.nan).fillna(art["nac_feature_medians"])
    return out


def _forecast_future(art, euribor_overrides=None, stop_key=None):
    euribor_overrides = euribor_overrides or {}
    future_qs = pd.date_range("2026-01-01", "2030-12-31", freq="QS")
    raw_prov = art["raw"].copy()
    raw_nac = art["raw"].copy()
    national_history = art["raw"].groupby("Trimestre")["Hipotecas_Total"].sum().sort_index().tolist()

    prov_by_q = {}
    scaled_by_q = {}
    nac_by_q = {}
    prov_features_by_q = {}
    nac_features_by_q = {}

    for ts in future_qs:
        qkey = quarter_key(ts)
        override = euribor_overrides.get(qkey)

        rows_prov = _future_raw_rows(art, raw_prov, ts, override)
        features_prov = _future_feature_rows(art, raw_prov, rows_prov)
        prov_preds = art["rf_prov_final"].predict(features_prov[art["features_prov"]])
        prov_df = pd.DataFrame({"Provincia": features_prov["Provincia"].values, "Hipotecas_Total": prov_preds})

        rows_nac = _future_raw_rows(art, raw_nac, ts, override)
        features_nac_prov = _future_feature_rows(art, raw_nac, rows_nac)
        nac_row = _national_future_row(art, features_nac_prov, national_history)
        nac_pred = float(art["rf_nac_final"].predict(nac_row[art["features_nac"]])[0])

        prov_by_q[qkey] = prov_df.copy()
        nac_by_q[qkey] = nac_pred
        prov_features_by_q[qkey] = features_prov.copy()
        nac_features_by_q[qkey] = nac_row.copy()

        raw_update_prov = rows_prov.copy()
        raw_update_prov["Hipotecas_Total"] = prov_preds
        raw_prov = pd.concat([raw_prov, raw_update_prov], ignore_index=True)

        total_prov = float(np.sum(prov_preds))
        scale = nac_pred / total_prov if total_prov > 0 else 1.0
        scaled_df = prov_df.copy()
        scaled_df["Hipotecas_Total"] = scaled_df["Hipotecas_Total"] * scale
        scaled_by_q[qkey] = scaled_df

        raw_update_nac = rows_nac.copy()
        raw_update_nac["Hipotecas_Total"] = prov_preds * scale
        raw_nac = pd.concat([raw_nac, raw_update_nac], ignore_index=True)
        national_history.append(nac_pred)

        if stop_key and qkey == stop_key:
            break

    labels = list(nac_by_q.keys())
    return {
        "labels": labels,
        "prov_by_q": prov_by_q,
        "scaled_by_q": scaled_by_q,
        "nac_by_q": nac_by_q,
        "prov_features_by_q": prov_features_by_q,
        "nac_features_by_q": nac_features_by_q,
    }


def _with_euribor_prov(features, euribor):
    out = features.copy()
    out["Euribor"] = euribor
    if "Euribor_lag1" in out.columns:
        out["Euribor_change"] = out["Euribor"] - out["Euribor_lag1"]
    if "Precio_m2_lag1" in out.columns:
        out["Euribor_x_Precio"] = out["Euribor"] * out["Precio_m2_lag1"]
    if "Spread_Hipotecas_lag1" in out.columns:
        out["Spread_x_Euribor"] = out["Spread_Hipotecas_lag1"] * out["Euribor"]
    return out


def _with_euribor_nac(features, euribor):
    out = features.copy()
    out["Euribor"] = euribor
    if "Precio_m2_lag1" in out.columns:
        out["Euribor_x_Precio_nac"] = out["Euribor"] * out["Precio_m2_lag1"]
    return out


def _historical_stress(art, ts, province, scenarios):
    if province:
        base_rows = art["panel"][art["panel"]["Trimestre"] == ts].copy()
        if base_rows.empty:
            return []
        results = []
        mask = base_rows["Provincia"] == province
        for sc in scenarios:
            rows = _with_euribor_prov(base_rows, sc["euribor"])
            preds = art["rf_prov_final"].predict(rows[art["features_prov"]])
            total = float(preds[mask.values].sum())
            results.append((sc, total))
        return results

    if ts not in art["nac_df"].index:
        return []
    base_row = art["nac_df"].loc[[ts], art["features_nac"]].copy()
    results = []
    for sc in scenarios:
        row = _with_euribor_nac(base_row, sc["euribor"])
        total = float(art["rf_nac_final"].predict(row[art["features_nac"]])[0])
        results.append((sc, total))
    return results


def _series_value(series, ts):
    return float(series.loc[ts]) if ts in series.index else 0.0


def _feature_importance(model, features):
    imp = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False).head(15)
    return {"labels": imp.index.tolist(), "values": [round(float(v), 4) for v in imp.values]}


def build_demanda_response(df_hist, df_prov_preds, year_req="", prov_req=""):
    art = _train_artifacts(df_hist, df_prov_preds)
    province = resolve_province(prov_req, art["available_provs"])
    is_prov = bool(province)
    if "base_forecast" not in art:
        art["base_forecast"] = _forecast_future(art)
    forecast = art["base_forecast"]

    raw = art["raw"]
    hist_series = (
        raw[raw["Provincia"] == province].groupby("Trimestre")["Hipotecas_Total"].sum().sort_index()
        if is_prov else raw.groupby("Trimestre")["Hipotecas_Total"].sum().sort_index()
    )
    latest_hist_q = hist_series.index.max()

    if year_req and "Q" in str(year_req):
        selected_key = quarter_key(year_req)
        selected_ts = quarter_timestamp(selected_key)
        if is_prov:
            df_q = forecast["prov_by_q"].get(selected_key, pd.DataFrame())
            last_val = float(df_q.loc[df_q["Provincia"] == province, "Hipotecas_Total"].sum()) if not df_q.empty else 0.0
            mape = art["prov_mape_by_prov"].get(province, art["prov_mape"])
            model_label = "RF Provincial"
        else:
            last_val = float(forecast["nac_by_q"].get(selected_key, 0.0))
            mape = art["nac_mape"]
            model_label = "RF_Nac"
        last_q = selected_ts
    elif year_req:
        year_int = int(year_req)
        year_series = hist_series[hist_series.index.year == year_int]
        if year_series.empty:
            return {"error": f"No hay datos para el año {year_req}"}, 404
        last_q = year_series.index.max()
        last_val = float(year_series.loc[last_q])
        mape = art["prov_mape_by_prov"].get(province, art["prov_mape"]) if is_prov else art["nac_mape"]
        model_label = "RF Provincial" if is_prov else "RF_Nac"
    else:
        last_q = latest_hist_q
        last_val = float(hist_series.loc[last_q])
        mape = art["prov_mape_by_prov"].get(province, art["prov_mape"]) if is_prov else art["nac_mape"]
        model_label = "RF Provincial" if is_prov else "RF_Nac"

    prev_q = last_q - pd.DateOffset(years=1)
    prev_key = quarter_key(prev_q)
    if last_q.year >= 2026:
        if is_prov:
            prev_df = forecast["prov_by_q"].get(prev_key, pd.DataFrame())
            prev_val = float(prev_df.loc[prev_df["Provincia"] == province, "Hipotecas_Total"].sum()) if not prev_df.empty else _series_value(hist_series, prev_q)
        else:
            prev_val = float(forecast["nac_by_q"].get(prev_key, _series_value(hist_series, prev_q)))
    else:
        prev_val = _series_value(hist_series, prev_q)
    yoy = round((last_val - prev_val) / prev_val * 100, 1) if prev_val > 0 else 0.0

    if is_prov:
        forecast_values = []
        for key in forecast["labels"]:
            df_q = forecast["prov_by_q"][key]
            forecast_values.append(round(float(df_q.loc[df_q["Provincia"] == province, "Hipotecas_Total"].sum())))
        importance = _feature_importance(art["rf_prov_final"], art["features_prov"])
    else:
        forecast_values = [round(float(forecast["nac_by_q"][key])) for key in forecast["labels"]]
        importance = _feature_importance(art["rf_nac_final"], art["features_nac"])

    available_years = sorted(raw["Trimestre"].dt.year.unique().tolist(), reverse=True)
    available_years += [f"{year}-Q{q}" for year in range(2026, 2031) for q in range(1, 5)]

    result = {
        "available_years": available_years,
        "available_provs": art["available_provs"],
        "feature_importance": importance,
        "forecast": {"labels": forecast["labels"], "values": forecast_values},
        "kpis": {
            "ultimo_trimestre": quarter_key(last_q),
            "hipotecas_total": round(last_val),
            "crecimiento_interanual": yoy,
            "mape_modelo": mape,
            "n_features": len(art["features_prov"] if is_prov else art["features_nac"]),
            "modelo": model_label,
        },
        "serie_historica": {
            "labels": [d.strftime("%Y-%m") for d in hist_series.index],
            "values": [round(float(v)) for v in hist_series.values],
        },
    }

    # Stress test: centered on the selected quarter/year, not on the last historical row.
    base_euribor = bce_value("Euribor", last_q) if last_q.year >= 2026 else float(raw.loc[raw["Trimestre"] == last_q, "Euribor"].mean())
    stress_scenarios = [
        {"name": "BCE Optimista", "euribor": round(max(0.25, base_euribor - 0.50), 2), "color": "#28a745"},
        {"name": "BCE Base", "euribor": round(base_euribor, 2), "color": "#007BC0"},
        {"name": "BCE Adverso", "euribor": round(base_euribor + 1.00, 2), "color": "#dc3545"},
    ]
    stress_results = []
    if last_q.year >= 2026:
        selected_key = quarter_key(last_q)
        for sc in stress_scenarios:
            if is_prov:
                rows = forecast["prov_features_by_q"][selected_key]
                shocked_rows = _with_euribor_prov(rows, sc["euribor"])
                preds = art["rf_prov_final"].predict(shocked_rows[art["features_prov"]])
                mask = rows["Provincia"] == province
                total = float(preds[mask.values].sum())
            else:
                row = _with_euribor_nac(forecast["nac_features_by_q"][selected_key], sc["euribor"])
                total = float(art["rf_nac_final"].predict(row[art["features_nac"]])[0])
            stress_results.append((sc, total))
    else:
        stress_results = _historical_stress(art, last_q, province, stress_scenarios)

    result["stress_test"] = [
        {
            "name": sc["name"],
            "euribor": sc["euribor"],
            "hipotecas": round(float(total)),
            "color": sc["color"],
            "diff_pct": round((float(total) - last_val) / last_val * 100, 1) if last_val > 0 else 0.0,
        }
        for sc, total in stress_results
    ]

    if last_q.year >= 2026:
        selected_key = quarter_key(last_q)
        top_df = forecast["prov_by_q"].get(selected_key, pd.DataFrame())
        if not is_prov and selected_key in forecast["scaled_by_q"]:
            top_df = forecast["scaled_by_q"][selected_key]
        top_prov = top_df.groupby("Provincia")["Hipotecas_Total"].sum() if not top_df.empty else pd.Series(dtype=float)
    else:
        top_df = raw[raw["Trimestre"] == last_q]
        top_prov = top_df.groupby("Provincia")["Hipotecas_Total"].sum()
    top_prov = top_prov.sort_values(ascending=False).head(10)
    result["top_provincias"] = {
        "labels": top_prov.index.tolist(),
        "values": [round(float(v)) for v in top_prov.values],
    }

    result["benchmark"] = {
        "modelos": [
            {"nombre": "RF_Nac", "tipo": "ML Provincial", "mape": f"{art['nac_mape']}%", "ventaja": "Modelo nacional dedicado, no suma errores provinciales"},
            {"nombre": "RF Provincial", "tipo": "ML Provincial", "mape": f"{art['prov_mape']}%", "ventaja": "Predicción territorial con encoding provincial y lags"},
            {"nombre": "SARIMAX / VAR", "tipo": "Econométrico", "mape": "Referencia", "ventaja": "Contraste estructural, shocks e interpretabilidad"},
        ]
    }

    return result, 200
