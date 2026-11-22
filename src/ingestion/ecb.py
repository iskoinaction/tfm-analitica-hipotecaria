"""Conector BCE (ECB Data Portal, API SDMX 2.1 REST en CSV): https://data.ecb.europa.eu/help/api/data."""
from __future__ import annotations

import io as _io

import pandas as pd

from src.common import config, http, io

from .base import Connector, FetchResult, period_label

REQUIRED_COLS = {"KEY", "TIME_PERIOD", "OBS_VALUE"}


class ECBConnector(Connector):
    source = "ecb"

    def fetch(self, spec, dry_run=False, since: str | None = None) -> FetchResult:
        """``since`` (AAAAMMDD): pide solo desde ese mes y fusiona con el último snapshot.

        Vintages: la API SDMX del BCE admite ``includeHistory=true`` (versiones anteriores de cada observación);
        no se usa por defecto, los snapshots fechados hacen de vintage propio."""
        prev = io.latest_snapshot("ecb", spec.key) if since else None
        if since and prev is None:
            since = None
        frm = since or config.DOWNLOAD_FROM
        start = f"{frm[:4]}-{frm[4:6]}"
        payload, infos = {}, {}
        for vs in spec.variables:
            key = vs.match["key"]
            url = f"{config.ECB_BASE}/{key}"
            text, info = http.get(url, params={"format": "csvdata", "startPeriod": start}, expect="text")
            df = pd.read_csv(_io.StringIO(text))
            if not REQUIRED_COLS <= set(df.columns) or df.empty:
                raise http.HttpError(f"BCE {key}: esquema inesperado {list(df.columns)[:8]}")
            keep = [c for c in ["KEY", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS", "TITLE", "UNIT", "UNIT_MULT"] if c in df.columns]
            payload[vs.name] = df[keep].to_dict(orient="list")
            infos[vs.name] = {"url": info["url"], "last_modified": info.get("last_modified"), "rows": len(df)}
        if since:
            old = io.read_snapshot(prev[0])
            for name, d in payload.items():
                o = pd.DataFrame(old.get(name, {}))
                if not o.empty:
                    o = o[o["TIME_PERIOD"].astype(str) < start]
                    payload[name] = pd.concat([o, pd.DataFrame(d)], ignore_index=True).to_dict(orient="list")
        content_hash = io.sha256_bytes(io.canonical_json(payload))
        meta = {"source": "BCE", "dataset": spec.key, "requests": infos,
                "series_ids": [v.match["key"] for v in spec.variables], "mode": "incremental" if since else "full",
                "retrieved_at": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "licence": "BCE: reutilización permitida citando la fuente"}
        path, meta, changed = io.save_snapshot("ecb", spec.key, payload, meta, content_hash, dry_run=dry_run)
        return FetchResult(spec.key, "ecb", changed, str(path) if path else None, meta, payload)

    def parse(self, payload, spec, snapshot_meta) -> pd.DataFrame:
        rows = []
        for vs in spec.variables:
            d = pd.DataFrame(payload[vs.name])
            geo = ("zona_euro", "U2") if ".U2." in vs.match["key"] else ("nacional", "00")
            for _, r in d.iterrows():
                if pd.isna(r["OBS_VALUE"]):
                    continue
                ref = pd.Timestamp(str(r["TIME_PERIOD"]) + "-01")
                rows.append({"variable": vs.name, "geo_level": geo[0], "geo_code": geo[1], "freq": "M",
                             "ref_date": ref.strftime("%Y-%m-%d"), "period": period_label(ref, "M"),
                             "value": float(r["OBS_VALUE"]), "unit": vs.unit,
                             "status": r.get("OBS_STATUS"), "source": "BCE", "series_id": vs.match["key"]})
        return pd.DataFrame(rows)
