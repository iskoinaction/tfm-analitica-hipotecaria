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
    def __init__(self, f: pd.DataFrame):
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

    def __init__(self, f: pd.DataFrame):
        self.f = f
        self.idx = list(f.index)
        self.ly = np.log(f["y"].values)
        self.eur = f["euribor"].values
        self.paro = f["paro_ma4"].values
        self.y = f["y"].values

    def _row(self, j, h, eur_t, paro_t, period_t):
        if j < 4:
            return None
        r = {"d_eur": eur_t - self.eur[j], "d_paro": paro_t - self.paro[j],
             "gap_ma4": self.ly[j] - np.log(np.mean(self.y[j - 3:j + 1]))}
        r = add_target_quarter(r, period_t)
        return r if np.all(np.isfinite(list(r.values()))) else None

    def fit_h(self, pos, h):
        X, t = [], []
        for j in range(0, pos - h + 1):
            r = self._row(j, h, self.eur[j + h], self.paro[j + h], self.idx[j + h])
            if r is not None:
                X.append([r[c] for c in self.cols])
                t.append(self.ly[j + h] - self.ly[j])
        if len(X) < 20:
            return None
        X = np.column_stack([np.ones(len(X)), np.asarray(X)])
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
            x = np.r_[1.0, [r[c] for c in self.cols]]
            out[h] = float(np.exp(self.ly[pos] + x @ beta))
        return out

    def forecast_scenario(self, pos, horizons, eur_path: dict, paro_ma4_path: dict, periods: dict):
        """Producción: exógenas de escenario. eur_path/paro_ma4_path/periods indexados por h."""
        out, coefs = {}, {}
        for h in horizons:
            beta = self.fit_h(pos + 0, h) if pos - h + 1 > 0 else None
            # en producción se entrena con TODA la historia disponible (objetivos <= pos)
            if beta is None:
                continue
            r = self._row(pos, h, eur_path[h], paro_ma4_path[h], periods[h])
            if r is None:
                continue
            x = np.r_[1.0, [r[c] for c in self.cols]]
            out[h] = float(np.exp(self.ly[pos] + x @ beta))
            coefs[h] = dict(zip(["const", *self.cols], map(float, beta)))
        return out, coefs
