"""Comprobaciones complementarias: IPC CCAA, materiales (14 series), PIB_pc por año, ahorro y transmisiones por año."""
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
p = load_panel(); p["code"] = p.Provincia.map(PANEL2CODE); p["q"] = pd.to_datetime(p.Trimestre)

ip = ine_table(50913, nult=1)
print("IPC 50913 nombres CCAA:", ip[ip.nombre.str.contains("Índice general. Variación anual")].nombre.head(20).tolist()[:5])

ma = ine_table(8378, nult=300)
ma["q"] = pd.to_datetime(ma.fecha).map(quarter_start)
ma14 = ma[~ma.nombre.str.contains("Ligantes")]
g = ma14.groupby("q")["valor"].mean()
pm = p.groupby("q")["Indice_Materiales"].first()
x = pd.concat([pm, g], axis=1).dropna()
print("Materiales: panel vs media 14 series (sin Ligantes): max abs diff", float((x.iloc[:, 0] - x.iloc[:, 1]).abs().max()))
print("rango niveles series 8378 último mes:", ma[ma.fecha == ma.fecha.max()][["nombre", "valor"]].values.tolist())

for tab in (82285,):
    pb = ine_table(tab, nult=30); pb = pb[pb.nombre.str.contains("Dato base")]
    pb["code"] = pb.nombre.map(prov_code_from_ine_name); pb = pb[pb.code.notna()]
    pb["year"] = pd.to_datetime(pb.fecha).dt.year
    print("CRE", tab, "años con dato provincial:", sorted(pb.year.unique())[-4:], "nombre ej:", pb.nombre.iloc[0])
    pa = p[p.q.dt.month == 1].assign(year=lambda d: d.q.dt.year)
    m = pa.merge(pb, on=["code", "year"])
    m["eq"] = (m.PIB_pc - m.valor).abs() < 0.5
    print("PIB_pc % iguales por año:", m.groupby("year").eq.mean().round(2).to_dict())

s, d = ine_series("CTNFSI11271", date="20050101:20261231")
d["q"] = pd.to_datetime(d.fecha).map(quarter_start)
pa = p.groupby("q")["tasa_ahorro"].first()
x = pd.concat([pa, d.set_index("q").Valor], axis=1).dropna()
x.columns = ["panel", "api"]
diff = x[(x.panel - x.api).abs() > 0.05]
print("tasa_ahorro trimestres distintos:", [(str(i.date()), r.panel, r.api) for i, r in diff.iterrows()])

tt = ine_table(6150, nult=240)
tt["code"] = tt.nombre.map(prov_code_from_ine_name); tt = tt[tt.code.notna() & tt.nombre.str.contains("General. Compraventa. Número")]
tt["q"] = pd.to_datetime(tt.fecha).map(quarter_start)
g = tt.groupby(["code", "q"], as_index=False)["valor"].sum()
m = p.merge(g, on=["code", "q"])
m["eq"] = (m.Transmisiones_Total - m.valor).abs() < 0.5
print("Transmisiones vs 6150: % iguales por año:", m.groupby(m.q.dt.year).eq.mean().round(3).to_dict())
xl = pd.read_excel(ROOT / "Datos sucios" / "transmisiones propiedades 2005-2006.xls", header=None)
print("XLS 2005-2006 cabecera:", [str(v) for v in xl.iloc[:14, :3].values.ravel() if str(v) != "nan"][:20])
