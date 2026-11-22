"""Conector INE (API JSON Tempus3, https://www.ine.es/dyngs/DataLab/manual.html?cid=45).

Estrategia: 1) catálogo de la tabla con ``DATOS_TABLA/{id}?nult=1&tip=AM`` (metadatos con códigos INE de
provincia/CCAA, sin parsear nombres); 2) selección de series por metadatos; 3) descarga de cada serie con
``DATOS_SERIE/{cod}?tip=AM&date=AAAAMMDD:AAAAMMDD``. El valor se toma del campo numérico ``Valor`` (nunca del CSV
con formato español, origen del bug de miles de la v1). Se registra ``T3_TipoDato`` (provisional/definitivo) y la
``Ultima_Modificacion`` de la tabla (detección de cambios).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from src.common import config, http, io
from src.common.geography import CCAA, ccaa_code, province_code, provinces_of_ccaa

from .base import Connector, FetchResult, log, period_label

GEO_NATIONAL = {"Total Nacional", "Totales Territoriales"}
GEO_CCAA = "Comunidades y Ciudades Autónomas"


def _meta_dict(series: dict) -> dict:
    return {m["T3_Variable"].strip(): m["Nombre"].strip() for m in series.get("MetaData", [])}


def geo_of(series: dict, geo_vars: tuple) -> tuple[str, str] | None:
    """(geo_level, geo_code) a partir de los metadatos; None si la serie no es de un ámbito aceptado."""
    for m in series.get("MetaData", []):
        var = m["T3_Variable"].strip()
        if var not in geo_vars and var not in GEO_NATIONAL:
            continue
        if var == "Provincias":
            code = (m.get("Codigo") or "").strip()
            return "provincia", code.zfill(2) if code else province_code(m["Nombre"])
        if var == GEO_CCAA:
            code = (m.get("Codigo") or "").strip()
            return "ccaa", code.zfill(2) if code else ccaa_code(m["Nombre"])
        if var in GEO_NATIONAL:
            if "nacional" in m["Nombre"].lower():
                return "nacional", "00"
    return None


def match_variable(series: dict, spec: config.DatasetSpec):
    md = _meta_dict(series)
    for k, v in spec.base_filter.items():
        if md.get(k) != v:
            return None
    for vs in spec.variables:
        if all(md.get(k) == v for k, v in vs.match.items()):
            return vs
    return None


class INEConnector(Connector):
    source = "ine"

    def _table_last_modified(self, spec) -> str | None:
        if not spec.operation or spec.ref.startswith("SERIE:"):
            return None
        try:
            tabs, _ = http.get(f"{config.INE_BASE}/TABLAS_OPERACION/{spec.operation}")
            for t in tabs:
                if str(t.get("Id")) == spec.ref:
                    return t.get("Ultima_Modificacion")
        except http.HttpError as e:
            log.warning("No se pudo leer Ultima_Modificacion de %s: %s", spec.ref, e)
        return None

    def select_series(self, spec) -> list[dict]:
        if spec.ref.startswith("SERIE:"):
            return [{"COD": c} for c in spec.ref.split(":", 1)[1].split(",")]
        cat, _ = http.get(f"{config.INE_BASE}/DATOS_TABLA/{spec.ref}", params={"nult": 1, "tip": "AM"})
        if not isinstance(cat, list) or not cat:
            raise http.HttpError(f"Catálogo vacío o inesperado para tabla {spec.ref}: {str(cat)[:120]}")
        out = []
        for s in cat:
            if "COD" not in s or "MetaData" not in s:
                raise http.HttpError(f"Esquema de respuesta inesperado en tabla {spec.ref}")
            if match_variable(s, spec) and geo_of(s, spec.geo_vars):
                out.append({"COD": s["COD"], "Nombre": s["Nombre"]})
        if not out:
            raise http.HttpError(f"Ninguna serie de la tabla {spec.ref} cumple el filtro: ¿ha cambiado la tabla?")
        return out

    def fetch(self, spec, dry_run=False, since: str | None = None) -> FetchResult:
        """``since`` (AAAAMMDD): descarga incremental; las observaciones previas se toman del último snapshot."""
        sel = self.select_series(spec)
        prev = io.latest_snapshot("ine", spec.key) if since else None
        if since and prev is None:
            since = None  # sin snapshot previo no hay incremental posible
        date = f"{since or config.DOWNLOAD_FROM}:20351231"

        def one(cod):
            d, info = http.get(f"{config.INE_BASE}/DATOS_SERIE/{cod}", params={"tip": "AM", "date": date})
            if not isinstance(d, dict) or "Data" not in d:
                raise http.HttpError(f"Serie {cod}: esquema inesperado")
            return cod, d

        with ThreadPoolExecutor(max_workers=3) as ex:
            series = dict(ex.map(lambda s: one(s["COD"]), sel))
        if since:
            old = io.read_snapshot(prev[0])["series"]
            cut = pd.Timestamp(since)
            for cod, d in series.items():
                keep = [o for o in old.get(cod, {}).get("Data", []) if pd.Timestamp(o["Fecha"][:10]) < cut]
                d["Data"] = keep + d["Data"]
        payload = {"table": spec.ref, "series": series}
        content_hash = io.sha256_bytes(io.canonical_json(payload))
        n_obs = sum(len(s["Data"]) for s in series.values())
        meta = {"source": "INE", "dataset": spec.key, "table": spec.ref,
                "url": f"{config.INE_BASE}/DATOS_SERIE/<COD>?tip=AM&date={date}",
                "catalog_url": f"{config.INE_BASE}/DATOS_TABLA/{spec.ref}?nult=1&tip=AM",
                "n_series": len(series), "n_obs": n_obs, "mode": "incremental" if since else "full", "since": since, "series_ids": sorted(series),
                "table_last_modified": self._table_last_modified(spec),
                "retrieved_at": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "licence": "INE: reutilización libre citando la fuente (Aviso legal INE)"}
        path, meta, changed = io.save_snapshot("ine", spec.key, payload, meta, content_hash, dry_run=dry_run)
        return FetchResult(spec.key, "ine", changed, str(path) if path else None, meta, payload)

    def parse(self, payload, spec, snapshot_meta) -> pd.DataFrame:
        rows = []
        for cod, s in payload["series"].items():
            if spec.ref.startswith("SERIE:"):  # series explícitas: variables en el mismo orden que los códigos
                vs = spec.variables[spec.ref.split(":", 1)[1].split(",").index(cod)]
            else:
                vs = match_variable(s, spec)
            if vs is None:
                continue
            geo = geo_of(s, spec.geo_vars) or ("nacional", "00")
            unit = f"{s.get('T3_Unidad', '')} {s.get('T3_Escala', '')}".strip()
            for o in s["Data"]:
                if o.get("Valor") is None:
                    continue
                ref = pd.Timestamp(o["Fecha"][:10])
                rows.append({"variable": vs.name, "geo_level": geo[0], "geo_code": geo[1],
                             "freq": spec.freq, "ref_date": ref.strftime("%Y-%m-%d"),
                             "period": period_label(ref, spec.freq), "value": float(o["Valor"]),
                             "unit": unit or vs.unit, "status": o.get("T3_TipoDato"),
                             "source": "INE", "series_id": cod})
        df = pd.DataFrame(rows)
        if df.empty:
            raise ValueError(f"{spec.key}: parse sin filas")
        # CCAA uniprovinciales: algunas tablas (p.ej. CRE) solo las publican como CCAA. Si la tabla tiene datos
        # provinciales, se añade la fila provincial equivalente cuando falta (misma cifra, misma unidad territorial).
        if (df["geo_level"] == "provincia").any() and (df["geo_level"] == "ccaa").any():
            uni = {c: provinces_of_ccaa(c)[0] for c in CCAA if len(provinces_of_ccaa(c)) == 1}
            extra = df[(df["geo_level"] == "ccaa") & df["geo_code"].isin(list(uni))].copy()
            extra["geo_level"], extra["geo_code"] = "provincia", extra["geo_code"].map(uni)
            df = pd.concat([df, extra], ignore_index=True)
        # Las CCAA uniprovinciales pueden aparecer dos veces (como CCAA y como provincia): se conserva una.
        return df.drop_duplicates(["variable", "geo_level", "geo_code", "ref_date"])
