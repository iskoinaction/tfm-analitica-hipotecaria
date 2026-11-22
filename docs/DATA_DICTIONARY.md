# Diccionario de datos (v2)

> Generado desde `data/metadata/data_dictionary.csv` (fuente única de verdad). Claves: paneles `prov_code` (código INE 01–52) y `period` (`YYYYQn`) o `year`.

**Fecha de referencia vs. fecha de publicación:** las variables llevan la fecha de *referencia*. Las reglas de disponibilidad (retraso de publicación por variable) están en `data/metadata/availability_rules.yaml` y se aplican en `panel_modelado.csv`. No existen *vintages* públicos de la mayoría de series (el BCE sí conserva versiones con `includeHistory=true`): se documenta como limitación en `MODEL_VALIDATION.md`.


## panel_trimestral

| Columna | Ámbito | Unidad | Frec. origen | Agregación | Fuente | Tabla/serie | Descripción |
|---|---|---|---|---|---|---|---|
| `prov_code` |  |  |  |  | clave/estructura |  | Código INE de provincia (01-52) |
| `period` |  |  |  |  | clave/estructura |  | Trimestre YYYYQn |
| `provincia` |  |  |  |  | clave/estructura |  | Nombre oficial INE |
| `ccaa_code` |  |  |  |  | clave/estructura |  | Código INE de CCAA |
| `quarter_start` |  |  |  |  | clave/estructura |  | Fecha de inicio del trimestre |
| `compraventas_viviendas_num` | provincia | número | M | sum | ine | 6150 | Compraventas de viviendas inscritas (ETDP, régimen y estado: general). |
| `hipotecas_fincas_total_num` | provincia | número | M | sum | ine | 3200 | Hipotecas constituidas sobre el total de fincas (comparable con Hipotecas_Total v1). |
| `hipotecas_viviendas_importe` | provincia | miles de euros | M | sum | ine | 3200 | Importe de hipotecas constituidas sobre viviendas. |
| `hipotecas_viviendas_num` | provincia | número | M | sum | ine | 3200 | Hipotecas constituidas sobre viviendas (número). Objetivo principal v2. |
| `precio_m2_mivau_tasado` | provincia | €/m² | Q | none | mivau | VDP006_01 | Valor tasado medio de vivienda libre €/m² (MIVAU, todas las tasaciones). Alternativa oficial a Tinsa. |
| `precio_m2_tinsa` | provincia | €/m² | Q | none | tinsa | legacy_v1_csv | Valor medio €/m² (Tinsa IMIE, provincias). |
| `tasa_paro` | provincia | % | Q | none | ine | 65349 | Tasa de paro EPA (ambos sexos). |
| `ipc_indice` | ccaa | índice base 2025=100 | M | mean | ine | 76136 | IPC índice general (base 2025), media trimestral. Ámbito CCAA. |
| `ipc_var_anual` | ccaa | % | M | mean | ine | 76136 | IPC índice general, variación anual (media de los meses del trimestre). Ámbito CCAA. |
| `ipv_general_indice` | ccaa | índice base 2015=100 | Q | none | ine | 80270 | Índice de Precios de Vivienda (INE), general. Desde 2007. |
| `diferencial_tae_euribor` | nacional | p.p. |  |  | derivada |  | Diferencial TAE vivienda − Euríbor 12M (antes 'Spread_Hipotecas') |
| `diferencial_tedr_euribor` | nacional | p.p. |  |  | derivada |  | Diferencial tipo sin comisiones − Euríbor 12M |
| `euribor_12m` | zona_euro | % | M | mean | ecb | FM+MIR | Euríbor a 12 meses, media mensual; trimestral = media de los 3 meses. |
| `indice_coste_construccion` | nacional | índice 2021=100 | Q | none | eurostat | sts_copi_q | Índice general de costes de construcción de edificios residenciales nuevos (STS, Eurostat), sustituye a Indice_Materiales v1. |
| `indice_mano_obra_construccion` | nacional | índice base 1980 | M | mean | ine | 8377 | Índice de coste de mano de obra en la construcción (MIVAU, difundido por el INE), media trimestral. |
| `pib_nominal_meur` | nacional | millones de euros corrientes | Q | none | ine | 67821 | PIB trimestral nominal (CNTR, no ajustado). |
| `pib_nominal_meur_sa` | nacional | millones de euros corrientes | Q | none | ine | 67821 | PIB trimestral nominal (CNTR, ajustado de estacionalidad y calendario). |
| `pib_volumen_indice` | nacional | índice de volumen encadenado | Q | none | ine | 67822 | PIB trimestral en volumen encadenado (no ajustado). |
| `pib_volumen_indice_sa` | nacional | índice de volumen encadenado | Q | none | ine | 67822 | PIB trimestral en volumen encadenado (ajustado). |
| `tae_vivienda` | nacional | % | M | mean | ecb | FM+MIR | TAE (APRC) de nuevas operaciones de préstamos a hogares para vivienda, España. |
| `tasa_ahorro_hogares` | nacional | % de la renta disponible | Q | none | ine | SERIE:CTNFSI11271,CTNFSI11270 | Tasa de ahorro de hogares e ISFLSH, serie original no ajustada (CTNFSI11271). |
| `tasa_ahorro_hogares_sa` | nacional | % de la renta disponible | Q | none | ine | SERIE:CTNFSI11271,CTNFSI11270 | Tasa de ahorro de hogares e ISFLSH, ajustada de estacionalidad y calendario (CTNFSI11270). |
| `tedr_vivienda` | nacional | % | M | mean | ecb | FM+MIR | Tipo sin comisiones (AAR/NDER) de nuevas operaciones de préstamos a hogares para vivienda, España. |

## panel_anual

| Columna | Ámbito | Unidad | Frec. origen | Agregación | Fuente | Tabla/serie | Descripción |
|---|---|---|---|---|---|---|---|
| `prov_code` |  |  |  |  | clave/estructura |  | Código INE de provincia (01-52) |
| `year` |  |  |  |  | clave/estructura |  | Año de referencia |
| `provincia` |  |  |  |  | clave/estructura |  | Nombre oficial INE |
| `ccaa_code` |  |  |  |  | clave/estructura |  | Código INE de CCAA |
| `edad_media` | provincia | años | A | annual | ine | 3199 | Edad media de la población a 1 de enero. |
| `pib_pc` | provincia | euros corrientes | A | annual | ine | 82285 | PIB a precios de mercado per cápita (Contabilidad Regional, solo publicado). |
| `poblacion` | provincia | personas | S | annual | ine | 59591 | Población residente (ECP) a 1 de enero. |
| `poblacion_extranjera` | provincia | personas | S | annual | ine | 59591 | Población residente de nacionalidad extranjera (ECP) a 1 de enero. Fuente única homogénea. |
| `edad_media_status` | provincia | años | A | annual | ine | 3199 | Estado INE del dato de edad_media (Definitivo/Provisional/Avance) |
| `pib_pc_status` | provincia | euros corrientes | A | annual | ine | 82285 | Estado INE del dato de pib_pc (Definitivo/Provisional/Avance) |
| `poblacion_status` | provincia | personas | S | annual | ine | 59591 | Estado INE del dato de poblacion (Definitivo/Provisional/Avance) |
| `poblacion_extranjera_status` | provincia | personas | S | annual | ine | 59591 | Estado INE del dato de poblacion_extranjera (Definitivo/Provisional/Avance) |

## panel_modelado

| Columna | Ámbito | Unidad | Frec. origen | Agregación | Fuente | Tabla/serie | Descripción |
|---|---|---|---|---|---|---|---|
| `prov_code` |  |  |  |  | clave/estructura |  | Código INE de provincia (01-52) |
| `period` |  |  |  |  | clave/estructura |  | Trimestre YYYYQn |
| `provincia` |  |  |  |  | clave/estructura |  | Nombre oficial INE |
| `ccaa_code` |  |  |  |  | clave/estructura |  | Código INE de CCAA |
| `quarter_start` |  |  |  |  | clave/estructura |  | Fecha de inicio del trimestre |
| `compraventas_viviendas_num` | provincia | número | M | sum | ine | 6150 | Compraventas de viviendas inscritas (ETDP, régimen y estado: general). |
| `hipotecas_fincas_total_num` | provincia | número | M | sum | ine | 3200 | Hipotecas constituidas sobre el total de fincas (comparable con Hipotecas_Total v1). |
| `hipotecas_viviendas_importe` | provincia | miles de euros | M | sum | ine | 3200 | Importe de hipotecas constituidas sobre viviendas. |
| `hipotecas_viviendas_num` | provincia | número | M | sum | ine | 3200 | Hipotecas constituidas sobre viviendas (número). Objetivo principal v2. |
| `precio_m2_mivau_tasado` | provincia | €/m² | Q | none | mivau | VDP006_01 | Valor tasado medio de vivienda libre €/m² (MIVAU, todas las tasaciones). Alternativa oficial a Tinsa. |
| `precio_m2_tinsa` | provincia | €/m² | Q | none | tinsa | legacy_v1_csv | Valor medio €/m² (Tinsa IMIE, provincias). |
| `tasa_paro` | provincia | % | Q | none | ine | 65349 | Tasa de paro EPA (ambos sexos). |
| `ipc_indice` | ccaa | índice base 2025=100 | M | mean | ine | 76136 | IPC índice general (base 2025), media trimestral. Ámbito CCAA. |
| `ipc_var_anual` | ccaa | % | M | mean | ine | 76136 | IPC índice general, variación anual (media de los meses del trimestre). Ámbito CCAA. |
| `ipv_general_indice` | ccaa | índice base 2015=100 | Q | none | ine | 80270 | Índice de Precios de Vivienda (INE), general. Desde 2007. |
| `diferencial_tae_euribor` | nacional | p.p. |  |  | derivada |  | Diferencial TAE vivienda − Euríbor 12M (antes 'Spread_Hipotecas') |
| `diferencial_tedr_euribor` | nacional | p.p. |  |  | derivada |  | Diferencial tipo sin comisiones − Euríbor 12M |
| `euribor_12m` | zona_euro | % | M | mean | ecb | FM+MIR | Euríbor a 12 meses, media mensual; trimestral = media de los 3 meses. |
| `indice_coste_construccion` | nacional | índice 2021=100 | Q | none | eurostat | sts_copi_q | Índice general de costes de construcción de edificios residenciales nuevos (STS, Eurostat), sustituye a Indice_Materiales v1. |
| `indice_mano_obra_construccion` | nacional | índice base 1980 | M | mean | ine | 8377 | Índice de coste de mano de obra en la construcción (MIVAU, difundido por el INE), media trimestral. |
| `pib_nominal_meur` | nacional | millones de euros corrientes | Q | none | ine | 67821 | PIB trimestral nominal (CNTR, no ajustado). |
| `pib_nominal_meur_sa` | nacional | millones de euros corrientes | Q | none | ine | 67821 | PIB trimestral nominal (CNTR, ajustado de estacionalidad y calendario). |
| `pib_volumen_indice` | nacional | índice de volumen encadenado | Q | none | ine | 67822 | PIB trimestral en volumen encadenado (no ajustado). |
| `pib_volumen_indice_sa` | nacional | índice de volumen encadenado | Q | none | ine | 67822 | PIB trimestral en volumen encadenado (ajustado). |
| `tae_vivienda` | nacional | % | M | mean | ecb | FM+MIR | TAE (APRC) de nuevas operaciones de préstamos a hogares para vivienda, España. |
| `tasa_ahorro_hogares` | nacional | % de la renta disponible | Q | none | ine | SERIE:CTNFSI11271,CTNFSI11270 | Tasa de ahorro de hogares e ISFLSH, serie original no ajustada (CTNFSI11271). |
| `tasa_ahorro_hogares_sa` | nacional | % de la renta disponible | Q | none | ine | SERIE:CTNFSI11271,CTNFSI11270 | Tasa de ahorro de hogares e ISFLSH, ajustada de estacionalidad y calendario (CTNFSI11270). |
| `tedr_vivienda` | nacional | % | M | mean | ecb | FM+MIR | Tipo sin comisiones (AAR/NDER) de nuevas operaciones de préstamos a hogares para vivienda, España. |
| `poblacion_ref_year` | provincia | personas | S | annual | ine | 59591 | Año de referencia de poblacion disponible (publicado) al cierre del trimestre; regla: 1-ene-Y + 5 meses |
| `poblacion` | provincia | personas | S | annual | ine | 59591 | Población residente (ECP) a 1 de enero. |
| `poblacion_extranjera_ref_year` | provincia | personas | S | annual | ine | 59591 | Año de referencia de poblacion_extranjera disponible (publicado) al cierre del trimestre; regla: 1-ene-Y + 5 meses |
| `poblacion_extranjera` | provincia | personas | S | annual | ine | 59591 | Población residente de nacionalidad extranjera (ECP) a 1 de enero. Fuente única homogénea. |
| `edad_media_ref_year` | provincia | años | A | annual | ine | 3199 | Año de referencia de edad_media disponible (publicado) al cierre del trimestre; regla: 1-ene-Y + 6 meses |
| `edad_media` | provincia | años | A | annual | ine | 3199 | Edad media de la población a 1 de enero. |
| `pib_pc_ref_year` | provincia | euros corrientes | A | annual | ine | 82285 | Año de referencia de pib_pc disponible (publicado) al cierre del trimestre; regla: 1-ene-Y + 35 meses |
| `pib_pc` | provincia | euros corrientes | A | annual | ine | 82285 | PIB a precios de mercado per cápita (Contabilidad Regional, solo publicado). |

## nacional_trimestral

| Columna | Ámbito | Unidad | Frec. origen | Agregación | Fuente | Tabla/serie | Descripción |
|---|---|---|---|---|---|---|---|
| `period` |  |  |  |  | clave/estructura |  | Trimestre YYYYQn |
| `compraventas_viviendas_num` | nacional | número | M | sum | ine | 6150 | Compraventas de viviendas inscritas (ETDP, régimen y estado: general). |
| `diferencial_tae_euribor` | nacional | p.p. |  |  | derivada |  | Diferencial TAE vivienda − Euríbor 12M (antes 'Spread_Hipotecas') |
| `diferencial_tedr_euribor` | nacional | p.p. |  |  | derivada |  | Diferencial tipo sin comisiones − Euríbor 12M |
| `euribor_12m` | zona_euro | % | M | mean | ecb | FM+MIR | Euríbor a 12 meses, media mensual; trimestral = media de los 3 meses. |
| `hipotecas_fincas_total_num` | nacional | número | M | sum | ine | 3200 | Hipotecas constituidas sobre el total de fincas (comparable con Hipotecas_Total v1). |
| `hipotecas_viviendas_importe` | nacional | miles de euros | M | sum | ine | 3200 | Importe de hipotecas constituidas sobre viviendas. |
| `hipotecas_viviendas_num` | nacional | número | M | sum | ine | 3200 | Hipotecas constituidas sobre viviendas (número). Objetivo principal v2. |
| `indice_coste_construccion` | nacional | índice 2021=100 | Q | none | eurostat | sts_copi_q | Índice general de costes de construcción de edificios residenciales nuevos (STS, Eurostat), sustituye a Indice_Materiales v1. |
| `indice_mano_obra_construccion` | nacional | índice base 1980 | M | mean | ine | 8377 | Índice de coste de mano de obra en la construcción (MIVAU, difundido por el INE), media trimestral. |
| `ipc_indice` | ccaa | índice base 2025=100 | M | mean | ine | 76136 | IPC índice general (base 2025), media trimestral. Ámbito CCAA. |
| `ipc_var_anual` | ccaa | % | M | mean | ine | 76136 | IPC índice general, variación anual (media de los meses del trimestre). Ámbito CCAA. |
| `ipv_general_indice` | ccaa | índice base 2015=100 | Q | none | ine | 80270 | Índice de Precios de Vivienda (INE), general. Desde 2007. |
| `pib_nominal_meur` | nacional | millones de euros corrientes | Q | none | ine | 67821 | PIB trimestral nominal (CNTR, no ajustado). |
| `pib_nominal_meur_sa` | nacional | millones de euros corrientes | Q | none | ine | 67821 | PIB trimestral nominal (CNTR, ajustado de estacionalidad y calendario). |
| `pib_volumen_indice` | nacional | índice de volumen encadenado | Q | none | ine | 67822 | PIB trimestral en volumen encadenado (no ajustado). |
| `pib_volumen_indice_sa` | nacional | índice de volumen encadenado | Q | none | ine | 67822 | PIB trimestral en volumen encadenado (ajustado). |
| `precio_m2_mivau_tasado` | nacional | €/m² | Q | none | mivau | VDP006_01 | Valor tasado medio de vivienda libre €/m² (MIVAU, todas las tasaciones). Alternativa oficial a Tinsa. |
| `tae_vivienda` | nacional | % | M | mean | ecb | FM+MIR | TAE (APRC) de nuevas operaciones de préstamos a hogares para vivienda, España. |
| `tasa_ahorro_hogares` | nacional | % de la renta disponible | Q | none | ine | SERIE:CTNFSI11271,CTNFSI11270 | Tasa de ahorro de hogares e ISFLSH, serie original no ajustada (CTNFSI11271). |
| `tasa_ahorro_hogares_sa` | nacional | % de la renta disponible | Q | none | ine | SERIE:CTNFSI11271,CTNFSI11270 | Tasa de ahorro de hogares e ISFLSH, ajustada de estacionalidad y calendario (CTNFSI11270). |
| `tasa_paro` | nacional | % | Q | none | ine | 65349 | Tasa de paro EPA (ambos sexos). |
| `tedr_vivienda` | nacional | % | M | mean | ecb | FM+MIR | Tipo sin comisiones (AAR/NDER) de nuevas operaciones de préstamos a hogares para vivienda, España. |
| `hipotecas_viviendas_num_suma_prov` | nacional | número | M | sum | ine | 3200 | Suma de las 52 provincias de hipotecas_viviendas_num (reconciliación con el total nacional oficial) |
| `hipotecas_fincas_total_num_suma_prov` | nacional | número | M | sum | ine | 3200 | Suma de las 52 provincias de hipotecas_fincas_total_num (reconciliación con el total nacional oficial) |
| `hipotecas_viviendas_importe_suma_prov` | nacional | miles de euros | M | sum | ine | 3200 | Suma de las 52 provincias de hipotecas_viviendas_importe (reconciliación con el total nacional oficial) |
| `compraventas_viviendas_num_suma_prov` | nacional | número | M | sum | ine | 6150 | Suma de las 52 provincias de compraventas_viviendas_num (reconciliación con el total nacional oficial) |
| `poblacion_ecp` |  |  |  |  | clave/estructura |  | Población ECP nacional en la fecha de stock más reciente <= inicio del trimestre (sin interpolar) |
| `poblacion_ecp_fecha` |  |  |  |  | clave/estructura |  | Fecha de referencia del stock de población usado |
| `pib_pc_trimestral_eur` |  |  |  |  | clave/estructura |  | PIB nominal trimestral (no ajustado) / población ECP (euros por habitante y trimestre) |
| `precio_m2_tinsa_pond_pob` |  |  |  |  | clave/estructura |  | Media de precio_m2_tinsa de las 52 provincias ponderada por población ECP a 1-ene del año |
