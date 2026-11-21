"""Utilidades comunes de la auditoría DS (Fase V).

Replica literalmente el feature engineering de
`notebooks acabados/4. econometria_y_demanda_hipotecaria.ipynb` (celdas 7, 11, 13, 19)
para poder reproducir y perturbar el modelo RF_Nac.
Solo lectura de datos; no escribe fuera de reports/audit/02_ds/.
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "notebooks acabados" / "dataset_final_tfm.csv"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def load_raw():
    df = pd.read_csv(DATA)
    df["Trimestre"] = pd.to_datetime(df["Trimestre"])
    return df


def build_panel(df_in, accesibilidad_contemporanea=True, euribor_contemporaneo=True):
    """Celda 7 (+ efecto colateral de la celda 11) del notebook 4.

    accesibilidad_contemporanea=True reproduce lo que ocurrió en el notebook: la celda 11
    (mapa) sobrescribe df['Accesibilidad'] con PIB_pc, Tasa_Paro y Precio_m2 del MISMO trimestre
    y esa columna entra después en features_ml y en el agregado nacional.
    euribor_contemporaneo=False sustituye Euribor (media del trimestre t) por su lag1 en las
    features que lo usan (Euribor, Euribor_change, Euribor_x_Precio, Spread_x_Euribor).
    """
    df = df_in.copy()
    df = df.sort_values(["Provincia", "Trimestre"]).reset_index(drop=True)
    for c in ["tasa_ahorro", "Indice_Mano_Obra", "Indice_Materiales", "IPC", "PIB_pc", "Transmisiones_Total", "Pob_Ext"]:
        df[c] = df.groupby("Provincia")[c].transform(lambda x: x.ffill().bfill())
    lag_cols = ["Precio_m2", "Transmisiones_Total", "Spread_Hipotecas", "Tasa_Paro", "IPC",
                "Indice_Mano_Obra", "Indice_Materiales", "Hipotecas_Total", "Pob_Ext", "Poblacion",
                "PIB_pc", "tasa_ahorro", "Edad_Media"]
    new = {}
    g = df.groupby("Provincia")
    for col in lag_cols:
        new[f"{col}_lag1"] = g[col].shift(1)
        new[f"{col}_lag2"] = g[col].shift(2)
        new[f"{col}_lag4"] = g[col].shift(4)
    for col in ["Hipotecas_Total", "Precio_m2", "Transmisiones_Total", "Tasa_Paro", "PIB_pc"]:
        s = g[col].shift(1)
        # NOTA: rolling NO agrupado por provincia (igual que el notebook); las filas
        # contaminadas entre provincias caen luego en el dropna (primeras 5 de cada provincia).
        new[f"{col}_rmean4"] = s.rolling(4, min_periods=2).mean()
        new[f"{col}_rstd4"] = s.rolling(4, min_periods=2).std()
        new[f"{col}_rmin4"] = s.rolling(4, min_periods=2).min()
        new[f"{col}_rmax4"] = s.rolling(4, min_periods=2).max()
    for col in ["Hipotecas_Total", "Precio_m2", "Transmisiones_Total", "PIB_pc"]:
        l1 = g[col].shift(1)
        l5 = g[col].shift(5)
        new[f"{col}_yoy"] = (l1 - l5) / l5.abs().clip(lower=1)
    for col in ["Hipotecas_Total", "Precio_m2", "Tasa_Paro", "Euribor"]:
        new[f"{col}_diff1"] = g[col].shift(1).diff()
        new[f"{col}_diff4"] = g[col].shift(1).diff(4)
    df = pd.concat([df, pd.DataFrame(new)], axis=1)
    df["Euribor_ma4"] = df.groupby("Provincia")["Euribor"].transform(lambda x: x.shift(1).rolling(4).mean())
    df["Euribor_lag1"] = df.groupby("Provincia")["Euribor"].shift(1)
    df["Euribor_lag2"] = df.groupby("Provincia")["Euribor"].shift(2)
    eur = df["Euribor"] if euribor_contemporaneo else df["Euribor_lag1"]
    eur_prev = df["Euribor_lag1"] if euribor_contemporaneo else df["Euribor_lag2"]
    df["Euribor_change"] = eur - eur_prev
    df["Euribor_x_Precio"] = eur * df["Precio_m2_lag1"]
    df["Accesibilidad"] = (df["PIB_pc_lag1"] * (1 - df["Tasa_Paro_lag1"] / 100)) / df["Precio_m2_lag1"].clip(lower=1)
    df["Hip_per_cap"] = df["Hipotecas_Total_lag1"] / df["Poblacion_lag1"].clip(lower=1)
    df["Pob_Ext_ratio"] = df["Pob_Ext_lag1"] / df["Poblacion_lag1"].clip(lower=1)
    df["Precio_x_Paro"] = df["Precio_m2_lag1"] * df["Tasa_Paro_lag1"]
    df["Spread_x_Euribor"] = df["Spread_Hipotecas_lag1"] * eur
    df["Trans_per_cap"] = df["Transmisiones_Total_lag1"] / df["Poblacion_lag1"].clip(lower=1)
    df["Hip_trans_ratio"] = df["Hipotecas_Total_lag1"] / (df["Transmisiones_Total_lag1"].clip(lower=1))
    df["Hip_lag1_vs_rmean"] = df["Hipotecas_Total_lag1"] / df["Hipotecas_Total_rmean4"].clip(lower=1)
    df["Precio_lag1_vs_rmean"] = df["Precio_m2_lag1"] / df["Precio_m2_rmean4"].clip(lower=1)
    df["Q"] = df["Trimestre"].dt.quarter
    df["Year"] = df["Trimestre"].dt.year
    df["Trend"] = df.groupby("Provincia").cumcount()
    for q in [1, 2, 3, 4]:
        df[f"Q{q}"] = (df["Q"] == q).astype(int)
    from sklearn.preprocessing import LabelEncoder
    df["Prov_code"] = LabelEncoder().fit_transform(df["Provincia"])
    if not euribor_contemporaneo:
        df["Euribor"] = df["Euribor_lag1"]  # la columna 'Euribor' del modelo pasa a ser t-1
    df = df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    # Celda 11 (mapa de accesibilidad): sobrescribe la feature con valores contemporáneos
    if accesibilidad_contemporanea:
        df["Accesibilidad"] = (df["PIB_pc"] * (1 - df["Tasa_Paro"] / 100)) / df["Precio_m2"]
    return df


def features_ml(df):
    return [c for c in df.columns if any([
        c.endswith("_lag1"), c.endswith("_lag2"), c.endswith("_lag4"),
        c.endswith("_rmean4"), c.endswith("_rstd4"), c.endswith("_rmin4"), c.endswith("_rmax4"),
        c.endswith("_yoy"), c.endswith("_diff1"), c.endswith("_diff4"),
        c in ["Euribor", "Euribor_ma4", "Euribor_change", "Euribor_x_Precio", "Accesibilidad", "Hip_per_cap",
              "Pob_Ext_ratio", "Precio_x_Paro", "Spread_x_Euribor", "Trans_per_cap", "Hip_trans_ratio",
              "Hip_lag1_vs_rmean", "Precio_lag1_vs_rmean", "Q", "Q1", "Q2", "Q3", "Q4", "Year", "Trend", "Prov_code"]])]


VARS_TO_WEIGHT = ["Precio_m2_lag1", "Precio_m2_lag2", "Precio_m2_lag4", "Tasa_Paro_lag1", "Tasa_Paro_lag4",
                  "IPC_lag1", "PIB_pc_lag1", "PIB_pc_lag4", "Indice_Mano_Obra_lag1", "Indice_Materiales_lag1",
                  "tasa_ahorro_lag1", "Edad_Media_lag1", "Spread_Hipotecas_lag1", "Spread_Hipotecas_lag2",
                  "Precio_m2_rmean4", "Tasa_Paro_rmean4", "Precio_m2_yoy", "PIB_pc_yoy", "Precio_m2_diff1",
                  "Tasa_Paro_diff1", "Accesibilidad"]
VARS_TO_SUM = {"Hipotecas_Total": "sum", "Transmisiones_Total_lag1": "sum", "Transmisiones_Total_lag4": "sum",
               "Hipotecas_Total_lag1": "sum", "Hipotecas_Total_lag4": "sum", "Pob_Ext_lag1": "sum",
               "Poblacion_lag1": "sum", "Hipotecas_Total_rmean4": "sum", "Transmisiones_Total_rmean4": "sum",
               "Hipotecas_Total_yoy": "mean", "Transmisiones_Total_yoy": "mean", "Hipotecas_Total_diff1": "sum"}


def build_national(df):
    """Celda 19 del notebook 4 (agregado nacional, medias ponderadas por Poblacion_lag1)."""
    t = df.copy()
    peso = t["Poblacion_lag1"].fillna(1)
    for v in VARS_TO_WEIGHT:
        t[f"{v}_pond"] = t[v] * peso
    sum_agg = {v: a for v, a in VARS_TO_SUM.items()}
    pond_agg = {f"{v}_pond": "sum" for v in VARS_TO_WEIGHT}
    pond_agg["Poblacion_lag1"] = "sum"
    extra = {"Euribor": "mean", "Q": "first", "Trend": "mean", "Euribor_ma4": "mean",
             "Euribor_change": "mean", "Hipotecas_Total_rstd4": "mean"}
    n = t.groupby("Trimestre").agg({**sum_agg, **pond_agg, **extra}).sort_index()
    for v in VARS_TO_WEIGHT:
        n[v] = n[f"{v}_pond"] / n["Poblacion_lag1"]
        n = n.drop(columns=[f"{v}_pond"])
    H = n["Hipotecas_Total"]
    n["Hip_total_lag1_nac"] = H.shift(1)
    n["Hip_total_lag2_nac"] = H.shift(2)
    n["Hip_total_lag4_nac"] = H.shift(4)
    n["Hip_total_rmean4_nac"] = H.shift(1).rolling(4).mean()
    n["Hip_yoy_nac"] = (H.shift(1) - H.shift(5)) / H.shift(5).abs().clip(lower=1)
    n["Hip_momentum"] = H.shift(1) - H.shift(2)
    n["Hip_vs_rmean"] = n["Hip_total_lag1_nac"] / n["Hip_total_rmean4_nac"].clip(lower=1)
    n["Euribor_x_Precio_nac"] = n["Euribor"] * n["Precio_m2_lag1"]
    n["Accesibilidad_nac"] = (n["PIB_pc_lag1"] * (1 - n["Tasa_Paro_lag1"] / 100)) / n["Precio_m2_lag1"].clip(lower=1)
    n["Hip_per_cap_nac"] = n["Hip_total_lag1_nac"] / n["Poblacion_lag1"].clip(lower=1)
    for q in [1, 2, 3, 4]:
        n[f"Q{q}"] = (n["Q"] == q).astype(int)
    n = n.replace([np.inf, -np.inf], np.nan).dropna()
    feats = [c for c in n.columns if c != "Hipotecas_Total"]
    return n, feats


def national_series(df_raw=None):
    """Serie nacional de Hipotecas_Total = suma de las 52 provincias (2005Q1-2025Q4)."""
    if df_raw is None:
        df_raw = load_raw()
    s = df_raw.groupby("Trimestre")["Hipotecas_Total"].sum().sort_index()
    s.index = pd.DatetimeIndex(s.index, freq="QS-JAN")
    return s


# ---------------------------------------------------------------- métricas
def mape(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.mean(np.abs((y - p) / y)) * 100)


def smape(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.mean(2 * np.abs(y - p) / (np.abs(y) + np.abs(p))) * 100)


def mae(y, p):
    return float(np.mean(np.abs(np.asarray(y, float) - np.asarray(p, float))))


def rmse(y, p):
    return float(np.sqrt(np.mean((np.asarray(y, float) - np.asarray(p, float)) ** 2)))
