"""Compara Precio_m2 (Tinsa IMIE, panel v1) con MIVAU 'Valor tasado de la vivienda libre' (VDP006_01.csv)
y con INE IPV (índice, CCAA). No descarga nada de Tinsa: usa el CSV ya existente en 'Datos ya metidos'.
Descarga MIVAU: https://cdn.mivau.gob.es/portal-web-mivau/Datos_MIVAU/CSV/VDP006_01.csv (datos.gob.es e05233601).
Uso: python -I compare_tinsa_mivau.py
"""
import json
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *  # noqa: E402,F403

raw = SAMPLES / "raw_mivau" / "VDP006_01.csv.gz"
if not raw.exists():
    raw.parent.mkdir(exist_ok=True)
    r = get("https://cdn.mivau.gob.es/portal-web-mivau/Datos_MIVAU/CSV/VDP006_01.csv", as_json=False)
    import gzip; raw.write_bytes(gzip.compress(r.content))
v = pd.read_csv(raw, sep=";", dtype=str, encoding="utf-8-sig")
v = v[v["Régimen"] == "Libre"].copy()
v["Valor"] = pd.to_numeric(v["Valor"].str.replace(",", "."), errors="coerce")
UNI = {"Madrid, Comunidad de": "28", "Murcia, Region de": "30", "Navarra, Comunidad Foral de": "31",
       "Asturias, Principado de": "33"}
v["code"] = v["CPRO"].dropna().astype(int).map(lambda x: f"{x:02d}")
mask_uni = v["Provincia"].eq("Total CCAA") & v["Comunidad_Autónoma"].isin(UNI)
v.loc[mask_uni, "code"] = v.loc[mask_uni, "Comunidad_Autónoma"].map(UNI)
v = v[v.code.notna()]
OUT_PRE = {"mivau_ceros_o_vacios_libre": int((v["Valor"].fillna(0) <= 0).sum())}
v.loc[v["Valor"] <= 0, "Valor"] = np.nan  # MIVAU publica 0/vacío cuando no hay muestra suficiente
v = v.drop_duplicates(["code", "Año", "Trimestre"])
v["q"] = pd.to_datetime(v["Año"] + "-" + ((v["Trimestre"].astype(int) - 1) * 3 + 1).astype(str) + "-01")
mv = v[["code", "q", "Valor"]].rename(columns={"Valor": "mivau"})

p = load_panel()
p["code"] = p.Provincia.map(PANEL2CODE)
p["q"] = pd.to_datetime(p.Trimestre)
m = p[["code", "Provincia", "q", "Precio_m2"]].merge(mv, on=["code", "q"], how="left")
OUT = {**OUT_PRE, "mivau_codes_available": int(mv.code.nunique()), "mivau_last": str(mv.q.max().date()),
       "mivau_first": str(mv.q.min().date()),
       "panel_codes_without_mivau": sorted(set(p.code) - set(mv.code))}
rows = []
for code, d in m.dropna().groupby("code"):
    d = d.sort_values("q").set_index("q")
    yo_t = d.Precio_m2.pct_change(4)
    yo_m = d.mivau.pct_change(4)
    ok = yo_t.notna() & yo_m.notna()
    rows.append({
        "code": code, "provincia": d.Provincia.iloc[0], "n": len(d),
        "corr_niveles": round(float(d.Precio_m2.corr(d.mivau)), 3),
        "corr_yoy": round(float(yo_t[ok].corr(yo_m[ok])), 3),
        "ratio_tinsa_mivau_medio": round(float((d.Precio_m2 / d.mivau).mean()), 3),
        "tinsa_2025Q4": round(float(d.Precio_m2.iloc[-1]), 1), "mivau_2025Q4": float(d.mivau.iloc[-1]),
        "yoy_2025Q4_tinsa_%": round(float(yo_t.iloc[-1] * 100), 1), "yoy_2025Q4_mivau_%": round(float(yo_m.iloc[-1] * 100), 1),
    })
res = pd.DataFrame(rows).sort_values("corr_yoy")
OUT["resumen"] = {
    "n_provincias": int(len(res)),
    "corr_niveles_mediana": float(res.corr_niveles.median()), "corr_niveles_min": float(res.corr_niveles.min()),
    "corr_yoy_mediana": float(res.corr_yoy.median()), "corr_yoy_min": float(res.corr_yoy.min()),
    "ratio_medio_mediana": float(res.ratio_tinsa_mivau_medio.median()),
    "ratio_min": float(res.ratio_tinsa_mivau_medio.min()), "ratio_max": float(res.ratio_tinsa_mivau_medio.max()),
}
sel = res[res.code.isin(["28", "08", "46", "29", "41", "07", "50", "05", "44"])]
OUT["provincias_ejemplo"] = sel.to_dict("records")
OUT["peores_corr_yoy"] = res.head(5).to_dict("records")
res.to_csv(SAMPLES / "tinsa_vs_mivau_por_provincia.csv", index=False)

# INE IPV (CCAA, índice base 2015, vivienda libre general) vs media CCAA de Tinsa: solo correlación de tasas
tabs = get(f"{INE}/TABLAS_OPERACION/15")
OUT["ipv_tables"] = [(t["Id"], t["Nombre"]) for t in tabs][:12]
save_sample("compare_tinsa_mivau_summary.json", OUT)
print(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
