"""Compara Euribor, APRC y Spread del panel v1 con la API del BCE (data-api.ecb.europa.eu).
Uso: python -I compare_ecb.py
"""
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *  # noqa: E402,F403

OUT = {}
panel = load_panel()
nat = panel.groupby("Trimestre")[["Euribor", "Spread_Hipotecas"]].agg(["min", "max"])
OUT["panel_national_vars_unique_per_quarter"] = bool(
    ((nat["Euribor"]["max"] - nat["Euribor"]["min"]).abs().max() < 1e-12)
)
p = panel.groupby("Trimestre")[["Euribor", "Spread_Hipotecas"]].first().reset_index()
p["q"] = pd.to_datetime(p.Trimestre)

eq = ecb("FM/Q.U2.EUR.RT.MM.EURIBOR1YD_.HSTA", start="2003-01")
eq["q"] = pd.PeriodIndex(eq.TIME_PERIOD.str.replace("-", ""), freq="Q").to_timestamp()
em = ecb("FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA", start="2003-01")
em["q"] = pd.to_datetime(em.TIME_PERIOD).map(quarter_start)
em_q = em.groupby("q", as_index=False)["OBS_VALUE"].mean().rename(columns={"OBS_VALUE": "eur_m_avg"})
ap = ecb("MIR/M.ES.B.A2C.A.C.A.2250.EUR.N", start="2003-01")
ap["q"] = pd.to_datetime(ap.TIME_PERIOD).map(quarter_start)
ap_q = ap.groupby("q").agg(aprc=("OBS_VALUE", "mean"), n=("OBS_VALUE", "size")).reset_index()
fr = ecb("MIR/M.ES.B.A2C.F.R.A.2250.EUR.N", start="2003-01")
fr["q"] = pd.to_datetime(fr.TIME_PERIOD).map(quarter_start)
fr_q = fr.groupby("q", as_index=False)["OBS_VALUE"].mean().rename(columns={"OBS_VALUE": "aar_var_1y"})

m = (p.merge(eq[["q", "OBS_VALUE"]].rename(columns={"OBS_VALUE": "eur_q"}), on="q", how="left")
     .merge(em_q, on="q", how="left").merge(ap_q, on="q", how="left").merge(fr_q, on="q", how="left"))
m["spread_api"] = m.aprc - m.eur_q
m["spread_var_api"] = m.aar_var_1y - m.eur_q
mm = m.dropna(subset=["Euribor", "eur_q"])
OUT["euribor_vs_FM.Q_max_abs_diff"] = float((mm.Euribor - mm.eur_q).abs().max())
OUT["euribor_FM.Q_vs_mean_of_FM.M_max_abs_diff"] = float((mm.eur_q - mm.eur_m_avg).abs().max())
ms = m.dropna(subset=["Spread_Hipotecas", "spread_api"])
OUT["spread_vs_api_max_abs_diff"] = float((ms.Spread_Hipotecas - ms.spread_api).abs().max())
OUT["spread_api_quarters_with_<3_months"] = m.loc[m.n < 3, "Trimestre"].tolist()
OUT["spread_last_quarters"] = m[["Trimestre", "Euribor", "eur_q", "aprc", "Spread_Hipotecas", "spread_api",
                                  "aar_var_1y", "spread_var_api"]].tail(6).round(4).to_dict("records")
OUT["spread_min_panel"] = m.loc[m.Spread_Hipotecas.idxmin(), ["Trimestre", "Spread_Hipotecas"]].to_dict()
# Ficheros intermedios
eu_csv = pd.read_csv(ROOT / "Datos ya metidos" / "euribor_trim_fixed.csv")
eu_csv["q"] = pd.PeriodIndex(eu_csv.TIME_PERIOD.str.replace("-", ""), freq="Q").to_timestamp()
x = eu_csv.merge(eq[["q", "OBS_VALUE"]], on="q")
OUT["euribor_trim_fixed_csv_vs_api_max_abs_diff"] = float((x.EURIBOR_VALUE - x.OBS_VALUE).abs().max())
ap_csv = pd.read_csv(ROOT / "Datos sucios" / "APRC_hipotecas_nuevas_men.csv")
y = ap_csv.merge(ap[["TIME_PERIOD", "OBS_VALUE"]], on="TIME_PERIOD", suffixes=("_csv", "_api"))
OUT["aprc_monthly_csv_vs_api"] = {"n": int(len(y)), "max_abs_diff": float((y.OBS_VALUE_csv - y.OBS_VALUE_api).abs().max()),
                                  "n_diff>0.005": int(((y.OBS_VALUE_csv - y.OBS_VALUE_api).abs() > 0.005).sum())}
diffs = y[(y.OBS_VALUE_csv - y.OBS_VALUE_api).abs() > 0.005]
OUT["aprc_monthly_revised_points"] = diffs.head(10).to_dict("records")
OUT["aprc_api_first_last"] = [ap.TIME_PERIOD.min(), ap.TIME_PERIOD.max()]
OUT["euribor_api_last"] = [eq.TIME_PERIOD.max(), em.TIME_PERIOD.max()]
save_sample("ecb_euribor_aprc_quarterly.csv", m[["Trimestre", "eur_q", "eur_m_avg", "aprc", "aar_var_1y"]])
save_sample("compare_ecb_summary.json", OUT)
print(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
