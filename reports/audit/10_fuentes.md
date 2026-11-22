# 10 · Auditoría de fuentes de datos (API-first)

Fecha: 2026-11-21 · Autor: especialista en investigación de fuentes · Alcance: las 14 variables de
`notebooks acabados/dataset_final_tfm.csv` y la fiscalidad del asesor.

Artefactos:
- Catálogo máquina-legible: `reports/audit/10_source_catalog.yaml` (ids y endpoints probados).
- Scripts reproducibles: `reports/audit/10_fuentes_scripts/` (ejecutar con `python -I <script>` desde ese directorio):
  `common.py` (cliente INE/ECB/Eurostat + mapa de provincias INE), `compare_ine.py`, `compare_ecb.py`,
  `check_hipotecas_parse.py`, `check_misc.py`, `compare_tinsa_mivau.py`, `ecb_vintages.py`,
  `probe_ine_tables.py`, `fiscal_boe_extract.py`, `fiscal_boe_article.py`.
- Muestras y resultados: `reports/audit/10_fuentes_scripts/samples/` (764 KB; MIVAU comprimido en `.csv.gz`).

Todas las cifras de este informe proceden de esos scripts (salidas en `samples/*.json|*.txt|*.csv`).

---

## 1. Resumen ejecutivo

| Gravedad | Hallazgo |
|---|---|
| **CRÍTICA** | **Hipotecas_Total mal parseado**: el CSV bruto trae miles con ceros finales recortados (`"10.24"` = 10.240, `"8.95"` = 8.950). `limpiar_numero()` (notebook 3) solo quita el punto si hay 3 decimales. 375 celdas (8,6 %) del panel son no enteras y **496 celdas difieren > 0,5 % del INE, con error mediano −33 %** (p. ej. Madrid 2022T2: panel 7.155,19 vs INE 26.326). Afecta sobre todo a las provincias grandes (Barcelona 27 trimestres, Madrid 24, Valencia 23...). Ver `samples/hipotecas_parse_errors.csv`. |
| **CRÍTICA** | **Indice_Materiales no es un índice**: es la media aritmética de 14 niveles base 1964 (7 materiales × Península/Canarias, sin "Ligantes") de la tabla INE 8378 (verificado: diferencia 9e-13). Mezcla energía (≈5.200–9.500) con aluminio (≈1.137): la variable carece de interpretación económica. |
| **ALTA** | **Pob_Ext con ruptura de concepto en 2023**: 2005-2022 = Padrón INE (empadronados); 2023-2025 = Ministerio de Inclusión (stock de extranjeros con documentación de residencia), anualizado por media de trimestres. Frente a la ECP del INE (residentes extranjeros), la mediana de la diferencia relativa salta de +0,0 % (2022) a **+17,0 % (2023), +14,6 % (2024), +9,0 % (2025)**. |
| **ALTA** | **Spread_Hipotecas conceptualmente sesgado**: APRC/TAE (incluye comisiones y TODOS los periodos de fijación; hoy dominan fijos/mixtos) menos Euribor 12m. Llega a −0,13 pp (2024T2) y 0,23 pp (2024T3). Con el tipo variable/fijación ≤1 año (AAR, `MIR.M.ES.B.A2C.F.R.A.2250.EUR.N`) el diferencial 2024T3 es 0,88 pp. La operación aritmética está bien (diferencia máx. 0,012 pp con la API). |
| **ALTA** | **Precio_m2 (Tinsa) obtenido por scraping contra las condiciones de uso**: tinsa.es (titular Accumin Home S.L.U.) prohíbe "cualquier explotación de todo o parte del contenido ... sin la previa autorización expresa". robots.txt no lo impide, pero no hay API ni licencia. Alternativa oficial verificada: MIVAU valor tasado (provincial, trimestral, 1995T1-2026T2), con mediana de correlación de tasas interanuales 0,79 y ratio de niveles mediano 1,00. |
| **ALTA** | **Transmisiones_Total mezcla dos fuentes**: 2005-2006 de un XLS del Ministerio ("Número total de transacciones inmobiliarias de viviendas", origen notarial) y 2007-2025 de INE ETDP (compraventas de viviendas inscritas en registros). Conceptos y fechas de referencia distintos (firma vs inscripción) → posible escalón en 2007. 2007-2024 coincide al 100 % con INE 6150; 2025 solo 23 % (revisión de provisionales, hasta 333 operaciones). |
| **MEDIA** | **IPC del panel = tasa de variación anual (%)**, no índice (nombre engañoso). Coincide al 100 % con INE 50913 (base 2021). La base 2025 (tabla 76136) cambia el 1,2 % de los valores históricos (hasta 0,27 pp). |
| **MEDIA** | **Poblacion mezcla Padrón (2005-2021, tabla 2852 congelada) y ECP (2022-2025)**. Ambas coinciden al 100 % con su fuente, pero son conceptos distintos (empadronados vs residentes): en 2005 el Padrón supera a la ECP en +1,3 % (mediana). |
| **MEDIA** | **Revisiones no incorporadas**: PIB_pc 2023-2024 (0 % coincidencia; máx. 2.062 €, Salamanca 2024), tasa_ahorro 2023T1-2025T3 (hasta 0,7 pp), Transmisiones 2025. Además PIB_pc 2025 provincial **todavía no existe** (CRE solo publica 2025 para CCAA). |
| **MEDIA** | Hipotecas_Total = **total fincas** (rústicas + urbanas: viviendas, solares, otros). Para demanda hipotecaria residencial procede la naturaleza "Viviendas" (misma tabla). |
| **BAJA** | tasa_ahorro es **no desestacionalizada** (CTNFSI11271, oscila 0,1 ↔ 16,7). Existe la serie ajustada CTNFSI11270. |
| **BAJA** | Fiscalidad del asesor (`web scrapping/datos_fiscales_scraped/`) procede de una web privada (financialtools.web.app) y contiene tipos desactualizados o erróneos (ver §5). |

Variables que **coinciden exactamente** con su fuente oficial: Tasa_Paro (100 %, INE 65349), Edad_Media (100 %, INE 3199),
Indice_Mano_Obra (100 %, INE 8377), Poblacion 2005-2021 (100 %, INE 2852) y 2022-2025 (100 %, ECP), IPC (100 %, INE 50913),
Euribor (máx. 0,012 pp, revisiones de datos diarios), APRC mensual (0 diferencias en 252 meses).

---

## 2. Tabla por variable

Prioridad de recomendación: API > descarga oficial > servicio > scraping > manual.

| Variable panel | Fuente actual (v1) | Mejor fuente oficial (verificada) | Endpoint / id | Geo · freq · histórico | Retraso publicación (medido) | Revisiones / vintages | Comparación numérica | Recomendación |
|---|---|---|---|---|---|---|---|---|
| Precio_m2 | Tinsa IMIE (scraping web) | MIVAU Valor tasado vivienda libre | `cdn.mivau.gob.es/.../VDP006_01.csv` (datos.gob.es e05233601) | Provincia · Q · 1995T1-2026T2 | ≈2,5 meses (2026T2 → 17-09-2026) | Sobrescribe; sin vintages | Corr. niveles mediana 0,92 (mín 0,50 Ourense); corr. yoy mediana 0,79 (mín 0,38 Cáceres); ratio Tinsa/MIVAU mediano 1,00 (0,85-1,10) | **Descarga oficial MIVAU** como serie principal; Tinsa solo con permiso. Arbitrar (§4) |
| Euribor | BCE `FM.Q.U2.EUR.RT.MM.EURIBOR1YD_.HSTA` (ecbdata) | Igual (correcto: 12m, media trimestral de diarios) | ECB API | Zona euro · Q/M · 1994- (último 2026Q3 / 2026-10) | 1 día hábil | `includeHistory=true` disponible (4 vintages) | Máx. 0,0118 pp; FM.Q vs media de FM.M: máx. 0,028 pp | **API** (mantener). Alternativa BdE `be1901.csv` D_1NBAF472 |
| Spread_Hipotecas | APRC `MIR.M.ES.B.A2C.A.C.A.2250.EUR.N` media trimestral − Euribor | APRC es correcto como "TAE nuevas operaciones vivienda ES"; para spread sobre Euribor usar AAR variable ≤1a `MIR.M.ES.B.A2C.F.R.A.2250.EUR.N` (o IRPH BdE D_1T9H0000) | ECB API | Nacional · M · 2003-01 → 2026-09 | ≈2 meses (2025-12 → 2026-03-04) | **Vintages vía includeHistory** (12 en 2025, sin cambios de valor) | Panel = API ±0,012 pp | **API**; redefinir spread (arbitrar) |
| IPC | INE (CSV de 76136/50913) variación anual CCAA | INE 76136 (base 2025) / 50913 (base 2021, hasta 2025-12) | `DATOS_TABLA/76136` | CCAA · M · 2002- (último 2026-10) | ≈13 días | Cambio de base | 100 % vs 50913; 98,8 % vs 76136 | **API**; renombrar a `IPC_var_anual` o usar índice |
| Tasa_Paro | INE EPA CSV | INE EPA 65349 (= 72989; 3996 parada en 2023T4) | `DATOS_TABLA/65349` | Provincia · Q · 2002T1-2026T3 | ≈4 semanas | Solo última versión | 100 % | **API** |
| PIB_pc | INE CRE xlsx (rev. 2024) | INE CRE 82285 (= 80110) | `DATOS_TABLA/82285` | Provincia · A · 2000-2024 (CCAA hasta 2025) | provincial ≈ t+20 meses (aprox.) | Revisa 2 últimos años | 2005-2022 100 %; 2023-2024 0 % (revisados) | **API**; no usar 2025 provincial (no existe) |
| tasa_ahorro | INE CTNFSI (NSA) | INE CTNFSI11271 (NSA) / CTNFSI11270 (SA); Eurostat `nasq_10_ki` SRG_S14_S15 | `DATOS_SERIE/CTNFSI11271` | Nacional · Q · 1999-2026T2 | ≈3 meses | Revisa ~3 años | 88 % iguales; difiere 2023-2025 hasta 0,7 pp | **API**; preferir SA |
| Hipotecas_Total | INE HPT CSV (total fincas) | INE 76317 (alias 3200) | `DATOS_TABLA/76317` | Provincia · M · 2003-2026-08 | ≈8 semanas | Provisionales | 87,9 % iguales; **error de parseo** (§1) | **API**; corregir parseo; valorar naturaleza "Viviendas" |
| Indice_Materiales | INE 8378 (base 1964) media de 14 series | INE 8381/77209 (base 2011, Total Nacional) o series individuales | `DATOS_TABLA/8378` | Nacional (Pen.+Bal./Canarias) · M · 1995-2026-03 | ≈6 meses | — | Reproduce la media de 14 series (9e-13) | **API**; redefinir (arbitrar) |
| Indice_Mano_Obra | INE 8377 | Igual | `DATOS_TABLA/8377` (IMM1) | Nacional · M · 1995-2026-03 | ≈6 meses | — | 100 % | **API**; ojo: NaN 2025T2-T4 eran por retraso (hoy hay datos hasta 2026-03) |
| Poblacion | INE 2852 (≤2021) + ECP (2022-25) | INE ECP 59591/82104 (serie homogénea 2002-2026) | `DATOS_SERIE/ECP181529` etc. | Provincia · Q · 2002-01-01 → 2026-10-01 | ≈6 semanas | Retropolada | 100 % con cada fuente; Padrón−ECP +1,3 % (2005) → −0,08 % (2021) | **API ECP** (homogénea) o Padrón por series (arbitrar concepto) |
| Edad_Media | INE IDB 3199 | Igual | `DATOS_TABLA/3199` | Provincia · A · 1975-2025 | ≈11 meses | — | 100 % | **API** |
| Pob_Ext | INE Padrón (≤2022) + Min. Inclusión (2023-25) | INE ECP 59591 "Extranjera" | `DATOS_SERIE/ECP181397` (Madrid) etc. | Provincia · Q · 2002-2026 | ≈6 semanas | Retropolada | 0 % iguales; mediana +0-7 % (2005-2022), **+17 % 2023** | **API ECP** (elimina la ruptura) |
| Transmisiones_Total | MIVAU XLS (2005-06) + INE ETDP (2007-25) | INE ETDP 6150 (compraventa viviendas, General) | `DATOS_TABLA/6150` | Provincia · M · 2007-01 → 2026-09 | ≈7 semanas | Provisionales | 2007-2024 100 %; 2025 23 % | **API**; arrancar en 2007 o usar MIVAU VDP003 completo (arbitrar) |

Notas de concepto verificadas (punto 4 del encargo):
- Euribor: `FM.Q...HSTA` = "Euribor 1-year – Historical close, average of observations through period" → Euribor 12m, media de datos diarios del trimestre. Correcto. (Euribor es benchmark de EMMI; BCE/BdE lo redistribuyen citando sus términos de uso.)
- APRC `MIR.M.ES.B.A2C.A.C.A.2250.EUR.N`: "Spain, APRC, MFIs, lending for house purchase ..., Total initial rate fixation, New business, Households & NPISH" → TAE de nuevas operaciones de vivienda en España, todas las fijaciones. Correcto como tipo medio de nuevas hipotecas; inadecuado como "spread sobre Euribor".
- Hipotecas_Total: "Total fincas. Número de hipotecas" → incluye rústicas y urbanas no residenciales.
- tasa_ahorro: "Hogares e ISFLSH. Tasa de ahorro. Datos no ajustados" → hogares (S.14+S.15), bruta, NSA.
- Indice_Materiales: INE op. IMM "Índices de precios de materiales (base enero 1964)", elaborados para la revisión de precios de contratos del sector público.
- Transmisiones_Total: compraventas de **viviendas** (no total fincas: frente a INE 6146 el 0 % coincide; Madrid 2007T1 24.366 vs 78.763 fincas).

---

## 3. Fecha de referencia vs fecha de publicación (look-ahead bias)

Retrasos medidos con la API (`Ultima_Modificacion` de INE vs último periodo; `validFromDate` del BCE):

| Serie | Último dato disponible a 2026-11-21 | Retraso típico | Implicación para backtesting |
|---|---|---|---|
| Euribor (BCE/EMMI) | 2026-10 | 1 día | Usable en t |
| APRC MIR ES | 2026-09 | ≈2 meses | En t solo se conoce t−2 (mensual) → trimestre t se completa ≈ mes 2 de t+1 |
| IPC CCAA | 2026-10 | ≈13 días | Usable con 1 mes de desfase |
| EPA paro provincial | 2026T3 | ≈4 semanas | t+1 mes |
| Hipotecas INE | 2026-08 | ≈8 semanas | t+2 meses; provisionales |
| Compraventas ETDP | 2026-09 | ≈7 semanas | t+2 meses; provisionales |
| ECP población | 2026-10-01 | ≈6 semanas | Ok |
| Tasa de ahorro CTNFSI | 2026T2 | ≈3 meses | t+1 trimestre; se revisa |
| Mano de obra / materiales | 2026-03 | ≈6 meses | Desfase de 2 trimestres |
| MIVAU valor tasado | 2026T2 | ≈2,5 meses | t+1 trimestre |
| Edad media (IDB) | 1-ene-2025 | ≈11 meses | Anual con 1 año de desfase |
| PIB pc provincial (CRE) | 2024 | ≈20 meses (aprox.) | Valor anual de t no disponible hasta t+2 |

Vintages:
- **BCE: SÍ** expone vintages en la API (`includeHistory=true`, SDMX-ML con `validFromDate`); se conservan versiones recientes (12 para MIR en 2025; 4 para Euribor). Script `ecb_vintages.py`.
- **INE Tempus3**: solo sirve la última versión (no hay parámetro de versión). Para tiempo real habría que guardar snapshots propios (contrato `data/raw/<fuente>/<YYYYMMDD>/`).
- **Eurostat**: sin vintages en la API de diseminación (campo `updated` del dataset). No se verificó la Real-Time Database de euro-indicadores.
- **MIVAU**: fichero sobrescrito (Last-Modified 2026-09-17).
- ALFRED responde (200) pero no se verificó cobertura útil para España; no se recomienda.

Recomendación: el panel v2 debe guardar `fecha_publicacion` por (serie, periodo) y construir los predictores con el desfase de la tabla anterior.

---

## 4. Tinsa vs alternativas oficiales (Precio_m2)

Metodologías (no se recomienda sustituir sin entender las diferencias):

| Fuente | Qué mide | Geo | Freq | Acceso |
|---|---|---|---|---|
| Tinsa IMIE Mercados Locales | Valor de tasación €/m² de tasaciones de Tinsa (una sociedad) | Prov./municipio | Q, 2001- | Web; sin API; condiciones prohíben explotación |
| MIVAU Valor tasado | Valor tasado medio €/m² de vivienda libre, tasaciones de todas las sociedades homologadas | Provincia | Q, 1995- | CSV oficial (datos.gob.es) |
| INE IPV | Índice de precios de transacción (datos notariales, hedónico) | CCAA | Q (histórico no verificado aquí) | API (tabla 80270, id listado en TABLAS_OPERACION/15) |
| Notariado (Portal Estadístico) | Precio €/m² de compraventas escrituradas | Prov./municipio | M | Web; `penotariado.com` respondió 502 desde aquí → **pendiente** |
| Registradores (ERI) | Precio €/m² inscrito | CCAA/prov. | Q | Informes PDF; **pendiente** |

Comparación Tinsa (panel) vs MIVAU (52 provincias, 2005T1-2025T4; `samples/tinsa_vs_mivau_por_provincia.csv`):
correlación de niveles mediana 0,92 (mín. 0,50 Ourense), correlación de tasas interanuales mediana 0,79
(mín. 0,38 Cáceres; 0,55 Navarra; 0,58 Lugo/Ceuta/Zamora), ratio Tinsa/MIVAU mediano 1,00 (rango 0,85-1,10).
Ejemplos 2025T4: Madrid 3.805 vs 3.902 €/m² (yoy 19,8 % vs 15,8 %); Barcelona 2.876 vs 3.083; Málaga 2.701 vs 2.897;
Valencia 1.740 vs 1.832. Ambas son de tasación (concepto muy próximo); MIVAU es oficial, gratuita, más larga y no requiere scraping.
**Decisión a arbitrar**: adoptar MIVAU como `Precio_m2` (rompe comparabilidad con resultados v1, niveles casi iguales) o
mantener Tinsa v1 congelado como benchmark con solicitud formal de permiso.

---

## 5. Fiscalidad

No existe API oficial de tipos impositivos. La fuente primaria automatizable es la **API de legislación consolidada del BOE**
(`/datosabiertos/api/legislacion-consolidada/id/{ID}/texto`), que devuelve cada artículo con todas sus versiones y
`fecha_vigencia` → base natural para la tabla de vigencias. El compendio de Hacienda "Tributación Autonómica. Medidas 2026"
(Cap. II) es la referencia consolidada, pero `hacienda.gob.es` y `sede.agenciatributaria.gob.es` no fueron accesibles
desde este entorno (conexión cerrada por el proxy) → **pendiente de contraste**.

Esquema propuesto (`data/metadata/fiscalidad_vigencias.csv`):
`ccaa_code, ccaa, impuesto (ITP|AJD|IVA|IVA_AJD|NOTARIA|REGISTRO), modalidad, tipo (decimal) | tarifa_json, base (precio|valor_real|responsabilidad_hipotecaria), condiciones (vivienda_habitual, edad_max, valor_max, VPO, familia_numerosa...), progresivo (bool), vigente_desde, vigente_hasta, norma, boe_id, articulo, url_fuente, verificado (bool), fecha_verificacion`.

Tipos generales vigentes verificados en el texto consolidado del BOE (fecha de consolidación indicada en `samples/fiscal_boe_versions.csv`):

| CCAA | ITP general vivienda (TPO) | Vigente desde | AJD general documentos notariales | Norma / artículo |
|---|---|---|---|---|
| Andalucía | 7 % | 2021-10-27 | 1,2 % | Ley 5/2021, arts. 41 y 49 (BOE-A-2021-17915) |
| Aragón | Escala: 8 % hasta 400.000; 8,5 %; 9 %; 9,5 %; 10 % > 750.000 | 2015-12-30 | 1,5 % | DLeg 1/2005, arts. 121-1 y 122-1 |
| Asturias | Tarifa: 8 % (≤300.000), 9 % (≤500.000), 10 % | 2014-10-30 | 1,2 % | DLeg 2/2014, arts. 26 y 34 |
| Illes Balears | Tarifa (tipo medio): 8 % ≤400.000; 9 %; 10 %; 12 %; 13 % > 2.000.000 | 2026-06-14 (última versión) | 1,5 % | DLeg 1/2014, arts. 10 y 15 |
| Canarias | 6,5 % | 2026-01-01 (versión) | 0,75 % (1 % si sujeto a IGIC/IVA) | DLeg 1/2009, arts. 31 y 36 |
| Cantabria | **9 %** | 2026-05-01 | 1,5 % (préstamos hipotecarios 2 %) | DLeg 62/2008, arts. 9 y 13 |
| Castilla y León | 8 % (10 % sobre el exceso de 250.000) | 2013-09-19 / 2022-12-13 | 1,5 % | DLeg 1/2013, arts. 24-25 (consolidado a 2024-07-17) |
| Cataluña | Tarifa (tipo medio): 10 % ≤600.000; 11 %; 12 %; 13 % > 1.500.000 | versión 2026-07-14 | **no verificado** | DLeg 1/2024, art. 641-1 |
| C. Valenciana | 9 % (11 % si valor > 1.000.000) | versión 2026-08-11 | 1,4 % ("demás casos") | Ley 13/1997, arts. 13 y 14 |
| Extremadura | Tarifa: 8 % ≤360.000; 10 %; 11 % > 600.000 | 2018-05-24 | 1,5 % | DLeg 1/2018, arts. 36 y 46 |
| Galicia | **8 %** | 2026-01-01 | 1,5 % | DLeg 1/2011, arts. 14 y 15 |
| Madrid | 6 % | 2014-01-01 | 0,75 % | DLeg 1/2010, arts. 28 y 36 |
| La Rioja | 7 % | 2017-10-31 | **no verificado** (art. 48) | Ley 10/2017, art. 44 |
| Ceuta / Melilla | 6 % estatal con bonificación 50 % (inmuebles allí situados) → 3 % efectivo | 2003-01-01 | 0,5 % estatal con bonificación 50 % | RDLeg 1/1993, arts. 11, 31.2 y 57 bis |
| Murcia | **no verificado** | — | **no verificado** | DLeg 1/2010 (BOE-A-2011-10542) |
| Castilla-La Mancha, Navarra, Álava, Bizkaia, Gipuzkoa | **no verificados** (normativa foral / no consolidada en BOE en esta prueba) | | | |

Discrepancias con `web scrapping/datos_fiscales_scraped/itp_por_ccaa.csv`: Aragón, Asturias, Baleares, Cataluña y Extremadura
son **tarifas progresivas** (el CSV usa un tipo plano); Cantabria 10 % (BOE: 9 % desde 2026-05-01); Galicia 10 % (BOE: 8 % desde 2026-01-01);
C. Valenciana 10 % (BOE: 9 %); Ceuta/Melilla 6 % (efectivo 3 %). AJD: Canarias 1,0 (BOE 0,75 % general), Valencia 1,5 (BOE 1,4 %),
Madrid 0,75 ✓, Andalucía 1,2 ✓, Asturias 1,2 ✓, Ceuta/Melilla 0,5 (efectivo 0,25 %).
El AJD de la escritura de préstamo hipotecario lo paga el prestamista desde el RDL 17/2018 (no repercutir al comprador en el asesor) — no verificado en esta auditoría.
IVA vivienda nueva 10 % (4 % VPO régimen especial) y aranceles (RD 1426/1989 y RD 1427/1989) **no verificados** aquí: pendientes de consulta con la misma API del BOE.
Los tipos "jóvenes" del CSV no se han verificado salvo Andalucía (3,5 % ≤35 años y valor ≤150.000, art. 43, vigente 2026-01-01).

---

## 6. Proyecciones externas (última edición a 2026-11-21)

| Organismo | Edición | URL | Estado |
|---|---|---|---|
| BCE staff (zona euro) | Septiembre 2026 (+ anexo xlsx) | https://www.ecb.europa.eu/press/projections/html/ecb.projections202609_ecbstaff~8e340fc69d.en.html | Verificado (página BCE). Próxima: Eurosistema dic-2026 |
| Banco de España | Proyecciones e informe trimestral 3T 2026 (cierre 24-sep-2026) | https://www.bde.es/wbe/es/publicaciones/analisis-economico-investigacion/proyecciones-macro-informe-trimestral/proyecciones-e-informe-trimestral-de-la-economia-espanola-tercer-trimestre-2026.html | Localizado por búsqueda web; no descargado |
| FMI WEO | Octubre 2026 (13-oct-2026) | https://www.imf.org/en/Publications/WEO/issues/2026/10/13/world-economic-outlook-october-2026 | Localizado; la API DataMapper devuelve 403 desde este entorno |

Son proyecciones nacionales/zona euro: sirven como escenario exógeno (Euribor, IPC, PIB), no como dato provincial.

---

## 7. Decisiones a arbitrar

1. `Precio_m2`: MIVAU (oficial, descargable) vs Tinsa (permiso). Recomendación: MIVAU.
2. `Spread_Hipotecas`: mantener APRC−Euribor (documentando el sesgo) o usar AAR variable ≤1 año − Euribor / IRPH − Euribor.
3. `Indice_Materiales`: sustituir la media de niveles por una serie concreta o un índice agregado con pesos.
4. `Poblacion` y `Pob_Ext`: adoptar ECP homogénea 2002-2026 (recomendado) frente a Padrón + Ministerio de Inclusión.
5. `Transmisiones_Total`: empezar en 2007 (INE homogéneo) o usar MIVAU VDP003 para toda la serie (origen notarial).
6. `Hipotecas_Total`: total fincas vs viviendas.
7. `tasa_ahorro`: NSA vs SA. `IPC`: tasa vs índice (y base 2021 vs 2025).
8. Política de vintages/snapshots y desfases de publicación en el pipeline v2.

## 8. Pendientes (no verificados desde este entorno)
Hacienda "Tributación Autonómica 2026" (host inaccesible), AEAT, Notariado (penotariado.com 502), Registradores (ERI),
Ministerio de Inclusión (403), FMI API (403), SEPE/Seguridad Social/OCDE/Catastro (no necesarios para las 14 variables),
tipos de Murcia, Castilla-La Mancha, forales, AJD Cataluña y La Rioja, aranceles notariales/registrales e IVA.

## 9. Verificación solicitada por coordinación: AI Act (Banca)
Afirmación: "el Reglamento (UE) 2026/1744 aplaza al 2/12/2027 las obligaciones de alto riesgo del anexo III del AI Act".
**Verificado en EUR-Lex** (https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32026R1744, consultado 2026-11-22):
Reglamento (UE) 2026/1744 de 8 de julio de 2026 ("Ómnibus digital sobre IA"), modifica el Reglamento (UE) 2024/1689.
El texto indica: "procede fijar la fecha de aplicación del capítulo III, secciones 1, 2 y 3 el 2 de diciembre de 2027 en el caso
de los sistemas de IA clasificados como de alto riesgo en virtud del artículo 6, apartado 2, y el anexo III" (y 2 de agosto de 2028
para los del anexo I). Nota: la cita procede de un considerando; no se revisó el artículo dispositivo concreto que modifica el art. 113.
