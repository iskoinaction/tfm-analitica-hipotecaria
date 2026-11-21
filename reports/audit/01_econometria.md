# 01 · Auditoría econométrica (Fase IV): VAR / VECM / cointegración / panel

Autor: agente econometría (series temporales y panel). Fecha: 2026-11-21.
Ámbito: `notebooks acabados/4.2. vecm_hipotecas.ipynb` (VECM), `notebooks acabados/4. econometria_y_demanda_hipotecaria.ipynb` §7-8,
`notebooks acabados/4.1. formalizacion_matematica_v2.ipynb` §14-15, `Web/templates/vecm.html`, `Web/templates/econometria.html`,
textos del asistente en `Web/app.py` (l. 1840-1845 y 2252-2256). Datos: `notebooks acabados/dataset_final_tfm.csv`.

Todo lo de este informe se ha calculado con los scripts de `reports/audit/01_econometria/` (ver §10 para reproducirlo).
Las cifras salen de los JSON/CSV/LOG que hay en esa carpeta. No se ha modificado ningún otro fichero.

---

## 0. Resumen ejecutivo

1. **Reproducción.** Las cifras documentadas del VECM **se reproducen exactamente** con el código del nb 4.2:
   β = (+0,35 PIB; +2,48 precio; −0,10 Euríbor; −1,09 materiales), α_hip = −0,4377, FEVD(20) = 53,3 % / 38,8 % / 2,2 %,
   traza 92,89 > 69,82 y Portmanteau con p = 0,22. Que se reproduzcan no significa que sean válidas.
   - **No se reproducen** las cifras de Johansen de la app (89,14/76,97; 44,21/54,07).
   - **No se reproducen** las IRF de la app (0,61; −0,50; −0,09; 0,11).
   - **Es falsa** la afirmación de que el ECT es estacionario: el propio notebook da ADF p = 0,204.
2. **Las conclusiones principales no son robustas.** Hay tres causas:
   - (a) **Datos.** Las 4 observaciones de 2025 tienen el PIB_pc y los materiales **arrastrados por ffill**. Las series nacionales son **medias simples** de provincias. Las hipotecas no están desestacionalizadas y no se usan dummies estacionales (estacionalidad F = 10,0, p < 0,001). El PIB_pc es anual repetido en escalón: el 76 % de los ΔlogPIB trimestrales son exactamente 0.
   - (b) **Inferencia.** La cointegración depende de la especificación. El bootstrap salvaje da p = 0,021 con los datos originales y p = 0,052 con los datos auditados. Engle-Granger no rechaza (p = 0,63-0,75). β es inestable en ventanas móviles.
   - (c) **Identificación e interpretación.** La FEVD de Cholesky varía mucho con el orden: la cuota del Euríbor va del 2,2 % al 17,6 % según las 120 ordenaciones, y el IC bootstrap 90 % es [0,3 %, 27 %]. Con los datos auditados, la cuota de los materiales cae del 38,8 % al 0,9 %. La elasticidad del PIB (+0,35) no es significativa (p = 0,46). El α del 44 % corresponde a otra normalización de β. Con datos auditados las hipotecas **no** corrigen el desequilibrio (α p = 0,20; exogeneidad débil p = 0,48): lo corrige el **precio**.
3. **Veredicto: el VECM no es defendible tal cual. Es defendible solo con correcciones sustanciales y reinterpretado.**
   - Corregir los datos: sin arrastres, agregación ponderada, estacionalidad tratada y, preferiblemente, PIB trimestral oficial.
   - Elegir el rango por bootstrap e informarlo como evidencia débil (≈10 %).
   - Leer β como **relación de equilibrio de forma reducida entre crédito y precios**, no como "demanda hipotecaria".
   - Sustituir las cuotas FEVD puntuales por GIRF/GFEVD con bandas y rangos por ordenación.
   - Complementar con un ARDL-bounds y con un panel PMG (evidencia exploratoria favorable).
   - Hay que **corregir o retirar** varias cifras de la documentación y de la app (§9).

---

## 1. Construcción de las series nacionales (nb 4.2, celda 3)

| Serie | Construcción en nb 4.2 | Problema detectado | Evidencia |
|---|---|---|---|
| Hipotecas | `sum` de 52 provincias | Bien agregada, pero **no desestacionalizada** y sin dummies. El 8,6 % de los valores provinciales no son enteros (posibles imputaciones; lo revisa el agente de datos). | F de dummies trimestrales sobre ΔlogH: 10,0 (p = 1,2e-5) |
| PIB_pc | `mean` **simple** de provincias + `ffill().bfill()` | Es anual repetido en 4 trimestres, así que ΔlogPIB = 0 en el 75,9 % de los trimestres. Los saltos se concentran en Q1 y se confunden con la estacionalidad de las hipotecas: la correlación de residuos PIB-Hip es 0,31 y baja a 0,17 con dummies. **2025 es entero 2024 arrastrado**. La media simple pesa igual Soria y Madrid. | `02_unit_root`, `04_vecm_analysis.json` (`corr_residuos`) |
| Precio_m2 (Tinsa IMIE) | `mean` simple | La media simple está ~20 % por debajo de la ponderada (2005: 1.312 frente a 1.630 €/m²). La serie es muy suavizada: la ACF de ΔlogP es 0,94 en el retardo 1, lo que apunta a **casi I(2)**. | §2 |
| Euríbor, Materiales | `mean` de valores replicados | Hay un único valor por trimestre (verificado: `nunique` = 1), así que la media es inocua. **Materiales 2025Q2-Q4 está arrastrado** de 2025Q1. | `common.national_raw` |
| Muestra | `dropna()` tras ffill → **84 obs. 2005Q1-2025Q4** | 4 de las 84 observaciones (5 %) contienen datos inventados por arrastre. | `01_reproduce.json` |

**Impacto de las 4 observaciones arrastradas.** Comparamos la especificación A (original) con la G (idéntica pero hasta 2024Q4):

| | A (original) | G (idéntica, hasta 2024Q4) |
|---|---|---|
| α_hip | −0,40 | −0,69 |
| Materiales en FEVD(20) | 38,8 % | 20,4 % |
| β_precio | 2,48 | 2,93 |

Cuatro puntos imputados mueven las conclusiones principales. Al añadir además la ponderación por población (B), el signo del PIB pasa a −1,10 (p = 0,001).

Figura: `01_econometria/figs/series_nacionales.png`.

---

## 2. Orden de integración (ADF, DF-GLS, PP, KPSS, Zivot-Andrews)

Script: `02_unit_root.py` → `02_unit_root.csv`. ADF con retardos por AIC/BIC (máximo 8), deterministas `c` y `ct` en niveles y `c` en diferencias. KPSS con ancho de banda automático. ZA en sus modalidades c/t/ct (recorte 15 %).

Muestra auditada 2005Q1-2024Q4 (T = 80), p-valores:

| Serie | ADF ct (nivel) | DF-GLS ct | KPSS ct (H0: estac.) | ADF c (1ª dif) | KPSS c (1ª dif) | ZA (mejor modalidad) | Dictamen |
|---|---|---|---|---|---|---|---|
| log Hipotecas | 0,979 | 0,937 | 0,001 | 0,000 | 0,115 | t: p = 0,022 (ruptura 2013Q4) | I(1); posible tendencia rota tras la crisis |
| log Hipotecas SA (STL) | 0,976 | 0,877 | 0,001 | 0,000 | 0,053 | ct: p = 0,040 (2011Q1) | igual |
| log Precio_m2 (pond.) | 0,340 | **0,008** | 0,003 | **0,330** | 0,152 | ct: **p = 0,014** (2012Q1) | **Ambiguo: I(1) con ruptura o casi I(2).** ADF/PP no rechazan raíz unitaria en Δ. |
| log PIB_pc (pond.) | 0,937 | 0,706 | 0,005 | 0,000* | 0,196 | n.s. | I(1). *Rechazo trivial por el escalón anual. |
| Euríbor | 0,638 (c: 0,184) | 0,152 (c: 0,076) | 0,006 | 0,000 | 0,483 | c: p = 0,069 (2021Q4) | I(1) en la muestra; el submuestreo es inestable (en 2015-2024 ADF c p = 0,04) |
| log Materiales | 0,213 | 0,102 | 0,050 | 0,000 | 0,731 | c: p = 0,047 (2020Q4) | I(1), con ruptura 2020-21 (choque de costes) |

Hallazgos:

- **ALTA. El precio es casi I(2).** El ADF de la 1ª diferencia da p = 0,30 en la serie original y 0,33 en la ponderada. El propio nb 4 lo reconocía (p = 0,48, "No concluyente"), pero luego lo "confirmó" como I(1) con un KPSS sobre la diferencia, que tiene poca potencia. Además, la app afirma "Estacionaria en 1ª diferencia" (`vecm.html`, Paso 3), lo que es inexacto. Con un componente I(2), los estadísticos de Johansen I(1) están mal dimensionados.
- **MEDIA. Hay rupturas** en 2008-2013 (hipotecas, precio) y en 2020-2022 (materiales, Euríbor). No se modelan. ZA con tendencia rota rechaza la raíz unitaria en hipotecas y precio.
- **MEDIA. Errores de transcripción en la app.**
  - `vecm.html` muestra "Log_Materiales p = 0.582": ese valor es el de **Mano de Obra**. Materiales tiene p = 0,1997.
  - `econometria.html` repite el error ("Indice_Materiales 0.5822").
  - 4.1 §14.3 da otros p-valores (PIB 0,978; precio 0,031) que no corresponden a ninguna ejecución del nb 4.

---

## 3. Selección de retardos y componentes deterministas

- **Retardos.** `03_johansen.py` usa una muestra común, con `select_order` sobre el VAR en niveles, maxlags de 4 y 6, con y sin dummies. **AIC = BIC = HQ = FPE = 2** en todas las especificaciones (la única excepción es la serie SA, donde AIC = 3). En consecuencia, k_ar_diff = 1 está bien justificado, y la frase "AIC = BIC = 2" del nb 4 es correcta.
- **Deterministas: error de rotulado (MEDIA).** El nb 4.2 usa `deterministic='co'`. 4.1 §15.4 y `vecm.html` lo describen como "constante dentro de la relación de cointegración (Caso 2)".
  - En statsmodels, `'co'` es una **constante no restringida (Caso 3)**; el Caso 2 es `'ci'`.
  - Del mismo modo, `coint_johansen(det_order=0)` es el Caso 3: sus valores críticos coinciden con los de MacKinnon-Haug-Michelis Caso 3 (69,82; 47,86…).
  - En lo sustantivo, el Caso 3 es el **adecuado**: PIB nominal, precio y materiales tienen deriva, cosa que el Caso 2 no permite.
- **Estacionalidad (ALTA).** No se usan dummies estacionales ni datos desestacionalizados, aunque la estacionalidad de ΔlogH es muy significativa.

---

## 4. Rango de cointegración

Implementación propia (`johansen.py`), validada contra statsmodels (Caso 3: idéntico en todos los decimales). Incluye:
- Casos 2, 3 y 4.
- Dummies estacionales centradas y de impulso como regresores no restringidos.
- Corrección de Reinsel-Ahn, factor (T−n·p)/T.
- **Bootstrap salvaje de Cavaliere-Rahbek-Taylor (2012)**, B = 999, secuencial.

Estadístico de traza para H0: r = 0 / H0: r ≤ 1 (k_ar_diff = 1):

| Especificación | T ef. | Caso | Traza r=0 | Traza r≤1 | VC 95 % (r=0 / r≤1) | Reinsel-Ahn r=0 / r≤1 | **p bootstrap r=0 / r≤1** |
|---|---|---|---|---|---|---|---|
| A original nb 4.2 | 82 | 3 | 92,89 | 46,45 | 69,82 / 47,86 | 81,57 / 40,78 | **0,021 / 0,516** → r = 1 |
| B auditada (pond., sin 2025), sin estac. | 78 | 3 | 87,22 | 53,23 | 69,82 / 47,86 | 76,04 / 46,41 | **0,056 / 0,146** |
| C auditada + dummies estacionales | 78 | 3 | 85,43 | 53,64 | 69,82 / 47,86 | 74,48 / 46,76 | **0,052 / 0,139** |
| C, Caso 2 (const. restringida) | 78 | 2 | 96,40 | 63,68 | 76,97 / 54,08 | 84,04 / 55,52 | 0,035 / 0,085 |
| C, Caso 4 (tendencia restringida) | 78 | 4 | 105,58 | 73,71 | 88,80 / 63,88 | 92,04 / 64,26 | 0,068 / 0,081 |
| C, k_ar_diff = 2 | 77 | 3 | 84,37 | 52,90 | 69,82 / 47,86 | 67,94 / 42,60 | 0,128 / 0,183 |

La rejilla completa (6 especificaciones × 3 casos × 3 retardos) está en `03_johansen_grid.csv`. Con los VC asintóticos, el rango "elegido" va de 1 a 5 según la especificación, el máximo autovalor da a menudo 0, y la corrección de Reinsel-Ahn da 0, 1 o 2.

Hallazgos:

- **ALTA. La evidencia de cointegración es débil y no robusta.** r = 1 solo es claro con los datos originales (que incluyen las imputaciones). Con los datos auditados, el bootstrap rechaza r = 0 solo al 10 % (p ≈ 0,05-0,07) y con k_ar_diff = 2 no lo rechaza (p = 0,13).
  - **Engle-Granger con 5 variables** no rechaza la ausencia de cointegración: τ = −2,67, p = 0,75 (A); τ = −2,92, p = 0,63 (C); VC 5 % = −4,59.
  - El **ARDL-bounds** (PSS 2001) sí rechaza: F = 5,50 (A) y 5,73 (C) frente a I(1) 5 % = 3,79. Ese contraste supone que los regresores son débilmente exógenos y que ninguno es I(2), supuestos dudosos aquí (§2 y §5).
- **CRÍTICA (documental). El ECT no es estacionario según el propio notebook.**
  - Celda 9 del nb 4.2: ADF del ECT = −2,207, p = 0,204, con el mensaje "AVISO: revisar estacionariedad".
  - Aun así, 4.1 §15.8 afirma "el test ADF sobre el ECT arroja p < 0.05, confirmando la estacionariedad", y la app (Paso 9) muestra "I(0) ECT … Estacionario → cointegración genuina ✓".
  - Además, los p-valores DF estándar no valen para una combinación estimada; con valores críticos de Engle-Granger el resultado es aún más lejano al rechazo.
- **ALTA (documental). Contradicciones sobre la cointegración.**
  - 4.1 §14.3 dice que "el test de Johansen … no detecta ninguna relación de cointegración … se descarta el VECM" (coincide con nb 4, celda 44: 4 variables, traza 39,55 < 47,85). En cambio, §15 dice r = 1.
  - La app muestra una traza de 89,14 frente a 76,97 y de 44,21 frente a 54,07. Esas cifras **no se reproducen** con ningún caso: Caso 2 da 102,53/50,95 y Caso 3 da 92,89/46,45. Además mezclan valores críticos del Caso 2 con un modelo del Caso 3.
- **MEDIA. Muestra pequeña.** T = 78-82 con 5 variables. Los VC asintóticos sobredimensionan el contraste, como muestra la diferencia entre la rejilla asintótica y el bootstrap. Ni el nb 4 ni el 4.2 aplican corrección.

---

## 5. β, α, identificación e interpretación

### 5.1 Cifras documentadas frente a reproducidas frente a especificación auditada

`04_vecm_analysis.json`. Ecuación `log H = …`; entre paréntesis, p-valores (statsmodels, misma especificación) o IC 90 % bootstrap (B = 499).

| Parámetro | Documentado | Reproducido A (nb 4.2) | Auditado C (pond., ≤2024Q4, dummies estac., Caso 3, k=1) |
|---|---|---|---|
| β log PIB_pc | +0,35 | +0,352 (p = 0,46; IC [−1,36, 2,09]; LR exclusión p = 0,55) | **−1,11** (p = 0,001; IC [−2,54, 0,51]) |
| β log Precio_m2 | +2,48 | +2,484 (p < 0,001; IC [1,54, 3,43]) | +3,04 (IC [2,16, 3,95]) |
| β Euríbor | −0,10 | −0,097 (p < 0,001) | −0,028 (p = 0,10; LR excl. p = 0,29) |
| β log Materiales | −1,09 | −1,091 (p < 0,001) | −0,79 (p < 0,001) |
| α hipotecas | −0,44 (44 %/trim) | −0,4377 con β normalizado en **Materiales**; con β normalizado en hipotecas (el de la ecuación mostrada) = **−0,401** | **−0,162 (p = 0,20)**; exogeneidad débil LR p = 0,48 |
| Semivida hipotecas | 1,2 trim | 1,35 (fórmula univariante con α coherente); ECT del sistema 1+β'α = 0,554 → 1,17 | 3,9 (univariante); sistema 3,1 |
| α precio | −0,006 (0,6 %/trim) | −0,0053 (LR p = 0,023) | **+0,0118 (p = 0,012)**: el precio *corrige* (ver 5.3) |
| Semivida precio | ≈120 trim | 131 trim | no aplica (signo opuesto) |
| α Euríbor / PIB | n.s. | n.s. (p = 0,30 / 0,36) | n.s. |
| Homogeneidad nominal (β_PIB+β_P+β_M = 0) | — | rechazada (LR = 8,97; p = 0,003) | rechazada (p = 0,013) |

### 5.2 Hallazgos

- **ALTA. α y β mal emparejados.** statsmodels normaliza β sobre la primera variable (Log_Materiales). El notebook renormaliza β sobre las hipotecas, pero **no reescala α**. El "44 %" y la "semivida 1,2" no corresponden a la ecuación publicada: lo correcto es 40,1 % y 1,35 trim. Además, la fórmula `log(0,5)/log(1+α)` ignora la dinámica del sistema.
- **ALTA. La elasticidad del PIB, +0,35, no es significativa** (p = 0,46; la exclusión no se rechaza). No puede presentarse como "elasticidad-renta moderada".
- **MEDIA. Unidades del Euríbor mal leídas.** La semielasticidad −0,097 equivale a ≈ −9,2 % de hipotecas por cada +1 pp (`exp(−0,097)−1`).
  - 4.1 §15.6 dice "−0,10 %": error de un factor 100.
  - La app dice "−10 %": aproximadamente correcto.
  - Con datos auditados la semielasticidad es −0,028 y no significativa.
- **ALTA. La interpretación económica no se sostiene.**
  - Una elasticidad de **+2,48** del número de hipotecas respecto al precio no es una curva de demanda: a igualdad de renta y tipos, la demanda debería caer con el precio. Lo que recoge es el **co-movimiento del ciclo de crédito y precios** (auge 2005-07, desplome 2008-13, recuperación).
  - Con r = 1 y sin restricciones identificadoras contrastadas, el vector es una **forma reducida**. Llamarlo "demanda" o "efecto especulativo" no está identificado.
  - Las variables son **nominales** (PIB, precio y materiales sin deflactar) y la homogeneidad se rechaza. El β de materiales (−1,09) puede estar actuando como proxy de nivel de precios o tendencia, no como "restricción de oferta".

### 5.3 Normalización alternativa: el precio es la variable que corrige

En C, las hipotecas son débilmente exógenas (p = 0,48) y el precio no lo es. Normalizando sobre el precio (`05_price_norm_ardl.json`):

`log P* = 0,33·log H (p<0,001) + 0,37·log PIB (p=0,001) + 0,26·log Mat (p<0,001) + 0,009·Euríbor (p=0,07)`, con α_P = −0,036 (p = 0,007).

Es una ecuación de precios de la vivienda con signos razonables: crédito, renta y costes de construcción. El ARDL condicional del precio coincide en lo esencial: 0,30·log H + 0,71·log PIB; bounds F = 8,75, p < 0,001.

Aun así, el β recursivo normalizado en el precio es inestable. Entre 2016 y 2024, el coeficiente de log H va de −3,3 a 0,9 (`figs/beta_recursivo_norm_precio.png`). **Esta normalización es preferible, pero hay que presentarla con cautela.**

### 5.4 Estabilidad

`04_beta_recursivo.csv`, `figs/beta_estabilidad.png`:

- Ventanas móviles de 48 trimestres: β_precio oscila entre −28,9 y 5,8 en A, y entre −3,4 y 224 en C.
- El β recursivo de A es estable desde 2016 (precio entre 1,96 y 3,22), pero el de C no.
- Las raíces de la representación en niveles son correctas: 4 unitarias y la mayor del resto 0,94 (A) / 0,94 (C).

**MEDIA. No hay contraste formal de constancia de β** (Hansen-Johansen) ni dummies de ruptura en el nb.

---

## 6. Diagnósticos de residuos

| Contraste | A original | C auditada |
|---|---|---|
| Portmanteau (8) | 183,8; p = 0,222 (reproduce el nb) | — |
| LM autocorrelación h=1 (Edgerton-Shukur F) | p = 0,75 | p = 0,73 |
| LM h=4 | p = 0,46 | p = 0,52 |
| Normalidad multivariante (Lütkepohl) | 230,2; p < 0,001 | 597,1; p < 0,001 |
| JB por ecuación (p) | Mat 0,00 · Eur 0,00 · PIB 0,00 · Pre 0,76 · Hip 0,79 | Mat 0,00 · Eur 0,00 · PIB 0,00 · Pre 0,67 · Hip 0,26 |
| ARCH-LM(4) por ecuación (p) | Eur 0,00 · PIB 0,00 · resto > 0,6 | Eur 0,00 · PIB 0,09 · resto > 0,17 |

- **BAJA/MEDIA.** No hay autocorrelación. La no normalidad y el ARCH se concentran en Euríbor (saltos 2008 y 2022), PIB (escalón anual) y materiales (2021-22).
- La app califica la no normalidad de "desviación leve, aceptable": es incorrecto, el estadístico vale 230 frente a un VC de 18.
- Consecuencia: para la inferencia sobre IRF/FEVD hace falta bootstrap (salvaje o por residuos), no bandas asintóticas.

---

## 7. IRF y FEVD: identificación, sensibilidad e incertidumbre

`04_vecm_analysis.json`, figuras `figs/irf_A_original_nb42.png` y `figs/irf_C_auditada_dumest.png` (bandas bootstrap 90 %, B = 499, Cholesky + GIRF).

FEVD(h = 20) de log Hipotecas:

| Shock | Documentado (Cholesky orden nb) | A: rango en 120 ordenaciones (mín/med/máx) | A: GFEVD Pesaran-Shin | A: IC 90 % bootstrap | C auditada: Cholesky / GFEVD / rango |
|---|---|---|---|---|---|
| Precio | 53,3 % | 49,3 / 51,1 / 55,7 | 47,6 % | [10,3 ; 72,4] | 38,5 / 29,8 / [7,2 ; 50,7] |
| Materiales | 38,8 % | 26,5 / 35,2 / 41,8 | 36,6 % | [5,8 ; 68,5] | **0,9** / 0,7 / [0,2 ; 12,0] |
| Euríbor | 2,2 % | **2,2** / 8,5 / 17,6 | **11,4 %** | [0,3 ; 27,0] | 6,5 / 5,2 / [6,5 ; 15,6] |
| PIB_pc | 2,6 % | 0,3 / 1,5 / 3,1 | 0,9 % | [0,9 ; 28,9] | 23,5 / 15,4 / [6,9 ; 23,5] |
| Propio | 3,0 % | 2,8 / 3,6 / 4,8 | 3,5 % | [1,8 ; 15,9] | 30,6 / 48,9 / [27,1 ; 71,1] |

Hallazgos:

- **CRÍTICA (conclusión publicada). "El Euríbor explica solo el 2,2 %… resultado robusto" es falso.**
  - 2,2 % es el **mínimo** de las 120 ordenaciones de Cholesky.
  - La GFEVD, que no depende del orden, da 11,4 %.
  - El IC bootstrap 90 % es [0,3 %, 27 %].
  - Con datos auditados, el peso de los materiales (38,8 %) desaparece (0,9 %).
  - La narrativa de que "la oferta domina y la política monetaria no" no tiene soporte.
- **ALTA. Las IRF de la app no se reproducen.**
  - La app publica una "respuesta acumulada en desviaciones estándar" de +0,61 (precio), −0,50 (materiales), −0,09 (Euríbor) y +0,11 (PIB).
  - El nb imprime la **suma acumulada de IRF en niveles** (+2,00; −1,70; −0,43; +0,45). Esa suma no tiene sentido en un VECM en niveles, porque las IRF ya son respuestas del nivel.
  - La respuesta correcta en h = 20 (log-puntos ante un choque de 1σ) es +0,131 [0,011; 0,164], −0,112 [−0,149; −0,026], −0,019 [−0,072; 0,037] y +0,016 [−0,034; 0,070].
  - El efecto del Euríbor y el del PIB **no son significativos**.
- **MEDIA. Orden de Cholesky discutible.** El orden Materiales → Euríbor → PIB → Precio → Hipotecas supone que el Euríbor no responde en el trimestre al PIB español (razonable) y que los materiales no responden al Euríbor (discutible, correlación de residuos 0,34-0,43). Hay que **informar las GIRF** y la sensibilidad al orden.
- **ALTA. Confusión entre IRF y causalidad.** Se escribe "la causalidad va PIB → hipotecas", "confirma exogeneidad" o "relaciones causales estructurales". α no significativo indica exogeneidad *débil* respecto a β, no causalidad. Las IRF de Cholesky son descomposiciones condicionadas a un supuesto recursivo.

### 7.1 VAR del nb 4 (§8) y página `econometria.html`

- **ALTA. La app describe un modelo distinto del estimado.**
  - La app dice: "VAR en diferencias, 4 variables (Δlog H, Δlog P, ΔEur, Δlog PIB)", con FEVD de 70,3 % / 18,1 % / 11,5 %.
  - Esas cifras **sí se reproducen** (`01_reproduce.json`), pero salen de un **VAR(4) de 5 variables** (ΔlogPIB, Tasa_Paro en niveles, **log Precio en niveles**, ΔEuríbor, ΔlogH). El 18,1 % es Precio 8,2 + Euríbor 9,9, y el 11,5 % es PIB 8,0 + Paro 3,5.
  - Mezcla un precio I(1) en niveles, rotulado como "I(0)" en el código, con variables diferenciadas, y estima 21 parámetros por ecuación con 79 observaciones.
  - Un VAR de verdad con 4 variables en diferencias da otra cosa: propio 94,8 % (p = 1), 77,6 % (p = 2) o 75,7 % (p = 4).
- **MEDIA. La "tabla IRF escalada a shock de 1 %" está mal escalada.**
  - Divide la IRF ortogonal por la desviación típica del residuo, cuando el tamaño del choque es el elemento diagonal de Cholesky.
  - Un "1 %" en una variable en log es 0,01, no 1.
  - La lectura "+6,04 % … elasticidades porcentuales puras" de `econometria.html` es incorrecta.
- **BAJA.** En las celdas 47 y 49 del nb 4, `groupby().ffill().bfill()` no agrupa el `bfill`. Es inocuo con estos datos, porque los NaN son finales y el ffill los rellena antes.

---

## 8. Econometría de panel (exploratoria, 52 provincias × 80 trimestres, 2005Q1-2024Q4)

`06_panel.py` → `06_panel.json` (linearmodels 7.1 instalado en el entorno de la sesión).

| Análisis | Resultado |
|---|---|
| CD de Pesaran (ΔlogH) | CD = 48,8 (p ≈ 0), ρ̄ = 0,15. En ΔlogP: CD = 209, ρ̄ = 0,65. **Fuerte dependencia transversal.** |
| CIPS (VC simulados N=52, T=80; 5 %: c −2,11 / ct −2,59) | log H: −4,71 (c) → el componente provincial (neto de la media transversal) es **I(0)**. log P: −2,01 (c) / −2,81 (ct). log PIB: −2,07 / −2,30 (I(1)). |
| FE niveles + Driscoll-Kraay (h = 4) | lp 1,13 (0,32); ly 0,88 (0,65, n.s.); eu **+0,12** (0,04); lm −1,70 (0,62). Los residuos tienen CD = 179: regresión en niveles con dependencia transversal, **de riesgo espurio**. Los errores clúster por provincia son 3-5 veces menores: no usarlos. |
| FE primeras diferencias + DK | lp 1,14 (0,51, p = 0,03); ly, eu, lm n.s. |
| MG (ARDL(1,1)-ECM por provincia, bruto, 4 regresores) | θ_P 1,74 (0,18); θ_PIB 1,60 (0,22); θ_Eur 0,008 (n.s.); θ_M −1,84 (0,13); φ̄ = −0,51 |
| PMG bruto | θ_P 1,40 (0,10); θ_PIB 1,45 (0,19); θ_Eur 0,024 (0,011); θ_M −1,70 (0,12); φ̄ = −0,38 (52/52 negativos). **Hausman rechaza la homogeneidad** (48,9; p ≈ 0) → preferir MG. |
| PMG sobre datos *demeaned* transversalmente (controla factores comunes homogéneos) | **θ_P = 0,33 (0,10)**; θ_PIB = 0,23 (0,19, n.s.); φ̄ = −0,59; Hausman p = 0,47 (PMG aceptable) |
| Gt tipo Westerlund (nulo simulado) | −3,65 (bruto) y −4,83 (demeaned), p_sim < 0,005. Ojo: en el caso demeaned, el rechazo refleja sobre todo que log H provincial relativo es I(0). |

Conclusiones del panel (**complemento recomendable, no sustituto**):

- **ALTA (interpretativa).** La elasticidad hipotecas-precio **entre provincias**, neta de factores comunes, es ≈ 0,3 y no 2,5. El 2,48 nacional recoge sobre todo el ciclo común de crédito y precios, no un efecto precio identificable.
- Los efectos de las variables nacionales (Euríbor, materiales) **no se identifican por separado** de los efectos temporales en un panel. Su estimación descansa en la variación temporal (80 trimestres), igual que el VECM nacional, y además con CD fuerte.
- Para la siguiente fase se recomienda reportar como robustez:
  - **CS-ARDL / CCE-MG** (Chudik-Pesaran), o PMG con *demeaning*, para las elasticidades provinciales.
  - **CD-test** y **CIPS**.
  - Westerlund con bootstrap para la dependencia transversal, si se implementa una librería.

---

## 9. Cifras a corregir en documentación y app

| Lugar | Afirmación actual | Situación | Acción |
|---|---|---|---|
| 4.1 §15.8, `vecm.html` Paso 9 | "ADF del ECT p < 0,05 / I(0) ✓" | **Falso** (p = 0,204; EG p = 0,75) | Eliminar; informar el bootstrap de Johansen y el ARDL-bounds |
| 4.1 §15.4, `vecm.html` Paso 4 | "`co` = constante dentro, Caso 2" | Es el Caso 3 | Corregir el rótulo |
| `vecm.html` Paso 4 (gráfico l. 617-628) | Traza 89,14 / 76,97; 44,21 / 54,07 | No reproducible | Sustituir por las cifras v2 (§4) con p bootstrap |
| 4.1 §14.3 | "Johansen no detecta cointegración → se descarta VECM" | Contradice §15 | Unificar con el resultado v2 |
| `vecm.html` Paso 3, `econometria.html` | Materiales p = 0,582; "Precio estacionario en 1ª dif." | Error (0,582 es Mano de Obra; ADF Δprecio p = 0,30) | Corregir |
| 4.1 §14.3 | PIB p = 0,978; precio p = 0,031; paro ZA p = 0,048 | No corresponden a ejecuciones presentes | Recalcular |
| Todos | α_hip −0,44, "44 %/trim", semivida 1,2 | Mal normalizado (−0,40; 1,35) y no robusto (−0,16 n.s. en C) | Recalcular con v2 |
| Todos | α precio −0,006, semivida 120 trim (30 años) | 131 en A; signo opuesto en C | Retirar la narrativa de "30 años" |
| 4.1 §15.6, app | Elasticidad PIB +0,35 | n.s. (p = 0,46) | Indicar n.s. o recalcular |
| 4.1 §15.6 | Euríbor "−0,10 %" | Es ≈ −9 % por pp (A); n.s. en C | Corregir |
| Todos | "+2,48 efecto especulativo domina" | Forma reducida del ciclo crédito-precio | Reinterpretar |
| `vecm.html`, `app.py` l. 1844 y 2255 | FEVD 53,3 / 38,8 / 2,6 / 2,2 "robusto" | Reproduce, pero depende del orden y de los datos | Sustituir por GFEVD + rango + IC |
| `vecm.html` (l. 746-776), `app.py` l. 1845 | IRF acumuladas 0,61 / −0,50 / −0,09 / 0,11 | No reproducibles | Sustituir por IRF en nivel con bandas |
| `econometria.html`, `app.py` l. 1841 y 2253 | "VAR 4 var en diferencias: 70,3 / 18,1 / 11,5" | Proceden de un VAR(4) mixto de 5 variables | Corregir la descripción o reestimar |
| `econometria.html` §4 | "IRF reescalada = elasticidad pura (+6,04 %)" | Escalado incorrecto | Eliminar |
| 4.1 §15, app | "relaciones causales", "confirma exogeneidad", "causalidad PIB → hipotecas" | IRF ≠ causalidad | Reformular |
| `vecm.html` Paso 9 | "No normalidad leve, aceptable" | 230 frente a VC 18; ARCH en Eur/PIB | Reformular y usar bootstrap |

---

## 10. Propuesta de especificación final (para implementar en la Fase V)

**Objetivo declarado:** describir la relación de largo plazo y la dinámica conjunta crédito hipotecario–precios–renta–tipos. No es un modelo de predicción ni una curva de demanda estructural.

1. **Datos** (`src/models/econometrics/`, a partir del panel maestro v2):
   - Muestra: 2005Q1 hasta el último trimestre con **todas** las series observadas. Hoy es 2024Q4: T = 80, efectiva 78. Sin `ffill`/`bfill`.
   - log Hipotecas: número nacional, suma provincial o serie INE nacional, NSA con dummies, o SA oficial si INE la publica.
   - log Precio: Tinsa IMIE nacional, o media provincial **ponderada** (población u hogares). Como robustez, INE IPV desde 2007.
   - log PIB_pc: **sustituir el PIB provincial anual repetido** por el PIB trimestral nacional de la Contabilidad Nacional Trimestral del INE (corregido de estacionalidad y calendario) dividido por la población. Si no está disponible, usar la media ponderada actual con la advertencia del escalón.
   - Euríbor 12m: media trimestral.
   - log Índice de materiales.
   - Variante de robustez en **términos reales** (precio, PIB y materiales deflactados por el IPC nacional), dado que la homogeneidad nominal se rechaza.
2. **Deterministas:** Caso 3 (constante no restringida; `deterministic='co'`) + **3 dummies estacionales centradas** (`seasons=4` o `exog`). Sensibilidad: Casos 2 y 4, e impulso COVID 2020Q2-Q3.
3. **Retardos:** k_ar_diff = 1 (VAR(2), seleccionado por AIC/BIC/HQ/FPE sobre muestra común). Sensibilidad k = 2.
4. **Rango:** traza asintótica + Reinsel-Ahn + **bootstrap salvaje CRT (B = 999)**, junto con el máximo autovalor y Engle-Granger.
   - Con los datos actuales: r = 1 con p_boot(r = 0) = 0,052 → informar como "evidencia de cointegración al 10 %, frágil".
   - Si con datos v2 el p_boot supera 0,10, presentar un **VAR en diferencias con dummies** como modelo principal y el VECM como sensibilidad.
5. **Identificación de β:** r = 1.
   - Contrastar exogeneidad débil de cada variable y su exclusión.
   - Contrastar la restricción sobreidentificadora "Euríbor excluido de β" (LR p = 0,29 en C) y la homogeneidad.
   - **Normalizar sobre la variable que corrige.** Con los datos actuales es el precio: α_P p = 0,007, mientras que para las hipotecas la exogeneidad débil da p = 0,48. Presentar también la normalización sobre hipotecas con su α no significativo.
   - Interpretar como "equilibrio de largo plazo crédito–precio (forma reducida)".
6. **Dinámica:** GIRF de Pesaran-Shin (invariantes al orden) + Cholesky con el orden del nb y su rango sobre las 120 ordenaciones. **Bandas bootstrap 90 % (B ≥ 499)**. Respuestas en **nivel**, nunca sumas acumuladas. FEVD como GFEVD + rango + IC, sin cifras puntuales "robustas".
7. **Diagnósticos y estabilidad:** LM(1,4) Edgerton-Shukur, ARCH-LM por ecuación, normalidad, raíces, β recursivo y en ventanas, y contraste de constancia de β.
8. **Complementos:**
   - **ARDL-bounds** (PSS 2001, caso 3) para log H y log P.
   - **Panel:** CD-test, CIPS, MG/PMG (ARDL(1,1)-ECM) bruto y demeaned, Hausman, y FE-DK solo en diferencias.
9. **Salidas** a `artifacts/econometrics/vecm_v2.json` (todas las cifras que muestre la app), generadas por script y consumidas por `vecm.html`/`app.py`. Prohibido copiar cifras a mano en las plantillas.

### Decisiones que requieren arbitraje del coordinador

- (a) ¿Se incorpora el PIB trimestral nacional (INE CNTR) al pipeline de datos? Recomendado.
- (b) ¿Variable de precio principal: Tinsa ponderado o INE IPV (muestra desde 2007)?
- (c) Si con datos v2 la cointegración no supera el 10 % bootstrap, ¿se acepta degradar el VECM a análisis de sensibilidad frente a un VAR en diferencias? Recomendado.
- (d) Retirar de la app y del asistente Gemini el mensaje "el Euríbor explica solo el 2 %" y la narrativa de "rigidez de 30 años".

---

## 11. Reproducibilidad

Ejecutar desde `reports/audit/01_econometria/` con Python 3.13, statsmodels 0.15, arch 9.0 y linearmodels 7.1 (`pip install arch linearmodels`):

| Script | Contenido | Salidas |
|---|---|---|
| `common.py` | Carga y construcción de series: original (réplica literal nb 4.2) y auditada | — |
| `01_reproduce.py` | Reproducción de nb 4.2 y nb 4 (§7-8) | `01_reproduce.json/.log` |
| `02_unit_root.py` | ADF, DF-GLS, PP, KPSS, ZA | `02_unit_root.csv/.log` |
| `johansen.py`, `03_johansen.py [B]` | Johansen propio con Casos 2-5, Reinsel-Ahn y bootstrap CRT; selección de retardos y rejilla | `03_johansen.json`, `03_johansen_grid.csv`, `03_johansen.log` (B = 999) |
| `vecm_tools.py`, `04_vecm_analysis.py [B]` | β/α, LR, diagnósticos, FEVD/GFEVD/permutaciones, bootstrap IRF, estabilidad | `04_vecm_analysis.json/.log` (B = 499), `04_beta_recursivo.csv`, figuras |
| `05_price_normalisation_ardl.py` | Normalización sobre el precio, β recursivo y ARDL-bounds | `05_price_norm_ardl.json/.log`, `05_beta_recursivo_norm_precio.csv` |
| `06_panel.py` | CD, CIPS, FE-DK, MG/PMG, Gt | `06_panel.json` |
| `07_figures.py` | Figura de series nacionales | `figs/series_nacionales.png` |

Semillas fijas en todos los bootstraps. Tiempos: menos de 1 minuto por script con 1 CPU.
