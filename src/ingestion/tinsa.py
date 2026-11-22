"""Conector Tinsa (IMIE provincial, €/m²). Fuente OPCIONAL.

Modos:
- ``legacy`` (por defecto): registra como snapshot el CSV v1 ``Datos ya metidos/tinsa_prov_precios_trim.csv``
  (fecha de descarga desconocida; se documenta). No hace peticiones.
- ``scrape``: solo si ``ETL_TINSA_SCRAPE=1``. Respeta robots.txt (se comprueba en cada ejecución), 1 petición
  cada 2 s, User-Agent identificable, guarda el HTML crudo de cada provincia. Revisar el aviso legal de Tinsa
  antes de redistribuir los datos (pendiente de confirmación por el agente de Fuentes).
"""
from __future__ import annotations

import io as _io
import os
import re
import urllib.robotparser

import pandas as pd

from src.common import config, http, io
from src.common.geography import province_code
from src.common.periods import quarter_label

from .base import Connector, FetchResult, log

TINSA_INDEX = "https://www.tinsa.es/precio-vivienda/"
LEGACY_CSV = config.V1_INPUTS / "tinsa_prov_precios_trim.csv"
_LOC = re.compile(r'imieAddLocationToMap\([^,]+,\s*"([^"]+)",\s*"Provincia",\s*[^,]+,\s*[^,]+,\s*"([^"]+)"')


def extract_chart(html: str):
    m = re.search(r"categories:\s*\[(.*?)\]", html, re.S)
    if not m:
        return None
    dates = [d.strip().strip("'\"") for d in m.group(1).split(",") if d.strip()]
    for block in re.findall(r"data:\s*\[([\d\.,\s-]+)\]", html):
        try:
            vals = [float(x) for x in block.split(",") if x.strip()]
        except ValueError:
            continue
        if len(vals) == len(dates) and all(v > 100 for v in vals):
            return list(zip(dates, vals))
    return None


def scraping_enabled() -> bool:
    return os.environ.get("ETL_TINSA_SCRAPE") == "1"


class TinsaConnector(Connector):
    source = "tinsa"

    def fetch(self, spec, dry_run=False, since: str | None = None) -> FetchResult:  # since: descarga completa (fichero/dataset pequeño)
        if not scraping_enabled():
            raw = LEGACY_CSV.read_bytes()
            meta = {"source": "Tinsa (vía CSV v1)", "dataset": spec.key, "mode": "legacy",
                    "origin_file": str(LEGACY_CSV.relative_to(config.ROOT)),
                    "retrieved_at": None, "retrieved_at_note": "desconocida: CSV generado en v1 por tinsa_scraper.py sin fecha",
                    "series_ids": ["tinsa:IMIE:provincias"], "licence": "Tinsa: condiciones de uso pendientes de verificar"}
            path, meta, changed = io.save_snapshot("tinsa", spec.key, raw, meta, io.sha256_bytes(raw),
                                                   ext="csv", dry_run=dry_run)
            return FetchResult(spec.key, "tinsa", changed, str(path) if path else None, meta, raw,
                               notes=["modo legacy (ETL_TINSA_SCRAPE!=1)"])
        rp = urllib.robotparser.RobotFileParser("https://www.tinsa.es/robots.txt")
        rp.read()
        if not rp.can_fetch(config.USER_AGENT, TINSA_INDEX):
            raise http.HttpError("robots.txt de Tinsa no permite /precio-vivienda/")
        index_html, _ = http.get(TINSA_INDEX, expect="text")
        provs = dict(_LOC.findall(index_html))
        pages = {}
        for name, url in sorted(provs.items()):
            if not rp.can_fetch(config.USER_AGENT, url):
                continue
            try:
                pages[name], _ = http.get(url, expect="text")
            except http.HttpError as e:
                log.warning("Tinsa %s: %s", name, e)
        payload = {"index": TINSA_INDEX, "pages": pages}
        meta = {"source": "Tinsa", "dataset": spec.key, "mode": "scrape", "n_pages": len(pages),
                "series_ids": ["tinsa:IMIE:provincias"],
                "retrieved_at": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
        content = {k: extract_chart(v) for k, v in pages.items()}
        path, meta, changed = io.save_snapshot("tinsa", spec.key, payload, meta,
                                               io.sha256_bytes(io.canonical_json(content)), dry_run=dry_run)
        return FetchResult(spec.key, "tinsa", changed, str(path) if path else None, meta, payload)

    def parse(self, payload, spec, snapshot_meta) -> pd.DataFrame:
        vs = spec.variables[0]
        if isinstance(payload, (bytes, bytearray)):
            df = pd.read_csv(_io.BytesIO(payload))
            recs = df[["Provincia", "Trimestre", "Precio_m2"]].itertuples(index=False)
        else:
            recs = [(n, d, v) for n, html in payload["pages"].items() for d, v in (extract_chart(html) or [])]
        rows = []
        for prov, trim, val in recs:
            q = quarter_label(trim)
            rows.append({"variable": vs.name, "geo_level": "provincia", "geo_code": province_code(prov),
                         "freq": "Q", "ref_date": pd.Period(q, freq="Q").start_time.strftime("%Y-%m-%d"),
                         "period": q, "value": float(val), "unit": vs.unit, "status": None,
                         "source": "Tinsa", "series_id": "tinsa:IMIE"})
        return pd.DataFrame(rows)
