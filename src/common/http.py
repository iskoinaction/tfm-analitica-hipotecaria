"""Cliente HTTP común: timeouts, reintentos con backoff exponencial, límite de peticiones por host y
validación básica del tipo de respuesta. Sin credenciales; User-Agent identificable."""
from __future__ import annotations

import logging
import threading
import time
from urllib.parse import urlparse

import requests

from . import config

log = logging.getLogger("etl.http")
RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    pass


class _RateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def wait(self, host: str):
        rate = config.RATE_LIMIT_PER_SEC.get(host, config.RATE_LIMIT_PER_SEC["default"])
        with self._lock:
            now = time.monotonic()
            t = max(now, self._next.get(host, 0.0))
            self._next[host] = t + 1.0 / rate
        if t > now:
            time.sleep(t - now)


_LIMITER = _RateLimiter()
_SESSION = threading.local()


def _session() -> requests.Session:
    s = getattr(_SESSION, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": config.USER_AGENT})
        _SESSION.s = s
    return s


def get(url: str, params: dict | None = None, expect: str = "json", headers: dict | None = None,
        retries: int = config.HTTP_RETRIES, timeout=config.HTTP_TIMEOUT):
    """GET con reintentos. ``expect``: 'json' (devuelve objeto), 'text' o 'bytes'.

    Devuelve (payload, info) donde info incluye url final, status, cabeceras útiles y fecha UTC de descarga.
    Lanza HttpError tras agotar reintentos o ante 4xx no recuperable.
    """
    host = urlparse(url).netloc
    last_exc = None
    for attempt in range(retries + 1):
        _LIMITER.wait(host)
        try:
            r = _session().get(url, params=params, headers=headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            log.warning("red %s (%s/%s): %s", url, attempt + 1, retries + 1, e)
        else:
            if r.status_code in RETRY_STATUS:
                last_exc = HttpError(f"HTTP {r.status_code} {r.url}")
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    time.sleep(min(int(ra), 60))
            elif r.status_code >= 400:
                raise HttpError(f"HTTP {r.status_code} {r.url}: {r.text[:200]}")
            else:
                info = {"url": r.url, "status": r.status_code,
                        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "last_modified": r.headers.get("Last-Modified"), "etag": r.headers.get("ETag"),
                        "content_type": r.headers.get("Content-Type")}
                if expect == "json":
                    try:
                        payload = r.json()
                    except ValueError:
                        # El INE devuelve a veces HTML/texto de error con HTTP 200
                        last_exc = HttpError(f"Respuesta no JSON en {r.url}: {r.text[:150]!r}")
                        payload = None
                    if payload is not None:
                        return payload, info
                elif expect == "text":
                    return r.text, info
                else:
                    return r.content, info
        if attempt < retries:
            time.sleep(config.HTTP_BACKOFF * 2 ** attempt)
    raise HttpError(f"Agotados reintentos para {url}: {last_exc}")
