"""Agregación temporal declarativa (mensual→trimestral) y reglas de disponibilidad de variables anuales."""
from __future__ import annotations

import pandas as pd


def monthly_to_quarterly(df: pd.DataFrame, how: str) -> pd.DataFrame:
    """Agrega observaciones mensuales (col. ref_date) a trimestre. Solo trimestres con los 3 meses; si no, NaN
    (se descarta la fila). ``how``: 'sum' para flujos, 'mean' para precios/tipos/índices."""
    d = df.copy()
    d["q"] = pd.PeriodIndex(pd.to_datetime(d["ref_date"]), freq="Q")
    g = d.groupby(["variable", "geo_level", "geo_code", "q"])["value"]
    out = g.agg(["sum" if how == "sum" else "mean", "count"]).reset_index()
    out.columns = ["variable", "geo_level", "geo_code", "q", "value", "n_months"]
    out = out[out["n_months"] == 3].drop(columns="n_months")
    out["period"] = out["q"].map(lambda p: f"{p.year}Q{p.quarter}")
    return out.drop(columns="q")


def quarterly_obs(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    q = pd.PeriodIndex(pd.to_datetime(d["ref_date"]), freq="Q")
    d["period"] = [f"{p.year}Q{p.quarter}" for p in q]
    return d[["variable", "geo_level", "geo_code", "period", "value"]]


def stock_at_january(df: pd.DataFrame) -> pd.DataFrame:
    """Stocks puntuales (ECP): valor a 1 de enero de cada año → anual (año = año de la fecha de referencia)."""
    d = df[pd.to_datetime(df["ref_date"]).dt.strftime("%m-%d") == "01-01"].copy()
    d["year"] = pd.to_datetime(d["ref_date"]).dt.year
    return d[["variable", "geo_level", "geo_code", "year", "value", "status"]]


# Regla de disponibilidad para la vista panel_modelado: el dato anual del año Y (referido a 1-ene-Y o al
# año natural Y) se considera publicado ``lag`` meses después del 1 de enero de Y. Para un trimestre que
# termina en la fecha E se usa el año de referencia más reciente con fecha de publicación <= E.
AVAILABILITY_LAG_MONTHS = {
    "poblacion": 5,             # ECP: población a 1-ene-Y, provisional publicada ~mayo Y
    "poblacion_extranjera": 5,
    "edad_media": 6,            # Indicadores demográficos básicos: ~junio Y
    "pib_pc": 35,               # CRE: PIB provincial del año Y, primera estimación en diciembre Y+2
}


def available_ref_year(quarter_end: pd.Timestamp, lag_months: int) -> int:
    """Año de referencia más reciente publicado a la fecha ``quarter_end``."""
    y = quarter_end.year
    while pd.Timestamp(year=y, month=1, day=1) + pd.DateOffset(months=lag_months) > quarter_end:
        y -= 1
    return y
