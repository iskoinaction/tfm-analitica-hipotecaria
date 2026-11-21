#!/usr/bin/env python3
"""Comprueba (sin importar app.py) si los diccionarios hardcodeados de app.py casan con los
nombres de provincia del dataset: PROVINCE_TO_CCAA (vía _get_ccaa), PROV_SARIMA_DUMMY y PROV_ARIMA_DUMMY.
Uso: check_province_mappings.py <REPO_ROOT>"""
import ast, sys, os
import pandas as pd
root = sys.argv[1]
src = open(os.path.join(root, "Web", "app.py"), encoding="utf-8").read()
tree = ast.parse(src)
consts, funcs = {}, {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
        if name in {"PROVINCE_TO_CCAA", "PROV_SARIMA_DUMMY", "PROV_ARIMA_DUMMY", "ITP_POR_CCAA", "YOUNG_FINANCING"}:
            consts[name] = ast.literal_eval(node.value)
    if isinstance(node, ast.FunctionDef) and node.name == "_get_ccaa":
        funcs["_get_ccaa"] = ast.get_source_segment(src, node)
ns = {"PROVINCE_TO_CCAA": consts["PROVINCE_TO_CCAA"]}
exec(funcs["_get_ccaa"], ns)
df = pd.read_csv(os.path.join(root, "notebooks acabados", "dataset_final_tfm.csv"))
provs = sorted(df["Provincia"].unique())
res = {p: ns["_get_ccaa"](p) for p in provs}
missing = [p for p, c in res.items() if not c]
print(f"Provincias en dataset: {len(provs)}")
print(f"_get_ccaa sin CCAA (-> ITP por defecto 8%, sin financiación joven): {len(missing)}")
print("  ", missing)
wrong = {p: c for p, c in res.items() if c and p in ("Badajoz",)}
sar = consts["PROV_SARIMA_DUMMY"].keys(); ari = consts["PROV_ARIMA_DUMMY"]
print("PROV_SARIMA_DUMMY no presentes en dataset:", [p for p in sar if p not in provs])
print("PROV_ARIMA_DUMMY no presentes en dataset:", sorted(p for p in ari if p not in provs))
# coincidencias por subcadena peligrosas
amb = {p: c for p, c in res.items() if c and p not in consts["PROVINCE_TO_CCAA"]}
print("Resueltas por coincidencia difusa (subcadena):", amb)
