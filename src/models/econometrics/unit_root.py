"""Batería de raíces unitarias: ADF (AIC y BIC), DF-GLS, Phillips-Perron, KPSS y Zivot-Andrews."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from arch.unitroot import ADF, DFGLS, KPSS, PhillipsPerron, ZivotAndrews


def _za_break(x: pd.Series, trend: str):
    from statsmodels.tsa.stattools import zivot_andrews
    try:
        out = zivot_andrews(np.asarray(x, float), trim=0.15, maxlag=6, regression=trend, autolag="AIC")
        return str(x.index[out[4]])
    except Exception:
        return None


def _safe(make, lags=False):
    try:
        t = make()
        out = (float(t.stat), float(t.pvalue))
        return out + (int(t.lags),) if lags else out
    except Exception:
        return (np.nan, np.nan, -1) if lags else (np.nan, np.nan)


def battery(name: str, s: pd.Series, max_lags: int = 8) -> list[dict]:
    rows = []
    s = s.dropna()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for d, lab in ((0, "nivel"), (1, "dif1"), (2, "dif2")):
            x = s.diff(d).dropna() if d else s
            if d == 2:
                x = s.diff().diff().dropna()
            for tr in (("c", "ct") if d == 0 else ("c",)):
                r = {"serie": name, "transf": lab, "det": tr, "T": int(len(x))}
                for meth in ("aic", "bic"):
                    st, pv, lg = _safe(lambda: ADF(x, trend=tr, method=meth, max_lags=max_lags), lags=True)
                    r[f"adf_{meth}_stat"], r[f"adf_{meth}_p"], r[f"adf_{meth}_lags"] = st, pv, lg
                r["dfgls_stat"], r["dfgls_p"] = _safe(lambda: DFGLS(x, trend=tr, method="aic", max_lags=max_lags))
                r["pp_stat"], r["pp_p"] = _safe(lambda: PhillipsPerron(x, trend=tr))
                r["kpss_stat"], r["kpss_p"] = _safe(lambda: KPSS(x, trend=tr))
                if d == 0:
                    for zt in ("c", "t", "ct"):
                        try:
                            z = ZivotAndrews(x, trend=zt, trim=0.15, max_lags=6, method="aic")
                            r[f"za_{zt}_stat"], r[f"za_{zt}_p"] = float(z.stat), float(z.pvalue)
                        except Exception:
                            r[f"za_{zt}_stat"], r[f"za_{zt}_p"] = np.nan, np.nan
                        r[f"za_{zt}_break"] = _za_break(x, zt)
                rows.append(r)
    return rows


def classify(rows: list[dict], alpha=0.05) -> str:
    """Dictamen orientativo combinando ADF(ct)/KPSS(ct) en nivel y ADF/KPSS en 1ª y 2ª diferencia."""
    get = lambda tr, d: next(r for r in rows if r["transf"] == tr and r["det"] == d)
    lv, d1, d2 = get("nivel", "ct"), get("dif1", "c"), get("dif2", "c")
    lvl_stat = lv["adf_aic_p"] < alpha and lv["kpss_p"] >= alpha
    d1_stat = d1["adf_aic_p"] < alpha or d1["pp_p"] < alpha
    if lvl_stat:
        return "I(0) (tendencia)"
    if d1_stat:
        note = "" if d1["kpss_p"] >= alpha else " (KPSS en 1ª dif. rechaza al 5 %: estacionalidad/rupturas)"
        return "I(1)" + note
    if d2["adf_aic_p"] < alpha:
        return "I(1)/I(2) ambiguo: ADF no rechaza raíz unitaria en 1ª diferencia"
    return "no concluyente"
