# Notebooks y datos de la v1 (histórico)

Estos notebooks, CSV y PDF son la **línea base v1** del TFM y se conservan sin modificar para poder reconstruir las comparaciones antes/después. **No reflejan la v2** y contienen errores identificados en la auditoría (`reports/audit/`):

- `Hipotecas_Total` mal leído (miles sin ceros finales: «17.49» = 17.490) en 382 provincia-trimestre.
- Cifras que no se sostienen: MAPE 7,11 % de RF_Nac (el naive da 7,30 %), VECM r = 1 con FEVD 53,3 %/38,8 %/2,2 %, ajuste 44 % trimestral, R² 0,997 del modelo de tipos.
- PIB per cápita 2024 provincial imputado, suelo NAIRU 8,5 %, tope CAGR del PIB, precio por scraping de Tinsa.

La implementación vigente está en `src/`, `data/`, `artifacts/`, `Web/` y `site/`. Resultados corregidos: `docs/MODEL_VALIDATION.md` y `reports/phase2/`.
