"""Modelos univariantes y benchmarks. Firma común: ``f(train: np.ndarray, H: int) -> np.ndarray`` (niveles, pasos 1..H)."""
from __future__ import annotations

import warnings

import numpy as np
import statsmodels.api as sm
from statsmodels.tsa.ar_model import AutoReg, ar_select_order
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")


def naive(y, H):
    return np.repeat(float(y[-1]), H)


def seasonal_naive(y, H, m=4):
    y = np.asarray(y, float)
    return np.array([y[len(y) - 1 + h - m * int(np.ceil(h / m))] for h in range(1, H + 1)])


def mean_last(y, H, k=4):
    return np.repeat(float(np.mean(y[-k:])), H)


def drift(y, H):
    y = np.asarray(y, float)
    b = (y[-1] - y[0]) / (len(y) - 1)
    return y[-1] + b * np.arange(1, H + 1)


def log_drift(y, H, window=None):
    """Random walk con deriva en logaritmos (crecimiento medio; ``window`` = nº de crecimientos recientes)."""
    ly = np.log(np.asarray(y, float))
    g = np.diff(ly)
    g = g[-window:] if window else g
    return np.exp(ly[-1] + g.mean() * np.arange(1, H + 1))


def ets_log(y, H, m=4, damped=True):
    """ETS aditivo (tendencia amortiguada + estacionalidad aditiva) sobre log(y)."""
    ly = np.log(np.asarray(y, float))
    try:
        fit = ExponentialSmoothing(ly, trend="add", damped_trend=damped, seasonal="add" if m > 1 else None,
                                   seasonal_periods=m if m > 1 else None, initialization_method="estimated").fit()
        return np.exp(fit.forecast(H))
    except Exception:
        return naive(y, H)


def hw_damped(y, H, m=4):
    """Holt-Winters del TFM v1 (niveles, tendencia amortiguada + estacionalidad aditiva)."""
    try:
        fit = ExponentialSmoothing(np.asarray(y, float), trend="add", damped_trend=True, seasonal="add",
                                   seasonal_periods=m).fit(optimized=True)
        return np.asarray(fit.forecast(H))
    except Exception:
        return naive(y, H)


def ets_level_damped(y, H):
    """Holt amortiguado sin estacionalidad (niveles) — para tasas (paro)."""
    try:
        fit = ExponentialSmoothing(np.asarray(y, float), trend="add", damped_trend=True,
                                   initialization_method="estimated").fit()
        return np.asarray(fit.forecast(H))
    except Exception:
        return naive(y, H)


def sarima_log(y, H, order=(1, 1, 1), seasonal=(1, 0, 0, 4)):
    try:
        fit = sm.tsa.SARIMAX(np.log(np.asarray(y, float)), order=order, seasonal_order=seasonal).fit(disp=False)
        return np.exp(fit.forecast(H))
    except Exception:
        return naive(y, H)


def arima_level(y, H, order=(3, 1, 2)):
    try:
        fit = sm.tsa.ARIMA(np.asarray(y, float), order=order).fit()
        return np.asarray(fit.forecast(H))
    except Exception:
        return naive(y, H)


def ar_log(y, H, maxlag=4):
    ly = np.log(np.asarray(y, float))
    try:
        sel = ar_select_order(ly, maxlag=maxlag, ic="aic", trend="c")
        lags = sel.ar_lags if sel.ar_lags else [1]
        fit = AutoReg(ly, lags=lags, trend="c").fit()
        return np.exp(fit.predict(start=len(ly), end=len(ly) + H - 1))
    except Exception:
        return naive(y, H)


def seasonal_naive_scale(y, m=4):
    """Escala MASE: MAE in-sample del seasonal naive (m=1 -> naive)."""
    y = np.asarray(y, float)
    if len(y) <= m:
        return np.nan
    return float(np.mean(np.abs(y[m:] - y[:-m])))


QUARTERLY_BENCHMARKS = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "media_movil_4": mean_last,
    "drift": drift,
}
