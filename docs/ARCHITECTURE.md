# Arquitectura (v2)

```
Fuentes oficiales ──► src/ingestion (conector por fuente) ──► data/raw/<fuente>/<AAAAMMDD>/  (snapshot + sha256 + manifest)
                                              │
                                              ▼
                       src/transformations + src/validation ──► data/staging/  (formato largo + metadatos)
                                              │
                                              ▼
                              src/pipelines/build_master.py ──► data/processed/ (panel_trimestral, panel_anual,
                                              │                                  panel_modelado, nacional_trimestral)
                  ┌───────────────────────────┼────────────────────────────┐
                  ▼                           ▼                            ▼
   src/models/econometrics        src/models/forecasting + demand      src/advisor (motor puro)
   artifacts/econometrics/        artifacts/forecasting|demand/        artifacts/advisor/
                                  data/forecasts/
                  └───────────────────────────┬────────────────────────────┘
                                              ▼
                  Web/atalaya (Flask, solo lectura)        site/ (Vite + React, presentación)
```

| Directorio | Contenido |
|---|---|
| `src/common/` | geografía INE canónica, periodos, HTTP (reintentos, timeouts), IO, configuración |
| `src/ingestion/` | `ine.py`, `ecb.py`, `eurostat.py`, `vivienda.py` (MIVAU), `fiscalidad.py` (watcher BOE), `registry.py` |
| `src/pipelines/` | `update_all.py` (`--dry-run`, `--source`, `--since`, `--rebuild`), `build_master.py`, `generate_forecasts.py` |
| `src/models/` | `econometrics/`, `forecasting/`, `demand/` |
| `src/advisor/` | motor del simulador hipotecario (sin Flask) |
| `data/metadata/` | catálogo de series, procedencia, diccionario, reglas de disponibilidad, fiscalidad con vigencias, escenarios macro, política del asesor |
| `artifacts/` | resultados generados (JSON/CSV) que consumen la app y la web |
| `Web/atalaya/` | app Flask: factory, blueprints, servicios que **solo leen artefactos** (no entrenan al arrancar), seguridad (CSRF, límites, CSP), `/healthz`, `/readyz` |
| `site/` | web independiente de presentación; `npm run sync-data` copia datos reales a `public/data/` |
| `reports/audit/`, `reports/phase2/` | auditoría de la v1 (histórico; la v1 original está en el commit `6b418c6`) y registros de implementación v2 |

**Principios:** un conector independiente por fuente; nunca se sobrescribe un raw; los modelos solo se recalibran si cambia una variable de la que dependen (`data/metadata/model_dependencies.yaml`); la app y la web no contienen cifras de modelos escritas a mano; si falta un artefacto muestran un estado vacío con el comando para generarlo.

**Despliegue:** `Procfile`, `render.yaml` y `Dockerfile` para la app; `site/vercel.json` para la web. Ninguno de los dos está desplegado a fecha de este documento. Actualización automática: `.github/workflows/update-data.yml` (semanal, rama `datos/auto-update`, nunca `main`); ver `docs/API_PIPELINE.md`.
