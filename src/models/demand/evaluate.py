"""Evaluación rolling-origin de la demanda (nacional y provincial) y sendas condicionales 2026-2030."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.models.forecasting import config as C
from src.models.forecasting import univariate as U
from src.models.forecasting.backtest import (dm_table, empirical_log_quantiles, extend_quantiles, panel_summary,
                                             rolling_origin, select_models)
from src.models.forecasting.metrics import mape, summarise
from src.models.forecasting import scenarios as S
from .features import national_frame
from .models import ConditionalOLS, DirectML, _FeatureCache, ml_factories

BENCHMARKS = ["naive", "seasonal_naive", "media_movil_4", "drift"]
STAT_MODELS = {"ets_log": U.ets_log, "sarima_log": U.sarima_log, "ar_log": U.ar_log}
COND = "condicional_ex_post"
COND_CAPS = [1, 2, 4]


def _origins(f: pd.DataFrame) -> list:
    return [p for p in f.index if p >= C.FIRST_ORIGIN_Q][:-1]


def evaluate_national(national: pd.DataFrame, target: str = "hip_viv", with_ml: bool = True) -> dict:
    f = national_frame(national, target)
    y = f["y"]
    origins = _origins(f)
    models = {k: getattr(U, {"naive": "naive", "seasonal_naive": "seasonal_naive", "media_movil_4": "mean_last",
                             "drift": "drift"}[k]) for k in BENCHMARKS}
    models.update(STAT_MODELS)
    if with_ml:
        cache = _FeatureCache(f)
        models.update({k: DirectML(cache, fac) for k, fac in ml_factories().items()})
    fc = rolling_origin(y, models, origins, C.HORIZONS_Q, unit="nacional", min_train=24)
    # trayectoria larga (h=1..20) para intervalos: naive + condicional ex post
    # Variantes del condicional: elasticidades estimadas a cap_h trimestres y reutilizadas para h > cap_h.
    # cap_h se elige (regla pre-especificada) por menor MASE medio sobre h=1..20 en la ventana de selección.
    caps = {f"condicional_cap{c}": c for c in COND_CAPS}
    long = rolling_origin(y, {"naive": U.naive, **{k: ConditionalOLS(f, cap_h=c) for k, c in caps.items()}},
                          [p for p in f.index if p >= pd.Period("2010Q4", "Q-DEC")][:-1],
                          C.HORIZONS_Q_PATH, unit="nacional", min_train=24)
    lm = summarise(long)
    cap_score = lm[(lm.window == "seleccion") & lm.model.isin(caps)].groupby("model")["MASE"].mean()
    chosen = cap_score.idxmin()
    long_metrics = lm
    long = pd.concat([long[long.model == "naive"], long[long.model == chosen].assign(model=COND)], ignore_index=True)
    cond = long[(long.model == COND) & long.h.isin(C.HORIZONS_Q)]
    cond = cond[cond.origin >= C.FIRST_ORIGIN_Q]
    allfc = pd.concat([fc, cond], ignore_index=True)
    met = summarise(allfc)
    candidates = [m for m in met.model.unique() if m != COND]
    sel = select_models(met, candidates)
    best_bench = select_models(met, BENCHMARKS)
    pairs = []
    for h in C.HORIZONS_Q:
        pairs.append((h, sel[h], best_bench[h]))
        pairs.append((h, sel[h], "naive"))
        pairs.append((h, COND, best_bench[h]))
    pairs = list(dict.fromkeys(pairs))
    dm_hold = dm_table(allfc, pairs, "holdout")
    dm_sel = dm_table(allfc, pairs, "seleccion")
    # estabilidad: MAPE en ventanas móviles de 8 objetivos (h=1) y por subperiodo
    stab = []
    for (m, h), g in allfc[allfc.window != "oos_extra"].groupby(["model", "h"]):
        g = g.sort_values("target")
        ape = (np.abs(g.y - g.yhat) / g.y * 100).values
        if len(ape) >= 8:
            r = [ape[k:k + 8].mean() for k in range(len(ape) - 7)]
            stab.append({"model": m, "h": int(h), "MAPE8_min": min(r), "MAPE8_p50": float(np.median(r)), "MAPE8_max": max(r)})
    sub = []
    periods = {"2013-2019": ("2013Q1", "2019Q4"), "2020-2021": ("2020Q1", "2021Q4"), "2022-2025 (hold-out)": ("2022Q1", "2025Q4")}
    for nm, (a, b) in periods.items():
        g = allfc[(allfc.target >= pd.Period(a, "Q-DEC")) & (allfc.target <= pd.Period(b, "Q-DEC"))]
        for (m, h), gg in g.groupby(["model", "h"]):
            sub.append({"periodo": nm, "model": m, "h": int(h), "n": len(gg), "MAPE": mape(gg.y, gg.yhat)})
    return {"frame": f, "forecasts": allfc, "long": long, "long_metrics": long_metrics,
            "cond_cap_chosen": int(caps[chosen]), "cond_cap_scores": cap_score.to_dict(), "metrics": met, "selected": sel, "best_benchmark": best_bench,
            "dm_holdout": dm_hold, "dm_seleccion": dm_sel, "stability": pd.DataFrame(stab), "subperiods": pd.DataFrame(sub)}


def evaluate_provincial(panel: pd.DataFrame, national_long: pd.DataFrame, target: str = "hip_viv",
                        national_model: str = COND) -> dict:
    """Univariantes por provincia + top-down (previsión nacional × cuota media de los 4 últimos trimestres)."""
    recs = []
    nat = national_long[national_long.model.isin([national_model, "naive"])]
    for pc, g in panel.groupby("prov_code"):
        s = g.set_index("period")[target].dropna()
        s = s[s > 0]
        origins = [p for p in s.index if p >= C.FIRST_ORIGIN_Q][:-1]
        models = {"naive": U.naive, "seasonal_naive": U.seasonal_naive, "media_movil_4": U.mean_last, "ets_log": U.ets_log}
        recs.append(rolling_origin(s, models, origins, C.HORIZONS_Q, unit=pc, min_train=24))
        # top-down
        tot = panel.groupby("period")[target].sum(min_count=52)
        share = (s / tot.reindex(s.index))
        scale = None
        for nm, natm in (("top_down_condicional", national_model), ("top_down_naive", "naive")):
            nn = nat[nat.model == natm]
            rows = []
            for _, r in nn.iterrows():
                o = r.origin
                if o not in share.index or r.target not in s.index:
                    continue
                sh = share.loc[:o].tail(4).mean()
                tr = s.loc[:o].values
                rows.append({"unit": pc, "model": nm, "origin": o, "h": r.h, "target": r.target, "window": r.window,
                             "y": float(s.loc[r.target]), "yhat": float(r.yhat * sh),
                             "scale": U.seasonal_naive_scale(tr, 4)})
            recs.append(pd.DataFrame(rows))
    df = pd.concat(recs, ignore_index=True)
    df_tab = df[df.h.isin(C.HORIZONS_Q) & (df.origin >= C.FIRST_ORIGIN_Q)]
    agg, per = panel_summary(df_tab)
    sel = select_models(agg[agg.model != "top_down_condicional"], None)
    return {"forecasts": df, "metrics": agg, "per_unit": per, "selected": sel}


def conditional_paths(f: pd.DataFrame, long_fc: pd.DataFrame, cap_h: int, cfg: dict | None = None) -> dict:
    """Sendas nacionales 2026-2030 por escenario con el modelo condicional + intervalos empíricos (p10/p90)."""
    cfg = cfg or S.load_yaml()
    model = ConditionalOLS(f, cap_h=cap_h)
    pos = len(f) - 1
    last = f.index[pos]
    fut = pd.period_range(last + 1, C.PROJ_END_Q, freq="Q-DEC")
    H = len(fut)
    q = extend_quantiles(empirical_log_quantiles(long_fc, COND, max_target=C.HOLDOUT_END_Q), H)
    qn = extend_quantiles(empirical_log_quantiles(long_fc, "naive", max_target=C.HOLDOUT_END_Q), H)
    out, coefs_all = [], {}
    for scen in S.SCENARIOS:
        eur = S.euribor_path(scen, cfg)
        paro_a = S.annual_path("paro", scen, cfg)
        paro_q = S.quarterly_from_annual(paro_a)
        # serie de exógenas empalmada: observado (panel) + escenario
        eur_full = pd.concat([f["euribor"].dropna(), eur[~eur.index.isin(f["euribor"].dropna().index)]]).sort_index()
        paro_full = pd.concat([f["paro"].dropna(), paro_q[~paro_q.index.isin(f["paro"].dropna().index)]]).sort_index()
        paro_ma4 = paro_full.rolling(4).mean()
        # exógenas en el origen: si el origen es posterior al último dato del panel se usan las del empalme
        hs = list(range(1, H + 1))
        fc, coefs = model.forecast_scenario(pos, hs, {h: eur_full[fut[h - 1]] for h in hs},
                                            {h: paro_ma4[fut[h - 1]] for h in hs}, {h: fut[h - 1] for h in hs},
                                            float(eur_full[last]), float(paro_ma4[last]))
        coefs_all[scen] = coefs
        for h in hs:
            if h not in fc:
                continue
            out.append({"period": fut[h - 1], "h": h, "escenario": scen, "valor": fc[h],
                        "p10": fc[h] * np.exp(q.loc[h, "q_low"]), "p90": fc[h] * np.exp(q.loc[h, "q_high"]),
                        "modelo": f"condicional_ols_cap{cap_h} (ΔEuribor12M, Δparo; escenario)"})
    naive_v = float(f["y"].iat[pos])
    for h in range(1, H + 1):
        out.append({"period": fut[h - 1], "h": h, "escenario": "referencia_naive", "valor": naive_v,
                    "p10": naive_v * np.exp(qn.loc[h, "q_low"]), "p90": naive_v * np.exp(qn.loc[h, "q_high"]),
                    "modelo": "naive (persistencia)"})
    return {"paths": pd.DataFrame(out), "coefs": coefs_all, "quantiles": q, "quantiles_naive": qn, "origin": str(last)}


def provincial_paths(panel: pd.DataFrame, nat_paths: pd.DataFrame, prov_fc: pd.DataFrame, target: str) -> pd.DataFrame:
    """Top-down: senda nacional × cuota media de los 4 últimos trimestres; intervalos = cuantiles empíricos del
    error logarítmico del top-down condicional por provincia y horizonte (extendidos si faltan)."""
    tot = panel.groupby("period")[target].sum(min_count=52)
    rows = []
    for pc, g in panel.groupby("prov_code"):
        s = g.set_index("period")[target].dropna()
        sh = (s / tot.reindex(s.index)).tail(4).mean()
        e = prov_fc[(prov_fc.unit == pc) & (prov_fc.model == "top_down_condicional") & (prov_fc.target <= C.HOLDOUT_END_Q)]
        qq = empirical_log_quantiles(e.assign(model="x"), "x") if len(e) else None
        H = int(nat_paths.h.max())
        qq = extend_quantiles(qq, H) if qq is not None and len(qq) else None
        for _, r in nat_paths[nat_paths.escenario != "referencia_naive"].iterrows():
            v = r.valor * sh
            lo, hi = (r.p10 * sh, r.p90 * sh) if qq is None else (v * np.exp(qq.loc[r.h, "q_low"]), v * np.exp(qq.loc[r.h, "q_high"]))
            rows.append({"prov_code": pc, "period": r.period, "escenario": r.escenario, "valor": v, "p10": lo, "p90": hi,
                         "modelo": "top-down: senda nacional condicional x cuota (media 4T)"})
    return pd.DataFrame(rows)


def publication_table(met: pd.DataFrame, dm_hold: pd.DataFrame, dm_sel: pd.DataFrame, selected: dict) -> pd.DataFrame:
    """Tabla publicable: por modelo y horizonte, métricas en selección y hold-out, marca de elegido y DM vs naive."""
    out = met.copy()
    out["elegido_en_seleccion"] = [selected.get(int(h)) == m for m, h in zip(out.model, out.h)]
    dm = pd.concat([dm_sel, dm_hold])
    dm = dm[dm.benchmark == "naive"][["h", "window", "model", "DM_sq", "p_sq", "DM_abs", "p_abs"]].drop_duplicates(["h", "window", "model"])
    return out.merge(dm, on=["h", "window", "model"], how="left")
