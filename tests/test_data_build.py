"""Tests offline de transformaciones, paneles y snapshots."""
import json

import pandas as pd

from src.common import config, io
from src.common.geography import PROVINCES
from src.transformations import panels, temporal


def test_monthly_to_quarterly_requires_three_months():
    d = pd.DataFrame({"variable": "v", "geo_level": "provincia", "geo_code": "28",
                      "ref_date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"], "value": [1.0, 2.0, 3.0, 4.0]})
    q = temporal.monthly_to_quarterly(d, "sum")
    assert list(q["period"]) == ["2024Q1"] and q["value"].iloc[0] == 6.0
    assert temporal.monthly_to_quarterly(d, "mean")["value"].iloc[0] == 2.0


def test_available_ref_year():
    end = pd.Timestamp("2025-03-31")
    assert temporal.available_ref_year(end, 5) == 2024      # población 1-ene-2025 aún no publicada en marzo
    assert temporal.available_ref_year(pd.Timestamp("2025-06-30"), 5) == 2025
    assert temporal.available_ref_year(end, 35) == 2022      # PIB provincial: ~3 años de retraso


def _synthetic_staging():
    rows_q, rows_a, rows_m = [], [], []
    for c in PROVINCES:
        for m in range(1, 7):
            rows_m.append({"variable": "hipotecas_viviendas_num", "geo_level": "provincia", "geo_code": c,
                           "ref_date": f"2005-{m:02d}-01", "value": 10.0, "status": "Definitivo"})
        for q in ("2005-01-01", "2005-04-01"):
            rows_q.append({"variable": "tasa_paro", "geo_level": "provincia", "geo_code": c, "ref_date": q, "value": 12.0, "status": None})
        for y in (2004, 2005):
            rows_a.append({"variable": "poblacion", "geo_level": "provincia", "geo_code": c, "ref_date": f"{y}-01-01", "value": 1000.0 + y, "status": "Definitivo"})
    for m in range(1, 7):
        rows_m.append({"variable": "hipotecas_viviendas_num", "geo_level": "nacional", "geo_code": "00",
                       "ref_date": f"2005-{m:02d}-01", "value": 520.0, "status": None})
    return {"ine_hipotecas": pd.DataFrame(rows_m), "ine_epa_paro": pd.DataFrame(rows_q), "ine_ecp_poblacion": pd.DataFrame(rows_a)}


def test_build_panels_synthetic():
    stg = _synthetic_staging()
    q = panels.quarterly_long(stg)
    pt = panels.build_panel_trimestral(q)
    assert pt.shape[0] == 52 * 2 and (pt["hipotecas_viviendas_num"] == 30.0).all()
    pa = panels.build_panel_anual(stg, start_year=2004)
    assert set(pa["year"]) == {2004, 2005} and not pa.duplicated(["prov_code", "year"]).any()
    pm = panels.build_panel_modelado(pt, pa)
    r = pm[pm.period == "2005Q1"].iloc[0]
    assert r["poblacion_ref_year"] == 2004 and r["poblacion"] == 3004.0   # sin look-ahead
    nac = panels.build_nacional(q, pt, stg)
    row = nac[nac.period == "2005Q1"].iloc[0]
    assert row["hipotecas_viviendas_num"] == 1560.0 and row["hipotecas_viviendas_num_suma_prov"] == 52 * 30.0


def test_snapshot_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW", tmp_path / "raw")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    p1, m1, c1 = io.save_snapshot("ine", "ds", {"a": 1}, {"retrieved_at": "t"}, "h1")
    p2, m2, c2 = io.save_snapshot("ine", "ds", {"a": 1}, {"retrieved_at": "t"}, "h1")
    assert c1 and not c2 and p1 == p2                     # sin cambios: no se escribe
    p3, m3, c3 = io.save_snapshot("ine", "ds", {"a": 2}, {"retrieved_at": "t"}, "h2")
    assert c3 and p3 != p1 and p1.exists()                # nuevo snapshot, el anterior se conserva
    assert m3["previous_snapshot"] is not None
    assert io.read_snapshot(p1) == {"a": 1}


def test_processed_outputs_if_present():
    """Si los paneles reales existen, comprobar claves y cobertura (no falla si aún no se han construido)."""
    p = config.PROCESSED / "panel_trimestral.csv"
    if not p.exists():
        return
    pt = pd.read_csv(p, dtype={"prov_code": str})
    assert not pt.duplicated(["prov_code", "period"]).any()
    assert (pt.groupby("period")["prov_code"].nunique() == 52).all()
    hv = pt["hipotecas_viviendas_num"].dropna()
    assert ((hv % 1) == 0).all()
