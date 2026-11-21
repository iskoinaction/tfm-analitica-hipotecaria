"""ARDL en forma de corrección de error y contraste de límites de Pesaran, Shin & Smith (2001), caso 3."""
from __future__ import annotations

import warnings

import pandas as pd
from statsmodels.tsa.ardl import UECM


def bounds_test(Y: pd.DataFrame, dep: str, regs: list[str], fixed: pd.DataFrame | None = None,
                max_p: int = 4, max_q: int = 3) -> dict:
    """Orden (p, q común) por BIC sobre muestra común; todos los regresores con ≥1 retardo."""
    best = None
    trim = max(max_p, max_q)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for p in range(1, max_p + 1):
            for q in range(1, max_q + 1):
                m = UECM(Y[dep].iloc[trim:], p, Y[regs].iloc[trim:], q, trend="c",
                         fixed=None if fixed is None else fixed.iloc[trim:]).fit()
                if best is None or m.bic < best[0]:
                    best = (m.bic, p, q)
        _, p, q = best
        m = UECM(Y[dep], p, Y[regs], q, trend="c", fixed=fixed).fit()
        bt = m.bounds_test(case=3)
    ci = m.ci_params
    return {"dep": dep, "regresores": regs, "orden_p_q": [p, q], "T": int(m.nobs),
            "F": float(bt.statistic), "p_I0": float(bt.pvalue["lower"]), "p_I1": float(bt.pvalue["upper"]),
            "cv95_I0": float(bt.critical_values.loc[95.0, "lower"]), "cv95_I1": float(bt.critical_values.loc[95.0, "upper"]),
            "coef_LP": {k: float(-ci[k]) for k in ci.index if k != dep},
            "phi_ECT": float(m.params[f"{dep}.L1"]), "phi_p": float(m.pvalues[f"{dep}.L1"]),
            "supuestos": "regresores débilmente exógenos y ninguno I(2) (PSS 2001)"}
