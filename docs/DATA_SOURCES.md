# Fuentes de datos (v2)

> Generado desde `data/metadata/series_catalog.yaml` y `data/metadata/provenance.csv`. Informe de investigación completo y verificación de ids: `reports/audit/10_fuentes.md` y `reports/audit/10_source_catalog.yaml`.

| Dataset | Organismo | Tabla/serie | Frec. | Retraso de publicación | Última modificación en origen | Extraído | Opcional |
|---|---|---|---|---|---|---|---|
| `ine_hipotecas` | ine | 3200 | M | ≈2 meses tras el mes de referencia; datos del último año provisionales | Mon Oct 26 09:00:00 CET 2026 | 2026-11-21T19:12:50Z | False |
| `ine_etdp_compraventas` | ine | 6150 | M | ≈2 meses | Tue Nov 17 09:00:00 CET 2026 | 2026-11-21T19:13:05Z | False |
| `ine_epa_paro` | ine | 65349 | Q | ≈4 semanas tras el trimestre | Tue Oct 27 09:00:00 CET 2026 | 2026-11-21T19:11:45Z | False |
| `ine_ipc` | ine | 76136 | M | ≈2 semanas tras el mes | Fri Nov 13 09:00:00 CET 2026 | 2026-11-22T00:25:01Z | False |
| `ine_ecp_poblacion` | ine | 59591 | S | ≈1-2 meses; datos recientes provisionales | Thu Nov 12 09:00:00 CET 2026 | 2026-11-21T19:14:00Z | False |
| `ine_edad_media` | ine | 3199 | A | ≈6 meses | Tue Dec 02 11:00:00 CET 2025 | 2026-11-21T19:14:18Z | False |
| `ine_cre_pib_pc` | ine | 82285 | A | Diciembre t+1 (CCAA avance); provincias t+2 | Wed Sep 30 11:00:00 CEST 2026 | 2026-11-21T19:14:36Z | False |
| `ine_ipv` | ine | 80270 | Q | ≈10 semanas | Mon Sep 07 09:00:00 CEST 2026 | 2026-11-21T19:15:13Z | False |
| `ine_cntr_pib` | ine | 67821 | Q | ≈30 días (avance) | Fri Oct 30 09:00:00 CET 2026 | 2026-11-21T19:14:43Z | False |
| `ine_cntr_pib_vol` | ine | 67822 | Q | ≈30 días (avance) | Fri Oct 30 09:00:00 CET 2026 | 2026-11-21T19:14:45Z | False |
| `ine_tasa_ahorro` | ine | SERIE:CTNFSI11271,CTNFSI11270 | Q | ≈3 meses | None | 2026-11-22T00:25:21Z | False |
| `ine_mano_obra` | ine | 8377 | M | ≈2-3 meses | None | 2026-11-21T19:14:46Z | False |
| `eurostat_coste_construccion` | eurostat | sts_copi_q | Q | ≈3 meses | 2026-11-21T11:00:00+0100 | 2026-11-21T19:11:53Z | False |
| `ecb_tipos` | ecb | FM+MIR | M | ≈5 semanas (MIR) | None | 2026-11-21T19:11:53Z | False |
| `mivau_valor_tasado` | mivau | VDP006_01 | Q | ≈2,5 meses | Thu, 17 Sep 2026 14:46:28 GMT | 2026-11-22T00:24:47Z | False |
| `tinsa_precio` | tinsa | legacy_v1_csv | Q | ≈1 mes | None | desconocida: CSV generado en v1 por tinsa_scraper.py sin fecha | True |

## Metodología y documentación por fuente

- **ine_hipotecas** — Estadística de Hipotecas (HPT), datos procedentes de los Registros de la Propiedad. Flujo mensual. ([documentación](https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736170236))
- **ine_etdp_compraventas** — Estadística de Transmisiones de Derechos de la Propiedad (ETDP), Registros de la Propiedad. Disponible desde 2007. ([documentación](https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736171438))
- **ine_epa_paro** — Encuesta de Población Activa; tasas trimestrales provinciales (error muestral relevante en provincias pequeñas). ([documentación](https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736176918))
- **ine_ipc** — IPC base 2025 (tabla vigente 76136, series enlazadas por el INE desde 2002; sin empalmes propios). ([documentación](https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736176802))
- **ine_ecp_poblacion** — Estadística Continua de Población (ECP); stock a fecha (1 de enero/1 de julio, trimestral en años recientes). ([documentación](https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736177095))
- **ine_edad_media** — Indicadores demográficos básicos. ([documentación](None))
- **ine_cre_pib_pc** — Contabilidad Regional de España (CRE) base 2021; provincias con ~2 años de retraso, CCAA con avance. ([documentación](https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736167628))
- **ine_ipv** — IPV (precios de transacción, notarios). ([documentación](None))
- **ine_cntr_pib** — Contabilidad Nacional Trimestral. ([documentación](None))
- **ine_cntr_pib_vol** — Contabilidad Nacional Trimestral. ([documentación](None))
- **ine_tasa_ahorro** — Cuentas Trimestrales no Financieras de los Sectores Institucionales. ([documentación](None))
- **ine_mano_obra** — Índices de costes del sistema de la construcción (Ministerio de Vivienda), tabla INE 8377. ([documentación](None))
- **eurostat_coste_construccion** — Estadísticas coyunturales (STS) de Eurostat, dato remitido por España. ([documentación](https://ec.europa.eu/eurostat/databrowser/view/sts_copi_q/default/table))
- **ecb_tipos** — BCE: mercados financieros (FM) y estadísticas de tipos de interés de IFM (MIR). ([documentación](https://data.ecb.europa.eu/))
- **mivau_valor_tasado** — Estadística de Valor Tasado de Vivienda (IOE 20007), Ministerio de Vivienda y Agenda Urbana. ([documentación](https://datos.gob.es/apidata/catalog/dataset/e05233601-valor-tasado-de-la-vivienda.json))
- **tinsa_precio** — Tinsa IMIE General y Grandes Mercados. Por defecto se reutiliza el CSV v1 (snapshot sin fecha); el scraping es opcional y está desactivado: las condiciones de uso de tinsa.es prohíben la explotación sin autorización (10_source_catalog.yaml). ([documentación](https://www.tinsa.es/precio-vivienda/))

## Condiciones de uso y decisiones sobre fuentes
- **INE, BCE, Eurostat, MIVAU:** datos públicos accesibles por API o descarga oficial; se cita siempre el organismo. Revisar el aviso legal de cada uno antes de redistribuir.
- **Tinsa (precio del m², scraping en la v1):** sus condiciones de uso prohíben explotar el contenido sin autorización expresa. En la v2 el precio principal es el **valor tasado de vivienda libre del MIVAU** (CSV VDP006); la serie de Tinsa queda solo como legado de comparación v1↔v2, con el scraping desactivado y sin publicarse en la app ni en la web.
- **Financialtools (fiscalidad, scraping en la v1):** sustituida por una tabla propia con vigencias, verificada contra la API de legislación consolidada del BOE (`data/metadata/fiscalidad_vigencias.csv`). Reglas sin verificar: marcadas `verificado=false` y avisadas en la UI.
- **Ministerio de Inclusión (población extranjera 2023+):** retirada: la v2 usa una única fuente homogénea (INE, Estadística Continua de Población, tabla 59591), sin empalmes.
- **Proyecciones institucionales (BCE, Banco de España, Comisión Europea, FMI):** versionadas con edición y fecha en `data/metadata/escenarios_macro.yaml`; lo no releído en la fuente está marcado como supuesto.
- **Pendientes de investigar/acceder:** Notariado, Registradores (ERI), API del FMI y fichero del Ministerio de Inclusión (acceso denegado desde el entorno), AEAT/Hacienda.

