# Documentación técnica — Portal web Flask

**Aplicación:** `app.py` (2.442 líneas) + `demanda_models.py`  
**Framework:** Flask (Werkzeug WSGI) · Puerto 8000  
**Inicio:** `python app.py` desde el directorio `Web/`

Documento complementario al [README principal del repositorio](../README.md).

---

## Índice

1. [Secuencia de arranque](#1-secuencia-de-arranque)
2. [Estado global en memoria](#2-estado-global-en-memoria)
3. [Sistema de autenticación](#3-sistema-de-autenticación)
4. [Motor de proyecciones macro (_build_forecasts)](#4-motor-de-proyecciones-macro)
5. [Mapa de rutas](#5-mapa-de-rutas)
6. [API de datos del dashboard](#6-api-de-datos-del-dashboard)
7. [Mapas geoespaciales](#7-mapas-geoespaciales)
8. [Asesor hipotecario — flujo completo](#8-asesor-hipotecario)
9. [Modelo GBR + SHAP (pricing)](#9-modelo-gbr--shap)
10. [Chatbots Gemini](#10-chatbots-gemini)
11. [Panel de administración](#11-panel-de-administración)
12. [Datos de referencia embebidos](#12-datos-de-referencia-embebidos)

---

## 1. Secuencia de arranque

Cuando se ejecuta `python app.py`, Flask carga todo en memoria antes de aceptar la primera petición HTTP. El orden es el siguiente:

```
1. Carga de variables de entorno (.env)
2. Imports de ML: sklearn, shap  ← movidos al scope global para evitar
                                    deadlock en macOS con threads de Werkzeug
3. Creación de la app Flask y lectura de FLASK_SECRET_KEY
4. Resolución de DATASET_PATH  ← busca dataset_final_tfm.csv en 3 rutas posibles
5. df = pd.read_csv(DATASET_PATH)          ← dataset completo en RAM
6. df_tipos = pd.read_csv(tipos_hipotecas.csv)  ← spread histórico BCE
7. df_prov_preds = pd.read_csv(predicciones_provinciales_2026_2030.csv)
8. Inicialización de CUSTOM_CHARTS_DIR e index.json
9. Arranque de Werkzeug en puerto 8000
```

Los modelos ML (GBR, SHAP) **no se entrenan en el arranque**: se entrenan la primera vez que se llama a cada endpoint y se guardan en caché en memoria. Esto evita que el servidor tarde decenas de segundos en arrancar.

---

## 2. Estado global en memoria

La aplicación mantiene varios objetos globales que persisten entre peticiones:

| Variable | Tipo | Contenido | Se rellena en |
|---|---|---|---|
| `df` | DataFrame | Dataset completo (4.368 filas × 16 cols) | Arranque |
| `df_tipos` | DataFrame | Euribor, APRC, spread histórico mensual | Arranque |
| `df_prov_preds` | DataFrame | Proyecciones 2026–2030 por provincia (formato long) | Arranque |
| `_MACRO_FORECASTS` | dict | Forecasts nacionales por variable y año | Primera llamada a `_build_forecasts()` |
| `_PRICING_MODEL_CACHE` | dict | GBR + SHAP por año de entrenamiento | Primera llamada a `/api/hipoteca-recomendacion` |
| `_DEMANDA_CACHE` | dict | Resultado completo de `/api/demanda-data` sin filtros | Primera llamada a `/api/demanda-data` |
| `_GEOJSON_CACHE` | GeoDataFrame | GeoJSON de provincias españolas | Primera llamada a `/api/mapa/<tipo>` |
| `_CORR_IMG_CACHE` | str | Matriz de correlación en base64 (PNG) | Primera llamada a `/api/hipoteca-context` |

Todos los cachés tienen alcance de proceso (se pierden al reiniciar el servidor). No hay base de datos ni persistencia entre reinicios, excepto los ficheros CSV y los gráficos en `static/custom_charts/`.

---

## 3. Sistema de autenticación

Todas las rutas están protegidas por un `before_request` global:

```python
@app.before_request
def require_login():
    if request.endpoint in _PUBLIC_ENDPOINTS:   # login, logout, static
        return
    if request.endpoint in ('admin', 'upload_chart', 'delete_custom_chart'):
        if not session.get('admin'):
            return redirect(url_for('login_admin'))
        return
    if not (session.get('user') or session.get('admin')):
        return redirect(url_for('login'))
```

Hay dos niveles de sesión:

| Nivel | Cookie de sesión | Acceso |
|---|---|---|
| **Usuario** | `session['user'] = True` | Todas las páginas y APIs (excepto admin) |
| **Admin** | `session['admin'] = True` | Todo lo anterior + panel admin + ejecución de código |

Las credenciales se leen de las variables de entorno `APP_USERNAME` y `APP_PASSWORD` (definidas en `.env`). El login de usuario y el de admin usan las mismas credenciales pero crean cookies de sesión distintas con permisos distintos.

Las sesiones Flask son cookies firmadas con `FLASK_SECRET_KEY`. Si la clave cambia, todas las sesiones activas quedan invalidadas.

---

## 4. Motor de proyecciones macro

`_build_forecasts()` es la función central que genera todas las proyecciones macroeconómicas nacionales 2026–2031. Se llama de forma lazy (solo cuando se necesita) y guarda el resultado en `_MACRO_FORECASTS`. Si ya está relleno, retorna inmediatamente.

```
_build_forecasts()
│
├── PIB_pc      → SARIMA(1,1,0)(1,1,0)4  ← statsmodels SARIMAX
├── Tasa_Paro   → Auto-ARIMA (grid AIC sobre p∈[0-3], d∈[0-1], q∈[0-2])
│                 + np.clip(forecast, 8.5, None)   ← suelo NAIRU
├── Precio_m2   → Seasonal Naive + tendencia lineal
│                 (media de tendencia sobre últimos 8 trimestres)
├── tasa_ahorro → Auto-ARIMA (mismo grid)
├── Transmisiones_Total → Seasonal Naive + tendencia
│                         (excluye último trimestre anómalo)
├── Euribor     → Escenarios BCE hardcoded:
│                 {2026: 2.00, 2027: 2.10, 2028: 2.30, 2029: 2.15, 2030: 2.15}
├── IPC         → Escenarios BCE hardcoded:
│                 {2026: 1.88, 2027: 2.10, 2028-2031: 2.00}
└── Diferencia  → SARIMAX(1,1,1) sobre la serie histórica de spreads
```

El resultado se agrega de trimestral a anual (media de los 4 trimestres) y se guarda en `_MACRO_FORECASTS[variable][año]`.

Para los años futuros en el asesor hipotecario, la jerarquía de fuentes es:

```
1. CSV provincial (df_prov_preds) si hay datos para esa provincia y año
2. Fallback: _MACRO_FORECASTS[variable][año] (media nacional)
3. Fallback final: _MACRO_FORECASTS[variable]['last_real'] (último valor real)
```

Para el PIB_pc provincial en 2025, hay un caso especial: el INE no publica datos provinciales hasta mediados del año siguiente. En ese caso, se hace un forward-fill desde el último valor real provincial conocido (`_get_last_provincial_pib(province)`), evitando caer en la media nacional que sería incorrecta para provincias con PIB per cápita muy distinto (Madrid ~44.000 €, Extremadura ~19.000 €).

---

## 5. Mapa de rutas

### Páginas HTML (GET)

| Ruta | Template | Descripción |
|---|---|---|
| `GET /` | `index.html` | Dashboard principal con gráficos Chart.js y chatbot ejecutivo |
| `GET /hipotecas` | `hipotecas.html` | Asesor hipotecario completo (GBR + SHAP + DTI) |
| `GET /demanda` | `demanda.html` | Predicción de demanda nacional RF_Nac |
| `GET /demanda-provincial` | `demanda_provincial.html` | Predicción de demanda por provincia |
| `GET /hipotecas-provincial` | `hipotecas_provincial.html` | Vista provincial del asesor |
| `GET /econometria` | `econometria.html` | VAR: IRF, FEVD y predicciones |
| `GET /vecm` | `vecm.html` | VECM paso a paso |
| `GET /metodologia-ml` | `metodologia_ml.html` | Metodología de ML |
| `GET /business_case` | `business_case.html` | Business case para dirección |
| `GET /webscrapping` | `webscrapping.html` | Metodología de extracción de datos |
| `GET/POST /admin` | `admin.html` | Panel de administración (requiere `session['admin']`) |
| `GET/POST /login` | `login.html` | Login de usuario |
| `GET/POST /login_admin` | `login_admin.html` | Login de administrador |
| `GET /logout` | — | Limpia sesión y redirige a login |

### APIs JSON

| Ruta | Método | Descripción |
|---|---|---|
| `/api/data` | GET | Datos del dashboard (barras, líneas, hipotecas nacionales, top provincias) |
| `/api/dashboard-extra` | GET | Series temporales adicionales (precio m², PIB, paro, scatter) |
| `/api/hipoteca-context` | GET | Variables macro del año/provincia seleccionado para el asesor |
| `/api/hipoteca-recomendacion` | POST | Cálculo completo de hipoteca (tipo, cuota, DTI, impuestos, SHAP) |
| `/api/demanda-data` | GET | Predicción de demanda hipotecaria (RF_Nac + provincial) |
| `/api/mapa/<tipo>` | GET | Genera mapa PNG con GeoPandas (`tension`, `accesibilidad`, `mina_oro`) |
| `/api/paro-model-info` | GET | Modelo de paro asignado por provincia (nivel 1/2/3) |
| `/api/chat` | POST | Chatbot ejecutivo Gemini 2.5 Flash con Google Search |
| `/api/noa-chat` | POST | Chatbot Noa (cliente) — explicación personalizada de la hipoteca |
| `/api/noa-strategic` | POST | Chatbot Noa Strategic (gestor) — análisis de riesgo técnico |
| `/api/custom-charts` | GET | Listado de gráficos publicados en el admin |
| `/api/custom-charts/<id>` | DELETE | Elimina un gráfico publicado (requiere admin) |
| `/admin/upload-chart` | POST | Sube notebook/script Python y publica sus gráficos |
| `/admin/execute-code` | POST | Ejecuta código Python en el servidor y publica gráficos |

---

## 6. API de datos del dashboard

`GET /api/data` es el endpoint central del dashboard. Acepta los parámetros `year_from`, `year_to` y `specific_year`. Su flujo interno:

```
1. Copia df en fdf
2. Intenta inyectar predicciones futuras:
   - Llama a demanda_models._train_artifacts() para obtener Hipotecas_Total predichas
   - Hace merge de df_prov_preds con las predicciones de hipotecas por trimestre/provincia
   - Concatena fdf con los datos futuros → fdf incluye 2005-2030
3. Filtra fdf por year_from/year_to si se indica
4. Calcula y devuelve:
   - barData: top 20 provincias por precio m² medio
   - timeSeries: Euribor y spread histórico por trimestre
   - macroSeries: Tasa_Paro e IPC agrupados por año
   - hipotecasNac: serie temporal de hipotecas totales (suma nacional)
   - topProvHip: top 10 provincias por volumen de hipotecas, por año
   - availableYears: lista de años disponibles (2005-2030)
```

`GET /api/hipoteca-context` devuelve el contexto macro para un año y provincia concretos. La lógica de inyección de forecasts sigue la jerarquía de tres niveles descrita en la sección anterior. También genera y cachea la matriz de correlación como imagen PNG en base64.

---

## 7. Mapas geoespaciales

`GET /api/mapa/<tipo>` genera mapas coropléticos con GeoPandas + matplotlib. El GeoJSON de provincias se carga desde `static/spain-provinces.geojson` (o se descarga de GitHub la primera vez) y se cachea en `_GEOJSON_CACHE`. Los nombres de provincia del GeoJSON se normalizan para hacer merge con el dataset mediante un diccionario de alias.

Los mapas se persisten en disco como archivos `.b64` en `static/` tras la primera generación, de modo que las siguientes peticiones los sirven sin recalcular. El caché en disco se invalida al reiniciar el servidor (los archivos persisten, pero se regeneran si se borran manualmente).

| Tipo | Variable mapeada | Método de cálculo |
|---|---|---|
| `tension` | `Precio_m2` | Media del último trimestre disponible por provincia |
| `accesibilidad` | `(PIB_pc × (1 − Tasa_Paro/100)) / Precio_m2` | Índice compuesto, último trimestre |
| `mina_oro` | Score bancario (0-100) | Random Forest sobre features con lag → predicción hipotecas → score ponderado por Precio_m2 / Tasa_Paro |

El mapa `mina_oro` entrena un Random Forest localmente dentro de la petición (100 árboles, sin caché) y proyecta con Euribor fijo a 2.5% para simular un escenario de estabilización monetaria.

---

## 8. Asesor hipotecario

`POST /api/hipoteca-recomendacion` es el endpoint más complejo de la aplicación. Recibe un JSON con el perfil del cliente y ejecuta el siguiente flujo en orden estricto:

```
Inputs: year, tipo (variable/fijo), income, savings, age,
        province, other_debts, price_mode, custom_price, tenure_years

1. _build_forecasts()  ← asegura que _MACRO_FORECASTS está relleno

2. Carga macro del año seleccionado:
   - Datos históricos de df si year ≤ 2025
   - Predicciones de df_prov_preds si year ∈ 2026-2030
   - Fallbacks por jerarquía: CSV provincial → SARIMA nacional → last_real

3. Tipos de interés:
   - Histórico: _get_tipos_for_year(year) desde df_tipos
   - Futuro: _get_tipos_proyectados() usando SARIMAX del spread + escenarios BCE

4. Precio del m²:
   - Filtra por provincia y año en df
   - Si es futuro: usa _MACRO_FORECASTS['Precio_m2'][year]
   - Precio estimado vivienda = precio_m2 × 80 m² (o custom_price si price_mode='manual')

5. CCAA y financiación joven:
   - _get_ccaa(province) → diccionario PROVINCE_TO_CCAA con fuzzy matching
   - YOUNG_FINANCING[ccaa] → (max_pct, age_limit)
   - Si age ≤ age_limit: max_financing_pct = young_max_pct (hasta 100% en algunas CCAA)
   - Si no: max_financing_pct = 80%

6. Impuestos y gastos → _calc_taxes(precio, ccaa, age, is_new_build):
   - Segunda mano: ITP (tipo general o reducido joven según edad) + notaría + registro
   - Obra nueva: IVA (10%) + AJD por CCAA + notaría + registro
   - effective_savings = savings - total_taxes

7. Plazo:
   - requested_years del cliente
   - max_by_age = min(30, max(5, 75 - age))   ← límite de vencimiento a los 75 años
   - tenure_years = min(requested_years, max_by_age)

8. Tipo de interés base:
   - Variable: euribor + diferencia (con suelo del spread > 0)
   - Fijo: aprc + 0.50% de prima de fijo
   - Recargo de +0.75% si precio < 100.000 € (operaciones pequeñas, mayor riesgo)

9. Cuota mensual (amortización francesa):
   C = L × r(1+r)^n / ((1+r)^n - 1)
   donde L = loan_amount, r = tipo_mensual, n = tenure_years × 12

10. DTI:
    dti = (cuota_mensual + other_debts) / income × 100
    < 35%  → APROBADA automáticamente
    35-45% → ANALISTA DE RIESGOS
    > 45%  → DENEGADA

11. Modelo ML de pricing óptimo:
    _train_ml_pricing_model(year) → GBR + SHAP
    _compute_ml_optimal_rate()   → tipo alternativo con explicabilidad SHAP

12. Modelo de paro por provincia:
    _get_paro_model_info(province) → nivel 1, 2 o 3 (SARIMA/ARIMA/sin dummy)

13. Respuesta JSON con todos los campos para el frontend
```

### Cálculo de impuestos — `_calc_taxes()`

```
Vivienda segunda mano:
  ITP = precio × itp_rate / 100
  itp_rate = ITP_JOVEN[ccaa] si age ≤ 35, else ITP_POR_CCAA[ccaa]
  Notaría + registro: escala por tramos de precio (brackets: 25k-400k)
  Total = ITP + notaría + registro

Vivienda nueva:
  IVA = precio × 10%
  AJD = precio × AJD_POR_CCAA[ccaa] / 100
  Total = IVA + AJD + notaría + registro
```

### Ajuste por perfil de ingresos — `_calc_income_adjustment()`

El tipo final incorpora un ajuste continuo no lineal basado en el `income_ratio` del cliente:

```python
income_ratio = (income_mensual × 12) / PIB_pc_provincial
x = (income_ratio - 1.0) × 2.0
adj = -0.25 × tanh(x)
# income_ratio = 1.0 → adj = 0   (ingresos = PIB_pc provincial → tipo base)
# income_ratio > 1.5 → adj ≈ -0.25% (bonificación)
# income_ratio < 0.5 → adj ≈ +0.25% (penalización) + recargo adicional de 0.05%
```

---

## 9. Modelo GBR + SHAP

`_train_ml_pricing_model(year)` entrena un `GradientBoostingRegressor` sobre el spread histórico. El resultado se guarda en `_PRICING_MODEL_CACHE[year]` para no reentrenar en cada petición.

**Features:** `['Euribor', 'IPC', 'Tasa_Paro', 'Precio_m2', 'PIB_pc', 'tasa_ahorro']`  
**Target:** `Spread_Hipotecas`  
**Hiperparámetros:** `n_estimators=100, max_depth=3, learning_rate=0.06, min_samples_leaf=5`

El proceso de entrenamiento y evaluación:

```
1. Filtra df a las filas con las 6 features + Spread_Hipotecas sin NaN
2. StandardScaler sobre X
3. Entrena GBR sobre X_s (escalado), y
4. r2_train = R² sobre training (referencia, no es validación real)
5. Validación temporal: TimeSeriesSplit(n_splits=5) + Pipeline(scaler, GBR)
   → RMSE_CV y MAE_CV reales (sin data leakage temporal)
6. SHAP TreeExplainer sobre el modelo entrenado
```

`_compute_ml_optimal_rate()` usa el modelo entrenado para calcular el tipo alternativo:

```
1. Predice ml_spread_base = GBR(macro_vals escalados)
2. Calcula shap_values para cada feature → lista de contribuciones ordenadas por |shap|
3. Aplica income_adjustment → ml_spread_final
4. Variable: ml_rate = euribor + ml_spread_final
   Fijo:     ml_rate = aprc + income_adjustment + 0.50
5. Devuelve ml_rate, shap_contributions, income_ratio, expected_value
```

Las contribuciones SHAP se presentan como "X variable sube/baja tu tipo en Y puntos porcentuales", cumpliendo el artículo 13 del AI Act europeo sobre explicabilidad de sistemas de IA de alto riesgo.

---

## 10. Chatbots Gemini

La aplicación integra tres chatbots, todos usando `gemini-2.5-flash` a través del SDK `google-genai`:

### Asistente ejecutivo (`POST /api/chat`)

Diseñado para directivos. Antes de llamar a Gemini, construye el contexto:

```
1. Extrae años y provincias mencionados en el mensaje (regex)
2. Filtra df y df_tipos a esas fechas/provincias
3. Toma una muestra de 5 filas de cada subset
4. Inyecta en el prompt: datos del dataset, rango temporal, precio m² histórico medio,
   resumen del análisis VECM (β, FEVD, α)
5. Activa Google Search (grounding) para consultas de datos actuales
6. Extrae y formatea las fuentes consultadas desde grounding_metadata
```

### Chatbot Noa — cliente (`POST /api/noa-chat`)

Explica la hipoteca al cliente en lenguaje accesible. El contexto inyectado incluye el perfil completo del cliente: ingresos, DTI, tipo de interés ofrecido, contribuciones SHAP individuales y la decisión crediticia. Noa usa esa información para explicar "por qué tu tipo es X%" en términos que el cliente comprende.

### Chatbot Noa Strategic — gestor (`POST /api/noa-strategic`)

Versión para el gestor bancario con contexto técnico extendido: RMSE_CV, MAE_CV, R² del modelo, `spread_base_GBR`, `income_ratio`, nivel del modelo de paro de la provincia. Proporciona argumentos de venta y análisis de riesgo técnico del perfil.

---

## 11. Panel de administración

El panel admin (`GET/POST /admin`, protegido por `session['admin']`) permite:

- **Subir `dataset_final_tfm.csv`:** recarga `df` en memoria sin reiniciar el servidor.
- **Subir `tipos_hipotecas.csv`:** recarga `df_tipos` con los nuevos datos de spread.
- **Subir gráficos:** acepta `.ipynb` o `.py`. Si es un notebook, lo convierte a script con `nbconvert` antes de ejecutarlo.
- **Ejecutar código Python:** editor de código en el navegador que ejecuta el script en un proceso hijo aislado (`subprocess.run`) y captura los gráficos resultantes.

### Flujo de publicación de gráficos

```
Admin sube notebook/script o ejecuta código
         ↓
subprocess.run([python, wrapper_script.py], timeout=120s)
         ↓
El script puede usar publish_chart(chartjs_dict) → imprime "CHARTJS_DATA:{json}"
Si no lo usa → matplotlib captura todas las figuras abiertas → guarda PNG en custom_charts/
         ↓
_process_chart_output() parsea stdout:
  - "CHARTJS_DATA:" → gráfico interactivo Chart.js
  - "CHART_IDS:"    → PNG estático
         ↓
Escribe entrada en static/custom_charts/index.json
         ↓
GET /api/custom-charts → frontend los renderiza en el dashboard
```

El estilo CaixaBank (`_CAIXABANK_STYLE`) se inyecta automáticamente antes de cualquier script ejecutado desde el admin: configura la paleta de colores `#007BC0, #FF6600, #003F6C...`, tipografía Open Sans y rejilla estilo corporativo.

---

## 12. Datos de referencia embebidos

Los siguientes datos están hardcodeados en `app.py` como diccionarios Python (extraídos originalmente por web scraping de Financialtools):

| Diccionario | Contenido | Filas |
|---|---|---|
| `PROVINCE_TO_CCAA` | Mapeo provincia → CCAA | 52 provincias |
| `ITP_POR_CCAA` | Tipo general ITP por CCAA (4%–10%) | 19 CCAA |
| `ITP_JOVEN` | Tipo reducido ITP para compradores ≤35 años | 19 CCAA |
| `AJD_POR_CCAA` | Actos Jurídicos Documentados por CCAA (0.5%–1.5%) | 19 CCAA |
| `YOUNG_FINANCING` | Financiación máxima joven por CCAA: `{ccaa: (pct, age_limit)}` | 19 CCAA |
| `PROV_SARIMA_DUMMY` | Provincias nivel 1 con orden SARIMA específico | 2 provincias |
| `PROV_ARIMA_DUMMY` | Provincias nivel 2 (ARIMA + dummy COVID) | 17 provincias |

La función `_notaria_registro(precio)` calcula los aranceles notariales y registrales por tramos de precio (25k, 50k, 100k, 150k, 200k, 250k, 300k, 400k+ €) con valores fijos extraídos del Real Decreto 1426/1989 de aranceles notariales.
