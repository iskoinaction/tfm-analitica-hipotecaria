# Fase 2 · 01 Econometría v2 (VAR/VECM, IRF/FEVD, ARDL, panel)

Reproducir: `python -m src.models.econometrics.run` (≈40 s, semilla 20240521, hilos ≤ 2) y
`python -m pytest -q tests/test_econometrics*.py` (13 pruebas). Salidas: `artifacts/econometrics/`
(`econometrics_v2.json`, `unit_root.csv`, `irf_hipotecas.csv`, `fevd_hipotecas.csv`, `beta_recursivo.csv`, `irf_VAR_diferencias.png`, `irf_VECM.png`).
Todas las cifras de este informe salen de `econometrics_v2.json`.

## 0. Conclusión

- **No hay evidencia robusta de cointegración.** Johansen con bootstrap salvaje (CRT, B = 999): p(r=0) = **0,168** > 0,10
  (traza 82,81 frente a VC asintótico 69,82; Reinsel-Ahn 67,85 < 69,82; máx. autovalor 32,40 < 33,88). Engle-Granger 5 variables: τ = −2,91, p = 0,63.
- Por la regla del coordinador, el **modelo principal es el VAR en diferencias** (p = 2, constante, dummies estacionales Q2-Q4 e impulsos 2020Q2-Q3).
  El VECM (r = 1) se conserva como **sensibilidad**, presentado como relación de forma reducida, sin causalidad ni "cointegración genuina".
- Los resultados dependen de la especificación: con k+1 = 3 retardos el bootstrap rechaza (p = 0,024) y con precio IPV p = 0,086. La evidencia es frágil, no ausente.

## 1. Datos (sin ffill ni imputación)

`data/processed/nacional_trimestral.csv` (v2). Sistema de 5 variables, **2005Q1–2026Q2, T = 86, T efectiva = 83**, todos los trimestres observados (la función falla si hay huecos):
log hipotecas sobre viviendas (INE), **log precio MIVAU valor tasado (principal)**, log PIB per cápita (CNTR nominal CVEC / población ECP), Euríbor 12m, log índice de coste de construcción (Eurostat).
Robustez: precio Tinsa ponderado (2005Q1–2025Q4), IPV INE (desde 2007Q1), hipotecas total fincas.

## 2. Problema → evidencia → solución → justificación

| Problema (auditoría) | Evidencia v1 | Solución v2 | Justificación |
|---|---|---|---|
| Datos con arrastre (ffill 2025), medias simples, PIB anual en escalón | 4 de 84 obs. inventadas; 76 % de ΔlogPIB = 0 | Solo trimestres observados; PIB trimestral CNTR / población; precio MIVAU | Evita que 4 puntos imputados muevan α y FEVD |
| Sin estacionalidad | F dummies = 10,0 (p < 0,001) | Dummies Q2-Q4 + impulsos COVID 2020Q2-Q3 | Residuo de hipotecas con picos 2013Q2 (z = −2,3), 2019Q4 |
| Cointegración asumida por Johansen asintótico, T pequeño | traza 92,89 > 69,82, r = 1 | Bootstrap salvaje B = 999 + Reinsel-Ahn + máx. autovalor + EG; k elegido por ausencia de autocorrelación (LM h1, h4) | k = 1 deja LM h1 p = 0,03; con k = 2 p = 0,055/0,24; k = 3 p = 0,58/0,53 |
| ECT "estacionario" falso | ADF p = 0,204 (v1) | No se usa el ADF del ECT como prueba (VC no válidos para residuo estimado; v2 da p = 0,017 solo descriptivo; EG p = 0,63) | Honestidad inferencial |
| FEVD puntual dependiente del orden | 53,3/38,8/2,2 % | Cholesky + rango en 120 ordenaciones + GFEVD + bandas bootstrap 90 % (B = 499) | Ver §4 |
| α/β mal emparejados, interpretación "demanda" | α = −0,44 | β y α normalizados en hipotecas y precio, contrastes LR (exclusión, exogeneidad débil, homogeneidad) | Forma reducida, no estructural |
| Sin raíces unitarias robustas | precio casi I(2) | ADF (AIC/BIC), DF-GLS, PP, KPSS, Zivot-Andrews en nivel/Δ/Δ² (`unit_root.csv`) | Ver §3 |

## 3. Raíces unitarias (p-valores, `unit_root.csv`)

Todas las series se clasifican I(1). Matices: precio MIVAU Δ ADF p = 0,213 y KPSS(Δ) p = 0,050; hipotecas Δ ADF p = 0,059 y KPSS(Δ) p = 0,037
(estacionalidad/rupturas; ZA hipotecas p = 0,014). Esto debilita los contrastes de Johansen I(1) y es otra razón para no basar el modelo principal en el VECM.

## 4. Resultados (principal: VAR en diferencias; sensibilidad: VECM)

**VAR diferencias** (T = 83, raíz máx. 0,84, estable). LM h1 p = 0,115, LM h4 p = 0,034 (autocorrelación residual marginal a h = 4); no normalidad (p < 0,001) y ARCH en Euríbor, por lo que la inferencia usa bootstrap.
FEVD de log hipotecas a h = 20 (%), orden materiales→Euríbor→PIB→precio→hipotecas:

| Shock | Cholesky | GFEVD | Rango 120 ordenaciones (mín/med/máx) | IC 90 % bootstrap (Cholesky) |
|---|---|---|---|---|
| Coste construcción | 16,2 | 14,6 | 12,2 / 15,5 / 20,3 | [0,7; 39,4] |
| Euríbor | 4,6 | 7,3 | 4,6 / 10,2 / 16,5 | [0,4; 28,1] |
| PIB pc | 18,3 | 11,1 | 0,3 / 3,9 / 18,3 | [3,7; 38,3] |
| Precio MIVAU | 4,4 | 11,7 | 4,4 / 7,7 / 14,4 | [0,2; 19,4] |
| Propio | 56,5 | 55,3 | 50,1 / 56,6 / 70,1 | [30,8; 72,1] |

IRF en nivel (log-puntos por shock de 1 d.t., h = 20), Cholesky [banda 5-95 %]: coste −0,064 [−0,102; −0,001]; Euríbor −0,028 [−0,070; 0,021]; PIB +0,054 [0,006; 0,088]; precio +0,033 [−0,020; 0,071] (GIRF 0,052 [−0,008; 0,094]).
Solo coste de construcción y PIB tienen banda que excluye 0; Euríbor y precio no.

**VECM (sensibilidad), r = 1, k = 2, caso 3**: β (log H = …) PIB +4,72 (p < 0,001), precio +1,45 (p = 0,016), Euríbor +0,125 (p < 0,001; signo contrario al esperado, +13,3 % por pp), coste −5,66 (p < 0,001).
α_hipotecas = +0,045 (p = 0,42; no corrige), α_precio = +0,002 (p = 0,68); exogeneidad débil: hipotecas p = 0,55, precio p = 0,76, Euríbor p = 0,0005. Homogeneidad nominal no rechazada (p = 0,49).
β recursivo/móvil muy inestable (precio entre −190 y +185). Con α de signo incorrecto la "semivida" no es interpretable. Normalizado en precio: β hipotecas = 0,69 (p < 0,001).
Tratar como descripción de co-movimiento, no como curva de demanda.

**ARDL-bounds** (PSS caso 3): dep. hipotecas F = 3,38 (VC 5 % I(1) = 3,79; p_I1 = 0,095) → **no rechaza al 5 %**; dep. precio F = 4,41 (p_I1 = 0,017) → rechaza, pero supone regresores débilmente exógenos (Euríbor lo rechaza).

**Panel** (N = 44 provincias con serie completa, T = 86; excluidas 8 por huecos, sin imputar): CD de Pesaran Δlog H = 112,6 (ρ̄ = 0,40), Δlog P = 125,4: fuerte dependencia transversal.
FE en niveles + Driscoll-Kraay: precio 1,70 (se 0,26) pero residuos con CD = 193 (riesgo espurio); FE en diferencias + DK: precio 0,685 (p = 0,011), PIB n.s. PMG bruto θ_precio 1,75 (se 0,30), Hausman p = 0,82.
PMG/MG centrado transversalmente: θ_precio = 0,03 (se 0,11) / 0,16 (se 0,18), no significativo. La elasticidad provincial neta del ciclo común es ≈ 0; la nacional recoge el ciclo común.

## 5. Antes / después

| Concepto | v1 documentado | v2 ejecutado |
|---|---|---|
| β PIB / precio / Euríbor / materiales | +0,35 / +2,48 / −0,10 / −1,09 | +4,72 / +1,45 / +0,125 / −5,66 (VECM sensibilidad; inestable) |
| Rango | r = 1 (traza 92,89 > 69,82) | traza 82,81 (VC 69,82); p_boot = 0,168 → r = 0 |
| Modelo principal | VECM | VAR en diferencias (p = 2) |
| α hipotecas | −0,44 (44 %/trim) | +0,045 (p = 0,42), no corrige |
| FEVD(20) precio / materiales / Euríbor | 53,3 / 38,8 / 2,2 % | 4,4 / 16,2 / 4,6 % (Cholesky); GFEVD 11,7 / 14,6 / 7,3 %; rango Euríbor 4,6–16,5 % |
| Propio / ajuste "44 %" | 3,0 % propio | 56,5 % propio; sin ajuste del 44 % |

## 6. Validación

13 pruebas (Johansen = statsmodels, recuperación de β, bootstrap, FEVD filas = 1 e invariancia, panel simulado, regla de decisión, datos sin huecos, batería ADF/KPSS/ZA, ejecución rápida).
Límites: T = 83; no normalidad y ARCH; autocorrelación marginal a h = 4 en el VAR; IRF/FEVD no prueban causalidad.

## 7. Cifras a sustituir en README/app

1. "Cointegración r = 1 / traza 92,89" → traza 82,81 (VC 69,82), p_boot = 0,168: sin cointegración robusta; VECM solo sensibilidad.
2. β +0,35/+2,48/−0,10/−1,09 → +4,72/+1,45/+0,125/−5,66 (sensibilidad, inestables) y retirar "elasticidad de demanda".
3. α = −0,44, "44 %", semivida 1,2 trim → α = +0,045 (n.s.); retirar la semivida.
4. FEVD 53,3/38,8/2,2 % y "el Euríbor explica solo el 2 %" → tabla §4 (Euríbor 4,6–16,5 % según orden; GFEVD 7,3 %).
5. Retirar "ECT estacionario / cointegración genuina" y "causalidad PIB → hipotecas".
6. Muestra "84 obs. 2005-2025 con ffill" → 2005Q1–2026Q2, T = 86 (efectiva 83), sin imputación; precio MIVAU principal.
7. Panel: sustituir cifras v1 por §4 (N = 44, CD = 112,6; elasticidad centrada ≈ 0).
