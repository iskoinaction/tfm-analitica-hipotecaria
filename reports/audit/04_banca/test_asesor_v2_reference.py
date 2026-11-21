"""Tests unitarios clave propuestos para el asesor v2 (valores esperados calculados a mano / independientemente).
Ejecutar: python -m pytest -q reports/audit/04_banca/test_asesor_v2_reference.py
"""
import math, os, sys
from datetime import date
import pytest
sys.path.insert(0, os.path.dirname(__file__))
from asesor_v2_reference import (cuota_francesa, cuadro_amortizacion_saldo_final, capital_maximo_por_cuota,
                                 arancel_notarial_base, arancel_registral_base, ReglaFiscal, TramoITP,
                                 cuota_impuesto, regla_vigente, gastos_compra, Perfil, simulacion_capacidad,
                                 plazo_maximo_meses, rango_tipo_mercado, GASTOS_PRESTAMO_A_CARGO_BANCO)

INF = float('inf')


# 1. Cuota francesa
@pytest.mark.parametrize('P,tin,n,esperado', [
    (150000, 3.0, 300, 711.32),     # referencia clásica
    (237500, 2.78, 360, 973.35),    # perfil P01 del harness (coincide con la app)
    (200000, 3.5, 360, 898.09),
    (200000, 6.5, 360, 1264.14),    # +3 pp de estrés
    (100000, 0.0, 120, 833.33),     # TIN 0 => P/n
])
def test_cuota_francesa(P, tin, n, esperado):
    assert cuota_francesa(P, tin, n) == pytest.approx(esperado, abs=0.01)


def test_cuota_amortiza_saldo_cero():
    c = cuota_francesa(150000, 3.0, 300)
    assert abs(cuadro_amortizacion_saldo_final(150000, 3.0, 300, c)) < 1e-6


def test_capital_maximo_es_inversa():
    c = cuota_francesa(180000, 3.2, 300)
    assert capital_maximo_por_cuota(c, 3.2, 300) == pytest.approx(180000, rel=1e-9)


# 2. Aranceles base (RD 1426/1989 y RD 1427/1989, Anexo I Nº 2, con rebaja 5 %)
@pytest.mark.parametrize('base,notaria,registro', [
    (5000, 85.64, 22.84),      # cuota fija / mínimo
    (100000, 269.14, 126.92),
    (200000, 340.51, 176.90),  # 0,95·(90,15+108,18+45,08+90,15+24,87)=340,51
    (250000, 364.26, 191.15),
    (400000, 435.51, 233.90),
])
def test_aranceles_base(base, notaria, registro):
    assert arancel_notarial_base(base) == pytest.approx(notaria, abs=0.01)
    assert arancel_registral_base(base) == pytest.approx(registro, abs=0.01)


def test_arancel_registral_maximo():
    assert arancel_registral_base(50_000_000) == pytest.approx(2181.673939 * 0.95, abs=0.01)


# 3. Tabla fiscal con vigencias (valores de EJEMPLO, no verificados: el test comprueba la mecánica)
REGLAS = [
    ReglaFiscal('X', 'ITP', (TramoITP(INF, 10.0),), False, date(2020, 1, 1), date(2026, 5, 31), 'norma A', False),
    ReglaFiscal('X', 'ITP', (TramoITP(1_000_000, 9.0), TramoITP(INF, 11.0)), False, date(2026, 6, 1), None, 'norma B', False),
    ReglaFiscal('Y', 'ITP', (TramoITP(250_000, 8.0), TramoITP(INF, 10.0)), True, date(2020, 1, 1), None, 'norma C', False),
]


def test_vigencias():
    assert regla_vigente(REGLAS, 'X', 'ITP', date(2026, 5, 31)).fuente == 'norma A'
    assert regla_vigente(REGLAS, 'X', 'ITP', date(2026, 6, 1)).fuente == 'norma B'
    with pytest.raises(LookupError):
        regla_vigente(REGLAS, 'Z', 'ITP', date(2026, 6, 1))


def test_tipo_unico_por_valor_total_y_progresivo():
    b = regla_vigente(REGLAS, 'X', 'ITP', date(2026, 7, 1))
    assert cuota_impuesto(b, 300_000) == pytest.approx(27_000)
    assert cuota_impuesto(b, 1_200_000) == pytest.approx(132_000)          # 11 % sobre todo el valor
    c = regla_vigente(REGLAS, 'Y', 'ITP', date(2026, 7, 1))
    assert cuota_impuesto(c, 300_000) == pytest.approx(250_000 * 0.08 + 50_000 * 0.10)  # 25.000


# 4. Gastos: los del préstamo NO se imputan al comprador (Ley 5/2019 art. 14.1.e; RDL 17/2018)
def test_gastos_compra_no_imputa_gastos_prestamo():
    g = gastos_compra(200_000, REGLAS[0], tasacion=350.0)
    assert set(GASTOS_PRESTAMO_A_CARGO_BANCO) <= set(g['excluidos_por_LCCI'])
    assert g['total'] == pytest.approx(20_000 + 340.51 + 176.90 + 350.0, abs=0.02)
    assert 'AJD_prestamo' not in g


# 5. Capacidad de pago con estrés (sin "aprobada/denegada")
def test_estres_variable_vs_fijo():
    p = Perfil(ingresos_netos_mes=3000)
    v = simulacion_capacidad(250_000, 200_000, 3.5, 360, p, 'variable', estres_pp=3.0)
    f = simulacion_capacidad(250_000, 200_000, 3.5, 360, p, 'fijo', estres_pp=3.0)
    assert v['dsti'] == pytest.approx(0.2994, abs=1e-4)
    assert v['dsti_estres'] == pytest.approx(0.4214, abs=1e-4)
    assert f['dsti_estres'] == pytest.approx(0.2994, abs=1e-4)
    assert v['ltv'] == pytest.approx(0.80)
    assert v['holgura'] == 'por_encima_umbral_orientativo' and f['holgura'] == 'dentro_umbral_orientativo'
    assert 'aprobada' not in v and 'status' not in v


def test_coherencia_tipo_mostrado_y_cuota():
    """El tipo con el que se calcula la cuota/DSTI debe ser EXACTAMENTE el que se muestra (defecto v1)."""
    tin_mostrado = 3.5
    r = simulacion_capacidad(250_000, 200_000, tin_mostrado, 360, Perfil(3000), 'fijo')
    assert r['cuota'] == pytest.approx(cuota_francesa(200_000, tin_mostrado, 360))


def test_ingresos_cero():
    r = simulacion_capacidad(250_000, 200_000, 3.5, 360, Perfil(0), 'fijo')
    assert math.isinf(r['dsti'])


@pytest.mark.parametrize('edad,solicitado,meses', [(40, 30, 360), (60, 30, 180), (76, 30, 0), (50, 20, 240)])
def test_plazo_por_edad(edad, solicitado, meses):
    assert plazo_maximo_meses(edad, solicitado) == meses


# 6. Rango de tipo de mercado
def test_rango_mercado():
    r = rango_tipo_mercado([2.9, float('nan'), 2.7, 2.8, 3.04], ventana=3)
    assert r == {'ultimo': 3.04, 'min': 2.7, 'max': 3.04}
