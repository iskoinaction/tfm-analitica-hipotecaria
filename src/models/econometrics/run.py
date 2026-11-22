"""Pipeline de econometría v2.

Uso:
    python -m src.models.econometrics.run [--prefer auto|v2|provisional] [--quick]
                                          [--B-rank 999] [--B-irf 499] [--out artifacts/econometrics]

Lee los datos (v2 si existen; si no, construcción provisional marcada como tal), ejecuta
raíces unitarias, rango de Johansen con bootstrap salvaje, aplica la regla de decisión
VECM vs VAR en diferencias, estima ambos, IRF/FEVD (Cholesky + rango por ordenación + GIRF
+ bandas bootstrap), ARDL-bounds y panel, y escribe los artefactos (JSON + CSV + PNG).
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse
import datetime as dt
import json
import platform
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from .ardl import bounds_test
from .cointegration import engle_granger, rank_tests
from .irf_fevd import bootstrap_bands, fevd, fevd_order_range, gfevd, girf, orth_irf
from .panel import cd_test, cips, cips_critical, fe_driscoll_kraay, mg_pmg, wide
from .unit_root import battery, classify
from .var import VARdiff, select_lags
from .vecm import (VECMfit, beta_inference, diagnostics, exclusion_matrix, linear_restriction_matrix,
                   lr_beta_restriction, lr_weak_exog, recursive_beta)

warnings.filterwarnings("ignore")
SH = {"log_materiales": "coste_construccion", "euribor": "euribor", "log_pib_pc": "pib_pc",
      "log_precio": "precio", "log_hipotecas": "hipotecas"}


def _f(x, nd=4):
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), nd)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, dict):
        return {str(k): _f(v, nd) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_f(v, nd) for v in x]
    return x


def exog_matrix(index, impulses=True):
    parts = [D.seasonal_dummies(index)]
    if impulses:
        parts.append(D.impulse_dummies(index, C.SPEC["impulse_dummies"]))
    return pd.concat(parts, axis=1)


def irf_block(Phi, S, names, resp, H, bands, label, order=None):
    """Resultados IRF/FEVD de la variable ``resp`` + filas para CSV."""
    oi = orth_irf(Phi, S, order)
    gi = girf(Phi, S)
    fv = fevd(Phi[:H], S, order)
    gf = gfevd(Phi[:H], S)
    rng = {h: fevd_order_range(Phi, S, resp, h) for h in (4, 8, H)}
    out = {
        "irf_cholesky_h0_h4_h8_h20": {SH[n]: [oi[h, resp, j] for h in (0, 4, 8, H)] for j, n in enumerate(names)},
        "girf_h0_h4_h8_h20": {SH[n]: [gi[h, resp, j] for h in (0, 4, 8, H)] for j, n in enumerate(names)},
        "fevd_cholesky_pct": {f"h{h}": {SH[n]: 100 * fv[h - 1, resp, j] for j, n in enumerate(names)} for h in (1, 4, 8, H)},
        "gfevd_pct": {f"h{h}": {SH[n]: 100 * gf[h - 1, resp, j] for j, n in enumerate(names)} for h in (1, 4, 8, H)},
        "fevd_rango_120_ordenaciones_pct": {f"h{h}": {SH[n]: [100 * r["min"][j], 100 * r["median"][j], 100 * r["max"][j]]
                                                      for j, n in enumerate(names)} for h, r in rng.items()},
    }
    rows_irf, rows_fevd = [], []
    for j, n in enumerate(names):
        for h in range(H + 1):
            for typ, arr, bkey in (("cholesky", oi, "orth_irf"), ("girf", gi, "girf")):
                lo = bands[bkey][0][h, j] if bands else np.nan
                hi = bands[bkey][1][h, j] if bands else np.nan
                rows_irf.append({"modelo": label, "identificacion": typ, "shock": SH[n], "respuesta": SH[names[resp]],
                                 "horizonte": h, "valor": arr[h, resp, j], "p5": lo, "p95": hi})
        for h in range(1, H + 1):
            for typ, arr, bkey in (("cholesky", fv, "fevd"), ("gfevd", gf, "gfevd")):
                lo = bands[bkey][0][h - 1, j] if bands else np.nan
                hi = bands[bkey][1][h - 1, j] if bands else np.nan
                rows_fevd.append({"modelo": label, "metodo": typ, "shock": SH[n], "respuesta": SH[names[resp]],
                                  "horizonte": h, "cuota_pct": 100 * arr[h - 1, resp, j], "p5_pct": 100 * lo, "p95_pct": 100 * hi})
    if bands:
        out["bandas_bootstrap_B_validas"] = bands["B_valid"]
        out["irf_cholesky_h20_p5_p95"] = {SH[n]: [bands["orth_irf"][0][H, j], bands["orth_irf"][1][H, j]] for j, n in enumerate(names)}
        out["girf_h20_p5_p95"] = {SH[n]: [bands["girf"][0][H, j], bands["girf"][1][H, j]] for j, n in enumerate(names)}
        out["fevd_cholesky_h20_p5_p95_pct"] = {SH[n]: [100 * bands["fevd"][0][H - 1, j], 100 * bands["fevd"][1][H - 1, j]] for j, n in enumerate(names)}
        out["gfevd_h20_p5_p95_pct"] = {SH[n]: [100 * bands["gfevd"][0][H - 1, j], 100 * bands["gfevd"][1][H - 1, j]] for j, n in enumerate(names)}
    return out, rows_irf, rows_fevd


def vecm_block(Y, ex, k, case, B_irf, H, seed, label):
    names = list(Y.columns)
    ih, ip = names.index("log_hipotecas"), names.index("log_precio")
    exv = None if ex is None else ex.values
    fit_h = VECMfit(Y.values, k, case, exv, 1, norm_idx=ih, names=names)
    fit_p = VECMfit(Y.values, k, case, exv, 1, norm_idx=ip, names=names)
    J = fit_h.J
    p1 = J.Z1.shape[1]
    beta_h, alpha_h = beta_inference(Y, ex, k, case, "log_hipotecas")
    beta_p, alpha_p = beta_inference(Y, ex, k, case, "log_precio")
    R = np.zeros((1, p1)); R[0, [names.index("log_pib_pc"), ip, names.index("log_materiales")]] = 1  # homogeneidad nominal
    ba = fit_h.beta_alpha
    out = {
        "especificacion": {"k_ar_diff": k, "caso_johansen": case, "rango": 1, "T_efectiva": fit_h.T,
                           "exog": [] if ex is None else list(ex.columns)},
        "beta_normalizado_hipotecas (log H = ...)": {SH[v]: d for v, d in beta_h.items()},
        "alpha_normalizado_hipotecas": {SH[v]: d for v, d in alpha_h.items()},
        "beta_normalizado_precio (log P = ...)": {SH[v]: d for v, d in beta_p.items()},
        "alpha_normalizado_precio": {SH[v]: d for v, d in alpha_p.items()},
        "euribor_semielasticidad_hipotecas_pct_por_pp": 100 * (np.exp(beta_h["euribor"]["coef_LP"]) - 1),
        "ECT_AR1_1_mas_beta_alpha": 1 + ba,
        "semivida_ECT_sistema_trimestres": (np.log(.5) / np.log(1 + ba)) if -1 < ba < 0 else None,
        "LR_exclusion_beta": {SH[v]: lr_beta_restriction(J, exclusion_matrix(j, p1)) for j, v in enumerate(names)},
        "LR_exogeneidad_debil": {SH[v]: lr_weak_exog(J, j) for j, v in enumerate(names)},
        "LR_exogeneidad_debil_conjunta_salvo_hipotecas": lr_weak_exog(J, [j for j in range(len(names)) if j != ih]),
        "LR_exogeneidad_debil_conjunta_salvo_precio": lr_weak_exog(J, [j for j in range(len(names)) if j != ip]),
        "LR_homogeneidad_nominal (b_pib+b_precio+b_coste=0)": lr_beta_restriction(J, linear_restriction_matrix(R)),
        "diagnosticos": diagnostics(fit_h),
    }
    ect = Y.values @ fit_h.beta[:len(names), 0]
    from statsmodels.tsa.stattools import adfuller
    st, p, *_ = adfuller(ect, maxlag=4, autolag="AIC")
    out["ECT_ADF_tablas_DF (solo descriptivo; VC no válidos para residuo estimado)"] = {"stat": st, "p": p}
    out["engle_granger_5var_dep_hipotecas"] = engle_granger(Y["log_hipotecas"], Y.drop(columns="log_hipotecas"))
    Phi = fit_h.ma_rep(H)
    bands = bootstrap_bands(fit_h, B_irf, H, ih, seed=seed, band=tuple(C.SPEC["band"])) if B_irf > 0 else None
    blk, ri, rf = irf_block(Phi, fit_h.sigma, names, ih, H, bands, label)
    out["irf_fevd_hipotecas (respuesta en nivel, log-puntos por shock de 1 d.t.)"] = blk
    rec = pd.concat([recursive_beta(Y, exv, k, case, ip), recursive_beta(Y, exv, k, case, ip, window=48)])
    rec_h = recursive_beta(Y, exv, k, case, ih)
    stab = {}
    for tipo, d in rec.groupby("tipo"):
        stab[f"norm_precio|{tipo}"] = {SH[c]: [d[c].min(), d[c].max()] for c in names if c != "log_precio"}
    stab["norm_hipotecas|recursivo"] = {SH[c]: [rec_h[c].min(), rec_h[c].max()] for c in names if c != "log_hipotecas"}
    out["estabilidad_beta_min_max"] = stab
    return out, ri, rf, rec.assign(norm="precio")


def var_block(Y, ex, B_irf, H, seed, label, maxlags, p_forced=None):
    names = list(Y.columns)
    ih = names.index("log_hipotecas")
    dY = Y.diff().iloc[1:]
    exv = None if ex is None else ex.iloc[1:].values
    sel, ic = select_lags(dY.values, exv, maxlags)
    p = p_forced if p_forced else max(1, sel["bic"])
    m = VARdiff(dY.values, p, exv, names)
    Phi_d = m.ma_rep(H)
    Phi_l = np.cumsum(Phi_d, axis=0)    # respuestas en niveles (logs) = IRF acumuladas de las diferencias
    bands = bootstrap_bands(m, B_irf, H, ih, seed=seed, band=tuple(C.SPEC["band"]), level_from_diff=True) if B_irf > 0 else None
    blk, ri, rf = irf_block(Phi_l, m.sigma, names, ih, H, bands, label)
    fv_g = fevd(Phi_d[:H], m.sigma)
    out = {"especificacion": {"p_diferencias": p, "seleccion_ic": sel,
                              "regla_p": "p = k_ar_diff del VECM (VAR(k+1) en niveles con r=0), validado por LM" if p_forced else "BIC", "T_efectiva": m.T,
                              "exog": [] if ex is None else list(ex.columns), "constante": True},
           "estable": bool(np.max(m.roots()) < 1), "raiz_max": float(np.max(m.roots())),
           "irf_fevd_hipotecas (nivel = IRF acumulada de diferencias)": blk,
           "fevd_crecimiento_hipotecas_h20_cholesky_pct": {SH[n]: 100 * fv_g[H - 1, ih, j] for j, n in enumerate(names)}}
    from .vecm import arch_lm, lm_autocorr, normality
    out["diagnosticos"] = {"LM_h1": lm_autocorr(m.resid, m.X, 1), "LM_h4": lm_autocorr(m.resid, m.X, 4),
                           "ARCH4_p": dict(zip(names, arch_lm(m.resid))), "normalidad": normality(m.resid)}
    return out, ri, rf


def largest_residuals(Y, ex, k):
    f = VECMfit(Y.values, k, 3, None if ex is None else ex.values, 1, norm_idx=list(Y.columns).index("log_hipotecas"))
    z = f.resid / f.resid.std(0)
    idx = Y.index[k + 1:]
    j = list(Y.columns).index("log_hipotecas")
    top = np.argsort(-np.abs(z[:, j]))[:5]
    return {str(idx[t]): float(z[t, j]) for t in top}


def panel_block(pdata: D.PanelData, seed):
    df = pdata.df.copy()
    for c in ("hip", "precio", "pib_pc", "materiales"):
        df[f"l{c}"] = np.log(df[c])
    cols = ["lhip", "lprecio", "lpib_pc", "euribor", "lmateriales"]
    full = df.groupby("period")[cols].apply(lambda g: g.notna().all().all())
    periods = full[full].index
    periods = periods[periods >= pd.Period(C.START, freq="Q-DEC")]
    df = df[df.period.isin(periods)]
    Wl = wide(df, "lhip")
    T, N = Wl.shape
    out = {"N": N, "T": T, "periodo": [str(periods.min()), str(periods.max())], "hipotecas": pdata.hip_kind,
           "CD_dlog_hipotecas": cd_test(Wl.diff()), "CD_dlog_precio": cd_test(wide(df, "lprecio").diff())}
    cv = cips_critical(T, N, reps=200, seed=seed)
    out["CIPS_vc_simulados_1_5_10"] = cv
    out["CIPS"] = {v: {"nivel_c": cips(wide(df, v).values), "nivel_ct": cips(wide(df, v).values, True),
                       "dif_c": cips(np.diff(wide(df, v).values, axis=0))} for v in ("lhip", "lprecio", "lpib_pc")}
    out["FE_DK_niveles"] = fe_driscoll_kraay(df, "lhip", ["lprecio", "lpib_pc", "euribor", "lmateriales"])
    out["FE_DK_diferencias"] = fe_driscoll_kraay(df, "lhip", ["lprecio", "lpib_pc", "euribor", "lmateriales"], diff=True)
    out["MG_PMG_bruto"] = mg_pmg(df, "lhip", ["lprecio", "lpib_pc", "euribor", "lmateriales"], demean=False)
    out["MG_PMG_centrado_transversal"] = mg_pmg(df, "lhip", ["lprecio", "lpib_pc"], demean=True)
    return out


V1_DOCUMENTED = {
    "beta_pib_pc": 0.35, "beta_precio": 2.48, "beta_euribor": -0.10, "beta_materiales": -1.09,
    "alpha_hipotecas": -0.44, "semivida_hipotecas_trim": 1.2, "alpha_precio": -0.006, "semivida_precio_trim": 120,
    "fevd20_precio_pct": 53.3, "fevd20_materiales_pct": 38.8, "fevd20_pib_pct": 2.6, "fevd20_euribor_pct": 2.2,
    "fevd20_propio_pct": 3.0, "johansen_traza_r0": 92.89, "johansen_traza_r1": 46.45, "ECT_ADF_p (doc: <0.05)": 0.204,
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefer", default="auto", choices=["auto", "v2", "provisional"])
    ap.add_argument("--B-rank", type=int, default=C.SPEC["bootstrap_B_rank"])
    ap.add_argument("--B-irf", type=int, default=C.SPEC["bootstrap_B_irf"])
    ap.add_argument("--price", default="auto", choices=["auto", "mivau", "tinsa"],
                    help="precio principal: auto = MIVAU valor tasado si existe (decisión del coordinador), si no Tinsa")
    ap.add_argument("--quick", action="store_true", help="B pequeños, sin panel (para pruebas)")
    ap.add_argument("--no-panel", action="store_true")
    ap.add_argument("--out", default=str(C.ARTIFACTS))
    a = ap.parse_args(argv)
    if a.quick:
        a.B_rank, a.B_irf, a.no_panel = 49, 29, True
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    H, seed = C.SPEC["horizon"], C.SEED

    nd = D.load_national(a.prefer)
    has_mivau = "precio_mivau" in nd.raw and nd.raw["precio_mivau"].notna().sum() >= 60
    if a.price == "mivau" and not has_mivau:
        raise SystemExit("--price mivau pedido pero no hay columna precio_m2_mivau_tasado* con >= 60 trimestres")
    PRICE = "precio_mivau" if (a.price == "mivau" or (a.price == "auto" and has_mivau)) else "precio"
    PRICE_ROB = "precio" if PRICE == "precio_mivau" else ("precio_mivau" if has_mivau else None)
    Y = nd.system("hip_viv", PRICE)
    ex = exog_matrix(Y.index)
    res = {"metadatos": {
        "generado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fuente_datos": nd.source, "provisional": nd.source != "v2", "entradas": nd.inputs, "notas_datos": nd.notes,
        "mapeo_columnas": nd.colmap, "especificacion": C.SPEC, "semilla": seed,
        "precio_principal": {"precio": "Tinsa IMIE ponderado por población (PROVISIONAL: pendiente valor tasado MIVAU)",
                             "precio_mivau": "Valor tasado MIVAU"}[PRICE],
        "precio_robustez": PRICE_ROB,
        "muestra": [str(Y.index[0]), str(Y.index[-1])], "T": len(Y), "variables": list(Y.columns),
        "orden_cholesky_referencia": list(Y.columns),
        "versiones": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                      "statsmodels": __import__("statsmodels").__version__, "arch": __import__("arch").__version__,
                      "linearmodels": __import__("linearmodels").__version__},
        "B_rank": a.B_rank, "B_irf": a.B_irf,
        "advertencia": "IRF/FEVD son descomposiciones condicionadas a supuestos de identificación; no prueban causalidad.",
    }}

    # 1. Raíces unitarias
    ur_rows, verdict = [], {}
    series = dict(Y.items())
    if "hip_tot" in nd.raw:
        series["log_hipotecas_total_fincas"] = np.log(nd.raw["hip_tot"]).loc[Y.index[0]:Y.index[-1]]
    if "precio_ipv" in nd.raw and nd.raw["precio_ipv"].notna().sum() > 30:
        series["log_precio_ipv"] = np.log(nd.raw["precio_ipv"]).loc[Y.index[0]:Y.index[-1]]
    for nme, s in series.items():
        s2 = s.copy(); s2.index = s2.index.astype(str)
        rows = battery(nme, s2)
        ur_rows += rows
        verdict[nme] = classify(rows)
    pd.DataFrame(ur_rows).to_csv(out_dir / "unit_root.csv", index=False, float_format="%.4f")
    res["raices_unitarias_dictamen"] = verdict

    # 2. Retardos (VAR en niveles con dummies, muestra común)
    from statsmodels.tsa.api import VAR
    sel = VAR(Y.reset_index(drop=True), exog=ex.reset_index(drop=True)).select_order(maxlags=C.SPEC["max_lags_selection"], trend="c")
    so = {k: int(v) for k, v in sel.selected_orders.items()}
    from .vecm import lm_autocorr
    k0 = max(1, so["bic"] - 1)
    lm_path = {}
    k = None
    for kk in range(k0, 5):
        f_ = VECMfit(Y.values, kk, C.SPEC["deterministic_case"], ex.values, 1, norm_idx=list(Y.columns).index("log_hipotecas"))
        l1, l4 = lm_autocorr(f_.resid, f_.X, 1), lm_autocorr(f_.resid, f_.X, 4)
        lm_path[kk] = {"LM_h1_pF": l1["p_F"], "LM_h4_pF": l4["p_F"]}
        if k is None and l1["p_F"] >= 0.05 and l4["p_F"] >= 0.05:
            k = kk
    k = k or k0
    res["seleccion_retardos_VAR_niveles"] = {
        "criterios": so, "k_ar_diff_elegido": k, "LM_por_k": lm_path,
        "regla": "partir de BIC-1 (mín. 1) y aumentar hasta que los residuos del VECM no muestren autocorrelación "
                 "(LM Edgerton-Shukur h=1 y h=4, p>=0.05); con autocorrelación los contrastes de rango están sobredimensionados"}
    res["residuos_hipotecas_mayores_z (sin impulsos)"] = largest_residuals(Y, D.seasonal_dummies(Y.index), k)

    # 3. Rango
    rk = rank_tests(Y.values, k, C.SPEC["deterministic_case"], ex.values, B=a.B_rank, seed=seed)
    res["rango_principal"] = rk
    p0 = rk["tests"][0]["p_bootstrap_trace"]
    use_vecm = p0 < C.SPEC["alpha_rank_decision"]
    res["decision"] = {"p_bootstrap_r0": p0, "umbral": C.SPEC["alpha_rank_decision"],
                       "modelo_principal": "VECM (r=1)" if use_vecm else "VAR en diferencias",
                       "modelo_sensibilidad": "VAR en diferencias" if use_vecm else "VECM (r=1)",
                       "regla": "VECM si p_boot(H0: r=0) < 0.10 (bootstrap salvaje CRT, traza); si no, VAR en diferencias."}
    Bs = max(49, a.B_rank // 5)
    sens = {}
    grid = [("caso2", Y, ex, k, 2), ("caso4", Y, ex, k, 4), ("k+1", Y, ex, k + 1, 3),
            ("k=1 (BIC-1, residuos autocorrelacionados)", Y, ex, 1, 3),
            ("sin_impulsos", Y, D.seasonal_dummies(Y.index), k, 3)]
    if "hip_tot" in nd.raw:
        Yt = nd.system("hip_tot", PRICE)
        grid.append(("hip_total_fincas", Yt, exog_matrix(Yt.index), k, 3))
    if "precio_ipv" in nd.raw and nd.raw["precio_ipv"].notna().sum() > 30:
        Yi = nd.system("hip_viv", "precio_ipv")
        grid.append(("precio_ipv", Yi, exog_matrix(Yi.index), k, 3))
    if PRICE_ROB:
        Yv = nd.system("hip_viv", PRICE_ROB)
        grid.append((f"precio_robustez_{PRICE_ROB}", Yv, exog_matrix(Yv.index), k, 3))
    for nm, Yg, eg, kg, cg in grid:
        r = rank_tests(Yg.values, kg, cg, eg.values, B=Bs, seed=seed)
        sens[nm] = {"muestra": [str(Yg.index[0]), str(Yg.index[-1])], "T_efectiva": r["T_efectiva"], "B": Bs,
                    "traza_r0_r1": [r["tests"][0]["trace"], r["tests"][1]["trace"]],
                    "cv95_r0_r1": [r["tests"][0]["cv95_trace"], r["tests"][1]["cv95_trace"]],
                    "p_boot_r0_r1": [r["tests"][0]["p_bootstrap_trace"], r["tests"][1]["p_bootstrap_trace"]],
                    "rango_seleccionado": r["rango_seleccionado"]}
    res["rango_sensibilidad"] = sens

    # 4. Modelos
    irf_rows, fevd_rows = [], []
    vb, ri, rf, rec = vecm_block(Y, ex, k, C.SPEC["deterministic_case"], a.B_irf, H, seed, "VECM")
    res["VECM"] = vb; irf_rows += ri; fevd_rows += rf
    rec.to_csv(out_dir / "beta_recursivo.csv", index=False, float_format="%.4f")
    wb, ri, rf = var_block(Y, ex, a.B_irf, H, seed + 1, "VAR_diferencias", C.SPEC["max_lags_selection"], p_forced=k)
    res["VAR_diferencias"] = wb; irf_rows += ri; fevd_rows += rf
    if "hip_tot" in nd.raw:   # robustez: total fincas (sin bandas)
        Yt = nd.system("hip_tot", PRICE)
        vt, _, _, _ = vecm_block(Yt, exog_matrix(Yt.index), k, 3, 0, H, seed, "VECM_total_fincas")
        res["robustez_total_fincas_VECM"] = {kk: vt[kk] for kk in ("beta_normalizado_hipotecas (log H = ...)",
                                                                    "beta_normalizado_precio (log P = ...)",
                                                                    "alpha_normalizado_hipotecas", "irf_fevd_hipotecas (respuesta en nivel, log-puntos por shock de 1 d.t.)")}
        wt, _, _ = var_block(Yt, exog_matrix(Yt.index), 0, H, seed, "VAR_total_fincas", C.SPEC["max_lags_selection"], p_forced=k)
        res["robustez_total_fincas_VAR"] = wt
    if PRICE_ROB:
        Yp = nd.system("hip_viv", PRICE_ROB)
        wp, _, _ = var_block(Yp, exog_matrix(Yp.index), 0, H, seed, f"VAR_{PRICE_ROB}", C.SPEC["max_lags_selection"], p_forced=k)
        res[f"robustez_precio_{PRICE_ROB}_VAR"] = wp
    if "precio_ipv" in nd.raw and nd.raw["precio_ipv"].notna().sum() > 30:
        Yi = nd.system("hip_viv", "precio_ipv")
        wi, _, _ = var_block(Yi, exog_matrix(Yi.index), 0, H, seed, "VAR_precio_ipv", C.SPEC["max_lags_selection"], p_forced=k)
        res["robustez_precio_ipv_VAR"] = wi
    pd.DataFrame(irf_rows).to_csv(out_dir / "irf_hipotecas.csv", index=False, float_format="%.6f")
    pd.DataFrame(fevd_rows).to_csv(out_dir / "fevd_hipotecas.csv", index=False, float_format="%.4f")

    # 5. ARDL
    res["ARDL_bounds"] = {
        "dep_hipotecas": bounds_test(Y, "log_hipotecas", ["log_precio", "log_pib_pc", "log_materiales", "euribor"], ex),
        "dep_precio": bounds_test(Y, "log_precio", ["log_hipotecas", "log_pib_pc", "log_materiales", "euribor"], ex),
    }

    # 6. Panel
    if not a.no_panel:
        try:
            res["panel"] = panel_block(D.load_panel(a.prefer, price=PRICE), seed)
        except Exception as e:  # el panel es complementario: no bloquea
            res["panel"] = {"error": repr(e)}

    # 7. Antes / después
    vh = res["VECM"]["beta_normalizado_hipotecas (log H = ...)"]
    main_key = "VECM" if use_vecm else "VAR_diferencias"
    blk = res[main_key][[kk for kk in res[main_key] if kk.startswith("irf_fevd")][0]]
    res["antes_despues"] = {
        "v1_documentado": V1_DOCUMENTED,
        "v2_VECM": {"beta_pib_pc": vh["pib_pc"], "beta_precio": vh["precio"], "beta_euribor": vh["euribor"],
                    "beta_materiales": vh["coste_construccion"],
                    "alpha_hipotecas": res["VECM"]["alpha_normalizado_hipotecas"]["hipotecas"],
                    "alpha_precio": res["VECM"]["alpha_normalizado_hipotecas"]["precio"],
                    "traza_r0_r1": [rk["tests"][0]["trace"], rk["tests"][1]["trace"]],
                    "p_boot_r0": p0},
        f"v2_principal_{main_key}_fevd20": {"cholesky": blk["fevd_cholesky_pct"][f"h{H}"], "gfevd": blk["gfevd_pct"][f"h{H}"],
                                             "rango_ordenaciones": blk["fevd_rango_120_ordenaciones_pct"][f"h{H}"]},
    }

    with open(out_dir / "econometrics_v2.json", "w", encoding="utf-8") as fh:
        json.dump(_f(res), fh, indent=1, ensure_ascii=False, default=str)
    _plots(out_dir, irf_rows, fevd_rows, main_key, H)
    print(json.dumps({"fuente": nd.source, "T": len(Y), "k_ar_diff": k, "p_boot_r0": p0,
                      "principal": res["decision"]["modelo_principal"]}, ensure_ascii=False))
    return res


def _plots(out_dir, irf_rows, fevd_rows, main_key, H):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    irf = pd.DataFrame(irf_rows)
    for model in irf.modelo.unique():
        d = irf[irf.modelo == model]
        shocks = list(dict.fromkeys(d.shock))
        fig, axes = plt.subplots(1, len(shocks), figsize=(3.2 * len(shocks), 2.8), sharex=True)
        for ax, s in zip(axes, shocks):
            for typ, col in (("cholesky", "#1f3b70"), ("girf", "#b5523b")):
                e = d[(d.shock == s) & (d.identificacion == typ)]
                ax.plot(e.horizonte, e.valor, color=col, lw=1.6, label=typ)
                if typ == "cholesky" and e.p5.notna().any():
                    ax.fill_between(e.horizonte, e.p5, e.p95, color=col, alpha=.15)
            ax.axhline(0, color="k", lw=.5)
            ax.set_title(f"shock {s}", fontsize=8)
            ax.tick_params(labelsize=7)
        axes[0].legend(fontsize=6)
        fig.suptitle(f"{model}: respuesta de log(hipotecas) (nivel), banda 90 % bootstrap", fontsize=9)
        fig.tight_layout()
        fig.savefig(out_dir / f"irf_{model}.png", dpi=90)
        plt.close(fig)


if __name__ == "__main__":
    main()
