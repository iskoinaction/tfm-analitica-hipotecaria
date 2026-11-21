# Auditoría 03 — Sentido económico del TFM (economista)

**Ámbito:** selección de variables de demanda hipotecaria, coherencia económica del VAR/VECM, plausibilidad de las proyecciones 2026‑2030, interpretaciones del business case y del dashboard, y propuestas.
**Fecha de la auditoría:** 21‑11‑2026. **Autor:** agente 03 (economía española / ciclo inmobiliario).
**Reproducibilidad:** todo lo cuantitativo sale de `reports/audit/03_economia/analisis_economico.py` (ejecutar desde la raíz del repo; tarda ~1 min). Las series oficiales descargadas están en `reports/audit/03_economia/data/` (INE Tempus3 y API de datos del BCE). Las salidas son `resultados.json`, los `*.csv` y las figuras `fig_0*.png` de esa carpeta. No se ha modificado ningún otro fichero.

---

## 0. Resumen ejecutivo

1. **La variable objetivo no mide lo que se dice.** `Hipotecas_Total` es el número de hipotecas sobre el **total de fincas**: incluye rústicas, solares y "otras urbanas", no solo viviendas. Las viviendas son el 70,8 % del total en 2006 y el 77,9 % en 2025. Además, la función `limpiar_numero` (notebook 3) interpreta mal **414 de 13.104 valores mensuales**: el fichero del INE trae `"19.16"`, que significa 19.160, y se lee como 19,16. Por eso el dataset queda **‑13,1 % por debajo del INE en 2005, ‑9,4 % en 2006, ‑4,4 % en 2024 y ‑2,6 % en 2025**. El error es mayor en el boom, así que se subestima la amplitud del ciclo. Con un parseo correcto la diferencia con el INE baja a un máximo de 0,58 %.
2. **El VECM no aguanta los cambios de especificación, y su relato económico ("la demanda depende de la oferta, no del Euribor") no se sostiene:**
   - El ADF del término de corrección de error da **p = 0,204** en el propio notebook. La web dice "Estacionario → cointegración genuina ✓".
   - Si se quita 2025, que está imputado con ffill (todo el PIB_pc y Materiales desde 2025T2), **Johansen pasa a r = 2**.
   - El orden de Cholesky del notebook es, **de los 120 órdenes posibles, el que da la cuota mínima al Euribor**: 2,2 %, frente a un rango de 2,2‑17,6 %. Con el Euribor primero sale un 12,1 %. Sin Materiales, el Euribor explica el **42,5 %**.
   - La "rigidez de precios con semivida de 30 años" sale de un α del precio con el **signo que amplifica** el desequilibrio, no con el que lo corrige.
   - El propio β (semielasticidad de ‑0,097) implica que la subida de tipos de 2022‑23 (+4,6 pp) reduce las hipotecas un **‑36 %** a largo plazo. Eso contradice que el Euribor tenga un efecto "transitorio".
3. **El ciclo observado contradice la conclusión del FEVD.** En 2023 las hipotecas sobre vivienda cayeron un **‑17,9 %** respecto a 2022, con el Euribor pasando de ‑0,49 % (2021T4) a 4,12 % (2023T3). En ese mismo periodo, Materiales bajó un ‑10,8 % y el precio subió un +4,6 %. Según el β del TFM, ambos movimientos deberían haber hecho **subir** las hipotecas.
4. **Las proyecciones 2026‑2030 ya no valen como escenario base.**
   - Euribor: el TFM supone 2,00 % en 2026. La media observada en enero‑octubre de 2026 es 2,77 % y el dato de octubre es **3,239 %**.
   - Inflación: el TFM supone 1,88 % para 2026. BdE y CE proyectan **3,9 %**.
   - Paro: el suelo "NAIRU" del 8,5 % se aplica provincia a provincia. Hay 20 provincias con paro medio de 2025 por debajo de 8,5 %, y el suelo las sube de golpe hasta +4,8 pp.
   - PIB pc: crece al CAGR histórico nominal en las **52/52** provincias, porque el tope sustituye al SARIMA.
   - Precio m²: llega a +8,8 %/año en Málaga, con la renta al 2,2 % y sin ningún efecto de vuelta sobre la demanda.
5. **El business case hace afirmaciones causales y de negocio sin soporte**, recogidas abajo con archivo:línea. La principal: "la oferta constructiva es palanca estructural prioritaria frente a la política monetaria".

---

## 1. Hallazgos por gravedad

| ID | Gravedad | Hallazgo | Evidencia (reproducible) |
|---|---|---|---|
| E1 | **CRÍTICA** | `Hipotecas_Total` mezcla total fincas y además está mal parseado (414 valores mensuales, entre ‑13 % y ‑2,6 % anual frente al INE). El target de todos los modelos está sesgado y no es "demanda hipotecaria de vivienda". | `hipotecas_dataset_vs_INE_anual.csv`; series INE HPT34936 (total fincas) y HPT34618 (viviendas); `resultados.json → hipotecas_parse` |
| E2 | **CRÍTICA** | La web afirma que el ECT es estacionario y la cointegración "genuina", pero el notebook da ADF p = 0,204 ("AVISO: revisar"). En ninguna de las 8 variantes probadas baja de 0,05 (p entre 0,059 y 0,204). | Notebook 4.2, celda 9; `vecm_robustez.csv`; `vecm.html:576-577` |
| E3 | **CRÍTICA** | Conclusión "el Euribor explica el 2,2 %; la demanda la determina la oferta": depende del orden de Cholesky, que en el notebook es justo el que minimiza la cuota del Euribor. No es robusta a quitar 2025 imputado (Materiales pasa de 38,8 % a 20,4 %), ni a ponderar por población (6,4 %), ni a quitar Materiales (Euribor 42,5 %). | `fig_03_fevd_sensibilidad_orden.png`; `vecm_robustez.csv` |
| E4 | **ALTA** | El rango de cointegración "r = 1 exactamente" no es robusto: con la muestra 2005T1‑2024T4 (sin imputaciones) la traza da r = 2 en S1‑S6. Con r = 2, normalizar solo sobre log(H) no identifica la relación de largo plazo. | `vecm_robustez.csv` |
| E5 | **ALTA** | Interpretación errónea de α. α_precio = ‑0,0058 (p = 0,006) con β_precio < 0: el precio **amplifica** el desequilibrio, no lo corrige. La "semivida de 30 años" no tiene sentido. Además, `ln(0,5)/ln(1+α_i)` por variable no es la velocidad de ajuste del sistema: esa velocidad la da β'α. | `resultados.json → vecm[0].alpha_corrige_desequilibrio` |
| E6 | **ALTA** | La elasticidad de +2,48 al precio se presenta como "efecto especulativo". En realidad es una co‑variación de forma reducida del ciclo crédito‑precios‑transacciones (simultaneidad; el crédito causa precios). No es una curva de demanda. Tampoco hay homogeneidad nominal: 0,35 + 2,48 ‑ 1,09 = 1,74. | §3.2 |
| E7 | **ALTA** | `Indice_Materiales` no es un determinante de la demanda de hipotecas. Es la media simple no ponderada de los índices de precios por material (MITMA), un proxy de inflación de costes y energía: correlación de 0,75 con la variación interanual del IPC. En 2021‑23 se movió en sentido contrario al Euribor (correlación ‑0,83), así que absorbe el shock monetario e inflacionario. | §3.1 |
| E8 | **ALTA** | Proyecciones Euribor e IPC desfasadas y con fuente mal atribuida. Se presentan como "Staff Projections BCE/FMI", pero el BCE no proyecta el Euribor a 12 meses, y el notebook cita blogs (uci.es, futurfinances.com). Las filas de 2025 traen Euribor 2,50 % "observado" cuando el real fue 2,223 %, e IPC 2,80 sin verificar (IAPC 2025 según BdE: 2,7 %). | §3.4; `data/ecb_euribor12m.csv` |
| E9 | **ALTA** | Suelo de paro del 8,5 % aplicado a cada provincia, sin fuente verificable: la NAWRU nacional de AMECO es 11,7 % en 2026. Sube 20 provincias por encima de su nivel observado (Lleida de 5,2 % a 8,5 %; Gipuzkoa de 6,39 % a 8,50 % en un trimestre). | `paro_suelo_nairu_por_provincia.csv`; `fig_04_paro_suelo_nairu.png` |
| E10 | **ALTA** | En las filas 2025 de `predicciones_provinciales_2026_2030.csv`, precio, paro y PIB_pc se **congelan** en el último valor y **sustituyen** datos 2025 que sí están observados (el precio ponderado creció un 10,8 % en 2025). | `resultados.json → proyecciones.precio_2025_csv_constante_igual_ultimo_obs = true` |
| E11 | MEDIA | PIB_pc proyectado = tope de CAGR histórico nominal 2005‑2024 en 52/52 provincias, así que el SARIMA no se usa (el README dice lo contrario). Crece un 2,2 %/año nominal frente a aproximadamente 4‑5 % nominal per cápita que se desprende de las previsiones de CE/BdE. El SARIMA estacional se aplica a una serie anual repetida en escalones: la "estacionalidad de Q4 por consumo navideño" del README no existe en los datos. | §3.4 |
| E12 | MEDIA | Sendas mutuamente incoherentes: precio de +3,4 % a +8,3 %/año nacional (Málaga hasta 8,8 %/año, +52 % en 5 años), renta +2,2 %/año, Euribor plano y compraventas de +3 % a +6 %/año. La accesibilidad se deteriora sin ningún efecto sobre la demanda. Compraventas 2026 proyectadas: 757.010; el INE observa ‑3,6 % interanual en enero‑septiembre de 2026. | `proyecciones_agregado_nacional.csv`; INE ETDP1826 |
| E13 | MEDIA | `Spread_Hipotecas` (TAE ‑ Euribor 12m) no es "margen comercial de la banca". Fue negativo en 2023‑24 por el peso de las hipotecas a tipo fijo y la curva invertida, y no recoge comisiones ni vinculaciones. | dataset, columnas Euribor y Spread |
| E14 | MEDIA | VAR del notebook 4: la "elasticidad" de +6,04 es un multiplicador de impacto del crecimiento de las hipotecas ante un shock de **nivel** de log‑precio. Ese nivel se trata como I(0) en el VAR y como I(1) en el VECM, lo cual es incoherente. No es una "elasticidad porcentual pura". | `econometria.html:283-287` |
| E15 | MEDIA | Variables de demanda omitidas: empleo (el paro tiene correlación ‑0,68 con las hipotecas interanuales, más que cualquier otra variable), renta disponible de los hogares, condiciones de oferta de crédito (EPB), tipo real, formación de hogares, demanda extranjera y compras al contado. | §3.1 |
| E16 | BAJA | PIB_pc, Población y Edad_Media son anuales repetidos (escalones). PIB_pc no es renta de los hogares y en Madrid está inflado por el efecto sede. `tasa_ahorro` es nacional y sin desestacionalizar (valores negativos en T1). Agregar con medias simples de provincias (precio, PIB) da a Soria el mismo peso que a Madrid. | `fig_01` (media simple frente a ponderada) |
| E17 | BAJA | README:201 afirma que el mínimo histórico del paro fue 7,95 % en 2007T2 y que "la OCDE estima la NAIRU en el 9–10 % para 2030". No he podido verificar ninguna de las dos cifras; la NAWRU de AMECO consultada da 11,4 % en 2027. | §3.4 |

---

## 2. Ciclo 2005‑2025: qué dicen los datos (análisis descriptivo)

Figuras: `fig_01_ciclo_2005_2025.png` (niveles) y `fig_02_hipotecas_vs_euribor_interanual.png` (variaciones interanuales). Tabla: `ciclo_fases.csv`. Hipotecas sobre **viviendas** del INE (no del dataset). Precio Tinsa ponderado por población.

| Fase | Hip. viv./año (INE) | Var. hipotecas | Euribor medio | Δ Euribor | Precio m² | Paro medio | Materiales |
|---|---|---|---|---|---|---|---|
| Boom 2005‑07 | 1.279.558 | — | 3,41 % | +2,36 pp | +36,6 % | 8,8 % | +26,4 % |
| Crisis 2008‑13 | 496.147 | **‑83,9 %** | 1,91 % | ‑4,15 pp | ‑35,6 % | 20,3 % | +11,2 % |
| Recuperación 2014‑19 | 292.706 | +80,9 % | 0,01 % | ‑0,81 pp | +10,3 % | 18,9 % | +2,5 % |
| COVID 2020‑21 | 377.905 | +15,7 % | ‑0,40 % | ‑0,21 pp | +3,7 % | 15,3 % | +29,6 % |
| Subida de tipos 2022‑23 | 422.536 | ‑8,9 % (2023: **‑17,9 %** vs 2022) | 2,48 % | **+4,44 pp** | +9,7 % | 12,7 % | ‑3,9 % |
| 2024‑25 | 461.976 | +30,8 % | 2,75 % | ‑1,73 pp | +18,9 % | 11,0 % | +2,8 % |

Fuera de la muestra del TFM (INE): las hipotecas sobre vivienda de enero‑agosto de 2026 suben un **+5,1 %** interanual (336.897), mientras que las compraventas de enero‑septiembre de 2026 caen un **‑3,6 %**. El IPV del INE marca **+12,2 %** interanual en 2026T2 (serie IPV1376).

Lectura económica:
- **2008‑2013.** El Euribor cae 4 pp y aun así las hipotecas se desploman un 84 %. Lo que manda es la **oferta de crédito** (crisis bancaria, reestructuración de cajas) y el **empleo** (paro medio del 20 %). Un modelo sin indicadores de condiciones crediticias ni de empleo atribuye ese colapso a cualquier variable que se mueva a la vez: precio y Materiales.
- **Correlaciones interanuales** de las hipotecas sobre vivienda:
  - Con el ΔEuribor: ‑0,01 en 2006‑2025, porque el credit crunch domina, pero **‑0,63 en 2021‑2025**.
  - Con el Δparo: ‑0,68 en toda la muestra.
  - Con el Δprecio: +0,41, que es co‑movimiento cíclico y no causalidad.
- **2022‑2023 es el experimento natural más limpio de la muestra.** Las hipotecas cayeron con la subida de tipos aunque los precios siguieron subiendo y Materiales bajó. Un FEVD que da un 2,2 % al Euribor es incompatible con este episodio. El ajuste fue además menor de lo que el β sugeriría porque la cuota de nuevas hipotecas a tipo fijo era alta y por el ahorro acumulado.
- **La ratio hipotecas de vivienda / compraventas es mayor que 1 en 2008‑13 (1,24).** La estadística de hipotecas del INE incluye operaciones que no son de compra (refinanciaciones, novaciones inscritas, autoconstrucción). No sirve tal cual como "porcentaje de compras financiadas"; para eso hay que usar la estadística notarial de compraventas con préstamo.

---

## 3. Detalle de los hallazgos

### 3.1 Selección de variables (pregunta 1)

**Qué sobra o está mal usado:**
- **`Indice_Materiales`.** Es la media simple de niveles de índices de precios de materiales (cemento, acero, etc.; MITMA, Península y Baleares), base heterogénea, sin ponderar por consumos. Económicamente es un **shock de costes y energía** que afecta a la oferta de obra nueva con años de retraso, y por esa vía al precio. No es un determinante directo del número de hipotecas.
  - En la muestra se comporta como un **proxy de inflación** (correlación de 0,75 con el IPC interanual).
  - En 2021‑2023 subió más de un 30 % interanual justo antes de la subida de tipos y cayó cuando los tipos estaban altos (correlación ‑0,83 con el nivel del Euribor).
  - Ordenado primero en Cholesky, se queda con la varianza común del shock inflación → BCE → hipotecas.
  - Si se quiere un canal de oferta, la variable correcta son los **visados de obra nueva** (MITMA), las viviendas terminadas o el stock de vivienda nueva.
- **`Indice_Mano_Obra`.** Mismo problema; además deja de publicarse en 2025T1.
- **`Spread_Hipotecas` como "margen bancario".** Ver E13. Para pricing es mejor el TAE/TEDR de nuevas operaciones de vivienda (BdE/BCE MIR) junto con el porcentaje de hipotecas a tipo fijo (INE, tabla 24456).
- **`PIB_pc`.** Nominal, anual, mide producción y no renta de los hogares, y está distorsionado por el efecto sede. Sustituir por la renta disponible bruta de los hogares per cápita (INE Contabilidad Regional) o por la renta neta media por hogar (INE ADRH, provincial).
- **`tasa_ahorro`.** Nacional y sin desestacionalizar. Si se usa, la versión desestacionalizada (INE CNTR, sector hogares).
- **`IPC`.** Entra como tasa interanual. Su papel económico es convertir el tipo nominal en tipo real: `tipo real = TAE ‑ inflación esperada`.

**Qué falta, por orden de prioridad para España:**

| Bloque | Variable propuesta | Fuente (periodicidad / nivel) |
|---|---|---|
| Esfuerzo / accesibilidad | Cuota inicial / renta del hogar con el tipo de nuevas operaciones; años de renta para comprar | BdE (indicadores de accesibilidad), INE ADRH, precio INE IPV o MITMA |
| Coste de financiación | TAE de nuevas operaciones de vivienda; tipo real; porcentaje a tipo fijo | BCE MIR (M.ES.B.A2C.AM.R.A.2250.EUR.N), INE HPT |
| Empleo | Afiliados a la Seguridad Social (mensual, provincial); tasa de paro EPA | MISSM / INE |
| Renta de los hogares | Renta disponible bruta de los hogares per cápita | INE CRE (anual, provincial) |
| Oferta de crédito | Encuesta de Préstamos Bancarios: criterios de aprobación y demanda en préstamos para vivienda (España) | BdE (trimestral, nacional) |
| Expectativas | Confianza del consumidor; intención de compra de vivienda | Comisión Europea (encuesta de consumidores), CIS |
| Demografía | Formación neta de hogares; migración neta | INE ECH / ECP, proyecciones de hogares |
| Demanda extranjera | Porcentaje de compraventas por extranjeros (provincial) | Consejo General del Notariado / Registradores |
| Inversores / contado | Porcentaje de compraventas con préstamo hipotecario | Notariado |
| Oferta de vivienda | Visados de obra nueva; viviendas terminadas | MITMA |
| Macroprudencial / fiscal | ITP y AJD por CCAA con su vigencia; ayudas a jóvenes (avales ICO) | BOE, CCAA (el repo ya tiene parte en `web scrapping/`) |

### 3.2 Relaciones del VECM sin sentido económico (pregunta 2)

Réplica exacta: S0 reproduce los números del notebook (β, α, FEVD 53,3/38,8/2,2 y ADF p = 0,204). La robustez está en `vecm_robustez.csv`. Especificaciones probadas:
- **S0:** réplica del notebook.
- **S1:** sin 2025 imputado.
- **S2:** target de total fincas del INE con parseo correcto.
- **S3:** hipotecas sobre **vivienda**.
- **S4:** S3 con dummies estacionales.
- **S5:** S3 con precio y PIB ponderados por población.
- **S6:** S3 sin Materiales.
- **S7:** S3 con muestra pre‑COVID.

Resultados por elemento del modelo:
- **β precio de +2,48** (estable entre +2,5 y +3,1 en todas las variantes).
  - Es estable porque refleja el ciclo conjunto crédito‑precio‑transacciones: en el boom suben las tres cosas y en el bust caen las tres.
  - No identifica una curva de demanda. Una curva de demanda daría una relación negativa entre precio y cantidad, condicionando a la renta y al tipo.
  - Hay simultaneidad oferta‑demanda y causalidad inversa: más crédito lleva a precios más altos. Sin un instrumento o una restricción no se puede llamar "efecto especulativo".
  - Si se quiere el canal de "mayor principal por vivienda", el target debería ser el **importe** (HPT34565), no el número.
- **β Materiales de ‑1,09.** Una elasticidad negativa de las hipotecas al coste de materiales del mismo orden que la del PIB, y en dirección contraria a la del precio, no tiene una interpretación estructural clara.
- **β Euribor de ‑0,10.** Es la relación más defendible, con una semielasticidad estable entre ‑0,09 y ‑0,12. Implica ‑36 % a largo plazo ante +4,6 pp. Por tanto el TFM sí encuentra un efecto **permanente y grande** del tipo, y su propio texto lo niega.
- **α y velocidades de ajuste.** α_H ≈ ‑0,44 en S0, pero varía entre ‑0,06 y ‑1,12 según la especificación.
  - El α del precio no es estadísticamente distinto de cero en S2‑S7 y en S0 tiene el signo que no corrige el desequilibrio.
  - Afirmar que el VECM "cuantifica la velocidad de recuperación del valor de la garantía" (business_case:647) no tiene base.
- **FEVD.** En un sistema I(1), el FEVD a 20 trimestres atribuye **incertidumbre de previsión** según un orden recursivo; no mide la importancia causal de cada variable.
  - Euribor: 2,2 % (notebook) frente a 2,2‑17,6 % (rango) y 12,1 % con el Euribor primero.
  - Además, la elección de colocar Materiales antes que el Euribor no tiene justificación: el shock de energía de 2021‑22 y la respuesta del BCE son contemporáneos y están correlacionados.
- **Diagnósticos.** Los residuos no son normales (JB = 230). No hay dummies estacionales ni de crisis, aunque el target es NSA. La muestra efectiva es de 84 trimestres para 5 variables.

### 3.3 FEVD y la subida de tipos de 2022‑2023

Ver §2. Con datos del propio dataset, el 2,2 % del Euribor no es plausible: en 2023 la única variable del sistema que empuja en la dirección de la caída de las hipotecas es el Euribor. La evidencia del BdE sobre transmisión de la política monetaria al crédito a hogares en 2022‑2023 también apunta en esa dirección (caída de nuevas operaciones y endurecimiento de criterios en la EPB), pero no he extraído aquí sus cifras concretas.

### 3.4 Proyecciones 2026‑2030 (pregunta 3)

Contraste con las proyecciones públicas disponibles a 21‑11‑2026:

| Variable | TFM (csv) | Referencia pública (fuente, fecha) | Juicio |
|---|---|---|---|
| Euribor 12m 2025 | 2,50 ("observado") | **2,223** media anual (BCE Data API, FM EURIBOR1YD_; dataset 2,223) | Erróneo |
| Euribor 12m 2026 | 2,00 | Media enero‑octubre de 2026: **2,767**; octubre: **3,239 %** (nota de prensa BdE, 3‑11‑2026) | Desfasado |
| Tipos 2027‑28 | 2,10 / 2,30 | Euribor 3m: 3,0 / 3,0 (BCE, staff Sept‑2026, cut‑off 19‑8‑2026); 3,6 en 2027 (BdE, oct‑2026). El BCE subió la facilidad de depósito al 2,50 % el 10‑9‑2026 (según BdE). El 12m queda por encima del 3m. | Muy por debajo |
| IPC 2025 | 2,80 | IAPC 2025: 2,7 (BdE, oct‑2026) | Aceptable, pero mal fechado como "observado" |
| IPC 2026‑28 | 1,88 / 2,10 / 2,00 | IAPC 3,9 / 3,3 / 2,3 (CE otoño 2026, 17‑11‑2026); 3,9 / 3,7 (BdE, 2026‑27) | Muy por debajo |
| Paro nacional (pond.) 2026‑28 | 10,48 / 10,42 / 10,38 (plano hasta 2030) | CE: 9,9 / 9,6 / 9,4; BdE: 10,0 (2026), 9,7 (2027); EPA 2026T3: 10,18 % (INE, 27‑10‑2026) | Sesgo al alza y sin la tendencia descendente |
| Suelo NAIRU | 8,5 % por provincia | NAWRU España (AMECO, consultada el 21‑11‑2026; añada no indicada): 12,1 (2025), 11,7 (2026), 11,4 (2027) | Concepto mal aplicado (ver abajo) |
| PIB real | (no proyectado; PIB_pc nominal +2,2 %/año) | CE: 2,6 / 2,1 / 1,9 (2026‑28); BdE: 2,6 / 2,2 (2026‑27); FMI WEO oct‑2026: 2,5 (2026, **solo prensa, no verificado**) | PIB_pc nominal demasiado bajo |
| Precio m² (pond.) | +6,5 / +8,3 / +6,0 / +4,5 / +3,4 %; Málaga +8,8 %/año, Zamora +0,4 %/año | IPV INE 2026T2: +12,2 % interanual. No hay proyección oficial de precios a 2030. | Corto plazo posiblemente bajo; largo plazo extrapolación sin anclaje |
| Compraventas | 2026: 757.010 (+6 %) | INE enero‑septiembre de 2026: ‑3,6 % interanual (2025: 711.543) | Sobreestimado ~10 % en 2026 |

Notas:
- **Suelo de paro.** La NAIRU/NAWRU es un concepto **nacional** de equilibrio de salarios; no es un suelo de la tasa observada, que puede situarse por debajo durante una expansión. Aplicarla como `clip` provincial confunde estructura con nivel. En 2026T3 Baleares tiene un paro del 4,63 % (INE EPA, según el resumen de la nota; no la he abierto), y Gipuzkoa, Álava, Navarra, Lleida o Madrid llevan años por debajo del 8,5 %. Efecto en la proyección:
  - 24 provincias tocan el suelo algún trimestre y 16 están en el suelo todo 2026‑2030.
  - El salto máximo de 2025T4 a 2026T1 es de **+4,78 pp**.
  - Para el asesor (DTI, riesgo), estas provincias aparecen artificialmente más arriesgadas.
- **PIB per cápita nominal.** La derivación es aproximada: crecimiento real (CE) + inflación (IAPC CE como proxy del deflactor, supuesto no verificado) ‑ crecimiento de la población (+1,0 % en 2025 según el dataset). Sale del orden del 4‑5 % nominal per cápita en 2026‑27, frente al 2,2 % del TFM. En 2024 el dato observado fue +7,1 %.
- **No he podido verificar** las cifras del README "OCDE NAIRU 9–10 % en 2030" ni "mínimo histórico 7,95 % en 2007T2". Tampoco he encontrado una proyección pública de paro por provincia.

### 3.5 Frases que hay que corregir (pregunta 4)

| Archivo:línea | Frase (resumen) | Problema | Propuesta |
|---|---|---|---|
| `Web/templates/vecm.html:576-577` | "ECT … Estacionario → cointegración genuina ✓" | Falso: ADF p = 0,204 | "El ADF del ECT no rechaza raíz unitaria (p = 0,20): la cointegración es débil" |
| `vecm.html:536` | "El Euribor explica solo el 2,2 %… resultado contraintuitivo pero robusto… dominado por la escasez de vivienda, no por el coste del dinero" | No robusto (rango 2‑18 %; 42 % sin Materiales); causalidad indebida | Eliminar. Informar del rango por orden de Cholesky y de la semielasticidad β |
| `vecm.html:314-316`, `591` | Materiales → "canal oferta→precios→demanda"; "su shock estructura correctamente el sistema, evitando la endogeneidad del Euribor" | Sin soporte; el orden de Cholesky no resuelve la endogeneidad | Presentar Materiales como control de costes e inflación, o quitarlo |
| `vecm.html:298`, `427` | "Efecto especulativo domina: mayores precios → más hipotecas" | Co‑movimiento cíclico, no demanda | "Co‑movimiento de largo plazo precio‑hipotecas (ciclo de crédito); no es causal" |
| `vecm.html:437` | "+1 % en costes → ‑1,09 % hipotecas (restricción de oferta)" | Interpretación causal de un proxy de inflación | Quitar la lectura causal |
| `vecm.html:470`, `592` | "Semivida 30 años… rigidez estructural… oferta rígida" | α del precio con signo que no corrige; fórmula de semivida inadecuada | Eliminar |
| `vecm.html:480` | "Causalidad PIB → hipotecas" | Un α no significativo indica exogeneidad débil, no causalidad | "PIB débilmente exógeno respecto a esta relación" |
| `vecm.html:388`, `376-377`, `622-628` | "r = 1 — exactamente una relación"; tabla de traza 89,14 / 76,97 | Valores distintos a los del notebook (92,89 / 69,82); r = 2 sin 2025 imputado | Sincronizar con el notebook y añadir la sensibilidad |
| `vecm.html:554` | "el shock de Euribor desplaza permanentemente… α = ‑0,44" | Contradice la tarjeta "efecto transitorio" (`vecm.html:526`) | Unificar: el β implica un efecto permanente |
| `Web/templates/business_case.html:524` | "…la oferta constructiva como palanca estructural prioritaria frente a la política monetaria" | Conclusión causal y de política sin soporte | Eliminar |
| `business_case.html:647` | "El VECM cuantifica la velocidad a la que el mercado se corrige (44 %)… horizontes de recuperación del valor de la garantía" | α_H es la velocidad del número de hipotecas, no del valor de la garantía | Eliminar |
| `business_case.html:724` | "El VECM confirma… equilibrio robusto… proyecciones fiables a 4–8 trimestres" | No robusto; el VECM no se ha usado para proyectar ni se ha validado fuera de muestra | Eliminar |
| `business_case.html:723` | "MAPE 7,11 %… comparable a los modelos internos de los principales bancos europeos" | Afirmación sin fuente | Eliminar |
| `business_case.html:505`; `econometria.html:168` | "Análisis causal" / "explica causalmente" (VAR/VECM) | Un VAR recursivo identifica relaciones bajo supuestos, no causalidad | "Análisis de relaciones dinámicas bajo identificación recursiva" |
| `business_case.html:646` | Las proyecciones de paro provincial "permiten evaluar el riesgo de cada operación" | Están distorsionadas por el suelo de 8,5 % | Quitar el suelo o advertir |
| `business_case.html:653` | Precio m² "Seasonal Naive + tendencia" para revisar límites de tasación y LTV | El código usa Holt‑Winters amortiguado; una extrapolación no es base para políticas de LTV | Corregir el método y quitar el uso prudencial |
| `business_case.html:403` | "más de 400.000 operaciones anuales" | Ambiguo: 498.429 hipotecas sobre vivienda y 640.168 sobre total fincas en 2025 (INE) | Precisar la fuente y el universo |
| `econometria.html:283-287` | "6,04… elasticidades porcentuales puras" | Multiplicador de impacto (crecimiento frente a nivel) | Reescribir |
| `README.md:106` | "relaciones causales estructurales" | Igual | "relaciones de largo plazo" |
| `README.md:114` | FEVD 53,3 / 38,8 / 2,2 presentado como resultado | No robusto | Añadir la sensibilidad |
| `README.md:140`, `295` | "Staff Projections del BCE y del FMI… Euribor 2,00–2,30 %" | El BCE no publica el Euribor 12m; valores desfasados | Citar la fuente real con fecha y actualizar |
| `README.md:146-150` | SARIMA por "ciclo estacional Q4 por consumo navideño" del PIB_pc | La serie es anual replicada; no hay estacionalidad | Modelar en frecuencia anual |
| `README.md:172` | "el cap del 4 % no resulta activo en la mayoría de provincias" | El tope (= CAGR histórico) está activo en 52/52 | Corregir |
| `README.md:201` | Suelo NAIRU 8,5 % y cifras de OCDE y mínimo histórico | No verificable; concepto mal aplicado | Ver §3.4 |
| `README.md:65` | "Las series anuales se expanden por interpolación" | Se replican | Corregir (ya señalado por el coordinador) |
| `README.md:76` | Índice de accesibilidad `PIB_pc·(1‑paro)/Precio_m2` | Usa PIB y no renta de los hogares; no incorpora tipos | Sustituir por los indicadores de §4(c) |
| Notebook 4.2, celdas 8, 14 y 20 | Textos impresos ("rigidez", "2 % transitorio", "determinada por la oferta") | Igual que la web | Regenerar tras corregir |

---

## 4. Propuestas (pregunta 5)

### (a) Especificación económicamente defendible

**Target.** Hipotecas constituidas sobre **viviendas** (INE HPT, número e **importe**), desestacionalizadas o con dummies estacionales, y por separado las **compraventas** (ETDP). La demanda hipotecaria se puede descomponer como compraventas × proporción financiada × importe medio. Hay que corregir el parseo (`parse_ine_export` del script) o, mejor, descargar el JSON del INE.

**Nacional (VECM o ARDL/ECM, trimestral, 2005‑2025):**
```
log(H_viv/hogares)_t = f[ log(renta disponible real pc), tipo real TAE nuevas op.,
                         log(precio real) , paro (o empleo afiliado),
                         EPB criterios de oferta (exógena), dummies 2008-13/COVID, estacionales ]
```
- Para el largo plazo, preferir un **ECM uniecuacional (ARDL bounds test, Pesaran‑Shin‑Smith)**: con 84 observaciones es más robusto que Johansen con 5 variables.
- Tratar el Euribor, la TAE y la EPB como exógenas (el BCE fija tipos para la eurozona).
- Contrastar la identificación con restricciones de signo, o con el Euribor primero; reportar siempre el FEVD con su rango de sensibilidad.
- Llamar a los resultados "elasticidades de forma reducida".

**Panel provincial (52 × 84):** ECM de panel con efectos fijos provinciales y efectos de tiempo (o bien variables nacionales sin efectos de tiempo). Se puede estimar con Pooled Mean Group (Pesaran‑Shin‑Smith) para tener el largo plazo homogéneo y el ajuste heterogéneo.
```
Δlog H_it = φ_i (log H_i,t-1 − θ1 log Y_it − θ2 log P_it − θ3 r_t − θ4 U_it) + Σ γ ΔX + μ_i + ε_it
```
- **Regresores provinciales:** renta (INE CRE, interpolada **declarada** o en frecuencia anual), precio, paro y afiliación, población y hogares, porcentaje de compradores extranjeros, visados.
- **Regresores nacionales:** TAE de nuevas operaciones, EPB, confianza.
- **Variables a excluir:** `Indice_Materiales` como determinante (como mucho, de la oferta o del precio en una ecuación separada), `tasa_ahorro` NSA y `Edad_Media` en escalones.

### (b) Escenarios 2026‑2030

| Variable | Base (anclado a fuentes) | Adverso (sensibilidad ilustrativa) | Favorable (sensibilidad ilustrativa) |
|---|---|---|---|
| Euribor 12m | 2026: media observada a la fecha (≈2,8 %; octubre 3,24 %). 2027‑28: Euribor 3m del BCE (3,0 %) o del BdE (3,6 % en 2027) más el diferencial 12m‑3m observado (octubre de 2026: 0,60 pp, nota BdE). 2029‑30: mantener o converger a la curva de mercado vigente. | Base + 100 pb durante 2027‑28 | Base ‑75 pb desde 2027 |
| IAPC/IPC | CE otoño 2026: 3,9 / 3,3 / 2,3 (2026‑28); 2,0 en 2029‑30 (objetivo del BCE, supuesto) | +1 pp en 2027‑28 | ‑0,5 pp |
| PIB real | CE: 2,6 / 2,1 / 1,9; 2029‑30 ≈ 1,7 (supuesto de convergencia al crecimiento potencial; **no verificado**) | ‑2 pp en 2027 y ‑1 pp en 2028 | +0,5 pp |
| Paro nacional | CE: 9,9 / 9,6 / 9,4 (2026‑28), con una bajada de 0,2‑0,3 pp al año después. Provincial: paro_i = nacional + diferencial medio 2023‑25 de la provincia (**sin suelo**). | +2,5 pp acumulado hasta 2028 | ‑1 pp acumulado |
| Precio vivienda | Anclado al IPV del INE observado en 2026; desde 2027, crecimiento = renta nominal ± 1 pp (accesibilidad constante) | ‑10 % nominal acumulado en 2027‑28 | Renta + 2 pp |

Los escenarios adverso y favorable son **sensibilidades propuestas por esta auditoría, no proyecciones publicadas**. Para un uso bancario conviene anclarlos al escenario adverso del stress test de la EBA/ESRB vigente para España; no he verificado esas cifras. Cada escenario debe guardarse en `data/forecasts/` con su fuente, fecha de corte y fecha de consulta.

### (c) Indicadores de negocio calculables hoy

Calculados en `indicadores_negocio_provinciales.csv` (`fig_05_accesibilidad_provincial.png`):
- **Años de PIB pc para 90 m²** = 90 · Precio_m2 (2025T4) / PIB_pc (2024). Mediana 4,23.
  - Menos accesibles: Málaga 9,69, Baleares 9,09, Melilla 8,01, Ceuta 7,78, Madrid 7,65.
  - Más accesibles: Cuenca 2,49, Ciudad Real 2,63, Teruel 2,65.
- **Entrada del 20 % en años de PIB pc.**
- **Esfuerzo financiero** = cuota anual (LTV 80 %, 25 años, TAE de 2025T4 = 2,673 %) / PIB pc. Málaga 42,5 %; con +2 pp de tipo, 52,6 %. Esto da la **sensibilidad del esfuerzo al tipo**.
- **Hipotecas por 1.000 habitantes**, **hipotecas / compraventas**, **variación del precio 2025** y **paro 2025T4**.

Advertencias: el PIB pc no es renta del hogar (Madrid y Álava aparecen sobrevaloradas por el efecto sede, y el PIB está desfasado un año). Para producción hay que sustituirlo por la **renta neta media por hogar (INE ADRH)** o la RDBH per cápita (INE CRE), y usar los gastos de compra por CCAA (ITP/AJD, ya extraídos en `web scrapping/`) para calcular el **ahorro previo total necesario**.

Indicadores adicionales recomendados:
- Porcentaje de compras sin hipoteca (Notariado).
- Porcentaje de compradores extranjeros.
- Tipo fijo frente a variable de la nueva producción (INE HPT 24456).
- Diferencial TAE frente a IRS a 5 años (BdE: IRS a 5 años de 3,455 % en octubre de 2026) como proxy de margen en tipo fijo.
- Mapa de "presión de precios" = crecimiento del precio menos crecimiento de la renta.

---

## 5. Decisiones que requieren arbitraje del coordinador

1. **Target v2.** Pasar a hipotecas sobre **viviendas** (número e importe) y corregir el parseo. Esto cambia todas las métricas (MAPE, VECM, RF_Nac) y la línea base v1 deja de ser comparable 1:1.
2. **VECM.** Rehacerlo (ARDL/ECM o VECM con renta, tipo real y empleo, sin Materiales) o mantenerlo como ejercicio con las advertencias. En cualquier caso hay que retirar de la web el relato de "oferta frente a política monetaria".
3. **Escenarios.** Sustituir `ESCENARIOS_BCE` por un escenario base anclado a CE (otoño 2026) y BdE (octubre 2026) con fecha de corte, eliminar el suelo del 8,5 % y dejar de sobrescribir datos observados de 2025.
4. **Renta.** Incorporar INE ADRH o CRE (renta de los hogares) al panel v2. Lo necesitan los indicadores de accesibilidad y el asesor (income ratio).

## 6. Fuentes consultadas (fecha de consulta: 21‑11‑2026)

- INE Tempus3: HPT34936 (hipotecas total fincas), HPT34618 (viviendas, número), HPT34565 (viviendas, importe), ETDP1826 (compraventas), IPV1376 (IPV, variación anual). JSON guardados en `reports/audit/03_economia/data/`.
- BCE Data API: FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA (Euribor 12m) y MIR.M.ES.B.A2C.AM.R.A.2250.EUR.N (TAE de nuevas hipotecas de vivienda en España; 2,99 % en 2026‑09). CSV en `data/`.
- Banco de España, *Proyecciones macroeconómicas e informe trimestral, tercer trimestre de 2026* (publicado el 9‑10‑2026): https://www.bde.es/wbe/es/publicaciones/analisis-economico-investigacion/proyecciones-macro-informe-trimestral/proyecciones-e-informe-trimestral-de-la-economia-espanola-tercer-trimestre-2026.html
- Banco de España, nota de prensa del 3‑11‑2026 (Euribor de octubre de 2026: 3,239 %): https://www.bde.es/f/webbe/GAP/Secciones/SalaPrensa/NotasInformativas/26/presbe2026-104.pdf
- BCE, *ECB staff macroeconomic projections for the euro area, September 2026* (cut‑off 19‑8‑2026): https://www.ecb.europa.eu/press/projections/html/ecb.projections202609_ecbstaff~8e340fc69d.en.html
- Comisión Europea, *Autumn 2026 Economic Forecast – Spain* (17‑11‑2026): https://economy-finance.ec.europa.eu/economic-surveillance-eu-member-states/country-pages/spain/economic-forecast-spain_en
- AMECO, NAWRU de España (consulta WQ API; añada no indicada en la respuesta): https://ec.europa.eu/economy_finance/ameco/wq/series?fullVariable=1.0.0.0.ZNAWRU&countries=ESP
- INE, nota EPA 3T 2026 (27‑10‑2026), paro del 10,18 %; cifra tomada del resumen de búsqueda, sin abrir la nota: https://ine.es/dyngs/Prensa/EPA3T26.htm
- FMI WEO de octubre de 2026: España 2,5 % en 2026, **solo vía prensa** (https://en.ara.cat/economy/the-imf-raises-spain-s-2026-growth-forecast-to-2-5_1_5877400.html); no verificado en la base del FMI.

## 7. Ficheros entregados

`reports/audit/03_economia.md` (este informe) y en `reports/audit/03_economia/`:
- `analisis_economico.py`: script reproducible.
- `resultados.json` y `salida_consola.txt`.
- `hipotecas_dataset_vs_INE_anual.csv`, `ciclo_fases.csv`, `vecm_robustez.csv`, `proyecciones_agregado_nacional.csv`, `paro_suelo_nairu_por_provincia.csv`, `indicadores_negocio_provinciales.csv`.
- `fig_01_ciclo_2005_2025.png`, `fig_02_hipotecas_vs_euribor_interanual.png`, `fig_03_fevd_sensibilidad_orden.png`, `fig_04_paro_suelo_nairu.png`, `fig_05_accesibilidad_provincial.png`.
- `data/`: snapshots del INE y del BCE.
