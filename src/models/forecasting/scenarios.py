"""Lectura de ``data/metadata/escenarios_macro.yaml`` y construcción de sendas por escenario."""
from __future__ import annotations

import hashlib

import pandas as pd
import yaml

from . import config as C

SCENARIOS = ["base", "adverso", "favorable"]


def load_yaml(path=C.SCENARIOS_YAML) -> dict:
    return yaml.safe_load(open(path, encoding="utf-8"))


def yaml_hash(path=C.SCENARIOS_YAML) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _annual_with_sens(block: dict, scen: str, years) -> dict:
    base = {int(k): float(v) for k, v in block["base"].items() if str(k).isdigit()}
    out = {}
    sens = (block.get("sensibilidades") or {}).get(scen, {}) if scen != "base" else {}
    for y in years:
        v = base[y]
        if scen != "base":
            if y >= 2027 and "desde_2027" in sens:
                v += float(sens["desde_2027"])
            elif y in sens or str(y) in sens:
                v += float(sens.get(y, sens.get(str(y))))
        out[y] = v
    return out


def quarters(start="2026Q1", end=C.PROJ_END_Q) -> pd.PeriodIndex:
    return pd.period_range(pd.Period(start, freq="Q-DEC"), end, freq="Q-DEC")


def euribor_path(scen: str, cfg: dict | None = None, start="2026Q1") -> pd.Series:
    """Euribor 12M trimestral: observado (2026Q1-Q3) + base/sensibilidad. Las sensibilidades no tocan lo observado."""
    cfg = cfg or load_yaml()
    e = cfg["euribor_12m"]
    obs = {pd.Period(k, freq="Q-DEC"): float(v) for k, v in e["observado_trimestral"].items()}
    base = e["base"]
    sens = e["sensibilidades"].get(scen, {}) if scen != "base" else {}
    out = {}
    for q in quarters(start):
        if q in obs:
            out[q] = obs[q]
            continue
        key = f"{q.year}Q{q.quarter}"
        v = float(base[key]) if key in base else float(base[q.year])
        if scen != "base":
            v += float(sens.get(key, sens.get("desde_2027", 0.0) if q.year >= 2027 else 0.0))
        out[q] = v
    return pd.Series(out, name="euribor")


def annual_path(var: str, scen: str, cfg: dict | None = None, years=range(2026, 2031)) -> pd.Series:
    cfg = cfg or load_yaml()
    key = {"ipc": "ipc_espana", "paro": "paro_nacional", "pib_pc_growth": "pib_pc_nominal"}[var]
    return pd.Series(_annual_with_sens(cfg[key], scen, list(years)), name=var)


def quarterly_from_annual(s: pd.Series, start="2026Q1") -> pd.Series:
    """Valor anual asignado a sus cuatro trimestres (sin interpolar)."""
    q = quarters(start)
    return pd.Series([s[p.year] for p in q], index=q, name=s.name)


def observed_quarters(cfg: dict | None = None) -> list:
    cfg = cfg or load_yaml()
    return [pd.Period(k, freq="Q-DEC") for k in cfg["euribor_12m"]["observado_trimestral"]]
