# Atalaya · Plataforma de Analítica Avanzada del Mercado Hipotecario

**TFM — Máster en Business Analytics, IA y Machine Learning · Universidad Francisco de Vitoria**

Plataforma reproducible de analítica del mercado hipotecario español: datos oficiales por API, panel provincial, econometría y predicción validadas con rigor temporal, un simulador hipotecario y una web de presentación. Esta es la **v2**, resultado de una auditoría completa de la v1 (`reports/audit/`).

> **Estado honesto:** el proyecto no está desplegado. Los resultados predictivos son modestos y así se reportan (ningún modelo elegible bate al naive en el hold-out de demanda; la cointegración no es concluyente). El asesor es un simulador informativo, no un motor de admisión crediticia.

## Qué hay
| Componente | Dónde | Descripción |
|---|---|---|
| Pipeline de datos | `src/ingestion`, `src/pipelines` | Conectores INE, BCE, Eurostat y MIVAU, snapshots con hash, validación, reconciliación, informe de actualización |
| Datos | `data/` | `raw/` (snapshots), `processed/` (paneles v2), `metadata/` (catálogo, diccionario, fiscalidad con vigencias, escenarios) |
| Modelos | `src/models` | Econometría (VAR/VECM/Johansen bootstrap/ARDL/panel), forecasting y demanda con rolling-origin y hold-out |
| Asesor | `src/advisor` | Simulador de capacidad de pago y costes de compra |
| Aplicación | `Web/` | Flask de solo lectura que consume `artifacts/` |
| Presentación | `site/` | Vite + React, 14 secciones y estado del pipeline |

## Cómo reproducir
```bash
pip install -r requirements-data.txt -r Web/requirements.txt   # (versiones fijadas)
python -m src.pipelines.update_all --dry-run                   # consulta fuentes sin escribir
python -m src.pipelines.update_all                             # descarga, valida y reconstruye paneles
python -m src.pipelines.build_master --from-raw                # reconstruir paneles sin red
python -m src.models.econometrics.run                          # econometría -> artifacts/econometrics/
python -m src.pipelines.generate_forecasts                     # proyecciones y demanda (~15 min)
python -m pytest -q tests                                      # 179 pruebas
ATALAYA_ENV=development python -m flask --app Web/wsgi:app run -p 8100   # app (ver Web/README.md)
cd site && npm ci && npm run sync-data && npm run build        # web de presentación
```
La actualización semanal automática (`.github/workflows/update-data.yml`) publica en la rama `datos/auto-update`, nunca en `main`; **no se ha ejecutado aún en GitHub**.

## Resultados principales (verificados; ver `docs/MODEL_VALIDATION.md`)
- **Datos:** el panel v1 contenía un error de lectura de `Hipotecas_Total` (382 provincia-trimestre, ~7,7 % de las hipotecas); en la v2 la suma de provincias coincide con el total oficial del INE.
- **Econometría:** bootstrap de Johansen p = 0,168 → modelo principal VAR en diferencias; el VECM de la v1 (r = 1, elasticidad 2,48, ajuste 44 %) no se sostiene con datos limpios.
- **Predicción:** hold-out 2022–2025 (n = 16): ningún modelo elegible mejora al naive a h = 1, 2, 4, 8. Las sendas 2026–2030 son **escenarios condicionales**, con limitaciones listadas.
- **Asesor:** 18 vectores de prueba idénticos en Python y TypeScript; fiscalidad verificada en 38 de 45 reglas.

## Documentación
[`AUDITORIA_TFM.md`](AUDITORIA_TFM.md) · [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/MODEL_VALIDATION.md`](docs/MODEL_VALIDATION.md) · [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) · [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) · [`docs/API_PIPELINE.md`](docs/API_PIPELINE.md)

## Fuentes y licencias
INE, BCE, Eurostat, Ministerio de Vivienda y Agenda Urbana (valor tasado), BOE (legislación consolidada) y proyecciones del BCE/Comisión Europea. Ver `docs/DATA_SOURCES.md`.

## Versión 1 original
La primera versión del proyecto (notebooks, datos brutos y salidas) ya no forma parte del árbol de trabajo; sigue recuperable en el commit `6b418c6` (`git checkout 6b418c6`).

## Autor
Trabajo desarrollado en el contexto del Máster en Business Analytics, IA y ML — Universidad Francisco de Vitoria (2025–2026).
