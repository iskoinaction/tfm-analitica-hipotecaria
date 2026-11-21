"""Hipotecas_Total: parseo numérico (limpiar_numero), agregación mensual->trimestral
y contraste con la fuente oficial INE (tabla 3200, H - Estadística de Hipotecas,
series 'Total fincas. Número de hipotecas' por provincia, API Tempus3).

Hallazgo que se cuantifica: el CSV fuente guarda los miles con punto y SIN ceros
finales (p.ej. '1.07' = 1.070), porque se pasó por float. limpiar_numero solo
reconoce miles si hay exactamente 3 dígitos tras el punto, así que '1.07' -> 1,07.
"""
import sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *  # noqa
import requests

ns = load_nb_functions()
CACHE = OUT / "cache" / "ine_3200_numero.json"
if not CACHE.exists():
    r = requests.get("https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/3200?nult=260", timeout=300)
    sel = [s for s in r.json() if s["Nombre"].startswith(("Total fincas. Número de hipotecas.", "Viviendas. Número de hipotecas."))]
    json.dump(sel, open(CACHE, "w"))
sel = json.load(open(CACHE))
ine = []
for s in sel:
    parts = s["Nombre"].split(". ")
    for o in s["Data"]:
        ine.append(dict(concepto=parts[0], area=parts[2], anyo=o["Anyo"], mes=o["FK_Periodo"], ine=o["Valor"]))
ine = pd.DataFrame(ine)
ine["Periodo"] = ine.anyo.astype(str) + "M" + ine.mes.astype(int).map("{:02d}".format)

src = pd.read_csv(SRC_DIR / "hipotecas_por_prov_men.csv", sep=";", dtype=str)
src["nb_val"] = src.Total.map(ns["limpiar_numero"])
frac = src.Total.str.extract(r"\.(\d+)$")[0]
src["patron"] = np.select([frac.isna(), frac == "0", frac.str.len() == 3], ["entero", "x.0", "x.ddd"], "x.d/x.dd (miles truncados)")
print("Patrones de 'Total' en hipotecas_por_prov_men.csv:")
print(src.patron.value_counts().to_string())

tf = ine[ine.concepto == "Total fincas"].copy()
tf["code"] = tf.area.map(lambda a: None if a == "Total Nacional" else true_province_code(a))
src["code"] = src.Provincias.map(true_province_code)
m = src.merge(tf[tf.code.notna()][["code", "Periodo", "ine"]], on=["code", "Periodo"], how="left")
print("\nCobertura del cruce con INE:", m.ine.notna().sum(), "/", len(m))
m["err_nb"] = m.nb_val - m.ine
m["ok_nb"] = np.isclose(m.nb_val, m.ine)
print("\nCoincidencia valor notebook vs INE por patrón:")
print(m.groupby("patron").ok_nb.agg(["size", "sum"]).rename(columns={"size": "n", "sum": "coinciden"}).to_string())
bad = m[~m.ok_nb & m.ine.notna()]
print(f"\nValores mensuales erróneos tras limpiar_numero: {len(bad)} de {len(m)} ({len(bad)/len(m):.1%})")
print("Ejemplos:"); print(bad[["Provincias", "Periodo", "Total", "nb_val", "ine"]].head(12).to_string(index=False))
# ¿Coinciden los x.0 con INE? (ambigüedad x.0 = x  o  x.000)
x0 = m[m.patron == "x.0"]
print("\n'x.0' que en realidad son miles exactos (INE = 1000*x):", int(np.isclose(x0.nb_val * 1000, x0.ine).sum()))
# Corrección: miles truncados -> *1000
m["fix"] = np.where(m.patron.isin(["x.d/x.dd (miles truncados)"]), m.Total.astype(float) * 1000, m.nb_val)
m["fix"] = np.where((m.patron == "x.0") & np.isclose(m.nb_val * 1000, m.ine), m.nb_val * 1000, m.fix)
print("Tras corrección (x.d/x.dd*1000):", int(np.isclose(m.fix, m.ine).sum()), "/", m.ine.notna().sum(), "coinciden con INE")

# Agregación trimestral (el notebook SUMA meses -> correcto conceptualmente)
m["Trimestre"] = m.Periodo.map(ns["mensual_a_trimestral"])
q = m.groupby(["code", "Trimestre"]).agg(nb=("nb_val", "sum"), ine=("ine", "sum"), n_bad=("ok_nb", lambda s: (~s).sum())).reset_index()
ds = pd.read_csv(DATASET)
ds["code"] = ds.Provincia.map(lambda p: {v: k for k, v in LEGACY.items()}[p])
q = q.merge(ds[["code", "Trimestre", "Hipotecas_Total"]], on=["code", "Trimestre"], how="left")
print("\nDataset == suma trimestral del notebook reconstruida:", int(np.isclose(q.nb, q.Hipotecas_Total).sum()), "/", len(q))
q["rel_err"] = (q.Hipotecas_Total - q.ine) / q.ine
aff = q[~np.isclose(q.Hipotecas_Total, q.ine)]
print(f"Provincia-trimestres con Hipotecas_Total erróneo: {len(aff)} / {len(q)} ({len(aff)/len(q):.1%})")
print("Distribución del error relativo en los afectados:"); print(aff.rel_err.describe(percentiles=[.05, .25, .5, .75, .95]).to_string())
print("Afectados por provincia (top 15):")
print(aff.groupby("code").size().sort_values(ascending=False).head(15).rename(index=LEGACY).to_string())
aff_y = aff.assign(y=aff.Trimestre.str[:4]).groupby("y").size()
print("Afectados por año:"); print(aff_y.to_string())
q.to_csv(OUT / "03_hipotecas_trimestral_vs_ine.csv", index=False)

# Totales nacionales: suma de provincias (dataset) vs INE nacional total fincas / viviendas
nat = ine[ine.area == "Total Nacional"].pivot_table(index="Periodo", columns="concepto", values="ine")
nat["Trimestre"] = nat.index.map(ns["mensual_a_trimestral"])
natq = nat.groupby("Trimestre").sum()
dsn = ds.groupby("Trimestre").Hipotecas_Total.sum()
cmp = pd.DataFrame({"dataset_suma_prov": dsn, "INE_total_fincas": natq["Total fincas"], "INE_viviendas": natq["Viviendas"]}).dropna()
cmp["ratio_dataset/INE_fincas"] = cmp.dataset_suma_prov / cmp.INE_total_fincas
print("\nNacional trimestral (selección):")
print(cmp.loc[[t for t in cmp.index if t[5:7] == "01" and t[:4] in ("2005", "2007", "2008", "2013", "2019", "2023", "2024", "2025")]].round(3).to_string())
print("\nMedia mensual INE 2023-2024: total fincas %.0f ; viviendas %.0f" % (
    nat.loc[[p for p in nat.index if p[:4] in ("2023", "2024")], "Total fincas"].mean(),
    nat.loc[[p for p in nat.index if p[:4] in ("2023", "2024")], "Viviendas"].mean()))
print("Peor ratio dataset/INE (fincas):", cmp["ratio_dataset/INE_fincas"].min().round(3), "en", cmp["ratio_dataset/INE_fincas"].idxmin())
cmp.to_csv(OUT / "03_hipotecas_nacional_vs_ine.csv")
# Consistencia suma provincias INE = total nacional INE
sp = tf[tf.code.notna()].groupby("Periodo").ine.sum()
tn = tf[tf.code.isna()].set_index("Periodo").ine
print("INE: suma 52 provincias == total nacional en", int(np.isclose(sp, tn.reindex(sp.index)).sum()), "/", len(sp), "meses")
# Revisiones: fichero fuente vs INE hoy en valores no corrompidos
okp = m[m.patron.isin(["entero", "x.ddd"])]
print("Revisiones (patrones no ambiguos) fuente != INE actual:", int((~np.isclose(okp.nb_val, okp.ine)).sum()))

# Separar error de PARSEO (bug) de REVISIONES del INE (datos provisionales 2025)
q2 = m.groupby(["code", "Trimestre"]).agg(nb=("nb_val", "sum"), fix=("fix", "sum"),
                                           n_trunc=("patron", lambda s: (s == "x.d/x.dd (miles truncados)").sum())).reset_index()
q2["parse_err"] = q2.nb - q2.fix
pa = q2[~np.isclose(q2.parse_err, 0)]
print(f"\n[Solo bug de parseo] provincia-trimestres afectados: {len(pa)} / {len(q2)} ({len(pa)/len(q2):.1%}); "
      f"provincias afectadas: {pa.code.nunique()}")
print("  error relativo (nb/fix - 1):"); print((pa.nb / pa.fix - 1).describe(percentiles=[.05, .5, .95]).round(3).to_string())
print("  hipotecas 'perdidas' en total:", round(-pa.parse_err.sum()), "de", round(q2.fix.sum()),
      f"({-pa.parse_err.sum()/q2.fix.sum():.2%})")
print("  meses con miles truncados que el notebook leyó como <10:", int((m.patron == "x.d/x.dd (miles truncados)").sum()))
print("  afectados por año:", pa.Trimestre.str[:4].value_counts().sort_index().to_dict())
# revisiones
rv = m[m.patron.isin(["entero", "x.ddd", "x.0"]) & ~np.isclose(m.fix, m.ine)]
print("[Revisiones] meses donde fuente(parseo correcto) != INE actual:", len(rv), "; por año:", rv.Periodo.str[:4].value_counts().sort_index().to_dict())
