"""Tests offline de parseo (pipeline de datos v2)."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.common import config
from src.ingestion.ecb import ECBConnector
from src.ingestion.eurostat import jsonstat_to_frame
from src.ingestion.ine import INEConnector, geo_of, match_variable
from src.ingestion.vivienda import parse_vdp006
from src.transformations.v1_corrected import nb3_limpiar_numero, parse_v1_count

FX = Path(__file__).parent / "fixtures_data"


@pytest.mark.parametrize("raw,expected", [("17.49", 17490), ("1.041", 1041), ("398.0", 398), ("1.07", 1070),
                                          ("2.5", 2500), ("12", 12), ("1.234,5", 1234.5)])
def test_parse_v1_count(raw, expected):
    assert parse_v1_count(raw) == expected


def test_nb3_bug_reproduced():
    # el parseo v1 leía "17.49" (17.490 hipotecas) como 17,49
    assert nb3_limpiar_numero("17.49") == 17.49
    assert nb3_limpiar_numero("1.041") == 1041


def _ine_series(cod, nat, concepto, prov_name, prov_code, values):
    return {"COD": cod, "Nombre": f"{nat}. {concepto}. {prov_name}.", "T3_Unidad": "Hipotecas", "T3_Escala": " ",
            "MetaData": [{"T3_Variable": "Naturaleza de la finca", "Nombre": nat, "Codigo": ""},
                         {"T3_Variable": "Concepto financiero", "Nombre": concepto, "Codigo": ""},
                         {"T3_Variable": "Provincias", "Nombre": prov_name, "Codigo": prov_code},
                         {"T3_Variable": "Tipo de muestreo", "Nombre": "Base nueva. Mensual", "Codigo": "1"}],
            "Data": [{"Fecha": f"2024-{m:02d}-01T00:00:00.000+01:00", "T3_TipoDato": "Definitivo", "Valor": v}
                     for m, v in enumerate(values, start=1)]}


def test_ine_parse_uses_metadata_codes_and_numeric_value():
    spec = config.DATASET_BY_KEY["ine_hipotecas"]
    s1 = _ine_series("X1", "Viviendas", "Número de hipotecas", "Madrid", "28", [5000.0, 6000.0, 7000.0])
    s2 = _ine_series("X2", "Solares", "Número de hipotecas", "Madrid", "28", [1.0, 1.0, 1.0])
    assert match_variable(s1, spec).name == "hipotecas_viviendas_num"
    assert match_variable(s2, spec) is None
    assert geo_of(s1, spec.geo_vars) == ("provincia", "28")
    df = INEConnector().parse({"table": "3200", "series": {"X1": s1}}, spec, {})
    assert list(df["value"]) == [5000.0, 6000.0, 7000.0]
    assert set(df["geo_code"]) == {"28"} and set(df["period"]) == {"2024-01", "2024-02", "2024-03"}


def test_ine_uniprovincial_ccaa_completed_as_province():
    spec = config.DATASET_BY_KEY["ine_cre_pib_pc"]
    def s(cod, var, name, code, val):
        return {"COD": cod, "Nombre": name, "MetaData": [{"T3_Variable": var, "Nombre": name, "Codigo": code},
                {"T3_Variable": "Tipo de dato", "Nombre": "Dato base", "Codigo": ""},
                {"T3_Variable": "SALDOS CONTABLES", "Nombre": "Producto interior bruto a precios de mercado per capita", "Codigo": "03"}],
                "Data": [{"Fecha": "2023-01-01T00:00:00.000+01:00", "T3_TipoDato": "Definitivo", "Valor": val}]}
    payload = {"series": {"A": s("A", "Provincias", "Burgos", "09", 30000.0),
                          "B": s("B", "Comunidades y Ciudades Autónomas", "Madrid, Comunidad de", "13", 44000.0)}}
    df = INEConnector().parse(payload, spec, {})
    prov = df[df.geo_level == "provincia"].set_index("geo_code")["value"]
    assert prov["28"] == 44000.0 and prov["09"] == 30000.0


def test_ecb_parse_monthly():
    spec = config.DATASET_BY_KEY["ecb_tipos"]
    payload = {v.name: {"KEY": ["k"] * 2, "TIME_PERIOD": ["2024-01", "2024-02"], "OBS_VALUE": [3.6, 3.7]} for v in spec.variables}
    df = ECBConnector().parse(payload, spec, {})
    eur = df[df.variable == "euribor_12m"]
    assert set(eur.geo_level) == {"zona_euro"} and list(eur.value) == [3.6, 3.7]
    assert set(df[df.variable == "tae_vivienda"].geo_code) == {"00"}


def test_mivau_parse():
    df = parse_vdp006((FX / "mivau_vdp006_sample.csv").read_bytes())
    v = df.set_index("geo_code")["value"]
    assert v["09"] == 1500.5            # coma decimal
    assert "10" not in v.index          # valor 0 = sin muestra -> NaN (fila descartada)
    assert v["28"] == 3400.1 and v["30"] == 2000  # uniprovinciales desde 'Total CCAA'
    assert v["00"] == 1900               # total nacional
    assert len(df) == 4                  # protegida y Ceuta+Melilla excluidas


def test_jsonstat():
    d = {"id": ["geo", "time"], "size": [1, 2], "value": {"0": 1.5, "1": 2.5},
         "dimension": {"geo": {"category": {"index": {"ES": 0}}}, "time": {"category": {"index": {"2024-Q1": 0, "2024-Q2": 1}}}}}
    df = jsonstat_to_frame(d)
    assert list(df["value"]) == [1.5, 2.5] and list(df["time"]) == ["2024-Q1", "2024-Q2"]
