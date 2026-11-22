"""Tests del asesor v2: amortización, aranceles, tabla fiscal (valores esperados calculados a mano)."""
import datetime as dt

import pytest

from src.advisor import fiscal
from src.advisor.amortization import capital_maximo_por_cuota, cuadro_anual, cuota_francesa, saldo_tras

D = dt.date(2026, 11, 22)


@pytest.mark.parametrize("P,tin,n,esperado", [
    (150000, 3.0, 300, 711.32), (237500, 2.78, 360, 973.35), (200000, 3.5, 360, 898.09),
    (200000, 6.5, 360, 1264.14), (100000, 0.0, 120, 833.33)])
def test_cuota_francesa(P, tin, n, esperado):
    assert cuota_francesa(P, tin, n) == pytest.approx(esperado, abs=0.01)


def test_saldo_y_cuadro():
    c = cuota_francesa(150000, 3.0, 300)
    assert saldo_tras(150000, 3.0, c, 300) == pytest.approx(0, abs=1e-6)
    cu = cuadro_anual(150000, [(300, 3.0)])
    assert len(cu) == 25 and cu[-1]["saldo_final"] == pytest.approx(0, abs=0.01)
    assert sum(f["amortizacion"] for f in cu) == pytest.approx(150000, abs=0.05)
    assert capital_maximo_por_cuota(c, 3.0, 300) == pytest.approx(150000)


def test_cuadro_mixto_recalcula_cuota():
    cu = cuadro_anual(200000, [(60, 2.0), (300, 4.0)])
    assert cu[4]["tin_pct"] == 2.0 and cu[5]["tin_pct"] == 4.0
    assert cu[5]["cuota_mensual"] > cu[4]["cuota_mensual"]
    assert cu[-1]["saldo_final"] == pytest.approx(0, abs=0.01)


@pytest.mark.parametrize("base,notaria,registro", [
    (5000, 85.64, 22.84), (100000, 269.14, 126.92), (200000, 340.51, 176.90), (250000, 364.26, 191.15), (400000, 435.51, 233.90)])
def test_aranceles(base, notaria, registro):
    assert fiscal.arancel("notaria", base) == pytest.approx(notaria, abs=0.01)
    assert fiscal.arancel("registro", base) == pytest.approx(registro, abs=0.01)


def test_arancel_registro_maximo_y_prestamo():
    assert fiscal.arancel("registro", 5e7) == pytest.approx(2181.673939 * 0.95, abs=0.01)
    assert fiscal.arancel("notaria", 200000, prestamo_hipotecario=True) == pytest.approx(340.51 * 0.75, abs=0.02)


def test_tramos_parse_errores():
    with pytest.raises(ValueError):
        fiscal.parse_tramos("0-100:5|200-:6")
    with pytest.raises(ValueError):
        fiscal.parse_tramos("0-100:5")


@pytest.mark.parametrize("ccaa,precio,esperado", [
    ("09", 700000, 71000.0),       # Cataluña: 600k x 10 % + 100k x 11 % (tarifa)
    ("04", 650000, 55000.0),       # Baleares: 400k x 8 % + 200k x 9 % + 50k x 10 %
    ("07", 300000, 25000.0),       # Castilla y León: 250k x 8 % + 50k x 10 %
    ("03", 400000, 36000.0),       # Asturias: 9 % sobre todo el valor (300k-500k)
    ("10", 1200000, 132000.0),     # C. Valenciana: 11 % sobre todo el valor (> 1 M€)
    ("10", 300000, 27000.0),
    ("13", 250000, 15000.0), ("12", 200000, 16000.0), ("06", 200000, 18000.0), ("14", 200000, 15500.0),
    ("18", 150000, 4500.0),        # Ceuta: 6 % con bonificación 50 %
])
def test_itp(ccaa, precio, esperado):
    r = fiscal.select_rule(ccaa, "ITP", "vivienda_usada", D)
    assert fiscal.tax_amount(r, precio) == pytest.approx(esperado)


def test_ajd_madrid_tramos_y_habitual():
    r = fiscal.select_rule("13", "AJD", "vivienda_nueva", D)
    assert fiscal.tax_amount(r, 110000) == pytest.approx(440.0)
    assert fiscal.tax_amount(r, 250000) == pytest.approx(1875.0)
    assert fiscal.select_rule("10", "AJD", "vivienda_nueva", D, {"vivienda_habitual"}).tramos[0].tipo_pct == 0.1
    assert fiscal.select_rule("10", "AJD", "vivienda_nueva", D).tramos[0].tipo_pct == 1.4


def test_cobertura_y_verificacion_tabla():
    rules = fiscal.load_rules()
    for c in [f"{i:02d}" for i in range(1, 20)]:
        assert fiscal.select_rule(c, "ITP", "vivienda_usada", D), c
        assert fiscal.select_rule(c, "AJD", "vivienda_nueva", D), c
    for r in rules:
        if r.verificado:
            assert r.vigente_desde and r.fecha_verificacion and r.boe_id, r.id
    no_verif = {r.id for r in rules if not r.verificado}
    assert {"ITP-15", "ITP-16"} <= no_verif   # forales: no consultables en la API del BOE


def test_vigencia_anterior_no_modelada():
    # Antes de la vigencia verificada del 9 % valenciano no hay regla (no se inventan tipos históricos)
    assert fiscal.select_rule("10", "ITP", "vivienda_usada", dt.date(2020, 1, 1)) is None
