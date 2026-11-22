"""Tests offline de validación y reconciliación."""
import pandas as pd

from src.common.io import STAGING_COLUMNS
from src.validation import checks, reconciliation


def _stg(values, var="hipotecas_viviendas_num", geo="28"):
    return pd.DataFrame({"dataset": "t", "variable": var, "geo_level": "provincia", "geo_code": geo, "period": [f"2024-{i+1:02d}" for i in range(len(values))],
                         "freq": "M", "ref_date": [f"2024-{i+1:02d}-01" for i in range(len(values))], "value": values, "unit": "n",
                         "status": None, "source": "INE", "series_id": "X", "snapshot": "s", "retrieved_at": "r"})[STAGING_COLUMNS]


def test_integer_detector_catches_thousands_bug():
    iss = checks.check_integer_format(_stg([17.49, 13304.0, 398.0]), "t")
    assert iss and iss[0]["check"] == "numeric_format" and iss[0]["n"] == 1


def test_ranges_and_duplicates():
    df = _stg([100.0, 1e9])
    assert any(i["check"] == "range" for i in checks.check_staging(df, "t"))
    dup = pd.concat([df, df])
    assert any(i["check"] == "duplicates" for i in checks.check_schema(dup, STAGING_COLUMNS, "t", ["variable", "geo_code", "ref_date"]))


def test_reconcile_totals():
    nac = pd.DataFrame({"period": ["2024Q1", "2024Q2"], "x": [100.0, 100.0], "x_suma_prov": [100.0, 90.0]})
    iss = checks.reconcile_totals(nac, [("x", "x_suma_prov")])
    assert iss[0]["n"] == 1 and iss[0]["severity"] == "warning"


def test_diff_staging_new_revised_removed():
    old = _stg([1.0, 2.0, 3.0])
    new = _stg([1.0, 5.0])
    new = pd.concat([new, _stg([9.0]).assign(ref_date="2024-12-01")])
    d = reconciliation.diff_staging(old, new)["hipotecas_viviendas_num"]
    assert d == {**d, "new": 1, "revised": 1, "removed": 1, "same": 1}


def test_panel_coverage():
    p = pd.DataFrame({"prov_code": [f"{i:02d}" for i in range(1, 52)], "period": "2024Q1", "tasa_paro": 10.0})
    assert any(i["check"] == "coverage" for i in checks.check_panel(p, ["prov_code", "period"], "t"))
