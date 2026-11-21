"""Páginas HTML. Ninguna cifra de modelos está escrita en las plantillas: todo procede de
``artifacts/`` (vía ArtifactStore) o del panel observado (vía PanelService)."""
from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, url_for

from ..services import advisor_service
from ..services.assistant import DISCLAIMER, is_enabled
from ..services.geo import province_options
from ..services.metadata import load_sources
from ..services.panel import VARIABLES
from . import panel, store

bp = Blueprint("pages", __name__)


def _panel_info() -> dict | None:
    if not panel().available():
        return None
    q = panel().quality()
    return {k: q[k] for k in ("source", "is_legacy", "rows", "provinces", "first_period", "last_period")}


def _common(**kw):
    kw.setdefault("panel_info", _panel_info())
    kw.setdefault("provinces", province_options())
    kw.setdefault("variables", [{"key": k, **v} for k, v in VARIABLES.items()])
    return kw


@bp.get("/")
def index():
    return render_template("pages/index.html", forecasting=store().get("forecasting"),
                           demand=store().get("demand"), **_common())


@bp.get("/mercado/precios")
def precios():
    return render_template("pages/precios.html", **_common())


@bp.get("/mercado/demanda")
def demanda():
    demand = store().get("demand")
    scope_keys = store().scope_keys("demand", "provincial")
    return render_template("pages/demanda.html", demand=demand, scope_keys=scope_keys, **_common())


@bp.get("/simulador")
def simulador():
    return render_template("pages/simulador.html", advisor=store().get("advisor"),
                           engine=advisor_service.engine_status(), **_common())


@bp.get("/asistente")
def asistente():
    return render_template("pages/asistente.html", enabled=is_enabled(current_app.config),
                           disclaimer=DISCLAIMER, max_chars=current_app.config["ASSISTANT_MAX_INPUT_CHARS"])


@bp.get("/modelos/proyecciones")
def proyecciones():
    return render_template("pages/proyecciones.html", forecasting=store().get("forecasting"), **_common())


@bp.get("/modelos/econometria")
def econometria():
    return render_template("pages/econometria.html", econometrics=store().get("econometrics"), **_common())


@bp.get("/modelos/metodologia")
def metodologia():
    bundles = [store().get(d) for d in ("forecasting", "demand", "econometrics", "advisor")]
    return render_template("pages/metodologia.html", bundles=bundles, **_common())


@bp.get("/datos")
def datos():
    quality = panel().quality() if panel().available() else None
    return render_template("pages/datos.html", statuses=store().status_all(),
                           data_quality=store().get("data_quality"), quality=quality,
                           sources=load_sources(current_app.config["DATA_DIR"]), **_common())


@bp.get("/caso-de-negocio")
def caso_negocio():
    return render_template("pages/caso_negocio.html", demand=store().get("demand"),
                           forecasting=store().get("forecasting"), advisor=store().get("advisor"), **_common())


# Redirecciones permanentes desde las URL de la v1 (sin reintroducir las rutas retiradas)
_LEGACY = {
    "/hipotecas": "pages.simulador", "/hipotecas-provincial": "pages.simulador",
    "/demanda": "pages.demanda", "/demanda-provincial": "pages.demanda",
    "/econometria": "pages.econometria", "/vecm": "pages.econometria",
    "/metodologia-ml": "pages.metodologia", "/business_case": "pages.caso_negocio",
    "/webscrapping": "pages.datos",
}


def _make_redirect(target: str):
    def view():
        return redirect(url_for(target), code=301)
    return view


for _path, _target in _LEGACY.items():
    bp.add_url_rule(_path, endpoint="legacy_" + _path.strip("/").replace("-", "_"), view_func=_make_redirect(_target))
