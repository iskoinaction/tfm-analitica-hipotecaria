"""Tests rápidos (< 1 min) del paquete src.models.econometrics con datos simulados."""
import itertools

import numpy as np
import pandas as pd
import pytest

from src.models.econometrics import irf_fevd as F
from src.models.econometrics.cointegration import Johansen, wild_bootstrap_trace
from src.models.econometrics.data import (impulse_dummies, resolve_columns,
                                          seasonal_dummies, NATIONAL_RULES)
from src.models.econometrics.panel import cd_test, mg_pmg
from src.models.econometrics.var import VARdiff
from src.models.econometrics.vecm import VECMfit, lr_weak_exog


def coint_system(T=150, seed=0):
    """y1 = 2*x + u (u AR(0.5)); x paseo aleatorio; z paseo aleatorio independiente."""
    rng = np.random.default_rng(seed)
    x = np.cumsum(rng.standard_normal(T)) + 0.05 * np.arange(T)
    z = np.cumsum(rng.standard_normal(T))
    u = np.zeros(T)
    for t in range(1, T):
        u[t] = 0.5 * u[t - 1] + rng.standard_normal()
    return np.column_stack([2 * x + u, x, z])


def test_johansen_matches_statsmodels_case3():
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    y = coint_system()
    J = Johansen(y, 1, 3)
    sm = coint_johansen(y, 0, 1)
    assert np.allclose(J.trace, sm.lr1, atol=1e-6)
    assert np.allclose(J.maxeig, sm.lr2, atol=1e-6)
    assert np.allclose(J.cv("trace"), sm.cvt[:, 1], atol=1e-3)


def test_vecm_recovers_beta_and_weak_exogeneity():
    y = coint_system(T=300, seed=1)
    f = VECMfit(y, 1, 3, None, 1, norm_idx=0)
    assert f.beta[1, 0] == pytest.approx(-2.0, abs=0.1)     # y1 - 2 x
    assert abs(f.beta[2, 0]) < 0.3
    assert lr_weak_exog(f.J, 1)["p"] > 0.01                  # x débilmente exógena (DGP)
    assert lr_weak_exog(f.J, 0)["p"] < 0.01                  # y1 corrige
    r = f.roots()
    assert np.sum(np.isclose(r, 1, atol=1e-6)) == 2          # n - r raíces unitarias


def test_wild_bootstrap_rank_detects_cointegration():
    y = coint_system(T=150, seed=2)
    _, p = wild_bootstrap_trace(y, 1, 3, None, B=49, rmax=2, seed=3)
    assert p[0] < 0.1 and p[1] > 0.05


def test_bootstrap_reconstruction_identity():
    """Con residuos sin remuestrear, la simulación del VECM reproduce exactamente los datos."""
    y = coint_system(T=80, seed=4)
    ex = seasonal_dummies(pd.period_range("2000Q1", periods=80, freq="Q")).values
    f = VECMfit(y, 1, 3, ex, 1, norm_idx=0)
    assert np.allclose(f.simulate(f.resid), y, atol=1e-8)


def test_fevd_and_gfevd_rows_sum_to_one_and_order_invariance():
    rng = np.random.default_rng(5)
    A = rng.normal(scale=0.2, size=(3, 3))
    Phi = np.array([np.linalg.matrix_power(A, h) for h in range(11)])
    M = rng.normal(size=(3, 3)); S = M @ M.T + np.eye(3)
    fv = F.fevd(Phi[:10], S, order=[2, 0, 1])
    assert np.allclose(fv.sum(2), 1)
    assert np.allclose(F.gfevd(Phi[:10], S).sum(2), 1)
    g1 = F.girf(Phi, S)
    # GIRF del shock j coincide con Cholesky cuando j va primero
    for j in range(3):
        order = [j] + [i for i in range(3) if i != j]
        assert np.allclose(F.orth_irf(Phi, S, order)[:, :, j], g1[:, :, j])
    rng_ = F.fevd_order_range(Phi, S, 0, 10)
    assert rng_["n_orders"] == len(list(itertools.permutations(range(3))))
    assert np.all(rng_["min"] <= rng_["max"])


def test_var_diff_ma_and_resample():
    rng = np.random.default_rng(6)
    dy = rng.standard_normal((100, 2))
    m = VARdiff(dy, 2)
    assert m.ma_rep(5).shape == (6, 2, 2)
    m2 = m.resample(rng)
    assert m2.B.shape == m.B.shape and np.max(m.roots()) < 1


def test_resolve_columns_and_dummies():
    df = pd.DataFrame(columns=["period", "hipotecas_viviendas_num", "hipotecas_viviendas_importe",
                               "hipotecas_total_fincas_num", "precio_m2_mivau_tasado", "precio_ipv",
                               "pib_pc", "euribor_12m", "indice_materiales"])
    cm = resolve_columns(df, NATIONAL_RULES, ["period", "hip_viv", "precio_mivau", "euribor", "materiales"])
    assert cm["hip_viv"] == "hipotecas_viviendas_num" and cm["hip_tot"] == "hipotecas_total_fincas_num"
    assert cm["precio_mivau"] == "precio_m2_mivau_tasado" and cm["precio_ipv"] == "precio_ipv"
    idx = pd.period_range("2019Q1", "2021Q4", freq="Q")
    sd = seasonal_dummies(idx)
    assert np.allclose(sd.sum(axis=0), 0)
    assert impulse_dummies(idx, ["2020Q2"]).sum().iloc[0] == 1


def test_panel_cd_and_pmg_on_simulated_panel():
    rng = np.random.default_rng(7)
    N, T = 12, 60
    idx = pd.period_range("2005Q1", periods=T, freq="Q")
    rows = []
    for i in range(N):
        x = np.cumsum(rng.standard_normal(T))
        y = np.zeros(T)
        for t in range(1, T):
            y[t] = y[t - 1] - 0.5 * (y[t - 1] - 1.5 * x[t - 1]) + rng.standard_normal() * 0.3
        rows += [{"prov_code": f"{i:02d}", "period": p, "y": a, "x": b} for p, a, b in zip(idx, y, x)]
    df = pd.DataFrame(rows)
    r = mg_pmg(df, "y", ["x"], demean=False)
    assert r["PMG"]["x"]["coef"] == pytest.approx(1.5, abs=0.15)
    assert r["PMG_phi_medio"] < 0
    W = pd.DataFrame(rng.standard_normal((T, N)))
    assert abs(cd_test(W)["CD"]) < 4


def test_run_quick_smoke(tmp_path):
    from src.models.econometrics import run
    res = run.main(["--quick", "--out", str(tmp_path)])
    assert (tmp_path / "econometrics_v2.json").exists()
    assert (tmp_path / "irf_hipotecas.csv").exists() and (tmp_path / "fevd_hipotecas.csv").exists()
    assert res["decision"]["modelo_principal"] in ("VECM (r=1)", "VAR en diferencias")
    assert res["metadatos"]["entradas"] and all(len(e["sha256"]) == 64 for e in res["metadatos"]["entradas"])
