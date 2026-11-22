"""Tests del forecasting v2 (rápidos; no ejecutan el pipeline completo)."""
import numpy as np
import pandas as pd
import pytest

from src.models.forecasting import config as C
from src.models.forecasting import scenarios as S
from src.models.forecasting import univariate as U
from src.models.forecasting.backtest import rolling_origin, select_models, window_of
from src.models.forecasting.metrics import dm_test, mase, smape, summarise, theil_u
from src.models.demand.features import national_frame, origin_features
from src.models.demand.models import ConditionalOLS


def _series(n=60, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2005Q1", periods=n, freq="Q-DEC")
    return pd.Series(1000 * np.exp(np.cumsum(rng.normal(0.0, 0.05, n))), index=idx)


def test_seasonal_naive_and_naive():
    y = np.arange(1, 9, dtype=float)
    assert list(U.seasonal_naive(y, 5)) == [5, 6, 7, 8, 5]
    assert list(U.naive(y, 2)) == [8, 8]


def test_metrics_basic():
    assert smape([1, 2], [1, 2]) == 0
    assert mase([2, 2], [1, 3], [1, 1]) == 1
    assert theil_u([1, 2, 3], [1, 2, 3], [0, 0, 0]) == 0
    s, p = dm_test(np.ones(30) * 0.1, np.ones(30) * 1.0 + np.random.default_rng(1).normal(0, 0.1, 30), h=1)
    assert s < 0 and p < 0.05


def test_windows():
    assert window_of(pd.Period("2021Q4", "Q-DEC")) == "seleccion"
    assert window_of(pd.Period("2022Q1", "Q-DEC")) == "holdout"
    assert window_of(pd.Period("2026Q1", "Q-DEC")) == "oos_extra"
    assert window_of(2021) == "seleccion" and window_of(2023) == "holdout"


def test_rolling_origin_uses_only_past():
    """El modelo solo recibe datos <= origen: un 'oráculo' que mirase el futuro fallaría la comprobación."""
    s = _series()
    seen = []

    def spy(train, H):
        seen.append(len(train))
        return U.naive(train, H)

    origins = list(s.index[20:40])
    df = rolling_origin(s, {"spy": spy}, origins, [1, 4])
    pos = {p: i for i, p in enumerate(s.index)}
    assert seen == [pos[o] + 1 for o in origins]
    assert (df.target > df.origin).all()
    # el naive a h reproduce y_T
    r = df.iloc[0]
    assert r.yhat == pytest.approx(s.loc[r.origin])


def test_selection_ignores_holdout():
    m = pd.DataFrame({"model": ["a", "b", "a", "b"], "h": [1, 1, 1, 1], "window": ["seleccion", "seleccion", "holdout", "holdout"],
                      "MASE": [1.0, 2.0, 9.0, 0.1], "RMSE": [1, 1, 1, 1]})
    assert select_models(m)[1] == "a"


def test_origin_features_no_future():
    s = _series(40)
    nat = pd.DataFrame({"hip_viv": s, "euribor": 1.0, "paro": 10.0, "precio": 2000.0, "transmisiones": 5000.0, "ipc": 2.0})
    f = national_frame(nat, "hip_viv")
    a = origin_features(f, 20)
    f2 = f.copy()
    f2.iloc[21:, :] = f2.iloc[21:, :] * 3  # alterar el futuro no cambia las features en el origen
    assert origin_features(f2, 20) == a


def test_conditional_trains_only_on_past_targets():
    s = _series(60)
    nat = pd.DataFrame({"hip_viv": s, "euribor": np.linspace(1, 3, 60), "paro": np.linspace(15, 10, 60),
                        "precio": 2000.0, "transmisiones": 5000.0, "ipc": 2.0})
    f = national_frame(nat, "hip_viv")
    m = ConditionalOLS(f, cap_h=1)
    b1 = m.fit_h(40, 1)
    m2 = ConditionalOLS(f.assign(y=np.r_[f.y.values[:41], f.y.values[41:] * 5]), cap_h=1)
    assert np.allclose(b1, m2.fit_h(40, 1))


def test_scenarios_yaml():
    cfg = S.load_yaml()
    e = S.euribor_path("base", cfg)
    assert str(e.index[0]) == "2026Q1" and str(e.index[-1]) == "2030Q4"
    # lo observado no cambia entre escenarios; las sensibilidades sí desplazan el futuro
    ea, eb = S.euribor_path("adverso", cfg), S.euribor_path("base", cfg)
    assert ea["2026Q1"] == eb["2026Q1"] and ea["2028Q1"] > eb["2028Q1"]
    assert S.annual_path("ipc", "base", cfg)[2026] == pytest.approx(3.9)
    assert S.annual_path("paro", "base", cfg)[2030] == pytest.approx(9.4)
    for blk in ("bce_sep2026", "ce_otono2026"):
        assert cfg["fuentes"][blk]["url"].startswith("https://")


def test_output_csv_if_present():
    p = C.FORECASTS_DIR / "proyecciones_2026_2030_v2.csv"
    if not p.exists():
        pytest.skip("pipeline no ejecutado")
    d = pd.read_csv(p, dtype={"prov_code": str})
    assert list(d.columns) == ["provincia", "prov_code", "period", "variable", "escenario", "valor", "p10", "p90", "modelo"]
    paro = d[d.variable == "tasa_paro"]
    assert paro.valor.min() < 8.5 or paro.empty  # sin suelo NAIRU
    pib = d[d.variable == "pib_pc"]
    assert pib.period.astype(str).str.len().eq(4).all()  # anual, sin replicar en trimestres
    q = d[d.variable.isin(["hipotecas_viviendas", "precio_m2_mivau"])].dropna(subset=["p10", "p90"])
    assert (q.p10 <= q.p90).all()
