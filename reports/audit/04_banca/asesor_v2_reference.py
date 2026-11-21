"""Implementación de REFERENCIA (no productiva) de las fórmulas propuestas para el asesor v2.

Auditoría 04 (Banca). Sirve para fijar valores esperados de los tests unitarios
(test_asesor_v2_reference.py). No depende de Flask ni de la app.

Principios:
- Simulador de capacidad de pago + estimador de tipo de MERCADO (no oferta personalizada, no decisión).
- Toda tasa fiscal lleva vigencia y fuente; si no está verificada se marca y se avisa.
- Gastos de la hipoteca que paga el banco por Ley 5/2019 (art. 14.1.e) NO se imputan al cliente.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
import math


# ───────────────────────── 1. Amortización francesa ─────────────────────────
def cuota_francesa(capital: float, tin_anual_pct: float, n_meses: int) -> float:
    """Cuota constante (sistema francés), capitalización mensual, TIN nominal anual en %.
    C = P·r / (1 − (1+r)^−n), r = TIN/12. Con TIN = 0: C = P/n."""
    if capital <= 0 or n_meses <= 0:
        return 0.0
    r = tin_anual_pct / 100.0 / 12.0
    if abs(r) < 1e-12:
        return capital / n_meses
    return capital * r / (1.0 - (1.0 + r) ** (-n_meses))


def cuadro_amortizacion_saldo_final(capital: float, tin_anual_pct: float, n_meses: int, cuota: float) -> float:
    r = tin_anual_pct / 100.0 / 12.0
    saldo = capital
    for _ in range(n_meses):
        saldo = saldo * (1 + r) - cuota
    return saldo


def capital_maximo_por_cuota(cuota_max: float, tin_anual_pct: float, n_meses: int) -> float:
    """Inversa de la cuota francesa: capital que se amortiza con una cuota dada."""
    r = tin_anual_pct / 100.0 / 12.0
    if abs(r) < 1e-12:
        return cuota_max * n_meses
    return cuota_max * (1.0 - (1.0 + r) ** (-n_meses)) / r


# ───────────────────────── 2. Aranceles (RD 1426/1989 y RD 1427/1989) ─────────────────────────
_TRAMOS_NOTARIA = [  # Anexo I, Número 2 (documentos de cuantía): (límite superior del tramo, tipo por unidad)
    (30050.61, 0.0045), (60101.21, 0.0015), (150253.03, 0.0010), (601012.10, 0.0005), (6010121.04, 0.0003)]
_TRAMOS_REGISTRO = [  # Anexo I, Número 2
    (30050.61, 0.00175), (60101.21, 0.00125), (150253.03, 0.00075), (601012.10, 0.00030), (float('inf'), 0.00020)]


def _escala(base: float, fijo: float, umbral_fijo: float, tramos) -> float:
    importe, inf = fijo, umbral_fijo
    for sup, tipo in tramos:
        if base <= inf:
            break
        importe += (min(base, sup) - inf) * tipo
        inf = sup
    return importe


def arancel_notarial_base(cuantia: float, prestamo_hipotecario: bool = False) -> float:
    """Derechos de la escala del Número 2 del arancel notarial, con la rebaja general del 5 %.
    NO incluye folios de matriz (Nº 7), copias (Nº 4), suplidos ni IVA (21 %): la factura real es mayor.
    prestamo_hipotecario=True aplica la reducción del 25 % (Nº 2.2) — este coste lo paga el banco (LCCI)."""
    if cuantia > 6010121.04:
        raise ValueError('Por encima de 6.010.121,04 € el arancel es libre')
    imp = _escala(cuantia, 90.151816, 6010.12, _TRAMOS_NOTARIA)
    if prestamo_hipotecario:
        imp *= 0.75
    return imp * 0.95


def arancel_registral_base(valor: float, prestamo_hipotecario: bool = False) -> float:
    """Derechos del Número 2 del arancel registral (mín. 24,040484 €, máx. 2.181,673939 €) con rebaja del 5 %.
    No incluye notas simples, asientos de presentación, IVA, etc."""
    imp = _escala(valor, 24.040484, 6010.12, _TRAMOS_REGISTRO)
    if prestamo_hipotecario:
        imp *= 0.75
    imp = min(max(imp, 24.040484), 2181.673939)
    return imp * 0.95


# ───────────────────────── 3. Tabla fiscal con vigencias ─────────────────────────
@dataclass(frozen=True)
class TramoITP:
    hasta: float      # límite superior de valor (inf = sin límite)
    tipo_pct: float


@dataclass(frozen=True)
class ReglaFiscal:
    ccaa: str
    impuesto: str                 # 'ITP' | 'IVA' | 'IGIC' | 'AJD_compraventa'
    tramos: tuple                 # tuple[TramoITP]
    progresivo: bool              # True: por tramos (marginal); False: tipo único según valor total
    vigente_desde: date
    vigente_hasta: date | None
    fuente: str                   # norma + URL
    verificado: bool              # True solo si se ha contrastado con el boletín oficial
    notas: str = ''


def tipo_aplicable(regla: ReglaFiscal, valor: float) -> float:
    if regla.progresivo:
        raise ValueError('usar cuota_impuesto para escalas progresivas')
    for t in regla.tramos:
        if valor <= t.hasta:
            return t.tipo_pct
    return regla.tramos[-1].tipo_pct


def cuota_impuesto(regla: ReglaFiscal, valor: float) -> float:
    if not regla.progresivo:
        return valor * tipo_aplicable(regla, valor) / 100
    imp, inf = 0.0, 0.0
    for t in regla.tramos:
        if valor <= inf:
            break
        imp += (min(valor, t.hasta) - inf) * t.tipo_pct / 100
        inf = t.hasta
    return imp


def regla_vigente(reglas, ccaa: str, impuesto: str, fecha: date) -> ReglaFiscal:
    cand = [r for r in reglas if r.ccaa == ccaa and r.impuesto == impuesto and r.vigente_desde <= fecha
            and (r.vigente_hasta is None or fecha <= r.vigente_hasta)]
    if len(cand) != 1:
        raise LookupError(f'{len(cand)} reglas vigentes para {ccaa}/{impuesto} en {fecha}')
    return cand[0]


# ───────────────────────── 4. Gastos de compra (lado comprador) ─────────────────────────
GASTOS_PRESTAMO_A_CARGO_BANCO = ('notaria_escritura_prestamo', 'registro_hipoteca', 'gestoria', 'AJD_prestamo')
# Ley 5/2019 art. 14.1.e): tasación -> prestatario; gestoría, notaría del préstamo, registro de la hipoteca -> prestamista;
# AJD del préstamo: sujeto pasivo el prestamista (art. 29 TRLITPAJD tras RDL 17/2018).


def gastos_compra(precio: float, regla_impuesto: ReglaFiscal, tasacion: float,
                  regla_ajd: ReglaFiscal | None = None) -> dict:
    """Gastos que soporta el COMPRADOR. Notaría/registro de la compraventa con el arancel base (mínimo legal),
    que se presenta como cota inferior; la factura real incluye folios, copias e IVA."""
    impuesto = cuota_impuesto(regla_impuesto, precio)
    ajd = cuota_impuesto(regla_ajd, precio) if regla_ajd else 0.0   # solo vivienda nueva (escritura compraventa)
    notaria = arancel_notarial_base(precio)
    registro = arancel_registral_base(precio)
    total = impuesto + ajd + notaria + registro + tasacion
    return {'impuesto': impuesto, 'ajd_compraventa': ajd, 'notaria_arancel_base': notaria,
            'registro_arancel_base': registro, 'tasacion': tasacion, 'total': total,
            'excluidos_por_LCCI': list(GASTOS_PRESTAMO_A_CARGO_BANCO)}


# ───────────────────────── 5. Capacidad de pago con estrés ─────────────────────────
@dataclass
class Perfil:
    ingresos_netos_mes: float      # de la unidad familiar
    deudas_mes: float = 0.0
    gastos_fijos_mes: float = 0.0  # opcional (alquiler que desaparece no cuenta)
    edad_mayor_titular: int = 35
    ahorro: float = 0.0


def dsti(cuota: float, perfil: Perfil) -> float:
    if perfil.ingresos_netos_mes <= 0:
        return float('inf')
    return (cuota + perfil.deudas_mes) / perfil.ingresos_netos_mes


def plazo_maximo_meses(edad: int, plazo_solicitado_anios: int, edad_max_vencimiento: int = 75, plazo_max_anios: int = 30) -> int:
    anios = min(plazo_solicitado_anios, plazo_max_anios, edad_max_vencimiento - edad)
    return max(anios, 0) * 12


def simulacion_capacidad(precio: float, capital: float, tin_pct: float, n_meses: int, perfil: Perfil,
                         tipo: str, estres_pp: float = 3.0, umbral_dsti: float = 0.35) -> dict:
    """Devuelve métricas descriptivas. NO emite 'aprobada/denegada': clasifica la holgura frente a un umbral
    orientativo (parámetro, sin base legal en España)."""
    c = cuota_francesa(capital, tin_pct, n_meses)
    c_estres = cuota_francesa(capital, tin_pct + estres_pp, n_meses) if tipo in ('variable', 'mixto') else c
    ltv = capital / precio if precio > 0 else float('nan')
    r = {'cuota': c, 'cuota_estres': c_estres, 'dsti': dsti(c, perfil), 'dsti_estres': dsti(c_estres, perfil),
         'ltv': ltv, 'lti': capital / (12 * perfil.ingresos_netos_mes) if perfil.ingresos_netos_mes > 0 else float('inf'),
         'capital_max_dsti': capital_maximo_por_cuota(max(umbral_dsti * perfil.ingresos_netos_mes - perfil.deudas_mes, 0), tin_pct + (estres_pp if tipo in ('variable', 'mixto') else 0), n_meses)}
    r['holgura'] = ('dentro_umbral_orientativo' if r['dsti_estres'] <= umbral_dsti else 'por_encima_umbral_orientativo')
    return r


# ───────────────────────── 6. Estimador de tipo de MERCADO ─────────────────────────
def rango_tipo_mercado(serie_mensual: list[float], ventana: int = 12) -> dict:
    """Último dato publicado (p. ej. BCE MIR APRC España) y rango min–máx de los últimos `ventana` meses.
    Es una referencia de MEDIA DE MERCADO, no una oferta personalizada."""
    s = [x for x in serie_mensual if x is not None and not math.isnan(x)]
    w = s[-ventana:]
    return {'ultimo': s[-1], 'min': min(w), 'max': max(w)}
