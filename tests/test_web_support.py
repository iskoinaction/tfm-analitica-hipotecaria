"""Utilidades compartidas por los tests de la app web v2 (tests/test_web_*.py).

Construyen un ``artifacts/`` y un ``data/`` mínimos en un directorio temporal, de modo que los
tests no dependen de los artefactos reales (que regeneran los pipelines).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "Web"
for p in (str(WEB), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from atalaya import create_app  # noqa: E402
from atalaya.security import limiter  # noqa: E402

PROVS = [f"{i:02d}" for i in range(1, 53)]
PERIODS = ["2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3"]


def write_panel(data_dir: Path, with_tinsa: bool = True) -> None:
    processed = data_dir / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    cols = ["prov_code", "period", "hipotecas_viviendas_num", "precio_m2_mivau_tasado", "euribor_12m", "tasa_paro"]
    if with_tinsa:
        cols.append("precio_m2_tinsa")
    lines = [",".join(cols)]
    for pi, per in enumerate(PERIODS):
        for i, code in enumerate(PROVS):
            row = [code, per, str(100 + i + pi), f"{1500 + 10 * i:.1f}", "2.5", f"{10 + i % 5:.1f}"]
            if with_tinsa:
                row.append("9999.9")
            lines.append(",".join(row))
    (processed / "panel_trimestral.csv").write_text("\n".join(lines), encoding="utf-8")
    nat = ["period,hipotecas_viviendas_num,precio_m2_mivau_tasado,euribor_12m,tasa_paro"]
    for pi, per in enumerate(PERIODS):
        nat.append(f"{per},{5000 + 100 * pi},{1700 + pi},2.5,11.0")
    (processed / "nacional_trimestral.csv").write_text("\n".join(nat), encoding="utf-8")
    meta = data_dir / "metadata"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "data_dictionary.csv").write_text(
        "panel,columna,geo_level,unidad,frecuencia_origen,agregacion_trimestral,fuente,dataset,tabla_o_serie,descripcion\n"
        "panel_trimestral,precio_m2_mivau_tasado,provincia,€/m²,Q,none,mivau,mivau_valor_tasado,VDP006_01,Valor tasado\n"
        "panel_trimestral,hipotecas_viviendas_num,provincia,número,M,sum,ine,ine_hipotecas,3200,Hipotecas\n",
        encoding="utf-8")
    (meta / "series_catalog.yaml").write_text(
        "- dataset: ine_hipotecas\n  fuente: ine\n  tabla_o_clave: '3200'\n  frecuencia: M\n"
        "  url_documentacion: https://www.ine.es/\n", encoding="utf-8")


VIEWS = [
    {"type": "metrics", "title": "Error de validación", "items": [{"label": "MAPE test", "value": 6.25, "unit": "%"}]},
    {"type": "timeseries", "title": "Hipotecas: observado y proyección", "unit": "nº",
     "x": ["2025Q3", "2025Q4", "2026Q1"],
     "series": [{"name": "Observado", "values": [100, None, None], "role": "historical"},
                {"name": "Proyección", "values": [None, 110, 115], "role": "forecast"},
                {"name": "IC 80 % inf.", "values": [None, 100, 101], "role": "lower"},
                {"name": "IC 80 % sup.", "values": [None, 120, 129], "role": "upper"}]},
    {"type": "table", "title": "Benchmark", "columns": ["Modelo", "MAPE"], "rows": [["RF", 6.3]]},
    {"type": "bar", "title": "Ruptura", "labels": ["a"], "series": [{"name": "x", "values": ["no-num"]}]},
]


def write_artifact(root: Path, domain: str, views=None, manifest_extra=None, scopes=None) -> Path:
    d = root / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / "views.json").write_text(json.dumps({"views": views if views is not None else VIEWS}), encoding="utf-8")
    manifest = {"domain": domain, "version": "test-1", "generated_at": "2026-11-21T18:00:00Z",
                "generator": f"python -m src.pipelines.test_{domain}", "data_cutoff": "2025Q4",
                "sources": [{"name": "INE Estadística de Hipotecas", "url": "https://www.ine.es/", "series_id": "3200"}],
                "views": ["views.json"]}
    if scopes:
        (d / "prov.json").write_text(json.dumps(scopes), encoding="utf-8")
        manifest["scopes"] = {"provincial": "prov.json"}
    manifest.update(manifest_extra or {})
    (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return d


def make_app(tmp_path: Path, artifacts: bool = True, panel: bool = True, **overrides):
    art, data = tmp_path / "artifacts", tmp_path / "data"
    art.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    if panel:
        write_panel(data)
    if artifacts:
        for dom in ("econometrics", "forecasting", "advisor", "data_quality"):
            write_artifact(art, dom)
        write_artifact(art, "demand", scopes={"28": [VIEWS[0]]})
    cfg = {"ARTIFACTS_DIR": art, "DATA_DIR": data, "ALLOW_LEGACY_PANEL": False, "RATELIMIT_ENABLED": True,
           "SECRET_KEY": "x" * 40}
    cfg.update(overrides)
    limiter.reset()
    return create_app("testing", cfg)


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def empty_client(tmp_path):
    return make_app(tmp_path, artifacts=False, panel=False).test_client()


def csrf_of(client) -> str:
    html = client.get("/simulador").get_data(as_text=True)
    marker = 'name="csrf-token" content="'
    i = html.index(marker) + len(marker)
    return html[i:html.index('"', i)]
