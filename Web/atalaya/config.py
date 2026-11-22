"""Configuración por entorno de Atalaya · Analítica Hipotecaria.

Entornos (variable ``ATALAYA_ENV``): ``development`` (por defecto), ``testing``, ``production``.
En producción la app NO arranca sin ``SECRET_KEY``: no existe ninguna clave por defecto.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent          # .../Web
REPO_ROOT = WEB_DIR.parent                                  # raíz del repositorio


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


class BaseConfig:
    APP_NAME = "Atalaya · Analítica Hipotecaria"
    ENV_NAME = "base"
    DEBUG = False
    TESTING = False

    SECRET_KEY: str | None = os.environ.get("SECRET_KEY")

    # Rutas de datos (una sola fuente por concepto; sin búsqueda de candidatos dependiente del cwd)
    REPO_ROOT = REPO_ROOT
    ARTIFACTS_DIR = _path("ATALAYA_ARTIFACTS_DIR", REPO_ROOT / "artifacts")
    DATA_DIR = _path("ATALAYA_DATA_DIR", REPO_ROOT / "data")
    # Panel maestro v2 (contrato: data/processed/panel_trimestral.{parquet,csv}).

    # Caché de artefactos: se recargan si cambia el mtime del manifest (comprobado como mucho cada N s)
    ARTIFACT_CACHE_TTL = _int("ATALAYA_ARTIFACT_CACHE_TTL", 30)

    # Sesión / cookies (sólo se usa para el token CSRF; no hay cuentas de usuario)
    SESSION_COOKIE_NAME = "atalaya_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    MAX_CONTENT_LENGTH = 32 * 1024  # 32 KB: no hay subidas de ficheros
    JSON_SORT_KEYS = False

    # Límite de peticiones (en memoria, por IP y endpoint). Formato: (peticiones, ventana_s)
    RATELIMIT_ENABLED = _bool("ATALAYA_RATELIMIT_ENABLED", True)
    RATELIMIT_DEFAULT = (_int("ATALAYA_RATELIMIT_API_PER_MIN", 120), 60)
    RATELIMIT_SIMULATE = (_int("ATALAYA_RATELIMIT_SIMULATE_PER_MIN", 30), 60)
    RATELIMIT_ASSISTANT = (_int("ATALAYA_RATELIMIT_ASSISTANT_PER_MIN", 6), 60)
    RATELIMIT_ASSISTANT_DAILY = (_int("ATALAYA_RATELIMIT_ASSISTANT_PER_DAY", 60), 86400)

    # Proxy inverso (Render, etc.): nº de saltos de X-Forwarded-* en los que se confía
    TRUST_PROXY_HOPS = _int("ATALAYA_TRUST_PROXY_HOPS", 0)

    # Asistente LLM opcional: desactivado por defecto; requiere además GEMINI_API_KEY
    ASSISTANT_ENABLED = _bool("ASSISTANT_ENABLED", False)
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    ASSISTANT_MODEL = os.environ.get("ATALAYA_ASSISTANT_MODEL", "gemini-2.5-flash")
    ASSISTANT_TIMEOUT_S = _int("ATALAYA_ASSISTANT_TIMEOUT_S", 20)
    ASSISTANT_MAX_INPUT_CHARS = 600
    ASSISTANT_MAX_OUTPUT_TOKENS = 700

    # CDN con versión exacta + SRI. Se usa dist/chart.umd.js (fichero estático del paquete npm,
    # ya minificado): el ".min.js" de jsDelivr se genera dinámicamente y no admite SRI estable.
    # Versión recomendada por el sistema de diseño (reports/audit/09_ux.md §5.5).
    CHARTJS_URL = "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.js"
    CHARTJS_SRI = "sha384-zYPBGXwO4633CABX/5Spf6emCKUJCfoOkhOMYyxMsatqQZPnDblmmOewfjsIVWCM"

    # HSTS sólo tiene sentido detrás de HTTPS
    HSTS_ENABLED = False

    @classmethod
    def init_app(cls, app) -> None:  # pragma: no cover - sobrescrito
        pass


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"

    @classmethod
    def init_app(cls, app) -> None:
        if not app.config.get("SECRET_KEY"):
            # Clave aleatoria por proceso: nunca una constante en el código.
            app.config["SECRET_KEY"] = secrets.token_hex(32)


class TestingConfig(DevelopmentConfig):
    ENV_NAME = "testing"
    TESTING = True
    ARTIFACT_CACHE_TTL = 0


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    SESSION_COOKIE_SECURE = _bool("ATALAYA_COOKIE_SECURE", True)
    HSTS_ENABLED = _bool("ATALAYA_HSTS", True)
    TRUST_PROXY_HOPS = _int("ATALAYA_TRUST_PROXY_HOPS", 1)

    @classmethod
    def init_app(cls, app) -> None:
        key = app.config.get("SECRET_KEY")
        if not key or len(key) < 32:
            raise RuntimeError(
                "SECRET_KEY no definida o demasiado corta (mín. 32 caracteres). "
                "En producción la aplicación no arranca sin una clave secreta propia."
            )


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = (name or os.environ.get("ATALAYA_ENV") or "development").strip().lower()
    if name not in CONFIGS:
        raise ValueError(f"ATALAYA_ENV desconocido: {name!r} (usa {', '.join(CONFIGS)})")
    return CONFIGS[name]
