"""E/S del pipeline: snapshots raw versionados (nunca se sobrescriben), manifests con sha256, staging CSV."""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from . import config


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def snapshots(source: str, dataset: str) -> list[Path]:
    """Snapshots existentes de un dataset, del más antiguo al más reciente."""
    base = config.RAW / source
    if not base.exists():
        return []
    return sorted(base.glob(f"*/{dataset}.meta.json"), key=lambda p: (p.parent.name, p.stat().st_mtime))


def latest_snapshot(source: str, dataset: str) -> tuple[Path, dict] | None:
    snaps = snapshots(source, dataset)
    if not snaps:
        return None
    meta = json.loads(snaps[-1].read_text(encoding="utf-8"))
    return snaps[-1].parent / meta["file"], meta


def save_snapshot(source: str, dataset: str, payload, meta: dict, content_hash: str,
                  ext: str = "json.gz", dry_run: bool = False) -> tuple[Path | None, dict, bool]:
    """Guarda el payload en data/raw/<source>/<YYYYMMDD>[_HHMMSS]/<dataset>.<ext> + <dataset>.meta.json.

    ``content_hash`` es el hash del contenido normalizado (sin marcas de tiempo) y sirve para detectar cambios.
    Si coincide con el último snapshot, no se escribe nada (changed=False). Nunca sobrescribe un snapshot.
    """
    prev = latest_snapshot(source, dataset)
    changed = prev is None or prev[1].get("content_sha256") != content_hash
    meta = dict(meta, content_sha256=content_hash,
                previous_snapshot=str(prev[0].relative_to(config.ROOT)) if prev else None)
    if not changed or dry_run:
        return (prev[0] if prev else None), meta, changed
    now = dt.datetime.now(dt.timezone.utc)
    d = config.RAW / source / now.strftime("%Y%m%d")
    if (d / f"{dataset}.meta.json").exists():
        d = config.RAW / source / now.strftime("%Y%m%d_%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    fname = f"{dataset}.{ext}"
    path = d / fname
    if ext.endswith(".gz"):
        data = payload if isinstance(payload, bytes) else canonical_json(payload)
        with gzip.open(path, "wb", compresslevel=9, mtime=0) as f:
            f.write(data)
    elif isinstance(payload, bytes):
        path.write_bytes(payload)
    else:
        path.write_text(payload, encoding="utf-8")
    meta.update(file=fname, file_sha256=sha256_file(path), bytes=path.stat().st_size)
    (d / f"{dataset}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return path, meta, True


def read_snapshot(path: Path):
    if str(path).endswith(".json.gz"):
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    if str(path).endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return f.read()
    return path.read_bytes()


STAGING_COLUMNS = ["dataset", "variable", "geo_level", "geo_code", "period", "freq", "ref_date", "value",
                   "unit", "status", "source", "series_id", "snapshot", "retrieved_at"]


def write_staging(df: pd.DataFrame, dataset: str) -> Path:
    config.STAGING.mkdir(parents=True, exist_ok=True)
    missing = [c for c in STAGING_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"staging {dataset}: faltan columnas {missing}")
    out = config.STAGING / f"{dataset}.csv"
    df[STAGING_COLUMNS].sort_values(["variable", "geo_code", "ref_date"]).to_csv(out, index=False, encoding="utf-8")
    return out


def read_staging(dataset: str) -> pd.DataFrame:
    p = config.STAGING / f"{dataset}.csv"
    return pd.read_csv(p, dtype={"geo_code": str, "period": str}, encoding="utf-8")
