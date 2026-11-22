"""Conector Eurostat (API de difusión JSON-stat 2.0)."""
from __future__ import annotations

import itertools

import pandas as pd

from src.common import config, http, io

from .base import Connector, FetchResult


def jsonstat_to_frame(d: dict) -> pd.DataFrame:
    """Convierte un JSON-stat 2.0 (dataset) en DataFrame largo con una columna por dimensión."""
    ids, sizes = d["id"], d["size"]
    cats = []
    for dim in ids:
        idx = d["dimension"][dim]["category"]["index"]
        order = sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx)
        cats.append(order)
    values = d["value"]
    rows = []
    for flat, combo in enumerate(itertools.product(*cats)):
        v = values.get(str(flat)) if isinstance(values, dict) else values[flat]
        if v is None:
            continue
        rows.append(dict(zip(ids, combo), value=v))
    assert len(list(itertools.product(*cats))) == int(pd.Series(sizes).prod())
    return pd.DataFrame(rows)


class EurostatConnector(Connector):
    source = "eurostat"

    def fetch(self, spec, dry_run=False, since: str | None = None) -> FetchResult:  # since: descarga completa (fichero/dataset pequeño)
        vs = spec.variables[0]
        params = dict(vs.match, format="JSON", lang="EN")
        d, info = http.get(f"{config.EUROSTAT_BASE}/{spec.ref}", params=params)
        if d.get("class") != "dataset" or "value" not in d:
            raise http.HttpError(f"Eurostat {spec.ref}: respuesta inesperada")
        content = {k: d[k] for k in ("id", "size", "value", "dimension")}
        content_hash = io.sha256_bytes(io.canonical_json(content))
        meta = {"source": "Eurostat", "dataset": spec.key, "url": info["url"], "updated": d.get("updated"),
                "label": d.get("label"), "series_ids": [f"{spec.ref}:{vs.match}"],
                "retrieved_at": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "licence": "Eurostat: reutilización libre citando la fuente (Decisión 2011/833/UE)"}
        path, meta, changed = io.save_snapshot("eurostat", spec.key, d, meta, content_hash, dry_run=dry_run)
        return FetchResult(spec.key, "eurostat", changed, str(path) if path else None, meta, d)

    def parse(self, payload, spec, snapshot_meta) -> pd.DataFrame:
        vs = spec.variables[0]
        df = jsonstat_to_frame(payload)
        df = df[df["time"].str.match(r"^\d{4}-Q[1-4]$")]
        q = pd.PeriodIndex(df["time"].str.replace("-", ""), freq="Q")
        return pd.DataFrame({"variable": vs.name, "geo_level": "nacional", "geo_code": "00", "freq": "Q",
                             "ref_date": q.start_time.strftime("%Y-%m-%d"),
                             "period": [f"{p.year}Q{p.quarter}" for p in q],
                             "value": df["value"].astype(float).values, "unit": vs.unit, "status": None,
                             "source": "Eurostat", "series_id": f"{spec.ref}.{'.'.join(vs.match.values())}"})
