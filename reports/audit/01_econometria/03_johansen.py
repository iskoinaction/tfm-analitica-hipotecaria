"""Paso 3: selección de retardos (muestra común) y rango de Johansen bajo varias
especificaciones (datos, deterministas, estacionalidad, dummies, retardos),
con corrección de Reinsel-Ahn y bootstrap salvaje (Cavaliere-Rahbek-Taylor)."""
import json
import sys
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR

from common import OUT, build_clean, build_original, crisis_dummies, seasonal_dummies
from johansen import Johansen, wild_bootstrap_trace

warnings.filterwarnings("ignore")
B = int(sys.argv[1]) if len(sys.argv) > 1 else 199

specs = {}
Yo = build_original()
specs["A_original_nb42"] = (Yo, None)
Yc = build_clean(weighted=True, end="2024-10-01")
specs["B_auditada_NSA"] = (Yc, None)
specs["C_auditada_dumest"] = (Yc, seasonal_dummies(Yc.index))
Ysa = build_clean(weighted=True, sa_hip=True, end="2024-10-01")
specs["D_auditada_SA"] = (Ysa, None)
specs["E_auditada_dumest_covid"] = (Yc, pd.concat([seasonal_dummies(Yc.index), crisis_dummies(Yc.index)], axis=1))
specs["F_original_dumest"] = (Yo, seasonal_dummies(Yo.index))

# ---------- selección de retardos ----------
lagsel = {}
for name, (Y, ex) in specs.items():
    for ml in (4, 6):
        m = VAR(Y, exog=ex) if ex is not None else VAR(Y)
        s = m.select_order(maxlags=ml, trend="c")
        lagsel[f"{name}|maxlags={ml}"] = {k: int(v) for k, v in s.selected_orders.items()}
print("Selección de retardos (VAR en niveles, muestra común):")
for k, v in lagsel.items():
    print("  ", k, v)

# ---------- Johansen ----------
rows = []
for name, (Y, ex) in specs.items():
    exv = ex.values if ex is not None else None
    for case in (2, 3, 4):
        for k in (1, 2, 3):
            J = Johansen(Y.values, k, case, exv)
            cvt, cvm = J.cv("trace"), J.cv("max")
            r_tr = next((r for r in range(5) if J.trace[r] < cvt[r]), 5)
            r_ra = next((r for r in range(5) if J.trace_ra[r] < cvt[r]), 5)
            r_mx = next((r for r in range(5) if J.maxeig[r] < cvm[r]), 5)
            rows.append({"spec": name, "case": case, "k_ar_diff": k, "T": J.T,
                         "trace": np.round(J.trace, 2).tolist(), "trace_RA": np.round(J.trace_ra, 2).tolist(),
                         "cv95_trace": np.round(cvt, 2).tolist(), "maxeig": np.round(J.maxeig, 2).tolist(),
                         "cv95_max": np.round(cvm, 2).tolist(),
                         "rank_trace": r_tr, "rank_trace_RA": r_ra, "rank_maxeig": r_mx})
jt = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_colwidth", 60, "display.max_rows", 200)
print(jt[["spec", "case", "k_ar_diff", "T", "trace", "trace_RA", "rank_trace", "rank_trace_RA", "rank_maxeig"]].to_string())
jt.to_csv(OUT / "03_johansen_grid.csv", index=False)

# ---------- bootstrap salvaje para las especificaciones clave ----------
boot = {}
for name, case, k in (("A_original_nb42", 3, 1), ("B_auditada_NSA", 3, 1), ("C_auditada_dumest", 3, 1),
                      ("C_auditada_dumest", 2, 1), ("C_auditada_dumest", 4, 1), ("C_auditada_dumest", 3, 2)):
    Y, ex = specs[name]
    J, p = wild_bootstrap_trace(Y.values, k, case, ex.values if ex is not None else None, B=B, rmax=3, seed=2024)
    boot[f"{name}|case{case}|k{k}"] = {"trace": np.round(J.trace[:3], 2).tolist(), "p_boot": p}
    print("bootstrap", name, case, k, boot[f"{name}|case{case}|k{k}"], flush=True)

with open(OUT / "03_johansen.json", "w") as f:
    json.dump({"lag_selection": lagsel, "bootstrap_B": B, "bootstrap": boot}, f, indent=1)
