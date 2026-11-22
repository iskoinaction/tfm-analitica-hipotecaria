"""Configuración central del pipeline de datos v2 (rutas, red, catálogo de datasets, rangos y dependencias).

Todo lo que identifica una serie (tabla INE, clave SDMX del BCE, dataset de Eurostat) vive aquí y se exporta a
``data/metadata/series_catalog.yaml``; los conectores no contienen ids de series.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
STAGING = DATA / "staging"
PROCESSED = DATA / "processed"
METADATA = DATA / "metadata"
ARTIFACTS_DQ = ROOT / "artifacts" / "data_quality"
V1_DATASET = ROOT / "notebooks acabados" / "dataset_final_tfm.csv"
V1_INPUTS = ROOT / "Datos ya metidos"

USER_AGENT = "tfm-analitica-hipotecaria-etl/2.0 (proyecto academico; lectura de datos publicos)"
HTTP_TIMEOUT = (10, 90)          # (conexión, lectura) en segundos
HTTP_RETRIES = 4                 # reintentos ante 429/5xx/errores de red
HTTP_BACKOFF = 1.5               # espera = backoff * 2**intento
RATE_LIMIT_PER_SEC = {"servicios.ine.es": 4.0, "data-api.ecb.europa.eu": 2.0,
                      "ec.europa.eu": 2.0, "www.tinsa.es": 0.5, "default": 2.0}

PERIOD_START = "2005Q1"          # inicio del panel v2
DOWNLOAD_FROM = "20020101"       # se descarga algo de historia previa para lags

INE_BASE = "https://servicios.ine.es/wstempus/js/ES"
ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


@dataclass(frozen=True)
class VarSpec:
    """Una variable de salida: cómo se reconoce en la fuente y cómo se agrega/valida."""
    name: str
    match: dict                    # {T3_Variable: Nombre} (INE) o etiqueta lógica
    unit: str
    agg_q: str                     # sum | mean | last | none (ya trimestral) | annual
    valid_range: tuple
    description: str
    integer: bool = False          # conteos: detector de formato numérico (decimales prohibidos)


@dataclass(frozen=True)
class DatasetSpec:
    key: str                       # id interno del dataset (nombre de fichero en staging)
    source: str                    # ine | ecb | eurostat | tinsa | mivau | legacy_v1
    ref: str                       # tabla INE / clave SDMX / dataset Eurostat
    freq: str                      # M | Q | A | S (fecha puntual de stock)
    geo_vars: tuple                # T3_Variable(s) que contienen la geografía (INE)
    variables: tuple               # VarSpec
    base_filter: dict = field(default_factory=dict)
    methodology: str = ""
    publication_lag: str = ""
    operation: str = ""            # código de operación INE (para Ultima_Modificacion)
    url_doc: str = ""
    optional: bool = False


GEO_PROV = ("Provincias",)
GEO_ALL = ("Provincias", "Comunidades y Ciudades Autónomas", "Total Nacional", "Totales Territoriales")

DATASETS: list[DatasetSpec] = [
    DatasetSpec(
        "ine_hipotecas", "ine", "3200", "M", ("Provincias", "Total Nacional"),
        (
            VarSpec("hipotecas_viviendas_num", {"Naturaleza de la finca": "Viviendas", "Concepto financiero": "Número de hipotecas"},
                    "número", "sum", (0, 60000), "Hipotecas constituidas sobre viviendas (número). Objetivo principal v2.", True),
            VarSpec("hipotecas_viviendas_importe", {"Naturaleza de la finca": "Viviendas", "Concepto financiero": "Importe de hipotecas"},
                    "miles de euros", "sum", (0, 2e7), "Importe de hipotecas constituidas sobre viviendas."),
            VarSpec("hipotecas_fincas_total_num", {"Naturaleza de la finca": "Total fincas", "Concepto financiero": "Número de hipotecas"},
                    "número", "sum", (0, 80000), "Hipotecas constituidas sobre el total de fincas (comparable con Hipotecas_Total v1).", True),
        ),
        {"Tipo de muestreo": "Base nueva. Mensual"},
        "Estadística de Hipotecas (HPT), datos procedentes de los Registros de la Propiedad. Flujo mensual.",
        "≈2 meses tras el mes de referencia; datos del último año provisionales", "HPT",
        "https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736170236"),
    DatasetSpec(
        "ine_etdp_compraventas", "ine", "6150", "M", ("Provincias", "Total Nacional"),
        (VarSpec("compraventas_viviendas_num", {"Estado de la vivienda": "General", "Título de adquisición": "Compraventa", "Tipo de dato": "Número"},
                 "número", "sum", (0, 80000), "Compraventas de viviendas inscritas (ETDP, régimen y estado: general).", True),),
        {}, "Estadística de Transmisiones de Derechos de la Propiedad (ETDP), Registros de la Propiedad. Disponible desde 2007.",
        "≈2 meses", "ETDP", "https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736171438"),
    DatasetSpec(
        "ine_epa_paro", "ine", "65349", "Q", ("Provincias", "Total Nacional"),
        (VarSpec("tasa_paro", {"Tipo de dato": "Tasa de paro de la población", "Sexo": "Ambos sexos", "Nacionalidad": "Total"},
                 "%", "none", (0, 50), "Tasa de paro EPA (ambos sexos)."),),
        {}, "Encuesta de Población Activa; tasas trimestrales provinciales (error muestral relevante en provincias pequeñas).",
        "≈4 semanas tras el trimestre", "EPA", "https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736176918"),
    DatasetSpec(
        "ine_ipc", "ine", "76136", "M", ("Comunidades y Ciudades Autónomas", "Totales Territoriales"),
        (VarSpec("ipc_var_anual", {"Grupos ECOICOP": "Índice general", "Índices y Tasas": "Variación anual"},
                 "%", "mean", (-5, 15), "IPC índice general, variación anual (media de los meses del trimestre). Ámbito CCAA."),
         VarSpec("ipc_indice", {"Grupos ECOICOP": "Índice general", "Índices y Tasas": "Índice"},
                 "índice base 2025=100", "mean", (40, 200), "IPC índice general (base 2025), media trimestral. Ámbito CCAA.")),
        {}, "IPC base 2025 (tabla vigente 76136, series enlazadas por el INE desde 2002; sin empalmes propios).", "≈2 semanas tras el mes", "IPC",
        "https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736176802"),
    DatasetSpec(
        "ine_ecp_poblacion", "ine", "59591", "S", ("Provincias", "Total Nacional"),
        (VarSpec("poblacion", {"Totales de edad": "Todas las edades", "Nacionalidad": "Total", "Sexo": "Total", "Tipo de dato": "Número"},
                 "personas", "annual", (20000, 1e7), "Población residente (ECP) a 1 de enero.", True),
         VarSpec("poblacion_extranjera", {"Totales de edad": "Todas las edades", "Nacionalidad": "Extranjera", "Sexo": "Total", "Tipo de dato": "Número"},
                 "personas", "annual", (0, 2e6), "Población residente de nacionalidad extranjera (ECP) a 1 de enero. Fuente única homogénea.", True)),
        {"Conceptos demógraficos": "Población"},
        "Estadística Continua de Población (ECP); stock a fecha (1 de enero/1 de julio, trimestral en años recientes).",
        "≈1-2 meses; datos recientes provisionales", "ECP",
        "https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736177095"),
    DatasetSpec(
        "ine_edad_media", "ine", "3199", "A", ("Provincias", "Totales Territoriales"),
        (VarSpec("edad_media", {"Conceptos demógraficos": "Edad media de la población", "Sexo": "Ambos sexos", "Tipo de dato": "Dato base"},
                 "años", "annual", (30, 60), "Edad media de la población a 1 de enero."),),
        {}, "Indicadores demográficos básicos.", "≈6 meses", "IDB", ""),
    DatasetSpec(
        "ine_cre_pib_pc", "ine", "82285", "A", ("Provincias", "Comunidades y Ciudades Autónomas", "Totales Territoriales"),
        (VarSpec("pib_pc", {"Tipo de dato": "Dato base", "SALDOS CONTABLES": "Producto interior bruto a precios de mercado per capita"},
                 "euros corrientes", "annual", (8000, 90000), "PIB a precios de mercado per cápita (Contabilidad Regional, solo publicado)."),),
        {}, "Contabilidad Regional de España (CRE) base 2021; provincias con ~2 años de retraso, CCAA con avance.",
        "Diciembre t+1 (CCAA avance); provincias t+2", "CRE",
        "https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736167628"),
    DatasetSpec(
        "ine_ipv", "ine", "80270", "Q", ("Comunidades y Ciudades Autónomas", "Totales Territoriales"),
        (VarSpec("ipv_general_indice", {"General, vivienda nueva y de segunda mano": "General", "Índices y Tasas": "Índice"},
                 "índice base 2015=100", "none", (20, 300), "Índice de Precios de Vivienda (INE), general. Desde 2007."),),
        {}, "IPV (precios de transacción, notarios).", "≈10 semanas", "IPV", ""),
    DatasetSpec(
        "ine_cntr_pib", "ine", "67821", "Q", ("Total Nacional",),
        (VarSpec("pib_nominal_meur", {"Corrección de efectos": "Datos no ajustados de estacionalidad y calendario", "SALDOS CONTABLES": "Producto interior bruto a precios de mercado", "Tipo de dato": "Dato base"},
                 "millones de euros corrientes", "none", (1e5, 1e6), "PIB trimestral nominal (CNTR, no ajustado)."),
         VarSpec("pib_nominal_meur_sa", {"Corrección de efectos": "Datos ajustados de estacionalidad y calendario", "SALDOS CONTABLES": "Producto interior bruto a precios de mercado", "Tipo de dato": "Dato base"},
                 "millones de euros corrientes", "none", (1e5, 1e6), "PIB trimestral nominal (CNTR, ajustado de estacionalidad y calendario).")),
        {}, "Contabilidad Nacional Trimestral.", "≈30 días (avance)", "CNTR2010", ""),
    DatasetSpec(
        "ine_cntr_pib_vol", "ine", "67822", "Q", ("Total Nacional",),
        (VarSpec("pib_volumen_indice", {"Corrección de efectos": "Datos no ajustados de estacionalidad y calendario", "SALDOS CONTABLES": "Producto interior bruto a precios de mercado", "Tipo de dato": "Dato base"},
                 "índice de volumen encadenado", "none", (50, 200), "PIB trimestral en volumen encadenado (no ajustado)."),
         VarSpec("pib_volumen_indice_sa", {"Corrección de efectos": "Datos ajustados de estacionalidad y calendario", "SALDOS CONTABLES": "Producto interior bruto a precios de mercado", "Tipo de dato": "Dato base"},
                 "índice de volumen encadenado", "none", (50, 200), "PIB trimestral en volumen encadenado (ajustado).")),
        {}, "Contabilidad Nacional Trimestral.", "≈30 días (avance)", "CNTR2010", ""),
    DatasetSpec(
        "ine_tasa_ahorro", "ine", "SERIE:CTNFSI11271,CTNFSI11270", "Q", ("Total Nacional",),
        (VarSpec("tasa_ahorro_hogares", {}, "% de la renta disponible", "none", (-30, 40),
                 "Tasa de ahorro de hogares e ISFLSH, serie original no ajustada (CTNFSI11271)."),
         VarSpec("tasa_ahorro_hogares_sa", {}, "% de la renta disponible", "none", (-30, 40),
                 "Tasa de ahorro de hogares e ISFLSH, ajustada de estacionalidad y calendario (CTNFSI11270).")),
        {}, "Cuentas Trimestrales no Financieras de los Sectores Institucionales.", "≈3 meses", "CTNFSI", ""),
    DatasetSpec(
        "ine_mano_obra", "ine", "8377", "M", ("Total Nacional",),
        (VarSpec("indice_mano_obra_construccion", {"Materiales y Mano de Obra": "Mano de obra en la construcción"},
                 "índice base 1980", "mean", (100, 1000), "Índice de coste de mano de obra en la construcción (MIVAU, difundido por el INE), media trimestral."),),
        {}, "Índices de costes del sistema de la construcción (Ministerio de Vivienda), tabla INE 8377.", "≈2-3 meses", "", ""),
    DatasetSpec(
        "eurostat_coste_construccion", "eurostat", "sts_copi_q", "Q", (),
        (VarSpec("indice_coste_construccion", {"geo": "ES", "indic_bt": "COST", "unit": "I21", "s_adj": "NSA"},
                 "índice 2021=100", "none", (5, 250),
                 "Índice general de costes de construcción de edificios residenciales nuevos (STS, Eurostat), sustituye a Indice_Materiales v1."),),
        {}, "Estadísticas coyunturales (STS) de Eurostat, dato remitido por España.", "≈3 meses", "", "https://ec.europa.eu/eurostat/databrowser/view/sts_copi_q/default/table"),
    DatasetSpec(
        "ecb_tipos", "ecb", "FM+MIR", "M", (),
        (VarSpec("euribor_12m", {"key": "FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA"}, "%", "mean", (-1, 7),
                 "Euríbor a 12 meses, media mensual; trimestral = media de los 3 meses."),
         VarSpec("tae_vivienda", {"key": "MIR/M.ES.B.A2C.A.C.A.2250.EUR.N"}, "%", "mean", (0, 10),
                 "TAE (APRC) de nuevas operaciones de préstamos a hogares para vivienda, España."),
         VarSpec("tedr_vivienda", {"key": "MIR/M.ES.B.A2C.A.R.A.2250.EUR.N"}, "%", "mean", (0, 10),
                 "Tipo sin comisiones (AAR/NDER) de nuevas operaciones de préstamos a hogares para vivienda, España.")),
        {}, "BCE: mercados financieros (FM) y estadísticas de tipos de interés de IFM (MIR).", "≈5 semanas (MIR)", "", "https://data.ecb.europa.eu/"),
    DatasetSpec(
        "mivau_valor_tasado", "mivau", "VDP006_01", "Q", (),
        (VarSpec("precio_m2_mivau_tasado", {"Régimen": "Libre"}, "€/m²", "none", (300, 8000),
                 "Valor tasado medio de vivienda libre €/m² (MIVAU, todas las tasaciones). Alternativa oficial a Tinsa."),),
        {}, "Estadística de Valor Tasado de Vivienda (IOE 20007), Ministerio de Vivienda y Agenda Urbana.",
        "≈2,5 meses", "", "https://datos.gob.es/apidata/catalog/dataset/e05233601-valor-tasado-de-la-vivienda.json"),
    DatasetSpec(
        "tinsa_precio", "tinsa", "legacy_v1_csv", "Q", (),
        (VarSpec("precio_m2_tinsa", {}, "€/m²", "none", (300, 8000), "Valor medio €/m² (Tinsa IMIE, provincias)."),),
        {}, "Tinsa IMIE General y Grandes Mercados. Por defecto se reutiliza el CSV v1 (snapshot sin fecha); el scraping es opcional y está desactivado: las condiciones de uso de tinsa.es prohíben la explotación sin autorización (10_source_catalog.yaml).",
        "≈1 mes", "", "https://www.tinsa.es/precio-vivienda/", optional=True),
]

DATASET_BY_KEY = {d.key: d for d in DATASETS}

# Variables derivadas (se calculan en build_master, no se descargan)
DERIVED = {
    "diferencial_tae_euribor": ("tae_vivienda - euribor_12m", "p.p.", "Diferencial TAE vivienda − Euríbor 12M (antes 'Spread_Hipotecas')"),
    "diferencial_tedr_euribor": ("tedr_vivienda - euribor_12m", "p.p.", "Diferencial tipo sin comisiones − Euríbor 12M"),
}

# Qué modelos dependen de cada variable (para la lista de recalibración del informe de actualización)
MODEL_DEPENDENCIES = {
    "hipotecas_viviendas_num": ["demand.rf_nacional", "demand.rf_provincial", "econometrics.var", "econometrics.vecm"],
    "hipotecas_fincas_total_num": ["demand.v1_comparison"],
    "hipotecas_viviendas_importe": ["demand.rf_provincial", "advisor.importe_medio"],
    "compraventas_viviendas_num": ["demand.rf_provincial", "forecasting.transmisiones"],
    "tasa_paro": ["demand.rf_provincial", "advisor.gbr_spread", "forecasting.paro"],
    "ipc_var_anual": ["advisor.gbr_spread", "demand.rf_provincial"],
    "ipc_indice": ["econometrics.real_prices"],
    "poblacion": ["demand.rf_provincial", "forecasting.poblacion", "nacional.weights"],
    "poblacion_extranjera": ["demand.rf_provincial", "forecasting.pob_ext"],
    "edad_media": ["demand.rf_provincial"],
    "pib_pc": ["advisor.gbr_spread", "econometrics.vecm", "forecasting.pib"],
    "precio_m2_mivau_tasado": ["econometrics.robustness_price", "forecasting.precio"],
    "precio_m2_tinsa": ["advisor.gbr_spread", "econometrics.vecm", "forecasting.precio"],
    "ipv_general_indice": ["econometrics.robustness_price"],
    "euribor_12m": ["advisor.gbr_spread", "econometrics.var", "econometrics.vecm", "demand.rf_nacional"],
    "tae_vivienda": ["advisor.gbr_spread"],
    "tedr_vivienda": ["advisor.gbr_spread"],
    "tasa_ahorro_hogares": ["demand.rf_nacional", "advisor.gbr_spread"], "tasa_ahorro_hogares_sa": ["econometrics.var"],
    "indice_mano_obra_construccion": ["demand.rf_provincial"],
    "indice_coste_construccion": ["econometrics.vecm", "demand.rf_provincial"],
    "pib_nominal_meur": ["econometrics.var"], "pib_volumen_indice": ["econometrics.var"],
}
