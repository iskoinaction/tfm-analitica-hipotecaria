"""Motor rolling-origin (walk-forward, ventana expansiva), selección pre-especificada, DM e intervalos empíricos."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from . import config as C
from .metrics import dm_test, mae, mape, mase, rmse, smape, summarise, theil_u
from .univariate import seasonal_naive_scale


def window_of(target) -> str:
    """Ventana de un objetivo (Period trimestral o año int)."""
    if isinstance(target, pd.Period):
        if target <= C.SEL_END_Q:
            return "seleccion"
        if target <= C.HOLDOUT_END_Q:
            return "holdout"
        return "oos_extra"
    t = int(target)
    if t <= C.SEL_END_Y:
        return "seleccion"
    if t <= C.HOLDOUT_END_Q.year:
        return "holdout"
    return "oos_extra"


class ContextForecaster:
    """Modelo que necesita algo más que la serie (exógenas, panel). Implementa ``forecast(pos, horizons) -> {h: yhat}``
    donde ``pos`` es la posición del origen en la serie objetivo (solo puede usar información <= pos)."""

    def forecast(self, pos: int, horizons: list[int]) -> dict:  # pragma: no cover - interfaz
        raise NotImplementedError


def rolling_origin(series: pd.Series, models: dict, origins: list, horizons: list[int], m: int = 4,
                   unit: str | None = None, min_train: int = 16) -> pd.DataFrame:
    """series: índice Period (Q) o int (años), sin huecos internos. models: nombre -> f(train, H) o ContextForecaster."""
    s = series.dropna()
    idx = list(s.index)
    pos_of = {p: i for i, p in enumerate(idx)}
    vals = s.values.astype(float)
    H = max(horizons)
    recs = []
    for o in origins:
        if o not in pos_of:
            continue
        i = pos_of[o]
        if i + 1 < min_train or i + 1 >= len(idx):
            continue
        train = vals[: i + 1]
        scale = seasonal_naive_scale(train, m)
        hs = [h for h in horizons if i + h < len(idx)]
        if not hs:
            continue
        for name, f in models.items():
            if isinstance(f, ContextForecaster):
                fc = f.forecast(i, hs)
            else:
                path = f(train, max(hs))
                fc = {h: path[h - 1] for h in hs}
            for h in hs:
                if h not in fc or fc[h] is None or not np.isfinite(fc[h]):
                    continue
                tgt = idx[i + h]
                recs.append({"unit": unit or "nacional", "model": name, "origin": idx[i], "h": h, "target": tgt,
                             "window": window_of(tgt), "y": vals[i + h], "yhat": float(fc[h]), "scale": scale})
    return pd.DataFrame(recs)


def select_models(metrics: pd.DataFrame, candidates: list[str] | None = None, stat: str = "MASE") -> dict:
    """Regla pre-especificada: por horizonte, menor ``stat`` en la ventana de selección (desempate RMSE)."""
    sel = {}
    m = metrics[metrics.window == "seleccion"]
    if candidates:
        m = m[m.model.isin(candidates)]
    for h, g in m.groupby("h"):
        g = g.sort_values([stat, "RMSE"])
        sel[int(h)] = g.iloc[0]["model"]
    return sel


def panel_summary(df: pd.DataFrame, naive_model: str = "naive") -> pd.DataFrame:
    """Métricas por unidad y agregadas: mediana entre unidades de MASE/MAPE/U y WAPE agregado."""
    per = []
    for (u, mo, h, w), g in df.groupby(["unit", "model", "h", "window"]):
        nv = df[(df.unit == u) & (df.model == naive_model) & (df.h == h) & (df.window == w)].set_index("target")["yhat"]
        pn = nv.reindex(g.target).values
        per.append({"unit": u, "model": mo, "h": h, "window": w, "n": len(g), "MASE": mase(g.y, g.yhat, g.scale),
                    "MAPE": mape(g.y, g.yhat), "sMAPE": smape(g.y, g.yhat), "RMSE": rmse(g.y, g.yhat),
                    "MAE": mae(g.y, g.yhat), "TheilU": theil_u(g.y, g.yhat, pn) if not np.isnan(pn).any() else np.nan})
    per = pd.DataFrame(per)
    agg = []
    for (mo, h, w), g in df.groupby(["model", "h", "window"]):
        p = per[(per.model == mo) & (per.h == h) & (per.window == w)]
        agg.append({"model": mo, "h": int(h), "window": w, "n": len(g), "n_unidades": int(p.unit.nunique()),
                    "MASE": float(p.MASE.median()), "MAPE": float(p.MAPE.median()), "sMAPE": float(p.sMAPE.median()),
                    "TheilU": float(p.TheilU.median()), "RMSE": float(p.RMSE.median()), "MAE": float(p.MAE.median()),
                    "WAPE": float(np.sum(np.abs(g.y - g.yhat)) / np.sum(np.abs(g.y)) * 100),
                    "pct_unidades_U_menor_1": float((p.TheilU < 1).mean() * 100)})
    return pd.DataFrame(agg), per


def dm_table(df: pd.DataFrame, pairs: list[tuple], window: str) -> pd.DataFrame:
    """pairs: (h, modelo, benchmark). DM con pérdida cuadrática y absoluta sobre objetivos comunes."""
    rows = []
    for h, mod, ben in pairs:
        a = df[(df.model == mod) & (df.h == h) & (df.window == window)].set_index(["unit", "target"])
        b = df[(df.model == ben) & (df.h == h) & (df.window == window)].set_index(["unit", "target"])
        common = a.index.intersection(b.index)
        if len(common) < 5 or mod == ben:
            rows.append({"h": h, "window": window, "model": mod, "benchmark": ben, "n": len(common),
                         "DM_sq": np.nan, "p_sq": np.nan, "DM_abs": np.nan, "p_abs": np.nan})
            continue
        ea = (a.loc[common, "y"] - a.loc[common, "yhat"]).values
        eb = (b.loc[common, "y"] - b.loc[common, "yhat"]).values
        s2, p2 = dm_test(ea, eb, h, 2)
        s1, p1 = dm_test(ea, eb, h, 1)
        rows.append({"h": h, "window": window, "model": mod, "benchmark": ben, "n": len(common),
                     "DM_sq": s2, "p_sq": p2, "DM_abs": s1, "p_abs": p1})
    return pd.DataFrame(rows)


def empirical_log_quantiles(df: pd.DataFrame, model: str, q=(C.PI_LOW, C.PI_HIGH), windows=None,
                            max_target=None) -> pd.DataFrame:
    """Cuantiles por horizonte de e = log(y/yhat) del modelo (para intervalos multiplicativos)."""
    d = df[df.model == model]
    if windows:
        d = d[d.window.isin(windows)]
    if max_target is not None:
        d = d[d.target <= max_target]
    d = d[(d.y > 0) & (d.yhat > 0)]
    e = np.log(d.y / d.yhat)
    out = e.groupby(d.h).quantile(list(q)).unstack()
    out.columns = ["q_low", "q_high"]
    out["n"] = e.groupby(d.h).size()
    return out


def empirical_abs_quantiles(df: pd.DataFrame, model: str, q=(C.PI_LOW, C.PI_HIGH), max_target=None) -> pd.DataFrame:
    """Cuantiles por horizonte del error aditivo y - yhat (para tasas como el paro)."""
    d = df[df.model == model]
    if max_target is not None:
        d = d[d.target <= max_target]
    e = d.y - d.yhat
    out = e.groupby(d.h).quantile(list(q)).unstack()
    out.columns = ["q_low", "q_high"]
    out["n"] = e.groupby(d.h).size()
    return out


def extend_quantiles(qt: pd.DataFrame, H: int) -> pd.DataFrame:
    """Rellena horizontes sin errores suficientes escalando el último disponible por sqrt(h/h0) (documentado)."""
    qt = qt[qt["n"] >= 8] if "n" in qt else qt
    out = {}
    hs = sorted(qt.index)
    for h in range(1, H + 1):
        if h in qt.index:
            out[h] = qt.loc[h, ["q_low", "q_high"]].values
        else:
            h0 = max([x for x in hs if x < h], default=hs[0])
            out[h] = qt.loc[h0, ["q_low", "q_high"]].values * np.sqrt(h / h0)
    return pd.DataFrame(out, index=["q_low", "q_high"]).T


def interval_coverage(df: pd.DataFrame, model: str, horizons=None, q=(C.PI_LOW, C.PI_HIGH), additive=False) -> pd.DataFrame:
    """Cobertura EMPÍRICA en el hold-out de los intervalos construidos SOLO con errores de la ventana de selección
    (objetivos <= SEL_END). Nominal = q_high - q_low. Se calcula sobre todas las unidades y orígenes por horizonte."""
    d = df[df.model == model]
    d = d[(d.y > 0) & (d.yhat > 0)] if not additive else d
    sel, ho = d[d.window == "seleccion"], d[d.window == "holdout"]
    rows = []
    for h in sorted(ho.h.unique()):
        if horizons is not None and h not in horizons:
            continue
        a, b = sel[sel.h == h], ho[ho.h == h]
        if len(a) < 8 or len(b) == 0:
            continue
        e = np.log(a.y / a.yhat)
        lo, hi = e.quantile(q[0]), e.quantile(q[1])
        eh = np.log(b.y / b.yhat)
        rows.append({"model": model, "h": int(h), "n_seleccion": len(a), "n_holdout": len(b),
                     "nominal": q[1] - q[0], "cobertura_holdout": float(((eh >= lo) & (eh <= hi)).mean()),
                     "q_low_log": float(lo), "q_high_log": float(hi)})
    return pd.DataFrame(rows)
