# Informe de actualización de datos (dry-run)

- Inicio: 2026-11-22T15:57:19+00:00 · Fin: 2026-11-22T15:57:28+00:00
- Filtros: {'source': 'eurostat', 'dataset': None}

## Datasets

| dataset | fuente | ¿cambios en origen? | última modificación origen | staging | nuevas | revisadas | eliminadas |
|---|---|---|---|---|---|---|---|
| eurostat_coste_construccion | eurostat | no |  | HttpError('HTTP 404 https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_copi_q?geo=ES&indic_bt=COST&unit=I21&s_adj=NSA&format=JSON&lang=EN: { "error": [{"status": 404,"id": 100,"label": "ERR_NOT_FOUND_4: STS_COPI_Q (DATA_FLOW:ALL,1.0) is not available for dissemination."}]}') | 0 | 0 | 0 |

## Variables con cambios

(ninguna)

## Modelos que requieren recalibración

(ninguno)

## Incidencias de calidad (error/warning)

- **error** `fetch` eurostat_coste_construccion: HttpError('HTTP 404 https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sts_copi_q?geo=ES&indic_bt=COST&unit=I21&s_adj=NSA&format=JSON&lang=EN: { "error": [{"status": 404,"id": 100,"label": "ERR_NOT_FOUND_4: STS_COPI_Q (DATA_FLOW:ALL,1.0) is not available for dissemination."}]}')

## Watcher fiscal (BOE legislación consolidada)

| boe_id | norma | actualización BOE | verificada | ¿revisión? |
|---|---|---|---|---|
| BOA-d-2005-90006 | DLeg 1/2005 Texto refundido tributos cedidos de Aragón | 2025-07-17 | 2026-11-22 | no |
| BOC-j-2009-90008 | DLeg 1/2009 Texto refundido tributos cedidos de Canarias | 2026-08-14 | 2026-11-22 | no |
| BOCL-h-2013-90254 | DLeg 1/2013 Texto refundido tributos cedidos de Castilla y León | 2024-07-17 | 2026-11-22 | no |
| BOCM-m-2010-90068 | DLeg 1/2010 Texto refundido tributos cedidos de la Comunidad de Madrid | 2026-08-31 | 2026-11-22 | no |
| BOCT-c-2008-90028 | DLeg 62/2008 Texto refundido tributos cedidos de Cantabria | 2026-05-14 | 2026-11-22 | no |
| BOE-A-1992-28740 | Ley 37/1992 del IVA | 2026-10-07 | 2026-11-22 | no |
| BOE-A-1993-25359 | RDLeg 1/1993 Ley ITPAJD: tipo estatal 6 % (art. 11.1.a) con bonificación del 50 % para inmuebles situados en Ceuta o Melilla (art. 57 bis.3) | 2026-03-23 | 2026-11-22 | no |
| BOE-A-1998-8202 | Ley 13/1997 tramo autonómico IRPF y tributos cedidos (C. Valenciana) | 2026-09-18 | 2026-11-22 | no |
| BOE-A-2011-10542 | DLeg 1/2010 Texto refundido tributos cedidos de la Región de Murcia | 2026-03-17 | 2026-11-22 | no |
| BOE-A-2011-18161 | DLeg 1/2011 Texto refundido tributos cedidos de Galicia | 2026-05-04 | 2026-11-22 | no |
| BOE-A-2014-1368 | Ley 8/2013 de Medidas Tributarias de Castilla-La Mancha | 2026-11-10 | 2026-11-22 | no |
| BOE-A-2014-6925 | DLeg 1/2014 Texto refundido tributos cedidos de las Illes Balears | 2026-07-24 | 2026-11-22 | no |
| BOE-A-2015-945 | DLeg 2/2014 Texto refundido tributos cedidos del Principado de Asturias | 2026-02-09 | 2026-11-22 | no |
| BOE-A-2017-13750 | Ley 10/2017 Texto refundido tributos cedidos de La Rioja | 2026-10-29 | 2026-11-22 | no |
| BOE-A-2018-8159 | DLeg 1/2018 Texto refundido tributos cedidos de Extremadura | 2026-11-12 | 2026-11-22 | no |
| BOE-A-2021-17915 | Ley 5/2021 de Tributos Cedidos de Andalucía | 2026-01-16 | 2026-11-22 | no |
| BOE-A-2024-6951 | DLeg 1/2024 Código tributario de Cataluña (libro sexto) | 2026-11-19 | 2026-11-22 | no |
