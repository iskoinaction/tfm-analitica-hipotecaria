# Fase VII · Contraste independiente: Banca y Data Engineering

Revisor combinado. Fecha: 2026-11-22. Rama `claude/stoic-edison-gdie8p`. No se ha modificado código ni datos; solo este informe
(el dry-run generó un informe en `artifacts/data_quality/` que se borró).

Pruebas ejecutadas: `pytest tests/test_advisor_*.py` (42 OK), `pytest tests/test_data_*.py` (24 OK), `vitest advisor.test.ts` (23 OK),
`python -m src.pipelines.update_all --dry-run` (16 datasets, **1 error**), 40 perfiles contra `src.advisor.simulate`
(cuota contrastada con cálculo independiente: diferencia 0,00 € en todos), grep de secretos y tamaños.

---

## A. BANCA

### Lo que está bien (verificado)
- Cuota francesa, mixta y variable coinciden con el cálculo independiente (`C·r/(1-(1+r)^-n)`) en los 25+ perfiles con préstamo, incluidos TIN 0 % y negativo.
- Reparto de gastos conforme a Ley 5/2019 art. 14.1.e: el cliente paga tasación, ITP (usada) o IVA+AJD (nueva), y notaría y registro de la **compraventa**. Notaría, registro, gestoría y AJD de la **escritura de préstamo** se declaran a cargo del banco y no se suman. Vivienda nueva se calcula (IVA 10 %, AJD autonómico): Madrid 0,75 %, Cataluña 1,5 %, Valencia vivienda habitual 0,1 %.
- Sin lenguaje "aprobada/denegada" en motor, Flask, React ni salida JSON (se buscó `aprob|deneg|conced|cumple` en el resultado completo). El test TS lo impone.
- Parámetros de política (DSTI 35/40 %, LTV 80 %, LTI 6, estrés +3 pp, edad 75, plazo 30) etiquetados "ILUSTRATIVO / no límite legal" en YAML, avisos y salida (`parametros.naturaleza`).
- Rango de tipo de mercado etiquetado "no es intervalo de predicción"; escenarios etiquetados "supuesto, no predicción".
- Marca ficticia y disclaimers presentes en `base.html`, `simulador.html`, `App.tsx`, `Simulator.tsx`, `advisor.ts`.
- La claim de AI Act no aparece como cumplimiento. `caso_negocio.html` dice que un modelo de solvencia "entraría en alto riesgo" (condicional correcto).

### Hallazgos

**B1 · ALTA · El simulador Flask no funciona de extremo a extremo.**
- Evidencia: `Web/atalaya/services/advisor_service.py::validate_payload` emite `prov_code, ahorro_disponible, tipo_interes, primera_vivienda, tipo_vivienda="segunda_mano", anio`. El motor exige `aportacion`, `modalidad`, `usada|nueva`, `vivienda_habitual` y rechaza campos desconocidos. Llamada directa: `AdvisorEngineError: tipo_vivienda: valores 'usada'|'nueva'; aportacion: obligatorio; ahorro_disponible,primera_vivienda,prov_code,tipo_interes: campos no reconocidos`. Todo envío del formulario (`simulador.js`) da HTTP 400.
- Solución: traducir campos en el adaptador (`ahorro_disponible→aportacion`, `tipo_interes→modalidad`, `segunda_mano→usada`, `primera_vivienda→vivienda_habitual`, `prov_code→provincia`, `anio→escenario_anio`) y añadir un test que no mockee el motor.
- Riesgo: la demo de la web Flask se rompe en la defensa. La web React (réplica TS, 23 tests) sí funciona.

**B2 · MEDIA · Canarias, vivienda nueva: IGIC omitido, el resultado parece completo.**
- Evidencia: Tenerife nueva, 250.000 €: gastos 3.455 € frente a ~27.000 € en Madrid; LTV 77 %, semáforo verde. El aviso "NO MODELADO" existe, pero la cifra y el semáforo no cambian.
- Solución: modelar IGIC (7 %, verificar Ley 20/1991) o devolver `gastos_incompletos: true` y no emitir semáforo verde si falta un impuesto.
- Riesgo: subestimación de ~17.500 € en ese territorio. Igual en Ceuta y Melilla (IPSI).

**B3 · MEDIA · El semáforo solo mira DSTI.**
- Evidencia: aportación 40.000 € con tasación 200.000 € sobre precio 250.000 €: LTV 113 %, LTI 6,3, semáforo **verde**. Edad 80 con plazo 30 (vencimiento a 110 años): **verde**, solo un aviso.
- Solución: LTV > 100 %, LTI > referencia o edad+plazo > edad máxima degradan a ámbar (o muestran "fuera de parámetros ilustrativos").
- Riesgo: lectura engañosa de "verde" como "viable".

**B4 · MEDIA · Gastos incluidos en el capital por defecto.**
- Evidencia: capital = precio + gastos − aportación. Con 25.000 € de aportación sobre 200.000 € resulta LTV 94 %. Solo se avisa si la aportación no cubre los gastos.
- Solución: documentar la opción "gastos no financiables" (LTV sobre precio) o mostrar ambos.
- Riesgo: sobreestima el capital respecto a la práctica de mercado.

**B5 · BAJA · Excepción no controlada fuera de rango.**
- Evidencia: `precio_vivienda=20.000.000` pasa la validación (hi=50 M) y `fiscal.arancel` lanza `ValueError` (tope regulado 6,01 M). La fachada Flask lo captura (10 M), pero `simulate()` directo no.
- Solución: límite en `validate` o `AdvisorInputError`.
- Riesgo: bajo.

**B6 · BAJA · Edad 74 y plazo 1 año.**
- Evidencia: cuota 17.450 €/mes, DSTI 582 %, rojo. Correcto pero absurdo.
- Solución: aviso de "plazo residual inferior a X años".

**B7 · MEDIA · Fiscalidad no re-verificada de forma independiente.**
- Evidencia: 38 de 45 reglas "verificadas" (script contra API BOE, `fiscal_verification.json`). No verificadas: ITP/AJD Navarra y País Vasco, IGIC, IPSI. Bizkaia usada aplica 4 % no verificado, con aviso. Sin red, no repetí la comprobación ni las tablas de Madrid AJD 0,4/0,5/0,75 %.
- Solución: marcar en la UI "verificado el 22/11/2026" y revisión humana de las 7 filas pendientes.
- Riesgo: tipos autonómicos cambian cada año (el watcher avisa, no corrige).

**B8 · BAJA · Textos legales.**
- Evidencia: `simulador.html` cita "FIPRE", `Intro.tsx` cita "FEIN". El documento precontractual de la LCCI es la FEIN (más la FiAE); verificar el término. `caso_negocio.html` cita el Reglamento 2024/1689 pero no el aplazamiento a 2/12/2027 (Reglamento 2026/1744).
- Solución: unificar a FEIN y añadir la fecha. Además, el asistente Gemini (opcional, apagado por defecto) envía texto a un tercero; el aviso "no escribas datos personales" es correcto, y el art. 50 AI Act (transparencia de chatbot) queda cubierto por "Respuesta generada automáticamente".

### ¿Qué se puede y qué no se puede afirmar sobre aplicabilidad real en un banco?
**Se puede afirmar:**
- Es un simulador académico determinista de cuota, gastos y esfuerzo, con tipos de mercado del BCE (fuente y fecha) y fiscalidad trazable a BOE, con 38/45 reglas verificadas.
- La arquitectura sirve de prototipo para una calculadora de información al cliente: separa política (YAML), fiscalidad con vigencias y motor.
- No emite decisión de crédito y no usa datos personales reales.

**No se puede afirmar:**
- Que evalúa solvencia (LCCI art. 11, Orden EHA/2899/2011, EBA/GL/2020/06): no usa verificación de ingresos, historial, CIRBE ni estrés de ingresos.
- Que "cumple" el AI Act. Un TFM no desplegado queda fuera del ámbito, pero no hay evidencia de cumplimiento. Si se usara para scoring (anexo III 5.b), las obligaciones aplicarían desde 2/12/2027 (Reglamento 2026/1744), con gestión de riesgos, datos, supervisión humana y documentación.
- Que los umbrales (DSTI 35/40 %, LTV 80 %, estrés +3 pp) representen la política de ninguna entidad o del Banco de España.
- Que el tipo sea una oferta, ni que las cuotas coincidan con una FEIN (comisiones, vinculaciones, bonificaciones).
- Que los aranceles sean la factura real: son cota inferior (sin folios, copias, suplidos).
- Que los resultados valgan en Canarias, Ceuta y Melilla (vivienda nueva) ni en regímenes forales sin verificar.
- Cualquier uso real exigiría validación del modelo por riesgos y cumplimiento, revisión legal y la FEIN.

---

## B. DATA ENGINEERING

### Lo que está bien (verificado)
- Panel trimestral: 4.524 filas, **52 provincias**, 87 trimestres cada una, **0 duplicados** `(prov_code, period)`.
- Suma de provincias = total INE: ratio exacto 1,000 en 86 trimestres de hipotecas (viviendas y fincas) y 79 de compraventas.
- Diccionario de datos cubre el 100 % de columnas de `panel_trimestral`, `panel_modelado` y `panel_anual`.
- Raw inmutable: `save_snapshot` nunca sobrescribe (directorio con sello horario si existe) y guarda sha256 y licencia en `.meta.json`. Dry-run no escribe raw, staging ni processed.
- Workflow: commit solo en `datos/auto-update`, sin force push, tests antes del commit, concurrencia sin cancelar.
- Sin secretos: grep de patrones (AIza, sk-, ghp_, AKIA, claves privadas, `key=...`) sin resultados. `.env` ignorado; solo `Web/.env.example` versionado.
- Tinsa: la web nunca la expone (`BLOCKED_COLUMN_RE`) y el conector está desactivado por defecto.
- Ausencia de vintages documentada (`API_PIPELINE.md`, `build_master.py`).

### Hallazgos

**D1 · ALTA · Tinsa se redistribuye en el repositorio.**
- Evidencia: `data/raw/tinsa/20261121/tinsa_precio.csv`, `data/staging/tinsa_precio.csv` y `precio_m2_tinsa` en `panel_trimestral.csv` están versionados. La propia auditoría (`10_fuentes.md`) dice que las condiciones de tinsa.es prohíben explotar el contenido sin autorización. `econometrics_v2.json` expone la variable `precio_m2_tinsa_pond_pob`. La web filtra la columna, pero el repositorio no.
- Solución: retirar de git (o `.gitignore` más historial), usar MIVAU como sustituto, o pedir autorización a Tinsa. Citar en la memoria como uso académico privado.
- Riesgo: si el repositorio es público (`github.com/iskoinaction/...`), es redistribución. Retirar de la historia requiere reescribir (decisión del autor).

**D2 · ALTA · Un conector caído bloquea todo el workflow.**
- Evidencia: el dry-run de hoy dio `eurostat_coste_construccion` HTTP 404 ("STS_COPI_Q not available for dissemination"). `main()` devuelve 1 si algún dataset falla, y el paso de commit del workflow no se ejecuta, así que se pierden también los 15 datasets que sí funcionaron.
- Solución: `continue-on-error` en el paso de update, con commit de lo bueno y un issue/alerta para el conector caído. Revisar el dataset de Eurostat (puede ser temporal o un cambio de código `sts_copi_q`).
- Riesgo: datos obsoletos sin que nadie lo note durante semanas.

**D3 · MEDIA · Fechas de referencia frente a publicación solo cubren 4 variables.**
- Evidencia: `availability_rules.yaml` define lags solo para población (5 m), población extranjera (5 m), edad media (6 m) y PIB pc (35 m). El resto (hipotecas ~2 m, EPA, tasa de ahorro 3-6 m, IPV, MIVAU, PIB trimestral) entra en `panel_modelado` por periodo de referencia, sin retraso de publicación.
- Solución: ampliar la tabla de lags a todas las series que entren como regresores y documentar que el backtest es pseudo-tiempo-real (sin vintages).
- Riesgo: look-ahead optimista en los modelos con regresores contemporáneos.

**D4 · MEDIA · Vintages inexistentes en la práctica.**
- Evidencia: todos los snapshots son del 21-22/11/2026 (16 en provenance), de modo que no hay historial de revisiones. Está documentado, pero no cuantificado en la memoria.
- Solución: citar como limitación; empezar a acumular snapshots con el workflow; usar `includeHistory=true` del BCE cuando proceda.

**D5 · MEDIA · Licencias solo en `meta.json` y en la auditoría.**
- Evidencia: `provenance.csv` no tiene columna de licencia (el `licence` está en cada `.meta.json`). Condiciones: INE (reutilización citando fuente), BCE/Euribor (EMMI: términos propios del benchmark, la redistribución del Euribor merece cita), Eurostat (CC BY 4.0), MIVAU (datos.gob.es, cita), Tinsa (prohibido). No hay una nota de atribución visible por fuente en la web, salvo la sección de datos.
- Solución: columna `licencia` en `provenance.csv` y un `LICENCIAS.md` o sección "Atribución" en la web y el README.

**D6 · BAJA · Tamaños y LFS.**
- Evidencia: solo `data/staging/ine_hipotecas.csv` pesa 8,2 MB (>5 MB); resto <5 MB; `.git` 38 MB; sin `.gitattributes` ni LFS. El workflow comitea staging completo en cada cambio, y el raw (.gz) solo diffs.
- Solución: no versionar `staging/` (derivable con `--rebuild`) o usar LFS si crece. LFS no es necesario hoy.

**D7 · BAJA · Series nacionales replicadas en el panel provincial.**
- Evidencia: en 2026Q3, Euríbor, TAE, TEDR, PIB e IPC nacional aparecen en las 52 provincias. Esto ya está señalado por Econometría; aquí solo se confirma que el panel no lo marca (columna de nivel geográfico en `data_dictionary` ya existe).

**D8 · BAJA · Dry-run con efectos secundarios.**
- Evidencia: `--dry-run` escribe `artifacts/data_quality/update_report_*_dryrun.*` (y ya hay 3 en `site/public`). Contradice parcialmente "sin escribir". Solución: nota en la doc, o `.gitignore` de `*_dryrun*`.

---

## Veredicto

**Banca: APTO CON RESERVAS.** El motor es correcto, honesto y bien etiquetado como simulador académico. Falla B1 (Flask roto), que es bloqueante para la demo de esa web, y B2/B3 (resultado "verde" con información incompleta o fuera de parámetros).

**Data Engineering: APTO CON RESERVAS.** Datos, duplicados, sumas y procedencia sólidos, sin secretos y sin sobrescritura de raw. Pendientes D1 (Tinsa redistribuida) y D2 (fragilidad del workflow, ya activa con el 404 de Eurostat).

Prioridad: B1, D1, D2, B2, B3, D3.
