# 07 · Auditoría de Software: app Flask v1 (`Web/`)

**Agente:** arquitecto de Software (Python/Flask, APIs, seguridad, testing, rendimiento)
**Fecha:** 2026-11-21 · **Rama:** `claude/stoic-edison-gdie8p` · **Alcance:** solo lectura de `Web/`; todas las pruebas dinámicas se hicieron sobre una **copia sandbox** (scratchpad) para no tocar el repositorio.

---

## 0. Resumen ejecutivo

| # | Hallazgo | Gravedad | Evidencia |
|---|---|---|---|
| S1 | `/admin/execute-code` y `/admin/upload-chart` ejecutan **código Python arbitrario** (subprocess, mismo usuario y entorno del servidor, con acceso a `FLASK_SECRET_KEY`/`GEMINI_API_KEY`) | **CRÍTICA** | `smoke_audit.py`: `RCE_PROOF uid=0`, secreto visible = `true` |
| S2 | `secret_key` por defecto hardcodeada (`tfm_secret_key_fixed_12345`): se puede **forjar una cookie `{'admin': True}` sin credenciales** y llegar a S1 | **CRÍTICA** | `forge_session_demo.py`: prueba ejecutada = `True`, `GET /admin` → 200 |
| S3 | Credenciales por defecto `caixabank`/`caixabank` (usuario = contraseña = marca real) y **las mismas para usuario y admin**: todo usuario es admin | **CRÍTICA** | `/login_admin` con credenciales de usuario → 302 `/admin` |
| S4 | Subida de CSV en `/admin` sin `secure_filename`: **path traversal**/escritura fuera de `UPLOAD_FOLDER` (= `abspath('..')` relativo al **cwd**) y sobrescritura de datos | ALTA | `../pt_probe.csv` escrito fuera de la carpeta (sandbox) |
| S5 | **XSS** almacenado y reflejado: títulos de gráficos y respuestas del LLM se insertan con `innerHTML`; no hay CSP | ALTA | `static_scan.sh` §2 |
| S6–S8 | Sin CSRF, **open redirect** en `?next=`, sin rate limiting en Gemini (con Google Search activado), envío de datos financieros personales a un tercero | ALTA | §4 |
| F1 | **El asesor hipotecario (`POST /api/hipoteca-recomendacion`) devuelve 500 siempre** con las versiones actuales (shap 0.54.1): dependencias sin fijar y ningún test | ALTA | 4/4 llamadas → 500 `TypeError` |
| F2 | `_get_ccaa` no resuelve **12 de las 52 provincias** (tildes): ITP por defecto 8 % y sin financiación joven para Málaga, Cádiz, A Coruña… | ALTA | `check_province_mappings.py` |
| F3 | La "CV temporal" del GBR de pricing **no es temporal** (split por bloques de provincias; objetivo nacional replicado) y el modelo ignora el año pedido (usa datos futuros) | ALTA | §5 |
| F4 | Métricas **hardcodeadas** que contradicen las calculadas: R² 0,8492 / RMSE 0,1543 / MAPE 3,2 % fijos en la API; "MAPE 7,11 %" en plantillas frente al 6,3 % calculado | ALTA | §6 |
| A1 | Monolito de 2.442 líneas, estado global mutable, **entrenamiento de modelos dentro de las peticiones** con un servidor `threaded=False`: una petición fría bloquea a todos los usuarios entre 23 y 42 s | ALTA | `serve_probe.sh` |
| B1 | Marca CaixaBank en 18 ficheros, incluidos el logo oficial (`static/logo.png`), 12 hotlinks al CDN de caixabank.es, los prompts del LLM y el usuario por defecto | (Marca) | §7 |

**Recomendación:** no desplegar la v1 en ningún entorno accesible. Refactorizar a la v2 (§9): eliminar la ejecución de código, quitar todos los secretos y credenciales por defecto, servir artefactos precalculados (no entrenar en caliente), fijar dependencias y añadir tests.

---

## 1. Método y reproducibilidad

| Script (en `reports/audit/07_software/`) | Qué hace |
|---|---|
| `smoke_audit.py` | Importa la app (copia sandbox) y usa el test client de Flask: inventario `url_map`, acceso anónimo, login, cabeceras, open redirect, fuerza bruta, escalada usuario→admin, RCE inocua, path traversal, CSRF, borrado de gráficos, 43 llamadas a rutas con latencias, robustez de entrada. Salida: `results/smoke_results.json` |
| `serve_probe.sh` | Arranca la app real en **127.0.0.1:8100** (`app.run(threaded=False)` como `app.py`) y mide con `curl` el arranque, las latencias, el **bloqueo** de una petición trivial mientras otra entrena y las cabeceras. **Mata el servidor al terminar** (verificado: no queda ningún proceso en 8100). Salida: `results/serve_probe_out.txt` |
| `forge_session_demo.py` | Sin `FLASK_SECRET_KEY`, forja una cookie admin con la clave pública del repo y ejecuta un `print` inocuo. Salida: `results/forge_session_out.txt` |
| `static_scan.sh` | Marca, sumideros XSS, dominios externos, SRI, imports frente a `requirements.txt` y bandit. Salida: `results/static_scan_out.txt` |
| `check_province_mappings.py` | Extrae los diccionarios de `app.py` con `ast` (sin importarlo) y los cruza con las 52 provincias del dataset. Salida: `results/prov_map_out.txt` |

**Entorno:** Python 3.13.18, Flask 3.1.3, Werkzeug 3.1.9, pandas 3.0.5, numpy 2.5.3, scikit-learn 1.9.1, shap 0.54.1, statsmodels 0.15.0. Faltaban `google-genai`, `google-generativeai` y `geopandas`, así que se instalaron **solo en un venv del scratchpad** (`--system-site-packages`): google-genai 3.6.1, google-generativeai 0.8.6, geopandas 1.2.0, bandit 1.9.4.
**Variables de prueba:** `FLASK_SECRET_KEY=audit-test-secret`, `APP_USERNAME=audit_user`, `APP_PASSWORD=audit_pass_123`, `GEMINI_API_KEY` sin definir. Uso de CPU limitado con `LOKY_MAX_CPU_COUNT=2` y `OMP_NUM_THREADS=2`.
**Sandbox:** `<scratch>/sandbox*/a/run/{Web, notebooks acabados}` contiene la copia de `Web/` y de los 2 CSV. La app resuelve sus rutas relativas a `Web/..`.
**Advertencia de carga:** durante `serve_probe.sh` otros agentes tenían la máquina con una carga media de 10,6 (4 CPU). Por eso las latencias del servidor real son peores que las del test client; se dan las dos.

> Nota para el coordinador: en `Web/__pycache__/` aparecieron `app.cpython-313.pyc` (18:53) y `demanda_models.cpython-313.pyc` (18:56) creados **por otro proceso**: mis ejecuciones usan `PYTHONDONTWRITEBYTECODE=1` en el sandbox. Un `.pyc` que generé por error a las 18:49 lo borré. El directorio está en `.gitignore`.

---

## 2. Inventario de rutas (29 + `static`)

Leyenda de **Auth**: `—` = pública; `U` = sesión de usuario **o** de admin (`before_request`); `A` = admin (comprobado en `before_request` **o** dentro de la vista).
Leyenda de **Origen de datos**: `RT` = cálculo en tiempo de ejecución; `CSV` = lectura de CSV; `HC-py` = constantes en Python; `HC-tpl` = cifras escritas en la plantilla HTML/JS; `ML` = modelo entrenado dentro de la petición.
Estado y latencia proceden del test client (`smoke_results.json`).

### 2.1 Páginas HTML

| Método | Ruta | Auth | Plantilla / origen de las cifras | Estado · latencia |
|---|---|---|---|---|
| GET | `/` | U | `index.html` + `static/script.js` → `/api/data`, `/api/dashboard-extra`, `/api/mapa/*`, `/api/custom-charts`, `/api/chat` | 200 · 4 ms |
| GET | `/hipotecas` | U | `hipotecas.html` (1.485 líneas, JS inline) → `/api/data` (**dispara el entrenamiento RF de demanda**), `/api/hipoteca-context`, `/api/hipoteca-recomendacion`, `/api/noa-chat`, `/api/noa-strategic`; HC-tpl ("MAPE del 0.6 %") | 200 · 11 ms |
| GET | `/hipotecas-provincial` | U | `hipotecas_provincial.html`, que es un **93,7 % idéntico** a `hipotecas.html`; **no está enlazada** desde ninguna navegación | 200 |
| GET | `/demanda` | U | `demanda.html` → `/api/demanda-data` | 200 |
| GET | `/demanda-provincial` | U | `demanda_provincial.html`, un **97,9 % idéntico** a `demanda.html`; no está enlazada | 200 |
| GET | `/econometria` | U | HC-tpl (MAPE 7,11 %, 9,68 %, R² 0,40, FEVD 70,3/18,1/11,5 %) + 4 PNG de `static/img/econometria/`, generados por `gen_charts.py`, que **no funciona** (lee `../dataset_final_tfm.csv`, que no existe) | 200 |
| GET | `/vecm` | U | **100 % HC-tpl**: arrays Chart.js escritos en el JS (β, α, FEVD 53,3/38,8/3,0/2,6/2,2 %, IRF) | 200 |
| GET | `/metodologia-ml` | U | HC-tpl (24 porcentajes, un ejemplo SHAP fijo, "MAPE nacional ~9,7 %") | 200 |
| GET | `/business_case` | U | HC-tpl (MAPE 7,11 %, 53,3 %, 38,8 %) | 200 |
| GET | `/webscrapping` | U | Texto estático; describe cómo se **copió el diseño de caixabank.es** | 200 |
| GET/POST | `/test-hipoteca` | U | "Legacy": fórmula propia (Euribor + 1,0, entrada del 30 %, cuota de interés más amortización lineal) **incoherente** con el asesor principal | 200 · 4–25 ms |
| GET/POST | `/admin` | A | `admin.html`; POST sube un CSV a `UPLOAD_FOLDER` o sustituye `static/tipos_hipotecas.csv` (sin validar el esquema) | 200 |
| GET/POST | `/login`, `/login_admin` | — | Comparación `==` con `APP_USERNAME`/`APP_PASSWORD` (mismas credenciales para ambos); `next` sin validar | 302 |
| GET | `/logout` | — | Logout por GET | 302 |

### 2.2 APIs JSON

| Método | Ruta | Auth | Entrada | Salida / origen de datos | Estado · latencia (fría → caliente) |
|---|---|---|---|---|---|
| GET | `/api/data` | U | `year_from`, `year_to`, `specific_year` | Agregados del dataset (CSV) + **predicciones futuras** (CSV `predicciones_provinciales` + RF de demanda **ML**, entrenado si no lo estaba) | 200 · 0,36 s (con RF ya entrenado) → 0,47 s; **no cachea** (rehace el pivot en cada llamada) |
| GET | `/api/dashboard-extra` | U | `provincia`, `year` | RT sobre el CSV | 200 · 31 ms |
| GET | `/api/hipoteca-context` | U | `year`, `provincia` | CSV + `_build_forecasts()` (**ML**: SARIMA PIB, rejilla ARIMA de 24 ajustes × 2, SARIMAX del diferencial) + heatmap seaborn en base64 + **métricas HC-py** (`r2 0.8492, rmse 0.1543, mape "3.2%"`) + escenarios "BCE" HC-py | 200 · **3,0 s** (2,6–7,9 s en servidor) → 12 ms |
| POST | `/api/hipoteca-recomendacion` | U | JSON: year, tipo, income, savings, age, province, other_debts, price_mode, custom_price, tenure_years | Cálculo RT + GBR + SHAP (**ML**, entrenado por año) + tablas fiscales HC-py (ITP/AJD/IVA, notaría, registro, financiación joven) | **500** · 1,85 s (entrena y falla) → 6 ms (**F1**) |
| GET | `/api/demanda-data` | U | `year` (`YYYY` o `YYYY-Qn`), `provincia` | `demanda_models.py`: 4 Random Forest (300/300/200/200 árboles) + forecast recursivo de 20 trimestres (**ML**); escenarios BCE HC-py; caché global solo sin filtros | 200 · **23,7 s** (42,4 s en servidor) → 1 ms; con filtros 0,06–0,37 s |
| GET | `/api/mapa/<tipo>` | U | `tension`, `accesibilidad`, `mina_oro` | PNG en base64 con geopandas + matplotlib; `mina_oro` **entrena un RF** con Euribor 2,5 y spread 1,0 HC-py; caché `.b64` en `static/` que **nunca se invalida** | 200 · 1 ms (caché) / 0,60 s / 1,64 s; tipo inválido → 400 |
| GET | `/api/paro-model-info` | U | `provincia` | Tabla HC-py (niveles SARIMA/ARIMA con MAPE escritos en el código) | 200 · 1–2 ms |
| POST | `/api/chat` | U | `{message}` | Gemini 2.5 Flash **con la herramienta `google_search`**; el prompt incluye 5 filas aleatorias del dataset y cifras VAR/VECM HC-py | 200 (sin clave: mensaje de degradación) |
| POST | `/api/noa-chat` | U | `{message, context}`; el `context` lo envía el **cliente** | Gemini; prompt "asesora de CaixaBank" con ingresos, ahorros, edad y deudas | 200 (sin clave) |
| POST | `/api/noa-strategic` | U | ídem | Gemini; prompt **interno de gestor** ("maximizar el beneficio del banco"), accesible a cualquier usuario | 200 (sin clave) |
| GET | `/api/custom-charts` | U | — | `static/custom_charts/index.json` | 200 |
| DELETE | `/api/custom-charts/<id>` | A | id | Borra la entrada; **500 `KeyError 'filename'`** con los 3 gráficos existentes (todos de tipo `chartjs`) | 500 |
| POST | `/admin/upload-chart` | A (en la vista) | `.py`/`.ipynb` | **Ejecuta el fichero** (`nbconvert` + `python`) | RCE (S1) |
| POST | `/admin/execute-code` | A (en la vista; no está en la lista de `before_request`) | `{code}` | **Ejecuta el código** e inyecta el estilo `_CAIXABANK_STYLE` | RCE (S1) |

---

## 3. Resultados de la ejecución

* **Arranque sin dependencias extra:** `python -c "import app"` falla con `ImportError: cannot import name 'genai' from 'google'`. La app **no arranca con `requirements.txt`**.
* **Arranque (venv completo):** import en **3,9 s**; servidor en 8100 hasta el primer 200 en **4,06–4,21 s**. Carga el dataset (4.368×16), `predicciones_provinciales` (9.568×4) y `tipos_hipotecas.csv` (84×5). Aviso de deprecación de `google.generativeai` ("All support… has ended").
* **No se entrena ningún modelo al importar** (comprobado: `_MACRO_FORECASTS` vacío, `_PRICING_MODEL_CACHE` vacío, `demanda_models._ARTIFACTS is None`). Todo se entrena **en la primera petición** que lo necesita, en el hilo de la petición:

| Entrenamiento en caliente | Lo dispara | Coste medido |
|---|---|---|
| `_build_forecasts()`: SARIMA(1,1,0)(1,1,0)4 del PIB, rejillas ARIMA (4×2×3) para paro y ahorro, SARIMAX del diferencial, más el heatmap seaborn | `/api/hipoteca-context`, `/api/hipoteca-recomendacion` | 2,6–7,9 s |
| GBR (100 árboles) + CV de 5 pliegues + `TreeExplainer`, **una vez por año pedido** (el modelo es idéntico porque `year` no se usa) | `/api/hipoteca-recomendacion` | ~1,85 s por año |
| 4 Random Forest + forecast recursivo 2026Q1–2030Q4 | `/api/demanda-data` **y `/api/data`** (dashboard y `/hipotecas`) | **23,7 s** (test client) / **42,4 s** (servidor con carga) |
| RF de 100 árboles para el mapa "mina de oro" | `/api/mapa/mina_oro` (solo la primera vez; después lee la caché de disco) | 1,64 s |

* **Bloqueo:** con `threaded=False`, una petición trivial (`/api/paro-model-info`, 3 ms en frío) lanzada mientras `/api/demanda-data` entrenaba tardó **41,85 s**. El servidor de desarrollo atiende una sola petición a la vez.
* **Memoria:** RSS máximo de **561 MB** tras recorrer todas las rutas (un proceso).
* **Errores 500 reales:** `POST /api/hipoteca-recomendacion` (4/4), `DELETE /api/custom-charts/<id>`, y las entradas no numéricas o fuera de rango (`income="abc"`, `income=-1000`, `age=200`) → 500 HTML sin validación.
* **Fugas de información:** `GET /api/demanda-data?year=abc` → **200** con `traceback` completo y rutas absolutas del servidor; `/api/chat` devuelve `str(e)`; la ejecución de código devuelve 600 caracteres de stderr.
* **Métricas calculadas en esta ejecución** (deterministas, `random_state=42`, con las versiones indicadas):
  * Demanda: RF_Nac **MAPE 6,3 %**; RF provincial **MAPE 14,71 %** (test = últimos 8 trimestres); KPI último trimestre 2025-Q4 = 170.435 hipotecas, +14,9 % interanual.
  * Pricing GBR: n = 4.160, **R²_train 0,9864**, "RMSE_CV" 0,1037, "MAE_CV" 0,0752. Este CV no es válido (ver F3).

---

## 4. Seguridad (OWASP Top 10 2021), por gravedad

### CRÍTICA
**S1. Ejecución remota de código** (A03 Injection / A04 Insecure Design). En `app.py:1903-1975` y `2089-2149` el código del usuario se concatena en un wrapper y se ejecuta con `subprocess.run([sys.executable, wp], cwd=Web/)`. Hereda **todo el entorno del proceso**. Prueba: `RCE_PROOF uid=0 cwd=…/Web`; `secret_visible_to_user_code: true`. No hay sandbox, ni límite de memoria, ni red cortada; solo un timeout de 120 s. El código puede leer o escribir cualquier fichero (dataset, `.env`), exfiltrar la `GEMINI_API_KEY` o abrir una shell inversa. `.ipynb` pasa por `nbconvert`, también sin control. **Acción v2:** eliminar las dos rutas y el editor de `admin.html` (CodeMirror). Los gráficos personalizados, si se conservan, deben ser **declarativos** (JSON validado con un esquema).

**S2. Clave de sesión por defecto pública** (A02 Cryptographic Failures / A07). `app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'tfm_secret_key_fixed_12345')`. Si se olvida la variable, cualquiera firma `{'admin': True}` con `itsdangerous` y obtiene admin → S1 **sin credenciales** (demostrado en `forge_session_out.txt`). **Acción:** no arrancar si falta `SECRET_KEY` en producción.

**S3. Credenciales por defecto y modelo de roles roto** (A07 Identification and Authentication Failures). `APP_USERNAME`/`APP_PASSWORD` valen `'caixabank'` por defecto, el mismo valor en usuario y contraseña, y `.env.example` lo propone. `/login` y `/login_admin` comparan **las mismas** credenciales, así que cualquier usuario obtiene el rol admin pasando por `/login_admin` (demostrado). Además, `index.html` enlaza "Acceso Admin" desde la portada.

### ALTA
**S4. Path traversal y sobrescritura de datos** (A01 Broken Access Control / A08). `fp = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)` sin `secure_filename`, y `UPLOAD_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__name__), '..'))`. Como `__name__ == 'app'`, `dirname` devuelve `''` y la ruta depende del **cwd**: la raíz del repo si se lanza desde `Web/`, el padre del repo si se lanza desde la raíz. Prueba: `../pt_probe.csv` quedó escrito fuera de la carpeta (en el sandbox). Además, subir `dataset_final_tfm.csv` lo coloca en la raíz, que **tiene prioridad** en `_candidate_paths` en el siguiente arranque (envenenamiento persistente), y reasigna el `df` global solo en el proceso actual. La acción `tipos` sobrescribe `static/tipos_hipotecas.csv` sin validar columnas. Tampoco hay `MAX_CONTENT_LENGTH` (`None`), así que las subidas no tienen límite.

**S5. XSS** (A03). (a) Almacenado: `title`, `description`, `source` y `labels` de los gráficos personalizados se insertan con `card.innerHTML` en el dashboard de **todos** los usuarios (`script.js:499-506`, `572-578`). (b) Salida del LLM: `reply.replace('\n','<br>')` → `innerHTML` (`hipotecas*.html:1434/1449/1455/1470`, `script.js:753/772`). Una inyección de prompt, o las URI y títulos de grounding de Google Search (insertados sin escapar en `app.py:2283-2294`), pueden ejecutar JavaScript. (c) Self-XSS en el mensaje del propio usuario. No hay CSP, y 76 sumideros `innerHTML` en total.

**S6. Sin protección CSRF** (A01). Ningún formulario lleva token; la cookie de sesión no tiene `SameSite` ni `Secure` (`Set-Cookie: session=…; HttpOnly; Path=/`). Los POST de formulario (`/admin` con subida, `/login`) se pueden forzar desde otro sitio en navegadores que no aplican Lax por defecto.

**S7. LLM: coste, abuso y privacidad** (A04 / LLM01-LLM06). No hay rate limiting ni límite de longitud del mensaje. `/api/chat` activa `google_search` (grounding, con coste por consulta). El `context` de Noa lo construye el **cliente**, que puede falsearlo. `noa-strategic`, un prompt interno orientado a "maximizar el beneficio del banco", es accesible a cualquier usuario autenticado. Se envían a Google **ingresos, ahorros, edad, deudas y provincia** del usuario sin aviso ni base legal documentada (RGPD; coordinar con el agente legal/compliance). Los prompts hacen que el modelo se presente como empleado de una entidad real.

**S8. Open redirect** (A01). `POST /login?next=https://evil.example/phish` → `302 Location: https://evil.example/phish` (demostrado). Ocurre lo mismo en `/login_admin`.

### MEDIA
* **S9. Fuerza bruta:** 30 contraseñas erróneas en 12 ms, todas con 200, sin bloqueo ni retardo. La comparación `==` no es de tiempo constante (impacto real bajo; usar `hmac.compare_digest` y hash de contraseña).
* **S10. Divulgación de información:** traceback con rutas absolutas en `/api/demanda-data` (HTTP 200); `str(e)` en `/api/chat`; stderr del código ejecutado; `print("[DEBUG ROUTE]…")` en cada llamada al asesor.
* **S11. Cabeceras:** faltan `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`, `Referrer-Policy` y `Permissions-Policy`; `Server: Werkzeug/3.1.9 Python/3.13.18` revela versiones; servidor de desarrollo (`app.run`) con el aviso de "do not use in production".
* **S12. Cadena de suministro front:** `chart.js` cargado de jsdelivr **sin versión** en 5 plantillas (y `@4` en una), sin `integrity=` en ninguna. 12 `<img>` **hotlinkean el logo de caixabank.es**: además del problema de marca, filtran el Referer a un tercero.
* **S13. Dependencias:** `requirements.txt` = `Flask, pandas, werkzeug, google-generativeai, python-dotenv`, **sin versiones**. Faltan `google-genai` (importado en la línea 20, provoca `ImportError`), `numpy`, `scikit-learn`, `shap`, `statsmodels`, `matplotlib`, `seaborn` y `geopandas`. `google-generativeai` está **deprecado y sin soporte**, y solo se importa (`import google.generativeai as _old_genai`, línea 2186) sin usarse. La falta de pins **ya rompe** el asesor (F1).

### BAJA
* Logout por GET; `threaded=False` facilita la denegación de servicio (DoS) con una sola petición lenta; `/api/mapa/<tipo>` con un tipo inválido carga primero geopandas y el GeoJSON (825 KB).
* bandit: 10 avisos de severidad baja (B404/B603 subprocess ×4, B110 `try/except/pass` ×6). No detecta la RCE porque la entrada llega por concatenación de strings.

---

## 5. Corrección funcional y metodológica (impacto directo en la app)

| # | Hallazgo | Gravedad | Detalle |
|---|---|---|---|
| F1 | Asesor caído | ALTA | `_compute_ml_optimal_rate`: `float(explainer.expected_value)` falla con shap 0.54.1 (`expected_value` es un `ndarray` de forma `(1,)`). Es la funcionalidad central y responde 500 en cualquier instalación nueva. Corrección trivial (`float(np.ravel(ev)[0])`), pero es síntoma de que no hay pins ni tests. |
| F2 | Fiscalidad errónea en silencio | ALTA | `PROVINCE_TO_CCAA` usa nombres sin tilde y `_get_ccaa` hace una coincidencia difusa por subcadena. Fallan **12/52** provincias: A Coruña, Almería, Castellón, Cáceres, Cádiz, Córdoba, Guipúzcoa, Jaén, León, Málaga, Álava y Ávila. En ellas se aplica **ITP 8 %** por defecto, no hay financiación joven y no se identifica la CCAA. Las tablas ITP/AJD/financiación joven y las de notaría/registro están **hardcodeadas sin fuente ni vigencia** (coordinar con el agente de fiscalidad). |
| F3 | Validación del GBR de pricing inválida | ALTA | El dataset está ordenado por provincia, así que `TimeSeriesSplit(5)` sobre filas parte por **bloques de ~10 provincias**: cada pliegue de test cubre 2005-01…2024-10 y entrena con todos los trimestres. El objetivo `Spread_Hipotecas` es nacional (1 valor único por trimestre, solo 80 valores distintos en 4.160 filas), de modo que el "RMSE_CV" mide memorización. Además, `_train_ml_pricing_model(year)` **ignora `year`**: para simular 2010 usa datos hasta 2025 (fuga de futuro), y vuelve a entrenar el mismo modelo para cada año. El docstring de `add_doc_notebooks.py` ("entrena con datos estrictamente anteriores") es falso. |
| F4 | Métricas fijas que no se corresponden | ALTA | `/api/hipoteca-context` devuelve siempre `{"r2": 0.8492, "rmse": 0.1543, "mape": "3.2%"}`; lo calculado es R²_train 0,9864 y RMSE "CV" 0,1037. Las plantillas afirman "RF_Nac MAPE 7,11 %" (business_case, econometria, webscrapping); el cálculo actual da **6,3 %**. El RF provincial da 14,71 % y metodologia_ml cita "~9,7 %". En el benchmark, RF_Nac aparece etiquetado como "ML Provincial". |
| F5 | Caché de mapas obsoleta | MEDIA | `_mapa_cache_<tipo>.b64` se escribe en `static/` y **no se invalida nunca** (el comentario dice "se invalida al reiniciar", lo cual es falso), tampoco al subir un dataset nuevo. El repo ya versiona `_mapa_cache_tension.b64`. |
| F6 | Supuestos hardcodeados duplicados | MEDIA | `ESCENARIOS_BCE`/`BCE_SCENARIOS` (Euribor 2,00/2,10/2,30/2,15…, IPC 1,88/2,10/2,00…) aparecen en `app.py` y en `demanda_models.py` (y en notebooks) sin fuente, fecha de publicación ni id de serie. Las cifras VAR/VECM están copiadas a mano en 3 prompts y 4 plantillas. |
| F7 | Identificadores de provincia inconsistentes | MEDIA | Hay 3 normalizadores distintos (`_get_ccaa`, `_resolve_demanda_province`/`resolve_province`, `get_geojson.diccionario_mapa`). `/api/hipoteca-context?provincia=Madrid` → "No hay datos" (el dataset usa "Comunidad de Madrid"); el asesor con "Madrid" usa sin avisar el precio medio **nacional**. |
| F8 | `gen_charts.py` no reproducible | MEDIA | Lee `ROOT/dataset_final_tfm.csv`, que no existe, así que los PNG de `/econometria` no se pueden regenerar desde el repo. |
| F9 | `/test-hipoteca` incoherente | BAJA | Fórmula de cuota distinta de la del asesor y supuestos propios (entrada del 30 %, Euribor + 1,0). |
| F10 | Código muerto y duplicado | BAJA | Páginas provinciales huérfanas, casi idénticas a las nacionales; `test_api.py` es un script de 5 líneas, no un test. |

---

## 6. Arquitectura v1: diagnóstico

1. **Monolito**: `app.py` tiene 2.442 líneas y mezcla 29 rutas, datos de referencia fiscal, 4 motores de modelos (forecast macro, GBR+SHAP, RF de demanda en `demanda_models.py`, RF del mapa), prompts del LLM, renderizado geoespacial y ejecución de código.
2. **Estado global mutable**: `df`, `df_tipos`, `df_prov_preds`, `_MACRO_FORECASTS`, `_PRICING_MODEL_CACHE`, `_DEMANDA_CACHE`, `_GEOJSON_CACHE`, `_CORR_IMG_CACHE` y `demanda_models._ARTIFACTS`. Se reasignan con `global` desde `/admin`. Con gunicorn y varios workers, cada proceso entrena su propia copia (×N de memoria y CPU), y una subida solo actualiza un worker. Los cachés tampoco son thread-safe.
3. **Entrenamiento en la ruta de la petición** (23–42 s en frío) en lugar de **artefactos precalculados**. La docstring de `_build_forecasts` dice "Código EXACTO del notebook HIPOTECA_PERSONALIZADA.ipynb", un notebook que no existe con ese nombre (sí existe `5. HIPOTECA_PERSONALIZADA_provincial.ipynb`). La lógica está **duplicada** entre notebooks y app, sin una fuente única de verdad.
4. **Sin tests, sin logging** (solo `print`), **sin configuración por entorno**, manejo de errores con `except: pass` y `except Exception` que devuelven 200 con `error`, y rutas de datos frágiles (3 candidatos, uno dependiente del cwd).
5. **Renderizado de imágenes en el servidor** (geopandas, matplotlib, seaborn) en base64 dentro del JSON (~80 KB por mapa), cuando el front ya usa Chart.js. El GeoJSON (825 KB) podría servirse estático y pintarse en el cliente.
6. **Front**: 14 plantillas sin herencia (`{% extends %}` en ninguna), navegación, CSS y JS duplicados e inline (hipotecas.html, 1.485 líneas), y 4 CDNs externos.
7. **Scripts sueltos obsoletos** (parches de un solo uso que reescriben `app.py` y las plantillas por sustitución de texto, y que contienen cifras de proyección hardcodeadas, p. ej. `projections = {2026: 622409, …}` en `patch_app_demanda.py`): `fix_app.py`, `patch_app_demanda.py`, `patch_demanda.py`, `update_nav.py`, `add_doc_notebooks.py` (este último modifica notebooks por ruta relativa) y `test_api.py`. **Retirar todos.**

---

## 7. Marca CaixaBank: inventario para eliminar (marca nueva: "Atalaya · Analítica Hipotecaria")

| Ubicación | Qué contiene |
|---|---|
| `Web/static/logo.png` | **Logo oficial de CaixaBank** (estrella + "CaixaBank ADVANCED BUSINESS ANALYTICS"), PNG CMYK de 3509×1123 y 944 KB. Usado en `metodologia_ml.html:221`. **Borrar** y sustituir por un SVG propio. |
| 12 plantillas | `<img src="https://www.caixabank.es/…/logo_laCaixa_principal.gif">` (hotlink): admin, business_case, demanda, demanda_provincial, econometria, hipotecas, hipotecas_provincial, index, login_admin, test_hipoteca, vecm, webscrapping |
| `<title>` y textos | "Hipotecas \| Asesor Inteligente \| CaixaBank", "Predicción de Demanda \| CaixaBank", "Panel de Administracion \| CaixaBank", "Acceso Admin \| CaixaBank Analytics", "Business Case… \| CaixaBank", "Metodología Web Scraping \| CaixaBank TFM", "Transparencia ML - Modelo Hipotecario CaixaBank"; `metodologia_ml.html` incluye "© 2026 CaixaBank, S.A." y "En CaixaBank nos regimos…"; `business_case.html` habla de integrarse con "sistemas core de CaixaBank"; `webscrapping.html` tiene **una sección entera** ("Replicación del Diseño Corporativo de CaixaBank", extracción del CDN), que se debe reescribir o retirar |
| Asistente "Noa" | "Noa — Asesora Hipotecaria CaixaBank" (hipotecas*.html:921/926), saludo "Soy Noa, tu asesora hipotecaria de CaixaBank" (líneas 1415/1430). Renombrar el asistente (p. ej. "Asistente Atalaya"). |
| `app.py` (13 ocurrencias) | Usuario y contraseña por defecto `'caixabank'` (33-34); comentario "CaixaBank max 80%" (1458); prompts de Noa (1719), Noa Strategic (1803) y del chat ejecutivo (2238-2242, que ordena buscar "beneficios de CaixaBank"); `_CAIXABANK_STYLE` y `_CB_COLORS` (1977-2026) |
| CSS/JS | `style.css:1` "CaixaBank Authentic Aesthetics"; `script.js:18` "Colores corporativos CaixaBank"; comentarios "Paleta Oficial CaixaBank" y "Nav Corporativa CAIXABANK" en metodologia_ml; "CaixaBank Colors" en demanda*.html y "Colores CaixaBank" en vecm.html. Paleta `#007BC0`/`#003F6C`/`#FF6600` y fuente Open Sans, copiadas de caixabank.es: **cambiar la paleta**. |
| `index.html:268` | Placeholder del chat: "beneficios de CaixaBank" |
| `.env.example:4` | `APP_USERNAME=caixabank` |
| `Web/README.md` | 2 menciones (`_CAIXABANK_STYLE`) |
| `add_doc_notebooks.py` | 3 menciones de Noa (se retira el script) |
| `static/custom_charts/index.json` | `"source": "Editor corporativo"` (neutro, pero procede del editor que se elimina) |

Recuento por fichero (líneas con "caixa"): metodologia_ml 8, webscrapping 10, hipotecas 5, hipotecas_provincial 5, business_case 5, demanda 4, demanda_provincial 4, admin 3, index 3, login_admin 3, vecm 2, test_hipoteca 2, econometria 1, style.css 1, script.js 1, README 1, .env.example 1, app.py 13.

---

## 8. Arquitectura v2 propuesta

### 8.1 Principios
1. **La app no entrena.** Solo lee artefactos versionados de `artifacts/<dominio>/` (JSON/CSV/Parquet con `manifest.json`: versión, fecha de generación, hash de entrada, métricas de validación, fuente). Los generan los pipelines de `src/pipelines/` (contrato del briefing). El único cálculo en tiempo de ejecución es la **simulación del asesor**: cuota, DTI, impuestos e inferencia de un modelo ya serializado y ligero.
2. **Seguridad por defecto**: sin ejecución de código, sin secretos por defecto, CSRF, rate limiting, CSP, escape sistemático.
3. **Configuración por entorno**, **app factory**, **blueprints**, **tests** y despliegue con gunicorn.
4. **Marca única "Atalaya · Analítica Hipotecaria"**, sin referencias a entidades reales.

### 8.2 Estructura de módulos

```
Web/
  wsgi.py                      # from atalaya import create_app; app = create_app()
  atalaya/
    __init__.py                # create_app(config_name): carga Config, registra blueprints, extensiones, errores, cabeceras
    config.py                  # BaseConfig / DevConfig / TestConfig / ProdConfig. ProdConfig exige SECRET_KEY y
                               # ARTIFACTS_DIR; SESSION_COOKIE_SECURE/SAMESITE='Lax'; MAX_CONTENT_LENGTH; LLM_ENABLED
    extensions.py              # csrf (Flask-WTF CSRFProtect), limiter (Flask-Limiter), talisman/cabeceras
    security.py                # auth (hash werkzeug.security, roles), login_required/admin_required, safe_next_url()
    errors.py                  # handlers JSON/HTML 400/404/413/429/500 sin traceback; logging estructurado
    logging.py                 # dictConfig, request-id
    blueprints/
      pages.py                 # GET: /, /asesor, /demanda, /econometria, /metodologia, /fuentes, /acerca
      api.py                   # /api/v1/... (ver 8.3), con esquemas de entrada (pydantic o marshmallow)
      admin.py                 # /admin: estado de artefactos, recarga (sin subida de código ni de CSV arbitrarios)
      health.py                # /healthz (liveness), /readyz (artefactos cargados + versión)
    services/
      artifacts.py             # ArtifactStore: lee artifacts/<dominio>/manifest.json, valida el esquema, cachea en memoria
                               # (lru_cache) y expone la versión; una única ruta raíz desde la config (adiós a _candidate_paths)
      panel.py                 # Acceso al panel maestro v2 (data/processed) por prov_code (INE "01".."52") y period YYYYQn
      provinces.py             # Catálogo canónico prov_code -> nombre oficial, CCAA, alias (sustituye los 3 normalizadores)
      taxes.py                 # Fiscalidad desde data/metadata (con vigencia y fuente), no dicts en código
      mortgage.py              # Simulador: cuota francesa, DTI, entrada, financiación, impuestos; puro y testeable
      pricing.py               # Inferencia del modelo de pricing serializado (+ SHAP precalculado o ligero), con métricas
                               # leídas del manifest (nunca hardcodeadas)
      demand.py                # Lectura de artifacts/demand (series históricas, forecast, escenarios, métricas)
      econometrics.py          # Lectura de artifacts/econometrics (IRF, FEVD, β, α) -> el front pinta con Chart.js
      llm.py                   # (opcional, desactivado por defecto) cliente google-genai; prompt server-side a partir
                               # del resultado recalculado en servidor (no del context del cliente); sin datos personales;
                               # límites de longitud; respuesta en texto plano
    templates/
      base.html                # layout, nav, footer, marca Atalaya, bloque CSP-nonce
      pages/*.html             # extienden base.html; sin cifras escritas a mano: se rellenan con datos de artefactos
    static/
      css/atalaya.css  js/{charts,asesor,demanda}.js  img/atalaya-logo.svg
      vendor/chart.umd.min.js  # copia local con versión fijada (o CDN con versión exacta + SRI)
  tests/ (en /tests del repo)
    conftest.py                # app de test con artifacts/ de fixture (mini)
    test_security.py           # sin rutas de ejecución; CSRF; open redirect; cabeceras; rate limit; cookies
    test_api_contracts.py      # esquemas de respuesta de /api/v1/*, códigos 400/404 ante entradas inválidas
    test_mortgage.py           # cuota/DTI/impuestos con casos calculados a mano; 52 provincias -> CCAA resuelta
    test_artifacts.py          # manifest válido, versiones, que las métricas mostradas = métricas del manifest
    test_pages.py              # 200 en todas las páginas; ninguna contiene "caixa" (test de marca)
  requirements.in / requirements.txt (pip-compile, versiones fijadas) · requirements-dev.txt
  Procfile                     # web: gunicorn wsgi:app --workers 2 --threads 4 --timeout 30 --preload
  render.yaml                  # servicio web Python, healthCheckPath /healthz, envVars SECRET_KEY (generateValue), etc.
  Dockerfile (opcional)        # python:3.12-slim, usuario no root, sin compiladores, COPY artifacts/, gunicorn
  .env.example                 # sin valores reales ni de marca
```

### 8.3 API v2 (solo lectura, salvo la simulación)

| Ruta | Método | Origen |
|---|---|---|
| `/api/v1/meta` | GET | Versiones de artefactos, fecha de corte de datos, fuentes |
| `/api/v1/panel/summary?from&to&prov` | GET | `services/panel` (sustituye `/api/data` y `/api/dashboard-extra`, sin inyectar predicciones mezcladas con el histórico) |
| `/api/v1/forecasts?var&prov` | GET | `artifacts/forecasting` (con bandas de incertidumbre si el pipeline las genera) |
| `/api/v1/demand?prov&period` | GET | `artifacts/demand` (histórico, forecast, escenarios Euribor y métricas del manifest) |
| `/api/v1/econometrics/{var,vecm}` | GET | `artifacts/econometrics` (IRF, FEVD, β, α → Chart.js; sin PNG ni cifras a mano) |
| `/api/v1/maps/<indicador>?period` | GET | Valores por `prov_code` (JSON); el mapa se pinta en el cliente con el GeoJSON estático (sin geopandas en el servidor) |
| `/api/v1/advisor/simulate` | POST (CSRF + rate limit) | `services/mortgage` + `services/pricing`; entrada validada (rangos de edad, ingresos, plazo), errores 400 |
| `/api/v1/assistant` | POST (opcional, flag `LLM_ENABLED`, rate limit estricto, p. ej. 10/min y 100/día por sesión) | `services/llm` |
| `/healthz`, `/readyz` | GET | health |

### 8.4 Seguridad concreta
* **Retirar** `/admin/execute-code`, `/admin/upload-chart`, la subida de CSV a la raíz y el editor CodeMirror. La actualización de datos se hace **solo** con los pipelines y un commit de `artifacts/`. El admin queda reducido a ver el estado de los artefactos y recargarlos.
* `SECRET_KEY` obligatoria en producción (si falta, la app no arranca). Usuarios con **hash** (`generate_password_hash`) en variables de entorno; rol admin con credencial distinta, o eliminar el rol admin. `hmac.compare_digest`; `safe_next_url()` que solo admite rutas relativas del mismo host.
* **CSRF**: `Flask-WTF CSRFProtect` (formularios + cabecera `X-CSRFToken` en fetch). La alternativa sin dependencia es un token de doble envío propio.
* **Rate limiting**: `Flask-Limiter` (memoria en un worker, Redis si hay varios). Login 5/min; simulación 30/min; LLM 10/min.
* **Cabeceras**: CSP con `default-src 'self'; script-src 'self' 'nonce-…'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'`, nosniff, Referrer-Policy `strict-origin-when-cross-origin`, HSTS en producción, `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE=Lax`, `MAX_CONTENT_LENGTH`.
* **XSS**: usar `textContent` o creación de nodos en lugar de `innerHTML`; si se quiere markdown del LLM, sanearlo (DOMPurify local) o devolver texto plano. Ninguna cadena externa se inserta sin escapar.
* **LLM**: el prompt se construye en el servidor con datos recalculados en el servidor y **sin datos personales** (o con consentimiento explícito y aviso, a coordinar con compliance). Sin `google_search` por defecto. Sin el rol "gestor/beneficio del banco". Timeout y límite de tokens.
* **Dependencias**: pin exacto + `pip-audit` en CI; sustituir `google-generativeai` por `google-genai` (solo si se mantiene el LLM, como dependencia opcional `extras`).

### 8.5 Funcionalidades: conservar, rehacer o retirar

| Funcionalidad v1 | Decisión v2 |
|---|---|
| Dashboard (`/`, `/api/data`, `/api/dashboard-extra`) | **Conservar**, servido desde el panel v2 y los artefactos; histórico y proyección separados visualmente |
| Asesor hipotecario (`/hipotecas`, `/api/hipoteca-context`, `/api/hipoteca-recomendacion`) | **Rehacer**: simulador transparente (cuota, DTI, impuestos con vigencias) + pricing con validación temporal real (dependiente de los agentes de modelado y banca). Fusionar con `/hipotecas-provincial` |
| Demanda (`/demanda`, `/api/demanda-data`) | **Conservar** leyendo `artifacts/demand`; fusionar con `/demanda-provincial` (selector de provincia) |
| Econometría y VECM | **Conservar**, pintadas desde `artifacts/econometrics` (sin PNG ni cifras a mano) |
| Metodología ML, Business case | **Rehacer** el contenido con las métricas del manifest; quitar marca y textos de "maximización comercial" |
| Web scraping | **Rehacer** como página de "Fuentes y licencias"; eliminar la sección de replicar el diseño de CaixaBank |
| Mapas | **Conservar** el concepto con mapa en el cliente; retirar "Mina de Oro Bancario" o rehacerlo como índice documentado sin RF en caliente |
| `/api/paro-model-info` | Pasar a artefacto (`artifacts/forecasting/model_selection.json`) |
| Chatbots Gemini (`/api/chat`, `noa-chat`, `noa-strategic`) | **Retirar `noa-strategic`** y la búsqueda web. Asistente único opcional, desactivado por defecto (decisión del coordinador) |
| `/test-hipoteca` | **Retirar** (duplicado e incoherente) |
| Admin: ejecutar código, subir notebooks o CSV, gráficos personalizados | **Retirar** |
| `gen_charts.py`, `fix_app.py`, `patch_*.py`, `update_nav.py`, `add_doc_notebooks.py`, `test_api.py` | **Retirar** (`gen_charts` se convierte en un pipeline de `src/`) |
| `static/logo.png`, hotlinks de caixabank.es, `_mapa_cache_*.b64`, `custom_charts/` | **Eliminar** del repo |

### 8.6 Orden de migración sugerido
1. Seguridad inmediata: quitar las rutas de ejecución y la subida, los secretos y credenciales por defecto, y el open redirect; fijar `requirements`.
2. App factory + config + blueprints moviendo el código tal cual, con tests de humo que fijen el comportamiento.
3. `ArtifactStore`; sustituir los entrenamientos en caliente por la lectura de artefactos, dominio a dominio (econometría, demanda, forecasts, pricing).
4. `base.html`, marca Atalaya, CSP con nonces, eliminación de `innerHTML`.
5. Despliegue con gunicorn y `render.yaml`/Dockerfile, `/healthz`, CI (pytest + pip-audit + bandit + test de marca).

---

## 9. Decisiones que requieren arbitraje del coordinador
1. **¿Mantener algún asistente LLM?** Recomiendo desactivarlo por defecto (coste, privacidad y alucinaciones sobre cifras) o dejarlo solo con contexto agregado y sin datos personales. `noa-strategic` debe retirarse en cualquier caso.
2. **¿Mantener login?** Para una demo pública de un TFM recomiendo un sitio público de solo lectura, sin cuentas ni rol admin. Si hay que mantener la autenticación: credenciales con hash por entorno y un único rol.
3. **Modelo de pricing (GBR sobre un spread nacional replicado):** con la validación corregida es probable que no aporte sobre una referencia simple. Hay que decidir con el agente de banca/modelado si el asesor ofrece un "tipo ML" o solo una simulación basada en tipos de mercado publicados (BdE/BCE).
4. **Cifras narrativas** (FEVD 53,3 %, β, MAPE 7,11 %…): deben salir de los artefactos v2. Mientras no existan, propongo retirarlas en lugar de dejar valores no verificados.
5. **Supuestos "BCE"** (Euribor/IPC 2026-2031): falta la fuente con fecha de publicación; debería resolverlo el agente de datos BCE.
