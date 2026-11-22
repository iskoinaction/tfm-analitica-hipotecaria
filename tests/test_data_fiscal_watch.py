"""Watcher fiscal BOE (offline: HTTP simulado)."""
import pandas as pd

from src.common import http
from src.ingestion import fiscalidad


def _tabla():
    return pd.DataFrame({"boe_id": ["X-1", "X-2", "X-3"], "norma": ["a", "b", "c"],
                         "fecha_verificacion": ["2026-01-01"] * 3})


def test_watch_marca_revision_y_tolera_fallos(monkeypatch):
    def fake(url, **kw):
        if "X-1" in url:
            return {"data": [{"fecha_actualizacion": "20260301T000000Z"}]}, {}
        if "X-2" in url:
            return {"data": [{"fecha_actualizacion": "20251201T000000Z"}]}, {}
        raise http.HttpError("sin red")
    monkeypatch.setattr(http, "get", fake)
    r = {x["boe_id"]: x for x in fiscalidad.boe_watch(_tabla())}
    assert r["X-1"]["revision_requerida"] is True
    assert r["X-2"]["revision_requerida"] is False
    assert r["X-3"]["revision_requerida"] is None and "error" in r["X-3"]
