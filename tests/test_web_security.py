"""Seguridad de la app v2: CSP/cabeceras, CSRF, rate limiting, configuración y asistente."""
import re

import pytest

from test_web_support import app, client, csrf_of, make_app  # noqa: F401  (fixtures)


def test_security_headers_and_csp(client):
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    html = r.get_data(as_text=True)
    # todos los <script> ejecutables llevan el nonce de la respuesta; no hay scripts inline
    for tag in re.findall(r"<script\b[^>]*>", html):
        if 'type="application/json"' in tag:
            continue
        assert f'nonce="{nonce}"' in tag and "src=" in tag
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Server" not in r.headers
    assert client.get("/api/v1/meta").headers["Cache-Control"] == "no-store"


def test_cdn_pinned_with_sri(client):
    html = client.get("/").get_data(as_text=True)
    m = re.search(r'<script[^>]+src="(https://cdn[^"]+)"[^>]*>', html)
    assert m and re.search(r"@\d+\.\d+\.\d+/", m.group(1))
    assert 'integrity="sha384-' in m.group(0) and 'crossorigin="anonymous"' in m.group(0)


def test_no_inline_styles_or_handlers_in_html(client):
    for path in ["/", "/simulador", "/datos", "/mercado/demanda"]:
        html = client.get(path).get_data(as_text=True)
        assert not re.search(r"\sstyle=\"", html), path
        assert not re.search(r"\son[a-z]+=\"", html), path


def test_session_cookie_flags(client):
    r = client.get("/simulador")
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_csrf_required_on_post(client):
    body = {"prov_code": "28"}
    assert client.post("/api/v1/simulator/simulate", json=body).status_code == 400
    bad = client.post("/api/v1/simulator/simulate", json=body, headers={"X-CSRF-Token": "falso"})
    assert bad.status_code == 400 and "CSRF" in bad.get_json()["error"]
    ok = client.post("/api/v1/simulator/simulate", json=body, headers={"X-CSRF-Token": csrf_of(client)})
    assert ok.status_code == 400 and "errors" in ok.get_json()  # pasa CSRF; falla la validación de campos


def test_rate_limit_simulator(tmp_path):
    app = make_app(tmp_path, RATELIMIT_SIMULATE=(3, 60))
    c = app.test_client()
    h = {"X-CSRF-Token": csrf_of(c)}
    codes = [c.post("/api/v1/simulator/simulate", json={}, headers=h).status_code for _ in range(5)]
    assert codes[:3] == [400, 400, 400] and codes[3:] == [429, 429]
    r = c.post("/api/v1/simulator/simulate", json={}, headers=h)
    assert "Retry-After" in r.headers


def test_body_size_limit(client):
    h = {"X-CSRF-Token": csrf_of(client)}
    r = client.post("/api/v1/simulator/simulate", data="x" * 100_000, headers=h, content_type="application/json")
    assert r.status_code == 413


def test_production_requires_secret_key(tmp_path):
    from atalaya import create_app
    with pytest.raises(RuntimeError):
        create_app("production", {"SECRET_KEY": None, "ARTIFACTS_DIR": tmp_path, "DATA_DIR": tmp_path})
    app = create_app("production", {"SECRET_KEY": "k" * 40, "ARTIFACTS_DIR": tmp_path, "DATA_DIR": tmp_path})
    assert app.config["SESSION_COOKIE_SECURE"] is True and app.debug is False
    assert "Strict-Transport-Security" in app.test_client().get("/healthz").headers


def test_no_debug_and_unknown_errors_hidden(client, app):
    assert app.debug is False
    r = client.get("/api/v1/panel/series?var=x")
    assert "Traceback" not in r.get_data(as_text=True)


def test_assistant_disabled_by_default(client):
    assert "/asistente" not in client.get("/").get_data(as_text=True).split("<main")[0]  # fuera del menú
    r = client.post("/api/v1/assistant", json={"message": "hola"}, headers={"X-CSRF-Token": csrf_of(client)})
    assert r.status_code == 503
    assert "No es asesoramiento financiero" in client.get("/asistente").get_data(as_text=True)


def test_assistant_context_has_no_personal_data(tmp_path, monkeypatch):
    """El asistente sólo ve artefactos agregados; no recibe el cuerpo del simulador."""
    from atalaya.services import assistant
    app = make_app(tmp_path, ASSISTANT_ENABLED=True, GEMINI_API_KEY="dummy", RATELIMIT_ASSISTANT=(2, 60))
    captured = {}

    def fake_ask(config, store, panel, message):
        captured["ctx"] = assistant.build_context(store, panel)
        return "<b>texto</b>"

    monkeypatch.setattr(assistant, "ask", fake_ask)
    c = app.test_client()
    h = {"X-CSRF-Token": csrf_of(c)}
    c.post("/api/v1/simulator/simulate", json={"ingresos_netos_mensuales": 31337, "prov_code": "28"}, headers=h)
    r = c.post("/api/v1/assistant", json={"message": "¿Qué error tiene el modelo?"}, headers=h)
    assert r.status_code == 200 and r.get_json()["reply"] == "<b>texto</b>"  # se devuelve como texto; el cliente usa textContent
    assert "31337" not in captured["ctx"] and "ingresos" not in captured["ctx"]
    assert c.post("/api/v1/assistant", json={"message": "x" * 5000}, headers=h).status_code == 400
    assert c.post("/api/v1/assistant", json={"message": "otra"}, headers=h).status_code == 429


def test_no_caixabank_ni_tinsa_en_web():
    """Ningún rastro de CaixaBank en Web/ y ninguna plantilla/JS que muestre series de Tinsa."""
    from pathlib import Path
    web = Path(__file__).resolve().parents[1] / "Web"
    for f in web.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts and f.suffix in {".py", ".html", ".js", ".css", ".md", ".txt", ".svg", ".yaml", ".json"}:
            low = f.read_text(encoding="utf-8", errors="ignore").lower()
            assert "caixa" not in low, f"rastro de CaixaBank en {f}"
            if f.suffix in {".html", ".js"}:
                assert "tinsa" not in low, f"Tinsa en {f}"
