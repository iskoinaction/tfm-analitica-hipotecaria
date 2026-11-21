"""Cuantifica el error de parseo de miles en Hipotecas_Total (valores '10.24' = 10.240 leídos como 10,24)."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
p = load_panel()
nonint = (p.Hipotecas_Total % 1).abs() > 1e-9
print("celdas panel Hipotecas_Total no enteras:", int(nonint.sum()), "de", len(p), f"({nonint.mean()*100:.1f}%)")
raw = pd.read_csv(ROOT / "Datos ya metidos" / "hipotecas_por_prov_men.csv", sep=";", dtype=str)
amb = raw.Total.str.match(r"^\d+\.\d{1,2}$") & ~raw.Total.str.endswith(".0")
print("valores brutos con 1-2 decimales distintos de '.0' (miles truncados):", int(amb.sum()))
h = ine_table(3200, nult=280)
h = h[h.nombre.str.startswith("Total fincas. Número de hipotecas")]
h["code"] = h.nombre.map(prov_code_from_ine_name); h = h[h.code.notna()].drop_duplicates(["code", "fecha"])
h["q"] = pd.to_datetime(h.fecha).map(quarter_start)
api = h.groupby(["code", "q"], as_index=False)["valor"].sum()
p["code"] = p.Provincia.map(PANEL2CODE); p["q"] = pd.to_datetime(p.Trimestre)
m = p.merge(api, on=["code", "q"])
m["rel"] = (m.Hipotecas_Total / m.valor - 1) * 100
bad = m[m.rel.abs() > 0.5]
print("celdas con |error| > 0.5%:", len(bad), "; error relativo mediano en esas celdas: %.1f%%" % bad.rel.median())
print("por provincia (top):", bad.groupby("Provincia").size().sort_values(ascending=False).head(8).to_dict())
print("ok enteros pero distintos (revisiones):", int(((~((m.Hipotecas_Total % 1).abs() > 1e-9)) & (m.rel.abs() > 0.5)).sum()))
save_sample("hipotecas_parse_errors.csv", bad[["Provincia", "Trimestre", "Hipotecas_Total", "valor", "rel"]].round(2))
