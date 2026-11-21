"""Configuración del forecasting v2 (demanda + proyecciones macro).

Todas las decisiones de protocolo están aquí y se vuelcan en los metadatos de los artefactos.
Las reglas de selección se fijan ANTES de ver el hold-out (pre-especificadas).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------- entradas v2 (Data Engineering)
DATA_PROCESSED = ROOT / "data" / "processed"
PANEL_V2 = DATA_PROCESSED / "panel_trimestral.csv"
PANEL_ANUAL_V2 = DATA_PROCESSED / "panel_anual.csv"
NATIONAL_V2 = DATA_PROCESSED / "nacional_trimestral.csv"
V1FIX = DATA_PROCESSED / "v1_corrected" / "dataset_final_tfm_v1fix.csv"

# ---------------------------------------------------------------- construcción PROVISIONAL (solo si no hay v2)
V1_DATASET = ROOT / "notebooks acabados" / "dataset_final_tfm.csv"
INE_3200_URL = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/3200?nult=300"

# ---------------------------------------------------------------- salidas
SCENARIOS_YAML = ROOT / "data" / "metadata" / "escenarios_macro.yaml"
FORECASTS_DIR = ROOT / "data" / "forecasts"
ART_FORECAST = ROOT / "artifacts" / "forecasting"
ART_DEMAND = ROOT / "artifacts" / "demand"
INPUT_CACHE = ART_DEMAND / "inputs"   # descargas cacheadas (INE 3200) con hash

SEED = 12345
N_JOBS = 2

# ---------------------------------------------------------------- protocolo de validación
# Ventana de SELECCIÓN: objetivos <= SEL_END. HOLD-OUT reservado: HOLDOUT_START..HOLDOUT_END (no interviene
# en ninguna decisión). Objetivos posteriores (si los datos llegan más allá de 2025Q4) = "oos_extra".
FIRST_ORIGIN_Q = pd.Period("2012Q4", freq="Q-DEC")
SEL_END_Q = pd.Period("2021Q4", freq="Q-DEC")
HOLDOUT_START_Q = pd.Period("2022Q1", freq="Q-DEC")
HOLDOUT_END_Q = pd.Period("2025Q4", freq="Q-DEC")
HORIZONS_Q = [1, 2, 4, 8]           # trimestres (tabla publicada)
HORIZONS_Q_PATH = list(range(1, 21))  # para intervalos empíricos de sendas (hasta 20 trimestres)

FIRST_ORIGIN_Y = 2012                # anual
SEL_END_Y = 2021
HOLDOUT_START_Y = 2022
HORIZONS_Y = [1, 2, 3]

PROJ_END_Q = pd.Period("2030Q4", freq="Q-DEC")
PROJ_END_Y = 2030

# Regla de selección pre-especificada: menor MASE medio (nacional) / mediana de MASE entre provincias
# (provincial) en la ventana de selección, por horizonte; desempate: menor RMSE.
SELECTION_RULE = ("Por horizonte, el modelo con menor MASE (media en serie nacional; mediana entre provincias en "
                  "paneles) en la ventana de selección (objetivos <= 2021Q4 / 2021). El hold-out 2022Q1-2025Q4 "
                  "(2022-2024 en anuales) se evalúa una sola vez tras fijar la elección y no modifica nada.")

# Cuantiles de los intervalos empíricos (errores logarítmicos de backtest por horizonte)
PI_LOW, PI_HIGH = 0.10, 0.90
