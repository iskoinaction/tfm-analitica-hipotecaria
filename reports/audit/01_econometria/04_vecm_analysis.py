"""Paso 4: análisis completo del VECM (original vs. especificaciones auditadas).

Uso: python3 04_vecm_analysis.py [B_bootstrap]
"""
import json
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.vector_ar.vecm import VECM

from common import FIG, OUT, ORDER_ORIG, build_clean, build_original, crisis_dummies, seasonal_dummies
from vecm_tools import (VECMfit, arch_lm, bootstrap_irf, lm_autocorr, lr_beta_restriction,
                        lr_weak_exog, normality_dh, permutation_fevd)

warnings.filterwarnings("ignore")
B = int(sys.argv[1]) if len(sys.argv) > 1 else 299
V = ORDER_ORIG
HIP = V.index("Log_Hipotecas")
SH = {"Log_Materiales": "Mat", "Euribor": "Eur", "Log_PIB_pc": "PIB", "Log_Precio_m2": "Pre", "Log_Hipotecas": "Hip"}

Yo = build_original()
Yc = build_clean(weighted=True, end="2024-10-01")
Yc_s = build_clean(weighted=False, end="2024-10-01")
SPECS = {
    "A_original_nb42": dict(Y=Yo, ex=None, case=3, k=1),
    "C_auditada_dumest": dict(Y=Yc, ex=seasonal_dummies(Yc.index), case=3, k=1),
    "E_auditada_dumest_covid": dict(Y=Yc, ex=pd.concat([seasonal_dummies(Yc.index), crisis_dummies(Yc.index)], axis=1), case=3, k=1),
    "G_original_hasta2024_simple": dict(Y=Yo.loc[:"2024-10-01"], ex=None, case=3, k=1),
    "B_auditada_NSA_sin_dummies": dict(Y=Yc, ex=None, case=3, k=1),
}


def H_excl(j, n=5):
    return np.delete(np.eye(n), j, axis=1)


def analyse(name, Y, ex, case, k, boot=True):
    exv = ex.values if ex is not None else None
    f = VECMfit(Y.values, k, case, exv, 1, norm_idx=HIP, names=V)
    J = f.J
    out = {"spec": name, "T_efectiva": f.T, "muestra": [str(Y.index[0].date()), str(Y.index[-1].date())],
           "case": case, "k_ar_diff": k}
    b = f.beta[:5, 0]
    out["ecuacion_LP_logH"] = {SH[v]: round(-b[i], 4) for i, v in enumerate(V) if i != HIP}
    # SE de β vía statsmodels con la misma especificación (hipotecas primero => normalización)
    order_sm = ["Log_Hipotecas"] + [v for v in V if v != "Log_Hipotecas"]
    det = {2: "ci", 3: "co", 4: "colo"}[case]
    sm = VECM(Y[order_sm], exog=ex, k_ar_diff=k, coint_rank=1, deterministic=det).fit()
    out["beta_sm_check"] = dict(zip([SH[v] for v in order_sm], np.round(-sm.beta[:, 0], 4)))
    out["beta_se"] = dict(zip([SH[v] for v in order_sm], np.round(sm.stderr_beta[:, 0], 4)))
    out["beta_p"] = dict(zip([SH[v] for v in order_sm], np.round(sm.pvalues_beta[:, 0], 4)))
    out["alpha"] = {SH[v]: round(f.alpha[i, 0], 4) for i, v in enumerate(V)}
    out["alpha_p"] = {SH[v]: round(f.p_alpha[i, 0], 4) for i, v in enumerate(V)}
    ba = float((f.beta[:5].T @ f.alpha).item())
    out["beta'alpha (AR(1) del ECT = 1+b'a)"] = round(ba, 4)
    out["semivida_ECT_sistema_trim"] = round(np.log(.5) / np.log(1 + ba), 2) if -1 < ba < 0 else None
    out["semivida_univariante_hip"] = round(np.log(.5) / np.log(1 + f.alpha[HIP, 0]), 2)
    out["semivida_univariante_precio"] = round(np.log(.5) / np.log(1 + f.alpha[V.index('Log_Precio_m2'), 0]), 1)
    out["LR_exclusion_beta"] = {SH[v]: [round(x, 3) for x in lr_beta_restriction(J, H_excl(j, J.Z1.shape[1]))] for j, v in enumerate(V)}
    out["LR_exog_debil"] = {SH[v]: [round(x, 3) for x in lr_weak_exog(J, j)] for j, v in enumerate(V)}
    out["LR_exog_debil_conjunta_no_hip"] = [round(x, 3) for x in lr_weak_exog(J, [0, 1, 2, 3])]
    # homogeneidad nominal: β_PIB + β_Pre + β_Mat = 0 (orden V: Mat, Eur, PIB, Pre, Hip)
    p1 = J.Z1.shape[1]
    R = np.zeros((1, p1)); R[0, [0, 2, 3]] = 1
    from scipy.linalg import null_space
    out["LR_homogeneidad_nominal"] = [round(x, 3) for x in lr_beta_restriction(J, null_space(R))]
    # Diagnósticos
    lm1, lm4 = lm_autocorr(f, 1), lm_autocorr(f, 4)
    out["LM_autocorr_h1 (LM,df,p_chi,F,p_F)"] = [round(float(x), 3) for x in lm1]
    out["LM_autocorr_h4"] = [round(float(x), 3) for x in lm4]
    out["ARCH4_p_por_ecuacion"] = dict(zip([SH[v] for v in V], np.round(arch_lm(f.resid), 3)))
    lam, p, jb = normality_dh(f.resid)
    out["Normalidad_multiv (stat,p)"] = [round(lam, 1), round(p, 4)]
    out["JB_p_por_ecuacion"] = dict(zip([SH[v] for v in V], np.round(jb, 4)))
    out["raices_modulo"] = np.round(f.roots()[:7], 4).tolist()
    # FEVD
    fe = f.fevd(20)
    out["FEVD_hip_h20_Cholesky_orig"] = {SH[v]: round(fe[19, HIP, j] * 100, 1) for j, v in enumerate(V)}
    out["FEVD_hip_h4_Cholesky_orig"] = {SH[v]: round(fe[3, HIP, j] * 100, 1) for j, v in enumerate(V)}
    g = f.gfevd(20)
    out["GFEVD_hip_h20_PesaranShin_normalizada"] = {SH[v]: round(g[19, HIP, j] * 100, 1) for j, v in enumerate(V)}
    perms = permutation_fevd(f, HIP, 20)
    arr = np.array([p[1] for p in perms]) * 100
    out["FEVD_hip_h20_120_ordenaciones_min_med_max"] = {SH[v]: [round(arr[:, j].min(), 1), round(np.median(arr[:, j]), 1), round(arr[:, j].max(), 1)] for j, v in enumerate(V)}
    irf = f.orth_irf(20)
    out["IRF_orth_nivel_hip_h0_h4_h20"] = {SH[v]: [round(irf[h, HIP, j], 4) for h in (0, 4, 20)] for j, v in enumerate(V)}
    gi = f.girf(20)
    out["GIRF_nivel_hip_h0_h4_h20"] = {SH[v]: [round(gi[h, HIP, j], 4) for h in (0, 4, 20)] for j, v in enumerate(V)}
    corr = np.corrcoef(f.resid.T)
    out["corr_residuos"] = pd.DataFrame(corr, index=[SH[v] for v in V], columns=[SH[v] for v in V]).round(2).to_dict()
    if boot:
        irfs, fevds, girfs, betas = bootstrap_irf(f, B=B, H=20, resp_idx=HIP, seed=11, norm_idx=HIP)
        out["bootstrap_B_validas"] = len(irfs)
        out["boot_FEVD_h20_P5_P95"] = {SH[v]: [round(np.percentile(fevds[:, j], 5) * 100, 1), round(np.percentile(fevds[:, j], 95) * 100, 1)] for j, v in enumerate(V)}
        out["boot_IRF_h20_P5_P95"] = {SH[v]: [round(np.percentile(irfs[:, 20, j], 5), 4), round(np.percentile(irfs[:, 20, j], 95), 4)] for j, v in enumerate(V)}
        out["boot_beta_LP_P5_P95"] = {SH[v]: [round(-np.percentile(betas[:, j], 95), 3), round(-np.percentile(betas[:, j], 5), 3)] for j, v in enumerate(V) if j != HIP}
        # figura IRF con bandas
        fig, axes = plt.subplots(1, 5, figsize=(17, 3.4))
        for j, v in enumerate(V):
            ax = axes[j]
            lo, hi = np.percentile(irfs[:, :, j], [5, 95], axis=0)
            ax.fill_between(range(21), lo, hi, color="#9db4d6", alpha=.6, label="IC 90% bootstrap")
            ax.plot(irf[:, HIP, j], color="#1f3b70", lw=2, label="Cholesky (orden nb 4.2)")
            ax.plot(gi[:, HIP, j], color="#c0504d", lw=1.4, ls="--", label="GIRF Pesaran-Shin")
            ax.axhline(0, color="k", lw=.6)
            ax.set_title(f"Shock {SH[v]} → log Hip", fontsize=9)
            ax.grid(alpha=.2)
        axes[0].legend(fontsize=7)
        fig.suptitle(f"IRF de log(Hipotecas) — {name} (B={len(irfs)})", fontsize=10)
        fig.tight_layout()
        fig.savefig(FIG / f"irf_{name}.png", dpi=110)
        plt.close(fig)
    return out, f


results = {}
fits = {}
for name, s in SPECS.items():
    boot = name in ("A_original_nb42", "C_auditada_dumest")
    out, f = analyse(name, s["Y"], s["ex"], s["case"], s["k"], boot=boot)
    results[name] = out
    fits[name] = f
    print("=" * 30, name)
    for kk, vv in out.items():
        print(f"  {kk}: {vv}")

# ---------------- Estabilidad: β recursivo y en ventana móvil ---------------
rec = []
for spec in ("A_original_nb42", "C_auditada_dumest"):
    s = SPECS[spec]
    Y, ex = s["Y"], s["ex"]
    for end in range(44, len(Y) + 1):
        Ys = Y.iloc[:end]
        exs = ex.iloc[:end].values if ex is not None else None
        f = VECMfit(Ys.values, 1, 3, exs, 1, norm_idx=HIP)
        b = -f.beta[:5, 0]
        rec.append({"spec": spec, "tipo": "recursivo", "fin": Ys.index[-1], **{SH[v]: b[i] for i, v in enumerate(V)},
                    "alpha_hip": f.alpha[HIP, 0], "trace0": f.J.trace[0], "trace1": f.J.trace[1]})
    W = 48
    for st in range(0, len(Y) - W + 1):
        Ys = Y.iloc[st:st + W]
        exs = ex.iloc[st:st + W].values if ex is not None else None
        f = VECMfit(Ys.values, 1, 3, exs, 1, norm_idx=HIP)
        b = -f.beta[:5, 0]
        rec.append({"spec": spec, "tipo": "movil48", "fin": Ys.index[-1], **{SH[v]: b[i] for i, v in enumerate(V)},
                    "alpha_hip": f.alpha[HIP, 0], "trace0": f.J.trace[0], "trace1": f.J.trace[1]})
rec = pd.DataFrame(rec)
rec.to_csv(OUT / "04_beta_recursivo.csv", index=False, float_format="%.4f")
fig, axes = plt.subplots(2, 4, figsize=(17, 6.5), sharex=True)
for r_i, tipo in enumerate(("recursivo", "movil48")):
    for c_i, v in enumerate(("Pre", "PIB", "Mat", "Eur")):
        ax = axes[r_i, c_i]
        for spec, col in (("A_original_nb42", "#c0504d"), ("C_auditada_dumest", "#1f3b70")):
            d = rec[(rec.spec == spec) & (rec.tipo == tipo)]
            ax.plot(d.fin, d[v].clip(-15, 15), color=col, lw=1.6, label=spec)
        ax.set_title(f"β {v} ({tipo})", fontsize=9)
        ax.grid(alpha=.2)
axes[0, 0].legend(fontsize=7)
fig.suptitle("Estabilidad del vector de cointegración (log H = ...); recortado a ±15", fontsize=10)
fig.tight_layout()
fig.savefig(FIG / "beta_estabilidad.png", dpi=110)
plt.close(fig)
summ = rec.groupby(["spec", "tipo"])[["Pre", "PIB", "Mat", "Eur", "alpha_hip"]].agg(["min", "max"]).round(2)
print(summ.to_string())
results["estabilidad_beta_min_max"] = {f"{a}|{b}": {f"{c}_{d}": float(summ.loc[(a, b), (c, d)]) for c, d in summ.columns} for a, b in summ.index}

# ---------------- ECT: figura y ADF con valores críticos correctos -----------
from statsmodels.tsa.stattools import adfuller, coint
for spec in ("A_original_nb42", "C_auditada_dumest"):
    f = fits[spec]
    Y = SPECS[spec]["Y"]
    ect = Y.values @ f.beta[:5, 0]
    st, p, *_ = adfuller(ect, maxlag=4, autolag="AIC")
    eg = coint(Y["Log_Hipotecas"], Y[[c for c in V if c != "Log_Hipotecas"]], trend="c", maxlag=4, autolag="aic")
    results[spec]["ADF_ECT_tablas_DF_(incorrectas)"] = [round(st, 3), round(p, 4)]
    results[spec]["Engle_Granger_5var (stat,p,cv5%)"] = [round(eg[0], 3), round(eg[1], 4), round(eg[2][1], 3)]
    print(spec, "ECT ADF", st, p, "EG", eg[0], eg[1], eg[2])

with open(OUT / "04_vecm_analysis.json", "w") as fh:
    json.dump(results, fh, indent=1, default=str, ensure_ascii=False)
