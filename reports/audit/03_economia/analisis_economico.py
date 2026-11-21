"""
Auditoría económica del TFM (agente 03 - economista).

Reproduce y contrasta, con los datos del propio repositorio y con series oficiales
descargadas (INE Tempus3 / BCE Data API, guardadas en ./data), los resultados
económicos del TFM:
  1. Ciclo hipotecario 2005-2025 (fases) y su relación con Euribor, precios, paro.
  2. Réplica y robustez del VECM del notebook 4.2 (beta, alpha, ECT, FEVD).
  3. Plausibilidad de las proyecciones 2026-2030 (predicciones_provinciales_2026_2030.csv).
  4. Indicadores de negocio provinciales (accesibilidad / esfuerzo) calculables con el dataset.

Uso (desde la raíz del repo):
    python reports/audit/03_economia/analisis_economico.py
Salidas en reports/audit/03_economia/: fig_*.png, *.csv, resultados.json

No modifica ningún fichero fuera de reports/audit/03_economia/.
"""
from __future__ import annotations

import itertools
import json
import re
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.vector_ar.vecm import VECM, coint_johansen

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = OUT / "data"
NB = ROOT / "notebooks acabados"
RAW = ROOT / "Datos ya metidos"

# Paleta (skill dataviz, referencia clara) + tintas de texto
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
    "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "axes.titlesize": 10, "axes.titleweight": "bold", "lines.linewidth": 2,
})

RES: dict = {}

PHASES = [
    ("Boom 2005-2007", "2005-01-01", "2007-12-31"),
    ("Crisis 2008-2013", "2008-01-01", "2013-12-31"),
    ("Recuperación 2014-2019", "2014-01-01", "2019-12-31"),
    ("COVID 2020-2021", "2020-01-01", "2021-12-31"),
    ("Subida de tipos 2022-2023", "2022-01-01", "2023-12-31"),
    ("2024-2025", "2024-01-01", "2025-12-31"),
]


# ----------------------------------------------------------------------------
# 0. Datos
# ----------------------------------------------------------------------------
def load_dataset() -> pd.DataFrame:
    d = pd.read_csv(NB / "dataset_final_tfm.csv")
    d["Trimestre"] = pd.to_datetime(d["Trimestre"])
    return d


def ine_series(code: str) -> pd.Series:
    """Serie mensual INE guardada en data/ine_<code>.json (DATOS_SERIE, nult=300)."""
    j = json.load(open(DATA / f"ine_{code}.json"))
    df = pd.DataFrame(j["Data"])
    # Fecha en ms (hora local de Madrid); se normaliza al día 1 del mes
    f = pd.to_datetime(df["Fecha"], unit="ms") + pd.Timedelta(hours=3)
    s = pd.Series(df["Valor"].values, index=f.dt.to_period("M").dt.to_timestamp())
    return s.sort_index()


def to_quarter_sum(s: pd.Series) -> pd.Series:
    q = s.groupby(s.index.to_period("Q")).agg(["sum", "count"])
    q = q[q["count"] == 3]["sum"]
    q.index = q.index.to_timestamp()
    return q


def parse_ine_export(val: str) -> float:
    """Interpretación correcta del CSV exportado por INE en el que los miles usan '.'
    y se han perdido los ceros finales ('19.16' = 19.160; '398.0' = 398)."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    m = re.fullmatch(r"(\d+)\.(\d+)", s)
    if not m:
        return float(s)
    ent, dec = m.groups()
    if dec == "0":  # entero escrito como 'NNN.0'
        return float(ent)
    return float(ent) * 1000 + float(dec.ljust(3, "0"))


def nb_limpiar_numero(val) -> float:
    """Copia literal de la función del notebook 3 (para medir el error)."""
    if pd.isna(val):
        return np.nan
    v = str(val).strip()
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    elif re.search(r"\.[0-9]{3}$", v):
        v = v.replace(".", "")
    try:
        return float(v)
    except ValueError:
        return np.nan


def national_panel(d: pd.DataFrame) -> pd.DataFrame:
    w = d["Poblacion"]
    g = d.assign(
        wP=d["Precio_m2"] * w, wU=d["Tasa_Paro"] * w, wY=d["PIB_pc"] * w,
    ).groupby("Trimestre")
    n = pd.DataFrame({
        "H_dataset": g["Hipotecas_Total"].sum(),
        "Compraventas": g["Transmisiones_Total"].sum(),
        "Euribor": g["Euribor"].first(),
        "Spread": g["Spread_Hipotecas"].first(),
        "Materiales": g["Indice_Materiales"].first(),
        "Precio_simple": g["Precio_m2"].mean(),
        "Precio_pond": g["wP"].sum() / g["Poblacion"].sum(),
        "Paro_pond": g["wU"].sum() / g["Poblacion"].sum(),
        "PIBpc_pond": g["wY"].sum() / g["Poblacion"].sum(),
        "PIBpc_simple": g["PIB_pc"].mean(),
    })
    n.loc[n["PIBpc_simple"].isna(), "PIBpc_pond"] = np.nan
    return n


# ----------------------------------------------------------------------------
# 1. Calidad del target y ciclo
# ----------------------------------------------------------------------------
def target_quality(d: pd.DataFrame, nat: pd.DataFrame) -> pd.DataFrame:
    raw = pd.read_csv(RAW / "hipotecas_por_prov_men.csv", sep=";", encoding="latin1", dtype=str)
    vals = raw["Total"]
    nb = vals.map(nb_limpiar_numero)
    ok = vals.map(parse_ine_export)
    raw["periodo"] = pd.to_datetime(raw["Periodo"].str.replace("M", "-") + "-01")
    raw["nb"], raw["ok"] = nb, ok
    mal = (nb != ok) & nb.notna()
    RES["hipotecas_parse"] = {
        "valores_mensuales": int(len(vals)),
        "valores_mal_parseados_por_limpiar_numero": int(mal.sum()),
        "ejemplos": raw.loc[mal, ["Provincias", "Periodo", "Total", "nb", "ok"]].head(6).astype(str).values.tolist(),
    }
    ine_tot = to_quarter_sum(ine_series("HPT34936"))
    ine_viv = to_quarter_sum(ine_series("HPT34618"))
    rep = to_quarter_sum(raw.groupby("periodo")["ok"].sum())
    comp = pd.DataFrame({
        "dataset": nat["H_dataset"], "reparseado": rep, "INE_total_fincas": ine_tot,
        "INE_viviendas": ine_viv,
    }).loc["2005":"2025"]
    yr = comp.groupby(comp.index.year).sum()
    yr["err_dataset_vs_INE_%"] = (yr["dataset"] / yr["INE_total_fincas"] - 1) * 100
    yr["err_reparseado_vs_INE_%"] = (yr["reparseado"] / yr["INE_total_fincas"] - 1) * 100
    yr["cuota_viviendas_%"] = yr["INE_viviendas"] / yr["INE_total_fincas"] * 100
    yr.round(1).to_csv(OUT / "hipotecas_dataset_vs_INE_anual.csv")
    RES["hipotecas_vs_INE"] = {
        "err_dataset_%_2005": round(yr.loc[2005, "err_dataset_vs_INE_%"], 1),
        "err_dataset_%_2006": round(yr.loc[2006, "err_dataset_vs_INE_%"], 1),
        "err_dataset_%_2024": round(yr.loc[2024, "err_dataset_vs_INE_%"], 1),
        "err_dataset_%_2025": round(yr.loc[2025, "err_dataset_vs_INE_%"], 1),
        "max_abs_err_reparseado_%": round(yr["err_reparseado_vs_INE_%"].abs().max(), 2),
        "cuota_viviendas_%_2006": round(yr.loc[2006, "cuota_viviendas_%"], 1),
        "cuota_viviendas_%_2025": round(yr.loc[2025, "cuota_viviendas_%"], 1),
    }
    return comp


def cycle_analysis(nat: pd.DataFrame, comp: pd.DataFrame) -> pd.DataFrame:
    n = nat.copy()
    n["H_viv"] = comp["INE_viviendas"]
    n["H_tot"] = comp["INE_total_fincas"]
    cv = to_quarter_sum(ine_series("ETDP1826"))
    n["Compraventas_INE"] = cv
    rows = []
    for name, a, b in PHASES:
        s = n.loc[a:b]
        ya, yb = pd.Timestamp(a).year, pd.Timestamp(b).year
        hv = comp["INE_viviendas"]
        h_ini = hv[hv.index.year == ya - 1].sum() if ya > 2005 else np.nan
        h_fin = hv[hv.index.year == yb].sum()
        p0 = n["Precio_pond"].loc[:a].iloc[-1] if ya > 2005 else s["Precio_pond"].iloc[0]
        rows.append({
            "Fase": name,
            "Hipotecas viviendas/año (INE, media)": round(s["H_viv"].sum() / (len(s) / 4)),
            "Var. hipotecas viv. (año fin vs año previo a la fase, %)": round((h_fin / h_ini - 1) * 100, 1) if h_ini == h_ini else np.nan,
            "Euribor 12m medio (%)": round(s["Euribor"].mean(), 2),
            "Euribor cambio (pp)": round(s["Euribor"].iloc[-1] - (n["Euribor"].loc[:a].iloc[-2] if ya > 2005 else s["Euribor"].iloc[0]), 2),
            "Precio m2 Tinsa pond. (var. %, fase)": round((s["Precio_pond"].iloc[-1] / p0 - 1) * 100, 1),
            "Paro medio pond. (%)": round(s["Paro_pond"].mean(), 1),
            "Materiales (var. %, fase)": round((s["Materiales"].dropna().iloc[-1] / s["Materiales"].dropna().iloc[0] - 1) * 100, 1),
            "Hip. viv./compraventas (media)": round(s["H_viv"].sum() / s["Compraventas_INE"].sum(), 2) if s["Compraventas_INE"].notna().all() else np.nan,
        })
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "ciclo_fases.csv", index=False)

    # Correlaciones interanuales
    y = np.log(n["H_viv"]).diff(4) * 100
    de = n["Euribor"].diff(4)
    dp = np.log(n["Precio_pond"]).diff(4) * 100
    dm = np.log(n["Materiales"]).diff(4) * 100
    du = n["Paro_pond"].diff(4)
    cc = pd.DataFrame({"dlogH_viv": y, "dEuribor": de, "dlogP": dp, "dlogMat": dm, "dParo": du}).dropna()
    RES["correlaciones_interanuales_2006_2025"] = cc.corr()["dlogH_viv"].round(2).to_dict()
    sub = cc.loc["2021":"2025"]
    RES["correlaciones_interanuales_2021_2025"] = sub.corr()["dlogH_viv"].round(2).to_dict()
    # Episodio 2022-2023
    hv = comp["INE_viviendas"]
    RES["episodio_subida_tipos"] = {
        "hip_viv_2022": int(hv[hv.index.year == 2022].sum()),
        "hip_viv_2023": int(hv[hv.index.year == 2023].sum()),
        "var_2023_vs_2022_%": round((hv[hv.index.year == 2023].sum() / hv[hv.index.year == 2022].sum() - 1) * 100, 1),
        "euribor_2021Q4": round(n.loc["2021-10-01", "Euribor"], 2),
        "euribor_2023Q3": round(n.loc["2023-07-01", "Euribor"], 2),
        "materiales_var_2022Q2_2023Q4_%": round((n.loc["2023-10-01", "Materiales"] / n.loc["2022-04-01", "Materiales"] - 1) * 100, 1),
        "precio_pond_var_2022Q4_2023Q4_%": round((n.loc["2023-10-01", "Precio_pond"] / n.loc["2022-10-01", "Precio_pond"] - 1) * 100, 1),
        "hip_viv_2024": int(hv[hv.index.year == 2024].sum()),
        "hip_viv_2025": int(hv[hv.index.year == 2025].sum()),
    }
    # 2026 (fuera de la muestra del TFM)
    hm = ine_series("HPT34618")
    cvm = ine_series("ETDP1826")
    RES["datos_2026_INE"] = {
        "hip_viv_ene_ago_2026": int(hm["2026-01":"2026-08"].sum()),
        "hip_viv_ene_ago_2025": int(hm["2025-01":"2025-08"].sum()),
        "var_%": round((hm["2026-01":"2026-08"].sum() / hm["2025-01":"2025-08"].sum() - 1) * 100, 1),
        "compraventas_ene_sep_2026": int(cvm["2026-01":"2026-09"].sum()),
        "compraventas_ene_sep_2025": int(cvm["2025-01":"2025-09"].sum()),
        "var_compraventas_%": round((cvm["2026-01":"2026-09"].sum() / cvm["2025-01":"2025-09"].sum() - 1) * 100, 1),
    }
    return n, tab


def fig_cycle(n: pd.DataFrame) -> None:
    fig, ax = plt.subplots(2, 2, figsize=(11, 6.8), sharex=True)
    spans = [("2008-01-01", "2013-12-31"), ("2020-01-01", "2021-12-31"), ("2022-04-01", "2023-12-31")]

    def shade(a):
        for s, e in spans:
            a.axvspan(pd.Timestamp(s), pd.Timestamp(e), color="#e9e8e4", lw=0, zorder=0)

    a = ax[0, 0]
    shade(a)
    a.plot(n.index, n["H_viv"] / 1000, color=C1, label="Hipotecas sobre viviendas (INE)")
    a.plot(n.index, n["H_dataset"] / 1000, color=C2, lw=1.4, label="Hipotecas_Total del dataset (total fincas, mal parseado)")
    a.set_title("Hipotecas constituidas por trimestre (miles)")
    a.legend(fontsize=7.5, frameon=False)
    a = ax[0, 1]
    shade(a)
    a.plot(n.index, n["Euribor"], color=C1)
    a.axhline(0, color=INK2, lw=0.8)
    a.set_title("Euribor 12 meses (%, media trimestral)")
    a = ax[1, 0]
    shade(a)
    a.plot(n.index, n["Precio_pond"], color=C1, label="Precio m² Tinsa (media pond. población)")
    a.plot(n.index, n["Precio_simple"], color=C2, lw=1.4, label="Media simple de provincias (usada en el VECM)")
    a.set_title("Precio de la vivienda (€/m², nominal)")
    a.legend(fontsize=7.5, frameon=False)
    a = ax[1, 1]
    shade(a)
    base = n["Materiales"].loc["2005-01-01"]
    a.plot(n.index, n["Materiales"] / base * 100, color=C1)
    a.set_title("Índice_Materiales (2005T1 = 100)")
    fig.suptitle("Ciclo hipotecario español 2005-2025 (sombreado: crisis 2008-13, COVID, subida de tipos 2022-23)",
                 fontsize=10.5, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_01_ciclo_2005_2025.png", dpi=130)
    plt.close(fig)

    # Variaciones interanuales: hipotecas vs Euribor (dos paneles, mismo eje temporal)
    y = (np.log(n["H_viv"]).diff(4) * 100)
    de = n["Euribor"].diff(4)
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True)
    for a in ax:
        shade(a)
        a.axhline(0, color=INK2, lw=0.8)
    ax[0].bar(y.index, y, width=70, color=C1)
    ax[0].set_title("Hipotecas sobre viviendas: variación interanual (%)")
    ax[1].bar(de.index, de, width=70, color=C2)
    ax[1].set_title("Euribor 12m: variación interanual (pp)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_02_hipotecas_vs_euribor_interanual.png", dpi=130)
    plt.close(fig)


# ----------------------------------------------------------------------------
# 2. VECM: réplica y robustez
# ----------------------------------------------------------------------------
ORDER_NB = ["Log_Materiales", "Euribor", "Log_PIB_pc", "Log_Precio_m2", "Log_Hipotecas"]


def build_vecm_data(d: pd.DataFrame, h_series: pd.Series | None = None, price="simple",
                    end=None) -> pd.DataFrame:
    df = d.copy()
    for col in ["tasa_ahorro", "Indice_Mano_Obra", "Indice_Materiales", "IPC", "PIB_pc", "Pob_Ext", "Precio_m2"]:
        df[col] = df.groupby("Provincia")[col].transform(lambda x: x.ffill().bfill())
    g = df.groupby("Trimestre")
    if price == "simple":
        P = g["Precio_m2"].mean()
        Y = g["PIB_pc"].mean()
    else:
        P = (df["Precio_m2"] * df["Poblacion"]).groupby(df["Trimestre"]).sum() / g["Poblacion"].sum()
        Y = (df["PIB_pc"] * df["Poblacion"]).groupby(df["Trimestre"]).sum() / g["Poblacion"].sum()
    H = g["Hipotecas_Total"].sum() if h_series is None else h_series.reindex(P.index)
    out = pd.DataFrame({
        "Log_Materiales": np.log(g["Indice_Materiales"].mean()),
        "Euribor": g["Euribor"].mean(),
        "Log_PIB_pc": np.log(Y),
        "Log_Precio_m2": np.log(P),
        "Log_Hipotecas": np.log(H),
    }).dropna()
    if end:
        out = out.loc[:end]
    out.index = pd.DatetimeIndex(out.index, freq="QS-JAN")
    return out


def fevd_from(fit, order_idx, h=20):
    """FEVD con Cholesky en el orden dado (índices de columnas)."""
    ma = fit.ma_rep(maxn=h)  # (h+1, k, k) no ortogonal
    sig = fit.sigma_u
    k = sig.shape[0]
    P = np.zeros((k, k))
    perm = list(order_idx)
    Ls = np.linalg.cholesky(sig[np.ix_(perm, perm)])
    # reconstruir P en el orden original de variables
    P[np.ix_(perm, perm)] = Ls
    orth = np.array([m @ P for m in ma])  # columnas: shocks en el orden original
    mse = np.cumsum(orth ** 2, axis=0)
    return mse / mse.sum(axis=2, keepdims=True)


def vecm_spec(name: str, data: pd.DataFrame, seasons: int = 0) -> dict:
    cols = list(data.columns)
    hi = cols.index("Log_Hipotecas")
    jo = coint_johansen(data, det_order=0, k_ar_diff=1)
    r_trace = int(sum(1 for i in range(len(cols)) if all(jo.lr1[j] > jo.cvt[j, 1] for j in range(i + 1))))
    fit = VECM(data, k_ar_diff=1, coint_rank=1, deterministic="co", seasons=seasons).fit()
    b = fit.beta[:, 0]
    bn = b / b[hi]
    a = fit.alpha[:, 0]
    pa = fit.pvalues_alpha[:, 0]
    ect = data.values @ b
    adf_p = adfuller(ect, maxlag=4, autolag="AIC")[1]
    # Signo "corrector" de cada variable: a_i * b_i < 0 => la variable reduce el desequilibrio
    corrige = {c: bool(a[i] * b[i] < 0) for i, c in enumerate(cols)}
    lr = {c: round(float(-bn[i]), 3) for i, c in enumerate(cols) if c != "Log_Hipotecas"}
    order_idx = [cols.index(c) for c in ORDER_NB if c in cols]
    fv = fevd_from(fit, order_idx)
    fevd20 = {c: round(float(fv[19, hi, i]) * 100, 1) for i, c in enumerate(cols)}
    res = {
        "spec": name, "muestra": f"{data.index[0].date()}..{data.index[-1].date()}", "n": len(data),
        "johansen_traza_r0": round(float(jo.lr1[0]), 2), "cv95_r0": round(float(jo.cvt[0, 1]), 2),
        "johansen_traza_r1": round(float(jo.lr1[1]), 2), "cv95_r1": round(float(jo.cvt[1, 1]), 2),
        "rango_traza_5%": r_trace,
        "beta_largo_plazo (log H* = ...)": lr,
        "alpha": {c: round(float(a[i]), 4) for i, c in enumerate(cols)},
        "p_alpha": {c: round(float(pa[i]), 3) for i, c in enumerate(cols)},
        "alpha_corrige_desequilibrio": corrige,
        "ADF_ECT_pvalor": round(float(adf_p), 3),
        "FEVD20_hipotecas_orden_notebook_%": fevd20,
    }
    if len(cols) == 5:
        eu = cols.index("Euribor")
        mat = cols.index("Log_Materiales")
        shares_e, shares_m = [], []
        for perm in itertools.permutations(range(len(cols))):
            f = fevd_from(fit, perm)
            shares_e.append(f[19, hi, eu] * 100)
            shares_m.append(f[19, hi, mat] * 100)
        res["FEVD20_Euribor_rango_120_ordenes_%"] = [round(min(shares_e), 1), round(max(shares_e), 1)]
        res["FEVD20_Materiales_rango_120_ordenes_%"] = [round(min(shares_m), 1), round(max(shares_m), 1)]
        # Euribor primero
        o = [eu] + [i for i in order_idx if i != eu]
        res["FEVD20_Euribor_si_Euribor_primero_%"] = round(float(fevd_from(fit, o)[19, hi, eu]) * 100, 1)
    return res, fit


def vecm_robustness(d: pd.DataFrame, comp: pd.DataFrame) -> list:
    base = build_vecm_data(d)
    specs = []
    r, fit0 = vecm_spec("S0 réplica notebook 4.2 (2005T1-2025T4, imputaciones ffill)", base)
    specs.append(r)
    specs.append(vecm_spec("S1 = S0 hasta 2024T4 (sin 2025 imputado)", build_vecm_data(d, end="2024-10-01"))[0])
    specs.append(vecm_spec("S2 = S1 con hipotecas total fincas INE (parseo correcto)",
                           build_vecm_data(d, h_series=comp["INE_total_fincas"], end="2024-10-01"))[0])
    specs.append(vecm_spec("S3 = S1 con hipotecas sobre VIVIENDAS INE",
                           build_vecm_data(d, h_series=comp["INE_viviendas"], end="2024-10-01"))[0])
    specs.append(vecm_spec("S4 = S3 + dummies estacionales", build_vecm_data(d, h_series=comp["INE_viviendas"], end="2024-10-01"), seasons=4)[0])
    specs.append(vecm_spec("S5 = S3 con precio y PIB pc ponderados por población",
                           build_vecm_data(d, h_series=comp["INE_viviendas"], price="pond", end="2024-10-01"))[0])
    specs.append(vecm_spec("S6 = S3 sin Log_Materiales",
                           build_vecm_data(d, h_series=comp["INE_viviendas"], end="2024-10-01").drop(columns="Log_Materiales"))[0])
    specs.append(vecm_spec("S7 = S3 muestra pre-COVID (2005T1-2019T4)",
                           build_vecm_data(d, h_series=comp["INE_viviendas"], end="2019-10-01"))[0])
    RES["vecm"] = specs
    # Implicación de la semielasticidad Euribor de S0 para 2022-2023
    se = specs[0]["beta_largo_plazo (log H* = ...)"]["Euribor"]
    RES["vecm_implicacion_euribor"] = {
        "semielasticidad": se,
        "efecto_LP_subida_4.6pp_%": round((np.exp(se * 4.6) - 1) * 100, 1),
    }
    # tabla compacta
    rows = []
    for s in specs:
        b = s["beta_largo_plazo (log H* = ...)"]
        rows.append({
            "Especificación": s["spec"], "n": s["n"], "rango (traza 5%)": s["rango_traza_5%"],
            "β PIB_pc": b.get("Log_PIB_pc"), "β Precio": b.get("Log_Precio_m2"),
            "β Euribor": b.get("Euribor"), "β Materiales": b.get("Log_Materiales", np.nan),
            "α Hip.": s["alpha"]["Log_Hipotecas"], "α Precio": s["alpha"]["Log_Precio_m2"],
            "α Precio corrige?": s["alpha_corrige_desequilibrio"]["Log_Precio_m2"],
            "ADF ECT p": s["ADF_ECT_pvalor"],
            "FEVD20 Euribor % (orden nb)": s["FEVD20_hipotecas_orden_notebook_%"]["Euribor"],
            "FEVD20 Euribor % rango 120 órdenes": s.get("FEVD20_Euribor_rango_120_ordenes_%"),
            "FEVD20 Precio % (orden nb)": s["FEVD20_hipotecas_orden_notebook_%"]["Log_Precio_m2"],
            "FEVD20 Materiales % (orden nb)": s["FEVD20_hipotecas_orden_notebook_%"].get("Log_Materiales"),
        })
    pd.DataFrame(rows).to_csv(OUT / "vecm_robustez.csv", index=False)
    return specs


def fig_fevd(specs: list) -> None:
    s = specs[0]
    lo, hi = s["FEVD20_Euribor_rango_120_ordenes_%"]
    mlo, mhi = s["FEVD20_Materiales_rango_120_ordenes_%"]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.barh([1], [hi - lo], left=[lo], color=C1, height=0.4)
    ax.barh([0], [mhi - mlo], left=[mlo], color=C2, height=0.4)
    ax.plot([s["FEVD20_hipotecas_orden_notebook_%"]["Euribor"]], [1], "o", color=INK, ms=7)
    ax.plot([s["FEVD20_hipotecas_orden_notebook_%"]["Log_Materiales"]], [0], "o", color=INK, ms=7)
    ax.set_yticks([0, 1], ["Materiales", "Euribor"])
    ax.set_xlim(0, 100)
    ax.set_xlabel("% de la varianza del error de previsión de log(hipotecas) a 20 trimestres")
    ax.set_title("FEVD del VECM del TFM según el orden de Cholesky (120 órdenes posibles)\n"
                 "barra = rango; punto = orden elegido en el notebook 4.2")
    ax.text(lo, 1.3, f"{lo:.1f}%", color=INK2, fontsize=8)
    ax.text(hi, 1.3, f"{hi:.1f}%", color=INK2, fontsize=8, ha="right")
    ax.text(mlo, 0.3, f"{mlo:.1f}%", color=INK2, fontsize=8)
    ax.text(mhi, 0.3, f"{mhi:.1f}%", color=INK2, fontsize=8, ha="right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_03_fevd_sensibilidad_orden.png", dpi=130)
    plt.close(fig)


# ----------------------------------------------------------------------------
# 3. Proyecciones 2026-2030
# ----------------------------------------------------------------------------
def projections(d: pd.DataFrame) -> pd.DataFrame:
    p = pd.read_csv(NB / "predicciones_provinciales_2026_2030.csv")
    p["anio"] = p["trimestre"].str[:4].astype(int)
    pv = p.pivot_table(index=["provincia", "trimestre"], columns="variable", values="valor").reset_index()
    pv["anio"] = pv["trimestre"].str[:4].astype(int)
    pop25 = d[d["Trimestre"].dt.year == 2025].groupby("Provincia")["Poblacion"].mean()
    pv["w"] = pv["provincia"].map(pop25)

    def wavg(g, c):
        return (g[c] * g["w"]).sum() / g["w"].sum()

    yrs = pv.groupby("anio")
    nat = pd.DataFrame({
        "Euribor": yrs["Euribor"].mean(), "IPC": yrs["IPC"].mean(),
        "Paro_pond": yrs.apply(lambda g: wavg(g, "Tasa_Paro")),
        "PIBpc_pond": yrs.apply(lambda g: wavg(g, "PIB_pc")),
        "Precio_pond": yrs.apply(lambda g: wavg(g, "Precio_m2")),
        "Compraventas": yrs["Transmisiones_Total"].sum(),
    })
    # Observado (dataset) para comparar
    dd = d.copy()
    dd["anio"] = dd["Trimestre"].dt.year
    obs = dd[dd["anio"].isin([2023, 2024, 2025])].groupby("anio").apply(lambda g: pd.Series({
        "Euribor": g["Euribor"].mean(), "IPC": (g["IPC"] * g["Poblacion"]).sum() / g["Poblacion"].sum(),
        "Paro_pond": (g["Tasa_Paro"] * g["Poblacion"]).sum() / g["Poblacion"].sum(),
        "PIBpc_pond": (g["PIB_pc"] * g["Poblacion"]).sum() / g["Poblacion"].sum() if g["PIB_pc"].notna().all() else np.nan,
        "Precio_pond": (g["Precio_m2"] * g["Poblacion"]).sum() / g["Poblacion"].sum(),
        "Compraventas": g["Transmisiones_Total"].sum(),
    }))
    obs.index = [f"{i} (obs. dataset)" for i in obs.index]
    nat.index = [f"{i} (proyección)" for i in nat.index]
    tab = pd.concat([obs, nat])
    tab["Var. precio %"] = tab["Precio_pond"].pct_change() * 100
    tab["Var. PIB pc nominal %"] = tab["PIBpc_pond"].pct_change() * 100
    tab.round(2).to_csv(OUT / "proyecciones_agregado_nacional.csv")

    # Paro: efecto del suelo 8.5
    last = d[d["Trimestre"] == d["Trimestre"].max()].set_index("Provincia")["Tasa_Paro"]
    m25 = d[d["Trimestre"].dt.year == 2025].groupby("Provincia")["Tasa_Paro"].mean()
    p26 = pv[pv["trimestre"] == "2026-01"].set_index("provincia")["Tasa_Paro"]
    clipped = pv[(pv["anio"] >= 2026)].groupby("provincia")["Tasa_Paro"].apply(lambda s: (s <= 8.5 + 1e-9).mean())
    lowp = m25[m25 < 8.5].sort_values()
    salto = pd.DataFrame({"paro_2025T4_obs": last, "paro_medio_2025_obs": m25.round(2),
                          "paro_2026T1_proy": p26, "salto_pp": (p26 - last).round(2),
                          "%_trimestres_2026_30_en_suelo": (clipped * 100).round(0)})
    salto.sort_values("paro_2025T4_obs").to_csv(OUT / "paro_suelo_nairu_por_provincia.csv")
    RES["proyecciones"] = {
        "euribor_por_anio": nat["Euribor"].round(2).to_dict(),
        "ipc_por_anio": nat["IPC"].round(2).to_dict(),
        "paro_pond_por_anio": nat["Paro_pond"].round(2).to_dict(),
        "precio_var_%_por_anio": tab["Var. precio %"].round(2).to_dict(),
        "pibpc_var_%_por_anio": tab["Var. PIB pc nominal %"].round(2).to_dict(),
        "compraventas_por_anio": tab["Compraventas"].round(0).to_dict(),
        "provincias_paro_medio_2025_<8.5": {k: round(v, 2) for k, v in lowp.items()},
        "n_provincias_con_algun_trimestre_en_suelo": int((clipped > 0).sum()),
        "n_provincias_todo_2026_2030_en_suelo": int((clipped == 1).sum()),
        "salto_max_2025T4_2026T1_pp": float(salto["salto_pp"].max()),
        "euribor_2025_en_csv": float(pv[pv["anio"] == 2025]["Euribor"].mean()),
        "euribor_2025_dataset": round(float(d[d["Trimestre"].dt.year == 2025]["Euribor"].mean()), 3),
        "precio_2025_csv_constante_igual_ultimo_obs": bool(
            pv[pv["anio"] == 2025].groupby("provincia")["Precio_m2"].nunique().max() == 1),
    }
    # Euribor 12m observado (BCE) para 2025 y 2026
    eu = pd.read_csv(DATA / "ecb_euribor12m.csv")[["TIME_PERIOD", "OBS_VALUE"]]
    eu["anio"] = eu["TIME_PERIOD"].str[:4]
    RES["euribor12m_BCE"] = {
        "media_2025": round(eu[eu.anio == "2025"]["OBS_VALUE"].mean(), 3),
        "media_ene_oct_2026": round(eu[eu.anio == "2026"]["OBS_VALUE"].mean(), 3),
        "ultimo": eu.iloc[-1][["TIME_PERIOD", "OBS_VALUE"]].tolist(),
    }

    # Figura: paro proyectado vs observado (provincias con paro < 8.5)
    fig, ax = plt.subplots(figsize=(9, 4))
    provs = list(lowp.index[:4])
    cols = [C1, C2, C3, C4]
    for c, pr in zip(cols, provs):
        o = d[(d["Provincia"] == pr) & (d["Trimestre"] >= "2019-01-01")].set_index("Trimestre")["Tasa_Paro"]
        f = pv[pv["provincia"] == pr].set_index(pd.to_datetime(pv[pv["provincia"] == pr]["trimestre"]))["Tasa_Paro"]
        f = f[f.index >= "2026-01-01"]
        ax.plot(o.index, o.values, color=c, label=pr)
        ax.plot(f.index, f.values, color=c, ls="--")
    ax.axhline(8.5, color=INK2, lw=1, ls=":")
    ax.text(pd.Timestamp("2026-02-01"), 8.9, "suelo 'NAIRU' 8,5% aplicado provincia a provincia", color=INK2, fontsize=8)
    ax.set_title("Tasa de paro: observado (continuo) y proyección del TFM (discontinuo)")
    ax.set_ylabel("%")
    ax.legend(frameon=False, fontsize=8, ncol=4)
    fig.tight_layout()
    fig.savefig(OUT / "fig_04_paro_suelo_nairu.png", dpi=130)
    plt.close(fig)
    return tab


# ----------------------------------------------------------------------------
# 4. Indicadores de negocio
# ----------------------------------------------------------------------------
def cuota(principal, tipo_anual, anios=25):
    i = tipo_anual / 100 / 12
    n = anios * 12
    return principal * i / (1 - (1 + i) ** -n) if i > 0 else principal / n


def business_indicators(d: pd.DataFrame) -> pd.DataFrame:
    t = d["Trimestre"].max()
    last = d[d["Trimestre"] == t].set_index("Provincia")
    pib24 = d[d["Trimestre"] == "2024-10-01"].set_index("Provincia")["PIB_pc"]
    y25 = d[d["Trimestre"].dt.year == 2025]
    y24 = d[d["Trimestre"].dt.year == 2024]
    h25 = y25.groupby("Provincia")["Hipotecas_Total"].sum()
    c25 = y25.groupby("Provincia")["Transmisiones_Total"].sum()
    pop = y25.groupby("Provincia")["Poblacion"].mean()
    p24 = y24.groupby("Provincia")["Precio_m2"].mean()
    p25 = y25.groupby("Provincia")["Precio_m2"].mean()
    tipo = float(last["Euribor"].iloc[0] + last["Spread_Hipotecas"].iloc[0])  # TAE media (APRC) 2025T4
    precio90 = 90 * last["Precio_m2"]
    prestamo = 0.8 * precio90
    c = prestamo.apply(lambda x: cuota(x, tipo)) * 12
    c_st = prestamo.apply(lambda x: cuota(x, tipo + 2)) * 12
    ind = pd.DataFrame({
        "Precio_m2_2025T4": last["Precio_m2"].round(0),
        "Precio_90m2_EUR": precio90.round(0),
        "PIB_pc_2024_EUR": pib24,
        "Anios_PIBpc_para_90m2": (precio90 / pib24).round(2),
        "Entrada_20%_en_anios_PIBpc": (0.2 * precio90 / pib24).round(2),
        "Cuota_anual_80LTV_25a_EUR": c.round(0),
        "Cuota/PIBpc_%": (c / pib24 * 100).round(1),
        "Cuota/PIBpc_%_tipo+2pp": (c_st / pib24 * 100).round(1),
        "Hipotecas_por_1000hab_2025": (h25 / pop * 1000).round(2),
        "Hipotecas/compraventas_2025": (h25 / c25).round(2),
        "Var_precio_2025_vs_2024_%": ((p25 / p24 - 1) * 100).round(1),
        "Paro_2025T4": last["Tasa_Paro"],
    }).sort_values("Anios_PIBpc_para_90m2", ascending=False)
    ind.to_csv(OUT / "indicadores_negocio_provinciales.csv")
    RES["indicadores_negocio"] = {
        "tipo_APRC_2025T4_usado_%": round(tipo, 3),
        "top5_menos_accesibles": ind["Anios_PIBpc_para_90m2"].head(5).to_dict(),
        "top5_mas_accesibles": ind["Anios_PIBpc_para_90m2"].tail(5).to_dict(),
        "mediana_anios": float(ind["Anios_PIBpc_para_90m2"].median()),
        "corr_hip_x1000_vs_anios": round(float(ind["Hipotecas_por_1000hab_2025"].corr(ind["Anios_PIBpc_para_90m2"])), 2),
    }
    # Figura ranking
    s = ind["Anios_PIBpc_para_90m2"].sort_values()
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.barh(s.index, s.values, color=C1, height=0.7)
    ax.axvline(s.median(), color=INK2, lw=1, ls=":")
    ax.set_xlabel("Años de PIB per cápita (2024) para pagar 90 m² al precio Tinsa 2025T4")
    ax.set_title("Accesibilidad provincial (proxy): precio de 90 m² / PIB per cápita")
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_05_accesibilidad_provincial.png", dpi=130)
    plt.close(fig)
    return ind


def main():
    d = load_dataset()
    nat = national_panel(d)
    comp = target_quality(d, nat)
    n, tab = cycle_analysis(nat, comp)
    fig_cycle(n)
    specs = vecm_robustness(d, comp)
    fig_fevd(specs)
    projections(d)
    business_indicators(d)
    with open(OUT / "resultados.json", "w") as f:
        json.dump(RES, f, ensure_ascii=False, indent=1, default=str)
    print(tab.to_string(index=False))
    print(json.dumps(RES, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
