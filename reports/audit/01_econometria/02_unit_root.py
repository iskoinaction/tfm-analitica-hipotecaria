"""Paso 2: orden de integración (ADF, DF-GLS, PP, KPSS, Zivot-Andrews).

Se analiza la versión original (nb 4.2, 2005Q1-2025Q4 con 2025 arrastrado) y la
auditada (2005Q1-2024Q4 sin imputaciones, medias ponderadas por población,
hipotecas desestacionalizadas por STL como sensibilidad).
"""
import warnings

import numpy as np
import pandas as pd
from arch.unitroot import ADF, DFGLS, KPSS, PhillipsPerron, ZivotAndrews

from common import OUT, build_clean, build_original, national_raw, seasonal_adjust

warnings.filterwarnings("ignore")
rows = []


def run(name, s, version):
    s = s.dropna()
    for d, lab in ((0, "nivel"), (1, "1ª dif")):
        x = s.diff().dropna() if d else s
        trends = ("c", "ct") if d == 0 else ("c",)
        for tr in trends:
            r = {"version": version, "serie": name, "transf": lab, "det": tr, "T": len(x)}
            a = ADF(x, trend=tr, method="aic", max_lags=8)
            r["ADF_aic_stat"], r["ADF_aic_p"], r["ADF_aic_lags"] = a.stat, a.pvalue, a.lags
            a = ADF(x, trend=tr, method="bic", max_lags=8)
            r["ADF_bic_stat"], r["ADF_bic_p"], r["ADF_bic_lags"] = a.stat, a.pvalue, a.lags
            g = DFGLS(x, trend=tr, method="aic", max_lags=8)
            r["DFGLS_stat"], r["DFGLS_p"] = g.stat, g.pvalue
            pp = PhillipsPerron(x, trend=tr)
            r["PP_stat"], r["PP_p"] = pp.stat, pp.pvalue
            k = KPSS(x, trend=tr)
            r["KPSS_stat"], r["KPSS_p"] = k.stat, k.pvalue
            if d == 0:
                for zt in ("c", "t", "ct"):
                    try:
                        z = ZivotAndrews(x, trend=zt, trim=0.15, max_lags=6 if len(x) > 60 else 3, method="aic")
                        r[f"ZA_{zt}_stat"], r[f"ZA_{zt}_p"] = z.stat, z.pvalue
                    except Exception:
                        r[f"ZA_{zt}_stat"], r[f"ZA_{zt}_p"] = np.nan, np.nan
                    # fecha de ruptura: arch no la expone de forma pública estable -> la buscamos
                    r[f"ZA_{zt}_break"] = za_break(x, zt)
            rows.append(r)


def za_break(x, zt):
    """Fecha de ruptura de Zivot-Andrews via statsmodels (devuelve índice de ruptura)."""
    from statsmodels.tsa.stattools import zivot_andrews
    try:
        out = zivot_andrews(np.asarray(x, float), trim=0.15, maxlag=6, regression=zt, autolag="AIC")
        return str(x.index[out[4]].date())
    except Exception as e:  # pragma: no cover
        return f"err {e}"


Yo = build_original()
for c in Yo.columns:
    run(c, Yo[c], "original_nb42")

Yc = build_clean(weighted=True, end="2024-10-01")
for c in Yc.columns:
    run(c, Yc[c], "auditada_2005-2024")
nac = national_raw()
hsa = seasonal_adjust(np.log(nac["Hipotecas"])).loc[:"2024-10-01"]
run("Log_Hipotecas_SA(STL)", hsa, "auditada_2005-2024")
run("Log_Transmisiones", np.log(nac["Transmisiones"]).loc[:"2024-10-01"], "auditada_2005-2024")
run("Spread", nac["Spread"].loc[:"2024-10-01"], "auditada_2005-2024")
run("Log_Mano_Obra", np.log(nac["Mano_Obra"]).loc[:"2024-10-01"], "auditada_2005-2024")

# Euribor y precio: sub-muestras
for lab, a, b in (("2005-2014", "2005-01-01", "2014-10-01"), ("2015-2024", "2015-01-01", "2024-10-01")):
    run(f"Euribor[{lab}]", nac["Euribor"].loc[a:b], "submuestra")
    run(f"Log_Precio_m2_pond[{lab}]", np.log(nac["Precio_pond"]).loc[a:b], "submuestra")

df = pd.DataFrame(rows)
df.to_csv(OUT / "02_unit_root.csv", index=False, float_format="%.4f")
pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_rows", 200)
cols = ["version", "serie", "transf", "det", "T", "ADF_aic_stat", "ADF_aic_p", "ADF_aic_lags", "ADF_bic_p",
        "DFGLS_p", "PP_p", "KPSS_stat", "KPSS_p"]
print(df[cols].round(3).to_string())
zcols = ["version", "serie", "ZA_c_stat", "ZA_c_p", "ZA_c_break", "ZA_t_p", "ZA_t_break", "ZA_ct_stat", "ZA_ct_p", "ZA_ct_break"]
print(df[df.transf == "nivel"].drop_duplicates(["version", "serie"])[zcols].round(3).to_string())
