# Atalaya · Analítica Hipotecaria: app web v2

Sitio público de solo lectura (Flask, factory `atalaya.create_app`). No hay administración, no ejecuta código ni entrena modelos:
lee `artifacts/`, `data/forecasts/` y `data/processed/` a través de servicios.

    pip install -r Web/requirements.txt
    ATALAYA_ENV=development python -m flask --app Web/wsgi:app run -p 8100      # desarrollo
    SECRET_KEY=... ATALAYA_ENV=production gunicorn --chdir Web wsgi:app          # producción

Páginas: `/`, `/mercado/precios`, `/mercado/demanda`, `/simulador`, `/asistente` (opcional, desactivado por defecto),
`/modelos/{proyecciones,econometria,metodologia}`, `/datos`, `/caso-de-negocio`. Salud: `/healthz`, `/readyz`.
Si un dominio de `artifacts/` trae `manifest.json` + `views.json` se usa ese contrato; si no, `services/native.py` adapta los ficheros
nativos de cada pipeline. Sin artefacto, la UI muestra estado "no generado". Detalle en `reports/phase2/07_app_v2.md`.
Tests: `python -m pytest -q tests/test_web_*.py`.
