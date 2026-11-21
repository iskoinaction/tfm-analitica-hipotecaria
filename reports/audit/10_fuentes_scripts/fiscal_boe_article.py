"""Imprime la versión vigente (y fechas de todas las versiones) de los artículos de un texto consolidado del BOE
cuyo título case con una regex, o cuyo texto contenga una cadena.
Uso: python -I fiscal_boe_article.py BOE-ID "regex_titulo" ["texto_contiene"] [maxchars]
"""
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import get  # noqa: E402

bid, pat = sys.argv[1], sys.argv[2]
contains = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
maxc = int(sys.argv[4]) if len(sys.argv) > 4 else 2500
r = get(f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{bid}/texto", as_json=False,
        headers={"Accept": "application/xml"})
root = ET.fromstring(r.content)
for b in root.iter("bloque"):
    t = b.get("titulo") or ""
    vs = b.findall("version")
    if not vs:
        continue
    cur = vs[-1]
    txt = " ".join(x.strip() for x in cur.itertext() if x.strip())  # incluye celdas de tablas (tarifas)
    if re.search(pat, t) and (contains is None or contains.lower() in txt.lower()):
        hist = [(v.get("fecha_vigencia"), v.get("id_norma")) for v in vs]
        print(f"=== {t} | versiones: {hist}")
        print(txt[:maxc])
