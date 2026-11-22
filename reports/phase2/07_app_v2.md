# App web v2: Atalaya · Analítica Hipotecaria

Estado: 10 páginas + `/healthz` `/readyz` responden 200 con gunicorn (puerto 8100), sin errores de consola ni scroll horizontal a 1440 y 390 px. Capturas JPEG (1,2 MB) en `Web/docs/screenshots/`. 179 tests en verde.

| Problema (v1) | Evidencia | Solución | Justificación |
|---|---|---|---|
| Admin con ejecución de código arbitrario, credencial por defecto, marca de entidad real | `/admin/execute-code`, `/admin/upload-chart`; briefing del coordinador | Sitio público de solo lectura sin admin; marca "Atalaya"; test que falla si aparece "caixa" (o "tinsa" en HTML/JS) en `Web/` | Seguridad y respeto de marcas |
| Modelos entrenados al arrancar; cifras tecleadas | `Web/demanda_models.py` | La app solo lee `artifacts/`, `data/forecasts/`, `data/processed/` vía servicios; estado vacío honesto ("Artefacto no generado" + comando) | Reproducibilidad y trazabilidad |
| Esquemas de artefactos distintos de lo previsto | Los pipelines escriben CSV/JSON sin manifest | `services/native.py`: si no hay `manifest.json` adapta los ficheros nativos (demanda, proyecciones, econometría VAR en diferencias principal, asesor, calidad). Si aparece manifest+views se usa ese contrato | Evita acoplar plantillas a esquemas |
| Seguridad/accesibilidad | UX audit | CSRF, rate limiting, CSP con nonce, cabeceras, labels, foco visible, tema claro/oscuro, es-ES, histórico (continua) vs escenarios (discontinua) con intervalo 10-90 % | Requisitos del coordinador |
| Precio | Tinsa | Solo MIVAU `precio_m2_mivau_tasado` con atribución; filas Tinsa filtradas de /datos | Licencia |

Corrección de tests: `test_artifact_provenance_rendered` fallaba porque Flask escapaba las tildes (`validación`) en el JSON embebido; `app.json.ensure_ascii = False`.

Despliegue: `Procfile`, `render.yaml` (healthCheck `/healthz`, `SECRET_KEY` generada, asistente desactivado), `Dockerfile`. Asistente LLM opcional, desactivado por defecto, sin datos personales.

Pendiente: econometría por provincias (panel) y Business case con cifras económicas dependen de artefactos aún no generados (se muestra "pendiente"); la prueba Playwright usa Chrome del sistema y Chart.js desde CDN con SRI.
