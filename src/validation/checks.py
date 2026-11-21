"""Controles de calidad. Cada control devuelve una lista de incidencias
``{"check", "severity" (error|warning|info), "target", "detail", "n"}``."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import config
from src.common.io import STAGING_COLUMNS

VAR_SPECS = {v.name: v for d in config.DATASETS for v in d.variables}


def _issue(check, severity, target, detail, n=None):
    return {"check": check, "severity": severity, "target": target, "detail": detail, "n": n}


def check_schema(df: pd.DataFrame, required: list, target: str, key: list | None = None) -> list:
    out = []
    miss = [c for c in required if c not in df.columns]
    if miss:
        out.append(_issue("schema", "error", target, f"faltan columnas {miss}"))
    if key and not miss:
        dup = int(df.duplicated(key).sum())
        if dup:
            out.append(_issue("duplicates", "error", target, f"{dup} claves duplicadas {key}", dup))
    if "value" in df.columns and not pd.api.types.is_numeric_dtype(df["value"]):
        out.append(_issue("schema", "error", target, "value no numérico"))
    return out


def check_staging(df: pd.DataFrame, dataset: str) -> list:
    out = check_schema(df, STAGING_COLUMNS, dataset, ["variable", "geo_level", "geo_code", "ref_date"])
    if out:
        return out
    out += check_ranges(df, dataset)
    out += check_integer_format(df, dataset)
    out += check_coverage_staging(df, dataset)
    return out


def check_ranges(df: pd.DataFrame, target: str) -> list:
    out = []
    for var, g in df.groupby("variable"):
        spec = VAR_SPECS.get(var)
        if not spec:
            continue
        lo, hi = spec.valid_range
        # los totales nacionales de flujos (conteos) superan los rangos provinciales
        vals = g.loc[g["geo_level"] != "nacional", "value"] if spec.integer else g["value"]
        bad = vals[(vals < lo) | (vals > hi)]
        if len(bad):
            out.append(_issue("range", "error", f"{target}:{var}", f"{len(bad)} valores fuera de [{lo}, {hi}] (ej. {bad.iloc[0]})", len(bad)))
    return out


def check_integer_format(df: pd.DataFrame, target: str) -> list:
    """Detector del 'bug de los miles': un conteo nunca puede tener decimales."""
    out = []
    for var, g in df.groupby("variable"):
        spec = VAR_SPECS.get(var)
        if spec and spec.integer:
            frac = g["value"].dropna() % 1
            n = int((frac != 0).sum())
            if n:
                out.append(_issue("numeric_format", "error", f"{target}:{var}", f"{n} conteos con decimales: posible error de separador de miles", n))
    return out


def check_coverage_staging(df: pd.DataFrame, target: str) -> list:
    out = []
    prov = df[df["geo_level"] == "provincia"]
    if prov.empty:
        return out
    n = prov.groupby(["variable", "period"])["geo_code"].nunique()
    inc = n[n < 52]
    if len(inc):
        out.append(_issue("coverage", "warning", target,
                          f"{len(inc)} (variable, periodo) con <52 provincias; ej. {inc.index[0]}={inc.iloc[0]}", len(inc)))
    return out


def check_panel(df: pd.DataFrame, key: list, target: str, expected_units: int = 52) -> list:
    out = check_schema(df, key, target, key)
    per = df.groupby(key[1])[key[0]].nunique()
    if (per != expected_units).any():
        out.append(_issue("coverage", "error", target, f"periodos sin {expected_units} unidades: {list(per[per != expected_units].index[:5])}"))
    nan = df.drop(columns=key).select_dtypes("number").isna().mean().round(3)
    for c, v in nan.items():
        if v > 0:
            out.append(_issue("missing", "info", f"{target}:{c}", f"{v:.1%} NaN", int(round(v * len(df)))))
    for c in df.columns:
        spec = VAR_SPECS.get(c)
        if spec and spec.valid_range and spec.agg_q not in ("sum",):
            lo, hi = spec.valid_range
            b = df[c].dropna()
            nb = int(((b < lo) | (b > hi)).sum())
            if nb:
                out.append(_issue("range", "error", f"{target}:{c}", f"{nb} fuera de [{lo},{hi}]", nb))
    return out


def check_jumps(df: pd.DataFrame, unit: str, time: str, cols: list, target: str, z: float = 6.0) -> list:
    """Saltos anómalos (posible ruptura de serie): |Δlog| a más de ``z`` desviaciones robustas."""
    out = []
    for c in cols:
        if c not in df:
            continue
        d = df.sort_values([unit, time])
        x = np.log(d[c].where(d[c] > 0))
        dl = x.groupby(d[unit]).diff()
        med, mad = dl.median(), (dl - dl.median()).abs().median() * 1.4826
        if not mad or np.isnan(mad):
            continue
        n = int(((dl - med).abs() > z * mad).sum())
        if n:
            out.append(_issue("jump", "warning", f"{target}:{c}", f"{n} saltos |Δlog|>{z}·MAD", n))
    return out


def reconcile_totals(nac: pd.DataFrame, pairs: list[tuple[str, str]], tol: float = 0.005) -> list:
    """Compara total nacional oficial vs suma de provincias (si la fuente publica ambos)."""
    out = []
    for official, summed in pairs:
        if official not in nac or summed not in nac:
            continue
        d = nac[["period", official, summed]].dropna()
        rel = (d[summed] / d[official] - 1).abs()
        bad = d[rel > tol]
        sev = "warning" if len(bad) else "info"
        out.append(_issue("reconciliation", sev, f"nacional:{official}",
                          f"suma provincias vs total oficial: {len(bad)}/{len(d)} trimestres con |dif|>{tol:.1%}; máx {rel.max():.3%}", len(bad)))
    return out
