"""Pipeline de forecasting v2: backtests rolling-origin + hold-out, sendas 2026-2030 y artefactos.

Uso:
    python -m src.pipelines.generate_forecasts                # datos v2 (data/processed) si existen
    python -m src.pipelines.generate_forecasts --prefer provisional --no-ml

Salidas:
    data/forecasts/proyecciones_2026_2030_v2.csv        long: provincia, prov_code, period, variable, escenario,
                                                         valor, p10, p90, modelo  (app y web)
    artifacts/demand/*.csv|json                          backtest de demanda (tablas, DM, estabilidad, metadatos)
    artifacts/forecasting/*.csv|json                     backtest de las variables macro, selección y metadatos
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import time

import numpy as np
import pandas as pd

from src.common.geography import PROVINCES
from src.models.forecasting import config as C
from src.models.forecasting import macro as M
from src.models.forecasting import scenarios as S
from src.models.forecasting import univariate as U
from src.models.forecasting.data import load_inputs
from src.models.demand import evaluate as D
from src.models.forecasting.backtest import interval_coverage


def _versions() -> dict:
    import lightgbm, scipy, sklearn, statsmodels, xgboost
    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
            "scikit-learn": sklearn.__version__, "statsmodels": statsmodels.__version__, "scipy": scipy.__version__,
            "lightgbm": lightgbm.__version__, "xgboost": xgboost.__version__}


def _jsonable(o):
    if isinstance(o, (pd.Period,)):
        return str(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    return o


def _csv(df: pd.DataFrame, path):
    d = df.copy()
    for c in d.columns:
        if d[c].dtype == object or str(d[c].dtype).startswith("period"):
            d[c] = d[c].astype(str)
    d.to_csv(path, index=False)


def _dump(obj, path):
    path.write_text(json.dumps(_jsonable(obj), indent=2, ensure_ascii=False))


QUARTERLY_VARS = {
    "precio_m2_mivau": ("precio", {"naive": U.naive, "seasonal_naive": U.seasonal_naive, "hw_amortiguado_tfm": U.hw_damped,
                                   "ets_log": U.ets_log}, True),
    "compraventas_viviendas": ("transmisiones", {"naive": U.naive, "seasonal_naive": U.seasonal_naive,
                                                 "media_movil_4": U.mean_last, "ets_log": U.ets_log}, False),
    "tasa_paro": ("paro", {"naive": U.naive, "seasonal_naive": U.seasonal_naive, "holt_amortiguado": U.ets_level_damped,
                           "arima_312": U.arima_level}, False),
}
ANNUAL_VARS = {"pib_pc": ("pib_pc", True), "poblacion": ("poblacion", False), "poblacion_extranjera": ("pob_ext", False)}


def run(prefer: str = "auto", with_ml: bool = True) -> dict:
    t0 = time.time()
    for d in (C.FORECASTS_DIR, C.ART_FORECAST, C.ART_DEMAND):
        d.mkdir(parents=True, exist_ok=True)
    I = load_inputs(prefer)
    cfg = S.load_yaml()
    meta = {"generado": dt.datetime.now().isoformat(timespec="seconds"), "datos": I.metadata(), "versiones": _versions(),
            "escenarios_yaml": {"path": str(C.SCENARIOS_YAML.relative_to(C.ROOT)), "sha256": S.yaml_hash(),
                                "version": cfg.get("version")},
            "protocolo": {"primer_origen": str(C.FIRST_ORIGIN_Q), "fin_seleccion": str(C.SEL_END_Q),
                          "holdout": [str(C.HOLDOUT_START_Q), str(C.HOLDOUT_END_Q)], "horizontes_tabla": C.HORIZONS_Q,
                          "regla_seleccion": C.SELECTION_RULE, "semilla": C.SEED, "n_jobs": C.N_JOBS,
                          "intervalos": f"cuantiles empíricos {C.PI_LOW:.0%}-{C.PI_HIGH:.0%} del error de backtest "
                                        "por horizonte (log para niveles, aditivo para el paro); h sin errores "
                                        "suficientes: escalado sqrt(h/h0)"}}
    out_rows = []
    names = {c: p.name for c, p in PROVINCES.items()}
    names["00"] = "España"

    # ------------------------------------------------------------------ DEMANDA
    demand_meta = {}
    for target, label in (("hip_viv", "hipotecas_viviendas"), ("hip_tot", "hipotecas_total_fincas")):
        r = D.evaluate_national(I.national, target, with_ml=with_ml)
        _csv(r["metrics"], C.ART_DEMAND / f"{label}_nacional_metricas.csv")
        _csv(r["forecasts"], C.ART_DEMAND / f"{label}_nacional_backtest.csv")
        _csv(pd.concat([r["dm_seleccion"], r["dm_holdout"]]), C.ART_DEMAND / f"{label}_nacional_dm.csv")
        _csv(r["stability"], C.ART_DEMAND / f"{label}_nacional_estabilidad.csv")
        _csv(r["subperiods"], C.ART_DEMAND / f"{label}_nacional_subperiodos.csv")
        _csv(r["long_metrics"], C.ART_DEMAND / f"{label}_nacional_metricas_h1_20.csv")
        _csv(D.publication_table(r["metrics"], r["dm_holdout"], r["dm_seleccion"], r["selected"]),
             C.ART_DEMAND / f"{label}_tabla_rolling_origin_holdout.csv")
        cov = pd.concat([interval_coverage(r["forecasts"], m_) for m_ in {r["selected"][h] for h in r["selected"]} | {"naive"}])
        _csv(cov, C.ART_DEMAND / f"{label}_cobertura_intervalos_holdout.csv")
        paths = D.conditional_paths(r["frame"], r["long"], r["cond_cap_chosen"], cfg)
        demand_meta[label] = {"seleccionado_por_h": r["selected"], "mejor_benchmark_por_h": r["best_benchmark"],
                              "condicional_cap_h": r["cond_cap_chosen"], "condicional_cap_scores": r["cond_cap_scores"],
                              "origen_sendas": paths["origin"], "coeficientes_condicional": paths["coefs"]["base"],
                              "ultimo_observado": str(r["frame"].index[-1])}
        p = paths["paths"]
        for _, x in p.iterrows():
            out_rows.append({"prov_code": "00", "period": str(x.period), "variable": label, "escenario": x.escenario,
                             "valor": x.valor, "p10": x.p10, "p90": x.p90, "modelo": x.modelo})
        if target == "hip_viv":
            rp = D.evaluate_provincial(I.panel, r["long"], "hip_viv")
            _csv(rp["metrics"], C.ART_DEMAND / f"{label}_provincial_metricas.csv")
            _csv(rp["per_unit"], C.ART_DEMAND / f"{label}_provincial_metricas_por_provincia.csv")
            demand_meta[label]["provincial_seleccionado_por_h"] = rp["selected"]
            pp = D.provincial_paths(I.panel, p, rp["forecasts"], "hip_viv")
            for _, x in pp.iterrows():
                out_rows.append({"prov_code": x.prov_code, "period": str(x.period), "variable": label,
                                 "escenario": x.escenario, "valor": x.valor, "p10": x.p10, "p90": x.p90, "modelo": x.modelo})
        print(f"[demanda] {label} ok ({time.time() - t0:.0f}s)", flush=True)
    meta_d = dict(meta, demanda=demand_meta,
                  nota=("La tabla publicable es rolling-origin por horizonte; el modelo condicional usa exógenas del "
                        "periodo objetivo (ex post) y NO compite en la selección; sus sendas son condicionales al escenario."))
    _dump(meta_d, C.ART_DEMAND / "metadata.json")

    # ------------------------------------------------------------------ MACRO
    macro_meta = {}
    covs = []
    for label, (var, models, pooled) in QUARTERLY_VARS.items():
        r = M.evaluate_quarterly(I.panel, var, models, national=I.national, pooled=pooled)
        _csv(r["metrics"], C.ART_FORECAST / f"{label}_metricas.csv")
        _csv(r["per_unit"], C.ART_FORECAST / f"{label}_metricas_por_provincia.csv")
        allm = dict(models)
        proj = M.project_quarterly(I.panel, var, r["chosen"], allm, r["forecasts"], I.national, cfg)
        proj["variable"] = label
        out_rows += proj.to_dict("records")
        macro_meta[label] = {"seleccionado": r["chosen"], "score_seleccion_MASE": r["score"]}
        covs.append(interval_coverage(r["forecasts"], r["chosen"], C.HORIZONS_Q).assign(variable=label))
        print(f"[macro] {label}: {r['chosen']} ({time.time() - t0:.0f}s)", flush=True)
    for label, (var, anchor) in ANNUAL_VARS.items():
        ann = I.annual
        if var == "pib_pc":  # solo años con las 52 provincias (2025 es 'Avance' en 9): sin mezclar vintages
            full = ann.dropna(subset=["pib_pc"]).groupby("year").size()
            ann = ann[ann.year.isin(full[full == 52].index)]
        r = M.evaluate_annual(ann, var, with_anchor=anchor)
        _csv(r["metrics"], C.ART_FORECAST / f"{label}_metricas.csv")
        _csv(r["per_unit"], C.ART_FORECAST / f"{label}_metricas_por_provincia.csv")
        proj = M.project_annual(ann, var, r["chosen"], r["forecasts"], cfg)
        proj["variable"] = label
        out_rows += proj.to_dict("records")
        macro_meta[label] = {"seleccionado": r["chosen"], "score_seleccion_MASE": r["score"]}
        covs.append(interval_coverage(r["forecasts"], r["chosen"], C.HORIZONS_Y).assign(variable=label))
        print(f"[macro] {label}: {r['chosen']} ({time.time() - t0:.0f}s)", flush=True)
    _csv(pd.concat(covs), C.ART_FORECAST / "cobertura_intervalos_holdout.csv")
    out_rows += M.scenario_rows(cfg).to_dict("records")
    _dump(dict(meta, macro=macro_meta), C.ART_FORECAST / "metadata.json")

    out = pd.DataFrame(out_rows)
    out["provincia"] = out.prov_code.map(names)
    out = out[["prov_code", "period", "variable", "escenario", "valor", "p10", "p90", "modelo"]]
    out = out.sort_values(["variable", "prov_code", "escenario", "period"]).reset_index(drop=True)
    path = C.FORECASTS_DIR / "proyecciones_2026_2030_v2.csv"
    out.to_csv(path, index=False, float_format="%.6g")
    summary = {"filas": len(out), "por_variable": out.groupby("variable").size().to_dict(),
               "csv": str(path.relative_to(C.ROOT)), "segundos": round(time.time() - t0, 1)}
    _dump(summary, C.FORECASTS_DIR / "proyecciones_2026_2030_v2.summary.json")
    _dump(dict(meta, columnas=list(out.columns), filas=len(out), demanda=demand_meta, macro=macro_meta,
               nota="Sendas CONDICIONALES a escenarios (base/adverso/favorable); no son predicciones con un % de error. "
                    "Variables sin modelo de escenario validado solo tienen 'base' (extrapolación del modelo elegido por regla pre-especificada). "
                    "p10/p90: cuantiles empíricos del error de backtest por horizonte."),
          C.FORECASTS_DIR / "proyecciones_2026_2030_v2.meta.json")
    print(json.dumps(_jsonable(summary), indent=2, ensure_ascii=False))
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefer", default="auto", choices=["auto", "v2", "provisional"])
    ap.add_argument("--no-ml", action="store_true")
    a = ap.parse_args()
    run(a.prefer, with_ml=not a.no_ml)


if __name__ == "__main__":
    main()
