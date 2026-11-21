"""Comprobaciones de salud para el orquestador (Render, Docker, etc.)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from .. import __version__
from . import panel, store

bp = Blueprint("health", __name__)


@bp.get("/healthz")
def healthz():
    """Liveness: el proceso responde. No toca disco."""
    return jsonify(status="ok", version=__version__)


@bp.get("/readyz")
def readyz():
    """Readiness: estado de artefactos y panel. Responde 200 aunque falten artefactos
    (la web funciona en modo degradado con estados vacíos honestos)."""
    artifacts = {m["domain"]: m["status"] for m in store().status_all()}
    panel_ok = panel().available()
    degraded = (not panel_ok) or any(s != "ok" for s in artifacts.values())
    return jsonify(status="degraded" if degraded else "ready", version=__version__,
                   panel=panel_ok, artifacts=artifacts)
