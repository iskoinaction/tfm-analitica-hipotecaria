"""Atalaya · Analítica Hipotecaria — aplicación Flask v2 (application factory).

Uso:
    from atalaya import create_app
    app = create_app()            # ATALAYA_ENV=development|testing|production

La app es un sitio público de sólo lectura: no hay cuentas, rol de administración, subidas de
ficheros ni ejecución de código. Lee artefactos versionados de ``artifacts/`` generados por los
pipelines de ``src/`` y delega el cálculo del asesor en ``src.advisor``.
"""
from __future__ import annotations

import logging
import sys
from logging.config import dictConfig

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .config import REPO_ROOT, get_config

__version__ = "2.0.0"

# `src` (motor del asesor, catálogo de provincias) vive en la raíz del repositorio.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _configure_logging(level: str) -> None:
    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std", "stream": "ext://sys.stderr"}},
        "root": {"level": level, "handlers": ["console"]},
    })


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    cfg = get_config(config_name)
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(cfg)
    if overrides:
        app.config.update(overrides)
    cfg.init_app(app)
    if not app.config.get("TESTING"):
        _configure_logging("INFO")

    if app.config.get("TRUST_PROXY_HOPS"):
        from werkzeug.middleware.proxy_fix import ProxyFix
        hops = int(app.config["TRUST_PROXY_HOPS"])
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    # ---------------------------------------------------------------- servicios
    from .services.artifacts import ArtifactStore
    from .services.panel import PanelService

    app.extensions["atalaya.artifacts"] = ArtifactStore(app.config["ARTIFACTS_DIR"], app.config["ARTIFACT_CACHE_TTL"])
    app.extensions["atalaya.panel"] = PanelService(
        app.config["DATA_DIR"], app.config["LEGACY_PANEL_PATH"], app.config["ALLOW_LEGACY_PANEL"])

    # ---------------------------------------------------------------- seguridad
    from . import security

    @app.before_request
    def _csrf():
        try:
            security.verify_csrf()
        except security.CSRFError:
            if request.path.startswith("/api/"):
                return jsonify(error="Token CSRF ausente o no válido. Recarga la página."), 400
            return render_template("errors/error.html", code=400,
                                   message="La sesión del formulario ha caducado. Recarga la página."), 400
        return None

    app.after_request(security.apply_security_headers)

    # ---------------------------------------------------------------- plantillas
    from .services.assistant import is_enabled as assistant_enabled
    from .templating import register_template_helpers

    register_template_helpers(app)

    @app.context_processor
    def _inject():
        return {
            "csrf_token": security.csrf_token,
            "csp_nonce": security.csp_nonce,
            "app_name": app.config["APP_NAME"],
            "app_version": __version__,
            "assistant_enabled": assistant_enabled(app.config),
            "chartjs_url": app.config["CHARTJS_URL"],
            "chartjs_sri": app.config["CHARTJS_SRI"],
        }

    # ---------------------------------------------------------------- rutas
    from .blueprints.api import bp as api_bp
    from .blueprints.health import bp as health_bp
    from .blueprints.pages import bp as pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(health_bp)

    # ---------------------------------------------------------------- errores
    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=e.description or e.name), e.code
        return render_template("errors/error.html", code=e.code, message=e.description), e.code

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        app.logger.exception("Error no controlado en %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify(error="Error interno. El incidente ha quedado registrado."), 500
        return render_template("errors/error.html", code=500,
                               message="Se ha producido un error interno."), 500

    logging.getLogger(__name__).info("Atalaya %s iniciado (entorno %s)", __version__, app.config["ENV_NAME"])
    return app
