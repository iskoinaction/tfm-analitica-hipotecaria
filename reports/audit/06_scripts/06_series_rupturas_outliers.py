"""Agregaciones, unidades, rupturas de serie, ceros/outliers y estacionalidad.
Secciones: A IPC, B Materiales/Mano de obra, C tasa_ahorro, D Poblacion, E Pob_Ext,
F PIB_pc, G Tasa_Paro (ruido EPA), H Precio_m2 (Tinsa), I ceros/negativos/outliers,
J NaN, K Ceuta/Melilla y duplicados.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *  # noqa

ns = load_nb_functions()
ds = pd.read_csv(DATASET)
ds["year"] = ds.Trimestre.str[:4].astype(int)
ds["qy"] = ds.Trimestre.str[5:7].map({"01": 1, "04": 2, "07": 3, "10": 4})
ds = ds.sort_values(["Provincia", "Trimestre"])
P = lambda v: ds.pivot(index="Trimestre", columns="Provincia", values=v)

print("=== A) IPC ===")
ipc = pd.read_csv(SRC_DIR / "ipc_ccaa_men.csv", sep=";", dtype=str)
print("Tipo de dato:", ipc["Tipo de dato"].unique().tolist(), "| Grupo:", ipc["Grupos ECOICOP ver.2"].unique().tolist())
ipc["v"] = ipc.Total.map(ns["limpiar_numero"]); ipc["T"] = ipc.Periodo.map(ns["mensual_a_trimestral"])
iq = ipc.groupby(["Comunidades y Ciudades Autónomas", "T"]).v.agg(["mean", "size"])
print("Meses por CCAA-trimestre:", iq["size"].value_counts().to_dict())
print("=> IPC del panel = media trimestral de TASAS INTERANUALES mensuales (no índice, no tasa trimestral)")
print("Rango IPC dataset:", ds.IPC.min(), ds.IPC.max())

print("\n=== B) Índices de materiales y mano de obra ===")
mat = pd.read_csv(SRC_DIR / "indice_precio_materiales_men.csv", sep=";", encoding="latin1", dtype=str)
mat.columns = [c.strip() for c in mat.columns]
mat["v"] = mat.Total.map(ns["limpiar_numero"])
area = [c for c in mat.columns if "rea" in c][0]
last = mat[mat.Periodo == "2024M12"].pivot(index="Materiales", columns=area, values="v")
print("Niveles 2024M12 por material y área (el notebook promedia las 14 series sin ponderar):")
print(last.round(1).to_string())
w = (last.stack() / last.stack().sum()).sort_values(ascending=False)
print("Peso implícito de cada serie en la media (proporcional a su nivel):"); print(w.round(3).to_string())
first = mat[mat.Periodo == "2005M01"].pivot(index="Materiales", columns=area, values="v")
print("Crecimiento 2005M01->2024M12 por serie:"); print((last / first - 1).round(2).to_string())
mat["T"] = mat.Periodo.map(ns["mensual_a_trimestral"])
rec = mat.groupby("T").v.mean()
dsm = ds.groupby("Trimestre").Indice_Materiales.first()
print("Reconstrucción == dataset:", int(np.isclose(rec.reindex(dsm.dropna().index), dsm.dropna()).sum()), "/", dsm.notna().sum())
print("Último mes en fuentes: materiales", mat.Periodo.max(), "| mano de obra",
      pd.read_csv(SRC_DIR / "indice_mano_obra_men.csv", sep=";", encoding="latin1", dtype=str).Periodo.max())

print("\n=== C) tasa_ahorro (nacional, trimestral) ===")
ta = ds.groupby("Trimestre").agg(t=("tasa_ahorro", "first"), q=("qy", "first"), y=("year", "first")).dropna()
print("Media por trimestre del año:", ta.groupby("q").t.mean().round(2).to_dict())
def eta2(y, g):
    return 1 - ((y - y.groupby(g).transform("mean")) ** 2).sum() / ((y - y.mean()) ** 2).sum()
print("Varianza explicada por el trimestre del año (eta²):", round(eta2(ta.t, ta.q), 3))
ta["ma4"] = ta.t.rolling(4).mean()
print("Desv. típ. serie original vs media móvil 4T:", round(ta.t.std(), 2), round(ta.ma4.std(), 2))
print("Autocorrelación lag1 / lag4 serie original:", round(ta.t.autocorr(1), 2), round(ta.t.autocorr(4), 2))
print("Primeros 8 valores:", ta.t.head(8).tolist())

print("\n=== D) Poblacion ===")
po = P("Poblacion").groupby(lambda t: t[:4]).first()
nat = po.sum(axis=1)
g = nat.pct_change()
print("Crecimiento nacional anual (%):", (g * 100).round(2).to_dict())
gp = po.pct_change()
print("Dispersión (desv. típ.) del crecimiento provincial por año (pp):", (gp.std(axis=1) * 100).round(2).to_dict())
src = pd.read_csv(SRC_DIR / "poblacion_por_prov_combinado.csv", sep=";", dtype=str)
src["blk"] = (src.index >= 52 * 17).astype(int)
print("Bloques del fichero combinado (años):", src.groupby("blk").Periodo.agg(["min", "max", "size"]).to_dict("index"))

print("\n=== E) Pob_Ext ===")
pe = P("Pob_Ext").groupby(lambda t: t[:4]).first()
ge = pe.sum(axis=1).pct_change() * 100
print("Crecimiento nacional anual Pob_Ext (%):", ge.round(1).to_dict())
r = (pe.loc["2023"] / pe.loc["2022"] - 1).sort_values()
print("Salto 2022->2023 por provincia: min/mediana/max %:", round(r.min() * 100, 1), round(r.median() * 100, 1), round(r.max() * 100, 1))
print("   mayores saltos:", (r.tail(5) * 100).round(1).to_dict())
share = (pe / po).loc[["2021", "2022", "2023"]].median(axis=1)
print("Mediana provincial % extranjeros 2021/2022/2023:", (share * 100).round(2).to_dict())

print("\n=== F) PIB_pc ===")
pb = P("PIB_pc").groupby(lambda t: t[:4]).first()
print("Años con dato:", pb.dropna(how="all").index.min(), "-", pb.dropna(how="all").index.max())
gpb = pb.pct_change() * 100
ccaa_map = {p.legacy_name: p.ccaa_code for p in geo.PROVINCES.values()}
within_ccaa = gpb.T.groupby(gpb.columns.map(ccaa_map)).std().mean()
print("Desv. típ. media del crecimiento de PIB_pc ENTRE provincias de una misma CCAA, por año (pp):")
print(within_ccaa.round(2).to_dict())
print("Crecimiento nacional medio (media simple prov.) por año (%):", gpb.mean(axis=1).round(2).to_dict())

print("\n=== G) Tasa_Paro (EPA provincial): ruido muestral ===")
tp = P("Tasa_Paro")
mad = tp.diff().abs().median()
pop = P("Poblacion").iloc[-5]
corr = np.corrcoef(np.log(pop[mad.index]), mad)[0, 1]
print("Mediana |Δ trimestral| (pp) por provincia: 5 menores pobl. vs 5 mayores")
o = pop.sort_values()
print("  pequeñas:", mad[o.index[:5]].round(2).to_dict()); print("  grandes:", mad[o.index[-5:]].round(2).to_dict())
print("  corr(log población, mediana|Δ|) =", round(corr, 3))
nq = tp.mean(axis=1).diff()
print("Δ media provincial en Q1 por año (pp):", {k[:4]: round(v, 2) for k, v in nq.items() if k[5:7] == "01" and k[:4] in ("2018", "2019", "2020", "2021", "2022", "2023")})

print("\n=== H) Precio_m2 (Tinsa) ===")
pr = np.log(P("Precio_m2")).diff()
ac = pr.apply(lambda s: s.autocorr(1))
print("Autocorrelación lag1 de la variación trimestral log(Precio_m2): mediana", round(ac.median(), 3),
      "| min", round(ac.min(), 3), "| max", round(ac.max(), 3))
print("  (precios de transacción sin suavizar suelen tener AC1 de Δ baja o negativa; AC1 alta => serie suavizada/medias móviles)")
print("Volatilidad Δlog (desv. típ.) Ceuta/Melilla vs mediana:", round(pr["Ceuta"].std(), 4), round(pr["Melilla"].std(), 4), round(pr.std().median(), 4))

print("\n=== I) Ceros, negativos y outliers (Δlog robusto por provincia) ===")
num = [c for c in ds.columns if c not in ("Provincia", "Trimestre", "year", "qy")]
zn = pd.DataFrame({"ceros": (ds[num] == 0).sum(), "negativos": (ds[num] < 0).sum(), "NaN": ds[num].isna().sum()})
print(zn.to_string())
outs = []
for v in ["Precio_m2", "Hipotecas_Total", "Transmisiones_Total", "Tasa_Paro"]:
    x = np.log(P(v).clip(lower=1e-9)).diff()
    z = (x - x.median()) / (1.4826 * (x - x.median()).abs().median())
    st = z.stack()
    st = st[st.abs() > 6]
    for (t, p), val in st.items():
        outs.append(dict(variable=v, Provincia=p, Trimestre=t, z=round(val, 1), valor=P(v).loc[t, p]))
outs = pd.DataFrame(outs)
outs.to_csv(OUT / "06_outliers.csv", index=False)
print("Nº de |z|>6 por variable:", outs.groupby("variable").size().to_dict())
print(outs.sort_values("z", key=abs, ascending=False).head(15).to_string(index=False))

print("\n=== K) Duplicados y Ceuta/Melilla ===")
print("Duplicados (Provincia,Trimestre):", int(ds.duplicated(["Provincia", "Trimestre"]).sum()))
cm = ds[ds.Provincia.isin(["Ceuta", "Melilla"])].groupby("Provincia")[["Hipotecas_Total", "Transmisiones_Total", "Precio_m2", "Tasa_Paro"]].agg(["min", "median", "max"])
print(cm.round(1).to_string())
same = (P("IPC")["Las Palmas"] == P("IPC")["Santa Cruz de Tenerife"]).mean()
print("Canarias: IPC idéntico Las Palmas vs S.C. Tenerife en", f"{same:.0%}", "de trimestres")
print("Ceuta vs Melilla IPC idéntico en", f"{(P('IPC')['Ceuta'] == P('IPC')['Melilla']).mean():.0%}")

print("\n=== F2) PIB_pc 2024: origen de los valores provinciales ===")
raw = pd.read_excel(DIRTY_DIR / "pib_pc_prov.xlsx", header=None)
hdr = raw.iloc[4]
c23 = [i for i, v in hdr.items() if str(v).startswith("2023")][0]
c24 = [i for i, v in hdr.items() if str(v).startswith("2024")][0]
print("Cabeceras de año en el XLSX INE:", str(hdr[c23]), str(hdr[c24]), "| título:", raw.iloc[0, 1])
rr = raw.iloc[6:, [1, c23, c24]].dropna(subset=[1]); rr.columns = ["nombre", "v23", "v24"]
print("Filas con dato 2024 en el XLSX INE:", int(rr.v24.notna().sum()), "(solo CCAA/total; provincias vacías)")
upp = rr[rr.nombre.str.isupper() & rr.v24.notna()].copy()
upp["g24_INE_CCAA_%"] = (upp.v24 / upp.v23 - 1) * 100
pib = pd.read_excel(SRC_DIR / "pib_pc_prov_an.xlsx")
w = pib.pivot(index="Provincia", columns="Periodo", values="Total")
gi = ((w[2024] / w[2023] - 1) * 100).rename("g24_imputado_%")
gi.index = [geo.PROVINCES[true_province_code(n)].ccaa_code for n in gi.index]
gi = gi.groupby(level=0).agg(["mean", "std"])
upp["ccaa"] = upp.nombre.map(lambda n: {"ANDALUCÍA": "01", "ARAGÓN": "02", "CASTILLA Y LEÓN": "07", "CASTILLA-LA MANCHA": "08",
                                         "CATALUÑA": "09", "COMUNITAT VALENCIANA": "10", "EXTREMADURA": "11", "GALICIA": "12",
                                         "PAÍS VASCO": "16", "CANARIAS": "05"}.get(n.strip()))
cmp = upp.dropna(subset=["ccaa"]).set_index("ccaa")[["nombre", "g24_INE_CCAA_%"]].join(gi)
print(cmp.round(3).to_string())
