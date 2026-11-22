# Validación de modelos (v2)

Todas las cifras proceden de `artifacts/` y de los informes `reports/phase2/`; los scripts son reproducibles con semilla fija. **Se informa también de lo que no funciona.**

## 1. Demanda nacional de hipotecas sobre viviendas
Protocolo: rolling-origin expansivo para seleccionar (orígenes 2012Q4–2021Q4, objetivos ≤ 2021Q4) y **hold-out 2022Q1–2025Q4 (n = 16)** evaluado una sola vez. Selección por menor MASE en la ventana de selección.

| h (trim.) | Naive: MAPE | Modelo elegido | Hold-out del elegido: MAPE / U de Theil |
|---|---|---|---|
| 1 | 6,48 % | ETS-log | 8,38 % / 1,44 |
| 2 | 9,09 % | SARIMA | 10,45 % / 1,14 |
| 4 | 15,12 % | SARIMA | 18,23 % / 1,21 |
| 8 | 20,50 % | SARIMA | 31,52 % / 1,46 |

**Ningún modelo elegible por la regla pre-especificada bate al naive en el hold-out, a ningún horizonte** (a h = 4, SARIMA es significativamente peor: Diebold-Mariano p = 0,001). Los mejores modelos *a posteriori* (ElasticNet a h = 1, U = 0,77; media móvil 4T a h = 8, U = 0,81) no eran elegibles por la regla y se basan en n = 16: no se presentan como resultado. Conclusión honesta: la demanda se comporta casi como un paseo aleatorio a estos horizontes y el valor del proyecto está en los **escenarios condicionales**, no en la predicción puntual.

**Cobertura de intervalos** (nominal 80 %, SARIMA, hold-out): 94 / 81 / 62 / 56 % a h = 1/2/4/8. A h ≥ 4 los intervalos son demasiado estrechos.

*Comparación con la v1:* el MAPE de 7,11 % de RF_Nac correspondía a h = 1, n = 8, un solo origen, y el naive daba 7,30 % en los mismos 8 trimestres (Diebold-Mariano p = 0,40). La cifra no es reproducible bit a bit (oscila entre 4,9 % y 9,9 % según la semilla).

## 2. Econometría
- Johansen con bootstrap salvaje: p(r = 0) = 0,168; traza 82,81 frente a un valor crítico de 69,82 (asintótico). Engle-Granger p = 0,63. Con 3 retardos p = 0,024; con IPV como precio p = 0,086 → **evidencia no concluyente (rechaza al 10 % en 3 de 9 variantes)**.
- Modelo principal: VAR(2) en diferencias, estable (raíz máxima 0,84). FEVD(20) de hipotecas (Cholesky / GFEVD): precio MIVAU 4,4 / 11,7 %, costes de construcción 16,2 / 14,6 %, Euribor 4,6 / 7,3 %, PIB pc 18,3 / 11,1 %, propio 56,5 / 55,3 %. El peso del Euribor va de 4,6 % a 16,5 % según el orden de Cholesky (el 2,2 % de la v1 era el extremo inferior de 120 ordenaciones).
- VECM (sensibilidad): coeficiente de ajuste de hipotecas +0,045 (p = 0,42): las hipotecas no corrigen el desequilibrio; β recursivo muy inestable; signo del Euribor contrario al esperado.
- Panel (N = 44 provincias; 8 excluidas por huecos): fuerte dependencia transversal (CD = 112,6); centrado transversalmente la elasticidad al precio es ≈ 0 (PMG 0,03; error estándar 0,11), frente al 2,48 del VECM v1, que recogía sobre todo el ciclo común.
- Limitaciones: autocorrelación marginal a 4 retardos (p = 0,034), no normalidad y ARCH en el Euribor; T pequeño; series nominales dominadas por la inflación 2022–23 → solo se afirma **co-movimiento**, no causalidad.

## 3. Proyecciones 2026–2030
Escenarios base/adverso/favorable con supuestos en `data/metadata/escenarios_macro.yaml` (BCE sep-2026, Comisión Europea otoño-2026; lo no releído está marcado). Paro y PIB per cápita usan un desvío nacional como supuesto, no un modelo validado; precio, compraventas y población solo tienen escenario base. Para el precio del m² la regla elige el naive (senda plana).

**Limitaciones conocidas** (señaladas por la revisión independiente, `reports/phase2/08_debate_estadistica_economia.md`, no corregidas para no romper el protocolo pre-especificado):
1. La forma **trimestral de 2026** de la demanda es poco fiable (dummies estacionales estimadas desde 2005 y nivel de paro del escenario por encima del EPA observado: 2026Q4 queda ~11 % bajo 2025Q4, mientras el primer semestre observado es +7,0 %). Se recomienda usar totales anuales de 2027 en adelante.
2. Que el escenario base (511.106 hipotecas en 2027) coincida casi con el naive (512.520) es una **compensación de errores** (≈ +3 % por paro frente a −2,9 % por Euribor).
3. Las bandas adverso/favorable las dominan los supuestos de paro, no el Euribor; son *sensibilidades mecánicas*, no riesgo calibrado.
4. El precio plano contradice el +12,5 % interanual observado y las bandas del precio cubren solo un 32 % en el hold-out; ETS-log sería mejor a h ≥ 4 en el hold-out pero no lo elige la regla (decisión pendiente para el siguiente ciclo de selección).
5. El hold-out tiene n = 16 en un régimen atípico (subida de tipos 2022–23).
6. PIB per cápita provincial llega con retardo de 2–3 años y en escalones; las variables nacionales replicadas en el panel solo aportan ~86 observaciones independientes.
7. No existen *vintages* de la mayoría de las series: no se puede reconstruir exactamente lo disponible en cada fecha pasada (el retraso de publicación se aproxima con `availability_rules.yaml`).

## 4. Asesor hipotecario
Motor determinista: 18 vectores de prueba (`artifacts/advisor/test_vectors.json`) reproducidos por el motor Python y por la versión TypeScript de la web. Fiscalidad: 38 de 45 reglas verificadas contra el BOE; las 7 restantes figuran como no verificadas y la interfaz lo advierte. Resultado negativo documentado: el GradientBoosting de la v1 daba un error de 0,380 pp frente a 0,200 pp de usar el último dato publicado, y su R² de 0,997 (validación con filas mezcladas) caía a ≈ 0,30 con una partición temporal real.

## 5. Tests
`python -m pytest -q tests` → 179 pruebas (geografía, ingestión y validación de datos, econometría, forecasting, demanda, asesor, rutas y seguridad de la app, ausencia de marca CaixaBank y de series no autorizadas en la app). La web: `cd site && npm test` (23 pruebas).
