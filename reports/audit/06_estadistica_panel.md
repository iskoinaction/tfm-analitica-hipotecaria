# 06 · Auditoría estadística del panel provincial (Fase III)

**Auditor:** Estadística (metodología, inferencia, sesgos, reproducibilidad)
**Objeto:** `notebooks acabados/dataset_final_tfm.csv` (4.368 filas = 52 provincias × 84 trimestres, 2005Q1–2025Q4) y su construcción en `1. data_cleaning.ipynb`, `2. datos_bce.ipynb`, `3. data_joining.ipynb` a partir de `Datos ya metidos/` y `Datos sucios/`.
**Fecha:** 2026-11-21

## 0. Cómo reproducir

Todos los cálculos de este informe salen de scripts en `reports/audit/06_scripts/`. Se ejecutan desde la raíz del repo con `python3 -I reports/audit/06_scripts/<script>.py`. Las salidas completas quedan en `06_scripts/out/*.log` y `*.csv`.

| Script | Qué audita |
|---|---|
| `common.py` | Ejecuta **literalmente** el código de las celdas del notebook 3 (`limpiar_provincia`, `limpiar_numero`, `expandir_*`…). Añade una verdad terreno de provincias (`src/common/geography.py` más reparación iterativa de mojibake). |
| `01_matching_provincias.py` | Fuzzy matching: nombres reales de cada fuente, prueba exhaustiva de variantes, cobertura 52×T, duplicados y colisiones. |
| `02_informacion_efectiva.py` | Información independiente por variable, ICC, efecto de diseño y errores estándar (OLS, clúster, Driscoll-Kraay). Réplica de la CV del notebook 5, R² del predictor ingenuo e importancia espuria. |
| `03_hipotecas_parseo.py` | Parseo y agregación de `Hipotecas_Total`, contrastados con la API INE (tabla 3200, caché en `out/cache/ine_3200_numero.json`). |
| `04_transmisiones.py` | Trazabilidad de `Transmisiones_Total` y ruptura de fuente MIVAU→INE. |
| `05_spread_euribor.py` | Descomposición de `Spread_Hipotecas` con series del BCE (MIR, FM; caché en `out/cache/ecb_*.csv`). |
| `06_series_rupturas_outliers.py` | IPC, materiales, tasa de ahorro, población, Pob_Ext, PIB_pc (imputación 2024), ruido EPA, suavizado Tinsa, outliers, NaN y Ceuta/Melilla. |

Fuentes externas consultadas:
- INE Tempus3: `https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/3200`. Se usan las series «Total fincas. Número de hipotecas» y «Viviendas. Número de hipotecas» (p.ej. HPT34936 y HPT34618 para el total nacional).
- BCE: `https://data-api.ecb.europa.eu/service/data/` con las claves `MIR.M.ES.B.A2C.{A.C,A.R,F.R,K.R}.A.2250.EUR.N`, `FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA` y `FM.Q.U2.EUR.RT.MM.EURIBOR1YD_.HSTA`.

---

## 1. Resumen de hallazgos por gravedad

| # | Gravedad | Hallazgo | Evidencia clave |
|---|---|---|---|
| C1 | **CRÍTICA** | `Hipotecas_Total` está **corrompida por el parseo numérico**. El CSV fuente guarda los miles con punto y sin ceros finales (`'1.07'` = 1.070) y `limpiar_numero` lo lee como 1,07. | Hay 414 valores mensuales leídos como menos de 10 y 8 miles exactos (`'5.0'` = 5.000) leídos como 5. Afecta a **382 de 4.368 provincia-trimestres (8,7 %) en 39 provincias**, infravalorados entre un 20 % y un 79 % (mediana −35 %). Faltan **1.235.733 hipotecas (7,69 % del total)**. |
| C2 | **CRÍTICA** | Los valores de **`PIB_pc` 2024 por provincia no son datos del INE**: se imputaron con tasas de crecimiento redondas e iguales para todas las provincias de cada CCAA, que además no coinciden con el dato autonómico del INE. | El XLSX INE solo trae 2024 (A) para las CCAA. En el dataset, la desviación típica del crecimiento dentro de cada CCAA es 0,000–0,002 pp. Ejemplos: C. Valenciana +8,0 % imputado frente a +4,20 % del INE; Canarias +9,8 % frente a +6,62 %. No hay código que lo genere. |
| C3 | **CRÍTICA** (resultado «demasiado bueno») | La **pseudo-replicación** de variables nacionales con una validación cruzada no agrupada infla el R² del modelo de spread del notebook 5. | RF con KFold sin barajar: R² 0,997 (reproducido 0,9968). Con «TimeSeriesSplit» sobre filas ordenadas por provincia: 0,9947. Con trimestres separados (GroupKFold): 0,76. Con partición temporal real: **0,30**. |
| A1 | ALTA | Cinco variables nacionales están replicadas en 52 provincias y el IPC autonómico está replicado entre las provincias de cada CCAA. | Solo hay 81–84 observaciones independientes (1,9 % de 4.368). En una regresión ilustrativa, el error estándar de Euribor por Driscoll-Kraay es **7,6×** el de OLS (t baja de 28,0 a 3,7) y el de Spread **12,4×**. |
| A2 | ALTA | Las variables anuales se repiten en escalón: `PIB_pc`, `Poblacion`, `Edad_Media` y `Pob_Ext`. | El 75 % de las variaciones trimestrales son exactamente 0 y el 100 % del cambio cae en el primer trimestre. Solo hay 1.092 celdas independientes (25 %); 1.040 en el caso del PIB. |
| A3 | ALTA | Hay **rupturas de fuente**: `Pob_Ext` en 2023 y `Transmisiones_Total` en 2007. | Pob_Ext sube +21,1 % nacional en 2022→2023 (mediana provincial +28,7 %; Zamora +100,9 %; Melilla +101,4 %). En Transmisiones, el ratio 2007Q1/2006Q1 por provincia va de 0,40 a 2,11. |
| A4 | ALTA | `Spread_Hipotecas` = APRC (TAE) − Euribor 1A **no es un diferencial puro**. | Las comisiones (APRC − TEDR) suman 0,158 pp de media (≈10 % del spread). La cuota implícita de tipo variable cae de 0,93 (2005) a 0,08 (2025). Correlación del spread con el Euribor: −0,83 (acoplamiento mecánico). |
| A5 | ALTA | `tasa_ahorro` **no está desestacionalizada**. | El trimestre del año explica el **81,6 %** de su varianza. Medias: T1 −1,16 y T2 18,15. Autocorrelación de orden 1: −0,63; de orden 4: 0,90. |
| A6 | ALTA | `Indice_Materiales` es una media **sin ponderar** de 14 índices heterogéneos (7 materiales × 2 áreas). | Pesos implícitos proporcionales al nivel del índice: Energía-Canarias 19,7 %; las series de Canarias pesan el 50 %. Además, la serie termina en 2025M03. |
| M1 | MEDIA | `Hipotecas_Total` cuenta **todas las fincas**, no solo viviendas. Los datos de 2025 son provisionales. | Media mensual INE 2023-2024: 43.496 hipotecas sobre todas las fincas frente a 33.604 sobre viviendas (+29 %). Hay 303 meses de 2025 que difieren del INE actual. |
| M2 | MEDIA | El fuzzy matching **acierta con los ficheros actuales**, pero es frágil y asigna en silencio. | 0 errores y 0 colisiones en las 6 fuentes provinciales y en las 19 CCAA del IPC. Sin embargo, `'Araba'`→Zaragoza, `'Nafarroa'`→La Rioja, `'Total Nacional'`→Valencia, `'Canarias'`→Cantabria, `'Leganés'`→León… |
| M3 | MEDIA | `Precio_m2` (Tinsa) es una serie muy suavizada. | La autocorrelación de orden 1 de Δlog tiene mediana 0,755 (rango 0,24–0,91). |
| M4 | MEDIA | Hipotecas: el R² agregado (pooled) de 0,96 del notebook 4 se debe a la escala de cada provincia. | El predictor ingenuo y = lag1 logra R² 0,950 en la misma ventana. Su R² dentro de cada provincia es −0,58 y su R² en el agregado nacional, 0,39. |
| M5 | MEDIA | La `Tasa_Paro` EPA provincial tiene mucho ruido de muestreo en las provincias pequeñas. | Mediana de \|Δ\| trimestral: Ceuta 2,95 pp frente a Madrid 0,56 pp. Correlación con log(población): −0,39. |
| M6 | MEDIA | La reproducibilidad está rota. | El notebook 3 lee `transmision_prov_trim_tot.csv`, que no existe en el repo. Las salidas guardadas no coinciden con el CSV (Ávila 2025Q2: 11.076 en la salida frente a 698 en el CSV). Los ficheros UTF-8 se leen como latin-1 (mojibake de hasta 3 capas). |
| B1 | BAJA | Euribor y la agregación trimestral del spread son correctos. | El fichero coincide con BCE FM.Q (máx. \|dif\| 0,0118 pp, por revisiones). |
| B2 | BAJA | El IPC es la media trimestral de **tasas interanuales** mensuales (no un índice). | 43 de 52 provincias comparten valor con otras. Canarias: valor idéntico en las dos provincias el 100 % de los trimestres. |
| B3 | BAJA | NaN, ceros, negativos y duplicados están bien. | Sin duplicados. Los ceros (27, IPC) y los negativos (Euribor, ahorro, IPC, spread) son legítimos. NaN: PIB_pc 208, materiales y mano de obra 156, tasa_ahorro 52. |
| B4 | BAJA | `Poblacion` combina dos bloques (2005–2021 y 2022–2025) sin ruptura visible. El PIB per cápita del INE usa la población a 1 de julio (ECP); `Poblacion` es a 1 de enero. | Crecimiento nacional: 2021 −0,14 %, 2022 +0,21 %, 2023 +1,26 %. |

---

## 2. Información independiente real por variable (tarea 1)

Fuente: `out/02_informacion_efectiva.csv`. Significado de las columnas:
- `eta²_trim`: proporción de la varianza explicada por efectos fijos de trimestre. Es el ICC del clúster temporal.
- `deff`: efecto de diseño de Kish, 1 + (m−1)ρ con m = 52.
- `N_eff`: n / deff.

| Variable | Nivel real de variación | Celdas independientes | Ratio vs 4.368 | Valores distintos | eta²_trim | eta²_prov-año | deff | N_eff |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Euribor | nacional (T) | 84 | 0,019 | 84 | 1,000 | 0,958 | 52 | 84 |
| Spread_Hipotecas | nacional (T) | 84 | 0,019 | 84 | 1,000 | 0,935 | 52 | 84 |
| tasa_ahorro | nacional (T) | 83 | 0,019 | 75 | 1,000 | 0,118 | 52 | 83 |
| Indice_Mano_Obra | nacional (T) | 81 | 0,019 | 81 | 1,000 | 0,990 | 52 | 81 |
| Indice_Materiales | nacional (T) | 81 | 0,019 | 81 | 1,000 | 0,977 | 52 | 81 |
| IPC | CCAA×T | 1.596 | 0,365 | 337 | 0,979 | 0,880 | 50,9 | 86 |
| PIB_pc | provincia×año | 1.040 | 0,238 | 1.015 | 0,266 | 1,000 | 14,6 | 285 |
| Poblacion | provincia×año | 1.092 | 0,250 | 1.092 | 0,000 | 1,000 | 1,0 | (4.291)* |
| Edad_Media | provincia×año | 1.092 | 0,250 | 715 | 0,179 | 1,000 | 10,1 | 432 |
| Pob_Ext | provincia×año | 1.092 | 0,250 | 1.086 | 0,009 | 1,000 | 1,5 | (2.991)* |
| Precio_m2 | provincia×T | 4.368 | 1,000 | 4.368 | 0,177 | 0,996 | 10,0 | 435 |
| Hipotecas_Total | provincia×T | 4.368 | 1,000 | 3.151 | 0,159 | 0,953 | 9,1 | 478 |
| Tasa_Paro | provincia×T | 4.368 | 1,000 | 2.182 | 0,477 | 0,961 | 25,3 | 172 |
| Transmisiones_Total | provincia×T | 4.368 | 1,000 | 2.865 | 0,067 | 0,984 | 4,4 | 987 |

\* Para las variables anuales, el N_eff por clúster temporal no aplica: su límite real son las 1.092 celdas provincia-año, y aun estas están muy autocorrelacionadas. Un eta² provincia-año de 1,000 significa que la varianza dentro de cada año es nula.

**Consecuencias en modelos de panel:**
- **Errores estándar subestimados (efecto Moulton).** Regresión ilustrativa `log(Hipotecas) ~ Euribor + tasa_ahorro + Spread + EF provincia` con N = 4.316:

  | Regresor | coef | SE OLS | SE clúster trimestre | SE clúster provincia | SE Driscoll-Kraay (4 retardos) | DK/OLS | t OLS → t DK |
  |---|---:|---:|---:|---:|---:|---:|---|
  | Euribor | 0,2219 | 0,0079 | 0,0343 | 0,0090 | 0,0600 | 7,6 | 28,0 → 3,7 |
  | tasa_ahorro | −0,0045 | 0,0009 | 0,0048 | 0,0004 | 0,0028 | 3,2 | −5,2 → −1,6 |
  | Spread | 0,0210 | 0,0157 | 0,0991 | 0,0167 | 0,1938 | 12,4 | 1,34 → 0,11 |

  La misma regresión con las **84 medias nacionales** (HAC) da coeficientes idénticos y SE ≈ Driscoll-Kraay: Euribor 0,0592, Spread 0,1914. Es decir, el panel no aporta información adicional sobre los coeficientes de las variables nacionales. Agrupar solo por provincia **no corrige** el problema: el SE resulta incluso menor que el de OLS para tasa_ahorro.
- **Pseudo-replicación y validación cruzada (C3).** Con filas ordenadas por provincia y trimestre, cualquier partición por filas pone el mismo trimestre en entrenamiento y en test. Una variable nacional como el Euribor, con 84 valores distintos, actúa como **identificador del trimestre**, y el árbol memoriza el objetivo nacional. Réplica de `5. HIPOTECA_PERSONALIZADA_provincial.ipynb`, celdas 15 y 37:

  | Esquema de validación | RF | Lineal |
  |---|---:|---:|
  | KFold(5) sin barajar (= celda 15; el notebook reporta RF 0,9974) | 0,9968 | 0,7991 |
  | TimeSeriesSplit(5) sobre filas ordenadas **por provincia** (= celda 37; el notebook reporta GBM 0,9464) | 0,9947 | 0,7958 |
  | GroupKFold(5) por trimestre | 0,7646 | 0,7822 |
  | Temporal real (entrenamiento ≤2018, test 2019-2024) | **0,3012** | **0,3658** |

  La celda 37 llama «CV temporal» a algo que no lo es: TimeSeriesSplit trocea por filas y las filas están ordenadas por provincia, así que cada bloque de test son provincias nuevas con todos los trimestres.
- **Importancia de variables en árboles.** Una variable de ruido puro replicada por trimestre (`ruido_nacional`) recibe una importancia por permutación 7,5 veces mayor que la de un ruido i.i.d. (0,0030 frente a 0,0004 de caída de R²; script 02, apartado d). En ese modelo el efecto es pequeño porque Poblacion domina la escala, pero el mecanismo queda demostrado. En los modelos de objetivo nacional (spread, C3) es el principal motor del R².
- **Correlación intra-clúster del IPC.** Las 9 provincias de Castilla y León, las 8 de Andalucía, etc. comparten exactamente el mismo IPC. eta²_trim = 0,979: el IPC aporta prácticamente la misma información que una serie nacional (N_eff ≈ 86).

**Recomendación.** Modelar las variables nacionales a nivel nacional, con N = 84 trimestres. Otra opción es incluirlas en el panel con efectos temporales o en interacción con características provinciales. En cualquier caso:
- inferencia con Driscoll-Kraay o clúster de dos vías (provincia y trimestre);
- validación **por bloques temporales** (expanding window por fecha, con GroupKFold por trimestre como mínimo);
- informar del N efectivo.

---

## 3. Series anuales repetidas en escalón (tarea 2)

Confirmado: `expandir_anual_a_trimestral` **repite** el valor anual en los cuatro trimestres; no interpola. Afecta a PIB_pc, Poblacion, Edad_Media y Pob_Ext. Transmisiones_Total **sí** es trimestral: suma de los meses del INE desde 2007 y trimestres MIVAU en 2005-2006.

| Variable | Δ trimestral = 0 | Cambio concentrado en el primer trimestre |
|---|---:|---:|
| PIB_pc | 71,4 % | 100 % |
| Poblacion | 75,0 % | 100 % |
| Edad_Media | 75,2 % | 100 % |
| Pob_Ext | 75,0 % | 100 % |
| (referencia) Tasa_Paro | 0,2 % | 24,7 % |
| (referencia) Hipotecas_Total | 0,1 % | 24,1 % |

**Consecuencias:**
1. **Escalones.** Todo el cambio anual entra como un salto en el primer trimestre. En modelos con `diff1`, `yoy` o `lag1`, eso crea un pico artificial en el T1 y tres trimestres de variación nula, lo que confunde estacionalidad con calendario de publicación.
2. **Varianza intra-año nula.** Estas variables no pueden explicar nada de la dinámica trimestral. Lo que capturan es nivel y tendencia: Poblacion actúa como efecto fijo de escala (eta²_prov = 0,998).
3. **Precisión ficticia.** Se aparentan 4.368 observaciones donde hay 1.092. Si además se interpolara (como afirma el README), se fabricaría variación intra-año correlacionada con la tendencia, lo que da R² y t espurios.
4. **Fecha de referencia ≠ fecha de publicación.** El PIB provincial del año t se publica con un retraso de alrededor de dos años: el XLSX en `Datos sucios` marca 2023 como «(P)» y para 2024 solo trae «(A)» de CCAA. Usar `PIB_pc_lag1` en el T1 de t+1 supone utilizar información que en esa fecha no existía (*look-ahead* en backtests). Las fechas exactas deben fijarse con el calendario del INE.

**Recomendación por variable:**

| Variable | Tratamiento recomendado |
|---|---|
| **PIB_pc** | Mantener **anual** y eliminar los valores 2024 imputados (C2). Para modelos trimestrales, usar **MIDAS** o alinear con la fecha de publicación (valor «último disponible»). Si se necesita señal trimestral, usar un **indicador trimestral auxiliar** (empleo EPA provincial, afiliación, o PIB trimestral nacional/CCAA). Chow-Lin/Denton solo con ese indicador y documentando que es una estimación. Nunca interpolación lineal. |
| **Poblacion** | Es un **stock** suave: interpolar log-linealmente entre stocks a 1 de enero está justificado **solo como denominador** (per cápita) o en cifras de 1 de julio, como hace el INE en el PIB pc. No debe usarse como regresor dinámico. Alternativa: ECP semestral del INE como fuente directa. |
| **Edad_Media** | Mantener anual. Varía muy lentamente (rol de efecto fijo y tendencia). Excluirla de modelos trimestrales dinámicos o usarla solo en especificaciones de nivel o entre provincias. |
| **Pob_Ext** | Mantener anual **tras homogeneizar la fuente** (A3): Padrón 1 de enero en toda la serie. Usarla como ratio sobre la población, no en niveles. |
| **Transmisiones_Total** | Ya es trimestral. Arreglar la ruptura de 2007 (usar una sola fuente para toda la serie). |

---

## 4. Agregación mensual → trimestral y unidades (tarea 3)

| Variable | Fuente / unidad | Agregación del notebook | Verificación | Juicio |
|---|---|---|---|---|
| Hipotecas_Total | INE H, «Total fincas. Número de hipotecas», mensual | **Suma** de 3 meses | Correcta conceptualmente, pero **sobre valores mal parseados** (C1). Tras corregir el parseo, 12.790 de 13.104 meses coinciden con el INE actual; los 314 restantes son revisiones de 2025 (303) y casos ambiguos. | Corregir el parseo. Total fincas ≠ viviendas: 43.496/mes frente a 33.604/mes en 2023-24, es decir +29 % (M1). |
| IPC | INE IPC por CCAA, «Variación anual», índice general | Media de 3 tasas interanuales mensuales | 1.596 celdas CCAA-trimestre con 3 meses cada una. Rango −2,2 a 12,13 %. | Aceptable como aproximación de la tasa interanual trimestral. No es un índice: no permite deflactar ni calcular inflación trimestral. Los cambios de base del IPC (2006/2011/2016/2021) no afectan a las tasas publicadas, que el INE enlaza. |
| Euribor | BCE FM.Q EURIBOR1YD_ (media trimestral de datos diarios) | Directo | Coincide con el BCE (máx. 0,0118 pp de diferencia). Frente a la media de las 3 medias mensuales: 0,028 pp. | Correcto. |
| Spread_Hipotecas | APRC mensual (media trimestral) − Euribor FM.Q | Media | Reproducido (máx. 0,0118 pp de diferencia). | Agregación correcta; concepto discutible (A4). |
| Indice_Mano_Obra | INE, Total Nacional, mensual | Media | Una sola serie. | Correcto. Termina en 2025M03. |
| Indice_Materiales | INE, 7 materiales × {Península y Baleares, Canarias}, mensual | **Media simple de 42 valores** (14 series × 3 meses) | Reconstrucción idéntica al dataset en 81 de 81 trimestres. | **Incorrecto (A6).** Ver detalle abajo. |
| tasa_ahorro | Nacional trimestral, **sin desestacionalizar** | Directo | Patrón T1 ≈ −1, T2 ≈ 18, T3 ≈ 4, T4 ≈ 14. | **A5**: usar la serie desestacionalizada o la suma móvil de 4 trimestres (desv. típ. 8,6 frente a 2,99). La «anomalía» 0,1 → 16,7 es pura estacionalidad. |
| Precio_m2 | Tinsa IMIE, trimestral | groupby mean (sin colisiones) | 52 × 100 trimestres, 2001–2025. | Correcto. Serie suavizada (M3). |
| Tasa_Paro | EPA provincial, trimestral | groupby mean (sin colisiones) | 52 × 84. | Correcto; ruidosa (M5). |

**Detalle de A6 (materiales).** Niveles en 2024M12: Energía-Canarias 8.081,5 frente a Aluminio 1.092,2. Cada serie pesa en proporción a su nivel, que depende de la base y de la inflación acumulada y no de su peso en el coste. Canarias pesa el 50 % aunque es una fracción menor de la construcción. Cobre, con un crecimiento de +253 % entre 2005 y 2024, arrastra la tendencia. Usar el índice agregado oficial (p.ej. el índice general de costes del INE) o una ponderación documentada.

**Magnitudes frente a INE** (`out/03_hipotecas_nacional_vs_ine.csv`): la suma de provincias del dataset dividida entre el INE «total fincas» vale 0,853 en 2005Q1, 0,941 en 2007Q1, 0,865 en 2019Q1 y 0,955 en 2023Q1. El mínimo es **0,803 en 2018Q2**. El INE es internamente consistente: la suma de las 52 provincias es igual al total nacional en 260 de 260 meses. Las diferencias son, por tanto, del parseo del TFM.

**Detalle de C1** (`out/03_hipotecas.log`). Patrones de la columna `Total` del CSV:

| Patrón | Casos | Lectura del notebook |
|---|---:|---|
| `x.0` | 8.939 | 8 son miles exactos (p.ej. `'5.0'` = 5.000) mal leídos |
| `x.ddd` | 3.751 | Correcta (salvo revisiones de 2025) |
| `x.d` / `x.dd` | 414 | **Todos** mal leídos: `'1.07'` → 1,07 en lugar de 1.070 |

Provincia-trimestres afectados por año: 2005: 52, 2006: 39, 2007: 34, 2008: 27, 2009: 34, 2010: 32. Después de 2010, entre 4 y 15 por año. Provincias más afectadas: Barcelona (30 trimestres), Madrid (26), Alicante (24), Valencia (23), Málaga (22).

Los outliers |z| > 6 de la Δlog de Hipotecas se deben a este bug. Ejemplos: A Coruña 2006Q4 = 1.301,82 (un mes leído como 1,82) y Lleida 2008Q2 = 1.000,41. Contaminan el **objetivo** del notebook 4 y variables derivadas como `Hip_lag1_vs_rmean` o `Hip_trans_ratio`.

---

## 5. Fuzzy matching de provincias (tarea 4)

Se probaron `limpiar_provincia` y `expandir_ccaa_a_prov` **tal como están en el notebook** (`out/01_matching.log`, `01_matching_fuentes.csv`, `01_matching_variantes.csv`).

**Ficheros reales.** Tinsa, hipotecas, población, edad, EPA y PIB tienen cada uno 52 nombres → 52 destinos correctos, **0 errores y 0 colisiones**. Cada fuente aporta exactamente 52 provincias en cada periodo, sin duplicados provincia-periodo:

| Fuente | Periodos |
|---|---:|
| Tinsa | 100 |
| Hipotecas | 252 |
| Población | 21 |
| Edad | 21 |
| EPA | 84 |
| PIB | 20 |

El IPC (19 CCAA → 52 provincias) también sale correcto, incluidos Canarias y Ceuta/Melilla por separado. Pob_Ext y Transmisiones usan un diccionario exacto (`mapa_pob_ext`): los 58 nombres de Pob_Ext (con variantes «Gerona», «Lérida», «Orense», «Vizcaya»…) se reducen a 52 sin duplicados.

**Robustez (prueba exhaustiva).** 103 variantes base × {original, mayúsculas, prefijo de código, mojibake ×1, ×2, ×3}. Fallan 2 por tipo:
- `'Araba'` → **Zaragoza**
- `'Nafarroa'` → **La Rioja**

`'Valladolid'`, `'Lleida'`, `'Melilla'`, `'Bizkaia'`, `'Gipuzkoa'`, `'Ourense'`, `'Gerona'` y `'Lérida'` se asignan bien.

**Asignaciones silenciosas de entradas no provinciales** (ninguna aparece hoy en los ficheros, pero bastaría con un cambio de formato del INE):

| Entrada | Asignada a |
|---|---|
| `'Total Nacional'` | Valencia |
| `'Total'` | Toledo |
| `'Andalucía'` | Valencia |
| `'Cataluña'` | Castellón |
| `'Canarias'` | Cantabria |
| `'Castilla y León'` | León |
| `'Península y Baleares'` | Islas Baleares |
| `'Otros'` | Burgos |
| `'No consta'` | A Coruña |
| `'Leganés'` | León |
| `'Vigo'` | Lugo |
| `'Gijón'` | Girona |
| `'Cartagena'` | Zaragoza |
| `'Reus'` | Ourense |

Las reglas por subcadena son la causa (`'Le' in s and 'n' in s` → León; `'cer' and 'C'` → Cáceres), junto con `difflib` con cutoff 0,5. Si dos nombres fuente cayeran en el mismo destino, el `groupby().mean()` final los **promediaría sin aviso**, y en hipotecas el `.sum()` los **sumaría**.

Además, los ficheros UTF-8 se leen con `encoding='latin1'`, lo que produce hasta triple mojibake (`'AlmerÃ\x83Â\x83Ã\x82Â\x83…'`). El matching funciona solo porque `remove_accents_and_bizarre` elimina todo lo que no es a-z.

**Recomendación.** Usar la resolución determinista por código INE de `src/common/geography.py`, que lanza `KeyError` ante un nombre desconocido. Leer cada fichero con su encoding real. Añadir una validación dura de 52 × T, sin duplicados ni NaN de clave, antes de cada merge.

---

## 6. Ausentes, rupturas, outliers y unidades (tareas 5 y 6)

**NaN:** PIB_pc 208 (2025 completo); Indice_Mano_Obra e Indice_Materiales 156 (2025Q2–Q4: las fuentes acaban en 2025M03); tasa_ahorro 52 (2025Q4). Sin duplicados (Provincia, Trimestre).

**Ceros:** solo IPC (27, legítimos).

**Negativos legítimos:** Euribor (1.248 filas = 24 trimestres), tasa_ahorro (884 = 17 trimestres), Spread (104 = 2 trimestres) e IPC (768).

**Rupturas de serie:**

| Serie | Ruptura | Evidencia |
|---|---|---|
| **Pob_Ext 2023** | 2005–2022: Padrón, «TOTAL EXTRANJEROS» a 1 de enero (`Datos sucios/pob_ext_2005_2022.csv`). 2023–2025: un fichero distinto, con dimensiones «Tipo de documentación», «Lugar de nacimiento» y «Principales nacionalidades» y stocks trimestrales (31-mar … 30-sep). El notebook 1 lo **promedia por año**; 2025 solo tiene 3 trimestres. | Nacional +21,1 % en 2022→2023, frente a +0,1 % y +1,9 % los dos años anteriores. Por provincia: de −6,9 % a +101,4 %. Mediana del % de extranjeros: 9,76 → 11,35. **Mezcla conceptos** (registro administrativo de documentación frente a padrón) y **fechas de referencia**. |
| **Transmisiones 2007** | 2005–2006: MIVAU, «Número total de transacciones inmobiliarias de viviendas» (notarial). 2007+: INE ETDP, «Viviendas: Total» (registral). Desde 2007, el dataset coincide con el fichero INE del repo en 3.952 de 3.952 celdas. | Ratio provincial 2007Q1/2006Q1 entre 0,40 (Palencia) y 2,11 (Cuenca). El notebook 1 filtraba «Naturaleza de la finca == Total», columna que el fichero del repo no tiene: el fichero cambió y no está versionado el intermedio. |
| PIB_pc 2024 | Imputado (C2). 2023 es provisional («(P)»). Unidades: euros corrientes, sin deflactar. | Crecimiento medio provincial 2021–2024: 10,1 %, 10,6 %, 6,7 % y 7,1 %, en términos nominales. |
| Hipotecas 2025 | Datos provisionales del INE | 303 meses de 2025 difieren del INE actual. |
| EPA 2021 | Cambio metodológico de 2021T1 | La Δ de la media provincial en T1 de 2021 (0,68 pp) es mayor que la de 2018–2023 (0,32–0,54), pero no es concluyente. Verificar que la tabla descargada es la serie retropolada del INE. |
| IPC | Cambios de base | Irrelevantes para tasas interanuales enlazadas por el INE. |
| Poblacion | Dos bloques (2005–2021 y 2022–2025) | Sin salto visible. Dispersión del crecimiento provincial estable (0,52–0,83 pp). |

**tasa_ahorro (pregunta del coordinador sobre 0,1 → 16,7).** Es la tasa trimestral **sin desestacionalizar**. El trimestre del año explica el 81,6 % de la varianza. No es un error de unidades, pero usarla tal cual, o con `lag1`, introduce un patrón de dientes de sierra que no tiene relación con las hipotecas provinciales.

**Outliers** (|z| robusto > 6 en Δlog por provincia; `out/06_outliers.csv`):
- Hipotecas: 8 casos, casi todos causados por C1.
- Transmisiones: 2 casos, Santa Cruz de Tenerife y Badajoz en 2020Q2 (confinamiento, genuinos).
- Precio_m2: 1 caso, Melilla 2006Q2.
- Tasa_Paro: 1 caso, Santa Cruz de Tenerife 2008Q1.

**Ceuta y Melilla:**
- Hipotecas: mediana de 144,5 y 180,5 por trimestre.
- Transmisiones: mediana de 102,5 y 140,5 por trimestre.
- Tasa de paro: entre 9,9 % y 39,2 %, con el mayor ruido EPA.

Su peso en métricas no ponderadas (MAPE, R² provincial) es desproporcionado. Conviene ponderar por tamaño o tratarlas aparte. El IPC de Ceuta y el de Melilla son distintos (solo coinciden el 1 % de los trimestres); Canarias tiene el mismo IPC en ambas provincias por construcción.

---

## 7. Spread_Hipotecas: APRC − Euribor no es un spread puro (tarea 7)

Las series del BCE se descomponen así (`out/05_spread.log`, `05_spread_descomposicion_trimestral.csv`):

```
spread_TFM = APRC − Euribor1A = (APRC − TEDR) + (TEDR − Euribor1A)
             [comisiones/gastos]  [margen + prima de plazo por mezcla fijo/variable]
```

| Periodo | APRC | TEDR | Euribor 1A | Spread TFM | Comisiones (APRC−TEDR) | TEDR variable − Euribor | Cuota implícita variable* |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2005 | 3,37 | 3,22 | 2,33 | 1,04 | 0,15 | 0,85 | 0,93 |
| 2013 | 3,19 | 3,04 | 0,54 | 2,66 | 0,15 | 2,32 | 0,68 |
| 2016 | 2,32 | 2,01 | −0,03 | 2,36 | 0,31 | 1,70 | 0,48 |
| 2019 | 2,22 | 1,99 | −0,22 | 2,43 | 0,23 | 1,87 | 0,35 |
| 2023 | 3,89 | 3,75 | 3,87 | **0,02** | 0,15 | 0,39 | 0,18 |
| 2025 | 2,78 | 2,72 | 2,22 | 0,56 | 0,07 | 0,78 | 0,08 |

\* w = (K − TEDR)/(K − F), donde F es el tipo variable o con fijación ≤ 1 año y K el tipo con fijación > 1 año. Solo se calcula cuando |K − F| > 0,25 pp; por eso no hay valor en 2021-22.

**Conclusiones:**
- **Las comisiones** suponen de media 0,158 pp (rango 0,037–0,350), ≈ 10 % del spread medio (1,599 pp). Su máximo llega en 2016–2018.
- **La mezcla fijo/variable** es el problema principal. Desde ≈2016 la mayoría de las nuevas hipotecas son a tipo fijo, cuya referencia son los swaps a largo plazo y no el Euribor 1A. En 2023 el «spread» es 0,02 pp mientras el margen de las hipotecas variables sobre el Euribor es 0,39 pp. La serie mide sobre todo **pendiente de la curva y composición de la cartera**, no el margen bancario.
- **Acoplamiento mecánico.** Por identidad, Spread ~ Euribor tiene pendiente igual a la de APRC ~ Euribor menos 1: −0,426 = 0,574 − 1, con R² = 0,690 en 84 trimestres. Parte del R² de los modelos que usan el Euribor para explicar el spread (notebook 5) es **contable, no económico**.

**Recomendaciones:**
- Renombrar la variable a «TAE − Euribor 1A» si se mantiene.
- Para medir margen, usar TEDR(F) − Euribor 1A para el tramo variable y TEDR(K) − IRS 10A/20A para el fijo, o directamente la TEDR.
- No incluir el Euribor como regresor de un objetivo que lo contiene restado.

---

## 8. Resultados «demasiado buenos» previsibles (tarea 8)

1. **Modelo de spread del notebook 5:** R² 0,997 (RF) o 0,946 (GBM, «CV temporal»). Lo explican la pseudo-replicación, la CV por filas y el acoplamiento mecánico. El R² honesto fuera de muestra temporal es **≈0,30–0,37** (sección 2).
2. **Hipotecas provinciales, notebook 4 (R² RF 0,9603).** Sobre los últimos 8 trimestres:

   | Métrica del predictor ingenuo y = lag1 | Valor |
   |---|---:|
   | R² agregado (pooled) | 0,950 |
   | R² con y = lag4 | 0,918 |
   | R² dentro de cada provincia | **−0,577** |
   | R² en el agregado nacional | 0,391 |
   | Varianza explicada por la provincia (eta²) | 0,968 |

   El R² agregado mide la escala de las provincias, no la capacidad predictiva. Esto es coherente con que el propio notebook obtenga R² −0,10 en el agregado nacional para el RF provincial. Recomendaciones:
   - reportar el **skill frente al ingenuo** (MASE o R² relativo a lag1/lag4);
   - reportar el R² dentro de cada provincia;
   - modelar log o per cápita.
3. **Variables suaves con lags propios.** Precio_m2 (Tinsa, AC1 de Δ de 0,755) y las anuales repetidas: los lags de la propia variable dan ajustes casi perfectos sin contenido económico. En VAR/VECM provinciales o nacionales, las variables en escalón (PIB_pc) generan **IRF y causalidades de Granger espurias** asociadas al primer trimestre de cada año.
4. **Look-ahead por calendario de publicación.** PIB_pc (≈2 años de retraso, y 2024 imputado), Poblacion a 1 de enero (usada desde el T1 del mismo año), tasa_ahorro y EPA (semanas o meses de retraso). Los backtests con `lag1` suponen disponibilidad inmediata.
5. **Significatividad inflada:** los t-ratios de las variables nacionales se multiplican por 3–12 si se usan errores OLS (sección 2).

---

## 9. Recomendación por variable (frecuencia y tratamiento para el panel v2)

| Variable | Nivel / frecuencia real | Acción |
|---|---|---|
| Hipotecas_Total | provincia × mes | **Re-descargar del INE** (API, valores numéricos) y sumar por trimestre. Separar viviendas y total de fincas. Marcar los datos provisionales y la *vintage*. |
| Transmisiones_Total | provincia × mes (INE desde 2007) | Una sola fuente: INE ETDP desde 2007, o MIVAU para toda la serie. Si se empalma, hacerlo con un año de solape y documentarlo. |
| Precio_m2 | provincia × trimestre | Mantener. Advertir del suavizado y evaluar frente a un ingenuo. |
| Tasa_Paro | provincia × trimestre (EPA) | Mantener. Medias móviles de 4 trimestres o modelos con error de medida para las provincias pequeñas. Verificar que es la serie retropolada de 2021. |
| IPC | CCAA × mes (tasa interanual) | Mantener como tasa interanual trimestral; descargar también el índice. Tratarlo como regresor casi nacional (clúster por CCAA y trimestre). |
| Euribor | nacional × trimestre | Mantener. Modelar a nivel nacional o con efectos temporales. Inferencia Driscoll-Kraay. |
| Spread_Hipotecas | nacional × trimestre | Sustituir por TEDR o márgenes por tramo de fijación (sección 7). |
| tasa_ahorro | nacional × trimestre | Serie desestacionalizada o suma móvil de 4 trimestres. Completar 2025Q4 cuando se publique. |
| Indice_Materiales | nacional × mes | Índice agregado oficial o ponderación documentada. Extender más allá de 2025M03 o declarar la serie truncada. |
| Indice_Mano_Obra | nacional × mes | Mantener. Truncada en 2025M03. |
| PIB_pc | provincia × año | **Eliminar los valores 2024 imputados**. Tratarlo como anual o con MIDAS, alineado con la fecha de publicación. Deflactar si se usa en términos reales. |
| Poblacion | provincia × año (1 de enero) | Interpolación log-lineal **solo como denominador**, o la ECP semestral. No como regresor dinámico. |
| Edad_Media | provincia × año | Mantener anual (control de nivel). Excluir de la dinámica trimestral. |
| Pob_Ext | provincia × año | Homogeneizar la fuente (Padrón a 1 de enero, 2005–2025). Usar el ratio sobre la población. |

---

## 10. Decisiones que requieren arbitraje del coordinador

1. **PIB_pc 2024.** Propongo borrarlo (dejar NaN) en v2 y avisar al equipo de modelos, porque los notebooks 4 y 5 y las predicciones 2026-2030 lo usan.
2. **Hipotecas_Total.** Hay que elegir entre «total fincas» (lo actual) y «viviendas» como objetivo. Para un TFM sobre hipotecas de vivienda recomiendo viviendas. Cambia la escala en ≈ −23 %.
3. **Spread.** Hay que decidir si v2 mantiene «TAE − Euribor» (renombrada) o pasa a TEDR o márgenes por tramo de fijación.
4. **Pob_Ext 2023–2025.** Re-descargar el Padrón a 1 de enero de esos años (INE) o truncar la serie en 2022.
5. **Esquema de validación obligatorio** para todos los agentes de modelos: particiones temporales por fecha, inferencia Driscoll-Kraay o clúster de dos vías, y métricas frente a un ingenuo y dentro de cada provincia.
