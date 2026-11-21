"""Compara las variables INE del panel v1 (dataset_final_tfm.csv) con la API Tempus3 del INE.

Para cada variable reconstruye la transformación que hizo el notebook (o la conceptualmente correcta)
y calcula diferencias (máx. abs., % de celdas coincidentes). Escribe samples/compare_ine_summary.json.
Uso: python -I compare_ine.py   (desde este directorio; tarda ~2-4 min)
"""
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *  # noqa: E402,F403

panel = load_panel()
panel["code"] = panel["Provincia"].map(PANEL2CODE)
panel["q"] = pd.to_datetime(panel["Trimestre"])
assert panel["code"].notna().all()
OUT = {}


def compare(name, api, col, tol=1e-6, rel=False):
    """api: DataFrame con code, q, val."""
    m = panel[["code", "q", col]].merge(api, on=["code", "q"], how="left")
    m = m.dropna(subset=[col, "val"])
    diff = (m[col] - m["val"]).abs()
    if rel:
        diff = diff / m["val"].abs().replace(0, float("nan"))
    res = {
        "n_compared": int(len(m)),
        "pct_equal(tol=%g%s)" % (tol, ",rel" if rel else ""): round(float((diff <= tol).mean() * 100), 2) if len(m) else None,
        "max_abs_diff": float((m[col] - m["val"]).abs().max()) if len(m) else None,
        "mean_abs_diff": float((m[col] - m["val"]).abs().mean()) if len(m) else None,
    }
    worst = m.assign(d=(m[col] - m["val"]).abs()).sort_values("d", ascending=False).head(5)
    res["worst"] = [
        {"code": r.code, "q": str(r.q.date()), "panel": float(r[col]), "api": float(r.val)} for _, r in worst.iterrows()
    ]
    OUT[name] = res
    print(f"\n### {name}\n", json.dumps(res, ensure_ascii=False, indent=1))
    return m


def by_prov(df):
    df = df.copy()
    df["code"] = df["nombre"].map(prov_code_from_ine_name)
    return df[df["code"].notna()]


# ---------------- Tasa de paro EPA (65349) -----------------
t = ine_table(65349, nult=120)
t = t[t.nombre.str.startswith("Tasa de paro") & t.nombre.str.contains("Ambos sexos")]
t = by_prov(t)
t = t[~t.nombre.str.contains("Total Nacional")]
api = t.assign(q=pd.to_datetime(t.fecha).map(quarter_start), val=t.valor)[["code", "q", "val"]]
api = api.drop_duplicates(["code", "q"])
compare("Tasa_Paro vs INE 65349 (EPA, tasa de paro, ambos sexos)", api, "Tasa_Paro", tol=0.005)
save_sample("epa_65349_tasa_paro_madrid.csv", api[api.code == "28"].sort_values("q"))

# ---------------- Hipotecas (3200 = 76317) -----------------
h = ine_table(3200, nult=280)
h = h[h.nombre.str.startswith("Total fincas. Número de hipotecas")]
h = by_prov(h)
h["q"] = pd.to_datetime(h.fecha).map(quarter_start)
OUT["hipotecas_series_variants"] = sorted(h.nombre.str.replace(r"^Total fincas\. Número de hipotecas\. [^.]+\. ", "", regex=True).unique().tolist())
for variant in OUT["hipotecas_series_variants"]:
    hv = h[h.nombre.str.endswith(variant)]
    api = hv.groupby(["code", "q"], as_index=False)["valor"].sum().rename(columns={"valor": "val"})
    nm = hv.groupby(["code", "q"]).size().rename("n").reset_index()
    api = api.merge(nm, on=["code", "q"])
    api = api[api.n == 3][["code", "q", "val"]]
    compare(f"Hipotecas_Total vs INE 3200 suma trimestral ({variant})", api, "Hipotecas_Total", tol=0.5)

# viviendas (para concepto)
hv = h  # placeholder
hviv = ine_table(3200, nult=3)
OUT["hipotecas_naturalezas"] = sorted(hviv.nombre.str.split(". ").str[0].unique().tolist())

# ---------------- Transmisiones / compraventas (6150 viviendas, 6146 fincas) -----------------
for tab, pref, label in [(6150, "General. Compraventa. Número", "compraventa viviendas (6150, General)"),
                         (6146, "Número", "total fincas transmitidas (6146)")]:
    tt = ine_table(tab, nult=240)
    tt = by_prov(tt)
    if tab == 6150:
        tt = tt[tt.nombre.str.contains("General. Compraventa. Número")]
    else:
        tt = tt[tt.nombre.str.contains("Total fincas") & tt.nombre.str.startswith("Número")]
    tt["q"] = pd.to_datetime(tt.fecha).map(quarter_start)
    g = tt.groupby(["code", "q"]).agg(val=("valor", "sum"), n=("valor", "size")).reset_index()
    g = g[g.n == 3][["code", "q", "val"]]
    compare(f"Transmisiones_Total vs INE {label}", g, "Transmisiones_Total", tol=0.5)
    if tab == 6150:
        OUT["etdp_6150_example_names"] = tt.nombre.drop_duplicates().head(3).tolist()

# ---------------- IPC CCAA variación anual (50913 base 2021) -----------------
CCAA2PROV = {
    "Andalucía": ["04", "11", "14", "18", "21", "23", "29", "41"], "Aragón": ["22", "44", "50"],
    "Asturias, Principado de": ["33"], "Balears, Illes": ["07"], "Canarias": ["35", "38"], "Cantabria": ["39"],
    "Castilla y León": ["05", "09", "24", "34", "37", "40", "42", "47", "49"],
    "Castilla - La Mancha": ["02", "13", "16", "19", "45"], "Cataluña": ["08", "17", "25", "43"],
    "Comunitat Valenciana": ["03", "12", "46"], "Extremadura": ["06", "10"], "Galicia": ["15", "27", "32", "36"],
    "Madrid, Comunidad de": ["28"], "Murcia, Región de": ["30"], "Navarra, Comunidad Foral de": ["31"],
    "País Vasco": ["01", "20", "48"], "Rioja, La": ["26"], "Ceuta": ["51"], "Melilla": ["52"],
}
for tab in (50913, 76136):
    ip = ine_table(tab, nult=260)
    ip = ip[ip.nombre.str.contains(r"\. Índice general\. Variación anual", regex=True)]
    ip["ccaa"] = ip.nombre.str.split(". ").str[0].str.strip()
    ip["q"] = pd.to_datetime(ip.fecha).map(quarter_start)
    g = ip.groupby(["ccaa", "q"], as_index=False)["valor"].mean()
    rows = []
    for _, r in g.iterrows():
        for c in CCAA2PROV.get(r.ccaa, []):
            rows.append({"code": c, "q": r.q, "val": r.valor})
    api = pd.DataFrame(rows)
    OUT[f"ipc_{tab}_ccaa_unmatched"] = sorted(set(g.ccaa) - set(CCAA2PROV))
    compare(f"IPC vs INE {tab} (media trimestral de la variación anual del índice general, CCAA)", api, "IPC", tol=1e-6)

# ---------------- Mano de obra (8377) y materiales (8378) -----------------
mo = ine_table(8377, nult=300)
mo["q"] = pd.to_datetime(mo.fecha).map(quarter_start)
g = mo.groupby("q", as_index=False)["valor"].mean()
api = pd.DataFrame([{"code": c, "q": r.q, "val": r.valor} for _, r in g.iterrows() for c in PROV])
compare("Indice_Mano_Obra vs INE 8377 (media trimestral, base jul-1980)", api, "Indice_Mano_Obra", tol=1e-6)
OUT["8377_last_date"] = str(mo.fecha.max())

ma = ine_table(8378, nult=300)
OUT["8378_series"] = ma.nombre.drop_duplicates().tolist()
ma["q"] = pd.to_datetime(ma.fecha).map(quarter_start)
g = ma.groupby("q", as_index=False)["valor"].mean()
api = pd.DataFrame([{"code": c, "q": r.q, "val": r.valor} for _, r in g.iterrows() for c in PROV])
compare("Indice_Materiales vs INE 8378 (media de TODAS las series y zonas, como el notebook)", api, "Indice_Materiales", tol=1e-6)
OUT["8378_last_date"] = str(ma.fecha.max())

# ---------------- Edad media (3199) -----------------
em = ine_table(3199, nult=30)
em = em[em.nombre.str.contains("Edad media de la población. Total")]
em = by_prov(em)
em["year"] = pd.to_datetime(em.fecha).dt.year
api = pd.DataFrame([{"code": r.code, "q": pd.Timestamp(year=r.year, month=m, day=1), "val": r.valor}
                    for _, r in em.iterrows() for m in (1, 4, 7, 10)])
compare("Edad_Media vs INE 3199 (anual, a 1 de enero, repetida 4 trimestres)", api, "Edad_Media", tol=0.005)

# ---------------- Población: 2852 (Padrón, <=2021) y ECP -----------------
pp = ine_table(2852, nult=30)
pp = pp[pp.nombre.str.contains(r"\. Total\. Total habitantes", regex=True)]
pp = by_prov(pp)
pp["year"] = pd.to_datetime(pp.fecha).dt.year
api = pd.DataFrame([{"code": r.code, "q": pd.Timestamp(year=r.year, month=m, day=1), "val": r.valor}
                    for _, r in pp.iterrows() for m in (1, 4, 7, 10)])
compare("Poblacion vs INE 2852 (Padrón, cifras oficiales a 1-ene, hasta 2021)", api, "Poblacion", tol=0.5)

# ECP: series provinciales total y extranjera (tabla 59591, todas las edades, ambos sexos)
ec = ine_table(59591, nult=1)
ec = ec[ec.nombre.str.contains("Todas las edades") & ec.nombre.str.contains(r"\. (Total|Extranjera)\. Total\. Población", regex=True)]
ec = by_prov(ec)
ec = ec[~ec.nombre.str.startswith("Total Nacional")]
ec["kind"] = ec.nombre.str.extract(r"Todas las edades\. (Total|Extranjera)\.")[0]
OUT["ecp_59591_n_series_selected"] = int(len(ec))
ecp_rows = []
for _, r in ec.iterrows():
    s, d = ine_series(r.cod, date="20020101:20261231")
    for _, o in d.iterrows():
        ecp_rows.append({"code": r.code, "kind": r.kind, "cod": r.cod, "fecha": o.fecha, "val": o.Valor})
ecp = pd.DataFrame(ecp_rows)
save_sample("ecp_59591_prov_total_extranjera.csv", ecp)
for kind, col in [("Total", "Poblacion"), ("Extranjera", "Pob_Ext")]:
    e = ecp[(ecp.kind == kind) & (pd.to_datetime(ecp.fecha).dt.month == 1)].copy()
    e["year"] = pd.to_datetime(e.fecha).dt.year
    api = pd.DataFrame([{"code": r.code, "q": pd.Timestamp(year=r.year, month=m, day=1), "val": r.val}
                        for _, r in e.iterrows() for m in (1, 4, 7, 10)])
    compare(f"{col} vs INE ECP 59591 ({kind}, a 1 de enero)", api, col, tol=0.5)
    # por año: concordancia
    mm = panel[["code", "q", col]].merge(api, on=["code", "q"]).dropna()
    mm["year"] = mm.q.dt.year
    OUT[f"{col}_vs_ECP_pct_equal_by_year"] = (mm.assign(eq=(mm[col] - mm.val).abs() <= 0.5)
                                              .groupby("year")["eq"].mean().round(3).to_dict())
    OUT[f"{col}_vs_ECP_median_reldiff_by_year_pct"] = (mm.assign(r=(mm[col] / mm.val - 1) * 100)
                                                       .groupby("year")["r"].median().round(3).to_dict())

# ---------------- PIB per cápita (CRE: 82285 y 80110) -----------------
for tab in (82285, 80110):
    pb = ine_table(tab, nult=30)
    pb = pb[pb.nombre.str.contains("Dato base")]
    pb = by_prov(pb)
    pb["year"] = pd.to_datetime(pb.fecha).dt.year
    api = pd.DataFrame([{"code": r.code, "q": pd.Timestamp(year=r.year, month=m, day=1), "val": r.valor}
                        for _, r in pb.iterrows() for m in (1, 4, 7, 10)])
    compare(f"PIB_pc vs INE CRE {tab} (PIB pm per cápita, precios corrientes)", api, "PIB_pc", tol=0.5)
    OUT[f"cre_{tab}_years"] = [int(pb.year.min()), int(pb.year.max())]

# ---------------- Tasa de ahorro hogares (62275: CTNFSI11271 NSA, CTNFSI11270 SA) -----------------
for cod, lab in [("CTNFSI11271", "no ajustada"), ("CTNFSI11270", "ajustada estac.")]:
    s, d = ine_series(cod, date="20050101:20261231")
    d["q"] = pd.to_datetime(d.fecha).map(quarter_start)
    api = pd.DataFrame([{"code": c, "q": r.q, "val": r.Valor} for _, r in d.iterrows() for c in PROV])
    compare(f"tasa_ahorro vs INE {cod} (tasa de ahorro hogares+ISFLSH, {lab})", api, "tasa_ahorro", tol=0.05)
    OUT[f"{cod}_last"] = str(d.fecha.max())

save_sample("compare_ine_summary.json", OUT)
print("\nOK -> samples/compare_ine_summary.json")
