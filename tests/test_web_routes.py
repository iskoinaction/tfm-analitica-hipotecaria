"""Rutas de la app v2: páginas 200, APIs con artefactos de prueba, estados vacíos y superficie retirada."""
import pytest

from test_web_support import app, client, empty_client, make_app  # noqa: F401  (fixtures)

PAGES = ["/", "/mercado/precios", "/mercado/demanda", "/simulador", "/asistente", "/modelos/proyecciones",
         "/modelos/econometria", "/modelos/metodologia", "/datos", "/caso-de-negocio"]


@pytest.mark.parametrize("path", PAGES)
def test_pages_200_with_artifacts(client, path):
    r = client.get(path)
    assert r.status_code == 200
    assert "Atalaya" in r.get_data(as_text=True)


@pytest.mark.parametrize("path", PAGES)
def test_pages_200_without_artifacts_or_panel(empty_client, path):
    assert empty_client.get(path).status_code == 200


def test_health(client):
    assert client.get("/healthz").get_json()["status"] == "ok"
    rz = client.get("/readyz").get_json()
    assert rz["panel"] is True and rz["artifacts"]["demand"] == "ok"


def test_readyz_degraded_without_artifacts(empty_client):
    rz = empty_client.get("/readyz").get_json()
    assert rz["status"] == "degraded" and rz["artifacts"]["forecasting"] == "missing"


def test_empty_state_shows_command_and_no_figures(empty_client):
    html = empty_client.get("/modelos/econometria").get_data(as_text=True)
    assert "Artefacto no generado" in html
    assert "python -m src.pipelines" in html


def test_artifact_provenance_rendered(client):
    html = client.get("/mercado/demanda").get_data(as_text=True)
    assert "INE Estadística de Hipotecas" in html          # fuente
    assert "21/11/2026 18:00 UTC" in html                    # fecha de generación
    assert "Error de validación" in html                     # vista embebida (JSON)


@pytest.mark.parametrize("path,target", [("/hipotecas", "/simulador"), ("/vecm", "/modelos/econometria"),
                                         ("/webscrapping", "/datos"), ("/business_case", "/caso-de-negocio")])
def test_legacy_redirects(client, path, target):
    r = client.get(path)
    assert r.status_code == 301 and r.headers["Location"].endswith(target)


@pytest.mark.parametrize("method,path", [
    ("get", "/admin"), ("post", "/admin"), ("get", "/login_admin"), ("post", "/login"),
    ("post", "/admin/execute-code"), ("post", "/admin/upload-chart"), ("get", "/test-hipoteca"),
    ("post", "/api/noa-strategic"), ("post", "/api/noa-chat"), ("post", "/api/chat"),
    ("get", "/api/custom-charts"), ("delete", "/api/custom-charts/x"), ("get", "/api/mapa/tension"),
])
def test_removed_surface_is_404(client, method, path):
    # Sin token CSRF las peticiones no seguras se rechazan antes (400); con token, 404.
    from test_web_support import csrf_of
    headers = {"X-CSRF-Token": csrf_of(client)}
    assert getattr(client, method)(path, headers=headers).status_code == 404


def test_panel_apis(client):
    s = client.get("/api/v1/panel/series?var=precio_m2_mivau_tasado").get_json()
    assert s["aggregation"] == "serie nacional del panel" and s["x"][-1] == "2025Q3"
    assert s["var_source"].startswith("MIVAU")
    p = client.get("/api/v1/panel/series?var=hipotecas_viviendas_num&prov=Málaga").get_json()
    assert p["scope"] == "Málaga" and len(p["values"]) == 5
    ch = client.get("/api/v1/panel/choropleth?var=precio_m2_mivau_tasado").get_json()
    assert ch["period"] == "2025Q3" and len(ch["values"]) == 52
    rk = client.get("/api/v1/panel/ranking?var=hipotecas_viviendas_num&n=5").get_json()
    assert len(rk["labels"]) == 5
    k = client.get("/api/v1/panel/kpis").get_json()["kpis"]
    assert {x["key"] for x in k} >= {"hipotecas_viviendas_num", "precio_m2_mivau_tasado"}


def test_panel_api_bad_input(client):
    assert client.get("/api/v1/panel/series?var=__import__").status_code == 400
    assert client.get("/api/v1/panel/series?var=tasa_paro&prov=Atlantida").status_code == 400
    assert client.get("/api/v1/panel/choropleth?var=tasa_paro&period=1900Q1").status_code == 400


def test_panel_unavailable_is_503(empty_client):
    assert empty_client.get("/api/v1/panel/series").status_code == 503


def test_tinsa_never_exposed(client):
    assert client.get("/api/v1/panel/series?var=precio_m2_tinsa").status_code == 400
    vars_ = client.get("/api/v1/panel/variables").get_json()["variables"]
    assert all("tinsa" not in v["key"] for v in vars_)
    assert "tinsa" not in client.get("/mercado/precios").get_data(as_text=True).lower()


def test_artifact_api_and_scopes(client):
    d = client.get("/api/v1/artifacts/demand").get_json()
    types = [v["type"] for v in d["views"]]
    assert types == ["metrics", "timeseries", "table", "invalid"]  # la vista rota se marca, no se inventa
    sc = client.get("/api/v1/artifacts/demand/scope/provincial/28").get_json()
    assert sc["available"] is True and sc["views"][0]["type"] == "metrics"
    assert client.get("/api/v1/artifacts/demand/scope/provincial/08").get_json()["available"] is False
    assert client.get("/api/v1/artifacts/../../etc").status_code == 404
    assert client.get("/api/v1/artifacts/otro").status_code == 404
