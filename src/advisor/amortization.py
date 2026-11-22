"""Sistema de amortización francés (cuota constante, capitalización mensual)."""
from __future__ import annotations


def cuota_francesa(capital: float, tin_anual_pct: float, n_meses: int) -> float:
    """C = P·r / (1 − (1+r)^−n), r = TIN/12 (TIN nominal anual en %). Con TIN = 0, C = P/n."""
    if capital <= 0 or n_meses <= 0:
        return 0.0
    r = tin_anual_pct / 100.0 / 12.0
    if abs(r) < 1e-12:
        return capital / n_meses
    return capital * r / (1.0 - (1.0 + r) ** (-n_meses))


def saldo_tras(capital: float, tin_anual_pct: float, cuota: float, meses: int) -> float:
    """Saldo pendiente tras ``meses`` pagos de ``cuota`` (forma cerrada)."""
    r = tin_anual_pct / 100.0 / 12.0
    if abs(r) < 1e-12:
        return max(capital - cuota * meses, 0.0)
    f = (1 + r) ** meses
    return max(capital * f - cuota * (f - 1) / r, 0.0)


def capital_maximo_por_cuota(cuota_max: float, tin_anual_pct: float, n_meses: int) -> float:
    if cuota_max <= 0 or n_meses <= 0:
        return 0.0
    r = tin_anual_pct / 100.0 / 12.0
    if abs(r) < 1e-12:
        return cuota_max * n_meses
    return cuota_max * (1.0 - (1.0 + r) ** (-n_meses)) / r


def cuadro_anual(capital: float, tramos: list[tuple[int, float]]) -> list[dict]:
    """Cuadro resumen anual. ``tramos`` = [(meses, tin_pct), ...] consecutivos (p. ej. mixta: fijo y luego variable).
    La cuota se recalcula al inicio de cada tramo sobre el saldo y el plazo restantes."""
    n_total = sum(m for m, _ in tramos)
    filas, saldo, mes, cuota, anio = [], capital, 0, 0.0, None
    acc = {"cuota": 0.0, "intereses": 0.0, "amortizacion": 0.0}
    for meses, tin in tramos:
        cuota = cuota_francesa(saldo, tin, n_total - mes)
        r = tin / 100.0 / 12.0
        for _ in range(meses):
            interes = saldo * r
            amort = min(cuota - interes, saldo)
            saldo -= amort
            mes += 1
            acc["cuota"] += interes + amort
            acc["intereses"] += interes
            acc["amortizacion"] += amort
            if mes % 12 == 0 or mes == n_total:
                filas.append({"anio": (mes - 1) // 12 + 1, "cuota_mensual": round(cuota, 2), "tin_pct": tin,
                              "pagado": round(acc["cuota"], 2), "intereses": round(acc["intereses"], 2),
                              "amortizacion": round(acc["amortizacion"], 2), "saldo_final": round(max(saldo, 0.0), 2)})
                acc = {"cuota": 0.0, "intereses": 0.0, "amortizacion": 0.0}
    return filas
