"""Tests del motor src.advisor.simulate / metadata."""
import json
from pathlib import Path

import pytest

import src.advisor.engine as eng
from src.advisor import AdvisorInputError, metadata, simulate
from src.advisor.amortization import cuota_francesa
from src.advisor.market import load_market, market_reference
from src.common.geography import PROVINCES

ROOT = Path(__file__).resolve().parents[1]
BASE = dict(provincia="28", precio_vivienda=250000, aportacion=60000, ingresos_netos_mensuales=3000, edad=32,
            plazo_anios=30, modalidad="fijo", tin_pct=3.0, fecha_operacion="2026-11-22")


@pytest.fixture(autouse=True)
def fixture_market(tmp_path, monkeypatch):
    """Fixture de mercado (no depende del panel real)."""
    panel = tmp_path / "nac.csv"
    panel.write_text("period,euribor_12m,tae_vivienda,tedr_vivienda\n2025Q4,2.2,2.7,2.6\n2026Q1,2.3,2.8,2.7\n"
                     "2026Q2,2.8,2.9,2.8\n2026Q3,3.0,3.0,2.9\n", encoding="utf-8")
    var = tmp_path / "var.csv"
    var.write_text("mes,tedr_variable\n2025-10,2.9\n2025-11,2.9\n2025-12,2.9\n2026-01,2.9\n2026-02,2.9\n2026-03,2.9\n"
                   "2026-04,3.0\n2026-05,3.0\n2026-06,3.0\n2026-07,3.2\n2026-08,3.2\n2026-09,3.2\n", encoding="utf-8")
    m = load_market(panel, var)
    eng._market.cache_clear()
    monkeypatch.setattr(eng, "_market", lambda: m)
    yield


def test_validacion_errores_claros():
    with pytest.raises(AdvisorInputError) as e:
        simulate({"provincia": "Narnia", "aportacion": -1, "edad": 15})
    campos = {x["campo"] for x in e.value.errors}
    assert {"provincia", "aportacion", "edad", "ingresos_netos_mensuales", "precio_vivienda"} <= campos
    with pytest.raises(AdvisorInputError):
        simulate(dict(BASE, campo_raro=1))
    with pytest.raises(AdvisorInputError):
        simulate(dict(BASE, modalidad="aprobada"))


def test_52_provincias_sin_fuzzy_y_json():
    for code, p in PROVINCES.items():
        for prov in (code, p.name, p.legacy_name):
            r = simulate(dict(BASE, provincia=prov))
            assert r["provincia"]["code"] == code
    json.dumps(simulate(BASE))


def test_tipo_mostrado_es_el_de_la_cuota():
    r = simulate(BASE)
    assert r["cuota"]["mensual_inicial"] == pytest.approx(
        cuota_francesa(r["financiacion"]["capital_prestamo"], r["tipo_interes"]["tin_inicial_pct"], 360), abs=0.01)


def test_sin_decision_de_concesion():
    txt = json.dumps(simulate(BASE), ensure_ascii=False).lower()
    for w in ("aprobada", "denegada", "approved", "denied", "caixabank"):
        assert w not in txt


def test_gastos_prestamo_no_imputados_y_tasacion_si():
    r = simulate(BASE)
    conceptos = " ".join(l["concepto"].lower() for l in r["gastos"]["lineas"])
    assert "tasación" in conceptos and "préstamo" not in conceptos
    assert any("AJD de la escritura de préstamo" in x for x in r["gastos"]["a_cargo_del_banco"])
    # Madrid usada 250k: ITP 15.000 + notaría 364,26·1,21 + registro 191,15·1,21 + tasación 400
    assert r["gastos"]["total_cliente"] == pytest.approx(15000 + 440.75 + 231.29 + 400, abs=0.02)
    assert r["financiacion"]["capital_prestamo"] == pytest.approx(250000 + r["gastos"]["total_cliente"] - 60000, abs=0.01)


def test_estres_variable_y_fijo():
    v = simulate(dict(BASE, modalidad="variable", tin_pct=3.5, aportacion=250000 + 16072.04 - 200000))
    assert v["esfuerzo"]["cuota_estres"] == pytest.approx(cuota_francesa(v["financiacion"]["capital_prestamo"], 6.5, 360), abs=0.01)
    f = simulate(dict(BASE, tin_pct=3.5))
    assert f["esfuerzo"]["cuota_estres"] == f["cuota"]["mensual_inicial"] and not f["esfuerzo"]["estres_aplicado"]


def test_semaforo():
    assert simulate(dict(BASE, ingresos_netos_mensuales=5000))["semaforo"]["color"] == "verde"
    assert simulate(dict(BASE, ingresos_netos_mensuales=2300))["semaforo"]["color"] == "ambar"   # 868,8/2300 = 37,8 %
    assert simulate(dict(BASE, ingresos_netos_mensuales=1500))["semaforo"]["color"] == "rojo"
    assert simulate(dict(BASE, ingresos_netos_mensuales=0))["semaforo"]["color"] == "rojo"


def test_edad_plazo():
    r = simulate(dict(BASE, edad=60, plazo_anios=30))
    assert r["financiacion"]["plazo_anios"] == 15 and any("75 años" in a for a in r["avisos"])


def test_ltv_sobre_min_precio_tasacion():
    r = simulate(dict(BASE, valor_tasacion=200000))
    assert r["financiacion"]["ltv"] == pytest.approx(r["financiacion"]["capital_prestamo"] / 200000, abs=1e-4)


def test_mercado_y_rango_fechados():
    r = simulate({k: v for k, v in BASE.items() if k != "tin_pct"})
    mk = r["tipo_interes"]["referencia_mercado"]
    assert r["tipo_interes"]["origen"] == "mercado" and r["tipo_interes"]["tin_inicial_pct"] == 2.9
    assert mk["tedr_medio_todas_fijaciones"]["periodo_ultimo"] == "2026Q3" and mk["tin_rango"] == [2.6, 2.9]
    v = simulate({**{k: x for k, x in BASE.items() if k != "tin_pct"}, "modalidad": "variable"})
    # diferencial = media 4T de (TEDR variable − Euríbor): (0.7+0.6+0.2+0.2)/4 = 0.425 -> TIN 3.0 + 0.425
    assert v["tipo_interes"]["tin_inicial_pct"] == pytest.approx(3.425, abs=1e-4)


def test_escenario_futuro_etiquetado():
    r = simulate({**{k: x for k, x in BASE.items() if k != "tin_pct"}, "modalidad": "variable", "escenario_anio": 2028, "escenario": "adverso"})
    assert "ESCENARIO" in r["tipo_interes"]["escenario"]["etiqueta"]


def test_no_verificado_avisa():
    r = simulate(dict(BASE, provincia="31"))
    assert any("NO VERIFICADO" in a for a in r["avisos"])
    c = simulate(dict(BASE, provincia="35", tipo_vivienda="nueva"))
    assert any("NO MODELADO" in a for a in c["avisos"])


def test_metadata():
    m = metadata()
    assert len(m["provincias"]) == 52 and len(m["ccaa"]) == 19
    assert m["parametros"]["naturaleza"].startswith("ILUSTRATIVO")
    json.dumps(m)


def test_vectores_exportados_reproducibles():
    p = ROOT / "artifacts" / "advisor" / "test_vectors.json"
    if not p.exists():
        pytest.skip("vectores no generados")
    from src.advisor.export import _key
    for c in json.loads(p.read_text(encoding="utf-8"))["casos"]:
        assert _key(simulate(c["entrada"])) == c["salida"], c["id"]
