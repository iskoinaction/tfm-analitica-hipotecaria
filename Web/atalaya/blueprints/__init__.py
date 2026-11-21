"""Blueprints: pages (HTML), api (JSON /api/v1) y health (/healthz, /readyz)."""
from flask import current_app


def store():
    return current_app.extensions["atalaya.artifacts"]


def panel():
    return current_app.extensions["atalaya.panel"]
