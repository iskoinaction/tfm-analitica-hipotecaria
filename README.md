# Plataforma de Analítica Avanzada del Mercado Hipotecario

**Trabajo Fin de Máster — Master en Business Analytics, IA y ML**  
Universidad Francisco de Vitoria | 2026

Panel de datos provincial español: 52 provincias · 2005–2030 · 4.368 observaciones

---

## Descripción del proyecto

Este TFM desarrolla una plataforma integral de analítica del mercado hipotecario español que combina econometría estructural, machine learning con explicabilidad y un portal web de banca digital. El sistema permite predecir la demanda hipotecaria agregada, analizar las relaciones de equilibrio a largo plazo entre las variables del mercado y ofrecer asesoramiento hipotecario personalizado a nivel provincial.

---

## Estructura del repositorio

```
TFM/
├── notebooks acabados/          # Notebooks de análisis en orden de ejecución
│   ├── 1. data_cleaning.ipynb
│   ├── 2. datos_bce.ipynb
│   ├── 3. data_joining.ipynb
│   ├── 4. econometria_y_demanda_hipotecaria.ipynb
│   ├── 4.1. formalizacion_matematica_v2.ipynb
│   ├── 4.2. vecm_hipotecas.ipynb
│   ├── 5. HIPOTECA_PERSONALIZADA_provincial.ipynb
│   ├── 6. pasos_web.ipynb
│   ├── dataset_final_tfm.csv
│   └── predicciones_provinciales_2026_2030.csv
├── Web/                         # Aplicación Flask
│   ├── app.py
│   ├── demanda_models.py
│   ├── gen_charts.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── static/
│   └── templates/
├── Datos sucios/                # Datos en bruto descargados de fuentes originales
├── Datos ya metidos/            # Datos procesados e integrados en el dataset final
├── web scrapping/               # Scripts y datos del proceso de scraping
└── outputs/                     # Gráficos y resultados exportados
```

---

## Fases del proyecto

### Fase 1 — Extracción y fuentes de datos

Se integraron 14 fuentes de datos heterogéneas para construir un panel provincial trimestral completo:

- **INE (API REST):** hipotecas por provincia, padrón municipal (población y edad media), transmisiones de propiedades, EPA (tasa de paro), IPC por CCAA, PIB per cápita provincial, índice de materiales de construcción, índice de mano de obra.
- **BCE (librería ecbdata):** TAE media de hipotecas (APRC) y Euribor 12 meses. Se calcula el spread de mercado como diferencia APRC − Euribor.
- **Tinsa (web scraping):** precios del m² por provincia mediante extracción de datos embebidos en gráficos Highcharts con expresiones regulares sobre el HTML.
- **Financialtools (scraping de app.js):** tipos de ITP, AJD y aranceles notariales y registrales por Comunidad Autónoma, parseados desde objetos JavaScript literales.
- **Ministerio de Inclusión:** datos de población extranjera por provincia para 2023–2025, fusionados con la serie histórica del INE mediante un diccionario de mapeo de variantes de nombre.

### Fase 2 — Limpieza y unificación del dataset

El notebook `3. data_joining.ipynb` construye el dataset maestro: 52 provincias × 84 trimestres = 4.368 filas. Los principales problemas técnicos resueltos fueron:

- **Estandarización de nombres de provincia:** decodificación de mojibake (latin-1 → UTF-8), eliminación de prefijos numéricos del INE y fuzzy matching para variantes ortográficas y nombres cooficiales.
- **Estandarización temporal:** todas las fuentes se normalizan a periodicidad trimestral con fecha del primer día del trimestre como estándar. Las series anuales se expanden por interpolación y las mensuales se agregan por media trimestral.
- **Fusión:** se construye una base cartesiana completa (52 provincias × todos los trimestres) y se aplican left joins sucesivos. Las variables de ámbito nacional o autonómico se expanden a nivel provincial.

Variables del dataset final: `Trimestre`, `Provincia`, `Precio_m2`, `Euribor`, `Spread_Hipotecas`, `IPC`, `Tasa_Paro`, `PIB_pc`, `tasa_ahorro`, `Hipotecas_Total`, `Indice_Materiales`, `Indice_Mano_Obra`, `Poblacion`, `Edad_Media`, `Pob_Ext`, `Transmisiones_Total`.

### Fase 3 — Análisis exploratorio y visualización

Se realizó un análisis exploratorio geoespacial con GeoPandas sobre el dataset panel:

- **Corrección de data leakage:** se crean variables con lag temporal (`_lag1`, `_lag4`) para todas las variables contemporáneas al target, evitando que el modelo acceda a información futura durante el entrenamiento. El Euribor no requiere lag por ser publicado en tiempo real por el BCE.
- **Mapa de tensión del mercado:** visualización del precio del m² en el último trimestre disponible. Las zonas de mayor presión son Madrid, Barcelona, País Vasco, Baleares y la costa mediterránea.
- **Índice de accesibilidad hipotecaria:** ratio `(PIB_pc × (1 − Tasa_Paro/100)) / Precio_m2` para cada provincia, que captura el poder adquisitivo efectivo ajustado por riesgo de desempleo.

### Fase 4 — Modelos de predicción de demanda hipotecaria

El notebook `4. econometria_y_demanda_hipotecaria.ipynb` compara cinco algoritmos de predicción de `Hipotecas_Total` con validación temporal estricta (sin aleatorización):

| Modelo | MAPE (test temporal) |
|---|---|
| Random Forest provincial agregado | ~18% |
| XGBoost | ~20% |
| LightGBM | ~22% |
| GBM sklearn | ~25% |
| ElasticNet | ~30% |
| SARIMAX | ~35% |
| **RF_Nac (modelo ganador)** | **7,11%** |

El modelo ganador (`RF_Nac`) entrena directamente sobre el agregado nacional con medias ponderadas por población de las variables provinciales, evitando la acumulación de errores del enfoque provincial. Se añaden features de momentum: variación interanual, media móvil de 4 trimestres y diferencia.

**Justificación del uso del RMSE como métrica de evaluación**

En el contexto de este proyecto, las variables objetivo son magnitudes macroeconómicas con alta varianza estructural: el volumen mensual de hipotecas formalizadas puede oscilar decenas de miles de unidades según el ciclo económico, y el precio del m² varía varios cientos de euros entre trimestres en provincias con mercados tensionados. En este entorno, el RMSE (Root Mean Squared Error) es la métrica de referencia por tres razones fundamentales.

En primer lugar, el RMSE penaliza de forma cuadrática los errores grandes, lo que resulta especialmente relevante en variables macroeconómicas donde los desvíos extremos tienen consecuencias asimétricas: una infraestimación severa de la demanda hipotecaria en un trimestre de expansión crediticia tiene un impacto operativo y de riesgo mucho mayor que un error moderado sostenido en el tiempo. Esta penalización cuadrática alinea la métrica con la función de pérdida real del negocio bancario.

En segundo lugar, el RMSE está expresado en las mismas unidades que la variable objetivo (número de hipotecas o euros/m²), lo que facilita su interpretación directa por parte de los equipos de negocio y su comparación con las tolerancias operativas reales, a diferencia del MSE cuya escala cuadrática dificulta la lectura intuitiva.

En tercer lugar, en series temporales de panel con validación temporal estricta (sin aleatorización), el RMSE se complementa con el MAPE para controlar el efecto de escala entre provincias: el MAPE permite comparar el error relativo entre Madrid (con volúmenes de hipotecas diez veces superiores a Soria) y el RMSE captura el error absoluto crítico para el modelo agregado nacional. Ambas métricas se reportan conjuntamente en el benchmarking para ofrecer una imagen completa de la capacidad predictiva.

### Fase 5 — Modelo VECM: cointegración a largo plazo

El notebook `4.2. vecm_hipotecas.ipynb` estima un Vector Error Correction Model con cinco variables para analizar las relaciones causales estructurales del mercado hipotecario español.

El test de traza de Johansen confirma `r = 1`: existe exactamente una relación de equilibrio a largo plazo. El vector de cointegración estimado, normalizado sobre `Log_Hipotecas`, es:

```
log(H*) = +0.35·log(PIB_pc) + 2.48·log(Precio_m2) − 0.10·Euribor − 1.09·log(Materiales)
```

La descomposición de la varianza (FEVD a 20 trimestres) muestra que el precio del m² explica el 53,3% de la varianza de las hipotecas y el coste de materiales de construcción el 38,8%, frente al 2,2% del Euribor. La velocidad de ajuste de las hipotecas al equilibrio es del 44% por trimestre (semivida de 1,2 trimestres), mientras que los precios son muy rígidos (0,6% por trimestre, semivida de 30 años).

### Fase 6 — Asesor hipotecario personalizado (GBR + SHAP)

El notebook `5. HIPOTECA_PERSONALIZADA_provincial.ipynb` implementa un asesor de tipo de interés en siete pasos:

1. Recepción del perfil del cliente (ingresos, ahorros, edad, provincia, año, tipo de hipoteca).
2. Carga de variables macroeconómicas del año seleccionado.
3. Cálculo de impuestos y gastos por CCAA (ITP/IVA, AJD, notaría, registro).
4. Verificación de ahorros disponibles frente a la entrada mínima requerida.
5. Predicción del tipo de interés mediante `GradientBoostingRegressor` sobre seis variables macro, con ajuste sigmoidal por perfil de ingresos basado en `tanh`.
6. Cálculo de la cuota mensual por amortización francesa y ratio DTI.
7. Decisión crediticia: aprobación automática (DTI < 35%), revisión por analista (35–45%) o denegación (> 45%).

SHAP (`TreeExplainer`) descompone la predicción variable a variable, cumpliendo los requisitos de explicabilidad del AI Act europeo. El sistema incorpora los programas de financiación especial para jóvenes de cada Comunidad Autónoma (hasta el 100% para determinadas CCAA).

### Fase 7 — Proyecciones macroeconómicas 2026–2030

Para alimentar el asesor con años futuros se proyectan las variables macro provinciales para las 52 provincias. Los resultados se almacenan en `predicciones_provinciales_2026_2030.csv` (8.320 filas en formato long). La elección del modelo para cada variable no es arbitraria: responde al análisis previo de las propiedades estocásticas de cada serie y a un protocolo de backtesting con ventana de entrenamiento 2005–2021 y test 2022–2025.

---

#### Euribor e IPC — Proyecciones institucionales del BCE

**Por qué no se modelizan.** El Euribor depende de las decisiones discrecionales del Consejo de Gobierno del BCE sobre los tipos de referencia; el IPC incorpora shocks de oferta (energía, cadenas de suministro) y tensiones geopolíticas. Ningún modelo de series temporales puede anticipar estos factores con fiabilidad: el Euribor pasó de valores negativos en 2021 a superar el 4% en 2023 en menos de 18 meses, un movimiento completamente fuera del rango de cualquier extrapolación histórica. Usar una ARIMA sobre el Euribor produciría MAPE superiores al 50% para horizontes mayores de dos años.

**Decisión.** Se utilizan directamente las Staff Projections del BCE y del FMI como escenario base: Euribor convergiendo al 2,00–2,30%; IPC convergiendo al objetivo del 2,0%.

---

#### PIB per cápita — SARIMA(1,1,0)(1,1,0)₄ por provincia

**Por qué SARIMA.** El test ADF sobre el PIB_pc nacional arroja p = 0,989 en niveles (no rechaza raíz unitaria) y p < 0,001 en primera diferencia (estacionaria): la serie es I(1). Además presenta un ciclo estacional marcado (mayor gasto en Q4 por consumo navideño). El SARIMA es el modelo canónico para series I(1) con estacionalidad: combina la diferenciación regular para eliminar la tendencia estocástica y la diferenciación estacional para eliminar el ciclo anual.

**Cómo se descompone el SARIMA(1,1,0)(1,1,0)₄.** La ecuación del modelo es:

```
Φ_1(L) · Φ_1(L⁴) · (1−L) · (1−L⁴) · Y_t = c + ε_t
```

Donde cada factor tiene un rol concreto:

| Factor | Expresión | Efecto |
|---|---|---|
| `(1−L)` | Diferencia regular | Elimina la tendencia estocástica (hace la serie I(0)) |
| `(1−L⁴)` | Diferencia estacional | Elimina el ciclo anual: ΔY_t = Y_t − Y_{t−4} |
| `Φ_1(L) = (1 − φ₁L)` | AR(1) regular | Captura la inercia trimestral del PIB |
| `Φ_1(L⁴) = (1 − Φ₁L⁴)` | AR(1) estacional | Captura la inercia año a año |

La doble diferenciación `(1−L)(1−L⁴)` es la firma del modelo: trabajar solo con `(1−L)` dejaría ciclos estacionales residuales; trabajar solo con `(1−L⁴)` no eliminaría la tendencia de crecimiento real. La combinación de ambas produce una serie estacionaria sobre la que el modelo AR estima los coeficientes de inercia.

**Guardrail CAGR.** Una vez obtenido el forecast, se aplica una restricción económica para evitar extrapolar el boom 2022–2024:

```
CAGR_cap = min(CAGR_histórico, 4%)
Ŷ_final  = min(Ŷ_SARIMA, Y_T · (1 + CAGR_cap)^años)
```

El CAGR histórico nacional (2005–2025) es del 2,24% anual, por lo que el cap del 4% no resulta activo en la mayoría de provincias pero evita extrapolaciones en las de mayor dinamismo reciente (Álava, Madrid). Resultados del backtesting: MAPE mediana de 7,2% sobre 8 trimestres de test; U de Theil mediana de 0,749 (supera al naive).

---

#### Tasa de paro — Sistema de tres niveles por provincia

La tasa de paro es la variable con mayor heterogeneidad estructural entre provincias: Baleares tiene un ciclo estacional de 15 puntos porcentuales entre verano e invierno; Extremadura tiene paro estructural del 20%; Madrid ronda el 10% con muy poca variación estacional. No existe un modelo único que funcione bien en todas. Se implementa un **sistema de tres niveles** donde cada provincia recibe el modelo que minimiza su error en backtesting.

**Protocolo de discriminación por provincia.** Para cada una de las 52 provincias se ejecuta el siguiente procedimiento:

1. Se estiman los tres modelos candidatos sobre el periodo de entrenamiento (2005Q1–2021Q4).
2. Se genera el forecast sobre el periodo de test (2022Q1–2025Q4, 16 trimestres) y se calcula el MAPE.
3. Se asigna a cada provincia el nivel de modelo con menor MAPE en test.

El periodo de test se fija deliberadamente en 2022–2025 (excluyendo el COVID) para evaluar los modelos en condiciones de mercado laboral normalizado. Incluir el periodo pandémico en el test penalizaría todos los modelos por un shock imposible de anticipar con información histórica.

**Los tres niveles:**

| Nivel | Modelo | N provincias | MAPE mediana | U₂ mediana | Criterio de asignación |
|---|---|:---:|:---:|:---:|---|
| 1 | SARIMA(1,0,0)(1,0,0)₄ + dummy COVID | 2 | 12,9% | 0,545 | Estacionalidad provincial fuerte + dummy mejora MAPE |
| 2 | ARIMA(3,1,2) + dummy COVID | 17 | 12,9% | 0,713 | Dummy mejora MAPE en backtesting |
| 3 | ARIMA(3,1,2) sin dummy | 33 | 16,9% | 1,032 | Dummy no mejora o empeora MAPE |
| **Total** | | **52** | **15,7%** | **0,944** | |

**Por qué solo 2 provincias usan SARIMA.** El SARIMA requiere que el patrón estacional sea consistente a lo largo del periodo muestral. Badajoz tiene empleo agrícola con ciclo Q3 marcado (recolecta de aceituna, tomate y fresa) que se mantiene estable 20 años. Girona tiene estacionalidad turística de verano igualmente estable. En el resto de provincias con estacionalidad turística fuerte, como Baleares, el COVID destruyó temporalmente el patrón (la amplitud del ciclo cayó de 12 a 5 puntos porcentuales en 2020–2021), lo que impide al SARIMA aprender un patrón limpio. En esos casos, el ARIMA(3,1,2) con dummy absorbe el shock COVID como un coeficiente discreto sin contaminar los parámetros de la dinámica regular.

**Por qué la dummy COVID mejora solo en 17 de 52 provincias.** La dummy absorbe el shock pandémico como un nivel adicional. En las 33 provincias donde no mejora, el COVID no dejó una huella estructural detectable en la serie de paro provincial: la variable consume un grado de libertad sin reducir el error de previsión. Forzar la dummy en esas provincias empeora el MAPE al introducir un parámetro innecesario en series con pocas observaciones (~68 trimestres de entrenamiento).

**Suelo estructural NAIRU del 8,5%.** Sobre el forecast de cualquiera de los tres modelos se aplica `np.clip(forecast, 8.5, None)`. El mínimo histórico del paro español fue el 7,95% en 2007Q2 —un outlier insostenible de la burbuja inmobiliaria—. La OCDE estima la NAIRU española post-reforma laboral de 2021 en el 9–10% para 2030. El suelo del 8,5% es coherente con el mínimo estructural bajo condiciones normales e impide que los modelos proyecten escenarios de pleno empleo que carecen de precedente histórico sostenido.

---

#### Precio del m² — Holt-Winters con amortiguación por provincia

**Por qué Holt-Winters y no ARIMA.** Los modelos ARIMA estiman sus parámetros otorgando igual peso a todas las observaciones de la muestra. Para el precio del m², cuyo régimen cambió drásticamente en 2022–2024 (rally sin precedente desde 2007), esto implica que un ARIMA aprende un nivel medio histórico que infravalora la aceleración reciente. Holt-Winters asigna pesos decrecientes hacia el pasado, priorizando la información reciente, y actualiza automáticamente su estimación del nivel y la tendencia con cada nuevo dato.

**Por qué la tendencia amortiguada.** El componente `damped_trend` introduce un parámetro φ ∈ (0,1) que frena la extrapolación de la pendiente actual conforme avanza el horizonte. Sin amortiguación, Holt-Winters extrapola el rally 2022–2024 indefinidamente, llegando a precios inverosímiles en 2030. Con φ estimado por MLE (en torno a 0,94 según el backtesting), la predicción frena la pendiente de forma automática respetando la rigidez estructural a la baja del mercado inmobiliario (*sticky prices*).

**Selección por backtesting de ventana expansiva.** Para cada provincia se comparan Holt-Winters y Seasonal Naive sobre los últimos 8 trimestres reales. Holt-Winters gana en el 79% de las provincias (MAPE mediana 2,9%; U₂ mediana 0,634). El Seasonal Naive se mantiene como benchmark: cualquier modelo con U₂ > 1 no aportaría valor sobre repetir el mismo trimestre del año anterior.

### Fase 8 — Portal web Flask

La aplicación web integra todos los modelos en un portal de banca digital con estética replicada de CaixaBank. Desarrollada en Flask (>2.200 líneas en `app.py`) con carga de modelos al arranque para minimizar la latencia de las peticiones.

**Rutas principales:**

| Ruta | Descripción |
|---|---|
| `GET /` | Dashboard con gráficos interactivos y chatbot ejecutivo |
| `GET /hipotecas` | Asesor hipotecario: GBR+SHAP, DTI, impuestos por CCAA |
| `GET /demanda` | Predicción de demanda nacional RF_Nac 2026–2030 |
| `GET /econometria` | VAR: IRF, FEVD y predicciones |
| `GET /vecm` | VECM paso a paso |
| `GET /business_case` | Business case para dirección |
| `GET /webscrapping` | Metodología de extracción de datos |
| `POST /api/hipoteca-recomendacion` | API de cálculo hipotecario (JSON) |
| `POST /api/noa-chat` | Chatbot Noa para clientes (Gemini 2.5 Flash) |
| `POST /api/noa-strategic` | Chatbot Noa Strategic para gestores (Gemini 2.5 Flash) |
| `GET/POST /admin` | Panel de administración protegido |

**Chatbots integrados:**
- **Asistente ejecutivo:** conectado a Google Search en tiempo real, con contexto del dataset filtrado por año y provincia.
- **Noa (cliente):** asesora hipotecaria que explica el tipo ofrecido a partir de las contribuciones SHAP y el perfil completo del cliente.
- **Noa Strategic (gestor):** analista de riesgos internos con acceso a métricas técnicas del modelo (RMSE_CV, MAE_CV, R², spread base GBR, income ratio).

---

## Instalación y ejecución

```bash
# 1. Instalar dependencias
pip install -r Web/requirements.txt

# 2. Crear el archivo de configuración a partir de la plantilla
cp Web/.env.example Web/.env
```

Editar `Web/.env` con los valores reales:

| Variable | Descripción | Cómo obtenerla |
|---|---|---|
| `GEMINI_API_KEY` | API key de Google Gemini (chatbots Noa y asistente ejecutivo) | Google AI Studio: aistudio.google.com |
| `FLASK_SECRET_KEY` | Clave secreta para las sesiones Flask | Cualquier cadena aleatoria segura (ej. `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `APP_USERNAME` | Usuario para acceder al portal | El que se desee |
| `APP_PASSWORD` | Contraseña para acceder al portal | La que se desee |

```bash
# 3. Arrancar la aplicación
cd Web
python app.py
# El portal queda disponible en http://localhost:8000
```

> El archivo `.env` está excluido del repositorio mediante `.gitignore` y nunca se sube a GitHub. Solo se comparte la plantilla `.env.example` sin valores reales.

---

## Tecnologías utilizadas

| Categoría | Tecnologías |
|---|---|
| Lenguaje | Python 3.x |
| Web framework | Flask, Werkzeug, Jinja2 |
| Machine Learning | scikit-learn (RF, GBR, ElasticNet), XGBoost, LightGBM, CatBoost |
| Explicabilidad | SHAP (TreeExplainer) |
| Econometría | statsmodels (VAR, VECM, ARIMA, SARIMAX, Holt-Winters) |
| Datos | pandas, numpy, scipy |
| Geoespacial | geopandas, GeoPandas + GeoJSON |
| Visualización | Chart.js, Plotly, matplotlib, seaborn |
| IA Generativa | Google Gemini 2.5 Flash (API) |
| Extracción de datos | requests, BeautifulSoup, ecbdata, regex |
| Frontend | HTML5, CSS3, JavaScript, Bootstrap |

---

## Fuentes de datos

- Instituto Nacional de Estadística (INE) — API REST
- Banco Central Europeo (BCE) — Statistical Data Warehouse via ecbdata
- Tinsa (IMIE) — web scraping de precios del m² por provincia
- Financialtools — scraping de tipos fiscales por CCAA
- Ministerio de Inclusión — datos de población extranjera 2023–2025
- Staff Projections del BCE — escenario macroeconómico base 2026–2030

---

## Autor

Trabajo desarrollado en el contexto del Master en Business Analytics, IA y ML — Universidad Francisco de Vitoria (2025–2026).  
Contacto: franbustos3@hotmail.es
