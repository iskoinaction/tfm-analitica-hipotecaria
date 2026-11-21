"""Paso 5: normalización alternativa (sobre el precio), estabilidad y ARDL bounds test (PSS 2001)."""
import json
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.ardl import UECM, ardl_select_order
from statsmodels.tsa.vector_ar.vecm import VECM

from common import FIG, OUT, build_clean, build_original, seasonal_dummies
from vecm_tools import VECMfit

warnings.filterwarnings("ignore")
res = {}
Yc = build_clean(weighted=True, end="2024-10-01")
Yo = build_original()
dum = seasonal_dummies(Yc.index)
order = ["Log_Precio_m2", "Log_Hipotecas", "Log_PIB_pc", "Log_Materiales", "Euribor"]
for name, Y, ex in (("C_auditada_dumest", Yc, dum), ("A_original_nb42", Yo, None)):
    sm = VECM(Y[order], exog=ex, k_ar_diff=1, coint_rank=1, deterministic="co").fit()
    res[f"{name}|beta_norm_precio (log P = ...)"] = {v: [round(-sm.beta[i, 0], 4), round(sm.stderr_beta[i, 0], 4), round(sm.pvalues_beta[i, 0], 4)] for i, v in enumerate(order)}
    res[f"{name}|alpha (norm precio)"] = {v: [round(sm.alpha[i, 0], 4), round(sm.pvalues_alpha[i, 0], 4)] for i, v in enumerate(order)}

# Recursivo con normalización en precio (C)
rows = []
V = list(Yc.columns)
ip = V.index("Log_Precio_m2")
for end in range(44, len(Yc) + 1):
    f = VECMfit(Yc.values[:end], 1, 3, dum.values[:end], 1, norm_idx=ip)
    b = -f.beta[:5, 0]
    rows.append({"fin": Yc.index[end - 1], **{v: b[i] for i, v in enumerate(V)}, "alpha_pre": f.alpha[ip, 0]})
rec = pd.DataFrame(rows)
rec.to_csv(OUT / "05_beta_recursivo_norm_precio.csv", index=False, float_format="%.4f")
res["C|recursivo_norm_precio_min_max"] = {c: [round(rec[c].min(), 3), round(rec[c].max(), 3)] for c in ["Log_Hipotecas", "Log_PIB_pc", "Log_Materiales", "Euribor", "alpha_pre"]}
res["C|recursivo_norm_precio_desde2016_min_max"] = {c: [round(rec[rec.fin >= "2016-01-01"][c].min(), 3), round(rec[rec.fin >= "2016-01-01"][c].max(), 3)] for c in ["Log_Hipotecas", "Log_PIB_pc", "Log_Materiales", "Euribor"]}
fig, ax = plt.subplots(1, 4, figsize=(15, 3))
for i, c in enumerate(["Log_Hipotecas", "Log_PIB_pc", "Log_Materiales", "Euribor"]):
    ax[i].plot(rec.fin, rec[c], color="#1f3b70")
    ax[i].set_title(f"β {c} (log P = ...), recursivo", fontsize=8)
    ax[i].grid(alpha=.2)
fig.tight_layout(); fig.savefig(FIG / "beta_recursivo_norm_precio.png", dpi=110); plt.close(fig)

# ---------- ARDL / bounds test (Pesaran, Shin & Smith 2001) ----------
def bounds(dep, regs, Y, ex, label):
    """ARDL con TODOS los regresores (al menos 1 retardo), orden elegido por BIC en rejilla."""
    best = None
    for py in (1, 2, 3, 4):
        for qx in (1, 2, 3):
            try:
                m = UECM(Y[dep].iloc[4:], py, Y[regs].iloc[4:], qx, trend="c",
                         fixed=None if ex is None else ex.iloc[4:]).fit()
            except Exception:
                continue
            if best is None or m.bic < best[0]:
                best = (m.bic, py, qx)
    _, py, qx = best
    m = UECM(Y[dep], py, Y[regs], qx, trend="c", fixed=ex).fit()
    bt = m.bounds_test(case=3)
    ci = m.ci_params
    out = {"orden_ARDL(BIC) p_y,q_x": [py, qx],
           "F_stat": round(bt.statistic, 3), "p_I0_I1": [round(float(bt.pvalue["lower"]), 4), round(float(bt.pvalue["upper"]), 4)],
           "crit_95_I0_I1": [round(float(bt.critical_values.loc[95.0, "lower"]), 3), round(float(bt.critical_values.loc[95.0, "upper"]), 3)],
           "coef_LP (dep = ...)": {k: round(float(-ci[k]), 4) for k in ci.index if k != dep},
           "ECT_coef(phi)": round(float(m.params[f"{dep}.L1"]), 4), "ECT_p": round(float(m.pvalues[f"{dep}.L1"]), 4),
           "T": int(m.nobs)}
    res[f"ARDL|{label}"] = out


regs_h = ["Log_Precio_m2", "Log_PIB_pc", "Log_Materiales", "Euribor"]
bounds("Log_Hipotecas", regs_h, Yc, dum, "C|dep=Hipotecas")
bounds("Log_Hipotecas", regs_h, Yo, seasonal_dummies(Yo.index), "A|dep=Hipotecas")
regs_p = ["Log_Hipotecas", "Log_PIB_pc", "Log_Materiales", "Euribor"]
bounds("Log_Precio_m2", regs_p, Yc, dum, "C|dep=Precio")
bounds("Log_Precio_m2", regs_p, Yo, seasonal_dummies(Yo.index), "A|dep=Precio")

with open(OUT / "05_price_norm_ardl.json", "w") as f:
    json.dump(res, f, indent=1, default=str, ensure_ascii=False)
for k, v in res.items():
    print(k, "->", v)
