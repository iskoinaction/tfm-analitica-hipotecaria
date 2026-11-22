# Fase VII · Revisión independiente estadística + economía (v2)

Alcance: contraste de `01_econometria_v2`, `02_ds_v2`, `02_pipeline`, `04_asesor_v2` contra `econometrics_v2.json`, `artifacts/demand/*`, `data/forecasts/*v2*`, `escenarios_macro.yaml`, `data/processed/*` y el front (`site/src`, `Web/atalaya/templates`, `README.md`). Cálculos propios en solo lectura.

## 1. Cifras informe vs artefacto (24 comprobadas, todas coinciden)
Traza 82,81/VC 69,82/RA 67,85/maxeig 32,40<33,88/p_boot 0,1682; EG −2,91 p 0,634; ARDL F 3,38 (p_I1 0,095) y 4,41 (0,017); β +4,72/+1,45/+0,125/−5,66; α_hip +0,0445 (p 0,42); FEVD Cholesky 16,2/4,6/18,3/4,4/56,5 y rango Euríbor 4,6–16,5; IRF Euríbor −0,028, PIB +0,054; LM h4 p 0,034; panel CD 112,6/125,4, FE-DK 1,698 y 0,685 (p 0,011), PMG centrado 0,034 (se 0,11); hold-out naive 6,48/9,09/15,12/20,50 %; cobertura SARIMA 94/81/62/56 %; sendas 511.106 / 441.302 / 557.150 / 523.748; Euríbor 3,414; 8.884 filas. **Los informes son fieles a los artefactos**; los problemas están en la interpretación, en los supuestos y en el front/README.

## 2. Hallazgos

### H1 · ALTA · Trayectoria 2026 incoherente con lo observado (estacionalidad espuria + salto de nivel de paro)
- Problema: el condicional (cap1) usa dummies Q2-Q4 estimadas desde 2005 (Q4 = −0,107). En 2022-25 el Q4 es el trimestre más alto (desviación +0,028; 2024 +0,147; 2025 +0,061). Resultado: 2026Q4 = 117.669 frente a 132.336 en 2025Q4 (−11 %). H1-2026 observado +7,0 % interanual (259.684 vs 242.655), H2-2026 proyectado −5,3 % (242.102 vs 255.774). Además el paro de escenario (CE 9,9 / 9,6) está por debajo del observado (EPA 2026T1-T3: 10,83/9,87/10,18; MA4 origen 10,27): Δparo ≈ −0,4 pp × (−0,078) ≈ +3 % en el base, que compensa casi exactamente el efecto Euríbor (+0,63 pp × −0,045 ≈ −2,9 %). Que el base (511.106) ≈ naive (512.520) es una coincidencia de errores, no una validación. Con CE 9,9 para 2026, el Q4 debería ser ≈ 8,7 %: imposible.
- Evidencia: `proyecciones_2026_2030_v2.csv` (base 2026Q3-Q4), `metadata.json` (coef. q4 −0,107, d_paro −0,078), `nacional_trimestral.csv`.
- Solución: (a) empalmar el paro del escenario con un ajuste de nivel (desvío = escenario − observado en el último dato, no nivel CE absoluto) o usar solo Δ del escenario; (b) estacionalidad recientes/ventana móvil o desestacionalizar; (c) presentar anual 2027+ y no trimestral, o etiquetar la forma intra-anual como no fiable.
- Riesgo: cambia las cifras citadas (511.106, 523.748); hay que regenerar CSV, front y tests. Si se ancla el paro, el base bajará ≈ 3 % (≈ 495-500k), por debajo del naive.

### H2 · ALTA · El "escenario" adverso/favorable lo dominan supuestos propios de paro, no el Euríbor
- Evidencia: adverso 441.302 (−13,7 % vs base): Δparo +1,5 pp × −0,078 ≈ −11,7 % + Euríbor +1,5 pp × −0,045 ≈ −6,8 % parcial. Las sensibilidades de paro/Euríbor son "supuesto propio" (YAML). El OLS del condicional es peor que el naive en hold-out a h=1,2 (U 1,29/1,21) y en 2026T1-T2 observado (MAPE h=1 7,3 % vs 1,6 % del naive; `oos_extra`, n=2). El VAR dice Euríbor no significativo (banda −0,07;+0,02), PIB sí: el modelo de sendas y el econométrico no concuerdan y el primero no incluye PIB ni precio.
- Gravedad ALTA solo si se comunica como "predicción de impacto del Euríbor". Solución: etiquetar la banda como "sensibilidad mecánica a un salto supuesto de paro/Euríbor", mostrar contribución por canal, y no presentar cociente adverso/base como riesgo calibrado. Riesgo: pérdida de atractivo del "stress test".

### H3 · ALTA · Precio plano nominal contradice la historia y la propia coherencia del escenario
- Evidencia: MIVAU 2.355 €/m² en 2026Q2, interanual +12,5 % (media histórica +3,3 %, máx. +18,5 %); IAPC 3,9/3,3/2,3 y PIB pc nominal +5,45/4,35/3,15 → precio plano = −3,9 %, −3,3 %, −2,3 % reales anuales y razón precio/renta cayendo 3-5 %/año. Bandas p10-p90 del precio (±5,5 % a h=8) salen de errores 2013-21 y cubren 32 % en hold-out (`cobertura_intervalos_holdout.csv`). ETS-log tiene U 0,83-0,92 en hold-out a h≥4. Además la banda del precio no incluye escenarios.
- Problema económico: cualquier uso en asesor/app (esfuerzo, entrada, LTV) con precio plano subestima el esfuerzo.
- Solución: mostrar "precio constante" explícitamente como *referencia sin tendencia* con una variante deriva/ETS y banda ancha; no mezclar con la demanda como si fuera predicción. Riesgo: re-selección de modelo (aplazada por decisión pendiente nº 1); si se cambia ahora, rompe el protocolo.

### H4 · MEDIA · Hold-out de 16 observaciones, régimen atípico y selección sin diferencias reales
- Evidencia: el hold-out 2022-25 contiene el ciclo Euríbor −0,35 → 4,1 % y hipotecas 119.911 → 88.378 → 132.336; la ventana de selección (2013-21) no contiene ese régimen. En selección h=4/8, SARIMA 0,36/0,47 vs naive 0,36/0,48: diferencia de 0,00-0,01 MASE = ruido; elegir SARIMA es arbitrario. Naive h=4 y h=8 coinciden con seasonal naive (misma tasa 15,12 %) por construcción. DM con n=16 y solapamiento tiene poca potencia: p_sq h=4 SARIMA 0,001 pero p_abs 0,080 (sensible a la pérdida y a 1-2 trimestres de 2022-23).
- Leakage: **no encontrado**. Selección con objetivos ≤2021Q4 (n=36/35/33/29 correctos), hold-out solo en tabla; cuantiles de intervalo de sendas usan `max_target=HOLDOUT_END` (válido para intervalos finales, no para selección); 2026T1-T2 etiquetado `oos_extra`. Matiz: la forma del condicional (regresores, `cap_h`) se diseñó tras ver el panel completo en auditoría v1 (grados de libertad del investigador).
- Solución: declarar que no hay prueba de superioridad ni de inferioridad ("sin evidencia de mejora"); añadir resultados con ventana de selección ≥ 2022 como sensibilidad; reportar 2026T1-T2 como verdadera predicción fuera de muestra. Riesgo: ninguno técnico; solo texto.

### H5 · MEDIA · Narrativa "ningún modelo bate al naive" / "sin cointegración robusta": bien calibrada con dos sobrecorrecciones
- "Ningún modelo elegible supera al naive": correcta como estimación puntual (U>1 en los 4 horizontes), pero con n=16 es ausencia de evidencia, no evidencia de ausencia; ElasticNet h=1 U 0,77 y media móvil h=8 U 0,81 se descartan por "a posteriori" (correcto) pero tampoco prueban nada. `Closing.tsx` dice "la mejora de los modelos es limitada", lo que sugiere alguna mejora: no la hay.
- Cointegración: p_boot r=0 oscila 0,024–0,47 según especificación (k+1 0,024; k=1 0,028; IPV 0,086; resto 0,11–0,47). Rechaza al 10 % en 3 de 9 variantes. "No robusta" es justo; "VAR en diferencias principal" también, pero un VAR en diferencias descarta información de nivel si r≥1 (T=83, 5 variables, dummies: poca potencia). El VECM tiene Euríbor con exogeneidad débil rechazada (p 0,0005; α_Euríbor 0,82) y β inestable (precio −190/+185): relación no interpretable, de acuerdo. Sobrecorrección: presentar el rango como "no hay" en vez de "no concluyente".
- Solución: mantener VAR principal, frase "no concluyente/frágil" en README y front. Riesgo: ninguno.

### H6 · MEDIA · Identificación económica débil en el sistema nacional
- PIB pc y precio y coste de construcción son series **nominales** I(1) dominadas por inflación; la homogeneidad nominal no se rechaza (p 0,49), signo de coste −0,064 y β_coste −5,66 recogen el choque inflacionario 2022-23 más que un canal de oferta; Euríbor con β +0,125 (+13 %/pp) de signo contrario; precio de vivienda en el FE-DK: +1,70 niveles/+0,685 diferencias y `lmateriales` −1,79 (niveles) → +1,46 (diferencias): cambio de signo según diseño. Ninguna afirmación causal puede sostenerse. Solución: añadir una versión real (deflactada por IAPC) como robustez; afirmar solo "co-movimiento". Riesgo: ampliar el informe, sin cambiar conclusiones.
- Afirmación indebida candidata: `Intro.tsx` "Separar el papel del Euríbor, la renta, el precio… mediante econometría": suena a atribución causal; la FEVD tiene IC bootstrap [0,4; 28,1] para Euríbor.

### H7 · MEDIA · Panel v2: pseudo-replicación y no estacionariedad no resueltas
- Euríbor y coste de construcción son nacionales (86 valores únicos × 44 provincias): sus coeficientes se identifican por 86 puntos; DK arregla el error estándar, pero MG/PMG "bruto" con 44 regresiones idénticas en estas variables no aporta información. La CD de residuos persiste (193 en niveles; 84 en diferencias): el ciclo común no se elimina del todo.
- `pib_pc` del panel NO es "anual asignado al año de referencia": `panel_modelado.csv` usa regla de disponibilidad (ejemplo Madrid: 2023Q1-Q3 con ref_year 2020; 2025Q4-2026Q3 con ref_year 2023) → retardo de 2-3 años y escalón de 4 trimestres (22 valores únicos por provincia), distinto del PIB pc nacional trimestral del VAR. Está declarado como "sin imputar" pero se arrastra el valor viejo.
- CIPS de log hipotecas en nivel (−3,93 con constante; VC 5 % −2,12) rechaza raíz unitaria, mientras precio (−1,55) y PIB (−2,18) no: la regresión en niveles mezcla I(0) con I(1), lo que contradice la clasificación I(1) nacional y no se menciona en el informe.
- 8 provincias excluidas (16, 22, 32, 34, 40, 42, 44, 52): provincias pequeñas con huecos en hipotecas, sesgo hacia las grandes; el informe no lo discute.
- Solución: dar peso solo al FE en diferencias con efectos temporales (o interacciones con características provinciales); citar N efectivo = 86 para variables nacionales; reportar CIPS; documentar el retardo del PIB pc y la exclusión. Riesgo: reducir la "lectura provincial".

### H8 · MEDIA · Supuestos macro: dos anclas verificables y un contraste no releído
- Euríbor 12M base 3,414 % fijo 2027-2030: BCE-3M 3,0 + diferencial 0,414 (media últimos 12 meses con curva ascendente) mantenido 4 años; 2029-30 = valor 2028 (supuesto). Cota alta respecto a la media 2023-26 (≈3,2 %) y sin reversión; el último dato mensual (oct-26) es 3,24 → la base asume +0,17 pp inmediato. El contraste BdE (3M 3,6 % en 2027) figura como "NO releído".
- IAPC 2026 3,9 %: el IPC observado T1-T3 es 2,67/3,20/4,27 → T4 ≈ 5,5 %; plausible solo si el repunte sigue; 2027 3,3 % requiere caída brusca. Paro: ver H1.
- Solución: marcar 2029-30 como "constante mantenida" (ya está) y no calcular métricas anuales largas; releer BdE o quitarlo de la lista de "contraste". Riesgo: ninguno.

### H9 · MEDIA · Intervalos trimestrales sumados como anual (front)
- `site/src/sections/Closing.tsx` suma p10 y p90 de 4 trimestres para dar la "banda anual 2030": los cuantiles no son aditivos (errores correlacionados) y el naive anual 2029-30 es una constante 523.748 repetida; 2029 y 2030 son idénticos (`523.748`) porque no hay tendencia. Solución: mostrar solo la banda trimestral o escalar con la covarianza empírica de errores anuales. Riesgo: bajo.

### H10 · BAJA · Avisos y nombres
- "Ex post condicional" se reconoce como techo; correcto. `02_pipeline`: "0 variables con cambios" tras primer día de datos y workflow no ejecutado: no verificado. `04_asesor`: cobertura de rango 21-37 % ya declarada.

## 3. Frases/cifras del README/front que contradicen los artefactos
`README.md` (v1 intacto; **CRÍTICA**: contradice todo v2):
1. L90 "RF_Nac (modelo ganador) 7,11 %" (naive 6,48 % h=1; ningún modelo elegible supera al naive) y tabla L82-90 (MAPE 18-35 %).
2. L106-108 "relaciones causales estructurales", "Johansen confirma r = 1", β +0,35/+2,48/−0,10/−1,09 (v2: p_boot 0,168; +4,72/+1,45/+0,125/−5,66, inestables).
3. L114 FEVD 53,3/38,8/2,2 %; "44 % por trimestre (semivida 1,2)" (v2: 56,5 % propio; α +0,045 n.s.).
4. L124 GBR+SHAP, ajuste `tanh` (eliminados), L132 "8.320 filas" (8.884), L140 Euribor 2,00-2,30 %, IPC 2,0 % (v2: 3,24→3,41 %; 3,9/3,3/2,3).
5. L172 cap 4 % del CAGR, L190-195 MAPE 15,7 %/U 0,944, L201 suelo NAIRU 8,5 % (eliminados), L211 Holt-Winters gana en 79 % de provincias, L219-225 `/demanda` "RF_Nac" y `/vecm`.
`site/src/sections/Models.tsx` L37: "VECM con rango contrastado por bootstrap, con VAR en diferencias como sensibilidad" — **invertido**: el principal es el VAR. L63 y `Closing.tsx` coherentes.
`Closing.tsx`: "Predicción modesta… la mejora es limitada" → "no hay mejora demostrada"; banda anual sumada (H9). `Intro.tsx` L60: "Separar el papel del Euríbor…" (atribución). `Web/.../demanda.html` L25: "dependen de supuestos (Euríbor, renta, precios)": el modelo condicional solo usa Euríbor y paro; el precio es plano. `Web/.../caso_negocio.html` L14 "relaciones dinámicas (VAR/VECM)": aceptable. No se hallaron cifras v1 en `Web/atalaya/templates`.

## 4. Veredicto
**Defendible:** pipeline y trazabilidad; protocolo de selección/hold-out sin leakage; reconocimiento de que el naive es la referencia; ausencia de cointegración robusta con VAR en diferencias como principal; FEVD con rangos; estimación de panel con DK y CD; asesor determinista sin "aprobada/denegada"; cifras de informes coherentes con artefactos.
**No defendible tal cual:** (i) la trayectoria trimestral 2026 (estacionalidad y salto de paro, H1); (ii) las bandas adverso/favorable como medida de riesgo del Euríbor (H2); (iii) precio plano como senda económica (H3); (iv) el README raíz entero (v1); (v) "no hay cointegración" sin matiz de potencia; (vi) lecturas causales o de "determinantes"; (vii) panel PIB pc retardado y CIPS no discutido.
**Prioridad:** README (CRÍTICA, solo texto), Models.tsx L37, H1 (recalcular con paro anclado), H3 (etiquetado), H9.
