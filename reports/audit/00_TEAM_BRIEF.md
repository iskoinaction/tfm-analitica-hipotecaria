# Briefing común del equipo (coordinador)

Repositorio: `/home/user/tfm-analitica-hipotecaria` (TFM UFV, Máster Business Analytics/IA/ML:
"Plataforma de Analítica Avanzada del Mercado Hipotecario"). Rama de trabajo: `claude/stoic-edison-gdie8p`.
**Solo el coordinador hace git commit/push.** Los agentes NO hacen commits.

## Reglas no negociables
- No inventar datos ni cifras. Toda cifra reportada debe proceder de un cálculo ejecutado o de una fuente consultada (citar URL / id de serie).
- No maquillar métricas; no usar datos futuros en predicciones históricas; no confundir predicción y causalidad;
  no confundir fecha de referencia con fecha de publicación; no interpolar por comodidad.
- Las cifras del README son HIPÓTESIS a verificar, no hechos.
- Respetar licencias / condiciones de uso; no saltarse restricciones de acceso. No usar credenciales.
- La app actual imita la marca CaixaBank (logo, nombre, usuario por defecto). Es una entidad real: NO se debe
  conservar su marca. La marca nueva neutral y ficticia es **"Atalaya · Analítica Hipotecaria"**.
- No exponer secretos (GEMINI_API_KEY etc.). No añadir datos personales.
- Documentación y textos de usuario en **español**. Código: nombres en inglés o español, consistentes.
- Mantener los originales: NO borrar ni modificar `Datos sucios/`, `Datos ya metidos/`, `notebooks acabados/`,
  `outputs/`, `web scrapping/` (son la línea base v1 para comparaciones antes/después), salvo instrucción del coordinador.

## Hechos ya verificados por el coordinador (punto de partida, re-verifica si te afecta)
- `notebooks acabados/dataset_final_tfm.csv`: 4.368 filas = 52 provincias × 84 trimestres (2005Q1–2025Q4). 16 columnas.
  NaN: PIB_pc 208 (todo 2025), Indice_Materiales/Mano_Obra 156 (2025Q2–Q4), tasa_ahorro 52 (2025Q4).
- Variables NACIONALES replicadas en las 52 provincias (1 valor único por trimestre): Euribor, Spread_Hipotecas,
  tasa_ahorro, Indice_Materiales, Indice_Mano_Obra. IPC es autonómico (≈15–19 valores únicos/trimestre).
- Variables ANUALES repetidas idénticas en los 4 trimestres (NO interpoladas, contra lo que dice el README):
  PIB_pc, Poblacion, Edad_Media (1 valor único por provincia-año).
- `notebooks acabados/predicciones_provinciales_2026_2030.csv`: 9.568 filas (README dice 8.320 = 8 vars × 1.040).
  Real: 6 vars × 1.248 (2025Q1–2030Q4, 24 trimestres) + Poblacion y Pob_Ext × 1.040 (2026–2030).
- `outputs/prediccion_macro/*` y `outputs/preciom2/*` NO los genera ningún notebook presente (huérfanos);
  usan modelos (LightGBM para precio m², Ridge/RF para spread) distintos de lo que describe el README (Holt-Winters).
- La app Flask (`Web/app.py`, ~2.400 líneas) entrena modelos al arrancar (`Web/demanda_models.py`), lee el dataset
  y `predicciones_provinciales_2026_2030.csv`. Tiene `/admin/execute-code` y `/admin/upload-chart` que ejecutan
  código Python arbitrario vía subprocess (riesgo grave). Credenciales por defecto hardcodeadas ('caixabank').
- Scripts sueltos `Web/fix_app.py`, `patch_*.py`, `update_nav.py`, `add_doc_notebooks.py` parecen parches puntuales obsoletos.
- Notebooks: 1 (limpieza + BCE), 2 (BCE, duplica parte de 1), 3 (data joining → dataset maestro),
  4 (benchmark ML + SARIMAX + VAR/IRF), 4.1 (formalización, 1 celda de código), 4.2 (VECM),
  5 (asesor GBR+SHAP + proyecciones 2026-2030 → escribe predicciones_provinciales), 6 (pasos web).
  Los notebooks leen ficheros por nombre "pelado" (dependientes del cwd): no son reproducibles tal cual.

## Entorno
- Python 3.13 con pandas 3, numpy 2, statsmodels 0.15, scikit-learn 1.9, xgboost, lightgbm, shap, flask, matplotlib,
  scipy, plotly, openpyxl, xlrd, nbconvert ya instalados. Node 22 / npm 10 disponibles. 4 CPU, 15 GB RAM.
- Red: hay acceso a servicios.ine.es (API JSON Tempus3), data-api.ecb.europa.eu, ec.europa.eu/eurostat API,
  www.bde.es, tinsa.es, pypi. Proxy HTTPS con CA en /root/.ccr/ca-bundle.crt (requests ya funciona).
  Si algo falla por TLS/proxy, leer /root/.ccr/README.md. Nunca desactivar verificación TLS.
- Usa con moderación la CPU (otros agentes trabajan en paralelo): n_jobs<=2.

## Contrato de arquitectura objetivo (v2)
```
data/raw/<fuente>/<YYYYMMDD>/...   snapshots originales de descargas (con manifest + hash)
data/staging/                      series normalizadas por fuente (formato long, con metadatos)
data/processed/                    panel maestro v2 (panel_trimestral.parquet/csv) + panel anual si procede
data/metadata/                     catálogo de fuentes (sources.yaml), diccionario, fiscalidad con vigencias
data/forecasts/                    proyecciones 2026-2030 v2
src/common/                        config, provincias (códigos INE 01-52), utilidades de fechas, IO
src/ingestion/                     ine.py, ecb.py, eurostat.py, bde.py, vivienda.py, tinsa.py, fiscalidad.py, inclusion.py ...
src/transformations/  src/validation/  src/pipelines/ (update_all.py, build_master.py, generate_forecasts.py)
src/models/econometrics/  src/models/forecasting/  src/models/demand/  src/advisor/
artifacts/<dominio>/               resultados (JSON/CSV) que consumen la app y la web: econometrics/, forecasting/,
                                   demand/, advisor/, data_quality/
reports/audit/                     informes de auditoría de cada agente
docs/                              documentación final
Web/                               app Flask (se refactoriza in situ)
site/                              web de presentación (Vite + React)
tests/                             pytest
```
Identificador de provincia canónico: código INE de 2 dígitos (`prov_code`, "01".."52") + nombre oficial normalizado.
Trimestre canónico: `period` en formato `YYYYQn` y/o fecha de inicio de trimestre.

## Formato de entrega de cada agente
- Escribe tu informe completo en el fichero que se te indique (Markdown, español), con evidencias reproducibles
  (scripts o comandos, cifras obtenidas, rutas). Clasifica hallazgos por gravedad: CRÍTICA / ALTA / MEDIA / BAJA.
- Tu respuesta final al coordinador: resumen ≤ 450 palabras con los hallazgos clave, cifras verificadas,
  ficheros creados y decisiones que requieren arbitraje.
- Solo escribe en los ficheros/directorios que te asigne el coordinador.
