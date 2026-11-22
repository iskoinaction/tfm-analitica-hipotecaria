# Asesor hipotecario v2 (Banca)

Estado: motor `src/advisor/` operativo; 179 tests en verde (`python -m pytest -q tests`). Fecha de generación: 2026-11-22.

| Problema | Evidencia | Solución | Justificación |
|---|---|---|---|
| El GBR "predecía" el Spread con RMSE CV 0,104 | Con fuga (CV aleatoria con 80 obs. efectivas, 4.160 filas replicadas). Origen móvil: GBR 0,380 frente a persistencia 0,200 (`artifacts/advisor/estimator_validation.json`) | GBR y ajuste `tanh` eliminados. Tipo de mercado = último dato BCE (MIR, TEDR) con rango de 4 trimestres y fecha | Un modelo peor que la persistencia no aporta; el rango se declara como rango, no como intervalo de predicción (cobertura 21-37 %) |
| El asesor emitía "Aprobada/Denegada" | Decisión sin política real de entidad | Semáforo de capacidad de pago (DSTI, LTI, LTV) con estrés +3 pp y parámetros de política ILUSTRATIVOS (`data/metadata/advisor_policy.yaml`) | No se simula una decisión de crédito; se informa del esfuerzo |
| Fiscalidad fija por provincia | Tipos cambian por vigencia y territorio | `fiscalidad_vigencias.csv` (45 reglas, 38 verificadas contra la API del BOE; no verificadas: ITP-15/16, AJD-15/16, IGIC-05, IPSI-18/19), `aranceles.yaml`; no verificado/no modelado se avisa (`NO VERIFICADO`, `NO MODELADO` Canarias IGIC) | Trazabilidad por fecha de operación |
| Gastos asignados al cliente | Ley 5/2019 art. 14 | Notaría de la hipoteca, registro, gestoría y AJD a cargo del banco; el cliente paga tasación, ITP/IVA+AJD de compraventa y su notaría/registro | Cumplimiento normativo |
| Años futuros como dato | — | Años 2026-2030 = escenarios (base/adverso/favorable) etiquetados "ESCENARIO ... (supuesto, no predicción)" | No confundir proyección y predicción |

## Antes / después
v1: GBR+SHAP, tanh, "Aprobada/Denegada". v2: motor determinista (cuota francesa, mixto, variable con Euríbor+diferencial), semáforo, recomendación de capital máximo, entrada necesaria, 18 vectores de prueba exportados (`artifacts/advisor/test_vectors.json`) para validar la réplica JS.

## Validación
- `tests/test_advisor_core.py`, `tests/test_advisor_engine.py`: 14+ pruebas de motor (ITP por tramos, ADJ, edad/plazo, mercado, escenario, no verificado, metadata).
- Corrección de este turno: `test_vectores_exportados_reproducibles` fallaba porque el caso mixto dependía del Euríbor de mercado (datos actualizados). Se añade la entrada opcional `tin_variable_pct` (TIN del tramo variable en mixto) y el vector la fija; vectores regenerados con `python -m src.advisor.export`.
- Limitación: la política (DSTI máx., LTV, estrés) es ilustrativa y no representa a ninguna entidad.
