"""Proyecciones macro provinciales v2 (2026-2030) con selección por rolling-origin y hold-out reservado.

Variables y candidatos (una regla fija por variable para TODAS las provincias; nada se elige provincia a provincia
mirando el test; sin suelos ni topes):
  * Precio m² (MIVAU tasado, trimestral): naive, seasonal naive, Holt-Winters amortiguado (TFM v1), ETS-log,
    LightGBM pooled directo (metodología del pipeline huérfano outputs/preciom2, reimplementada).
  * Compraventas de viviendas (trimestral): naive, seasonal naive, media 4T, ETS-log.
  * Tasa de paro (trimestral): naive, seasonal naive, Holt amortiguado, ARIMA(3,1,2), ancla nacional con
    desviación provincial que revierte (backtest: ancla = seasonal naive nacional; producción: senda CE).
  * PIB per cápita, población, población extranjera (ANUALES): naive, deriva log (toda la historia),
    deriva log (5 años) y, para PIB, ancla nacional (crecimiento nacional; producción: escenario BdE/CE).
Selección: un único modelo por variable = menor media de MASE (mediana entre provincias) sobre los horizontes de
la tabla, en la ventana de selección. El hold-out se evalúa después y no cambia nada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import scenarios as S
from . import univariate as U
from .backtest import (ContextForecaster, empirical_abs_quantiles, empirical_log_quantiles, extend_quantiles,
                       panel_summary, rolling_origin)

PATH_H_Q = 20


# ------------------------------------------------------------------------------------------ helpers
def _q_origins(s: pd.Series) -> list:
    """Orígenes anuales (Q4) desde FIRST_ORIGIN_Q + último dato (para errores oos_extra)."""
    return [p for p in s.index if p >= C.FIRST_ORIGIN_Q and p.quarter == 4][: -0 or None]


def _select(agg: pd.DataFrame, horizons: list[int], exclude=()) -> tuple[str, pd.Series]:
    a = agg[(agg.window == "seleccion") & agg.h.isin(horizons) & ~agg.model.isin(exclude)]
    score = a.groupby("model")["MASE"].mean().sort_values()
    return score.index[0], score


# ------------------------------------------------------------------------------------------ paro: ancla
class AnchorRevert(ContextForecaster):
    """u_p(T+h) = u_nat(T+h) + mu_q(T+h) + rho^h * (dev_T - mu_q(T)); dev = u_p - u_nat.
    mu_q: desviación media por trimestre (últimos 20 trimestres); rho: AR(1) de dev - mu_q (en [0, 0.99])."""

    def __init__(self, u_p: pd.Series, u_nat: pd.Series, nat_path_fn):
        self.idx = list(u_p.index)
        self.up = u_p.values
        self.un = u_nat.reindex(u_p.index).values
        self.nat_path_fn = nat_path_fn  # (pos, h) -> u_nat previsto para idx[pos+h] (o periodo)

    def params(self, pos):
        dev = self.up[: pos + 1] - self.un[: pos + 1]
        q = np.array([p.quarter for p in self.idx[: pos + 1]])
        last = slice(max(0, pos + 1 - 20), pos + 1)
        mu = {k: float(np.nanmean(dev[last][q[last] == k])) for k in (1, 2, 3, 4)}
        e = dev - np.array([mu[k] for k in q])
        e0, e1 = e[:-1], e[1:]
        ok = np.isfinite(e0) & np.isfinite(e1)
        rho = float(np.clip(np.sum(e0[ok] * e1[ok]) / np.sum(e0[ok] ** 2), 0, 0.99)) if ok.sum() > 8 else 0.9
        return mu, rho, float(e[-1])

    def forecast(self, pos, horizons):
        mu, rho, eT = self.params(pos)
        out = {}
        for h in horizons:
            if pos + h >= len(self.idx):
                continue
            tq = self.idx[pos + h].quarter
            un = self.nat_path_fn(pos, h)
            if un is None or not np.isfinite(un):
                continue
            out[h] = un + mu[tq] + rho ** h * eT
        return out

    def project(self, pos, periods, nat_values):
        mu, rho, eT = self.params(pos)
        return np.array([nat_values[i] + mu[p.quarter] + rho ** (i + 1) * eT for i, p in enumerate(periods)]), rho


# ------------------------------------------------------------------------------------------ precio: LightGBM pooled
class PooledLGBM:
    """LightGBM directo agrupado (todas las provincias), objetivo log(p_{T+h}/p_T), features <= T."""

    def __init__(self, wide: pd.DataFrame):
        self.wide = wide  # index Period, columnas prov_code
        self.lw = np.log(wide)
        self.idx = list(wide.index)

    def _feats(self, i):
        L = self.lw.values
        if i < 5:
            return None
        F = np.column_stack([L[i] - L[i - 1], L[i - 1] - L[i - 2], L[i - 2] - L[i - 3], L[i - 3] - L[i - 4],
                             L[i] - L[i - 4], L[i - 1] - L[i - 5], np.nanmean(L[i] - L[i - 4]) * np.ones(L.shape[1])])
        return F

    def forecast_all(self, pos, horizons):
        import lightgbm as lgb
        out = {}
        Fo = self._feats(pos)
        if Fo is None:
            return out
        for h in horizons:
            X, t = [], []
            for j in range(5, pos - h + 1):
                Fj = self._feats(j)
                q = np.full((Fj.shape[0], 1), self.idx[j + h].quarter)
                X.append(np.hstack([Fj, q]))
                t.append(self.lw.values[j + h] - self.lw.values[j])
            if not X:
                continue
            X, t = np.vstack(X), np.concatenate(t)
            ok = np.isfinite(X).all(axis=1) & np.isfinite(t)
            if ok.sum() < 100:
                continue
            m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20,
                                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=C.SEED,
                                  n_jobs=C.N_JOBS, verbose=-1).fit(X[ok], t[ok])
            tq = self.idx[pos + h].quarter if pos + h < len(self.idx) else (self.idx[pos] + h).quarter
            pred = m.predict(np.hstack([Fo, np.full((Fo.shape[0], 1), tq)]))
            out[h] = np.exp(self.lw.values[pos] + pred)
        return out


def _pooled_backtest(wide: pd.DataFrame, origins, horizons) -> pd.DataFrame:
    pl = PooledLGBM(wide)
    recs = []
    for o in origins:
        pos = pl.idx.index(o)
        fc = pl.forecast_all(pos, [h for h in horizons if pos + h < len(pl.idx)])
        for h, vec in fc.items():
            tgt = pl.idx[pos + h]
            for k, pc in enumerate(wide.columns):
                y = wide.iat[pos + h, k]
                tr = wide[pc].iloc[: pos + 1].dropna().values
                if not np.isfinite(y) or not np.isfinite(vec[k]) or len(tr) < 8:
                    continue
                from .backtest import window_of
                recs.append({"unit": pc, "model": "lightgbm_pooled", "origin": o, "h": h, "target": tgt,
                             "window": window_of(tgt), "y": float(y), "yhat": float(vec[k]),
                             "scale": U.seasonal_naive_scale(tr, 4)})
    return pd.DataFrame(recs)


# ------------------------------------------------------------------------------------------ trimestrales
def evaluate_quarterly(panel: pd.DataFrame, var: str, models: dict, national: pd.DataFrame | None = None,
                       pooled: bool = False, horizons=None) -> dict:
    horizons = horizons or list(range(1, PATH_H_Q + 1))
    recs = []
    wide = panel.pivot(index="period", columns="prov_code", values=var).sort_index()
    for pc in wide.columns:
        s = wide[pc].dropna()
        s = s[s > 0] if var != "paro" else s
        origins = [p for p in s.index if p >= C.FIRST_ORIGIN_Q and p.quarter == 4] + [s.index[-1]]
        ms = dict(models)
        if var == "paro" and national is not None:
            un = national["paro"]
            ms["ancla_nacional_revierte"] = AnchorRevert(s, un, _nat_snaive_fn(s, un))
        recs.append(rolling_origin(s, ms, sorted(set(origins)), horizons, unit=pc, min_train=24))
    df = pd.concat(recs, ignore_index=True)
    if pooled:
        origins = [p for p in wide.index if p >= C.FIRST_ORIGIN_Q and p.quarter == 4]
        df = pd.concat([df, _pooled_backtest(wide, origins, horizons)], ignore_index=True)
    tab = df[df.h.isin(C.HORIZONS_Q)]
    agg, per = panel_summary(tab)
    chosen, score = _select(agg, C.HORIZONS_Q)
    return {"forecasts": df, "metrics": agg, "per_unit": per, "chosen": chosen, "score": score.to_dict()}


def _nat_snaive_fn(s: pd.Series, un: pd.Series):
    idx = list(s.index)
    unv = un.reindex(s.index).values

    def f(pos, h):
        k = int(np.ceil(h / 4))
        j = pos + h - 4 * k
        return unv[j] if 0 <= j <= pos else None
    return f


# ------------------------------------------------------------------------------------------ anuales
def annual_wide(annual: pd.DataFrame, var: str) -> pd.DataFrame:
    return annual.pivot(index="year", columns="prov_code", values=var).sort_index()


def national_annual_pc(annual: pd.DataFrame) -> pd.Series:
    a = annual.dropna(subset=["pib_pc", "poblacion"])
    g = a.assign(x=a.pib_pc * a.poblacion).groupby("year")
    n = g["x"].sum() / g["poblacion"].sum()
    cnt = g.size()
    return n[cnt == 52]


class AnnualAnchor(ContextForecaster):
    """PIB_pc provincial crece al ritmo NACIONAL. Backtest: crecimiento nacional = media de los últimos 5 años
    observados en el origen (información disponible). Producción: escenario BdE/CE (yaml)."""

    def __init__(self, s: pd.Series, nat: pd.Series):
        self.idx = list(s.index)
        self.v = s.values
        self.nat = nat

    def forecast(self, pos, horizons):
        y0 = self.idx[pos]
        nat = self.nat.loc[:y0]
        if len(nat) < 6:
            return {}
        g = float(np.mean(np.diff(np.log(nat.values))[-5:]))
        return {h: self.v[pos] * np.exp(g * h) for h in horizons if pos + h < len(self.idx)}


def evaluate_annual(annual: pd.DataFrame, var: str, with_anchor: bool = False) -> dict:
    wide = annual_wide(annual, var)
    nat = national_annual_pc(annual) if with_anchor else None
    models = {"naive": U.naive, "deriva_log_total": U.log_drift,
              "deriva_log_5a": lambda y, H: U.log_drift(y, H, window=5)}
    recs = []
    for pc in wide.columns:
        s = wide[pc].dropna()
        s = s[s > 0]
        ms = dict(models)
        if with_anchor:
            ms["ancla_nacional"] = AnnualAnchor(s, nat)
        origins = [y for y in s.index if y >= C.FIRST_ORIGIN_Y]
        recs.append(rolling_origin(s, ms, origins, list(range(1, 7)), m=1, unit=pc, min_train=6))
    df = pd.concat(recs, ignore_index=True)
    tab = df[df.h.isin(C.HORIZONS_Y)]
    agg, per = panel_summary(tab)
    chosen, score = _select(agg, C.HORIZONS_Y)
    return {"forecasts": df, "metrics": agg, "per_unit": per, "chosen": chosen, "score": score.to_dict()}


# ------------------------------------------------------------------------------------------ proyección
def _future_q(last: pd.Period) -> pd.PeriodIndex:
    return pd.period_range(last + 1, C.PROJ_END_Q, freq="Q-DEC")


def national_paro_path(scen: str, national: pd.DataFrame, cfg: dict) -> pd.Series:
    """Senda nacional trimestral: valor anual CE (+sensibilidad) + factor estacional nacional medio (últimos 5 años).
    Los trimestres ya observados (EPA) se mantienen."""
    un = national["paro"].dropna()
    hist = un.loc[un.index[-20]:]
    ann = hist.groupby(hist.index.year).transform("mean")
    seas = (hist - ann).groupby(hist.index.quarter).mean()
    seas = seas - seas.mean()
    a = S.annual_path("paro", scen, cfg)
    q = S.quarters("2026Q1")
    path = pd.Series([a[p.year] + seas[p.quarter] for p in q], index=q)
    path.loc[path.index.isin(un.index)] = un.reindex(path.index).dropna()
    return path


def project_quarterly(panel: pd.DataFrame, var: str, chosen: str, models: dict, bt: pd.DataFrame,
                      national: pd.DataFrame | None = None, cfg: dict | None = None) -> pd.DataFrame:
    """Proyección hasta 2030Q4 con el modelo elegido. Intervalos empíricos (cuantiles 10/90 del error de backtest
    del modelo por horizonte, todas las provincias, objetivos <= fin del hold-out)."""
    cfg = cfg or S.load_yaml()
    additive = var == "paro"
    qfun = empirical_abs_quantiles if additive else empirical_log_quantiles
    qt = extend_quantiles(qfun(bt, chosen, max_target=C.HOLDOUT_END_Q), PATH_H_Q + 4)
    wide = panel.pivot(index="period", columns="prov_code", values=var).sort_index()
    rows = []
    scen_list = S.SCENARIOS if (var == "paro" and chosen == "ancla_nacional_revierte") else ["base"]
    pooled_fc = None
    if chosen == "lightgbm_pooled":
        last = wide.dropna(how="all").index[-1]
        w = wide.loc[:last]
        pl = PooledLGBM(w)
        pooled_fc = pl.forecast_all(len(pl.idx) - 1, list(range(1, len(_future_q(last)) + 1)))
    for k, pc in enumerate(wide.columns):
        s = wide[pc].dropna()
        fut = _future_q(s.index[-1])
        H = len(fut)
        for scen in scen_list:
            if chosen == "ancla_nacional_revierte":
                npath = national_paro_path(scen, national, cfg)
                un_full = pd.concat([national["paro"].dropna(), npath[~npath.index.isin(national["paro"].dropna().index)]])
                ar = AnchorRevert(s, national["paro"], None)
                vals, _ = ar.project(len(s) - 1, list(fut), un_full.reindex(fut).values)
                mname = "ancla nacional (CE) + desviación provincial que revierte"
            elif chosen == "lightgbm_pooled":
                vals = np.array([pooled_fc[h][k] for h in range(1, H + 1)])
                mname = "LightGBM pooled directo"
            else:
                vals = models[chosen](s.values, H)
                mname = chosen
            for i, p in enumerate(fut):
                h = i + 1
                lo, hi = qt.loc[h, "q_low"], qt.loc[h, "q_high"]
                v = float(vals[i])
                rows.append({"prov_code": pc, "period": str(p), "variable": var, "escenario": scen, "valor": v,
                             "p10": v + lo if additive else v * np.exp(lo), "p90": v + hi if additive else v * np.exp(hi),
                             "modelo": mname})
    return pd.DataFrame(rows)


def project_annual(annual: pd.DataFrame, var: str, chosen: str, bt: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or S.load_yaml()
    wide = annual_wide(annual, var)
    qt = extend_quantiles(empirical_log_quantiles(bt, chosen, max_target=C.HOLDOUT_END_Q.year), 10)
    rows = []
    for pc in wide.columns:
        s = wide[pc].dropna()
        last = int(s.index[-1])
        years = list(range(last + 1, C.PROJ_END_Y + 1))
        H = len(years)
        scen_list = S.SCENARIOS if (var == "pib_pc" and chosen == "ancla_nacional") else ["base"]
        for scen in scen_list:
            if chosen == "ancla_nacional":
                g = S.annual_path("pib_pc_growth", scen, cfg, years=range(2025, C.PROJ_END_Y + 1))
                vals = s.iloc[-1] * np.cumprod([1 + g[y] / 100 for y in years])
                mname = "ancla nacional (escenario CE/Eurostat: PIB real + IAPC - población)"
            elif chosen == "naive":
                vals = U.naive(s.values, H)
                mname = chosen
            elif chosen == "deriva_log_5a":
                vals = U.log_drift(s.values, H, window=5)
                mname = chosen
            else:
                vals = U.log_drift(s.values, H)
                mname = chosen
            for i, y in enumerate(years):
                v = float(vals[i])
                rows.append({"prov_code": pc, "period": str(y), "variable": var, "escenario": scen, "valor": v,
                             "p10": v * np.exp(qt.loc[i + 1, "q_low"]), "p90": v * np.exp(qt.loc[i + 1, "q_high"]),
                             "modelo": mname})
    return pd.DataFrame(rows)


def scenario_rows(cfg: dict | None = None) -> pd.DataFrame:
    """Euribor 12M (trimestral) e IPC/IAPC España (anual) por escenario, nivel nacional ('00')."""
    cfg = cfg or S.load_yaml()
    rows = []
    obs = set(S.observed_quarters(cfg))
    for scen in S.SCENARIOS:
        for p, v in S.euribor_path(scen, cfg).items():
            rows.append({"prov_code": "00", "period": str(p), "variable": "euribor_12m", "escenario": scen, "valor": v,
                         "p10": np.nan, "p90": np.nan,
                         "modelo": "observado (BCE)" if p in obs else "escenario: BCE sep-2026 3M + diferencial 12M-3M"})
        for y, v in S.annual_path("ipc", scen, cfg).items():
            rows.append({"prov_code": "00", "period": str(y), "variable": "ipc_iapc_espana", "escenario": scen,
                         "valor": v, "p10": np.nan, "p90": np.nan, "modelo": "escenario: CE otoño-2026 (2029-30 mantenido)"})
        for y, v in S.annual_path("paro", scen, cfg).items():
            rows.append({"prov_code": "00", "period": str(y), "variable": "paro_nacional", "escenario": scen,
                         "valor": v, "p10": np.nan, "p90": np.nan, "modelo": "escenario: CE otoño-2026 (2029-30 mantenido)"})
        for y, v in S.annual_path("pib_pc_growth", scen, cfg, years=range(2025, 2031)).items():
            rows.append({"prov_code": "00", "period": str(y), "variable": "pib_pc_crecimiento_nominal", "escenario": scen,
                         "valor": v, "p10": np.nan, "p90": np.nan, "modelo": "escenario: Eurostat 2025 + CE otoño-2026"})
    return pd.DataFrame(rows)
