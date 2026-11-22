# Fase 2 · Pipeline de datos v2

## Estado
Pipeline implementado y probado: `src/ingestion` (INE, BCE, Eurostat, MIVAU, Tinsa legado, watcher fiscal BOE), `src/validation`,
`src/pipelines/{update_all,build_master}.py`, workflow semanal, `docs/API_PIPELINE.md`.
Tests de datos: 24 pasan (`pytest tests/test_data_*.py`).

## Ejecución real (2026-11-22)
`python -m src.pipelines.update_all`: 16 datasets, 0 errores, 0 variables con cambios respecto al snapshot del día anterior
(sin modelos a recalibrar). Panel v2 (`data/processed/panel_trimestral.csv`): 4.524 filas, 52 provincias, 2005Q1-2026Q3,
0 duplicados (prov_code, period). Suma de provincias = total nacional INE en hipotecas (ratio 1,0 en 284 periodos). Watcher fiscal: sin normas
actualizadas después de la verificación (2026-11-22).

## Antes/después v1 vs v2 (`artifacts/data_quality/v1_vs_v2.csv`)
| Variable | Resultado |
|---|---|
| Hipotecas_Total | v1 corrupto por formato de miles; 88,64 % iguales, dif. máx. 369,9 %; media v1 3.393,9 vs v2 3.676,0 |
| Transmisiones | 96,94 % iguales; 2005-06 NaN en v2 (416 celdas) |
| Tasa_Paro | 100 % iguales |
| IPC | 99,18 % iguales |
| Precio_m2 | Tinsa 100 % (legado); MIVAU 5,01 % iguales, mediana dif. 5,9 %, medias 1.406,9 vs 1.408,2 |
| Euribor / Spread | 89,29 % / 82,14 % iguales (media trimestral de mensuales vs FM.Q) |
| tasa_ahorro | 87,95 % iguales; +52 celdas nuevas |
| Mano de obra | 100 %; +156 celdas nuevas |
| Indice_Materiales | no comparable (media de 14 subíndices vs índice Eurostat): media 2.161,8 vs 91,8 |
| Poblacion / Pob_Ext | 60,71 % / 7,33 % iguales (Padrón+OPI vs ECP homogénea) |
| Edad_Media | 100 % |
| PIB_pc | 94,62 % iguales; +9 nuevas; v1 imputaba 2024 |

## Validaciones
Formato de miles (detector de enteros), rangos, duplicados, saltos (MAD), total nacional vs suma provincial, esquema de respuesta de cada API,
reconciliación entre snapshots (nuevas/revisadas/eliminadas), esquema/vigencias de la tabla fiscal.

## Pendiente / limitaciones
- Tinsa y fiscalidad siguen manuales (decisión de diseño). MIVAU no es API (CSV oficial).
- Workflow no ejecutado en GitHub (solo escrito); probar con workflow_dispatch.
- Modo incremental implementado para INE y BCE; no ejecutado en la prueba real (solo update completo).
