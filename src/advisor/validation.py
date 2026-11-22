"""Validación del estimador de tipo de mercado y registro del modelo GBR descartado.

- Estimador: "último dato publicado" del TEDR (todas las fijaciones, y variable) como referencia del trimestre
  siguiente (h = 1, 2, 4 trimestres): MAE, RMSE y cobertura del rango [mín, máx] de los últimos 4 trimestres.
- GBR v1 (Web/app.py::_train_ml_pricing_model): se documenta como RESULTADO NEGATIVO a partir de la auditoría
  ``reports/audit/04_banca/out/gbr_audit.json`` (validación por origen móvil por trimestre).
Salida: ``artifacts/advisor/estimator_validation.json``. Uso: ``python -m src.advisor.validation``.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .market import load_market

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "advisor" / "estimator_validation.json"
GBR_AUDIT = ROOT / "reports" / "audit" / "04_banca" / "out" / "gbr_audit.json"


def backtest(series, horizons=(1, 2, 4), ventana=4, desde="2010Q1") -> dict:
    s = series.dropna()
    res = {}
    for h in horizons:
        err, cover = [], []
        for i in range(ventana - 1, len(s) - h):
            if s.index[i + h] < desde:
                continue
            ref, w, y = s.iloc[i], s.iloc[i - ventana + 1: i + 1], s.iloc[i + h]
            err.append(y - ref)
            cover.append(w.min() <= y <= w.max())
        e = np.array(err)
        res[f"h{h}"] = {"n": int(len(e)), "mae_pp": round(float(np.abs(e).mean()), 4),
                        "rmse_pp": round(float(np.sqrt((e ** 2).mean())), 4),
                        "sesgo_pp": round(float(e.mean()), 4), "cobertura_rango_4t": round(float(np.mean(cover)), 3)}
    return res


def main() -> dict:
    m = load_market()
    out = {"metodo": "referencia = último trimestre publicado; rango = [mín, máx] de los 4 últimos trimestres",
           "periodo_evaluado_desde": "2010Q1", "ultimo_dato": str(m["tedr_vivienda"].dropna().index[-1]),
           "tedr_todas_fijaciones": backtest(m["tedr_vivienda"]),
           "tedr_variable": backtest(m["tedr_variable"]),
           "lectura": ("El rango de 4 trimestres no es un intervalo de predicción: su cobertura del dato siguiente se "
                       "reporta para que el usuario no lo interprete como tal.")}
    if GBR_AUDIT.exists():
        g = json.loads(GBR_AUDIT.read_text(encoding="utf-8"))
        bt = g.get("backtest_origen_movil", {})
        out["gbr_v1_descartado"] = {
            "modelo": "GradientBoostingRegressor(6 variables macro) -> Spread_Hipotecas (APRC − Euríbor), Web/app.py v1",
            "observaciones_efectivas": g.get("n_trimestres_unicos"), "filas": g.get("n_filas_entrenamiento"),
            "rmse_cv_reportado_v1_con_fuga": g.get("app_TimeSeriesSplit_sobre_orden_provincial", {}).get("rmse_cv"),
            "rmse_origen_movil_gbr": bt.get("rmse_gbr_media_52_provincias"),
            "rmse_origen_movil_persistencia": bt.get("rmse_persistencia_t_1"),
            "periodo": bt.get("periodo"),
            "decision": "Retirado del flujo del cliente: peor que la persistencia del último dato publicado.",
            "fuente": str(GBR_AUDIT.relative_to(ROOT)),
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, ensure_ascii=False))
