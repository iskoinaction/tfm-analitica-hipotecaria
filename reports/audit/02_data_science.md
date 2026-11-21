# 02 — Auditoría de Data Science / ML y forecasting (Fase V)

Ámbito: modelo de demanda `RF_Nac` y benchmark del notebook 4, uso en la app (`Web/demanda_models.py`, `/api/demanda-data`),
proyecciones 2026-2030 del notebook 5 (`predicciones_provinciales_2026_2030.csv`), salidas huérfanas de `outputs/`, y la validación del GBR de spread.

Todas las cifras de este informe salen de los scripts de `reports/audit/02_ds/` (resultados en `reports/audit/02_ds/out/`),
ejecutados el 2026-11-21 con Python 3.13, scikit-learn 1.9.1, xgboost 3.4.1, lightgbm 4.7.0, statsmodels 0.15.0, pandas 3.0.5 y n_jobs ≤ 2.

| Script | Qué hace | Salida |
|---|---|---|
| `02_ds/common.py` | Réplica literal del feature engineering del nb4 (celdas 7, 11, 13 y 19) y de las métricas | — |
| `02_ds/01_reproduce_rfnac.py` | Reproduce los modelos provinciales y nacionales, la sensibilidad a la semilla, las variantes sin features contemporáneas y los naive sobre el mismo test | `out/01_reproduce_rfnac.json` |
| `02_ds/02_rolling_origin.py` | Benchmark rolling-origin con 40 orígenes, h = 1, 2, 3, 4 y 8, y test Diebold-Mariano | `out/02_rolling_*.csv/json` |
| `02_ds/03_projections_audit.py` | Auditoría de las proyecciones: PIB, paro, precio, Euribor e IPC, y estructura del CSV | `out/03_projections_audit.json`, `out/03_paro_backtest_por_provincia.csv` |
| `02_ds/04_spread_gbr_validation.py` | Validación del GBR de spread de la app y del nb5 | `out/04_spread_gbr.json` |

Para ejecutarlo: `cd reports/audit/02_ds && python 01_reproduce_rfnac.py` (y así con los demás). Solo leen datos; no escriben fuera de `02_ds/out/`.

---

## 0. Resumen

1. **El 7,11 % de `RF_Nac` se reproduce solo de forma aproximada y no supera a la persistencia.** En este entorno sale un MAPE del 6,82 %. Con 50 semillas el rango va del 4,9 % al 9,9 % (mediana 6,84 %). En los mismos 8 trimestres de test, el **naive y(t-1) obtiene un 7,30 %**. En un rolling-origin de 40 orígenes, RF_Nac a h=1 obtiene un MAPE del 8,25 % frente al 9,44 % del naive, pero el test de Diebold-Mariano no es significativo (p = 0,40).
2. **El 7,11 % es un error a 1 paso.** El modelo usa el dato real de hipotecas de t-1 y el Euribor del propio trimestre objetivo. Sin embargo, la app y el business case lo presentan como la fiabilidad de una **predicción recursiva a 20 trimestres (2026-2030)**. A h = 4 y h = 8 ningún modelo supera al naive o a la media móvil de 4 trimestres (U de Theil ≥ 1, salvo la propia MA4 a h=8).
3. **Hay leakage, aunque no es lo que explica la cifra.** La feature `Accesibilidad` se sobrescribe en la celda 11 con PIB, paro y precio **del mismo trimestre**. Además, el Euribor contemporáneo y `PIB_pc_lag1` contienen el PIB anual del año en curso, que no está publicado en la fecha de predicción. Al quitar estas features el MAPE apenas cambia (6,3 % y 6,2 %). El problema principal es de diseño de la evaluación: n = 8, un único origen, sin benchmark y modelo elegido mirando el test.
4. **Las proyecciones 2026-2030 tienen errores de construcción:**
   - **El PIB_pc está desfasado un año.** El CSV "2026" contiene la previsión de 2025; lo comprobé en el 100 % de las provincias.
   - **La "estacionalidad navideña" del PIB es un artefacto:** la serie es anual y se repite 4 veces por año.
   - **El guardrail no es "un tope del 4 %".** Es min(CAGR histórico, 4 %) y está activo en las 52 provincias, de modo que el crecimiento queda fijado en ≈ 1,8 % anual. En el backtest, el tope **empeora** el MAPE (7,2 % con tope frente a 3,6 % sin él).
   - **Paro:** los tres niveles de modelo se eligieron con el mismo test 2022-2025 en el que se reportan (17 de 17 coinciden con el "oráculo").
   - **El suelo NAIRU del 8,5 % contradice el dato observado:** **23 provincias tenían un paro inferior al 8,5 % en 2025Q4** (mínimo 4,69 %), y el CSV las hace saltar hacia arriba en 2026Q1 (Islas Baleares +4,8 pp, Huesca +3,8 pp).
   - **Los valores de 2025 del CSV son un forward-fill del dato de 2025Q4**, es decir, usan información futura dentro de 2025.
5. **La validación del GBR de spread de la app es inválida.** Aplica `TimeSeriesSplit` sobre un CSV ordenado por provincia, y el spread es una variable nacional, así que el 100 % de los trimestres de test están también en train. Así obtiene un RMSE de 0,104 frente a 0,575 con orden temporal, y el GBR **pierde frente al naive** en un rolling-origin trimestral (RMSE 0,55 frente a 0,22 a h=1). Además, la API muestra métricas literales sin calcular (R² 0,8492, MAPE 3,2 %).

---

## A. Modelo de demanda RF_Nac

### A.1 Pipeline real (notebook 4, celdas 7 → 20)

**Construcción del agregado nacional (celda 19):**
- Target: `Hipotecas_Total` nacional, calculado como **suma** de las 52 provincias.
- Variables provinciales "de nivel" (21 en total): precio, paro, IPC, PIB_pc, índices, ahorro, edad, spread y sus lags, rmean4, yoy, diff1 y `Accesibilidad`. Se agregan como **media ponderada por `Poblacion_lag1`**.
- Cantidades (transmisiones, población, lags de hipotecas): se suman.
- `Hipotecas_Total_yoy` y `Transmisiones_Total_yoy` se agregan como media simple de las ratios provinciales.
- Euribor: media de las 52 copias de un valor nacional.

**Features:**
- 52 nacionales en total.
- Lags de hipotecas (1, 2 y 4), `rmean4 = shift(1).rolling(4)`, yoy calculado como (lag1 − lag5)/lag5 y momentum calculado como lag1 − lag2. Todos están **bien alineados**: se calculan sobre `shift(1)`, así que no incluyen el trimestre t.
- El rolling provincial **no se agrupa por provincia** (`s.rolling(4)` sobre la serie concatenada). Las filas contaminadas entre provincias son las primeras de cada provincia y desaparecen en el `dropna()`, así que no tiene efecto, pero es frágil.
- El `ffill().bfill()` previo rellena PIB_pc 2025, los índices de 2025 y la tasa de ahorro de 2025Q4 con el último valor disponible.

**Split:**
- `iloc[:-8]`. El agregado nacional tiene 74 filas (2007Q3–2025Q4).
- Train: 66 puntos (2007Q3–2023Q4). Test: **8 puntos (2024Q1–2025Q4)**, con **un solo origen**.

**Hiperparámetros:** están fijados a mano (RF: 200 árboles, max_depth 10, min_samples_leaf 3, `sqrt`). No hay búsqueda, pero el "ganador" se elige comparando el MAPE de 9 alternativas **sobre el mismo test de 8 puntos** (celdas 22 y 28) y después se reporta ese mismo MAPE. Es una selección sobre el test.

**Evaluación a 1 paso:** cada predicción del test usa las hipotecas **reales** de t-1, t-2 y t-4 y el Euribor real de t. No es una previsión multi-paso.

### A.2 Reproducción (`01_reproduce_rfnac.py`)

| Cifra | Notebook (salida guardada) | Reproducción | README |
|---|---|---|---|
| RF_Nac MAPE (test 2024Q1–2025Q4, n=8) | 7,11 % | **6,82 %** (RMSE 12.261) | 7,11 % |
| RF_Nac, 50 semillas | — | mín. 4,93 / P25 6,13 / **mediana 6,84** / P75 7,50 / máx. 9,90 % | — |
| SARIMAX nacional | 16,57 % | **16,57 %** (idéntico) | ~35 % |
| RF provincial (MAPE provincial) | 16,75 % | 14,71 % | ~18 % |
| XGB / LGBM / GBM provincial | 19,87 / 20,22 / 21,51 % | 18,63 / 19,80 / 19,65 % | ~20 / ~22 / ~25 % |
| ElasticNet provincial | 49,21 % | 54,84 % | ~30 % |
| RF provincial → agregado nacional | 9,69 % | 7,53 % | — |
| XGB_Nac / LGBM_Nac / ElasticNet_Nac | 16,63 / 10,99 / 10,26 % | 13,17 / 7,46 / 10,14 % | — |
| **Naive y(t-1), mismos 8 trimestres** | no calculado | **7,30 %** | — |
| Media móvil 4T / seasonal naive y(t-4) | no calculado | 10,02 % / 14,26 % | — |

Lectura:
- El SARIMAX coincide al decimal, lo que confirma que los datos son los mismos. Las diferencias en los modelos ML se deben a las versiones de las librerías y al azar. **El 7,11 % no es reproducible bit a bit**, y una semilla distinta lo mueve entre el 4,9 % y el 9,9 %.
- La tabla de modelos provinciales del README (RF ~18 %, XGB ~20 %, LGBM ~22 %, GBM ~25 %, ElasticNet ~30 %, SARIMAX ~35 %) **no coincide con ninguna salida del notebook**: ElasticNet da un 49 % y SARIMAX un 16,6 %, y además a nivel nacional, no provincial.
- El Theil U2 provincial del notebook (celda 52) compara modelos a 1 paso con un naive **multi-paso** (el último valor del train repetido 8 trimestres: MAPE 28,4 %). Con un naive a 1 paso (y(t-1): 17,9 %), la ventaja del RF provincial (14,7 %) es mucho menor.

### A.3 Búsqueda sistemática de leakage

| # | Comprobación | Resultado | Gravedad |
|---|---|---|---|
| L1 | Lags del target, rolling, yoy y diff | Correctos: todos sobre `shift(1)`; el target no está en las features (assert de la celda 13) | OK |
| L2 | **`Accesibilidad` contemporánea** | La celda 11 (un mapa, "ratio descriptivo, no feature") ejecuta `df['Accesibilidad'] = PIB_pc*(1-Tasa_Paro/100)/Precio_m2` con valores **de t** después del feature engineering y antes del split (ejecución nº 6 frente a nº 7 de la celda 13). La columna entra en `features_ml` y en el agregado nacional. Sin ella: MAPE 6,30 % (semilla 42); 6,95 % frente a 6,94 % de media en 20 semillas | MEDIA (efecto empírico pequeño, error conceptual) |
| L3 | Euribor del trimestre objetivo (`Euribor`, `Euribor_change`, `Euribor_x_Precio_nac`, `Spread_x_Euribor`) | Es la media trimestral de t, desconocida al inicio de t: en el backtest actúa como oráculo y en producción hay que proyectarla. Sustituyéndola por t-1: 6,23 % (semilla 42) y 7,00 % de media en 20 semillas | MEDIA |
| L4 | **PIB_pc anual** | El 100 % de los `PIB_pc_lag1` de Q2-Q4 son iguales al PIB **del mismo año** (la serie anual se replica en los 4 trimestres). El PIB provincial de un año lo publica el INE (Contabilidad Regional) bastante después de cerrar el año, así que en la fecha de predicción no existe. Lo mismo ocurre con `Poblacion` y `Edad_Media` (anuales) | MEDIA |
| L5 | Retraso de publicación del target | Las hipotecas del trimestre t-1 (INE, estadística H) se publican aproximadamente 2 meses después de cerrar cada mes, así que el lag1 completo no está disponible al empezar t. El "h=1" del notebook es, en realidad, un *nowcast* tardío | BAJA (hay que documentarlo) |
| L6 | Escaladores | `StandardScaler` se ajusta solo con el train (correcto). En el rolling uso `Pipeline` | OK |
| L7 | **Selección de modelo y enfoque con el test** | El ganador sale de 9 o más alternativas evaluadas en los mismos 8 puntos y se reporta ese mismo MAPE: es optimista por construcción | ALTA |
| L8 | `ffill().bfill()` | `bfill` rellena hacia atrás los NaN iniciales con valores futuros. En 2025, el `ffill` del PIB y de los índices introduce "datos" que no existen | BAJA |
| L9 | Predicciones futuras de variables explicativas | En el backtest no se usan. En la app sí: 2026-2030 se alimentan con el CSV de proyecciones (PIB desfasado, paro con suelo); el resto de variables (spread, índices, tasa de ahorro, edad) **se congelan en su último valor** (`_future_raw_rows`) | ALTA (en el uso en producción) |

Conclusión: el leakage existe, pero **no** es lo que fabrica el 7,11 %. El MAPE bajo se explica porque el test es a 1 paso, con el lag real del target: un random walk ya consigue el 7,3 %.

### A.4 Benchmark rolling-origin (`02_rolling_origin.py`)

**Diseño:**
- Serie nacional 2005Q1–2025Q4. Ventana expansiva con 40 orígenes, T = 2015Q4…2025Q3.
- h = 1, 2, 3, 4 y 8. El número de previsiones baja con h: 40 a h=1 y 33 a h=8.
- En el origen T solo se usa información hasta T.
- Los modelos ML usan estrategia directa con objetivo log(y_{T+h}/y_T). Sus features son las variaciones de log y, Euribor, precio, paro, spread y transmisiones en T, más dummies del trimestre objetivo.
- MASE: escala = MAE in-sample del seasonal naive de cada origen. U de Theil = RMSE del modelo / RMSE del naive en las mismas previsiones.
- `RF_Nac (réplica)` se reentrena en cada origen con su pipeline literal (solo h=1 y con features de t).

**MAPE (%) por horizonte (los tres mejores en negrita):**

| Modelo | h=1 (n=40) | h=2 (39) | h=3 (38) | h=4 (37) | h=8 (33) |
|---|---|---|---|---|---|
| Naive (y_T) | 9,44 | **10,27** | **11,51** | **12,82** | 15,42 |
| Seasonal naive | 12,61 | 12,77 | 12,92 | **12,82** | 15,42 |
| Media móvil 4T | 9,66 | 10,64 | **11,87** | **12,81** | **12,99** |
| Drift | 10,61 | 13,13 | 17,87 | 21,48 | 37,86 |
| AR(p≤4, AIC) log | 9,63 | 10,53 | 12,82 | 14,28 | 18,86 |
| ETS amortiguado + estacional (log) | **8,30** | **10,26** | **11,58** | 14,78 | 18,99 |
| SARIMA(1,1,1)(1,0,0)4 log | 9,50 | **10,01** | 12,17 | 13,72 | **16,80** |
| ElasticNet | **8,83** | 11,44 | 13,41 | 18,40 | 21,84 |
| RF | 9,00 | 10,96 | 13,29 | 15,16 | **18,16** |
| GBM | 9,85 | 12,04 | 14,60 | 17,18 | 21,02 |
| XGB | 9,92 | 11,61 | 15,24 | 16,26 | 21,77 |
| LGBM | 10,05 | 12,46 | 15,34 | 16,61 | 21,99 |
| **RF_Nac réplica (solo h=1, info de t)** | **8,25** | — | — | — | — |

**Otras métricas** (en `out/02_rolling_metrics.csv`):
- h=1: RF_Nac obtiene MAE 9.677, RMSE 12.382, sMAPE 8,19 %, MASE 0,298 y U 0,926. El naive, MAE 11.050, RMSE 13.367 y MASE 0,335.
- h=4: el mejor U es 1,000 (el naive). Todos los ML quedan entre 1,27 y 1,42.
- h=8: solo la MA4 tiene U < 1 (0,852).

**Diebold-Mariano (corrección HLN; pérdida cuadrática y absoluta) contra el mejor benchmark de cada horizonte** (`out/02_rolling_dm.csv`):
- h=1, RF_Nac frente al naive: DM = −0,84 (p = 0,40) con pérdida cuadrática y −1,08 (p = 0,28) con pérdida absoluta. **No hay diferencia significativa.** Lo mismo ocurre con ETS (p = 0,51) y ElasticNet (p = 0,23).
- h=3: LGBM es significativamente **peor** que el naive (p = 0,027 y 0,003).
- h=4 y h=8: ElasticNet es significativamente peor que la MA4 (p ≤ 0,009), y el AR también lo es a h=8 (p < 0,001). Ningún modelo es significativamente mejor que un benchmark en ningún horizonte.

**Estabilidad (h=1):**
- El MAPE en ventanas móviles de 8 trimestres (el tamaño del test del TFM) oscila **entre el 5,9 % y el 11,2 % para RF_Nac** y entre el 6,5 % y el 15,7 % para el naive.
- Por subperiodos, RF_Nac obtiene 7,7 % (2016-2019), 10,8 % (2020-2021) y 7,5 % (2022-2025), frente al 11,3 / 8,5 / 8,0 % del naive. En la ventana 2024-2025 del notebook, RF_Nac ocupa su mejor tramo (5,9 % en el rolling).
- Con 8 puntos, la cifra que se publique depende sobre todo de la ventana elegida.

**Intervalos empíricos (cuantiles 2,5–97,5 % del error logarítmico, en %):**

| Horizonte | Naive | MA4 |
|---|---|---|
| h=1 | [−20, +18] | [−17, +20] |
| h=8 | [−19, +39] | [−14, +29] |

Una previsión puntual a 5 años sin bandas de este orden de magnitud no es defendible.

### A.5 Uso en la app (`Web/demanda_models.py`)

- `_train_artifacts` reentrena RF provincial y RF_Nac **cada vez que se arranca la app**, sin artefacto versionado. Usa `n_jobs=-1` y la semilla fija 42, pero en otro entorno la cifra cambia (ver A.2).
- `_forecast_future` genera 2026Q1–2030Q4 **de forma recursiva**: sus propias predicciones alimentan los lags.
  - Las exógenas salen del CSV de proyecciones o del escenario del BCE.
  - Las que no están (Spread, índices de construcción, tasa de ahorro, edad media) se **congelan** en el último valor.
  - Las provinciales se reescalan al total nacional.
- Sin embargo, `build_demanda_response` muestra `art['nac_mape']`, un MAPE **a 1 paso** sobre 2024-25, como fiabilidad de cualquier trimestre de 2026-2030. `templates/business_case.html` (l. 497 y 652), `econometria.html` y `webscrapping.html` repiten el "MAPE 7,11 %" para las predicciones 2026-2030.
- La tabla `benchmark` etiqueta RF_Nac como "ML Provincial", cuando es nacional.
- No hay intervalos de predicción.

---

## B. Proyecciones 2026-2030

### B.0 Qué generó el CSV

- El CSV final lo escriben la celda 49 y la celda 50 (esta última añade 2025).
- La celda 31 (modelos nacionales, Prophet y VAR descartados) y la markdown "Estrategia de Proyección Macroeconómica Híbrida" (celda 34) **no describen el pipeline final**. Esa markdown dice que se usa Prophet lineal para PIB, paro y precio y AR(1) para la tasa de ahorro, y en el código final no se usa ninguno de los dos. Hay que retirarla o corregirla.
- La celda 26 hace su backtest en 2017Q1–2019Q4, no en "2022-2025" como dice el README, y su ganador para el precio es el seasonal naive, no Holt-Winters.
- **Estructura del CSV (verificada):**
  - 9.568 filas.
  - Euribor, IPC, PIB_pc, Tasa_Paro, Precio_m2 y Transmisiones_Total: 1.248 filas cada una (2025Q1–2030Q4).
  - Poblacion y Pob_Ext: 1.040 filas cada una (2026–2030).
  - El "8.320 filas" del README corresponde a la salida de la celda 49 antes de que la celda 50 añadiera 2025.

### B.1 PIB_pc: SARIMA(1,1,0)(1,1,0)₄ más guardrail

- **No hay estacionalidad.**
  - El PIB_pc tiene exactamente 1 valor por provincia y año.
  - En la serie nacional, las diferencias trimestrales son distintas de cero **solo en Q1** (19 de 19 años) y nulas en Q2-Q4.
  - El "ciclo navideño" del README es inexistente. Lo que la diferencia estacional "aprende" es el escalón anual. Por eso el SARIMA "gana" en el backtest de la celda 26 (0,6 %): los otros modelos predicen escalones donde no los hay.
  - El "test" de 8 trimestres contiene solo **2 valores distintos por provincia** (2023 y 2024).
- **Desfase de un año (bug).**
  - `get_future()` fecha el primer paso en `last_date + 3 meses`, donde `last_date = 2025Q4` es la última fila del panel. Pero la serie de PIB termina en 2024Q4, porque los valores de 2025 son NaN.
  - Resultado: el CSV "2026" contiene la previsión de **2025** y el CSV "2030", la de 2029.
  - La réplica literal coincide con el CSV en el **100 %** de las provincias.
  - La mediana del cociente PIB 2030 (CSV) / PIB 2024 es 1,115, es decir, unos 6 años de crecimiento al 1,8 %.
- **El guardrail "CAGR cap 4 %" es en realidad un tope al CAGR histórico.**
  - Calcula cap = min(CAGR_hist, 4 %). El CAGR histórico va del 1,0 % al 3,5 % (mediana 2,2 %) y nunca supera el 4 %, así que el tope efectivo es el CAGR histórico.
  - Está activo en la mayoría de trimestres en **las 52 provincias**. El crecimiento medio sin tope sería del 5,8 % anual (extrapola 2022-24) y queda en el **1,8 % anual**. Es decir, la proyección final es una tendencia geométrica histórica, no un SARIMA.
  - El README dice lo contrario ("el cap del 4 % no resulta activo en la mayoría de provincias").
  - El exponente usa 20 años para 19 intervalos (2005→2024).
- **Backtest del README (MAPE 7,2 %, U 0,749): reproducido** (7,18 % y 0,749). Sin el tope, el MAPE es del **3,57 %**: el guardrail empeora el error. Un random walk con deriva anual en log da un 7,01 % (U 0,734) y mejora al SARIMA con tope en el 100 % de las provincias. Con 2 puntos anuales por provincia, la cifra no permite elegir entre modelos.

### B.2 Tasa de paro: sistema de 3 niveles más suelo del 8,5 %

- **Tabla del README reproducida** (`out/03_paro_backtest_por_provincia.csv`):

  | Nivel | N | MAPE mediano | U2 mediano |
  |---|---|---|---|
  | SARIMA + dummy | 2 | 12,9 % | 0,545 |
  | ARIMA + dummy | 17 | 12,9 % | 0,709 |
  | ARIMA sin dummy | 33 | 16,9 % | 1,021 |
  | Global | 52 | 15,7 % | 0,944 |

  Coincide con el notebook (U 0,713 y 1,032 allí: diferencias en el tercer decimal). El naive obtiene una mediana del 18,1 %.
- **Selección con el test.** Las 17 provincias con dummy son **exactamente** las 17 en las que la dummy da menor MAPE en 2022-2025, y ninguna de las 33 restantes la tendría. Badajoz y Girona se eligieron igual ("MAPE 20,6 % → 7,3 %").
  - Con una regla fija, la mediana sube al 19,7 % (ARIMA para todas) o al 19,2 % (ARIMA + dummy para todas), **peor que el naive (18,1 %)**.
  - El 15,7 % publicado es un error de "oráculo" sin validez fuera de muestra.
  - Además, 20 provincias tienen U2 > 1.
- **Dummy COVID en el backtest.** La dummy cubre 2020Q1–2021Q4, justo los 8 últimos trimestres del train, y se fija a 0 en el futuro. Equivale a imponer un escalón de vuelta al nivel previo a la pandemia, no a "limpiar" los coeficientes.
- **El suelo del 8,5 % contradice el dato observado:**
  - 23 provincias tienen un paro inferior al 8,5 % en 2025Q4 (mínimo 4,69 %), 20 de media en 2025 y 25 en algún trimestre de 2025. En el test 2022-25 eran 28 provincias.
  - En el CSV, 24 provincias tocan el suelo (406 filas) y las 23 provincias bajo el 8,5 % **saltan hacia arriba** entre 2025Q4 (observado) y 2026Q1 (proyectado). Ejemplos: Islas Baleares +4,78 pp, Huesca +3,81 pp, Lleida +2,77 pp, Guipúzcoa +2,11 pp, Madrid +1,46 pp.
  - La justificación (mínimo nacional de 2007, NAIRU de la OCDE) es **nacional** y se aplica a provincias. El suelo debería ser provincial (por ejemplo, el mínimo histórico provincial o una NAIRU regional con fuente), o eliminarse.
  - El huérfano `outputs/prediccion_macro` proyecta un paro del 7,6 % para A Coruña en 2026, lo que muestra que los artefactos son incoherentes entre sí.

### B.3 Precio del m²: Holt-Winters amortiguado

- La cifra del README "MAPE mediano 2,9 %, U₂ 0,634" está **verificada**: obtengo 2,89 % y 0,634, con un φ mediano de 0,917 (el README dice "en torno a 0,94").
- **"HW gana en el 79 % de las provincias" es incorrecto tal como está redactado.**
  - El 79 % de la celda 46 es la **mejora porcentual del MAPE en el agregado nacional**: HW 1,53 % frente a SN 7,29 %, es decir, (7,29 − 1,53)/7,29 = 79 %.
  - Por provincia, HW gana al seasonal naive en el **92,3 %** de las provincias y al naive (último valor) en el **78,8 %**.
- El test son los últimos 8 trimestres (2024-25), con un solo origen. El modelo se fijó después de ver ese mismo periodo (la celda 46 decide "todo Holt-Winters" con ese duelo).

### B.4 Euribor e IPC "institucionales"

- **Euribor 2026-2028 = 2,00 / 2,10 / 2,30**: coincide **exactamente** con los supuestos técnicos del **BCE de diciembre de 2025** para el **EURIBOR a 3 meses**: 2,2 (2025) / 2,0 / 2,1 / 2,3 ([Eurosystem staff projections, dic-2025](https://www.ecb.europa.eu/press/projections/html/ecb.projections202512_eurosystemstaff~12ead61977.en.html)). Hay dos problemas:
  - El dataset usa el **Euribor a 12 meses**. La comprobé contra la API del BCE (`FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA`): MAE trimestral de 0,002 pp con el 12M frente a 0,296 pp con el 3M. Hay un desajuste de plazo, y para el 12M habría que usar la curva forward o los futuros.
  - 2029-2030 = 2,15 no procede del BCE, cuyo horizonte acaba en 2028. Es un supuesto propio sin fuente.
- **IPC 2026-2028 = 1,88 / 2,10 / 2,00**: no coincide con el BCE de diciembre de 2025 (IAPC de la **zona euro** 1,9 / 1,8 / 2,0). La fuente no es trazable, y el dataset usa el IPC **autonómico de España**, que es un concepto distinto.
- **Valores de 2025 en el CSV (celda 50).** Están rotulados como "reales observados", pero son literales: Euribor 2,50 (la media real del 12M en 2025 es **2,22**, según la API del BCE y el propio dataset) e IPC 2,80 (la media del dataset en 2025 es 2,62).
  - Paro y precio de 2025 en el CSV = **último dato (2025Q4) copiado a Q1-Q4** en el 100 % de las provincias. Es información futura dentro del año, con un error frente a lo observado en 2025Q1 del 15,1 % (paro) y del 7,0 % (precio). El PIB de 2025 es el de 2024 copiado.
  - Interpolación: `bce_value` de la app interpola linealmente los valores anuales a trimestres, mientras que el notebook repite el valor anual. Hay una inconsistencia menor.

### B.5 Salidas huérfanas (`outputs/`)

- `outputs/preciom2/*`:
  - Compara LightGBM, XGB, HGB, Ridge, LastValue y SeasonalNaive con un backtest de **4 orígenes** (2018, 2020, 2022 y 2024) a h = 1-8. Es el protocolo más correcto del repositorio, aunque sin hold-out final.
  - LightGBM obtiene un MAPE del 2,93 % y U 0,784.
  - Incluye bandas p10/p90 y p2,5/p97,5.
  - **No lo genera ningún notebook presente** y contradice el "Holt-Winters" del README.
- `outputs/prediccion_macro/*`:
  - Usa un hold-out único de 8 trimestres (2024-25) con 4 estimadores, y elige el "mejor" sobre ese mismo hold-out.
  - Para el diferencial, el "mejor" tiene R² de 0,01 y un MAPE de ~100 %.
  - Hay que decidir si se integra (regenerable) o se elimina.

---

## C. GBR de Spread (solo validación)

- **Tamaño efectivo de la muestra.** `Spread_Hipotecas` tiene **1 valor por trimestre** (es nacional). Las 4.160 filas del modelo de la app corresponden a **80 observaciones independientes**.
- **App (`_train_ml_pricing_model`).** Aplica `TimeSeriesSplit(5)` sobre `df` en el orden del CSV (Provincia, Trimestre). Cada fold de test es un bloque de provincias, y **el 100 % de sus trimestres están en el train** con el mismo target. Así obtiene un RMSE_CV de 0,104. Ordenando por tiempo sube a **0,575** (5,5 veces más).
- **Métricas inventadas.** `/api` muestra `{"r2": 0.8492, "rmse": 0.1543, "mape": "3.2%"}` como literales (app.py, ~l. 1172), sin calcularlas.
- **Notebook 5 (celdas 45 y 51).** Hace un split 80/20 tras ordenar por trimestre. El test (832 filas) son 16 trimestres, y el trimestre frontera puede repartirse entre train y test. Su "U2 0,461 frente al naive" usa un naive multi-paso, mientras que el modelo usa las variables contemporáneas.
- **Validación correcta: rolling-origin trimestral sobre la serie nacional**, 2015-2025 (`04_spread_gbr_validation.py`):

  | Configuración | RMSE GBR | RMSE naive |
  |---|---|---|
  | Directo, h=1 | 0,547 | **0,216** |
  | Directo, h=4 | 0,894 | **0,608** |
  | Contemporáneo, con macro del mismo trimestre (como lo usa el asesor) | 0,404 | **0,215** (naive t-1) |

  **El GBR no supera la persistencia en ninguna configuración.** El SHAP explica un modelo sin capacidad predictiva demostrada.

---

## D. Protocolo de validación propuesto (v2)

1. **Separar tres usos:**
   - *nowcast/h=1* (con el calendario de publicación real).
   - *previsión a h = 1…8*.
   - *escenarios 2026-2030*. Estos últimos no se validan con MAPE, se acompañan de bandas.
2. **Información disponible por fecha de publicación** (vintage). Cada feature debe llevar un `lag de publicación`:
   - Hipotecas y transmisiones: unos 2 meses.
   - EPA: unas 4 semanas.
   - PIB provincial: al menos 12 meses.
   - Población (padrón): al menos 12 meses.

   Así, en el origen T solo se usan valores publicados en T. Hay que eliminar `Accesibilidad` contemporánea y el Euribor de t (o tratarlo como escenario explícito).
3. **Rolling-origin de selección** con ventana expansiva:
   - Orígenes trimestrales desde 2012Q4 hasta 2021Q4.
   - h = 1, 2, 3, 4 y 8.
   - Selección de modelos e hiperparámetros solo aquí (por ejemplo, `TimeSeriesSplit` anidado por **trimestre**, nunca por fila del panel).
4. **Hold-out final reservado: 2022Q1–2025Q4.** No interviene en ninguna decisión, ni en el modelo ni en las dummies, los suelos o los topes. Se evalúa una sola vez y se publica tal cual, aunque sea peor.
5. **Benchmarks obligatorios en cada tabla:**
   - naive, seasonal naive, MA4, drift y ETS/ARIMA automáticos.
   - Métricas MAE, RMSE, MAPE, sMAPE, **MASE** y U de Theil, por horizonte.
   - **Diebold-Mariano** (HLN) frente al mejor benchmark.
   - No usar R² en el test.
6. **Panel provincial:** la métrica se agrega por trimestre y origen (MAPE ponderado o WAPE). La selección de "nivel por provincia" solo con validación anidada (elegir en orígenes ≤ 2021, evaluar en el hold-out).
7. **Intervalos de predicción:**
   - Cuantiles empíricos de los errores logarítmicos del rolling por horizonte (ver A.4: a h=8, aproximadamente −19 %/+39 % para el naive), o intervalos del propio modelo (ETS/SARIMA), validados por su **cobertura** en el hold-out.
   - Para 2026-2030: escenarios explícitos (Euribor de la curva forward 12M, BCE/BdE con su fecha de edición, más escenarios adversos ±150 pb), propagados al modelo de demanda.
8. **Estabilidad:** reportar la dispersión entre orígenes y entre semillas (P10–P90). Fijar versiones (`requirements.txt` con pines) y guardar artefactos entrenados con hash. No reentrenar al arrancar la app.
9. **Guardrails económicos** (suelo de paro, tope de PIB): solo como restricción **documentada y provincial**, evaluada también en el hold-out. Si empeora el error (como el tope del PIB), se elimina o se defiende como supuesto de escenario, no como modelo.

---

## E. Hallazgos por gravedad

### CRÍTICA

- **E1. La fiabilidad de la previsión de demanda está mal representada.** El "MAPE 7,11 %" es un error a 1 paso en 8 puntos, con lags reales y Euribor real; no difiere significativamente del naive (7,30 % en el mismo test; DM p = 0,40 en el rolling). La app y el business case lo usan como fiabilidad de las predicciones recursivas 2026-2030, donde a h = 4-8 ningún modelo supera a la persistencia.
- **E2. PIB_pc proyectado con un desfase de un año** (CSV 2026 = previsión 2025). Alimenta al asesor y a la demanda.
- **E3. Las métricas del modelo de spread de la app son inválidas** (CV con leakage por orden de provincias, 0,104 frente a 0,575) y además hay métricas literales inventadas (R² 0,8492, MAPE 3,2 %). El GBR no supera al naive.

### ALTA

- **E4. Selección sobre el test en todos los benchmarks:** el ganador de demanda, los niveles de paro (17/17 coincidencias con el oráculo, 15,7 % frente a ≥ 19,2 % con una regla fija, peor que el naive con 18,1 %) y el Holt-Winters del precio.
- **E5. Suelo del 8,5 % incompatible con 23 provincias** (paro observado de 4,7 a 8,4 % en 2025Q4). Genera saltos artificiales de hasta +4,8 pp en 2026Q1.
- **E6. "Estacionalidad" del PIB_pc inexistente** (serie anual replicada). El tope "4 %" es en realidad el CAGR histórico, está activo en 52 de 52 provincias y empeora el backtest (7,2 % frente a 3,6 %). El README describe lo contrario.
- **E7. La tabla de modelos del README no procede de ninguna ejecución** (ElasticNet 49 % y no 30 %; SARIMAX 16,6 % nacional y no 35 %). El 7,11 % no es reproducible bit a bit (4,9-9,9 % según la semilla).
- **E8. En la app, las exógenas no proyectadas se congelan** en su último valor (spread, índices, tasa de ahorro, edad media) y el paro de 2025 se rellena hacia atrás desde 2025Q4.

### MEDIA

- **E9. Leakage contemporáneo:** `Accesibilidad` (sobrescrita en la celda 11), Euribor de t y PIB/población anual del año en curso. El efecto medido es pequeño (±0,6 pp), pero es incorrecto.
- **E10. Euribor de escenario BCE (3M) aplicado a una serie de Euribor 12M.** 2029-30 sin fuente. IPC 1,88/2,10/2,00 no trazable (el BCE da 1,9/1,8/2,0 para la zona euro). 2025 rotulado como "observado", pero con 2,50 y 2,80 (real: 2,22 y 2,62).
- **E11. Documentación contradictoria:** la markdown "Estrategia Híbrida" (Prophet y AR(1)), el backtest de la celda 26 en 2017-19 frente al "2022-2025" del README, "HW gana en el 79 % de las provincias" (es la mejora nacional; por provincia es un 92 % frente al SN y un 79 % frente al naive) y el recuento de filas del CSV (9.568, no 8.320).
- **E12. Salidas huérfanas** en `outputs/` con modelos distintos (LightGBM para el precio, RF/Ridge para el spread) e incoherentes con el CSV principal (por ejemplo, paro por debajo del suelo).

### BAJA

- **E13.** Rolling no agrupado por provincia (sin efecto gracias al `dropna`), `bfill` hacia atrás, exponente del CAGR (20 frente a 19 años), Theil U2 provincial con naive multi-paso, la etiqueta "ML Provincial" para RF_Nac y `n_jobs=-1` en la app.

## F. Decisiones que requieren arbitraje

1. **Qué cifra de demanda publicar.** Recomendación: reemplazar el "MAPE 7,11 %" por la tabla rolling por horizonte (con naive, MASE y DM) y declarar que, a h ≥ 2, el modelo no mejora a la persistencia. Una alternativa es reformular el producto como *nowcast* a h=1.
2. **Modelo de 2026-2030 de la app:** mantener RF recursivo con bandas empíricas, o sustituirlo por benchmark/ETS más escenarios. Decidir también si se integra el pipeline de `outputs/preciom2` (el mejor protocolo) en `src/models/forecasting`.
3. **Suelo de paro:** eliminarlo o hacerlo provincial con fuente.
4. **Tope del PIB:** eliminarlo o declararlo como supuesto de escenario. En ambos casos hay que corregir el desfase de un año.
5. **Fuente y plazo de Euribor e IPC:** usar el Euribor 12M de la curva forward (o el supuesto del BCE 3M más un diferencial 12M-3M documentado) y el IAPC/IPC de España (Banco de España), citando la edición.
6. **GBR de spread:** dado que no supera al naive, decidir si el asesor usa el spread observado más reciente (o un escenario) en lugar del GBR. El SHAP explicaría entonces una regla, no un modelo.
