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

Para alimentar el asesor con años futuros se proyectan las variables macro provinciales:

- **Euribor e IPC:** se usan las Staff Projections del BCE (convergencia al 2,00–2,30% y al objetivo del 2,0%) en lugar de modelos de series temporales, cuya capacidad predictiva a más de dos años es limitada para estas variables.
- **PIB per cápita:** SARIMA(1,1,0)(1,1,0)₄ por provincia.
- **Tasa de paro:** sistema de tres niveles seleccionado por criterio AIC (SARIMA con dummy COVID, ARIMA(3,1,2) con dummy, ARIMA(3,1,2) sin dummy), con un suelo estructural del 8,5% basado en la NAIRU española estimada por la OCDE.
- **Precio del m²:** Holt-Winters con selección por backtesting de ventana expansiva sobre los últimos 8 trimestres.

Los resultados se almacenan en `predicciones_provinciales_2026_2030.csv` (8.320 filas en formato long).

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
