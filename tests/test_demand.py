"""Tests rápidos de la demanda v2 y del pipeline de proyecciones (sin ejecutar el pipeline completo)."""
import numpy as np
import pandas as pd
import pytest

from src.models.demand.evaluate import publication_table
from src.models.demand.features import national_frame, origin_features
from src.models.demand.models import ConditionalOLS
from src.models.forecasting import scenarios as S
from src.models.forecasting.backtest import interval_coverage, rolling_origin
from src.models.forecasting import univariate as U


def _nat(n=70, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2005Q1", periods=n, freq="Q-DEC")
    return pd.DataFrame({"hip_viv": 1e5 * np.exp(np.cumsum(rng.normal(0, .04, n))),
                         "euribor": 2 + rng.normal(0, .3, n).cumsum() * .1 + 1, "paro": 12 + rng.normal(0, .2, n),
                         "precio": 1500 + np.arange(n) * 5.0, "transmisiones": 1e5 * np.exp(rng.normal(0, .05, n)),
                         "ipc": 2.0}, index=idx)


def test_features_use_only_past():
    f = national_frame(_nat(), "hip_viv")
    a = origin_features(f, 30)
    f2 = f.copy()
    f2.iloc[31:] = f2.iloc[31:] * 7  # cambiar el futuro no altera las features del origen
    assert a == origin_features(f2, 30)


def test_conditional_ols_runs_and_positive():
    f = national_frame(_nat(), "hip_viv")
    out = ConditionalOLS(f, cap_h=1).forecast(50, [1, 2, 4])
    assert set(out) == {1, 2, 4} and all(v > 0 for v in out.values())


def test_scenarios_euribor_observed_untouched():
    cfg = S.load_yaml()
    b, a = S.euribor_path("base", cfg), S.euribor_path("adverso", cfg)
    obs = S.observed_quarters(cfg)
    assert all(b[q] == a[q] for q in obs)
    assert (a.drop(obs) > b.drop(obs)).all()
    assert cfg["fuentes"]["ce_otono2026"]["fecha_edicion"]


def test_coverage_and_publication_table():
    s = _nat()["hip_viv"]
    df = rolling_origin(s, {"naive": U.naive}, list(s.index[24:-1]), [1, 4], unit="n")
    cov = interval_coverage(df, "naive")
    assert (cov.cobertura_holdout.between(0, 1)).all()
    from src.models.forecasting.metrics import summarise
    met = summarise(df)
    t = publication_table(met, pd.DataFrame(columns=["h", "window", "model", "benchmark", "DM_sq", "p_sq", "DM_abs", "p_abs"]),
                          pd.DataFrame(columns=["h", "window", "model", "benchmark", "DM_sq", "p_sq", "DM_abs", "p_abs"]),
                          {1: "naive", 4: "naive"})
    assert "elegido_en_seleccion" in t and t.elegido_en_seleccion.all()
