"""Métricas de previsión y test de Diebold-Mariano (corrección de Harvey-Leybourne-Newbold)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _a(x):
    return np.asarray(x, dtype=float)


def mae(y, p):
    return float(np.mean(np.abs(_a(y) - _a(p))))


def rmse(y, p):
    return float(np.sqrt(np.mean((_a(y) - _a(p)) ** 2)))


def mape(y, p):
    y, p = _a(y), _a(p)
    m = y != 0
    return float(np.mean(np.abs((y[m] - p[m]) / y[m])) * 100)


def smape(y, p):
    y, p = _a(y), _a(p)
    d = np.abs(y) + np.abs(p)
    m = d > 0
    return float(np.mean(2 * np.abs(y[m] - p[m]) / d[m]) * 100)


def mase(y, p, scale):
    """MASE con escala por previsión (MAE in-sample del seasonal naive del train de cada origen)."""
    s = _a(scale)
    return float(np.mean(np.abs(_a(y) - _a(p)) / s))


def theil_u(y, p, p_naive):
    """U de Theil relativa: RMSE(modelo)/RMSE(naive) sobre las mismas previsiones."""
    den = rmse(y, p_naive)
    return float(rmse(y, p) / den) if den > 0 else np.nan


def dm_test(e_model, e_bench, h: int, power: int = 2):
    """Diebold-Mariano con corrección HLN. Devuelve (estadístico, p-valor bilateral).
    d_t = |e_model|^p - |e_bench|^p ; estadístico < 0 => el modelo tiene menor pérdida."""
    d = np.abs(_a(e_model)) ** power - np.abs(_a(e_bench)) ** power
    n = len(d)
    if n < 5:
        return np.nan, np.nan
    dbar = d.mean()
    gam = [np.sum((d[k:] - dbar) * (d[:n - k] - dbar)) / n for k in range(max(1, h))]
    v = gam[0] + 2 * sum(gam[1:])
    if v <= 0:
        v = gam[0]
    if v <= 0:
        return np.nan, np.nan
    dm = dbar / np.sqrt(v / n)
    corr = (n + 1 - 2 * h + h * (h - 1) / n) / n
    hln = dm * np.sqrt(max(corr, 1e-12))
    return float(hln), float(2 * stats.t.sf(abs(hln), df=n - 1))


def summarise(df: pd.DataFrame, naive_model: str = "naive") -> pd.DataFrame:
    """df: columnas model, h, window, target, y, yhat, scale (+ unit opcional). Métricas por model/h/window."""
    rows = []
    key = ["unit", "target"] if "unit" in df.columns else ["target"]
    for (m, h, w), g in df.groupby(["model", "h", "window"]):
        nv = df[(df.model == naive_model) & (df.h == h) & (df.window == w)].set_index(key)["yhat"]
        pn = nv.reindex(pd.MultiIndex.from_frame(g[key]) if len(key) > 1 else g[key[0]]).values
        rows.append({"model": m, "h": int(h), "window": w, "n": len(g), "MAE": mae(g.y, g.yhat), "RMSE": rmse(g.y, g.yhat),
                     "MAPE": mape(g.y, g.yhat), "sMAPE": smape(g.y, g.yhat), "MASE": mase(g.y, g.yhat, g.scale),
                     "TheilU": theil_u(g.y, g.yhat, pn) if not np.isnan(pn).any() else np.nan})
    return pd.DataFrame(rows)
