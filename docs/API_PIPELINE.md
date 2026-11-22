# Pipeline de datos automatizado (v2)

## Uso
```bash
python -m src.pipelines.update_all                  # descarga todo, snapshot raw, reconcilia, valida, reconstruye paneles e informe
python -m src.pipelines.update_all --dry-run        # sin escribir raw/staging/processed
python -m src.pipelines.update_all --source ine      # ine | ecb | eurostat | mivau
python -m src.pipelines.update_all --dataset ine_hipotecas
python -m src.pipelines.update_all --since 20250101 # incremental: INE (date=) y BCE (startPeriod), fusionado con el último snapshot
python -m src.pipelines.update_all --rebuild        # sin red: borra staging/processed y reconstruye desde el último raw
python -m src.pipelines.update_all --rebuild --refetch  # snapshot completo nuevo + reconstrucción
```
Salida: `data/raw/<fuente>/<AAAAMMDD>/` (snapshot + `.meta.json` con sha256; nunca se sobrescribe un raw existente),
`data/staging/`, `data/processed/panel_*.csv`, e informe `artifacts/data_quality/update_report_<fecha>.{md,json}`
(nuevas/revisadas/eliminadas por variable, incidencias, modelos a recalibrar, watcher fiscal).
Un conector caído no detiene al resto; un dataset con errores de validación conserva su staging anterior.

## Variables → método
| Variable v2 | Fuente | Método |
|---|---|---|
| hipotecas (fincas/viviendas, nº e importe), compraventas, paro, IPC, IPV, población (ECP), edad media, PIB pc, PIB nacional, tasa de ahorro, mano de obra | INE Tempus3 | API oficial |
| euribor_12m, TAE/TEDR vivienda | BCE Data Portal | API oficial (SDMX) |
| índice coste construcción | Eurostat | API oficial |
| precio_m2_mivau_tasado | MIVAU VDP006_01.csv | descarga oficial automatizable (CSV fijo, sin API; datos.gob.es) |
| fiscalidad | `data/metadata/fiscalidad_vigencias.csv` | **curada manual**; no existe API de tipos. Watcher BOE avisa de cambios normativos |

Paso manual restante: solo la tabla fiscal.

## Watcher fiscal
`src/ingestion/fiscalidad.py` consulta `legislacion-consolidada/id/{boe_id}/metadatos` del BOE para cada norma de la tabla y compara
`fecha_actualizacion` con `fecha_verificacion`; si es posterior marca "revisión fiscal requerida" en el informe. Nunca modifica tipos. Tolerante a fallos de red.

## Vintages y limitaciones
- INE solo sirve la última versión: los snapshots fechados son el vintage propio. BCE admite `includeHistory=true` (no usado por defecto). MIVAU sobrescribe el fichero.
- Los datos provisionales se revisan; el informe lista observaciones revisadas entre snapshots.
- Retrasos de publicación: ver `reports/audit/10_fuentes.md` §3 (evitar look-ahead; `data/metadata/availability_rules.yaml`).
- PIB pc provincial 2025 no existe aún; INE tasa de ahorro/mano de obra tienen retraso de 3-6 meses.

## Automatización
- GitHub Actions: `.github/workflows/update-data.yml` (lunes 06:17 UTC + manual); commitea en la rama `datos/auto-update` (nunca main, sin force push) y sube el informe como artifact. Dependencias: `requirements-data.txt`.
- Cron local alternativo: `17 6 * * 1 cd /ruta/repo && python -m src.pipelines.update_all >> logs/update.log 2>&1`.

## Cómo recalibrar
El informe incluye "Modelos que requieren recalibración" según `data/metadata/model_dependencies.yaml` (variable → modelos).
Si la lista no está vacía, reejecutar `python -m src.pipelines.generate_forecasts` y los módulos de modelos indicados.
