"""Comprueba que la API del BCE expone vintages (includeHistory=true) y deduce el retraso de publicación
de MIR (APRC hipotecas ES) y del Euribor mensual: primera validFromDate en que aparece cada periodo.
Uso: python -I ecb_vintages.py
"""
import re
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *
for key in ["MIR/M.ES.B.A2C.A.C.A.2250.EUR.N", "FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA"]:
    r = get(f"https://data-api.ecb.europa.eu/service/data/{key}", params={"startPeriod": "2025-01", "endPeriod": "2025-12", "includeHistory": "true"}, as_json=False)
    t = r.text
    first = {}
    vals = {}
    for ds in re.split(r"<message:DataSet ", t)[1:]:
        vf = re.search(r'validFromDate="([^"]+)"', ds).group(1)[:10]
        for p, v in re.findall(r'<generic:ObsDimension value="([^"]+)"/>\s*<generic:ObsValue value="([^"]+)"', ds):
            first.setdefault(p, vf)
            vals.setdefault(p, set()).add(v)
    print(key, "n_vintages(DataSets)=", t.count("<message:DataSet "))
    for p in sorted(first)[:12]:
        print("  ", p, "primera publicación:", first[p], "| valores distintos entre vintages:", sorted(vals[p]))
