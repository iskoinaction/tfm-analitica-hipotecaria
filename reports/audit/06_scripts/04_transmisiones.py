"""Transmisiones_Total: trazabilidad y ruptura de fuente.
- notebook 3 lee 'transmision_prov_trim_tot.csv' (NO está en el repo); notebook 1 lo genera
  a partir de un CSV INE filtrado por 'Naturaleza de la finca == Total' (2007+) y del XLS
  MIVAU 'Número Total de Transacciones Inmobiliarias de Viviendas' (2005-2006).
- En el repo solo existe 'Datos ya metidos/transmision_propiedades_prov.csv' (INE ETDP,
  'Régimen y estado = Viviendas: Total', mensual 2007M01-2026M02).
Se comprueba qué serie contiene realmente el dataset y se mide el salto 2006Q4->2007Q1.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *  # noqa

ds = pd.read_csv(DATASET)
ds["code"] = ds.Provincia.map({v: k for k, v in LEGACY.items()})
t = pd.read_csv(SRC_DIR / "transmision_propiedades_prov.csv", sep=";", encoding="latin1", dtype=str)
print("Columnas fichero repo:", t.columns.tolist(), "| 'Régimen y estado':", t["Régimen y estado"].unique().tolist())
tp = t[t.Provincias.notna()].copy()
tp["code"] = tp.Provincias.map(true_province_code)
tp["v"] = tp.Total.str.replace(".", "", regex=False).astype(float)
tp["Trimestre"] = tp.Periodo.map(lambda p: f"{p[:4]}-{(int(p[5:])-1)//3*3+1:02d}-01")
q = tp.groupby(["code", "Trimestre"]).agg(v=("v", "sum"), n=("v", "size")).reset_index()
m = ds.merge(q, on=["code", "Trimestre"], how="left")
m = m[m.Trimestre >= "2007-01-01"]
eq = np.isclose(m.Transmisiones_Total, m.v)
print(f"Dataset 2007Q1-2025Q4 == suma trimestral 'Viviendas: Total' del fichero repo: {eq.sum()} / {len(m)}")
r = (m.Transmisiones_Total / m.v)
print("Ratio dataset/fichero repo: ", r.describe(percentiles=[.01, .5, .99]).round(4).to_dict())
print("Discrepancias por año:", m[~eq].Trimestre.str[:4].value_counts().sort_index().to_dict())
nat = ds.groupby("Trimestre").Transmisiones_Total.sum()
print("\nSerie nacional (suma provincias) alrededor del cambio de fuente MIVAU->INE:")
print(nat.loc["2005-01-01":"2008-10-01"].to_string())
yoy = nat.pct_change(4)
print("Variación interanual 2007Q1..Q4:", yoy.loc["2007-01-01":"2007-10-01"].round(3).to_dict())
# Estacionalidad/medida: ratio Q1 2007 (INE) vs Q1 2006 (MIVAU) por provincia
p = ds.pivot(index="Trimestre", columns="Provincia", values="Transmisiones_Total")
ratio = (p.loc["2007-01-01"] / p.loc["2006-01-01"]).sort_values()
print("\nRatio 2007Q1(INE)/2006Q1(MIVAU) por provincia: min/mediana/max",
      ratio.min().round(2), ratio.median().round(2), ratio.max().round(2))
print("  extremos:", ratio.head(4).round(2).to_dict(), ratio.tail(4).round(2).to_dict())
