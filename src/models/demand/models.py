"""Modelos de demanda (serie nacional trimestral).

* ``DirectML``: estrategia directa, objetivo log(y_{T+h}/y_T), features con información <= T (ver features.py).
* ``ConditionalOLS``: MCO por horizonte, log(y_{T+h}/y_T) ~ ΔEuribor(T→T+h) + Δparo_ma4(T→T+h) + gap + dummies
  del trimestre objetivo. Usa las exógenas del PERIODO OBJETIVO: en backtest con valores realizados (previsión
  *ex post*, cota superior de lo que aportaría conocer el escenario) y en producción con la senda del escenario.
  No compite en la selección de modelos de previsión: se reporta aparte y se usa para las sendas condicionales.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import ElasticNetCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.models.forecasting import config as C
from src.models.forecasting.backtest import ContextForecaster
from .features import add_target_quarter, origin_features


def ml_factories() -> dict:
    import lightgbm as lgb
    import xgboost as xgb
    s, nj = C.SEED, C.N_JOBS
    return {
        "elasticnet": lambda: make_pipeline(StandardScaler(), ElasticNetCV(l1_ratio=[0.1, 0.5, 0.9, 0.99], cv=3,
                                                                           max_iter=20000, random_state=s)),
        "random_forest": lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=3, max_features=0.5,
                                                       random_state=s, n_jobs=nj),
        "gbm": lambda: GradientBoostingRegressor(n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8,
                                                 random_state=s),
        "xgboost": lambda: xgb.XGBRegressor(n_estimators=300, max_depth=2, learning_rate=0.05, subsample=0.8,
                                            colsample_bytree=0.8, random_state=s, n_jobs=nj, verbosity=0),
        "lightgbm": lambda: lgb.LGBMRegressor(n_estimators=300, max_depth=3, num_leaves=7, learning_rate=0.05,
                                              min_child_samples=5, subsample=0.8, subsample_freq=1,
                                              colsample_bytree=0.8, random_state=s, n_jobs=nj, verbose=-1),
    }


class _FeatureCache:
    def __init__(self, f: pd.DataFrame, intercept: bool = False, cap_h: int | None = 4):
        self.intercept = intercept
        self.cap_h = cap_h  # para h > cap_h se reutilizan las elasticidades estimadas a cap_h (persistencia + escenario)
        self.f = f
        self.idx = list(f.index)
        self.ly = np.log(f["y"].values)
        self.feats = {i: origin_features(f, i) for i in range(len(f))}


class DirectML(ContextForecaster):
    def __init__(self, cache: _FeatureCache, factory):
        self.c, self.factory = cache, factory

    def forecast(self, pos, horizons):
        out = {}
        xo = self.c.feats.get(pos)
        if xo is None:
            return out
        for h in horizons:
            if pos + h >= len(self.c.idx):
                continue
            X, t = [], []
            for j in range(0, pos - h + 1):
                fj = self.c.feats.get(j)
                if fj is None:
                    continue
                X.append(add_target_quarter(fj, self.c.idx[j + h]))
                t.append(self.c.ly[j + h] - self.c.ly[j])
            if len(X) < 20:
                continue
            X = pd.DataFrame(X)
            m = self.factory()
            m.fit(X, np.asarray(t))
            xq = pd.DataFrame([add_target_quarter(xo, self.c.idx[pos + h])])[X.columns]
            out[h] = float(np.exp(self.c.ly[pos] + m.predict(xq)[0]))
        return out


class ConditionalOLS(ContextForecaster):
    """Ver docstring del módulo. ``exog_future`` permite pasar exógenas de escenario (producción)."""

    cols = ["d_eur", "d_paro", "gap_ma4", "q2", "q3", "q4"]

    def __init__(self, f: pd.DataFrame, intercept: bool = False, cap_h: int | None = 4):
        self.intercept = intercept
        self.cap_h = cap_h  # para h > cap_h se reutilizan las elasticidades estimadas a cap_h (persistencia + escenario)
        self.f = f
        self.idx = list(f.index)
        self.ly = np.log(f["y"].values)
        self.eur = f["euribor"].values
        self.paro = f["paro_ma4"].values
        self.y = f["y"].values

    def _row(self, j, h, eur_t, paro_t, period_t, eur_j=None, paro_j=None):
        if j < 4:
            return None
        eur_j = self.eur[j] if eur_j is None else eur_j
        paro_j = self.paro[j] if paro_j is None else paro_j
        r = {"d_eur": eur_t - eur_j, "d_paro": paro_t - paro_j,
             "gap_ma4": self.ly[j] - np.log(np.mean(self.y[j - 3:j + 1]))}
        po = self.idx[j]
        for k in (2, 3, 4):  # estacionalidad en niveles: D_k(objetivo) - D_k(origen); válida para cualquier h
            r[f"q{k}"] = float(period_t.quarter == k) - float(po.quarter == k)
        return r if np.all(np.isfinite(list(r.values()))) else None

    def fit_h(self, pos, h):
        if self.cap_h and h > self.cap_h:
            h = self.cap_h
        X, t = [], []
        for j in range(0, pos - h + 1):
            r = self._row(j, h, self.eur[j + h], self.paro[j + h], self.idx[j + h])
            if r is not None:
                X.append([r[c] for c in self.cols])
                t.append(self.ly[j + h] - self.ly[j])
        if len(X) < 20:
            return None
        X = np.asarray(X)
        if self.intercept:
            X = np.column_stack([np.ones(len(X)), X])
        beta, *_ = np.linalg.lstsq(X, np.asarray(t), rcond=None)
        return beta

    def forecast(self, pos, horizons):
        out = {}
        for h in horizons:
            if pos + h >= len(self.idx):
                continue
            beta = self.fit_h(pos, h)
            r = self._row(pos, h, self.eur[pos + h], self.paro[pos + h], self.idx[pos + h])
            if beta is None or r is None:
                continue
            x = np.r_[[1.0] if self.intercept else [], [r[c] for c in self.cols]]
            out[h] = float(np.exp(self.ly[pos] + x @ beta))
        return out

    def forecast_scenario(self, pos, horizons, eur_path: dict, paro_ma4_path: dict, periods: dict,
                          eur_origin: float, paro_ma4_origin: float):
        """Producción: exógenas de escenario (indexadas por h). El ajuste usa solo filas con exógenas OBSERVADAS
        (las del frame original); el origen puede tener exógenas empalmadas con el escenario (eur/paro_origin)."""
        out, coefs = {}, {}
        for h in horizons:
            beta = self.fit_h(pos + 0, h) if pos - h + 1 > 0 else None
            # en producción se entrena con TODA la historia disponible (objetivos <= pos)
            if beta is None:
                continue
            r = self._row(pos, h, eur_path[h], paro_ma4_path[h], periods[h], eur_origin, paro_ma4_origin)
            if r is None:
                continue
            x = np.r_[[1.0] if self.intercept else [], [r[c] for c in self.cols]]
            out[h] = float(np.exp(self.ly[pos] + x @ beta))
            coefs[h] = dict(zip((["const"] if self.intercept else []) + self.cols, map(float, beta)))
        return out, coefs
