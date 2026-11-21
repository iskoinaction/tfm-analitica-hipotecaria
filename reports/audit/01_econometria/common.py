"""Utilidades comunes de la auditoría econométrica (Fase IV).

Construcción de las series nacionales a partir del panel provincial
`notebooks acabados/dataset_final_tfm.csv`, en dos variantes:

* ``build_original``: réplica EXACTA del notebook 4.2 (ffill/bfill por provincia,
  suma de hipotecas, medias SIMPLES de provincias para PIB_pc, Precio_m2,
  Euribor e Índice de Materiales).  Incluye 2025 con PIB_pc y Materiales
  arrastrados (ffill) desde el último dato disponible.
* ``build_clean``: variante auditada: sin arrastres (2025 fuera si falta un dato),
  PIB_pc y Precio_m2 ponderados por población, opción de serie de hipotecas
  desestacionalizada.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "notebooks acabados" / "dataset_final_tfm.csv"
OUT = Path(__file__).resolve().parent
FIG = OUT / "figs"
FIG.mkdir(exist_ok=True)

ORDER_ORIG = ["Log_Materiales", "Euribor", "Log_PIB_pc", "Log_Precio_m2", "Log_Hipotecas"]


def load_panel() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df["Trimestre"] = pd.to_datetime(df["Trimestre"])
    return df.sort_values(["Provincia", "Trimestre"]).reset_index(drop=True)


def build_original() -> pd.DataFrame:
    """Réplica literal de la celda 3 del notebook 4.2."""
    df = load_panel()
    cols_fill = ["tasa_ahorro", "Indice_Mano_Obra", "Indice_Materiales",
                 "IPC", "PIB_pc", "Pob_Ext", "Precio_m2"]
    for col in cols_fill:
        df[col] = df.groupby("Provincia")[col].transform(lambda x: x.ffill().bfill())
    nac = df.groupby("Trimestre").agg({
        "Hipotecas_Total": "sum", "PIB_pc": "mean", "Precio_m2": "mean",
        "Euribor": "mean", "Indice_Materiales": "mean"}).sort_index()
    out = pd.DataFrame({
        "Log_Materiales": np.log(nac["Indice_Materiales"]),
        "Euribor": nac["Euribor"],
        "Log_PIB_pc": np.log(nac["PIB_pc"]),
        "Log_Precio_m2": np.log(nac["Precio_m2"]),
        "Log_Hipotecas": np.log(nac["Hipotecas_Total"]),
    }, index=nac.index).dropna()
    out.index = pd.DatetimeIndex(out.index, freq="QS-OCT")
    return out


def national_raw() -> pd.DataFrame:
    """Agregados nacionales sin imputar (NaN donde falte el dato)."""
    df = load_panel()
    g = df.groupby("Trimestre")
    w = df["Poblacion"]
    df["_pib_w"] = df["PIB_pc"] * w
    df["_p_w"] = df["Precio_m2"] * w
    nac = pd.DataFrame({
        "Hipotecas": g["Hipotecas_Total"].sum(min_count=52),
        "Transmisiones": g["Transmisiones_Total"].sum(min_count=52),
        "Poblacion": g["Poblacion"].sum(),
        "PIB_pc_simple": g["PIB_pc"].mean(),
        "PIB_pc_pond": g["_pib_w"].sum(min_count=52) / g["Poblacion"].sum(),
        "Precio_simple": g["Precio_m2"].mean(),
        "Precio_pond": g["_p_w"].sum(min_count=52) / g["Poblacion"].sum(),
        "Euribor": g["Euribor"].mean(),
        "Materiales": g["Indice_Materiales"].mean(),
        "Mano_Obra": g["Indice_Mano_Obra"].mean(),
        "Spread": g["Spread_Hipotecas"].mean(),
        "Paro_simple": g["Tasa_Paro"].mean(),
    }).sort_index()
    # Mínimos/máximos para comprobar que las nacionales son replicadas
    nac["Euribor_nuniq"] = g["Euribor"].nunique()
    nac["Materiales_nuniq"] = g["Indice_Materiales"].nunique()
    nac.index = pd.DatetimeIndex(nac.index, freq="QS-OCT")
    return nac


def build_clean(weighted: bool = True, sa_hip: bool = False, end: str | None = None) -> pd.DataFrame:
    """Series auditadas, en el orden de Cholesky original, sin imputaciones."""
    nac = national_raw()
    pib = nac["PIB_pc_pond"] if weighted else nac["PIB_pc_simple"]
    pre = nac["Precio_pond"] if weighted else nac["Precio_simple"]
    hip = np.log(nac["Hipotecas"])
    if sa_hip:
        hip = seasonal_adjust(hip)
    out = pd.DataFrame({
        "Log_Materiales": np.log(nac["Materiales"]),
        "Euribor": nac["Euribor"],
        "Log_PIB_pc": np.log(pib),
        "Log_Precio_m2": np.log(pre),
        "Log_Hipotecas": hip,
    }, index=nac.index).dropna()
    if end:
        out = out.loc[:end]
    out.index = pd.DatetimeIndex(out.index, freq="QS-OCT")
    return out


def seasonal_adjust(logy: pd.Series) -> pd.Series:
    """Desestacionalización aditiva sencilla del log mediante STL robusto (periodo 4).

    Se usa solo como análisis de sensibilidad (no sustituye a X-13/TRAMO-SEATS).
    """
    from statsmodels.tsa.seasonal import STL
    s = logy.dropna()
    res = STL(s, period=4, robust=True).fit()
    return (s - res.seasonal).reindex(logy.index)


def seasonal_dummies(index: pd.DatetimeIndex) -> pd.DataFrame:
    q = index.quarter
    d = pd.DataFrame({f"Q{k}": (q == k).astype(float) for k in (2, 3, 4)}, index=index)
    # centradas (para que no alteren la constante en Johansen)
    return d - 0.25


def crisis_dummies(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({
        "D_COVID": ((index >= "2020-04-01") & (index <= "2020-04-01")).astype(float),
        "D_COVID3": ((index >= "2020-07-01") & (index <= "2020-07-01")).astype(float),
    }, index=index)


def fmt(x, nd=3):
    try:
        return f"{x:.{nd}f}"
    except Exception:
        return str(x)
