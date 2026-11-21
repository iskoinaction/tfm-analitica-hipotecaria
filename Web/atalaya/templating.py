"""Filtros Jinja (formato numérico es-ES) y navegación común."""
from __future__ import annotations

import math

from flask import request

# Arquitectura de información v2 (reports/audit/09_ux.md §3)
NAV = [
    {"group": None, "items": [{"endpoint": "pages.index", "label": "Resumen", "icon": "home"}]},
    {"group": "Mercado", "items": [
        {"endpoint": "pages.precios", "label": "Precios y mapas", "icon": "map"},
        {"endpoint": "pages.demanda", "label": "Demanda hipotecaria", "icon": "trend"},
    ]},
    {"group": "Herramientas", "items": [
        {"endpoint": "pages.simulador", "label": "Simulador hipotecario", "icon": "calc"},
        {"endpoint": "pages.asistente", "label": "Asistente", "icon": "chat", "requires": "assistant"},
    ]},
    {"group": "Modelos", "items": [
        {"endpoint": "pages.proyecciones", "label": "Proyecciones 2026-2030", "icon": "forecast"},
        {"endpoint": "pages.econometria", "label": "Econometría (VAR/VECM)", "icon": "model"},
        {"endpoint": "pages.metodologia", "label": "Metodología", "icon": "book"},
    ]},
    {"group": "Datos", "items": [
        {"endpoint": "pages.datos", "label": "Datos y fuentes", "icon": "db"},
    ]},
    {"group": "Proyecto", "items": [
        {"endpoint": "pages.caso_negocio", "label": "Caso de negocio", "icon": "brief"},
    ]},
]


def fmt_num(value, decimals: int = 0, unit: str | None = None) -> str:
    """12345.678 -> '12.345,68' (es-ES). None/NaN -> '—'."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    if isinstance(value, str):
        return value
    txt = f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{txt} {unit}" if unit else txt


def fmt_period(value) -> str:
    """'2025Q3' -> '2025 T3'."""
    s = str(value or "")
    if len(s) == 6 and s[4] == "Q":
        return f"{s[:4]} T{s[5]}"
    return s


def register_template_helpers(app) -> None:
    app.jinja_env.filters["num"] = fmt_num
    app.jinja_env.filters["period"] = fmt_period

    @app.context_processor
    def _nav():
        return {"nav": NAV, "current_endpoint": request.endpoint}
