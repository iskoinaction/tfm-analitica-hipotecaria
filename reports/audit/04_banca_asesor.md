# Auditoría 04 — Banca: asesor hipotecario (Fase VI)

**Especialista:** banca (riesgo hipotecario, pricing, concesión, regulación bancaria ES/UE)
**Fecha:** 21/11/2026 · **Rama:** `claude/stoic-edison-gdie8p`
**Ámbito:** `notebooks acabados/5. HIPOTECA_PERSONALIZADA_provincial.ipynb`, `notebooks acabados/6. pasos_web.ipynb`,
`Web/app.py` (rutas `/api/hipoteca-context`, `/api/hipoteca-recomendacion`, `/test-hipoteca`, `/api/noa-chat`,
`/api/noa-strategic` y funciones auxiliares), `Web/static/tipos_hipotecas.csv`, `web scrapping/datos_fiscales_scraped/`,
`Web/templates/hipotecas*.html`, `Web/templates/test_hipoteca.html`.

> Todas las cifras de este informe proceden de scripts ejecutados (carpeta `reports/audit/04_banca/`) o de fuentes
> citadas con URL. Donde una cifra viene de una fuente secundaria se indica expresamente y se marca como *pendiente de
> verificación en boletín oficial*.

---

## 0. Resumen ejecutivo

1. **La aritmética básica es correcta, pero el producto no es lo que dice ser.** La cuota francesa coincide con un
   cálculo independiente (error máximo 0,005 €, por redondeo del tipo). Sin embargo:
2. **CRÍTICO — el tipo que ve el usuario no es el tipo con el que se calculan la cuota, el DTI y la decisión.** La
   interfaz solo muestra el "Tipo Óptimo ML" (`applied_rate`), pero cuota, DTI y estado se calculan con el tipo
   "básico". En 13 de 14 perfiles de prueba el tipo mostrado es mayor (mediana +0,72 pp, máx. +0,94 pp; hasta
   +122 €/mes). Dos perfiles salen **"Hipoteca Aprobada"** (DTI 34,8 % y 32,4 %) cuando con el tipo mostrado su DTI
   sería 38,3 % y 35,6 % (zona "analista").
3. **CRÍTICO — el "modelo de pricing" GBR no aporta información y empeora una regla ingenua.** Se entrena con
   4.160 filas que son en realidad **80 trimestres** (target nacional replicado 52 veces); el RMSE_CV = 0,104 que
   muestra la web procede de un `TimeSeriesSplit` sobre filas ordenadas por provincia (fuga). Con validación de origen
   móvil por trimestre (2013Q1–2024Q4) el RMSE es **0,380 pp frente a 0,200 pp de la persistencia** ("usar el último
   APRC − Euríbor publicado"). Para 2025 (fuera de muestra) predice un diferencial base de 1,20 pp en Madrid frente a
   0,557 pp observado. Además la app aplica "el mayor de los dos tipos", así que el sesgo al alza llega al cliente.
4. **CRÍTICO — SHAP no explica el tipo ofrecido y no "cumple el AI Act".** En hipoteca fija el GBR ni siquiera se usa
   (tipo = APRC + ajuste + 0,50) y aun así se muestran contribuciones SHAP; en variable el único factor individual
   (ingresos) entra por un ajuste `tanh` ajeno a SHAP; y las contribuciones de variables provinciales a un target
   nacional son espurias. La afirmación "SHAP cumple los requisitos de explicabilidad del AI Act" no es sostenible.
5. **Marco regulatorio verificado (DOUE):** el Reglamento (UE) **2026/1744** ("Ómnibus digital sobre IA", DO L de
   24/07/2026, en vigor 27/07/2026) aplaza las obligaciones de alto riesgo del anexo III (incluido el punto 5.b,
   solvencia/calificación crediticia) al **2 de diciembre de 2027** (anexo I: 2/08/2028). El art. 50 (transparencia de
   chatbots) aplica desde el 2/08/2026. Un TFM no desplegado está fuera del ámbito (art. 2.8), pero **no puede afirmar
   cumplimiento**.
6. **Clasificación del sistema actual:** *simulador hipotecario con reglas heurísticas de pre-evaluación* presentado
   como "modelo de pricing" y "motor de admisión". No es ninguno de los dos (§3.4).
7. **Fiscalidad y financiación:** 12 de 52 provincias (23 %) no se mapean a su CCAA (tildes) y reciben ITP por defecto
   y ningún programa joven; ITP de tipo único sin tramos (7 CCAA con escala ignorada) y 4 CCAA con tipo base distinto a
   la fuente consultada; la vivienda nueva (IVA + AJD) nunca se calcula; los "aranceles" son una tabla de una
   calculadora de terceros, no el arancel; la tabla de "financiación joven por CCAA" (90–100 %) no tiene fuente y se
   aplica automáticamente por edad. **Punto positivo:** el simulador **no** imputa al cliente los gastos del préstamo
   que la Ley 5/2019 atribuye al banco; sí omite la tasación (que paga el cliente).
8. **Chatbots Gemini:** envían datos económicos personales a un tercero, aceptan el "contexto" que manda el navegador
   (inyección de prompt), insertan la respuesta del LLM con `innerHTML` (XSS), se presentan como "asesora hipotecaria
   de CaixaBank" y el chatbot "Strategic" (accesible a cualquier usuario) tiene instrucciones de "maximizar el beneficio
   del banco" y "persuadir al cliente". Reciben un "tipo ofrecido" distinto del mostrado (y 0,00 % si la operación va a
   analista).

**Recomendación:** rediseñar el asesor como (a) *estimador de tipo de mercado* basado en series publicadas del BCE/BdE
con fecha y rango, (b) *simulador de capacidad de pago* con estrés de tipos y (c) *calculadora de gastos* con tabla
fiscal con vigencias; eliminar la decisión "aprobada/denegada", el ajuste `tanh`, el recargo por precio < 100.000 €, la
regla "el banco se queda el mayor" y el GBR del flujo del cliente (§5).

---

## 1. Método y evidencias reproducibles

| Script (en `reports/audit/04_banca/`) | Qué hace | Salida (`out/`) |
|---|---|---|
| `_app_loader.py` | Importa `Web/app.py` sin `GEMINI_API_KEY` ni SDK de Google (stubs), sin escribir ficheros (`sys.dont_write_bytecode`). Parche opcional para el fallo SHAP (M1). | — |
| `01_ecb_rates_check.py` | Descarga del BCE: APRC, TEDR (AAR) total y AAR flotante/fijación ≤1 año (MIR, España) y Euríbor 12M (FM). Compara con `tipos_hipotecas.csv`. | `ecb_rates_*.csv`, `tipos_csv_vs_ecb.csv`, `ecb_rates_summary.json` |
| `02_harness_asesor.py` | 14 perfiles contra `/api/hipoteca-recomendacion` (test client Flask). Cuota independiente por bisección sobre el cuadro de amortización. Mapeo provincia→CCAA. `/api/hipoteca-context`. `/test-hipoteca`. | `harness_profiles.csv`, `harness_summary.json` |
| `03_gbr_pricing_audit.py` | Observaciones efectivas, CV de la app y del notebook, validación de origen móvil, baselines, dispersión provincial. | `gbr_audit.json`, `gbr_backtest_origen_movil.csv` |
| `04_fiscal_y_ajuste_perfil.py` | Ajuste `tanh` (tabla, discontinuidad), aranceles app vs RD 1426/1427/1989, ITP app vs fuente secundaria con cita normativa. | `fiscal_ajuste.json` |
| `05_ecb_fixation_share.py` | Sondeo: el BCE no publica para España el volumen MIR por periodo de fijación (solo totales). | `ecb_fixation_probe.json` |
| `asesor_v2_reference.py` + `test_asesor_v2_reference.py` | Implementación de referencia de las fórmulas v2 y 24 tests con valores esperados (todos pasan). | — |
| `out/omnibus_ia_art113_extracto.txt` | Extracto literal del DOUE L 2026/1744 (art. 113 modificado). | — |

Reproducción: `cd reports/audit/04_banca && python3 01_ecb_rates_check.py && python3 02_harness_asesor.py && python3 03_gbr_pricing_audit.py && python3 04_fiscal_y_ajuste_perfil.py && python3 -m pytest -q -p no:cacheprovider test_asesor_v2_reference.py`.

Entorno: Python 3.13, scikit-learn 1.9.1, shap 0.54.1. Coincide con el trabajo de 02_ds (`reports/audit/02_ds/04_spread_gbr_validation.py`), que llega a la misma conclusión sobre la fuga del CV.

---

## 2. Hallazgos por gravedad

| ID | Grav. | Hallazgo | Evidencia |
|---|---|---|---|
| C1 | CRÍTICA | Tipo mostrado (`applied_rate`, ML) ≠ tipo usado para cuota, DTI y decisión (`rate` básico). La UI solo pinta la tarjeta ML. Noa recibe `rate` básico como "tipo ofrecido" (y `0.0` si `status` ≠ approved). | `app.py` 1484-1492 (cuota con `rate`), 1577-1584 (`applied_rate`), 1656 (`"rate": rate if approved else 0.0`); `hipotecas.html` 1180-1215, 1298; harness P13/P12 (§3.1) |
| C2 | CRÍTICA | SHAP no explica el tipo: fijo ignora el GBR; ingreso fuera de SHAP; atribuciones espurias provincia→target nacional. Afirmación "cumple AI Act" infundada (README l.128, Web/README l.342, UI "SHAP: AI Act", prompts de Noa). | `app.py` 1312-1316; `gbr_audit.json` (dispersión 2024Q4) |
| C3 | CRÍTICA | GBR: 80 observaciones efectivas; CV con fuga; peor que persistencia (0,380 vs 0,200 pp); sesgo al alza 2025; "max(ML, básico)"; R² de entrenamiento etiquetado "CV Accuracy"; métricas fijas R² 0,8492 / RMSE 0,1543 / MAPE 3,2 % sin origen en ningún notebook. | `gbr_audit.json`; `harness_summary.json`; `app.py` 1171-1176; `hipotecas.html` 1192 |
| C4 | CRÍTICA | Emisión automática de "Hipoteca Aprobada/Denegada" a consumidores con marca de una entidad real, chatbot "asesora de CaixaBank" y chatbot interno orientado a persuadir. Si fuera real: anexo III 5.b AI Act + art. 22 RGPD + LCCI art. 11 y 19. | `app.py` 1589-1630, 1719, 1803-1804 |
| A1 | ALTA | Ajuste `tanh` por "ingreso anual / PIB pc provincial": sin datos de pricing individual que lo respalden, magnitudes no comparables, discontinuidad +0,05 pp en ratio 0,5, y diferencia territorial (mismo ingreso: +0,14 pp en Madrid, −0,19 pp con PIB pc 20.000 €). Recargo +0,75 pp por precio < 100.000 € sin base. | `fiscal_ajuste.json`; `app.py` 1261-1277, 1475 |
| A2 | ALTA | "Diferencial real = APRC − Euríbor" no es el margen bancario (APRC es TAE con costes y mezcla fijo/variable). 2023: 0,027 pp vs 0,396 pp con el tipo variable (AAR flotante); negativo en 2023Q3 y 2024Q2. Fijo = APRC + 0,50 etiquetado como "TIN". | `ecb_rates_summary.json` |
| A3 | ALTA | 12/52 provincias (A Coruña, Almería, Castellón, Cáceres, Cádiz, Córdoba, Guipúzcoa, Jaén, León, Málaga, Álava, Ávila) sin CCAA → ITP 8 % por defecto, sin programa joven. | `harness_summary.json` |
| A4 | ALTA | Financiación 90–100 % "por CCAA" sin fuente, automática por edad, sin requisitos (renta, precio, primera vivienda, entidad adherida, aval). LTV sobre precio, no sobre tasación. P09: LTV 100 % "Aprobada" con 12.000 € de ahorro. | `app.py` 133-142, 1444-1462 |
| A5 | ALTA | Fiscalidad: ITP de tipo único (escala ignorada en 7 CCAA), 4 CCAA con tipo base distinto a la fuente consultada, condiciones del tipo joven ignoradas, sin vigencias; vivienda nueva nunca calculada (`is_new_build=False` fijo); IGIC (Canarias), bonificación Ceuta/Melilla y regímenes forales no modelizados; tasación omitida. | `fiscal_ajuste.json`; `app.py` 1452 |
| A6 | ALTA | Chatbots: datos personales a tercero, contexto controlado por el cliente (inyección), `innerHTML` de la salida del LLM (XSS), asesoramiento implícito, Noa Strategic accesible a cualquier usuario autenticado. | `app.py` 1707-1870; `hipotecas.html` 1449, 1470 |
| A7 | ALTA | "Proyección" 2026: Euríbor fijado en 2,00 %; el Euríbor 12M real ene–oct 2026 promedia 2,767 % (oct: 3,239 %); APRC ene–sep 2026: 2,902 % vs 2,719 % de la app. | `ecb_rates_monthly.csv`; harness P08 |
| M1 | MEDIA | `/api/hipoteca-recomendacion` devuelve HTTP 500 con shap 0.54 (`expected_value` es array). `Web/requirements.txt` solo lista Flask, pandas, werkzeug, google-generativeai, python-dotenv. | traza en §3.6 |
| M2 | MEDIA | Capital = % máximo de financiación siempre, aunque el cliente aporte más (P12: 200.000 € de ahorro y aun así LTV 95 %) → DTI sobreestimado. | harness P12 |
| M3 | MEDIA | Umbrales DTI 35/45 presentados como norma ("límite estricto normativo", nb 5 celda 40); sin estrés de tipos, sin LTI, sin gastos de vida, sin unidad familiar, 12/14 pagas ambiguo. | nb 5 celdas 12-13, 40 |
| M4 | MEDIA | Edad: denegación automática > 65 y "límite legal" de 75 años al vencimiento en la UI: no existe tal límite legal. | `app.py` 1464-1467, 1597; `hipotecas.html` 1004 |
| M5 | MEDIA | `/test-hipoteca` (legacy): cuota = interés sobre todo el principal + amortización lineal → sobreestima 25,9 % (160.000 €, 3,2 %, 30 a: 871,11 vs 691,95 €); exige 30 % de ahorro pero financia 80 %. | `harness_summary.json` |
| M6 | MEDIA | Notebook 5 se contradice: §7b elige Regresión Lineal "por interpretabilidad"; §11 usa GBR; CV-5 llamado "aleatorio" (es KFold por bloques de provincia, RF R² 0,9974); su propio hold-out temporal (celda 45) da R² 0,2292 / RMSE 0,79 pp. Ruta absoluta `/Users/fran/...`. Notebook 6 documenta reglas ya eliminadas ("Euríbor −8 % anual"). | salidas guardadas del notebook |
| M7 | MEDIA | Notaría/registro: tabla de `financialtools.web.app`, plana desde 400.000 €; no es el arancel. Arancel base (RD 1426/1427/1989, con rebaja 5 %) para 200.000 €: notaría 340,51 €, registro 176,90 € vs 750/510 € en la app (la cifra de la app puede incluir folios, copias e IVA, pero no está documentado). | `fiscal_ajuste.json` |
| B1 | BAJA | Euríbor = media anual; una hipoteca variable se revisa con el índice de un mes concreto. | `app.py` 221-237 |
| B2 | BAJA | Euríbor del CSV difiere del BCE (máx. 0,028 pp; probablemente media de datos diarios); APRC idéntico al BCE. | `ecb_rates_summary.json` |
| B3 | BAJA | Suelo arbitrario del diferencial (0,10 pp) y del tipo (0,5 %). | `app.py` 1410, 1486 |

---

## 3. Detalle técnico

### 3.1 Cuota, entrada y coherencia del tipo (misión 1)

**Fórmula.** `C = L·r(1+r)^n/((1+r)^n−1)`, `r = TIN/12`. Verificada contra una cuota obtenida por bisección sobre el
cuadro de amortización (saldo final = 0) en 14 perfiles: **error máximo 0,0052 €** (diferencias por redondeo del tipo a
2 decimales). Correcta.

**Incoherencia del tipo (C1).** Resultado del harness (`out/harness_profiles.csv`):

| Perfil | Estado devuelto | Tipo de la cuota | Tipo mostrado | Δ cuota €/mes | DTI app | DTI con tipo mostrado |
|---|---|---|---|---|---|---|
| P01 Madrid variable 250k, 2.500 €/mes | analista | 2,78 | 3,57 | +102,50 | 38,9 | 43,0 |
| P08 Madrid 2026 | analista | 2,72 | 3,57 | +110,29 | 38,6 | 43,0 |
| **P13 Madrid, 2.800 €/mes** | **aprobada** | 2,78 | 3,54 | +98,60 | **34,8** | **38,3 (analista)** |
| **P12 Madrid, 3.000 €/mes, 200k ahorro** | **aprobada** | 2,78 | 3,52 | +95,66 | **32,4** | **35,6 (analista)** |
| P05 Barcelona 8.000 €/mes | aprobada | 3,47 | 3,50 | +4,84 | 28,7 | 28,8 |
| P06 Sevilla 60 años, fijo | analista | 3,28 | 3,28 | 0 | 37,6 | 37,6 |

`applied_type = 'ml'` en 13/14 perfiles; Δ tipo mediana 0,72 pp, máximo 0,94 pp. La regla "el banco se queda con el
mayor de los dos" (`app.py` 1577-1584) es además una regla de *pricing* abusiva para un simulador dirigido al cliente.

**Entrada y capital.** `loan_amount = precio × %financiación_máxima` siempre (no `precio + gastos − aportación`).
`min_down_payment = precio × (1 − %máx)` y `effective_savings = ahorro − impuestos`. Consecuencias: el capital no baja
si el cliente aporta más (M2) y con 100 % de financiación la entrada exigida es 0 (P09).

**Edad y plazo.** `plazo = max(5, min(30, solicitado, 75 − edad))` y denegación si edad > 65. La práctica de mercado
sitúa la edad máxima al vencimiento en torno a 70–75 años, pero **no hay límite legal**; la UI dice "límite legal" (M4).
Debe ser un parámetro de política, con aviso.

### 3.2 Gastos e impuestos (misión 1)

**Lo que hace bien.** No imputa al comprador ningún gasto del préstamo. Según la **Ley 5/2019 (LCCI), art. 14.1.e)**:
tasación → prestatario; gestoría → prestamista; aranceles notariales de la escritura de préstamo → prestamista
(copias, quien las pida); inscripción de la hipoteca en el Registro → prestamista; AJD según la norma tributaria, que
desde el **RDL 17/2018** (art. 29 TRLITPAJD) designa sujeto pasivo al prestamista en las escrituras de préstamo
hipotecario. El simulador no incluye ninguno de esos conceptos → correcto, pero **no lo explica** al usuario.

**Lo que falla.**
- **Tasación omitida** (gasto del prestatario por la LCCI).
- **Vivienda nueva nunca calculada**: la ruta llama siempre a `_calc_taxes(..., is_new_build=False)`; el código
  IVA 10 % + AJD es código muerto. Además no contempla IVA superreducido de VPO, **IGIC en Canarias**, IPSI/bonificación
  en Ceuta y Melilla ni los regímenes forales.
- **ITP**: tipo único por CCAA. Comparación con una fuente **secundaria** que cita la norma de cada CCAA
  ([bm.consulting, 29/10/2026](https://bm.consulting/es/insights/tipos-itp-comunidad-autonoma-2026/)) — *pendiente de
  verificación en boletín oficial*:

| CCAA | App | Fuente secundaria (norma citada) | Situación |
|---|---|---|---|
| Cantabria | 10 % | 9 % (DLeg 62/2008 art. 9) | tipo base distinto |
| C. Valenciana | 10 % | 9 % desde 1/6/2026; 11 % si > 1 M€ (Ley 13/1997 art. 13) | tipo base distinto + vigencia |
| Galicia | 10 % | 8 % (DLeg 1/2011 art. 14) | tipo base distinto |
| Murcia | 8 % | 7,75 % (DLeg 1/2010 art. 6) | tipo base distinto |
| Aragón, Asturias, Baleares, Castilla y León, Cataluña, Extremadura | tipo único | escalas por tramos | tramos ignorados |
| Andalucía, Canarias, C-La Mancha, Madrid, Navarra, La Rioja, País Vasco | = | = | coincide (tipo base) |

  Los tipos reducidos "joven" (`ITP_JOVEN`) se aplican solo por edad ≤ 35, sin los requisitos habituales (vivienda
  habitual, límite de valor o renta). Las propias fuentes secundarias discrepan en varios tipos reducidos; **no** se
  proponen valores nuevos sin verificar en el boletín autonómico.
- **Notaría y registro (M7).** El "arancel real" es el del **RD 1426/1989** (notarios) y **RD 1427/1989**
  (registradores), Anexo I, Número 2, con rebaja general del 5 % ([BOE consolidado RD 1426/1989](https://www.boe.es/eli/es/rd/1989/11/17/1426/con),
  [BOE consolidado RD 1427/1989](https://www.boe.es/eli/es/rd/1989/11/17/1427/con)). Arancel base calculado:

| Precio | App notaría | Arancel base notaría | App registro | Arancel base registro |
|---|---|---|---|---|
| 100.000 € | 675 | 269,14 | 445 | 126,92 |
| 200.000 € | 750 | 340,51 | 510 | 176,90 |
| 400.000 € | 850 | 435,51 | 630 | 233,90 |
| 1.000.000 € | 850 | 644,71 | 630 | 367,00 |

  La factura real añade folios de matriz (Nº 7), copias (Nº 4), suplidos e IVA 21 %, por lo que el arancel base es una
  **cota inferior**. La tabla de la app procede de una calculadora de terceros (`financialtools.web.app`, notebook 6
  §2), es plana desde 400.000 € y no documenta qué incluye. Recomendación: arancel base + estimación explícita de
  folios/copias + IVA, mostrado como rango.

### 3.3 Financiación máxima, LTV, DTI (misión 2)

- **LTV 80 %.** No es un límite legal para el préstamo al consumo hipotecario; es práctica de mercado ligada al
  tratamiento prudencial y a la elegibilidad como colateral de bonos garantizados. Debe calcularse sobre el
  **menor de precio y valor de tasación** (Orden ECO/805/2003), no solo sobre precio.
- **"Programas de cada CCAA" hasta 100 %.** La base real verificable es estatal: la **Línea de Avales ICO para la
  primera vivienda** de jóvenes (hasta 35 años) y familias con menores, que avala hasta el 20 % del préstamo (25 % con
  ciertos requisitos de eficiencia energética), con requisitos de renta, patrimonio y precio, solo en entidades
  adheridas; fue prorrogada mediante adenda publicada en el [BOE de 2/07/2026](https://www.boe.es/boe/dias/2026/07/02/pdfs/BOE-A-2026-14404.pdf)
  (contexto: [La Moncloa](https://www.lamoncloa.gob.es/serviciosdeprensa/notasprensa/vivienda-agenda-urbana/paginas/2024/solicitar-avales-gobierno-ico-vivienda.aspx)).
  Algunas CCAA tienen programas propios con condiciones. La tabla `YOUNG_FINANCING` (90–100 %, edades 35/40) **no cita
  fuente** y concede el porcentaje automáticamente por edad. Debe sustituirse por información de elegibilidad con
  enlace oficial, sin alterar automáticamente el capital.
- **DTI 35/45 %.** El Banco de España no fija un DTI legal. La normativa exige **evaluar la solvencia** (LCCI art. 11;
  Orden EHA/2899/2011 art. 18; Circular 5/2012, Anexo 6 sobre préstamo responsable) y las **EBA/GL/2020/06** piden
  métricas (DSTI, LTI, LTV, DTI) y análisis de sensibilidad ante escenarios adversos (subidas de tipos en variable,
  caída de ingresos). El Banco de España dispone de herramientas macroprudenciales sobre condiciones de concesión
  (LTV, LTI, DSTI) habilitadas normativamente; en este informe no se ha localizado su activación (verificar en bde.es).
  Por tanto 35/45 son **umbrales orientativos de práctica**, no norma; el notebook 5 (celda 40) los llama "límite
  estricto normativo" (erróneo).
- **Sin estrés de tipos** para variable/mixto: con 200.000 € a 30 años, la cuota pasa de 898,09 € (3,5 %) a
  1.264,14 € (+3 pp); con 3.000 €/mes de ingresos, el DSTI pasa de 29,9 % a 42,1 % (test v2).

### 3.4 Tipo de interés: GBR + `tanh` (misión 3)

**Datos.** `tipos_hipotecas.csv` (84 trimestres 2005Q1–2025Q4): el APRC coincide exactamente (diferencia máx.
8,9e−16) con la serie BCE `MIR.M.ES.B.A2C.A.C.A.2250.EUR.N` (APRC, nuevas operaciones de préstamo a hogares para
vivienda, España) promediada por trimestre; el Euríbor difiere hasta 0,028 pp de `FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA`.
El CSV no tiene manifiesto, fecha de descarga ni fuente; el notebook 6 lo describe como "datos de mercado reales" de
`tipos_combinados_hipotecas_trim.csv`. `Spread_Hipotecas` del dataset maestro **es exactamente** `APRC − Euríbor`
de este CSV (2005Q1: 1,1109 en ambos).

**Qué mide "APRC − Euríbor" (A2).** El APRC es una **TAE** (incluye comisiones y costes) de todas las nuevas
operaciones (fijas, mixtas y variables). Restarle el Euríbor 12M no da el margen de una hipoteca variable:

| Año | APRC | TEDR total | TEDR variable (fij. ≤1a) | Euríbor 12M | APRC−Eur | TEDR var.−Eur | APRC−TEDR |
|---|---|---|---|---|---|---|---|
| 2013 | 3,192 | 3,044 | 2,861 | 0,536 | 2,656 | 2,325 | 0,148 |
| 2021 | 1,619 | 1,486 | 1,400 | −0,491 | 2,110 | 1,891 | 0,133 |
| 2023 | 3,892 | 3,746 | 4,261 | 3,865 | **0,027** | **0,396** | 0,146 |
| 2025 | 2,780 | 2,715 | 3,005 | 2,223 | 0,557 | 0,782 | 0,065 |
| 2026 (ene–sep) | 2,902 | 2,849 | 3,033 | 2,846 | 0,187 | 0,318 | 0,053 |

Fuente: `out/ecb_rates_summary.json`. APRC − Euríbor fue negativo en 2023Q3 y 2024Q2. El BCE no publica para España el
volumen MIR por periodo de fijación (`05_ecb_fixation_probe.json`), por lo que el peso del tipo fijo en el APRC debe
tomarse de otra fuente (p. ej. INE).

**GBR (C3).** `out/gbr_audit.json`:
- 4.160 filas = **80 trimestres** (2005Q1–2024Q4; 2025 cae por `PIB_pc` NaN) × 52 provincias. Target con **80
  valores únicos**; Euríbor y tasa de ahorro, 1 valor por trimestre; IPC ~15; paro, precio m² y PIB pc, ~52.
- Filas ordenadas por provincia → `TimeSeriesSplit(5)` corta **bloques de provincias**: cada trimestre de test ya está
  en entrenamiento con su target. RMSE_CV de la app: **0,1037**; con solo Euríbor y tasa de ahorro (que solo
  identifican el trimestre) el mismo CV da 0,1115 → el CV mide memorización del trimestre, no capacidad predictiva.
  El CV-5 del notebook (KFold sin barajar) da 0,0992.
- **Origen móvil por trimestre** (entrena con < t, predice t; 48 trimestres 2013Q1–2024Q4): RMSE **GBR 0,380 pp**,
  **persistencia (t−1) 0,200 pp**, OLS spread~Euríbor 0,514 pp, media histórica 1,007 pp. Para comparación, la
  desviación típica del propio spread 2005–2025 es 0,859 pp.
- **Lo que aporta el GBR frente al último dato publicado: nada positivo.** En modo histórico el APRC del año ya es
  conocido (la tarjeta "básica" lo usa); en modo previsión, la persistencia es 1,9 veces más precisa.
- Dispersión espuria: en 2024Q4 (spread real nacional 0,619) el modelo de la app predice entre 0,546 (Álava) y 0,722
  (Melilla) según la provincia.
- 2025 fuera de muestra: Madrid, diferencial base GBR **1,20 pp** vs **0,557 pp** observado → tipo ML 3,57 % vs
  APRC 2,78 %.
- El notebook 5 justificaba el GBR por un R² CV temporal de 0,9464 (mismo problema de orden por provincia) y su
  propio hold-out temporal (celda 45) daba **R² 0,2292 / RMSE 0,79 pp**, no recogido en README ni web.

**Ajuste `tanh` (A1).** `adj = −0,25·tanh(2·(ratio−1)) + 0,05·[ratio<0,5]`, `ratio = 12·ingreso_neto_mensual /
PIB_pc_provincial`. Valores: ratio 0 → +0,291; 0,4999 → +0,240 / 0,5 → +0,190 (salto 0,05); 1 → 0; 2 → −0,241;
≥3 → −0,25. **No hay ninguna estimación**: el repositorio no contiene datos de pricing individual (solo series
agregadas del BCE), así que los parámetros (0,25; 2; 0,05) son supuestos. El PIB per cápita es producción por
habitante, no renta disponible del hogar. Efecto territorial: el mismo ingreso de 2.500 €/mes recibe +0,14 pp con PIB pc
44.749 € (Madrid) y −0,19 pp con 20.000 €.

### 3.5 Decisión crediticia: qué es y qué falta (misión 4)

| Concepto | Qué hace | Entradas mínimas | ¿El sistema actual lo es? |
|---|---|---|---|
| **Simulador hipotecario** | Calcula cuota, intereses, gastos y esfuerzo para un tipo dado | Precio, aportación, plazo, TIN, ingresos | **Sí (núcleo correcto)** |
| **Estimador de tipos de mercado** | Informa del tipo medio publicado y su rango | Series BCE/BdE con fecha | Parcial (usa APRC anual, mal etiquetado) |
| **Modelo de pricing** | Fija el tipo de una operación: coste de fondos (Euríbor/IRS), liquidez, pérdida esperada (PD × LGD × EAD), coste de capital, costes operativos, margen, bonificaciones por vinculación | Datos internos de la entidad y de la operación | **No** (GBR macro + `tanh` sin datos de operaciones) |
| **Motor de admisión** | Decide conceder/denegar según política y modelo de riesgo validado | Identidad/KYC, CIRBE y ficheros de solvencia, ingresos verificados (nóminas, IRPF, vida laboral), estabilidad laboral, unidad familiar y gastos de vida, LTV sobre tasación (ECO/805/2003), LTI, DSTI con estrés, edad/plazo, scoring de PD validado, políticas y excepciones, revisión humana, FEIN y motivación de denegación | **No** (3 reglas DTI + edad + ahorro) |

**Clasificación:** *simulador hipotecario con reglas heurísticas de pre-evaluación*, presentado como pricing y
admisión. Debe presentarse como **simulador orientativo** y no emitir "Aprobada/Denegada".

### 3.6 Fallo de ejecución (M1)

Con shap 0.54.1, `float(explainer.expected_value)` lanza `TypeError: only 0-dimensional arrays can be converted to
Python scalars` → HTTP 500 en `/api/hipoteca-recomendacion`. El harness lo rodea solo para auditar el resto
(`patch_shap_scalar`). `Web/requirements.txt` no incluye scikit-learn, shap, numpy, statsmodels, seaborn ni
`google-genai` (el paquete realmente importado), y no fija versiones.

---

## 4. Marco regulatorio y qué puede afirmar el TFM (misión 5)

### 4.1 AI Act — Reglamento (UE) 2024/1689, modificado por el Reglamento (UE) 2026/1744

- **Clasificación.** Anexo III, punto 5.b): son de alto riesgo los sistemas de IA destinados a *evaluar la solvencia
  de personas físicas o establecer su calificación crediticia* (salvo detección de fraude). El art. 6.3 permite
  excepcionar algunos sistemas del anexo III, pero **no si realizan elaboración de perfiles** de personas físicas,
  que es el caso (ingresos, deudas, edad → evaluación de situación económica). El Ómnibus no modifica el anexo III
  ni el art. 6.3 (solo añade los apartados 1 bis–1 quater del art. 6, sobre componentes de seguridad).
- **¿Es "sistema de IA"?** El GBR (aprendizaje automático) sí; las reglas DTI aisladas probablemente no (las
  Directrices de la Comisión sobre la definición de sistema de IA excluyen sistemas basados solo en reglas definidas
  por personas). El conjunto, si lo desplegase un prestamista para decidir o fijar condiciones, entraría en el
  anexo III 5.b.
- **El TFM no está obligado**: el art. 2.8 excluye la investigación, prueba y desarrollo previos a la introducción en
  el mercado o puesta en servicio. Pero eso significa que **no se puede afirmar cumplimiento**; solo describir qué
  exigiría.
- **Obligaciones si se desplegara (proveedor):** gestión de riesgos (art. 9), datos y gobernanza (art. 10, retocado por
  el Ómnibus), documentación técnica (art. 11 + anexo IV), registros (art. 12), transparencia e instrucciones de uso
  (art. 13), supervisión humana (art. 14), precisión, solidez y ciberseguridad (art. 15), sistema de gestión de la
  calidad (art. 17), evaluación de la conformidad (art. 43), declaración UE y marcado CE, registro (art. 49).
  **Responsable del despliegue (entidad):** art. 26 y **evaluación de impacto en derechos fundamentales (art. 27)**,
  exigida expresamente para los sistemas del anexo III 5.b y c; el Ómnibus permite referenciar la EIPD del RGPD
  (art. 27.4-5 modificados). Derecho a explicación de decisiones individuales: art. 86.
- **Calendario verificado en el DOUE** (`out/omnibus_ia_art113_extracto.txt`): Reglamento (UE) 2026/1744 de 8/07/2026,
  [DO L de 24/07/2026](https://www.boe.es/doue/2026/1744/L00001-00041.pdf), en vigor a los 3 días de su publicación.
  Nuevo art. 113.c): capítulo III secciones 1–3 aplicables desde el **2/12/2027** (anexo III) y el **2/08/2028**
  (anexo I). El art. 50 (informar de que se interactúa con una IA) aplica desde el 2/08/2026 (art. 111.4: hasta
  2/12/2026 para el marcado de contenido sintético de sistemas ya comercializados). El art. 4 (alfabetización) pasa
  a obligación de "apoyar la promoción". Confirmado también por el [Consejo/SEAE (30/06/2026)](https://eeas.europa.eu/delegations/chile/artificial-intelligence-council-gives-final-green-light-simplify-and-streamline-rules_en)
  y por [EUR-Lex ELI 2026/1744](https://eur-lex.europa.eu/eli/reg/2026/1744/oj?locale=en).
- **SHAP.** Es una técnica de atribución local *post hoc*. Puede apoyar la documentación (art. 11/13) o la explicación
  (art. 86), pero no satisface por sí sola ninguna obligación. En este sistema además explica un modelo que no
  determina el tipo (C2). Con variables correlacionadas (Euríbor, IPC, ahorro), las atribuciones no son causales.

### 4.2 Otras normas

- **RGPD art. 22** (decisiones automatizadas con efectos significativos): la denegación automática de crédito entra de
  lleno. El TJUE (C-634/21, *SCHUFA*, 7/12/2023) consideró decisión automatizada la generación de un score cuando es
  determinante, y en C-203/22 (*Dun & Bradstreet Austria*, 27/02/2025) precisó el derecho a una explicación del
  procedimiento y la lógica. También arts. 13-15, 35 (EIPD), 28 (encargado: Google) y 44 y ss. (transferencias).
- **LCCI (Ley 5/2019)**: art. 11 (evaluación de solvencia completa, que no puede basarse predominantemente en el valor
  del inmueble), art. 12 (tasación), art. 14 (FEIN, FiAE, reparto de gastos), art. 19 (servicios de asesoramiento:
  requisitos específicos si se presta "asesoramiento"; un chatbot llamado "asesora hipotecaria" que orienta al
  cliente se acerca a ello). La Directiva 2014/17/UE (art. 7) exige actuar con honestidad, imparcialidad y
  transparencia atendiendo a los intereses del consumidor: incompatible con un chatbot que "maximiza el beneficio del
  banco" y "persuade".
- **Transparencia bancaria**: Orden EHA/2899/2011 y Circular 5/2012 del BdE (TAE, información precontractual,
  préstamo responsable); Circular 4/2020 del BdE (publicidad). Mostrar "TIN" construido sobre una TAE, o una
  "oferta" con marca de una entidad real, es incompatible con estas exigencias si fuera real.
- **EBA/GL/2020/06** (concesión y seguimiento de préstamos): evaluación de solvencia con métricas y análisis de
  sensibilidad; requisitos específicos para modelos automatizados (comprensión del modelo, calidad de datos,
  explicabilidad, supervisión humana, seguimiento del rendimiento) y fijación de precios basada en riesgo y costes.

### 4.3 Qué puede y qué no puede afirmar el TFM

| Puede afirmar | No puede afirmar |
|---|---|
| "Prototipo académico de simulador hipotecario orientativo, no desplegado" | "Cumple el AI Act / los requisitos de explicabilidad" |
| "Si lo desplegara un prestamista para evaluar solvencia, sería de alto riesgo (anexo III 5.b) y exigiría arts. 9-15, 17, 43, 49, 26-27 y 86, aplicables desde el 2/12/2027 (Reglamento 2026/1744)" | "Tipo óptimo", "tipo justo", "oferta personalizada", "diferencial real del banco" |
| "SHAP se usa para interpretar un modelo macro exploratorio, con limitaciones" | "Hipoteca aprobada/denegada", "límite legal" de DTI o de edad |
| "Las cuotas siguen el sistema francés (verificado)" | "RMSE CV 0,10 / CV Accuracy 98,6 %" como métrica de validación |

---

## 5. Especificación funcional del asesor v2

### 5.1 Conservar / eliminar

| Conservar | Eliminar o mover |
|---|---|
| Cuota francesa (verificada) | GBR del flujo del cliente (si se quiere, apéndice metodológico con validación de origen móvil frente a persistencia) |
| Estructura ITP (usada) vs IVA + AJD compraventa (nueva) | Ajuste `tanh` por renta/PIB pc; recargo +0,75 pp por precio < 100.000 €; prima fija +0,50 pp |
| No imputar gastos del préstamo al cliente (y decirlo) | Regla "el banco se queda el mayor de los dos tipos" |
| Series BCE APRC/Euríbor (con trazabilidad) | Estados "Aprobada/Denegada/Analista"; denegación automática por edad |
| Selección de provincia (con código INE) | Tabla `YOUNG_FINANCING`; métricas fijas (R² 0,8492…) y "CV Accuracy" |
| | `/test-hipoteca` legacy; Noa Strategic; marca de entidad real |

### 5.2 Módulos y fórmulas

**M1 — Estimador de tipo de mercado (no oferta).**
- Fuente: BCE MIR España (APRC `A2C.A.C`, TEDR total `A2C.A.R`, TEDR variable `A2C.F.R`) y Euríbor 12M (FM), con
  **mes de referencia y fecha de descarga** visibles.
- Fijo: referencia = último TEDR total publicado; rango = [mín, máx] de los últimos 12 meses (`rango_tipo_mercado`).
- Variable: referencia = Euríbor 12M último + diferencial de referencia, con diferencial = `TEDR_var − Euríbor12M`
  (proxy; rango de 12 meses). Etiquetar TAE vs TIN correctamente (APRC − TEDR ≈ 0,04–0,25 pp).
- Siempre editable: el usuario introduce el TIN de la oferta que tenga.
- Años futuros: sin "proyección" puntual; como mucho escenarios (base / +1 pp / +3 pp) claramente etiquetados.

**M2 — Simulador de capacidad de pago.**
- `capital = precio + gastos_comprador − aportación`, acotado por `LTV_max·min(precio, tasación)` (parámetro).
- `cuota = cuota_francesa(capital, TIN, n)`; `n = 12·min(plazo, 30, edad_max_venc − edad)` con `edad_max_venc`
  parámetro de política (por defecto 75) y aviso de que no es límite legal.
- `DSTI = (cuota + deudas)/ingresos_netos_unidad_familiar`; `DSTI_estrés` con `TIN + Δ` (Δ = 3 pp por defecto,
  configurable) en variable y mixto (tras el periodo fijo); `LTI = capital/(12·ingresos)`; `LTV`.
- `capital_max = capital_maximo_por_cuota(u·ingresos − deudas, TIN(+Δ), n)` con `u` umbral orientativo (35 %).
- Salida descriptiva: "holgura dentro/fuera del umbral orientativo", **nunca** aprobación.

**M3 — Gastos de compra (lado comprador).** `impuesto(regla vigente, precio)` + `AJD compraventa` (solo nueva) +
`arancel_notarial_base` + `arancel_registral_base` (cotas inferiores, con rango que incluya folios, copias e IVA) +
`tasación` (parámetro). Lista explícita de gastos a cargo del banco (LCCI art. 14.1.e; RDL 17/2018).

**M4 — Programas de ayuda.** Ficha informativa (ICO y programas autonómicos verificados) con requisitos y enlace; no
modifica el capital automáticamente.

**M5 — Explicaciones.** Texto determinista a partir de fórmulas ("tu cuota sube X € si el Euríbor sube 1 pp").

### 5.3 Tabla fiscal con vigencias (`data/metadata/fiscalidad.csv`)

Campos: `ccaa_code`, `impuesto` (ITP | IVA | IGIC | AJD_compraventa), `tipo_vivienda` (usada | nueva | VPO),
`colectivo` (general | joven | familia_numerosa | discapacidad…), `edad_max`, `valor_max`, `renta_max`,
`requisito_vivienda_habitual`, `tramo_desde`, `tramo_hasta`, `tipo_pct`, `modo` (marginal | total),
`vigente_desde`, `vigente_hasta`, `norma`, `url_boletin`, `fecha_verificacion`, `estado` (verificado | pendiente).
La app debe negarse a mostrar un tipo con `estado = pendiente` sin aviso visible. Mecánica implementada en
`asesor_v2_reference.py` (`ReglaFiscal`, `regla_vigente`, `cuota_impuesto`); los 7 tramos ignorados y las 4
discrepancias de §3.2 son los primeros registros a verificar.

### 5.4 Presentación honesta y avisos

> *Simulación orientativa con fines académicos. No es una oferta vinculante, ni una evaluación de solvencia, ni
> asesoramiento en el sentido del art. 19 de la Ley 5/2019. Los tipos mostrados son medias de mercado publicadas por el
> BCE (mes de referencia: AAAA-MM), no el precio que te ofrecería una entidad concreta. Los impuestos dependen de tu
> CCAA y circunstancias; comprueba la normativa vigente. Los gastos de notaría y registro del préstamo, la gestoría y el
> AJD del préstamo corresponden a la entidad (Ley 5/2019, art. 14). La tasación corre de tu cuenta.*

Chatbot (si se conserva): aviso art. 50 ("estás hablando con un sistema de IA"), contexto construido **en el servidor**
a partir del cálculo (no aceptado desde el navegador), minimización de datos (sin edad/ingresos exactos: rangos),
salida renderizada con `textContent` o markdown saneado, prompt sin afirmaciones legales falsas, sin persuasión ni
recomendación de producto, límite de longitud y de frecuencia, contrato de encargo y plan de pago de la API que no
reutilice los datos.

### 5.5 Tests unitarios clave (implementados en `test_asesor_v2_reference.py`, 24/24 OK)

| Test | Entrada | Esperado |
|---|---|---|
| Cuota francesa | 150.000 €, 3 %, 300 m | 711,32 € |
| | 237.500 €, 2,78 %, 360 m | 973,35 € (coincide con la app, P01) |
| | 200.000 €, 3,5 % / 6,5 %, 360 m | 898,09 € / 1.264,14 € |
| | 100.000 €, 0 %, 120 m | 833,33 € |
| Saldo final del cuadro | cuota anterior | 0 (±1e-6) |
| Inversa capital ↔ cuota | 180.000 €, 3,2 %, 300 m | 180.000 € |
| Arancel notarial base (Nº 2, −5 %) | 5.000 / 100.000 / 200.000 / 250.000 / 400.000 € | 85,64 / 269,14 / 340,51 / 364,26 / 435,51 € |
| Arancel registral base (Nº 2, −5 %) | ídem | 22,84 / 126,92 / 176,90 / 191,15 / 233,90 €; máx. 2.072,59 € |
| Vigencias | regla A hasta 31/05/2026, B desde 01/06/2026 | selecciona A o B según fecha; error si no hay regla |
| Tipo sobre valor total vs escala | 9 %/11 % >1 M€; 8 % hasta 250k y 10 % el exceso | 300k → 27.000; 1,2 M → 132.000; escala 300k → 25.000 |
| Gastos sin conceptos del préstamo | 200.000 €, ITP 10 %, tasación 350 € | 20.867,41 €; sin AJD ni notaría ni registro del préstamo |
| Estrés variable vs fijo | 200.000 €, 3,5 %, 360 m, 3.000 €/mes | DSTI 29,94 %; estrés variable 42,14 %; fijo sin estrés |
| Coherencia del tipo mostrado | — | cuota = cuota_francesa(tipo mostrado) |
| Plazo por edad | 40/60/76/50 años | 360/180/0/240 meses |
| Sin "aprobada" | — | la salida no contiene estado de concesión |

Tests de regresión adicionales para la app v2: las 52 provincias mapean a una CCAA (hoy fallan 12); ninguna salida
contiene `approved/denied`; el TIN del JSON es el que usa la cuota; el endpoint no da 500 con las versiones fijadas
en `requirements.txt`.

---

## 6. Decisiones que requieren arbitraje del coordinador

1. **GBR**: retirarlo del asesor (recomendado) y dejarlo como apéndice con validación honesta, o eliminarlo.
2. **Chatbots**: eliminar Noa Strategic (recomendado); Noa cliente solo con las salvaguardas de §5.4, o eliminarla.
3. **Parámetros de política** del simulador: umbral DSTI orientativo (35 %), estrés (+3 pp), edad máxima al vencimiento
   (75), LTV de referencia (80 %).
4. **Verificación fiscal**: quién contrasta en el boletín oficial cada registro de `fiscalidad.csv` (hoy solo hay
   fuente secundaria) y alcance (¿incluir regímenes forales, Canarias, Ceuta y Melilla o excluirlos expresamente?).
5. **Años futuros**: el escenario Euríbor 2026 = 2,00 % ya está refutado por los datos (2,767 % de media ene–oct);
   decidir si se muestran escenarios o se elimina el modo "futuro".
6. **Marca**: sustituir la marca de CaixaBank y "Noa — Asesora Hipotecaria CaixaBank" por "Atalaya · Analítica
   Hipotecaria" en plantillas y prompts.

---

## 7. Fuentes consultadas

- BCE Data Portal (API): [APRC ES](https://data-api.ecb.europa.eu/service/data/MIR/M.ES.B.A2C.A.C.A.2250.EUR.N?format=csvdata),
  [TEDR ES](https://data-api.ecb.europa.eu/service/data/MIR/M.ES.B.A2C.A.R.A.2250.EUR.N?format=csvdata),
  [TEDR variable ES](https://data-api.ecb.europa.eu/service/data/MIR/M.ES.B.A2C.F.R.A.2250.EUR.N?format=csvdata),
  [Euríbor 12M](https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA?format=csvdata) (descarga 21/11/2026).
- Reglamento (UE) 2026/1744: [DOUE vía BOE](https://www.boe.es/doue/2026/1744/L00001-00041.pdf), [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2026/1744/oj?locale=en);
  [nota del Consejo (SEAE)](https://eeas.europa.eu/delegations/chile/artificial-intelligence-council-gives-final-green-light-simplify-and-streamline-rules_en);
  comentarios secundarios: [Gibson Dunn](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/),
  [Bird & Bird](https://www.twobirds.com/en/insights/2026/digital-omnibus-on-ai-provisional-agreement-reached-at-the-may-trilogue),
  [Lewis Silkin](https://lewissilkin.com/insights/2026/07/09/council-of-the-eu-gives-ai-omnibus-final-green-light-102nbb1).
- Reglamento (UE) 2024/1689 (AI Act): arts. 2.8, 3.1, 6.3, 9-15, 17, 26, 27, 43, 49, 50, 86, 113; anexo III 5.b.
- [RD 1426/1989 (arancel notarial)](https://www.boe.es/eli/es/rd/1989/11/17/1426/con); [RD 1427/1989 (arancel registral)](https://www.boe.es/eli/es/rd/1989/11/17/1427/con).
- Ley 5/2019 (LCCI), arts. 11, 12, 14, 19; RDL 17/2018; Directiva 2014/17/UE art. 7; Orden EHA/2899/2011; Circulares
  BdE 5/2012 y 4/2020; Orden ECO/805/2003; EBA/GL/2020/06; RGPD arts. 13-15, 22, 28, 35, 44; TJUE C-634/21 y C-203/22.
- Línea de Avales ICO: [BOE 2/07/2026 (adenda)](https://www.boe.es/boe/dias/2026/07/02/pdfs/BOE-A-2026-14404.pdf),
  [La Moncloa](https://www.lamoncloa.gob.es/serviciosdeprensa/notasprensa/vivienda-agenda-urbana/paginas/2024/solicitar-avales-gobierno-ico-vivienda.aspx);
  secundaria: [Diario de Avisos](https://diariodeavisos.elespanol.com/2026/07/boe-prorroga-avales-ico-comprar-primera-vivienda-2027/), [Finect](https://www.finect.com/usuario/davidcarmona/articulos/como-comprar-primera-vivienda-aval-ico).
- ITP por CCAA (secundaria, con cita normativa): [bm.consulting, 29/10/2026](https://bm.consulting/es/insights/tipos-itp-comunidad-autonoma-2026/);
  otras comparativas con discrepancias: [registrosdepropiedad.es](https://www.registrosdepropiedad.es/itp/), [visorfiscal.es](https://visorfiscal.es/blog/itp-vivienda-usada-comunidades-autonomas).

*Limitaciones:* no se ha verificado en el boletín oficial cada tipo autonómico (marcados como pendientes); los
detalles de la adenda ICO de 2026 (límites de renta por provincia) no se han leído en el texto del BOE; las
referencias a EBA/GL, Circulares BdE y jurisprudencia se citan por su contenido general, sin número de párrafo.
