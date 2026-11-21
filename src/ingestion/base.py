"""Interfaz común de conectores y utilidades de fechas/periodos para staging."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.common import config, io

log = logging.getLogger("etl.ingestion")


@dataclass
class FetchResult:
    dataset: str
    source: str
    changed: bool
    snapshot: str | None
    meta: dict
    payload: object = None
    error: str | None = None
    notes: list = field(default_factory=list)


def period_label(ref_date: pd.Timestamp, freq: str) -> str:
    if freq == "M":
        return f"{ref_date.year}-{ref_date.month:02d}"
    if freq == "Q":
        return f"{ref_date.year}Q{(ref_date.month - 1) // 3 + 1}"
    if freq == "A":
        return f"{ref_date.year}"
    return ref_date.strftime("%Y-%m-%d")


class Connector:
    source = "base"

    def fetch(self, spec: config.DatasetSpec, dry_run: bool = False) -> FetchResult:  # pragma: no cover
        raise NotImplementedError

    def parse(self, payload, spec: config.DatasetSpec, snapshot_meta: dict) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    # ---- helpers
    def stage_from_latest(self, spec: config.DatasetSpec) -> pd.DataFrame:
        """Parsea el último snapshot raw del dataset (sin red)."""
        snap = io.latest_snapshot(self.source, spec.key)
        if snap is None:
            raise FileNotFoundError(f"No hay snapshot raw para {self.source}/{spec.key}")
        path, meta = snap
        df = self.parse(io.read_snapshot(path), spec, meta)
        df["snapshot"] = str(path.relative_to(config.ROOT))
        df["retrieved_at"] = meta.get("retrieved_at")
        df["dataset"] = spec.key
        return df
