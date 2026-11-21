"""Spread_Hipotecas = APRC (TAE, incluye comisiones) - Euribor 1A: ¿es un spread puro?
Descarga (y cachea) series BCE (data-api.ecb.europa.eu, MIR y FM):
  APRC   MIR.M.ES.B.A2C.A.C.A.2250.EUR.N  (TAE, vivienda, nuevas operaciones)
  NDER   MIR.M.ES.B.A2C.A.R.A.2250.EUR.N  (TEDR: tipo sin comisiones)
  F      MIR.M.ES.B.A2C.F.R.A.2250.EUR.N  (variable / fijación <=1 año)
  K      MIR.M.ES.B.A2C.K.R.A.2250.EUR.N  (fijación > 1 año)
  E1Y_M  FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA ; E1Y_Q FM.Q.U2.EUR.RT.MM.EURIBOR1YD_.HSTA
Descomposición: APRC - Euribor = (APRC - NDER) [comisiones/gastos]
                                + (NDER - Euribor) [margen + prima de plazo por mezcla fijo/variable]
Cuota implícita de tipo variable w: NDER = w*F + (1-w)*K  =>  w = (K - NDER)/(K - F).
"""
import sys, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *  # noqa
import requests

KEYS = {"APRC": "MIR/M.ES.B.A2C.A.C.A.2250.EUR.N", "NDER": "MIR/M.ES.B.A2C.A.R.A.2250.EUR.N",
        "F": "MIR/M.ES.B.A2C.F.R.A.2250.EUR.N", "K": "MIR/M.ES.B.A2C.K.R.A.2250.EUR.N",
        "E1Y_M": "FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA", "E1Y_Q": "FM/Q.U2.EUR.RT.MM.EURIBOR1YD_.HSTA"}
ser = {}
for k, key in KEYS.items():
    c = OUT / "cache" / f"ecb_{k}.csv"
    if not c.exists():
        r = requests.get(f"https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata&startPeriod=2003-01", timeout=60)
        r.raise_for_status()
        pd.read_csv(io.StringIO(r.text))[["TIME_PERIOD", "OBS_VALUE"]].to_csv(c, index=False)
    ser[k] = pd.read_csv(c).set_index("TIME_PERIOD").OBS_VALUE
mon = pd.DataFrame({k: ser[k] for k in ["APRC", "NDER", "F", "K", "E1Y_M"]})
mon.index = pd.PeriodIndex(mon.index, freq="M")
q = mon.groupby(mon.index.asfreq("Q")).mean()
q["E1Y_Q"] = pd.Series(ser["E1Y_Q"].values, index=pd.PeriodIndex(ser["E1Y_Q"].index.str.replace("-", ""), freq="Q"))
q.index = q.index.to_timestamp().strftime("%Y-%m-%d")

# 1) Reproducción del fichero fuente y del dataset
sp = pd.read_csv(SRC_DIR / "spread_hipotecas_trim.csv").set_index("Fecha").Diferencia
eu = pd.read_csv(SRC_DIR / "euribor_trim_fixed.csv")
eu.index = eu.TIME_PERIOD.map(lambda s: f"{s[:4]}-{(int(s[-1])-1)*3+1:02d}-01")
cmp = pd.DataFrame({"spread_fichero": sp, "aprc_q_menos_e1y_q": q.APRC - q.E1Y_Q, "euribor_fichero": eu.EURIBOR_VALUE,
                    "E1Y_Q": q.E1Y_Q, "E1Y_media_mensual": q.E1Y_M}).dropna()
print("Fichero spread reproducido (APRC trimestral media - Euribor FM.Q):",
      f"max|dif| = {(cmp.spread_fichero - cmp.aprc_q_menos_e1y_q).abs().max():.4f} pp (revisiones BCE incluidas)")
print("Euribor fichero vs BCE FM.Q: max|dif| =", round((cmp.euribor_fichero - cmp.E1Y_Q).abs().max(), 4),
      "; FM.Q vs media de 3 meses FM.M: max|dif| =", round((cmp.E1Y_Q - cmp.E1Y_media_mensual).abs().max(), 4))

# 2) Descomposición
q["spread_tfm"] = q.APRC - q.E1Y_Q
q["comisiones"] = q.APRC - q.NDER
q["NDER_menos_E"] = q.NDER - q.E1Y_Q
q["F_menos_E"] = q.F - q.E1Y_Q
q["w_variable"] = ((q.K - q.NDER) / (q.K - q.F)).where((q.K - q.F).abs() > 0.25)
q = q[(q.index >= "2005-01-01") & (q.index < "2026-01-01")]
q["year"] = q.index.str[:4]
ann = q.groupby("year")[["APRC", "NDER", "F", "K", "E1Y_Q", "spread_tfm", "comisiones", "NDER_menos_E", "F_menos_E", "w_variable"]].mean()
print("\nMedias anuales (pp):"); print(ann.round(2).to_string())
q.to_csv(OUT / "05_spread_descomposicion_trimestral.csv")
tot = q[["spread_tfm", "comisiones", "NDER_menos_E", "F_menos_E"]].describe().round(3)
print("\nResumen 2005Q1-2025Q4:"); print(tot.to_string())
print("Peso de comisiones en el 'spread' (media de comisiones / media spread):",
      round(q.comisiones.mean() / q.spread_tfm.mean(), 3))
print("Correlación spread_tfm con Euribor:", round(q.spread_tfm.corr(q.E1Y_Q), 3),
      "| (F-Euribor) con Euribor:", round(q.F_menos_E.corr(q.E1Y_Q), 3))
print("Trimestres con spread_tfm < 0:", int((q.spread_tfm < 0).sum()), "| con F-Euribor < 0:", int((q.F_menos_E < 0).sum()))
# Acoplamiento mecánico: Spread = APRC - Euribor => regresar Spread sobre Euribor tiene
# un componente -1 por construcción.
import statsmodels.api as sm
ds = pd.read_csv(DATASET).groupby("Trimestre")[["Spread_Hipotecas", "Euribor"]].first()
r = sm.OLS(ds.Spread_Hipotecas, sm.add_constant(ds.Euribor)).fit()
r_aprc = sm.OLS(ds.Spread_Hipotecas + ds.Euribor, sm.add_constant(ds.Euribor)).fit()
print(f"\nNacional (84 trimestres): Spread ~ Euribor: pendiente={r.params.Euribor:.3f}, R²={r.rsquared:.3f}; "
      f"APRC ~ Euribor: pendiente={r_aprc.params.Euribor:.3f}, R²={r_aprc.rsquared:.3f}")
print("  => pendiente(Spread) = pendiente(APRC) - 1 por identidad:", round(r_aprc.params.Euribor - 1, 3))
