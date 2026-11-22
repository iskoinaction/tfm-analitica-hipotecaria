"""Conector MIVAU — Estadística de Valor Tasado de Vivienda (IOE 20007), fichero CSV oficial.

Endpoint: https://cdn.mivau.gob.es/portal-web-mivau/Datos_MIVAU/CSV/VDP006_01.csv (catálogo datos.gob.es).
Filtro: Régimen = Libre. Valor 0/vacío = sin muestra suficiente → se descarta (NaN, nunca 0).
Madrid, Murcia, Navarra y Asturias solo aparecen como 'Total CCAA' (uniprovinciales) → se asignan a su provincia.
La detección de cambios usa Last-Modified/ETag y el sha256 del fichero (el MIVAU sobrescribe el fichero: sin vintages).
"""
from __future__ import annotations

import io as _io

import pandas as pd

from src.common import config, http, io
from src.common.geography import CCAA, ccaa_code, provinces_of_ccaa

from .base import Connector, FetchResult

URL = "https://cdn.mivau.gob.es/portal-web-mivau/Datos_MIVAU/CSV/VDP006_01.csv"
COLS = {"Año", "Trimestre", "Valor", "Régimen", "CPRO", "Provincia", "Comunidad_Autónoma", "CODAUTO"}


def parse_vdp006(raw: bytes, var: str = "precio_m2_mivau_tasado", unit: str = "€/m²") -> pd.DataFrame:
    d = pd.read_csv(_io.BytesIO(raw), sep=";", encoding="utf-8-sig", dtype=str)
    if not COLS <= set(d.columns):
        raise ValueError(f"VDP006: columnas inesperadas {list(d.columns)}")
    d = d[d["Régimen"].str.strip() == "Libre"].copy()
    d["v"] = pd.to_numeric(d["Valor"].str.replace(",", ".", regex=False), errors="coerce")
    d = d[d["v"] > 0].rename(columns={"Año": "anio", "Comunidad_Autónoma": "ccaa"})
    rows = []
    for r in d.itertuples(index=False):
        prov, ca = str(r.Provincia).strip(), str(r.ccaa).strip()
        cpro = str(r.CPRO).strip()
        if prov == "Total CCAA":
            try:
                cc = ccaa_code(ca)
            except KeyError:
                continue
            pp = provinces_of_ccaa(cc)
            if len(pp) != 1:
                continue
            geo = ("provincia", pp[0])
        elif cpro.isdigit():
            geo = ("provincia", cpro.zfill(2))
        elif prov.lower().startswith("total nacional"):
            geo = ("nacional", "00")
        else:
            continue  # 'Ceuta y Melilla' agregado
        q = pd.Period(year=int(r.anio), quarter=int(r.Trimestre), freq="Q")
        rows.append({"variable": var, "geo_level": geo[0], "geo_code": geo[1], "freq": "Q",
                     "ref_date": q.start_time.strftime("%Y-%m-%d"), "period": f"{q.year}Q{q.quarter}",
                     "value": float(r.v), "unit": unit, "status": None, "source": "MIVAU", "series_id": "VDP006_01:Libre"})
    out = pd.DataFrame(rows)
    return out.drop_duplicates(["variable", "geo_level", "geo_code", "ref_date"])


class MivauConnector(Connector):
    source = "mivau"

    def fetch(self, spec, dry_run=False) -> FetchResult:
        raw, info = http.get(URL, expect="bytes")
        parse_vdp006(raw)  # valida esquema antes de guardar
        meta = {"source": "MIVAU", "dataset": spec.key, "url": URL, "last_modified": info.get("last_modified"),
                "etag": info.get("etag"), "table_last_modified": info.get("last_modified"),
                "retrieved_at": info["retrieved_at"], "series_ids": ["VDP006_01"],
                "licence": "datos.gob.es / Aviso legal MIVAU: reutilización con cita (Ley 37/2007)"}
        path, meta, changed = io.save_snapshot("mivau", spec.key, raw, meta, io.sha256_bytes(raw), ext="csv", dry_run=dry_run)
        return FetchResult(spec.key, "mivau", changed, str(path) if path else None, meta, raw)

    def parse(self, payload, spec, snapshot_meta) -> pd.DataFrame:
        vs = spec.variables[0]
        return parse_vdp006(payload, vs.name, vs.unit)
