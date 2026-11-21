"""Configuración de la econometría v2: rutas, especificación y reglas de decisión.

Todas las decisiones de especificación están aquí (y se vuelcan en los metadatos
de los artefactos) para que la app y la documentación lean la misma fuente.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_PROCESSED = ROOT / "data" / "processed"
NATIONAL_V2 = DATA_PROCESSED / "nacional_trimestral.csv"
PANEL_V2 = DATA_PROCESSED / "panel_trimestral.csv"
V1FIX = DATA_PROCESSED / "v1_corrected" / "dataset_final_tfm_v1fix.csv"

# Fuentes de la construcción PROVISIONAL (solo desarrollo; los resultados finales salen de v2)
V1_DATASET = ROOT / "notebooks acabados" / "dataset_final_tfm.csv"
V1_HIP_RAW = ROOT / "Datos ya metidos" / "hipotecas_por_prov_men.csv"
INE_HPT_VIV = ROOT / "reports" / "audit" / "03_economia" / "data" / "ine_HPT34618.json"   # viviendas, número
INE_HPT_TOT = ROOT / "reports" / "audit" / "03_economia" / "data" / "ine_HPT34936.json"   # total fincas, número

PANEL_MODELADO_V2 = DATA_PROCESSED / "panel_modelado.csv"

# Mapeo explícito de columnas v2 (data/metadata/data_dictionary.csv). Si el esquema cambia, se cae
# a las reglas regex de data.resolve_columns y, ante ambigüedad, se lanza error.
V2_NATIONAL_COLMAP = {
    "period": "period",
    "hip_viv": "hipotecas_viviendas_num",            # INE 3200, objetivo principal v2
    "hip_tot": "hipotecas_fincas_total_num",         # robustez
    "precio": "precio_m2_tinsa_pond_pob",            # Tinsa IMIE, media provincial ponderada por población
    "precio_ipv": "ipv_general_indice",              # INE IPV (desde 2007), robustez
    "pib_nominal_sa": "pib_nominal_meur_sa",         # INE CNTR 67821, nominal, CVEC
    "poblacion": "poblacion_ecp",                    # INE ECP (stock semestral, sin interpolar)
    "euribor": "euribor_12m",
    "materiales": "indice_coste_construccion",       # Eurostat STS sts_copi_q (sustituye a Indice_Materiales v1)
}
V2_PANEL_COLMAP = {
    "prov_code": "prov_code", "period": "period", "hip_viv": "hipotecas_viviendas_num",
    "hip_tot": "hipotecas_fincas_total_num", "precio": "precio_m2_tinsa", "pib_pc": "pib_pc",
    "poblacion": "poblacion", "euribor": "euribor_12m", "materiales": "indice_coste_construccion",
}

ARTIFACTS = ROOT / "artifacts" / "econometrics"

SEED = 20240521
N_JOBS = 1

# Variables del sistema (nombres canónicos internos). Orden = orden de Cholesky de referencia (nb 4.2):
# de "más exógeno" a "más endógeno". Se informa además el rango sobre las 120 ordenaciones y las GIRF.
SYSTEM = ["log_materiales", "euribor", "log_pib_pc", "log_precio", "log_hipotecas"]
TARGET = "log_hipotecas"
LABELS = {
    "log_materiales": "Índice de costes de construcción residencial (log; v1: índice de materiales)",
    "euribor": "Euríbor 12m (%)",
    "log_pib_pc": "PIB per cápita (log)",
    "log_precio": "Precio vivienda m² (log)",
    "log_hipotecas": "Hipotecas sobre viviendas, número (log)",
}

SPEC = {
    "deterministic_case": 3,          # Johansen caso 3 = statsmodels deterministic='co' (constante no restringida)
    "sensitivity_cases": [2, 4],
    "seasonal_dummies": "centradas Q2-Q4, no restringidas",
    "impulse_dummies": ["2020Q2", "2020Q3"],   # estado de alarma COVID (cierre registral) y rebote
    "max_lags_selection": 6,
    "k_ar_diff_default": 1,
    "bootstrap_B_rank": 999,
    "bootstrap_B_irf": 499,
    "horizon": 20,
    "alpha_rank_decision": 0.10,       # regla del coordinador: si p_boot(r=0) >= 0.10 -> VAR en diferencias principal
    "band": [5, 95],
}

# Fechas de corte
START = "2005Q1"
