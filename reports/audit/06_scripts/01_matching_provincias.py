"""Auditoría del fuzzy matching de provincias del notebook 3 (limpiar_provincia,
expandir_ccaa_a_prov, mapa_pob_ext).

1) Aplica las funciones LITERALES del notebook a los nombres de cada fuente tal y
   como el notebook los lee (mismo encoding) y los compara con la verdad terreno.
2) Prueba exhaustiva con variantes (oficial, cooficial, INE invertido, castellano
   antiguo, mayúsculas, prefijo de código, mojibake 1-3 capas, errores tipográficos).
3) Cobertura 52 provincias × periodos, duplicados y colisiones (dos nombres
   fuente distintos -> mismo destino, que el groupby().mean()/sum() fusionaría).
"""
import sys, itertools
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import *  # noqa

ns = load_nb_functions()
limpiar = ns["limpiar_provincia"]
canon = set(ns["provincias_limpias"])
legacy_to_code = {v: k for k, v in LEGACY.items()}

SOURCES = [  # (fichero, columna, encoding usado por el notebook, lector)
    ("tinsa_prov_precios_trim.csv", "Provincia", "utf-8", ","),
    ("hipotecas_por_prov_men.csv", "Provincias", "latin1", ";"),
    ("poblacion_por_prov_combinado.csv", "Provincias", "latin1", ";"),
    ("edad_media_provincias_an.csv", "Provincias", "latin1", ";"),
    ("epa_prov.csv", "Provincias", "latin1", ";"),
    ("pib_pc_prov_an.xlsx", "Provincia", None, None),
]
rows = []
for f, col, enc, sep in SOURCES:
    p = SRC_DIR / f
    d = pd.read_excel(p) if f.endswith("xlsx") else pd.read_csv(p, sep=sep, encoding=enc, engine="python", dtype=str)
    for name, n in d[col].value_counts(dropna=False).items():
        dest = limpiar(name)
        try:
            tc = true_province_code(name)
            truth = LEGACY[tc]
        except KeyError:
            truth = "??"
        rows.append(dict(fuente=f, nombre_leido=repr(name)[:60], n_filas=n, destino_nb=dest,
                         verdad=truth, ok=(dest == truth), destino_valido=dest in canon))
res = pd.DataFrame(rows)
res.to_csv(OUT / "01_matching_fuentes.csv", index=False)
print("=== 1) Asignaciones por fuente (nombres reales leídos por el notebook) ===")
for f, g in res.groupby("fuente"):
    col = g.groupby("destino_nb").size()
    print(f"{f}: nombres={len(g)} errores={int((~g.ok).sum())} destinos_distintos={g.destino_nb.nunique()} "
          f"colisiones={int((col > 1).sum())} no_canonicos={int((~g.destino_valido).sum())}")
    print(g[~g.ok].to_string(index=False) if (~g.ok).any() else "   (sin errores)")

# IPC: expandir_ccaa_a_prov
ipc = pd.read_csv(SRC_DIR / "ipc_ccaa_men.csv", sep=";", encoding="latin1", engine="python", dtype=str)
colc = [c for c in ipc.columns if "comunidad" in c.lower()][0]
print("\n=== IPC: CCAA -> provincias (expandir_ccaa_a_prov) ===")
bad = 0
for ccaa in ipc[colc].unique():
    out = ns["expandir_ccaa_a_prov"](pd.DataFrame({colc: [ccaa], "x": [1]}), col_ccaa=colc)
    provs = sorted(out["Provincia"])
    _k = geo.normalize(re.sub(r"^\d+\s+", "", demojibake(ccaa)))
    tcc = {"balearsilles": "04", "castillalamancha": "08"}.get(_k) or geo.ccaa_code(re.sub(r"^\d+\s+", "", demojibake(ccaa)))
    truth = sorted(LEGACY[c] for c in geo.provinces_of_ccaa(tcc))
    flag = "OK" if provs == truth else "ERROR"
    bad += flag != "OK"
    print(f"  {flag:5s} {demojibake(ccaa)!r:40s} -> {provs}")
print("errores IPC:", bad)

# 2) Prueba exhaustiva de variantes
print("\n=== 2) Prueba exhaustiva de variantes contra limpiar_provincia ===")
variants = {}
def add(v, code, kind):
    variants.setdefault((v, kind), code)
alt = {  # formas alternativas reales (INE, cooficiales, históricas, sin tildes)
    "01": ["Araba/Álava", "Araba", "Alava", "Álava", "ÁLAVA"], "03": ["Alicante/Alacant", "Alacant"],
    "07": ["Balears, Illes", "Illes Balears", "Baleares"], "12": ["Castellón/Castelló", "Castelló"],
    "15": ["Coruña, A", "La Coruña", "Coruña (A)", "A Coruña"], "17": ["Gerona", "Girona"],
    "20": ["Gipuzkoa", "Guipúzcoa", "Guipuzcoa"], "25": ["Lérida", "Lleida"], "26": ["Rioja, La", "La Rioja"],
    "28": ["Madrid", "Madrid, Comunidad de"], "30": ["Murcia", "Murcia, Región de"],
    "31": ["Navarra", "Navarra, Comunidad Foral de", "Nafarroa"], "32": ["Orense", "Ourense"],
    "33": ["Asturias", "Asturias, Principado de"], "35": ["Palmas, Las", "Las Palmas", "Palmas (Las)"],
    "38": ["Santa Cruz de Tenerife", "S.C. Tenerife", "Tenerife"], "46": ["Valencia/València", "València"],
    "48": ["Bizkaia", "Vizcaya"], "05": ["Avila", "ÁVILA"], "24": ["Leon", "LEÓN"], "23": ["Jaen", "JAÉN"],
    "29": ["Malaga", "MÁLAGA"], "10": ["Caceres", "CÁCERES"], "11": ["Cadiz", "CÁDIZ"], "14": ["Cordoba", "CÓRDOBA"],
    "04": ["Almeria"],
}
def moji(s, k):
    for _ in range(k):
        s = s.encode("utf-8").decode("latin-1")
    return s
for code, p in geo.PROVINCES.items():
    names = {p.name, p.legacy_name, *alt.get(code, [])}
    for n in names:
        add(n, code, "base"); add(n.upper(), code, "mayus"); add(f"{code} {n}", code, "prefijo_codigo")
        for k in (1, 2, 3):
            add(moji(n, k), code, f"mojibake_x{k}")
res2 = []
for (v, kind), code in variants.items():
    dest = limpiar(v)
    res2.append(dict(variante=v, tipo=kind, verdad=LEGACY[code], destino_nb=dest, ok=dest == LEGACY[code]))
r2 = pd.DataFrame(res2)
r2.to_csv(OUT / "01_matching_variantes.csv", index=False)
print(r2.groupby("tipo").ok.agg(["size", "sum"]).assign(errores=lambda x: x["size"] - x["sum"]))
print("\nErrores (variante -> destino_nb | verdad):")
for _, r in r2[~r2.ok].drop_duplicates(["variante"]).iterrows():
    print(f"  {r.variante!r:45s} [{r.tipo}] -> {r.destino_nb!r} | verdad {r.verdad!r}")

# Pruebas de robustez: nombres NO provinciales que deberían rechazarse
print("\n=== Nombres no provinciales / ruido (deberían NO asignarse) ===")
for v in ["Total Nacional", "Total", "Andalucía", "Castilla y León", "Cataluña", "Galicia", "Extremadura",
          "País Vasco", "Canarias", "Ceuta y Melilla", "Península y Baleares", "Otros", "No consta",
          "Extranjero", "Leganés", "Jaca", "Lena", "Cerdanyola", "Madridejos", "Valencia de Don Juan",
          "Alcalá de Henares", "Elche", "Vigo", "Gijón", "Cartagena", "Jerez", "Ponferrada", "Reus"]:
    print(f"  {v!r:28s} -> {limpiar(v)!r}")

# 3) Cobertura 52 x periodo + duplicados en fuentes provinciales (tras limpiar_provincia)
print("\n=== 3) Cobertura y duplicados por fuente tras el mapeo del notebook ===")
cover = []
for f, col, enc, sep in SOURCES:
    p = SRC_DIR / f
    d = pd.read_excel(p) if f.endswith("xlsx") else pd.read_csv(p, sep=sep, encoding=enc, engine="python", dtype=str)
    d["dest"] = d[col].map(limpiar)
    per = "Periodo" if "Periodo" in d.columns else "Trimestre"
    dup = d.duplicated(["dest", per]).sum()
    n_per = d[per].nunique()
    cnt = d.groupby(per)["dest"].nunique()
    cover.append(dict(fuente=f, periodos=n_per, prov_por_periodo_min=cnt.min(), prov_por_periodo_max=cnt.max(),
                      duplicados_prov_periodo=int(dup), destinos=d.dest.nunique()))
print(pd.DataFrame(cover).to_string(index=False))

# Pob_Ext: mapa exacto + drop_duplicates (keep first tras ordenar)
pe = pd.read_csv(SRC_DIR / "pob_ext_provincias_2005_2025.csv", sep=";", encoding="utf-8-sig")
print("\nPob_Ext fuente: filas", len(pe), "provincias", pe.provincia.nunique(), "años", pe["año"].nunique(),
      "duplicados (provincia,año):", int(pe.duplicated(["provincia", "año"]).sum()))
print("  nombres con <21 años:", pe.groupby("provincia").size().loc[lambda s: s != 21].to_dict())
