"""Pruebas rápidas de integridad de la econometría v2 (datos v2, regla de decisión, sin imputación)."""
import json

import numpy as np
import pandas as pd
import pytest

from src.models.econometrics import config as C
from src.models.econometrics import data as D
from src.models.econometrics.unit_root import battery

ART = C.ARTIFACTS / "econometrics_v2.json"


def test_system_fully_observed_no_imputation():
    nd = D.load_national("v2")
    Y = nd.system("hip_viv", "precio_mivau")
    assert not Y.isna().any().any()
    idx = pd.PeriodIndex(Y.index)
    assert idx.is_unique and len(idx) == (idx[-1] - idx[0]).n + 1   # trimestres contiguos
    assert str(Y.index[0]) == C.START


def test_unit_root_battery_has_adf_kpss_za():
    rng = np.random.default_rng(C.SEED)
    s = pd.Series(np.cumsum(rng.normal(size=100)))
    keys = set().union(*[r.keys() for r in battery("x", s)])
    assert {"adf_aic_p", "kpss_p", "za_ct_p", "dfgls_p", "pp_p"} <= keys


@pytest.mark.skipif(not ART.exists(), reason="ejecutar python -m src.models.econometrics.run")
def test_decision_rule_consistent_with_bootstrap_pvalue():
    r = json.loads(ART.read_text(encoding="utf-8"))
    d = r["decision"]
    vecm_main = d["p_bootstrap_r0"] < C.SPEC["alpha_rank_decision"]
    assert d["modelo_principal"] == ("VECM (r=1)" if vecm_main else "VAR en diferencias")
    assert r["metadatos"]["provisional"] is False
    assert r["metadatos"]["B_rank"] >= 999
