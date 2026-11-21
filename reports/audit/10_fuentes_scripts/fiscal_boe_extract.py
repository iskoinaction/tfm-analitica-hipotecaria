"""Extrae de la legislación consolidada del BOE (API de datos abiertos) los preceptos con los tipos
generales de ITP (TPO, inmuebles) y AJD (documentos notariales) por CCAA, CON SU HISTORIAL DE VERSIONES
(cada <bloque> trae sus <version fecha_vigencia id_norma>), lo que permite construir una tabla de vigencias.

API: https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{ID}/texto   (Accept: application/xml)
Salidas: samples/fiscal_boe_versions.csv  (todas las versiones de los artículos relevantes)
         samples/fiscal_boe_snippets.txt  (lectura humana)
La interpretación jurídica final (qué tipo es "general") se hizo leyendo los fragmentos; ver 10_fuentes.md.
Uso: python -I fiscal_boe_extract.py
"""
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import *  # noqa: E402,F403

TEXTS = {
    "Andalucía": "BOE-A-2021-17915",            # Ley 5/2021 Tributos Cedidos
    "Aragón": "BOA-d-2005-90006",               # DLeg 1/2005
    "Asturias": "BOE-A-2015-945",               # DLeg 2/2014
    "Illes Balears": "BOE-A-2014-6925",         # DLeg 1/2014
    "Canarias": "BOC-j-2009-90008",             # DLeg 1/2009
    "Cantabria": "BOCT-c-2008-90028",           # DLeg 62/2008
    "Castilla y León": "BOCL-h-2013-90254",     # DLeg 1/2013
    "Cataluña": "BOE-A-2024-6951",              # DLeg 1/2024 libro sexto Código tributario
    "Comunitat Valenciana": "BOE-A-1998-8202",  # Ley 13/1997
    "Extremadura": "BOE-A-2018-8159",           # DLeg 1/2018
    "Galicia": "BOE-A-2011-18161",              # DLeg 1/2011
    "Madrid": "BOCM-m-2010-90068",              # DLeg 1/2010
    "Murcia": "BOE-A-2011-10542",               # DLeg 1/2010
    "La Rioja": "BOE-A-2017-13750",             # Ley 10/2017
    "Estatal (TRLITPAJD)": "BOE-A-1993-25359",  # RDLeg 1/1993 (Ceuta, Melilla y supletorio)
}
PAT_ITP = re.compile(r"(transmisi[oó]n(es)? de (bienes )?inmuebles|transmisi[oó]n de inmuebles|valor real del inmueble|"
                     r"tarifa|base liquidable)", re.I)
PAT_AJD = re.compile(r"(primeras copias de escrituras|documentos notariales)", re.I)
PAT_NUM = re.compile(r"\d+(,\d+)?\s*(por\s*(100|ciento)|%)", re.I)
PAT_GEN = re.compile(r"(con car[aá]cter general|tipo (de gravamen )?general|se aplicar[aá] (el|la) (tipo|tarifa)|"
                     r"siguiente (tarifa|escala)|cuota tributaria se obtendr[aá])", re.I)


def fetch_xml(boe_id):
    r = get(f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{boe_id}/texto",
            as_json=False, headers={"Accept": "application/xml"})
    return ET.fromstring(r.content)


rows = []
for ccaa, bid in TEXTS.items():
    try:
        root = fetch_xml(bid)
    except Exception as e:  # noqa: BLE001
        print("ERROR", ccaa, e)
        continue
    for bloque in root.iter("bloque"):
        titulo = bloque.get("titulo") or bloque.get("id")
        versions = bloque.findall("version")
        for k, ver in enumerate(versions):
            ptexts = ["".join(p.itertext()).strip() for p in ver.iter("p")]
            full = " ".join(ptexts)
            if not PAT_NUM.search(full):
                continue
            is_itp = bool(PAT_ITP.search(full)) and "transmisiones patrimoniales" in full.lower() or \
                bool(re.search(r"tipo de gravamen aplicable a inmuebles|transmisi[oó]n de (bienes )?inmuebles", full, re.I))
            is_ajd = bool(PAT_AJD.search(full))
            if not (is_itp or is_ajd) or not PAT_GEN.search(full):
                continue
            # sólo párrafos relevantes (para legibilidad)
            rel = [p for p in ptexts if PAT_NUM.search(p) and (PAT_GEN.search(p) or "tramo" in p.lower()
                                                               or re.search(r"^\s*(desde|entre|m[aá]s de|hasta)", p, re.I))]
            rows.append({
                "ccaa": ccaa, "boe_id": bid, "bloque": titulo, "id_norma_version": ver.get("id_norma"),
                "fecha_publicacion": ver.get("fecha_publicacion"), "fecha_vigencia": ver.get("fecha_vigencia"),
                "es_version_vigente": k == len(versions) - 1, "itp": is_itp, "ajd": is_ajd,
                "texto": " | ".join(rel)[:1500],
                "url": f"https://www.boe.es/buscar/act.php?id={bid}#{bloque.get('id')}",
            })
df = pd.DataFrame(rows)
df.to_csv(SAMPLES / "fiscal_boe_versions.csv", index=False)
with open(SAMPLES / "fiscal_boe_snippets.txt", "w", encoding="utf-8") as f:
    for ccaa, d in df.groupby("ccaa", sort=False):
        f.write(f"##### {ccaa} ({d.boe_id.iloc[0]})\n")
        for _, r in d[d.es_version_vigente].iterrows():
            f.write(f"  [{r.bloque} | vigente desde {r.fecha_vigencia} | {r.id_norma_version}] {r.texto[:900]}\n")
print(df.groupby("ccaa").agg(n=("bloque", "size"), vigentes=("es_version_vigente", "sum")))
