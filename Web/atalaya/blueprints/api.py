"""API JSON v1 (sólo lectura, salvo la simulación y el asistente opcional)."""
from __future__ import annotations

import logging

from flask import Blueprint, abort, current_app, jsonify, request

from ..security import rate_limit
from ..services import advisor_service, assistant
from ..services.artifacts import DOMAINS
from ..services.geo import province_name, province_options, resolve
from ..services.panel import VARIABLES, PanelUnavailable
from . import panel, store

bp = Blueprint("api", __name__)
log = logging.getLogger(__name__)


def _panel_or_503():
    try:
        return panel().load()
    except (PanelUnavailable, OSError, ValueError, ImportError) as e:
        abort(503, description=str(e))


def _meta(var: str) -> dict:
    return panel().var_meta(var)


def _var_arg(default: str) -> str:
    var = request.args.get("var", default)
    if var not in VARIABLES:
        abort(400, description=f"Variable no válida: {var}")
    return var


def _prov_arg() -> str | None:
    try:
        return resolve(request.args.get("prov"))
    except KeyError:
        abort(400, description="Provincia no reconocida")


# ------------------------------------------------------------------ metadatos
@bp.get("/meta")
@rate_limit("RATELIMIT_DEFAULT")
def meta():
    pnl = None
    if panel().available():
        q = panel().quality()
        pnl = {k: q[k] for k in ("source", "rows", "provinces", "first_period", "last_period")}
    return jsonify(artifacts=store().status_all(), panel=pnl, provinces=province_options())


# ------------------------------------------------------------------ panel (datos observados)
@bp.get("/panel/variables")
@rate_limit("RATELIMIT_DEFAULT")
def panel_variables():
    _panel_or_503()
    return jsonify(variables=panel().variables(), periods=panel().periods())


@bp.get("/panel/series")
@rate_limit("RATELIMIT_DEFAULT")
def panel_series():
    data = _panel_or_503()
    var, prov = _var_arg("hipotecas_viviendas_num"), _prov_arg()
    try:
        s = panel().province_series(var, prov) if prov else panel().national_series(var)
    except KeyError:
        abort(404, description="Variable no disponible en el panel")
    return jsonify(var=var, label=_meta(var)["label"], unit=_meta(var)["unit"], var_source=_meta(var).get("source"),
                   scope=province_name(prov) if prov else "España",
                   aggregation=None if prov else s.get("agg_label"), source=data.source_label,
                   x=s["x"], values=s["values"])


@bp.get("/panel/choropleth")
@rate_limit("RATELIMIT_DEFAULT")
def panel_choropleth():
    data = _panel_or_503()
    var = _var_arg("precio_m2_mivau_tasado")
    period = request.args.get("period") or None
    if period and period not in panel().periods():
        abort(400, description="Periodo no válido")
    try:
        used, values = panel().by_province(var, period)
    except KeyError:
        abort(404, description="Variable no disponible en el panel")
    return jsonify(var=var, label=_meta(var)["label"], unit=_meta(var)["unit"], var_source=_meta(var).get("source"), period=used,
                   scope_note=_meta(var).get("geo_level") or "provincia", source=data.source_label,
                   values=values)


@bp.get("/panel/ranking")
@rate_limit("RATELIMIT_DEFAULT")
def panel_ranking():
    data = _panel_or_503()
    var = _var_arg("hipotecas_viviendas_num")
    try:
        n = max(3, min(int(request.args.get("n", 10)), 52))
    except ValueError:
        abort(400, description="n no válido")
    try:
        r = panel().ranking(var, request.args.get("period") or None, n)
    except KeyError:
        abort(404, description="Variable no disponible en el panel")
    return jsonify(var=var, label=_meta(var)["label"], unit=_meta(var)["unit"], var_source=_meta(var).get("source"),
                   source=data.source_label, **r)


@bp.get("/panel/kpis")
@rate_limit("RATELIMIT_DEFAULT")
def panel_kpis():
    data = _panel_or_503()
    return jsonify(source=data.source_label, kpis=panel().kpis())


# ------------------------------------------------------------------ artefactos
@bp.get("/artifacts/<domain>")
@rate_limit("RATELIMIT_DEFAULT")
def artifact(domain: str):
    if domain not in DOMAINS:
        abort(404, description="Dominio de artefactos desconocido")
    return jsonify(store().get(domain).to_dict())


@bp.get("/artifacts/<domain>/scope/<scope>/<key>")
@rate_limit("RATELIMIT_DEFAULT")
def artifact_scope(domain: str, scope: str, key: str):
    if domain not in DOMAINS:
        abort(404, description="Dominio de artefactos desconocido")
    bundle = store().get(domain)
    views = store().scope_views(domain, scope, key)
    if views is None:
        return jsonify(meta=bundle.meta(), views=[], available=False)
    return jsonify(meta=bundle.meta(), views=views, available=True)


# ------------------------------------------------------------------ simulador (asesor)
@bp.get("/simulator/status")
@rate_limit("RATELIMIT_DEFAULT")
def simulator_status():
    return jsonify(engine=advisor_service.engine_status(), metadata=advisor_service.metadata())


@bp.post("/simulator/simulate")
@rate_limit("RATELIMIT_SIMULATE")
def simulator_simulate():
    payload = request.get_json(silent=True)
    if payload is None:
        abort(400, description="Se esperaba un cuerpo JSON")
    try:
        out = advisor_service.simulate(payload)
    except advisor_service.AdvisorInputError as e:
        return jsonify(status="invalid", errors=e.errors), 400
    except advisor_service.AdvisorEngineError as e:
        return jsonify(status="invalid", errors={"_": str(e)}), 400
    # Datos personales: no se registran (sólo el estado del resultado).
    log.info("simulación: estado=%s", out["status"])
    return jsonify(out), (503 if out["status"] == "pending" else 200)


# ------------------------------------------------------------------ asistente (opcional)
@bp.post("/assistant")
@rate_limit("RATELIMIT_ASSISTANT", "RATELIMIT_ASSISTANT_DAILY")
def assistant_ask():
    cfg = current_app.config
    if not assistant.is_enabled(cfg):
        return jsonify(error="El asistente está desactivado en este despliegue."), 503
    payload = request.get_json(silent=True) or {}
    msg = str(payload.get("message", "")).strip()
    if not msg:
        abort(400, description="Escribe una pregunta.")
    if len(msg) > cfg["ASSISTANT_MAX_INPUT_CHARS"]:
        abort(400, description=f"La pregunta supera {cfg['ASSISTANT_MAX_INPUT_CHARS']} caracteres.")
    try:
        reply = assistant.ask(cfg, store(), panel(), msg)
    except assistant.AssistantUnavailable as e:
        return jsonify(error=str(e)), 503
    except Exception:  # noqa: BLE001 - errores del proveedor: no se exponen detalles
        log.exception("Fallo del proveedor LLM")
        return jsonify(error="El asistente no está disponible en este momento."), 502
    return jsonify(reply=reply, disclaimer=assistant.DISCLAIMER)
