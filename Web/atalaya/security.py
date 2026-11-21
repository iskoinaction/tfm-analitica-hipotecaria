"""Seguridad transversal: CSRF, límite de peticiones, CSP con nonce y cabeceras.

Implementación propia y sin dependencias para que sea auditable en pocas líneas:

* CSRF: token aleatorio por sesión (``session['csrf']``), comparado en tiempo constante.
  Se exige en todo método no seguro (POST/PUT/PATCH/DELETE), en campo de formulario
  ``csrf_token`` o en la cabecera ``X-CSRF-Token`` (peticiones ``fetch``).
* Rate limiting: ventana fija en memoria por (IP, clave). Suficiente para 1 proceso/pocos
  workers; para despliegues con varias réplicas, sustituir por Redis (misma interfaz).
* CSP: ``script-src 'self' 'nonce-…'`` + el CDN con versión fija; sin ``unsafe-inline``.
"""
from __future__ import annotations

import hmac
import secrets
import threading
import time
from functools import wraps

from flask import current_app, g, jsonify, request, session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ─────────────────────────────── CSRF ────────────────────────────────
def csrf_token() -> str:
    tok = session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(32)
        session["csrf"] = tok
    return tok


class CSRFError(Exception):
    pass


def verify_csrf() -> None:
    if request.method in SAFE_METHODS:
        return
    if request.endpoint and getattr(current_app.view_functions.get(request.endpoint), "_csrf_exempt", False):
        return
    expected = session.get("csrf")
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if not expected or not sent or not hmac.compare_digest(str(expected), str(sent)):
        raise CSRFError("Token CSRF ausente o no válido")


# ─────────────────────────── Rate limiting ───────────────────────────
class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[tuple, tuple[int, float]] = {}

    def hit(self, key: tuple, limit: int, window: int) -> tuple[bool, int]:
        """Registra un acceso. Devuelve (permitido, segundos_hasta_reset)."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 50_000:  # protección de memoria
                self._hits = {k: v for k, v in self._hits.items() if v[1] > now}
            count, reset = self._hits.get(key, (0, now + window))
            if now >= reset:
                count, reset = 0, now + window
            count += 1
            self._hits[key] = (count, reset)
            return count <= limit, max(1, int(reset - now))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip() -> str:
    return request.remote_addr or "unknown"


def rate_limit(*config_keys: str):
    """Decorador: aplica uno o varios límites definidos en la config (tuplas (n, ventana_s))."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_app.config.get("RATELIMIT_ENABLED", True):
                for ck in config_keys:
                    limit, window = current_app.config[ck]
                    ok, retry = limiter.hit((client_ip(), fn.__name__, ck), limit, window)
                    if not ok:
                        resp = jsonify(error="Demasiadas peticiones. Inténtalo más tarde.", retry_after_s=retry)
                        resp.status_code = 429
                        resp.headers["Retry-After"] = str(retry)
                        return resp
            return fn(*args, **kwargs)

        return wrapper

    return deco


# ─────────────────────────── Cabeceras / CSP ─────────────────────────
def csp_nonce() -> str:
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


def build_csp() -> str:
    cdn = "https://cdn.jsdelivr.net"
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{csp_nonce()}' {cdn}",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


def apply_security_headers(response):
    response.headers["Content-Security-Policy"] = build_csp()
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if current_app.config.get("HSTS_ENABLED"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.pop("Server", None)
    return response
