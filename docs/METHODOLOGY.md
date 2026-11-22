# Metodología (v2)

Este documento resume las decisiones metodológicas del proyecto y su justificación. Cada decisión importante tiene su cadena *problema → evidencia → solución → justificación → antes/después → validación* en `reports/audit/` (auditoría v1) y `reports/phase2/` (implementación v2). Las cifras proceden de scripts ejecutados y de los artefactos de `artifacts/`; ninguna está tecleada a mano en la app ni en la web.

## 1. Datos
- **Panel provincial:** 52 provincias × trimestres. Claves canónicas: `prov_code` (INE 01–52) y `period` (`YYYYQn`). Resolución de nombres por alias explícitos (`src/common/geography.py`), sin *fuzzy matching*: un nombre desconocido lanza error.
- **Frecuencia según naturaleza estadística:** las variables anuales (población, población extranjera, edad media, PIB per cápita provincial) se mantienen **anuales** (`panel_anual.csv`). No se interpolan ni se replican por comodidad; `panel_modelado.csv` las une al panel trimestral con `<var>_ref_year` y la regla de disponibilidad (retraso de publicación) de `data/metadata/availability_rules.yaml`.
- **Variables nacionales y autonómicas** (Euribor, TAE, índices de construcción, IPC…) se identifican con `geo_level` en el diccionario. En el panel solo hay unos 81–86 datos independientes por variable nacional, no 4.368: la inferencia debe tenerlo en cuenta (errores Driscoll-Kraay, efectos temporales).
- **Objetivo de demanda:** hipotecas sobre **viviendas** (número), suma mensual→trimestral por ser un flujo. El total de fincas se conserva como robustez.
- **Precio:** valor tasado de vivienda libre del MIVAU (`precio_m2_mivau_tasado`). Ver `docs/DATA_SOURCES.md`.
- **Sin imputación silenciosa:** el PIB provincial de 2024 de la v1 no era un dato publicado y se elimina; los trimestres con datos mensuales incompletos son NaN.
- **Trazabilidad:** snapshots `data/raw/<fuente>/<AAAAMMDD>/` con hash, `provenance.csv`, catálogo de series, reconciliación suma de provincias = total nacional del INE (ratio 1,0 en los 284 periodos comprobados en la última ejecución).

## 2. Econometría
- Muestra 2005Q1–2026Q2 (T = 86, efectiva 83), sin imputación; el código falla si hay huecos.
- Raíces unitarias (ADF/KPSS, con rupturas), selección de retardos por criterios de información, Johansen con **bootstrap salvaje** (B = 999), Engle-Granger, ARDL-bounds y panel (efectos fijos con Driscoll-Kraay, PMG, CD-test).
- **Regla de decisión pre-especificada:** si la cointegración no supera el 10 % por bootstrap, el modelo principal es un **VAR en diferencias** (con dummies estacionales e impulsos 2020Q2–Q3) y el VECM se presenta como análisis de sensibilidad.
- **Resultado:** p-valor bootstrap de r = 0 igual a 0,168; evidencia *frágil y no concluyente*, no ausente (con 3 retardos el bootstrap rechaza, p = 0,024). Las IRF/FEVD se presentan con rango por ordenación de Cholesky e IRF generalizadas; **no son efectos causales identificados**.

## 3. Predicción
- Rolling-origin expansivo (orígenes 2012Q4–2021Q4) para seleccionar; **hold-out 2022Q1–2025Q4** (n = 16) que no interviene en ninguna decisión.
- Benchmarks: naive, seasonal naive, media móvil, drift, ETS-log, AR/ARIMA/SARIMA, ElasticNet, RF, GBM, XGBoost, LightGBM. Métricas: MAE, RMSE, MAPE, sMAPE, MASE, U de Theil, Diebold-Mariano.
- Sin suelos ni topes ocultos (desaparecen el suelo NAIRU del 8,5 % y el tope CAGR del PIB). PIB per cápita modelizado en frecuencia anual.
- **Las sendas 2026–2030 son condicionales a escenarios** (base/adverso/favorable) declarados en `data/metadata/escenarios_macro.yaml` con fuente y edición. No son predicciones con un error garantizado.

## 4. Asesor hipotecario
Es un **simulador de capacidad de pago y de costes de compra**, no un motor de admisión ni un modelo de pricing. Cuota por amortización francesa; gastos con tabla fiscal con vigencias (ITP/AJD/IVA, aranceles de notaría y registro) y asignación de los gastos del préstamo al banco (Ley 5/2019); tipo de mercado estimado a partir de series publicadas por el BCE, con rango y fecha; semáforo de capacidad con estrés de +3 pp; parámetros de política **ilustrativos**. Se retiraron el GradientBoosting y el ajuste `tanh` por ingresos (no tenían base empírica; ver `reports/phase2/04_asesor_v2.md`).

## 5. Qué no se afirma
- No se afirma causalidad a partir de IRF/FEVD ni de coeficientes de panel.
- No se afirma que SHAP (retirado del flujo del cliente) garantice el cumplimiento del AI Act. La evaluación de solvencia de personas físicas es un caso de alto riesgo (Reglamento (UE) 2024/1689, anexo III); según la verificación realizada, el Reglamento (UE) 2026/1744 aplaza sus obligaciones al 2/12/2027. Un TFM no desplegado queda fuera del ámbito, pero esto no equivale a cumplir.
- No se afirma que el sistema esté desplegado públicamente.
