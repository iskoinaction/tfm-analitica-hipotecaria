import os
# Cargar .env desde el directorio del propio script (independiente del cwd)
from dotenv import load_dotenv as _load_dotenv
_load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
import io
import json
import uuid
import sys
import subprocess
import shutil
import ast
import math
import base64
import tempfile
import re
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from datetime import datetime
from google import genai
from google.genai import types as genai_types

# ML Imports (moved explicitly to global scope to prevent macOS thread deadlock)
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from sklearn.model_selection import cross_val_score
import shap

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'tfm_secret_key_fixed_12345')
_APP_USERNAME = os.environ.get('APP_USERNAME', 'caixabank')
_APP_PASSWORD = os.environ.get('APP_PASSWORD', 'caixabank')
app.config['UPLOAD_FOLDER'] = os.path.abspath(os.path.join(os.path.dirname(__name__), '..'))

# Buscar dataset_final_tfm.csv: primero en el directorio padre, luego en notebooks acabados
_tfm_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_candidate_paths = [
    os.path.join(_tfm_root, 'dataset_final_tfm.csv'),
    os.path.join(_tfm_root, 'notebooks acabados', 'dataset_final_tfm.csv'),
    os.path.join(app.config['UPLOAD_FOLDER'], 'dataset_final_tfm.csv'),
]
DATASET_PATH = next((p for p in _candidate_paths if os.path.exists(p)),
                    os.path.join(_tfm_root, 'dataset_final_tfm.csv'))
TIPOS_PATH = os.path.join(os.path.dirname(__file__), 'static', 'tipos_hipotecas.csv')
CUSTOM_CHARTS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'custom_charts')
CUSTOM_CHARTS_INDEX = os.path.join(CUSTOM_CHARTS_DIR, 'index.json')

os.makedirs(CUSTOM_CHARTS_DIR, exist_ok=True)
if not os.path.exists(CUSTOM_CHARTS_INDEX):
    with open(CUSTOM_CHARTS_INDEX, 'w') as f:
        json.dump([], f)

try:
    df = pd.read_csv(DATASET_PATH)
except Exception as e:
    df = pd.DataFrame()
    print(f"Warning: Could not load dataset: {e}")

try:
    df_tipos = pd.read_csv(TIPOS_PATH)
    df_tipos['year'] = df_tipos['TIME_PERIOD'].str[:4]
except Exception as e:
    df_tipos = pd.DataFrame()
    print(f"Warning: Could not load tipos CSV: {e}")

# ╔══════════════════════════════════════════════╗
# ║  CCAA / PROVINCE REFERENCE DATA             ║
# ╚══════════════════════════════════════════════╝

# Province → CCAA mapping (using dataset province names)
PROVINCE_TO_CCAA = {
    "Almeria": "Andalucia", "Cadiz": "Andalucia", "Cordoba": "Andalucia",
    "Granada": "Andalucia", "Huelva": "Andalucia", "Jaen": "Andalucia",
    "Malaga": "Andalucia", "Sevilla": "Andalucia",
    "Huesca": "Aragon", "Teruel": "Aragon", "Zaragoza": "Aragon",
    "Asturias": "Asturias",
    "Baleares": "Baleares", "Illes Balears": "Baleares",
    "Las Palmas": "Canarias", "Santa Cruz de Tenerife": "Canarias",
    "Cantabria": "Cantabria",
    "Albacete": "Castilla-La Mancha", "Ciudad Real": "Castilla-La Mancha",
    "Cuenca": "Castilla-La Mancha", "Guadalajara": "Castilla-La Mancha",
    "Toledo": "Castilla-La Mancha",
    "Avila": "Castilla y Leon", "Burgos": "Castilla y Leon",
    "Leon": "Castilla y Leon", "Palencia": "Castilla y Leon",
    "Salamanca": "Castilla y Leon", "Segovia": "Castilla y Leon",
    "Soria": "Castilla y Leon", "Valladolid": "Castilla y Leon",
    "Zamora": "Castilla y Leon",
    "Barcelona": "Cataluna", "Girona": "Cataluna",
    "Lleida": "Cataluna", "Tarragona": "Cataluna",
    "Alicante": "Comunidad Valenciana", "Castellon": "Comunidad Valenciana",
    "Valencia": "Comunidad Valenciana",
    "Badajoz": "Extremadura", "Caceres": "Extremadura",
    "La Coruna": "Galicia", "Lugo": "Galicia",
    "Ourense": "Galicia", "Pontevedra": "Galicia",
    "Madrid": "Madrid",
    "Murcia": "Murcia",
    "Navarra": "Navarra",
    "Alava": "Pais Vasco", "Guipuzcoa": "Pais Vasco", "Vizcaya": "Pais Vasco",
    "La Rioja": "La Rioja",
    "Ceuta": "Ceuta", "Melilla": "Melilla",
}

# ITP rates (second-hand), general rate per CCAA
ITP_POR_CCAA = {
    "Andalucia": 7.0, "Aragon": 8.0, "Asturias": 8.0, "Baleares": 8.0,
    "Canarias": 6.5, "Cantabria": 10.0, "Castilla-La Mancha": 9.0,
    "Castilla y Leon": 8.0, "Cataluna": 10.0, "Comunidad Valenciana": 10.0,
    "Extremadura": 8.0, "Galicia": 10.0, "Madrid": 6.0, "Murcia": 8.0,
    "Navarra": 6.0, "Pais Vasco": 4.0, "La Rioja": 7.0, "Ceuta": 6.0, "Melilla": 6.0,
}

# ITP reduced rate for young buyers (<=35) first home
ITP_JOVEN = {
    "Andalucia": 3.5, "Aragon": 5.0, "Asturias": 6.0, "Baleares": 6.0,
    "Canarias": 5.0, "Cantabria": 4.0, "Castilla-La Mancha": 5.0,
    "Castilla y Leon": 4.0, "Cataluna": 5.0, "Comunidad Valenciana": 6.0,
    "Extremadura": 6.0, "Galicia": 5.0, "Madrid": 6.0, "Murcia": 3.0,
    "Navarra": 5.0, "Pais Vasco": 4.0, "La Rioja": 4.0, "Ceuta": 6.0, "Melilla": 6.0,
}

# AJD rates per CCAA (%)
AJD_POR_CCAA = {
    "Andalucia": 1.2, "Aragon": 1.5, "Asturias": 1.2, "Baleares": 1.5,
    "Canarias": 1.0, "Cantabria": 1.5, "Castilla-La Mancha": 1.25,
    "Castilla y Leon": 1.5, "Cataluna": 1.5, "Comunidad Valenciana": 1.5,
    "Extremadura": 1.2, "Galicia": 1.5, "Madrid": 0.75, "Murcia": 1.5,
    "Navarra": 0.5, "Pais Vasco": 0.5, "La Rioja": 1.0, "Ceuta": 0.5, "Melilla": 0.5,
}

# Max financing % for young buyers by CCAA {ccaa: (max_pct, age_limit)}
YOUNG_FINANCING = {
    "Andalucia": (95, 35), "Aragon": (95, 35), "Asturias": (90, 35),
    "Baleares": (100, 35), "Canarias": (95, 35), "Cantabria": (90, 35),
    "Castilla-La Mancha": (90, 35), "Castilla y Leon": (97, 35),
    "Cataluna": (95, 35), "Comunidad Valenciana": (95, 35),
    "Extremadura": (95, 35), "Galicia": (100, 40), "Madrid": (95, 40),
    "Murcia": (100, 35), "Navarra": (90, 35), "Pais Vasco": (100, 40),
    "La Rioja": (100, 35), "Ceuta": (90, 35), "Melilla": (90, 35),
}


def _get_ccaa(province: str) -> str:
    """Return CCAA name for a province, with fuzzy matching."""
    if not province:
        return ""
    # Exact match
    if province in PROVINCE_TO_CCAA:
        return PROVINCE_TO_CCAA[province]
    # Fuzzy: strip accents simple approach
    for k, v in PROVINCE_TO_CCAA.items():
        if k.lower() in province.lower() or province.lower() in k.lower():
            return v
    return ""


def _notaria_registro(precio):
    """Estimate notary + registry fees based on property price."""
    brackets = [25000, 50000, 100000, 150000, 200000, 250000, 300000, 400000]
    notaria_vals = [600, 625, 675, 710, 750, 790, 830, 850]
    registro_vals = [395, 420, 445, 470, 510, 550, 590, 630]

    idx = len(brackets) - 1
    for i, b in enumerate(brackets):
        if precio <= b:
            idx = i
            break

    return notaria_vals[idx], registro_vals[idx]


def _calc_taxes(precio: float, ccaa: str, age: int, is_new_build: bool = False) -> dict:
    """
    Calculate purchase taxes and fees for a property.
    Returns dict with itemized breakdown and total.
    """
    is_young = age <= 35
    notaria, registro = _notaria_registro(precio)

    if is_new_build:
        # New build: IVA (10%) + AJD
        iva_rate = 10.0
        iva = precio * iva_rate / 100
        ajd_rate = AJD_POR_CCAA.get(ccaa, 1.5)
        ajd = precio * ajd_rate / 100
        total_taxes = iva + ajd + notaria + registro
        return {
            "tipo_impuesto": "IVA + AJD (vivienda nueva)",
            "itp_rate": None,
            "iva_rate": iva_rate,
            "iva": round(iva, 2),
            "ajd_rate": ajd_rate,
            "ajd": round(ajd, 2),
            "itp": 0,
            "notaria": notaria,
            "registro": registro,
            "total": round(total_taxes, 2),
            "is_young_rate": False,
        }
    else:
        # Second-hand: ITP
        itp_rate_gen = ITP_POR_CCAA.get(ccaa, 8.0)
        itp_rate = ITP_JOVEN.get(ccaa, itp_rate_gen) if is_young else itp_rate_gen
        is_young_rate = is_young and itp_rate < itp_rate_gen
        itp = precio * itp_rate / 100
        total_taxes = itp + notaria + registro
        return {
            "tipo_impuesto": "ITP (segunda mano)",
            "itp_rate": itp_rate,
            "itp_rate_gen": itp_rate_gen,
            "itp": round(itp, 2),
            "ajd": 0, "iva": 0,
            "notaria": notaria,
            "registro": registro,
            "total": round(total_taxes, 2),
            "is_young_rate": is_young_rate,
        }


def _get_tipos_for_year(year_str):
    if df_tipos.empty:
        return None
    ydata = df_tipos[df_tipos['year'] == str(year_str)]
    if ydata.empty:
        return None
    aprc_val    = float(ydata['APRC_VALUE'].mean())
    euribor_val = float(ydata['EURIBOR_VALUE'].mean())
    diferencia  = float(ydata['Diferencia'].mean())
    # Garantizar diferencia positiva real: APRC debe ser mayor que Euribor
    if abs(aprc_val - euribor_val) < 0.01:
        aprc_val = euribor_val + diferencia if diferencia != 0 else euribor_val + 1.0
    return {
        'aprc': aprc_val,
        'euribor': euribor_val,
        'diferencia': round(aprc_val - euribor_val, 4),
    }


_MACRO_FORECASTS = {}

# ╔══════════════════════════════════════════════╗
# ║  TASA_PARO MODEL SELECTION PER PROVINCE      ║
# ║  Resultado del backtesting (notebook 5)      ║
# ╚══════════════════════════════════════════════╝
# Tier 1: SARIMA + dummy COVID (estacionalidad fuerte)
PROV_SARIMA_DUMMY = {
    'Badajoz': {'order': (1, 1, 0), 'seasonal': (1, 1, 0, 4),
                'reason': 'Fuerte estacionalidad agrícola. SARIMA(1,1,0)(1,1,0)4 + dummy COVID. MAPE 20.6% → 7.3%.'},
    'Girona':  {'order': (1, 1, 0), 'seasonal': (0, 0, 1, 4),
                'reason': 'Estacionalidad turística (costa brava). SARIMA(1,1,0)(0,0,1)4 + dummy COVID. MAPE 28.1% → 18.5%.'},
}
# Tier 2: ARIMA(3,1,2) + dummy COVID (shock 2020-2021 estructuralmente significativo)
PROV_ARIMA_DUMMY = {
    'Castellón', 'Ciudad Real', 'Granada', 'Islas Baleares', 'Jaén',
    'La Rioja', 'León', 'Málaga', 'Palencia', 'Pontevedra',
    'Región de Murcia', 'Santa Cruz de Tenerife', 'Tarragona',
    'Valladolid', 'Vizcaya', 'Zamora', 'Zaragoza',
}
# Tier 3: ARIMA(3,1,2) sin dummy (resto de provincias)
# Todas las demás provincias no incluidas en los dos grupos anteriores

def _get_paro_model_info(province: str) -> dict:
    """Retorna info del modelo de Tasa_Paro para una provincia."""
    if province in PROV_SARIMA_DUMMY:
        cfg = PROV_SARIMA_DUMMY[province]
        return {
            'tier': 1,
            'model': f"SARIMA{cfg['order']}x{cfg['seasonal']}",
            'model_short': 'SARIMA + Dummy COVID',
            'reason': cfg['reason'],
            'color': '#28a745',
            'label': 'Nivel 1',
        }
    elif province in PROV_ARIMA_DUMMY:
        return {
            'tier': 2,
            'model': 'ARIMA(3,1,2) + Dummy COVID',
            'model_short': 'ARIMA + Dummy COVID',
            'reason': 'El shock COVID 2020-2021 sesga los coeficientes AR. '
                      'Incluir una variable dummy aísla ese periodo y mejora la estimación '
                      'de la dinámica estructural del paro provincial.',
            'color': '#f0a500',
            'label': 'Nivel 2',
        }
    else:
        return {
            'tier': 3,
            'model': 'ARIMA(3,1,2)',
            'model_short': 'ARIMA(3,1,2)',
            'reason': 'El shock COVID no dejó señal estructural detectable en la dinámica '
                      'del paro de esta provincia. La dummy añadiría ruido sin mejorar la predicción.',
            'color': '#007BC0',
            'label': 'Nivel 3',
        }

def _get_last_provincial_pib(province: str):
    """Forward-fill helper: returns last non-NaN PIB_pc for a province.
    Used when 2025 data is NaN (INE not yet published) to avoid falling back
    to the national SARIMA average (~30k) for high-PIB provinces like Madrid (~44k)."""
    if df.empty or not province:
        return None
    prov_series = df[df['Provincia'] == province]['PIB_pc'].dropna()
    return float(prov_series.iloc[-1]) if not prov_series.empty else None

# Load provincial predictions if file exists
df_prov_preds = pd.DataFrame()
prov_preds_file = os.path.join(app.root_path, '..', 'notebooks acabados', 'predicciones_provinciales_2026_2030.csv')
if os.path.exists(prov_preds_file):
    try:
        df_prov_preds = pd.read_csv(prov_preds_file)
        print(f"[INIT] Loaded {len(df_prov_preds)} provincial predictions.")
    except Exception as e:
        print(f"[INIT] Error loading provincial predictions: {e}")

def _build_forecasts():
    """Código EXACTO del notebook HIPOTECA_PERSONALIZADA.ipynb (cell 29).
    Ganadores backtesting:
      PIB_pc       -> SARIMA(1,1,0)(1,1,0)4
      Tasa_Paro    -> ARIMA (Auto AIC) + Suelo 8.5%
      Precio_m2    -> Seasonal Naive + tendencia lineal
      tasa_ahorro  -> ARIMA (Auto AIC)
      Euribor/IPC  -> Proyecciones BCE (exógenas)
    Horizonte: 24 trimestres (2026Q1–2031Q4)
    """
    global _MACRO_FORECASTS
    if _MACRO_FORECASTS: return

    import statsmodels.api as sm
    import warnings
    warnings.filterwarnings('ignore')

    # ── 0. CONFIGURACIÓN (idéntica al notebook) ─────────────────
    ALL_COLS = ['PIB_pc', 'Tasa_Paro', 'Precio_m2', 'tasa_ahorro', 'Euribor', 'IPC', 'Transmisiones_Total']
    TARGETS  = ['PIB_pc', 'Tasa_Paro', 'Precio_m2', 'tasa_ahorro', 'Transmisiones_Total']
    PARO_MIN = 8.5

    ESCENARIOS_BCE = {
        'Euribor': {'2026': 2.00, '2027': 2.10, '2028': 2.30, '2029': 2.15, '2030': 2.15, '2031': 2.15},
        'IPC':     {'2026': 1.88, '2027': 2.10, '2028': 2.00, '2029': 2.00, '2030': 2.00, '2031': 2.00},
    }

    def anuales_a_trimestrales(d):
        vals = []
        for anio in sorted(d.keys()):
            vals.extend([d[anio]] * 4)
        return vals

    EURIBOR_PROJ = anuales_a_trimestrales(ESCENARIOS_BCE['Euribor'])
    IPC_PROJ     = anuales_a_trimestrales(ESCENARIOS_BCE['IPC'])
    N_STEPS      = len(EURIBOR_PROJ)  # 24

    # ── 1. DATOS ────────────────────────────────────────────────
    df_q = df.copy()
    df_q['Trimestre'] = pd.to_datetime(df_q['Trimestre'])
    df_nac = df_q.groupby('Trimestre')[ALL_COLS].mean().sort_index()
    df_nac.index = pd.DatetimeIndex(df_nac.index)

    df_full = df_nac.dropna(subset=TARGETS)

    last_date  = df_full.index[-1]
    future_idx = pd.date_range(start=last_date + pd.DateOffset(months=3),
                                periods=N_STEPS, freq='QS')

    # ── 2. PIB_pc — SARIMA(1,1,0)(1,1,0)4 ──────────────────────
    try:
        tr_pib   = pd.Series(df_full['PIB_pc'].values)
        r_pib    = sm.tsa.SARIMAX(tr_pib, order=(1,1,0),
                                   seasonal_order=(1,1,0,4)).fit(disp=False)
        fc_pib   = r_pib.get_forecast(steps=N_STEPS)
        pred_pib = fc_pib.predicted_mean.values
    except Exception as e:
        print(f"Error PIB_pc: {e}")
        pred_pib = np.full(N_STEPS, np.nan)

    # ── 3. Tasa_Paro — ARIMA (Auto AIC) + Suelo 8.5% ───────────
    try:
        tr_paro = pd.Series(df_full['Tasa_Paro'].values)
        best_aic, best_order_paro, best_res_paro = np.inf, None, None
        for p in range(0, 4):
            for d_ord in range(0, 2):
                for q in range(0, 3):
                    try:
                        r = sm.tsa.ARIMA(tr_paro, order=(p, d_ord, q)).fit()
                        if r.aic < best_aic:
                            best_aic, best_order_paro, best_res_paro = r.aic, (p, d_ord, q), r
                    except:
                        pass
        fc_paro    = best_res_paro.get_forecast(steps=N_STEPS)
        pred_paro  = np.clip(fc_paro.predicted_mean.values, PARO_MIN, None)
    except Exception as e:
        print(f"Error Tasa_Paro: {e}")
        pred_paro = np.full(N_STEPS, np.nan)

    # ── 4. Precio_m2 — Seasonal Naive + tendencia lineal ────────
    try:
        tr_pm2    = df_full['Precio_m2'].dropna()
        tendencia = tr_pm2.diff().iloc[-8:].mean()
        base      = np.array([tr_pm2.iloc[-(4 - i % 4)] for i in range(N_STEPS)])
        drift     = np.array([(i // 4 + 1) * 4 * tendencia for i in range(N_STEPS)])
        pred_pm2  = base + drift
    except Exception as e:
        print(f"Error Precio_m2: {e}")
        pred_pm2 = np.full(N_STEPS, np.nan)

    # ── 5. tasa_ahorro — ARIMA (Auto AIC) ───────────────────────
    try:
        tr_aho = pd.Series(df_full['tasa_ahorro'].values)
        best_aic, best_order_aho, best_res_aho = np.inf, None, None
        for p in range(0, 4):
            for d_ord in range(0, 2):
                for q in range(0, 3):
                    try:
                        r = sm.tsa.ARIMA(tr_aho, order=(p, d_ord, q)).fit()
                        if r.aic < best_aic:
                            best_aic, best_order_aho, best_res_aho = r.aic, (p, d_ord, q), r
                    except:
                        pass
        fc_aho   = best_res_aho.get_forecast(steps=N_STEPS)
        pred_aho = fc_aho.predicted_mean.values
    except Exception as e:
        print(f"Error tasa_ahorro: {e}")
        pred_aho = np.full(N_STEPS, np.nan)

    # ── 5b. Transmisiones_Total — Seasonal Naive + tendencia (excl. Q4 2025)
    try:
        tr_trans = df_full['Transmisiones_Total'].dropna()
        # Excluir último trimestre anómalo para tendencia (como en notebook)
        tr_trans_clean = tr_trans[:-1] if len(tr_trans) > 1 else tr_trans
        tendencia_trans = tr_trans_clean.diff().iloc[-8:].mean()
        base_trans      = np.array([tr_trans_clean.iloc[-(4 - i % 4)] for i in range(N_STEPS)])
        drift_trans     = np.array([(i // 4 + 1) * 4 * tendencia_trans for i in range(N_STEPS)])
        pred_trans      = base_trans + drift_trans
    except Exception as e:
        print(f"Error Transmisiones_Total: {e}")
        pred_trans = np.full(N_STEPS, np.nan)

    # ── 6. Empaquetar en _MACRO_FORECASTS ───────────────────────
    pred_dict = {
        'PIB_pc':      pred_pib,
        'Tasa_Paro':   pred_paro,
        'Precio_m2':   pred_pm2,
        'tasa_ahorro': pred_aho,
        'Transmisiones_Total': pred_trans,
    }

    # Variables modelizadas → promediar trimestres a años
    for col in TARGETS:
        preds = pred_dict[col]
        df_pred = pd.DataFrame({'Q': future_idx, 'val': preds})
        df_pred['year'] = df_pred['Q'].dt.year.astype(str)
        annual = df_pred.groupby('year')['val'].mean()
        _MACRO_FORECASTS[col] = {yr: round(float(v), 2) for yr, v in annual.items()}
        _MACRO_FORECASTS[col]['last_real'] = float(df_full[col].dropna().iloc[-1])

    # Euribor e IPC → escenarios BCE directos
    _MACRO_FORECASTS['IPC'] = dict(ESCENARIOS_BCE['IPC'])
    _MACRO_FORECASTS['IPC']['last_real'] = float(df_full['IPC'].dropna().iloc[-1]) if 'IPC' in df_full.columns else 2.0

    # Euribor/Diferencia desde df_tipos (para tipos hipotecarios)
    if not df_tipos.empty:
        df_t = df_tipos.copy()
        df_t['y'] = df_t['TIME_PERIOD'].str[:4]
        ann = df_t.groupby('y')[['EURIBOR_VALUE', 'Diferencia']].mean()

        for col in ['EURIBOR_VALUE', 'Diferencia']:
            ts_series = ann[col].dropna()
            ts = ts_series.values
            if len(ts) < 3: continue
            last_yr = int(ts_series.index[-1])
            steps = max(0, 2031 - last_yr)
            future_years = list(range(last_yr + 1, last_yr + 1 + steps))

            if col == 'EURIBOR_VALUE':
                _MACRO_FORECASTS[col] = {str(y): ESCENARIOS_BCE['Euribor'].get(str(y), 2.15) for y in future_years}
            else:  # Diferencia
                try:
                    model = sm.tsa.statespace.SARIMAX(ts, order=(1,1,1),
                                enforce_stationarity=False, enforce_invertibility=False)
                    res = model.fit(disp=False)
                    fc_preds = res.forecast(steps=steps)
                    _MACRO_FORECASTS[col] = {str(last_yr+1+i): float(v) for i, v in enumerate(fc_preds)}
                except:
                    _MACRO_FORECASTS[col] = {}
            _MACRO_FORECASTS.setdefault(col, {})['last_real'] = float(ts[-1])


def _get_tipos_proyectados(base_year="2025", years_ahead: int = 0):
    """Genera tipos simulados usando el motor econométrico SARIMAX cacheados en memoria."""
    _build_forecasts()
    target_yr = str(int(base_year) + years_ahead)
    
    euribor = _MACRO_FORECASTS.get('EURIBOR_VALUE', {}).get(target_yr, _MACRO_FORECASTS.get('EURIBOR_VALUE', {}).get('last_real', 2.5))
    spread = _MACRO_FORECASTS.get('Diferencia', {}).get(target_yr, _MACRO_FORECASTS.get('Diferencia', {}).get('last_real', 1.0))
    
    euribor = max(0.1, round(float(euribor), 4))
    spread = round(float(spread), 4)
    aprc = round(euribor + spread, 4)
    
    return {'euribor': euribor, 'aprc': aprc, 'diferencia': spread}


# ╔══════════════════════════════════════════════╗
# ║  GLOBAL AUTH GUARD                           ║
# ╚══════════════════════════════════════════════╝

# Public routes — no session required
_PUBLIC_ENDPOINTS = {'login', 'login_admin', 'logout', 'static'}

@app.before_request
def require_login():
    """Protect all routes. Admin routes require session['admin'];
    every other route accepts session['user'] OR session['admin']."""
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    # Admin-only routes
    if request.endpoint in ('admin', 'upload_chart', 'delete_custom_chart'):
        if not session.get('admin'):
            return redirect(url_for('login_admin'))
        return
    # General site routes — either user or admin session is fine
    if not (session.get('user') or session.get('admin')):
        return redirect(url_for('login'))


# ╔══════════════════════════════════════════════╗
# ║  CORE PAGES                                  ║
# ╚══════════════════════════════════════════════╝

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/hipotecas', methods=['GET'])
def hipotecas():
    return render_template('hipotecas.html')

@app.route('/demanda', methods=['GET'])
def demanda():
    return render_template('demanda.html')

@app.route('/demanda-provincial', methods=['GET'])
def demanda_provincial():
    return render_template('demanda_provincial.html')

@app.route('/hipotecas-provincial', methods=['GET'])
def hipotecas_provincial():
    return render_template('hipotecas_provincial.html')

@app.route('/metodologia-ml', methods=['GET'])
def metodologia_ml():
    return render_template('metodologia_ml.html')

@app.route('/econometria', methods=['GET'])
def econometria():
    return render_template('econometria.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """General site login — grants session['user'] only."""
    if session.get('user') or session.get('admin'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        if request.form.get('username') == _APP_USERNAME and request.form.get('password') == _APP_PASSWORD:
            session['user'] = True
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)
        return render_template('login.html', error="Credenciales incorrectas")
    return render_template('login.html')

@app.route('/login_admin', methods=['GET', 'POST'])
def login_admin():
    """Admin login — grants session['admin'] (superset of user access)."""
    if session.get('admin'):
        return redirect(url_for('admin'))
    if request.method == 'POST':
        if request.form.get('username') == _APP_USERNAME and request.form.get('password') == _APP_PASSWORD:
            session['admin'] = True
            next_url = request.args.get('next') or url_for('admin')
            return redirect(next_url)
        return render_template('login_admin.html', error="Credenciales incorrectas")
    return render_template('login_admin.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('admin', None)
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin'):
        return redirect(url_for('login_admin'))
    success = error = None
    if request.method == 'POST':
        action = request.form.get('action', 'dataset')
        if action == 'tipos':
            f = request.files.get('tipos_file')
            if f and f.filename.endswith('.csv'):
                f.save(TIPOS_PATH)
                global df_tipos
                df_tipos = pd.read_csv(TIPOS_PATH)
                df_tipos['year'] = df_tipos['TIME_PERIOD'].str[:4]
                success = "Fichero de tipos actualizado correctamente."
            else:
                error = "Solo se admiten ficheros .csv para los tipos."
        else:
            f = request.files.get('file')
            if f and f.filename.endswith('.csv'):
                fp = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
                f.save(fp)
                if f.filename == 'dataset_final_tfm.csv':
                    global df
                    df = pd.read_csv(fp)
                success = f"Archivo {f.filename} subido correctamente."
            else:
                error = "Solo se admiten ficheros .csv."
    return render_template('admin.html', success=success, error=error)


# ╔══════════════════════════════════════════════╗
# ║  DASHBOARD DATA API                          ║
# ╚══════════════════════════════════════════════╝

@app.route('/api/data')
def get_data():
    if df.empty:
        return jsonify({"error": "No data available."})
    year_from = request.args.get('year_from', '')
    year_to   = request.args.get('year_to', '')
    specific_year = request.args.get('specific_year', '')

    fdf = df.copy()
    
    # ── INYECTAR FUTURO EN FDF PARA EL DASHBOARD ──
    try:
        from demanda_models import _train_artifacts, _forecast_future, quarter_key
        art = _train_artifacts(df, df_prov_preds)
        if "base_forecast" not in art:
            art["base_forecast"] = _forecast_future(art)
        
        if not df_prov_preds.empty:
            future_df = df_prov_preds.pivot_table(index=["trimestre", "provincia"], columns="variable", values="valor").reset_index()
            future_df.rename(columns={"trimestre": "Trimestre", "provincia": "Provincia"}, inplace=True)
            if "Trimestre" in future_df.columns:
                future_df["Trimestre"] = future_df["Trimestre"].apply(lambda x: x + "-01" if len(str(x)) == 7 else x)

            # Construir lookup vectorizado en vez de iterrows (mucho más rápido)
            prov_by_q = art["base_forecast"].get("prov_by_q", {})
            hip_frames = []
            for qkey, hip_df in prov_by_q.items():
                if hip_df is not None and not hip_df.empty:
                    tmp = hip_df[["Provincia", "Hipotecas_Total"]].copy()
                    tmp["_qkey"] = qkey
                    hip_frames.append(tmp)
            if hip_frames:
                hip_lookup = pd.concat(hip_frames, ignore_index=True)
                future_df["_qkey"] = future_df["Trimestre"].apply(quarter_key)
                future_df = future_df.merge(
                    hip_lookup.rename(columns={"Hipotecas_Total": "_hip"}),
                    left_on=["_qkey", "Provincia"], right_on=["_qkey", "Provincia"], how="left"
                )
                future_df["Hipotecas_Total"] = future_df.pop("_hip")
                future_df.drop(columns=["_qkey"], inplace=True)
            else:
                future_df["Hipotecas_Total"] = np.nan
            
            # Use columns that match historical df
            cols = [c for c in future_df.columns if c in df.columns]
            fdf = pd.concat([fdf, future_df[cols]], ignore_index=True)
    except Exception as e:
        print("[API DATA] Error inyectando predicciones futuras:", e)
    if year_from and year_to:
        yr_range = [str(y) for y in range(int(year_from), int(year_to) + 1)]
        fdf = fdf[fdf['Trimestre'].str[:4].isin(yr_range)]
    elif year_from:
        fdf = fdf[fdf['Trimestre'].str[:4] >= year_from]
    elif year_to:
        fdf = fdf[fdf['Trimestre'].str[:4] <= year_to]

    if fdf.empty:
        return jsonify({"error": "No data for this filter."})
        
    res = {}
    
    # 1. Gráfico de barras (Pondera el filtro specific_year si existe)
    df_bars = fdf
    if specific_year:
        df_bars = df[df['Trimestre'].str.startswith(str(specific_year))]
        
    if 'Provincia' in df_bars.columns and 'Precio_m2' in df_bars.columns and not df_bars.empty:
        g = df_bars.groupby('Provincia')['Precio_m2'].mean().dropna().sort_values(ascending=False).head(20)
        res['barData'] = {"labels": g.index.tolist(), "values": g.values.tolist(), "year": specific_year}
        
    # 2. Gráfico de líneas (Línea de tiempo)
    if 'Trimestre' in fdf.columns:
        tg = fdf.groupby('Trimestre')[['Euribor', 'Spread_Hipotecas']].mean().dropna()
        res['timeSeries'] = {"labels": tg.index.tolist(),
                             "euribor": tg['Euribor'].tolist(),
                             "spread": tg['Spread_Hipotecas'].tolist()}
                             
    # 3. Nuevo Gráfico (Paro vs IPC) - Agrupado por año
    if 'Trimestre' in fdf.columns and 'Tasa_Paro' in fdf.columns and 'IPC' in fdf.columns:
        fdf['Year'] = fdf['Trimestre'].str[:4]
        ag = fdf.groupby('Year')[['Tasa_Paro', 'IPC']].mean().dropna()
        res['macroSeries'] = {"labels": ag.index.tolist(),
                              "paro": ag['Tasa_Paro'].tolist(),
                              "ipc": ag['IPC'].tolist()}
        fdf.drop(columns=['Year'], inplace=True)

    if 'Trimestre' in df.columns:
        uy = sorted(df['Trimestre'].str[:4].dropna().unique().tolist())
        for fy in ["2025", "2026", "2027", "2028", "2029", "2030"]:
            if fy not in uy:
                uy.append(fy)
        if "2026-2030" in uy:
            uy.remove("2026-2030")
        res['availableYears'] = uy
        res['years'] = uy

    # 4. Hipotecas nacionales (serie temporal)
    if 'Trimestre' in fdf.columns and 'Hipotecas_Total' in fdf.columns:
        hn = fdf.groupby('Trimestre')['Hipotecas_Total'].sum().dropna().sort_index()
        res['hipotecasNac'] = {"labels": hn.index.tolist(),
                               "values": [round(float(v)) for v in hn.values]}

    # 5. Top 10 provincias por volumen (por año)
    if 'Provincia' in fdf.columns and 'Hipotecas_Total' in fdf.columns:
        top_by_year = {}
        for y in fdf['Trimestre'].str[:4].unique():
            df_y = fdf[fdf['Trimestre'].str[:4] == y]
            tp = df_y.groupby('Provincia')['Hipotecas_Total'].sum().dropna().sort_values(ascending=False).head(10)
            top_by_year[y] = {"labels": tp.index.tolist(), "values": [round(float(v)) for v in tp.values], "year": y}
            
        last_yr = str(fdf['Trimestre'].str[:4].max())
        res['topProvHip'] = {"by_year": top_by_year, "last_yr": last_yr}

    return jsonify(res)


# ╔══════════════════════════════════════════════╗
# ║  DEMAND PREDICTION API  (data_science.ipynb) ║
# ╚══════════════════════════════════════════════╝

_DEMANDA_CACHE = {}

def _forecast_quarter_key(value):
    """Normalize forecast quarter labels to YYYY-Qn."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    match = re.match(r'^(\d{4})-?Q([1-4])$', text, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1)}-Q{match.group(2)}"
    dt = pd.to_datetime(text, errors='coerce')
    if pd.isna(dt):
        return None
    return f"{dt.year}-Q{dt.quarter}"

def _clean_province_key(value):
    import unicodedata
    text = '' if value is None else str(value).strip().lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text

def _resolve_demanda_province(province, available_provs):
    """Accept common short province names while preserving dataset labels."""
    if not province:
        return ''
    by_clean = {_clean_province_key(p): p for p in available_provs}
    key = _clean_province_key(province)
    aliases = {
        'madrid': 'comunidad de madrid',
        'asturias': 'principado de asturias',
        'murcia': 'region de murcia',
        'navarra': 'comunidad foral de navarra',
        'baleares': 'islas baleares',
        'illes balears': 'islas baleares',
    }
    return by_clean.get(key) or by_clean.get(aliases.get(key, '')) or province

@app.route('/api/demanda-data')
def demanda_data():
    """Predicción de demanda hipotecaria con RF_Nac y RF provincial."""
    year_req = request.args.get('year', '')
    prov_req = request.args.get('provincia', '')
    global _DEMANDA_CACHE
    if not year_req and not prov_req and _DEMANDA_CACHE:
        return jsonify(_DEMANDA_CACHE)

    if df.empty:
        return jsonify({"error": "No data available."}), 500

    try:
        from demanda_models import build_demanda_response
        result, status = build_demanda_response(df, df_prov_preds, year_req, prov_req)
        if not year_req and not prov_req:
            _DEMANDA_CACHE = result
        return jsonify(result), status

    except Exception as e:
        import traceback
        result = {}
        result['error'] = str(e)
        result['traceback'] = traceback.format_exc()

        # If an error occurs, _DEMANDA_CACHE should not be updated with an error state
        # only cache if no year and no prov is requested (default view).
        if not year_req and not prov_req:
            _DEMANDA_CACHE = result
        return jsonify(result)

_GEOJSON_CACHE = None
_GEOJSON_LOCAL = os.path.join(os.path.dirname(__file__), 'static', 'spain-provinces.geojson')

def get_geojson():
    global _GEOJSON_CACHE
    if _GEOJSON_CACHE is None:
        import geopandas as gpd
        import unicodedata
        url_geojson = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/spain-provinces.geojson"
        if os.path.exists(_GEOJSON_LOCAL):
            gdf = gpd.read_file(_GEOJSON_LOCAL)
        else:
            gdf = gpd.read_file(url_geojson)
            gdf.to_file(_GEOJSON_LOCAL, driver='GeoJSON')
        
        def clean_text(text):
            if pd.isna(text): return ""
            s = str(text).lower().strip()
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
            
        gdf['name_clean'] = gdf['name'].apply(clean_text)
        diccionario_mapa = {
            'illes balears': 'islas baleares',
            'alacant/alicante': 'alicante',
            'castello/castellon': 'castellon',
            'valencia/valencia': 'valencia',
            'araba/alava': 'alava',
            'bizkaia/vizcaya': 'vizcaya',
            'gipuzkoa/guipuzcoa': 'guipuzcoa',
            'madrid': 'comunidad de madrid',
            'murcia': 'region de murcia',
            'asturias': 'principado de asturias',
            'navarra': 'comunidad foral de navarra',
            'la coruna': 'a coruna',
            'las palmas': 'las palmas',
            'santa cruz de tenerife': 'santa cruz de tenerife'
        }
        gdf['name_clean'] = gdf['name_clean'].replace(diccionario_mapa)
        _GEOJSON_CACHE = gdf
    return _GEOJSON_CACHE

@app.route('/api/mapa/<tipo>')
def generar_mapa(tipo):
    # Servir desde caché en disco si existe (se genera en la primera llamada)
    cache_path = os.path.join(os.path.dirname(__file__), 'static', f'_mapa_cache_{tipo}.b64')
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as _cf:
                img_b64 = _cf.read()
            return jsonify({"image": "data:image/png;base64," + img_b64})
        except Exception:
            pass
    import geopandas as gpd
    import matplotlib; matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import unicodedata
    from io import BytesIO
    import base64
    
    def clean_text(text):
        if pd.isna(text): return ""
        s = str(text).lower().strip()
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
        
    gdf = get_geojson()
    df_map = df.copy()
    
    if tipo == "tension":
        ultimo_trimestre = df_map['Trimestre'].max()
        df_reciente = df_map[df_map['Trimestre'] == ultimo_trimestre].copy()
        df_reciente['Provincia_Clean'] = df_reciente['Provincia'].apply(clean_text)
        df_reciente['Tension'] = df_reciente['Precio_m2']
        merged = gdf.merge(df_reciente, left_on='name_clean', right_on='Provincia_Clean', how='left')
        
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        ax.set_facecolor('white')
        merged.plot(column='Tension', cmap='Blues', linewidth=0.8, ax=ax, edgecolor='black',
                    legend=True,
                    legend_kwds={'label': f"Precio del m² (€) — Tensión de Mercado",
                                 'shrink': 0.6, 'orientation': 'horizontal'},
                    missing_kwds={'color': 'lightgrey', "hatch": "///", "label": "Sin datos"})
        plt.title("Tensión del Mercado Inmobiliario", fontsize=18, fontweight='bold')
        
    elif tipo == "accesibilidad":
        cols_to_fill = ['PIB_pc', 'Tasa_Paro', 'Precio_m2']
        for c in cols_to_fill:
            if c in df_map.columns:
                df_map[c] = df_map.groupby('Provincia')[c].ffill().bfill()
        df_map['Accesibilidad'] = (df_map['PIB_pc'] * (1 - df_map['Tasa_Paro']/100)) / df_map['Precio_m2']
        ultimo_trimestre = df_map['Trimestre'].max()
        df_reciente = df_map[df_map['Trimestre'] == ultimo_trimestre].copy()
        df_reciente['Provincia_Clean'] = df_reciente['Provincia'].apply(clean_text)
        merged = gdf.merge(df_reciente, left_on='name_clean', right_on='Provincia_Clean', how='left')
        
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        ax.set_facecolor('white')
        merged.plot(column='Accesibilidad', cmap='Blues', linewidth=0.6, ax=ax, edgecolor='black',
                    legend=True,
                    legend_kwds={'label': "Índice de Accesibilidad (Mayor = Más fácil comprar casa)",
                                 'orientation': "horizontal", 'shrink': 0.6, 'pad': 0.05},
                    missing_kwds={'color': 'lightgrey', "hatch": "///", "label": "Sin datos"})
        plt.title(f"Mapa de Accesibilidad Hipotecaria", fontsize=18, fontweight='bold', color='#154360')
        
    elif tipo == "mina_oro":
        from sklearn.ensemble import RandomForestRegressor
        
        df_map['Trimestre'] = pd.to_datetime(df_map['Trimestre'])
        lag_cols_base = ['Precio_m2', 'Spread_Hipotecas', 'Poblacion',
                         'Edad_Media', 'Transmisiones_Total', 'Tasa_Paro',
                         'tasa_ahorro', 'PIB_pc', 'Pob_Ext', 'Indice_Mano_Obra', 'Indice_Materiales', 'IPC']
        for c in lag_cols_base:
            if c in df_map.columns:
                df_map[f'{c}_lag1'] = df_map.groupby('Provincia')[c].shift(1)
                
        df_model = df_map.dropna().reset_index(drop=True)
        features = ['Precio_m2_lag1', 'Euribor', 'tasa_ahorro_lag1', 'Spread_Hipotecas_lag1', 
                    'Poblacion_lag1', 'Edad_Media_lag1', 'Pob_Ext_lag1', 'Transmisiones_Total_lag1', 
                    'Indice_Mano_Obra_lag1', 'Indice_Materiales_lag1', 'IPC_lag1', 'Tasa_Paro_lag1', 'PIB_pc_lag1']
        features = [f for f in features if f in df_model.columns]
        
        if not features:
            return jsonify({"error": "No features available"}), 500
            
        X = df_model[features]
        y = df_model['Hipotecas_Total']
        rf = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        rf.fit(X, y)
        
        ultimo_trimestre = df_map['Trimestre'].max()
        df_futuro = df_map[df_map['Trimestre'] == ultimo_trimestre].copy()
        for f in features:
             if f not in df_futuro.columns:
                 df_futuro[f] = 0
        df_futuro['Euribor'] = 2.5
        if 'Spread_Hipotecas_lag1' in df_futuro.columns:
            df_futuro['Spread_Hipotecas_lag1'] = 1.0
            
        df_futuro['Prediccion_Hipotecas'] = rf.predict(df_futuro[features])
        if 'Poblacion_lag1' in df_futuro.columns:
            df_futuro['Vol_per_capita'] = df_futuro['Prediccion_Hipotecas'] / df_futuro['Poblacion_lag1']
        else:
            df_futuro['Vol_per_capita'] = df_futuro['Prediccion_Hipotecas'] / 1e6
        if 'Tasa_Paro_lag1' in df_futuro.columns and 'Precio_m2_lag1' in df_futuro.columns:
            df_futuro['Score_Bruto'] = (df_futuro['Vol_per_capita'] * df_futuro['Precio_m2_lag1']) / (df_futuro['Tasa_Paro_lag1'] / 100 + 0.001)
        else:
            df_futuro['Score_Bruto'] = df_futuro['Vol_per_capita']
            
        min_s = df_futuro['Score_Bruto'].min()
        max_s = df_futuro['Score_Bruto'].max()
        df_futuro['Mina_Oro_Score'] = 100 * (df_futuro['Score_Bruto'] - min_s) / (max_s - min_s + 1e-9)
        df_futuro['Provincia_Clean'] = df_futuro['Provincia'].apply(clean_text)
        merged = gdf.merge(df_futuro, left_on='name_clean', right_on='Provincia_Clean', how='left')
        
        fig, ax = plt.subplots(1, 1, figsize=(14, 10))
        ax.set_facecolor('white')
        merged.plot(column='Mina_Oro_Score', cmap='YlOrBr', linewidth=0.6, ax=ax, edgecolor='black',
                    legend=True,
                    legend_kwds={'label': "Índice 'Mina de Oro' Bancario",
                                 'orientation': "horizontal", 'shrink': 0.6, 'pad': 0.05},
                    missing_kwds={'color': 'lightgrey', "hatch": "///", "label": "Sin datos"})
        plt.title("Mapa Mina de Oro Bancario (Euríbor 2.5%)", fontsize=18, fontweight='bold', color='#B8860B')

    else:
        return jsonify({"error": "Tipo de mapa no válido"}), 400

    plt.axis('off')
    plt.tight_layout()
    
    img = BytesIO()
    plt.savefig(img, format='png', dpi=80, bbox_inches='tight')
    img.seek(0)
    plt.close(fig)

    img_b64 = base64.b64encode(img.getvalue()).decode('utf-8')
    result = jsonify({"image": "data:image/png;base64," + img_b64})

    # Cachear en disco para requests posteriores (se invalida al reiniciar)
    try:
        cache_path = os.path.join(os.path.dirname(__file__), 'static', f'_mapa_cache_{tipo}.b64')
        with open(cache_path, 'w') as _cf:
            _cf.write(img_b64)
    except Exception:
        pass

    return result



@app.route('/api/hipoteca-context')
def hipoteca_context():
    if df.empty:
        return jsonify({"error": "No data"})
    year = request.args.get('year', '2020')
    prov_req = request.args.get('provincia', '')
    FUTURE_YEARS = ["2026", "2027", "2028", "2029", "2030"]
    
    _build_forecasts()
    
    # ── 1. Cargar datos base ──
    ydf = df[df['Trimestre'].str.startswith(str(year))].copy()
    if ydf.empty and year in FUTURE_YEARS:
        ydf = df[df['Trimestre'].str.startswith("2025")].copy()
    
    # Filtrar por provincia si se solicita
    if prov_req and prov_req != 'Nacional':
        ydf = ydf[ydf['Provincia'] == prov_req]
        
    if ydf.empty:
        return jsonify({"error": f"No hay datos para {year} en {prov_req or 'Nacional'}"})
        
    agg = ydf[['IPC', 'Tasa_Paro', 'Precio_m2', 'PIB_pc', 'tasa_ahorro', 'Transmisiones_Total', 'Poblacion', 'Pob_Ext']].mean()

    # Para vista NACIONAL: Poblacion/Pob_Ext/Transmisiones son conteos provinciales;
    # hay que sumarlos por trimestre y luego promediar el año — no hacer mean directo.
    if not prov_req or prov_req == 'Nacional':
        for _cnt_col in ['Poblacion', 'Pob_Ext', 'Transmisiones_Total']:
            _by_q = ydf.groupby('Trimestre')[_cnt_col].sum()
            if not _by_q.empty and _by_q.notna().any():
                agg[_cnt_col] = _by_q.mean()

    is_pib_predicted = False
    is_future = year in FUTURE_YEARS

    # ── 2. Inyectar predicciones SARIMA (Provinciales o Nacionales) ──
    for col in ['IPC', 'Tasa_Paro', 'Precio_m2', 'PIB_pc', 'tasa_ahorro', 'Transmisiones_Total', 'Poblacion', 'Pob_Ext']:
        if pd.isna(agg[col]) or agg[col] == 0 or is_future:
            # Caso Provincial: futuro (2026-2030) o 2025 con NaN (INE pendiente)
            use_csv = is_future or (year == "2025" and pd.isna(agg[col]))
            if use_csv and prov_req and prov_req != 'Nacional' and not df_prov_preds.empty:
                mask = (df_prov_preds['provincia'] == prov_req) & (df_prov_preds['trimestre'].str.startswith(str(year))) & (df_prov_preds['variable'] == col)
                prov_vals = df_prov_preds[mask]['valor']
                if not prov_vals.empty:
                    agg[col] = prov_vals.mean()
                    if col == 'PIB_pc': is_pib_predicted = True
                    continue

            # Caso Nacional Futuro: sumar todas las provincias del CSV para conteos
            if use_csv and (not prov_req or prov_req == 'Nacional') and col in ['Poblacion', 'Pob_Ext', 'Transmisiones_Total'] and not df_prov_preds.empty:
                mask_nac = (df_prov_preds['trimestre'].str.startswith(str(year))) & (df_prov_preds['variable'] == col)
                nac_by_q = df_prov_preds[mask_nac].groupby('trimestre')['valor'].sum()
                if not nac_by_q.empty:
                    agg[col] = nac_by_q.mean()
                    continue

            # Fallback final: forward-fill desde último valor provincial real
            if col == 'PIB_pc' and prov_req and prov_req != 'Nacional' and pd.isna(agg[col]):
                last_prov_pib = _get_last_provincial_pib(prov_req)
                if last_prov_pib:
                    agg[col] = last_prov_pib
                    is_pib_predicted = True
                    continue

            # Caso Nacional Futuro (o fallback macro)
            if str(year) in _MACRO_FORECASTS.get(col, {}):
                agg[col] = _MACRO_FORECASTS[col][str(year)]
                if col == 'PIB_pc' and (year == "2025" or is_future):
                    is_pib_predicted = True
            else:
                agg[col] = _MACRO_FORECASTS.get(col, {}).get('last_real', 0)

    pib_pc = float(agg['PIB_pc'])
    pib_2025_disclaimer = (year == "2025")  # dataset NaN — forward-fill from 2024

    try:
        prev_year_str = str(int(year) - 1)
        prev_pib = None

        # Para vista provincial: usar valor provincial del año anterior
        # (evita comparar pib_pc provincial actual con media nacional del año anterior)
        if prov_req and prov_req != 'Nacional':
            if not df_prov_preds.empty:
                mask_prev = (df_prov_preds['provincia'] == prov_req) & \
                            (df_prov_preds['trimestre'].str.startswith(prev_year_str)) & \
                            (df_prov_preds['variable'] == 'PIB_pc')
                prev_csv = df_prov_preds[mask_prev]['valor']
                if not prev_csv.empty:
                    prev_pib = float(prev_csv.mean())
            if prev_pib is None:
                prev_prov_df = df[(df['Trimestre'].str.startswith(prev_year_str)) & (df['Provincia'] == prov_req)]
                if not prev_prov_df.empty and not prev_prov_df['PIB_pc'].isna().all():
                    prev_pib = float(prev_prov_df['PIB_pc'].mean())

        # Fallback nacional
        if prev_pib is None:
            prev_pib = _MACRO_FORECASTS.get('PIB_pc', {}).get(prev_year_str)
        if prev_pib is None:
            prev_ydf = df[df['Trimestre'].str.startswith(prev_year_str)]
            prev_pib = prev_ydf['PIB_pc'].mean() if not prev_ydf.empty else pib_pc

        pib_growth = ((pib_pc / float(prev_pib)) - 1) * 100 if prev_pib and prev_pib > 0 else 0.0
    except:
        pib_growth = 0.0

    FUTURE_YEARS = ["2026", "2027", "2028", "2029", "2030"]
    if year in FUTURE_YEARS:
        tipos = _get_tipos_proyectados(base_year="2025", years_ahead=int(year) - 2025)
    else:
        tipos = _get_tipos_for_year(year)
    if tipos is None:
        fallback = _get_tipos_for_year("2025") or {'euribor': 2.5, 'aprc': 3.7, 'diferencia': 1.2}
        tipos = fallback
    euribor = tipos['euribor']
    aprc    = tipos['aprc']
    diferencia = tipos['diferencia']

    global _CORR_IMG_CACHE
    if _CORR_IMG_CACHE is None:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import seaborn as sns
            corr_cols = ['Euribor', 'Spread_Hipotecas', 'IPC', 'Tasa_Paro', 'Precio_m2', 'PIB_pc', 'tasa_ahorro', 'Hipotecas_Total']
            corr_matrix = df[corr_cols].dropna().corr()
            fig, ax = plt.subplots(figsize=(7, 5))
            sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdYlGn', center=0, ax=ax,
                        linewidths=0.5, annot_kws={"size": 8}, cbar_kws={"shrink": 0.8})
            ax.set_title('Correlacion de variables (dataset completo)', fontsize=11, fontweight='bold')
            plt.xticks(rotation=30, ha='right', fontsize=8)
            plt.yticks(fontsize=8)
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=90, bbox_inches='tight')
            plt.close()
            buf.seek(0)
            _CORR_IMG_CACHE = base64.b64encode(buf.read()).decode('utf-8')
        except Exception:
            _CORR_IMG_CACHE = ""
    corr_img_b64 = _CORR_IMG_CACHE

    if not df_tipos.empty:
        ts_grouped = df_tipos.groupby('year')[['APRC_VALUE', 'EURIBOR_VALUE', 'Diferencia']].mean().sort_index()
        ts_labels = [f"{y}-01-01" for y in ts_grouped.index.tolist()]
        ts_euribor = [round(v, 3) for v in ts_grouped['EURIBOR_VALUE'].tolist()]
        ts_spread = [round(v, 3) for v in ts_grouped['Diferencia'].tolist()]
    else:
        ts = df.groupby('Trimestre')[['Euribor', 'Spread_Hipotecas']].mean().dropna()
        ts_labels = ts.index.tolist()
        ts_euribor = [round(v, 3) for v in ts['Euribor'].tolist()]
        ts_spread = [round(v, 3) for v in ts['Spread_Hipotecas'].tolist()]

    provinces = sorted(df['Provincia'].dropna().unique().tolist())
    scope_label = prov_req if prov_req else "Nacional"
    data_period_label = f"Proyección BCE/SARIMA {year}" if is_future else f"Media anual {year} (datos históricos)"
    return jsonify({
        "euribor": round(euribor, 4), "aprc": round(aprc, 4),
        "diferencia": round(diferencia, 4), "ipc": round(float(agg['IPC']), 4),
        "tasa_paro": round(float(agg['Tasa_Paro']), 2), "precio_m2": round(float(agg['Precio_m2']), 2),
        "pib_pc": round(pib_pc, 2), "pib_growth": round(pib_growth, 4),
        "pib_2025_disclaimer": pib_2025_disclaimer,
        "tasa_ahorro": round(float(agg['tasa_ahorro']), 2),
        "transmisiones": int(round(float(agg['Transmisiones_Total']), 0)) if not pd.isna(agg['Transmisiones_Total']) else 0,
        "poblacion": int(round(float(agg['Poblacion']), 0)) if not pd.isna(agg['Poblacion']) else 0,
        "poblacion_ext": int(round(float(agg['Pob_Ext']), 0)) if not pd.isna(agg['Pob_Ext']) else 0,
        "is_pib_predicted": is_pib_predicted,
        "is_future": is_future,
        "data_period": data_period_label,
        "scope": scope_label,
        "metrics": {
            "r2": 0.8492,
            "rmse": 0.1543,
            "mape": "3.2%",
            "modelo": "Gradient Boosting Regressor (Provincial)"
        },
        "time_series": {
            "labels": ts_labels,
            "euribor": ts_euribor,
            "spread": ts_spread
        },
        "corr_img": corr_img_b64,
        "provinces": provinces
    })



# ╔══════════════════════════════════════════════════════════╗
# ║  ML PRICING MODEL — GradientBoosting + SHAP (AI Act)     ║
# ║  Fuente: HIPOTECAS_PROV.ipynb                            ║
# ╚══════════════════════════════════════════════════════════╝

_PRICING_MODEL_CACHE = {}
_CORR_IMG_CACHE = None
_ML_FEATURES = ['Euribor', 'IPC', 'Tasa_Paro', 'Precio_m2', 'PIB_pc', 'tasa_ahorro']
_ML_TARGET   = 'Spread_Hipotecas'

def _train_ml_pricing_model(year: str):
    """
    Entrena un GradientBoostingRegressor para predecir Spread_Hipotecas.
    Hiperparámetros conservadores (HIPOTECAS_PROV.ipynb):
      max_depth=3, min_samples_leaf=5, lr=0.06, n_estimators=100
    Seleccionado NO por R² superior sino porque SHAP TreeExplainer
    proporciona explicabilidad exacta conforme a AI Act (Art. 13-14).
    Devuelve (model, scaler, explainer, r2_train, rmse_cv, n_samples, mae_cv) o None.
    """
    global _PRICING_MODEL_CACHE
    if year in _PRICING_MODEL_CACHE:
        return _PRICING_MODEL_CACHE[year]

    print(f"[ML] Entrenando GBR + SHAP para año {year}")
    try:
        data_model = df[_ML_FEATURES + [_ML_TARGET]].dropna()
        if len(data_model) < 20:
            return None

        X = data_model[_ML_FEATURES].values
        y = data_model[_ML_TARGET].values

        scaler = StandardScaler()
        X_s = scaler.fit_transform(X)

        model = GradientBoostingRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.06,
            min_samples_leaf=5, random_state=42
        )
        model.fit(X_s, y)

        # Train R² (referencia, NO es validación)
        r2_train = r2_score(y, model.predict(X_s))

        # CV temporal con TimeSeriesSplit para RMSE/MAE reales
        from sklearn.model_selection import TimeSeriesSplit, cross_validate
        from sklearn.pipeline import Pipeline
        from sklearn.metrics import make_scorer
        pipe = Pipeline([('scaler', StandardScaler()),
                         ('model', GradientBoostingRegressor(
                             n_estimators=100, max_depth=3, learning_rate=0.06,
                             min_samples_leaf=5, random_state=42))])
        tscv = TimeSeriesSplit(n_splits=5)
        cv = cross_validate(pipe, X, y, cv=tscv, scoring={
            'rmse': make_scorer(lambda yt, yp: np.sqrt(mean_squared_error(yt, yp)), greater_is_better=False),
            'mae': make_scorer(mean_absolute_error, greater_is_better=False)
        })
        rmse_cv = float(-cv['test_rmse'].mean())
        mae_cv  = float(-cv['test_mae'].mean())

        # SHAP TreeExplainer
        explainer = shap.TreeExplainer(model)

        res = (model, scaler, explainer, r2_train, rmse_cv, len(data_model), mae_cv)
        _PRICING_MODEL_CACHE[year] = res
        print(f"[ML] GBR entrenado: {len(data_model)} obs, R²_train={r2_train:.4f}, RMSE_CV={rmse_cv:.4f}")
        return res
    except Exception as e:
        print(f"[ML] Error: {e}")
        import traceback; traceback.print_exc()
        return None


def _calc_income_adjustment(income: float, pib_pc: float) -> float:
    """
    Ajuste continuo por perfil del cliente basado en income_ratio.
    Fuente: HIPOTECAS_PROV.ipynb — función sigmoidal tanh.
    income_ratio = ingreso_anual / PIB_pc_provincial
      ratio ≈ 1.0 → ajuste ≈ 0
      ratio > 1.5 → bonificación hasta -0.25%
      ratio < 0.5 → penalización hasta +0.30%
    """
    if pib_pc <= 0:
        return 0.0
    income_ratio = (income * 12) / pib_pc
    x = (income_ratio - 1.0) * 2.0
    adj = -0.25 * np.tanh(x)
    if income_ratio < 0.5:
        adj += 0.05
    return round(float(adj), 4)


def _compute_ml_optimal_rate(model, scaler, explainer, macro_vals: dict,
                              euribor: float, aprc: float,
                              loan: float, income: float, other_debts: float,
                              n_months: int, tipo: str,
                              base_diferencia: float, pib_pc_prov: float) -> dict:
    """
    Calcula tipo óptimo con GBR + SHAP + ajuste por perfil:
    1. Predice spread base con GBR
    2. Aplica ajuste sigmoidal por income_ratio (ingresos vs PIB_pc provincial)
    3. Calcula SHAP contributions para explicabilidad AI Act
    4. Busca DTI máximo por búsqueda binaria
    """
    x = [[macro_vals[f] for f in _ML_FEATURES]]
    x_s = scaler.transform(x)
    ml_spread_base = float(model.predict(x_s)[0])

    # SHAP values para explicabilidad
    shap_values = explainer.shap_values(x_s)
    expected_value = float(explainer.expected_value)
    shap_contributions = []
    for i, feat in enumerate(_ML_FEATURES):
        shap_contributions.append({
            'variable': feat,
            'value': round(float(macro_vals[feat]), 3),
            'contribution': round(float(shap_values[0][i]), 4)
        })
    shap_contributions.sort(key=lambda x: abs(x['contribution']), reverse=True)

    # Ajuste por perfil del cliente
    profile_adj = _calc_income_adjustment(income, pib_pc_prov)
    ml_spread_final = max(0.0, ml_spread_base + profile_adj)

    # Tipo bruto
    if tipo == 'variable':
        ml_rate_raw = euribor + ml_spread_final
    else:
        ml_rate_raw = aprc + profile_adj + 0.50

    # Tipo final: rate base + ajuste perfil, con suelo mínimo
    ml_rate = max(ml_rate_raw, 0.5)

    return {
        'ml_spread_base':   round(ml_spread_base, 4),
        'ml_spread_final':  round(ml_spread_final, 4),
        'profile_adj':      profile_adj,
        'income_ratio':     round((income * 12) / pib_pc_prov, 3) if pib_pc_prov > 0 else 0,
        'ml_rate_raw':      round(ml_rate_raw, 4),
        'ml_rate':          round(ml_rate, 4),
        'shap_expected':    round(expected_value, 4),
        'shap_contributions': shap_contributions,
    }


@app.route('/api/hipoteca-recomendacion', methods=['POST'])
def hipoteca_recomendacion():
    print("[DEBUG ROUTE] Endpoint /api/hipoteca-recomendacion alcanzado!", flush=True)
    """
    Full mortgage recommendation with:
    - Real APRC/Euribor spread from tipos CSV
    - Optional custom purchase price
    - DTI tiers: <35% approved, 35-45% "analista de riesgos", >45% denied
    - Other monthly debts included in DTI
    - CCAA-based max financing % (young buyer bonus)
    - Tax calculation (ITP/IVA + AJD + notary + registry) per CCAA
    """
    data = request.json
    year = str(data.get('year', '2020'))
    tipo = data.get('tipo', 'variable')
    income = float(data.get('income', 0))
    savings = float(data.get('savings', 0))
    age = int(data.get('age', 35))
    province = data.get('province', '')
    other_debts = float(data.get('other_debts', 0))
    price_mode = data.get('price_mode', 'auto')  # 'auto' or 'manual'
    custom_price = float(data.get('custom_price', 0))

    if df.empty:
        return jsonify({"error": "No hay datos disponibles."})
    if not province:
        return jsonify({"error": "Debes seleccionar una provincia."})

    FUTURE_YEARS = ["2026", "2027", "2028", "2029", "2030"]
    is_future = year in FUTURE_YEARS
    _build_forecasts()
    
    ydf = df[df['Trimestre'].str.startswith(str(year))].copy()
    if is_future and ydf.empty:
        ydf = df[df['Trimestre'].str.startswith("2025")].copy()

    if ydf.empty:
        return jsonify({"error": f"Sin datos para {year}."})

    macro_agg = ydf[['IPC', 'Tasa_Paro', 'PIB_pc', 'tasa_ahorro']].mean()

    for col in ['IPC', 'Tasa_Paro', 'PIB_pc', 'tasa_ahorro']:
        if pd.isna(macro_agg[col]) or macro_agg[col] == 0 or is_future:
            # CSV provincial: futuro (2026-2030) o 2025 con NaN (INE pendiente)
            use_csv = is_future or (year == "2025" and pd.isna(macro_agg[col]))
            if use_csv and province and not df_prov_preds.empty:
                mask = (
                    (df_prov_preds['provincia'] == province) &
                    (df_prov_preds['trimestre'].str.startswith(str(year))) &
                    (df_prov_preds['variable'] == col)
                )
                prov_vals = df_prov_preds[mask]['valor']
                if not prov_vals.empty:
                    macro_agg[col] = prov_vals.mean()
                    continue
            # Fallback final: forward-fill desde último valor provincial real
            if col == 'PIB_pc' and province and pd.isna(macro_agg[col]):
                last_prov_pib = _get_last_provincial_pib(province)
                if last_prov_pib:
                    macro_agg[col] = last_prov_pib
                    continue
            if str(year) in _MACRO_FORECASTS.get(col, {}):
                macro_agg[col] = _MACRO_FORECASTS[col][str(year)]

    ipc = float(macro_agg['IPC'])
    tasa_paro = float(macro_agg['Tasa_Paro'])
    paro_model_info = _get_paro_model_info(province) if province else None

    if is_future:
        tipos = _get_tipos_proyectados(base_year="2025", years_ahead=int(year) - 2025)
    else:
        tipos = _get_tipos_for_year(year)
    if tipos is None:
        fallback = _get_tipos_for_year("2025") or {'euribor': 2.5, 'aprc': 3.7, 'diferencia': 1.2}
        tipos = fallback
    euribor = tipos['euribor']
    aprc    = tipos['aprc']
    base_diferencia = max(tipos['diferencia'], 0.10)  # Suelo: ningún banco ofrece diferencial negativo


    # Province price
    precio_m2_raw = ydf['Precio_m2'].mean()
    precio_m2 = float(precio_m2_raw) if pd.notnull(precio_m2_raw) else 0.0
    
    prov_data = ydf[ydf['Provincia'] == province]
    if not prov_data.empty:
        prov_m2 = prov_data['Precio_m2'].mean()
        if pd.notnull(prov_m2):
            precio_m2 = float(prov_m2)
    
    if is_future:
        # Notebook logic for price future: Naive + trend or BCE scenario
        if str(year) in _MACRO_FORECASTS.get('Precio_m2', {}):
             precio_m2 = _MACRO_FORECASTS['Precio_m2'][str(year)]
    
    # Transmisiones (Demanda local)
    transmisiones_total = int(prov_data['Transmisiones_Total'].sum()) if not prov_data.empty else 0
    
    if is_future:
        if str(year) in _MACRO_FORECASTS.get('Transmisiones_Total', {}):
            transmisiones_total = int(_MACRO_FORECASTS['Transmisiones_Total'][str(year)] / 52) # approximation
    
    if transmisiones_total == 0:
        transmisiones_total = int(ydf['Transmisiones_Total'].mean() * 4) if not ydf['Transmisiones_Total'].empty else 0

    # Purchase price
    if price_mode == 'manual' and custom_price > 0:
        estimated_price = custom_price
    else:
        estimated_price = precio_m2 * 80  # standard 80m2

    # CCAA & young buyer financing %
    ccaa = _get_ccaa(province)
    std_financing_pct = 80.0
    young_max_pct, young_age_limit = YOUNG_FINANCING.get(ccaa, (80, 35))
    is_young_buyer = age <= young_age_limit and ccaa in YOUNG_FINANCING
    max_financing_pct = young_max_pct if is_young_buyer else std_financing_pct

    # Tax calculation (second-hand assumption — more common)
    tax_info = _calc_taxes(estimated_price, ccaa, age, is_new_build=False)
    total_taxes = tax_info['total']

    # Effective savings after taxes
    effective_savings = savings - total_taxes
    min_down_payment = estimated_price * (1 - max_financing_pct / 100)
    loan_amount = estimated_price * min(max_financing_pct, 80) / 100  # CaixaBank max 80% normally

    if is_young_buyer and max_financing_pct > 80:
        # With young program, bank can finance more
        loan_amount = estimated_price * max_financing_pct / 100

    # Plazo: el usuario elige, pero se aplica siempre el límite de edad
    requested_years = int(data.get('tenure_years', 25))
    max_by_age = max(5, min(30, 75 - age))
    tenure_years = max(5, min(requested_years, max_by_age))

    effective_rate = max(aprc if tipo == 'fijo' else (euribor + base_diferencia), 0.5) / 100

    # Eliminamos el diff_adjustment arbitrario por tramos de ingresos según feedback del usuario
    diff_adjustment = 0.0

    # +0.75% surcharge if property price is < 100,000 EUR
    low_loan_surcharge = 0.75 if estimated_price < 100000 else 0.0

    diferencia_final = round(base_diferencia + diff_adjustment + low_loan_surcharge, 2)

    if tipo == 'variable':
        rate = round(euribor + diferencia_final, 2)
    else:
        # Fijo includes base surcharge (0.50) + low_loan_surcharge
        rate = round(aprc + diff_adjustment + 0.50 + low_loan_surcharge, 2)

    # Monthly installment
    effective_annual = max(rate, 0.5) / 100
    n = tenure_years * 12
    monthly_r = effective_annual / 12
    if monthly_r > 0:
        monthly_installment = loan_amount * monthly_r * (1 + monthly_r) ** n / ((1 + monthly_r) ** n - 1)
    else:
        monthly_installment = loan_amount / n

    # DTI (includes other fixed debts)
    total_monthly_obligations = monthly_installment + other_debts
    dti_ratio = (total_monthly_obligations / income * 100) if income > 0 else 999

    # ── Modelo ML de pricing óptimo (GBR + SHAP — HIPOTECAS_PROV.ipynb) ──
    ml_result = None
    ml_r2, ml_rmse, ml_mae = None, None, None
    ml_rate, ml_spread = None, None
    ml_transparency = None
    contributions = []

    # PIB_pc provincial (para income_ratio)
    pib_pc_prov = float(macro_agg['PIB_pc'])
    if not prov_data.empty and not prov_data['PIB_pc'].isna().all():
        pib_pc_prov = float(prov_data['PIB_pc'].mean())

    # Provincial predictions for future years
    if is_future and not df_prov_preds.empty:
        pp_yr = df_prov_preds[(df_prov_preds['year'] == year) if 'year' in df_prov_preds.columns
                              else (df_prov_preds['trimestre'].str[:4] == year)]
        pp_prov = pp_yr[pp_yr['provincia'] == province] if not pp_yr.empty else pd.DataFrame()
        for var_name, macro_key in [('PIB_pc','PIB_pc'), ('Tasa_Paro','Tasa_Paro'),
                                     ('Precio_m2','Precio_m2'), ('tasa_ahorro','tasa_ahorro')]:
            vals = pp_prov[pp_prov['variable'] == var_name]['valor'] if not pp_prov.empty else pd.Series()
            if not vals.empty:
                val = float(vals.mean())
                macro_agg[macro_key] = val
                if var_name == 'PIB_pc':
                    pib_pc_prov = val
                elif var_name == 'Precio_m2':
                    precio_m2 = val
                    if price_mode != 'manual':
                        estimated_price = precio_m2 * 80

    ml_model_result = _train_ml_pricing_model(year)
    if ml_model_result:
        ml_model, ml_scaler, ml_explainer, ml_r2, ml_rmse, ml_n, ml_mae = ml_model_result
        macro_vals = {
            'Euribor': euribor, 'IPC': ipc, 'Tasa_Paro': float(macro_agg['Tasa_Paro']),
            'PIB_pc': pib_pc_prov, 'tasa_ahorro': float(macro_agg['tasa_ahorro']),
            'Precio_m2': precio_m2
        }
        ml_result = _compute_ml_optimal_rate(
            ml_model, ml_scaler, ml_explainer, macro_vals,
            euribor, aprc,
            loan_amount, income, other_debts, tenure_years * 12,
            tipo, base_diferencia, pib_pc_prov
        )
        ml_spread    = ml_result['ml_spread_final']
        ml_rate_raw  = ml_result['ml_rate_raw'] + low_loan_surcharge
        ml_rate      = round(max(ml_rate_raw, 0.5), 4)

        # SHAP contributions (reemplazan los coeficientes LR)
        contributions = ml_result.get('shap_contributions', [])

        # Top feature by SHAP
        top_feature = contributions[0]['variable'] if contributions else 'Euribor'

        # Transparencia ML (GBR + SHAP — AI Act)
        ml_transparency = {
            'model_type': 'GradientBoostingRegressor',
            'explainability': 'SHAP TreeExplainer (AI Act Art. 13-14)',
            'is_future': is_future,
            'n_samples': ml_n,
            'r2_train': round(ml_r2, 4),
            'rmse_cv': round(ml_rmse, 4),
            'mae_cv': round(ml_mae, 4),
            'spread_base': ml_result['ml_spread_base'],
            'spread_final': ml_result['ml_spread_final'],
            'profile_adj': ml_result['profile_adj'],
            'income_ratio': ml_result['income_ratio'],
            'shap_expected': ml_result['shap_expected'],
            'top_factor': top_feature,
            'importances': {c['variable']: c['contribution'] for c in contributions},
            # Valores macro usados
            'euribor_used': round(euribor, 3),
            'ipc_used': round(ipc, 3),
            'precio_m2_used': round(precio_m2, 2),
            'pib_pc_prov_used': round(pib_pc_prov, 2),
            'data_source': 'Proyecciones BCE + SARIMA provincial' if is_future else 'Datos históricos',
        }

    # ── Tipo aplicado: el banco se queda con el mayor de los dos ──
    if ml_rate is not None:
        if ml_rate >= rate:
            applied_rate = ml_rate
            applied_type = 'ml'
        else:
            applied_rate = rate
            applied_type = 'basico'
    else:
        applied_rate = rate
        applied_type = 'basico'

    # ── Decision ──
    # Check savings sufficiency (after taxes)
    savings_ok = effective_savings >= min_down_payment
    dti_decision = "approved" if dti_ratio < 35 else ("analyst" if dti_ratio <= 45 else "denied")
    other_denial = None

    if income == 0:
        dti_decision = "denied"
        other_denial = "No has indicado ingresos. El banco necesita verificar tu capacidad de pago."
    elif age > 65:
        dti_decision = "denied"
        other_denial = "Con tu edad actual el plazo maximo no permite estructurar una hipoteca estandar."

    if not savings_ok:
        overall_status = "denied"
        denial_reason = (
            f"No dispones de ahorros netos suficientes tras pagar los impuestos de compra. "
            f"Precio estimado: {estimated_price:,.0f} EUR. "
            f"Impuestos y gastos estimados ({ccaa or 'tu CCAA'}): {total_taxes:,.0f} EUR. "
            f"Ahorros netos disponibles: {effective_savings:,.0f} EUR. "
            f"Entrada minima requerida ({100 - max_financing_pct:.0f}% del precio): {min_down_payment:,.0f} EUR."
        )
    elif dti_decision == "denied":
        overall_status = "denied"
        denial_reason = other_denial or (
            f"La ratio deuda/ingresos ({dti_ratio:.1f}%) supera el maximo del 45%. "
            f"Cuota hipotecaria estimada: {monthly_installment:,.0f} EUR/mes. "
            f"Otras deudas: {other_debts:,.0f} EUR/mes. "
            f"Total obligaciones: {total_monthly_obligations:,.0f} EUR/mes sobre {income:,.0f} EUR/mes."
        )
    elif dti_decision == "analyst":
        overall_status = "analyst"
        denial_reason = (
            f"Tu ratio deuda/ingresos ({dti_ratio:.1f}%) esta entre 35% y 45%. "
            f"Esta operacion requiere revision por un analista de riesgos. "
            f"Cuota mensual estimada: {monthly_installment:,.0f} EUR. "
            f"Otras deudas declaradas: {other_debts:,.0f} EUR/mes."
        )
    else:
        overall_status = "approved"
        denial_reason = ""

    approved = overall_status == "approved"

    # ── Explanation ──
    if overall_status == "approved":
        if tipo == 'variable':
            explanation = (
                f"Para el ano {year}, el Euribor a 12 meses era {euribor:.2f}%. "
                f"La TAE media de mercado (APRC) fue {aprc:.2f}%, con un diferencial real banco-Euribor de {base_diferencia:.2f}% "
                f"(APRC {aprc:.2f}% - Euribor {euribor:.2f}%). "
            )
            if diff_adjustment != 0:
                explanation += f"Ajuste por perfil de ingresos: {diff_adjustment:+.2f}%. "
            explanation += f"Tipo final: Euribor {euribor:.2f}% + diferencial {diferencia_final:.2f}% = {rate:.2f}% TIN."
        else:
            explanation = (
                f"En hipoteca fija para {year}, la TAE media de mercado era {aprc:.2f}%. "
                f"Ajuste por perfil: {diff_adjustment:+.2f}%, mas prima de tipo fijo +0.50%. "
                f"Tipo fijo resultante: {rate:.2f}% TIN constante durante toda la vida del prestamo."
            )
    else:
        explanation = denial_reason

    return jsonify({
        "status": overall_status,
        "approved": approved,
        "tipo": tipo,
        "rate": rate if overall_status == "approved" else 0.0,
        "euribor": euribor, "aprc": aprc, "diferencia": base_diferencia,
        "differential": diferencia_final,
        "explanation": explanation,
        "contributions": contributions,
        "monthly_installment": round(monthly_installment, 2),
        "dti_ratio": round(dti_ratio, 1),
        "dti_decision": dti_decision,
        "total_monthly_obligations": round(total_monthly_obligations, 2),
        "price_m2": round(precio_m2, 2),
        "estimated_price": round(estimated_price, 0),
        "loan_amount": round(loan_amount, 0),
        "ipc": round(ipc, 2), "tasa_paro": round(tasa_paro, 2),
        "province": province, "ccaa": ccaa, "year": year,
        "transmisiones_total": transmisiones_total,
        "is_young_buyer": is_young_buyer,
        "max_financing_pct": max_financing_pct,
        "young_age_limit": young_age_limit,
        "taxes": {
            "total": round(total_taxes, 2),
            "itp": tax_info.get('itp', 0),
            "itp_rate": tax_info.get('itp_rate'),
            "itp_rate_gen": tax_info.get('itp_rate_gen'),
            "iva": tax_info.get('iva', 0),
            "ajd": tax_info.get('ajd', 0),
            "notaria": tax_info.get('notaria', 0),
            "registro": tax_info.get('registro', 0),
            "is_young_rate": tax_info.get('is_young_rate', False),
            "tipo_impuesto": tax_info.get('tipo_impuesto', ''),
        },
        "effective_savings": round(effective_savings, 2),
        "min_down_payment": round(min_down_payment, 2),
        "tenure_years": tenure_years,
        # ── ML Pricing ──
        "ml_rate":       round(ml_rate, 4) if ml_rate is not None else None,
        "ml_spread":     round(ml_spread, 4) if ml_spread is not None else None,
        "ml_r2":         round(ml_r2, 4) if ml_r2 is not None else None,
        "ml_rmse":       round(ml_rmse, 4) if ml_rmse is not None else None,

        "applied_rate":  round(applied_rate, 4),
        "applied_type":  applied_type,
        "ml_transparency": ml_transparency,
        "is_future":     is_future,
        "paro_model_info": paro_model_info,
    })


# ╔══════════════════════════════════════════════╗
# ║  NOA — MORTGAGE ADVISOR CHAT (CLIENTE)       ║
# ╚══════════════════════════════════════════════╝

@app.route('/api/noa-chat', methods=['POST'])
def noa_chat():
    payload = request.json
    user_msg = payload.get('message', '').strip()
    ctx = payload.get('context', {})

    if not gemini_model:
        return jsonify({"reply": "El asistente no esta disponible. Falta la API Key de Gemini."})

    try:
        status_str = {"approved": "Aprobada", "analyst": "Pendiente de analista de riesgos", "denied": "Denegada"}.get(ctx.get('status', ''), 'Desconocida')
        context_text = f"""
Eres Noa, asesora hipotecaria virtual de CaixaBank. Eres profesional, clara y cercana. No uses emojis.
Conoces el perfil completo del cliente:

- Ano de referencia: {ctx.get('year', 'desconocido')}
- Tipo de hipoteca: {ctx.get('tipo', 'desconocido')}
- Ingresos mensuales netos: {ctx.get('income', 0):,.0f} EUR/mes
- Otras deudas fijas: {ctx.get('other_debts', 0):,.0f} EUR/mes
- Ahorros brutos: {ctx.get('savings', 0):,.0f} EUR
- Impuestos y gastos de compra estimados: {ctx.get('taxes', {}).get('total', 0):,.0f} EUR
- Ahorros netos (tras impuestos): {ctx.get('effective_savings', 0):,.0f} EUR
- Edad: {ctx.get('age', 'desconocida')}
- Provincia: {ctx.get('province', 'no especificada')} | CCAA: {ctx.get('ccaa', 'desconocida')}
- Precio estimado de la vivienda: {ctx.get('estimated_price', 0):,.0f} EUR
- Euribor del ano: {ctx.get('euribor', 0):.2f}%
- APRC (TAE media de mercado): {ctx.get('aprc', 0):.2f}%
- Diferencial real (APRC - Euribor): {ctx.get('diferencia', 0):.2f}%
- Tipo ofrecido: {ctx.get('rate', 0):.2f}% TIN
- Ratio deuda/ingresos (DTI): {ctx.get('dti_ratio', 0):.1f}%
- Cuota mensual estimada: {ctx.get('monthly_installment', 0):,.0f} EUR/mes
- Decision: {status_str}
- Cliente joven (financiacion especial): {'Si, hasta ' + str(ctx.get('max_financing_pct', 80)) + '%' if ctx.get('is_young_buyer') else 'No'}

MODELO DE PRICING:
El tipo ofrecido se calcula con un modelo de Gradient Boosting + SHAP (inteligencia artificial explicable),
que analiza las variables macroeconomicas (Euribor, IPC, paro, precio m2, PIB per capita, tasa de ahorro)
y el perfil del cliente (ratio ingresos/PIB_pc provincial) para determinar el diferencial justo.
SHAP descompone la prediccion en la contribucion exacta de cada variable, cumpliendo la AI Act bancaria.
{'Para este ano futuro, los datos macro provienen de Proyecciones del BCE (Euribor, IPC) y modelos SARIMA provinciales.' if ctx.get('is_future') else 'Los datos macro son historicos del dataset.'}

Responde la pregunta del cliente de forma clara y concisa. No repitas toda la informacion; ve directo a lo que pregunta.
Si la hipoteca fue denegada o requiere analista, orienta sobre que puede mejorar.
Si pregunta por que ese tipo de interes, explica las contribuciones SHAP de forma comprensible.

Pregunta: "{user_msg}"
"""
        response = gemini_model.generate_content(context_text)
        reply = response.text.replace('\n', '<br>')
    except Exception as e:
        print(f"Noa error: {e}")
        reply = "Ha ocurrido un error al conectar con la asistente. Intentalo de nuevo."

    return jsonify({"reply": reply})


# ╔══════════════════════════════════════════════════════════╗
# ║  NOA STRATEGIC — ADVISOR CHAT (GESTOR BANCARIO)          ║
# ╚══════════════════════════════════════════════════════════╝

@app.route('/api/noa-strategic', methods=['POST'])
def noa_strategic():
    payload = request.json
    user_msg = payload.get('message', '').strip()
    ctx = payload.get('context', {})

    if not gemini_model:
        return jsonify({"reply": "Noa Strategic no disponible. Falta la API Key de Gemini."})

    try:
        status_str = {"approved":"Aprobada","analyst":"Revision analista","denied":"Denegada"}.get(ctx.get('status',''),'')
        ml_rate    = ctx.get('ml_rate')
        basic_rate = ctx.get('rate', 0)
        applied_r  = ctx.get('applied_rate', basic_rate)
        ml_r2      = ctx.get('ml_r2')
        ml_rmse    = ctx.get('ml_rmse')
        dti_max    = None  # DTI cap removed — rate is purely model-driven

        # Datos históricos del spread del año
        year = ctx.get('year', '')
        hist_spread = ''
        if year and not df.empty:
            try:
                prev_years = sorted(df['Trimestre'].str[:4].dropna().unique())
                prev_years = [y for y in prev_years if y < year][-5:]
                spread_col = 'Spread_Hipotecas' if 'Spread_Hipotecas' in df.columns else None
                if spread_col:
                    rows = []
                    for py in prev_years:
                        v = df[df['Trimestre'].str.startswith(py)][spread_col].mean()
                        rows.append(f"  · {py}: {v:.2f}%")
                    hist_spread = "Spread histórico (últimos 5 años anteriores):\n" + "\n".join(rows)
            except Exception:
                pass

        context_text = f"""
Eres Noa Strategic, asistente de análisis hipotecario interno de CaixaBank para gestores bancarios.
NO eres el chatbot del cliente. Tu lenguaje es técnico, directo y orientado a maximizar el beneficio del banco dentro del marco regulatorio.

PERFIL DEL CLIENTE:
- Año de referencia: {year}
- Tipo: {ctx.get('tipo','')}, Decisión: {status_str}
- Edad: {ctx.get('age','')} años | Provincia: {ctx.get('province','')} | CCAA: {ctx.get('ccaa','')}
- Ingresos netos: {ctx.get('income',0):,.0f} EUR/mes | Otras deudas: {ctx.get('other_debts',0):,.0f} EUR/mes
- Precio vivienda: {ctx.get('estimated_price',0):,.0f} EUR | Capital financiado: {ctx.get('loan_amount',0):,.0f} EUR
- Plazo: {ctx.get('tenure_years','')} años | DTI actual: {ctx.get('dti_ratio',0):.1f}%

- Tipo aplicado por defecto (mayor de los dos): {applied_r:.2f}%
- RECARGO ESPECIAL: {'+0.75% por precio < 100.000 EUR' if ctx.get('estimated_price',0) < 100000 else 'Ninguno'}

{hist_spread}

MODELO DE PRICING (GradientBoostingRegressor + SHAP):
- Modelo: GBR con hiperparámetros conservadores (max_depth=3, min_samples_leaf=5, lr=0.06)
- Explicabilidad: SHAP TreeExplainer — conforme a AI Act (Art. 13-14)
- Tipo básico (APRC/Euribor mercado + surcharges): {basic_rate:.2f}%
- Tipo ML (GBR + ajuste perfil sigmoidal): {f"{ml_rate:.2f}%" if ml_rate else "no disponible"}
  · Spread base GBR: {f"{ctx.get('ml_spread',0):.3f}%" if ctx.get('ml_spread') else "N/A"}
  · Ajuste por perfil (income_ratio tanh): {f"{ctx.get('ml_transparency',{}).get('profile_adj',0):+.3f}%" if ctx.get('ml_transparency') else "N/A"}
  · Income ratio (ingreso_anual/PIB_pc_prov): {f"{ctx.get('ml_transparency',{}).get('income_ratio',0):.2f}" if ctx.get('ml_transparency') else "N/A"}
  · Tipo máximo sin superar DTI 35%: {f"{dti_max:.2f}%" if dti_max else "N/A"}
  · RMSE CV temporal: {f"{ctx.get('ml_transparency',{}).get('rmse_cv',0):.4f}%" if ctx.get('ml_transparency') else "N/A"}
  · MAE CV temporal: {f"{ctx.get('ml_transparency',{}).get('mae_cv',0):.4f}%" if ctx.get('ml_transparency') else "N/A"}
  · R² entrenamiento (referencia, no validación): {f"{ml_r2:.4f}" if ml_r2 is not None else "N/A"}
- Tipo aplicado (mayor de los dos): {applied_r:.2f}%
- Fuente macro: {ctx.get('ml_transparency',{}).get('data_source','Datos históricos')}

FUENTES DE DATOS:
- Variables nacionales (Euribor, IPC): Proyecciones BCE Staff Projections
- Variables provinciales (PIB_pc, Tasa_Paro, Precio_m2): Predicciones SARIMA por provincia (data_science_provincial.ipynb)
- Spread hipotecario: GBR entrenado sobre dataset_final_tfm.csv (4,368 obs, 52 provincias, 2005-2025)
- Formalización matemática: formalizacion_matematica.ipynb

ANÁLISIS ECONOMÉTRICO VAR/VECM (usa si el gestor pregunta sobre dinámica estructural del mercado o justificación de variables):
- VAR en diferencias (4 var: Δlog_Hipotecas, Δlog_Precio_m2, ΔEuribor, Δlog_PIB_pc): FEVD a corto plazo → 70.3% inercia propia, 18.1% precio/tipos, 11.5% factores macro.
- VECM cointegrado con 5 variables (añade Log_Materiales). Test de Johansen: r=1. Vector de cointegración β (normalizado sobre Log_Hipotecas): +0.35·Log_PIB_pc, +2.48·Log_Precio_m2, −0.10·Euribor, −1.09·Log_Materiales.
- Velocidades de ajuste α: Log_Hipotecas α=−0.44 (corrige 44%/trimestre, semivida 1.2T, variable más endógena); Log_Precio_m2 α=−0.006 (semivida ~30 años, rigidez estructural); Euribor y PIB_pc no significativos (exógenos).
- FEVD a 20 trimestres (5 años): Log_Precio_m2 53.3%, Log_Materiales 38.8%, PIB_pc 2.6%, Euribor 2.2%. Hallazgo clave: el Euribor explica solo el 2.2% de la varianza a largo plazo; el mercado hipotecario está dominado por la escasez de oferta (costes de construcción) y el precio del m², no por el coste del dinero.
- IRF VECM (efectos permanentes): shock +1σ en Log_Precio_m2 → +0.61 log-pts acumulados a 20T; shock en Log_Materiales → −0.50 log-pts; shock en Euribor → −0.09 log-pts (efecto transitorio).

INSTRUCCIONES:
- REGLA DE NEGOCIO: Si el precio es < 100.000€, se aplica obligatoriamente +0.75% por gastos operativos fijos y mayor riesgo relativo.
- Si el gestor pregunta sobre el modelo ML, explica GBR + SHAP: GBR captura no-linealidades macro, SHAP proporciona contribuciones exactas auditables.
- El ajuste por perfil usa una función tanh centrada en income_ratio=1.0 (ingresos anuales / PIB per cápita provincial).
- Si pregunta cómo persuadir al cliente, da argumentos concretos basados en datos reales del perfil.
- Límites DTI: <35% aprobación automática, 35-45% analista de riesgos, >45% denegación.
- NO uses emojis. Sé técnico y conciso.

Pregunta del gestor: "{user_msg}"
"""
        response = gemini_model.generate_content(context_text)
        reply = response.text.replace('\n', '<br>')
    except Exception as e:
        print(f"Noa Strategic error: {e}")
        reply = "Error al conectar con Noa Strategic. Inténtalo de nuevo."

    return jsonify({"reply": reply})



# ╔══════════════════════════════════════════════╗
# ║  ADMIN: CHART UPLOAD                         ║
# ╚══════════════════════════════════════════════╝

# publish_chart() helper inyectado en el código del usuario.
# Serializa los datos de Chart.js a stdout para que el servidor los recoja.
_PUBLISH_CHART_HELPER = r"""
import json as _json_pc, sys as _sys_pc
_PUBLISHED_CHARTS = []

def publish_chart(labels, datasets, title='Grafico', chart_type='bar', description=None, year_for_labels=None):
    # Publica un grafico interactivo Chart.js en el Dashboard.
    # labels          : lista de etiquetas del eje X
    # datasets        : lista de dicts con 'label', 'data', y opcionalmente 'color', 'fill', 'tension'
    # title           : titulo del grafico
    # chart_type      : 'bar', 'line', 'doughnut', 'pie'
    # year_for_labels : lista del mismo tamano que labels con el anio (str/int) de cada punto.
    #                   Permite al filtro global refiltar los datos en el Dashboard.
    entry = {
        'title': title,
        'chart_type': chart_type,
        'labels': [str(l) for l in labels],
        'datasets': datasets,
        'description': description or title,
        'year_for_labels': [str(y) for y in year_for_labels] if year_for_labels else None
    }
    _PUBLISHED_CHARTS.append(entry)

def _flush_published_charts():
    if _PUBLISHED_CHARTS:
        print('CHARTJS_DATA:' + _json_pc.dumps(_PUBLISHED_CHARTS))

import atexit as _atexit_pc
_atexit_pc.register(_flush_published_charts)
"""

@app.route('/admin/upload-chart', methods=['POST'])
def upload_chart():
    if not session.get('admin'):
        return jsonify({"error": "No autorizado"}), 401
    if 'chart_file' not in request.files:
        return jsonify({"error": "No se adjunto ningun fichero"}), 400
    file = request.files['chart_file']
    filename = file.filename
    description = request.form.get('description', filename)
    if not any(filename.endswith(ext) for ext in ('.ipynb', '.py')):
        return jsonify({"error": "Solo se admiten .ipynb o .py"}), 400
    tmpdir = tempfile.mkdtemp()
    try:
        import sys as _sys
        src = os.path.join(tmpdir, filename)
        file.save(src)
        if filename.endswith('.ipynb'):
            nb_result = subprocess.run(
                [_sys.executable, '-m', 'nbconvert', '--to', 'script', src, '--output-dir', tmpdir],
                capture_output=True, timeout=60
            )
            py_src = os.path.join(tmpdir, os.path.splitext(filename)[0] + '.py')
            if not os.path.exists(py_src):
                err = nb_result.stderr.decode(errors='ignore')[:400]
                return jsonify({"error": f"No se pudo convertir el notebook: {err}"}), 400
            src = py_src
        with open(src, 'r', errors='ignore') as f:
            code = f.read()
        _web_dir_uc = os.path.dirname(os.path.abspath(__file__))
        _preamble_uc = f"""
import os as _os, pandas as _pd
DATASET_PATH = r'{DATASET_PATH}'
try:
    df = _pd.read_csv(DATASET_PATH)
except Exception:
    df = _pd.DataFrame()
"""
        wrapper = f"""
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as _plt, os as _os
{_PUBLISH_CHART_HELPER}
{_preamble_uc}
{code}
# Fallback: si no usó publish_chart(), guardar matplotlib figures como PNG
_chartjs_used = bool(_PUBLISHED_CHARTS)
if not _chartjs_used:
    _out = r'{CUSTOM_CHARTS_DIR}'
    _ids = []
    for _i, _f in enumerate(_plt.get_fignums()):
        _fig = _plt.figure(_f)
        _cid = '{uuid.uuid4().hex[:8]}_' + str(_i)
        _fig.savefig(_os.path.join(_out, _cid + '.png'), dpi=120, bbox_inches='tight')
        _ids.append(_cid + '.png')
        _plt.close(_fig)
    print('CHART_IDS:' + ','.join(_ids))
"""
        wp = os.path.join(tmpdir, '_w.py')
        with open(wp, 'w') as f:
            f.write(wrapper)
        result = subprocess.run([_sys.executable, wp], capture_output=True, text=True, timeout=120, cwd=_web_dir_uc)
        _filterable = request.form.get('filterable', '0') == '1'
        return _process_chart_output(result, description, filename, filterable=_filterable)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "El script tardo demasiado (>120s)."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ╔══════════════════════════════════════════════╗
# ║  ADMIN: EXECUTE RAW CODE (Corporate Style)   ║
# ╚══════════════════════════════════════════════╝

# CaixaBank corporate matplotlib style — injected before every user script
_CAIXABANK_STYLE = r"""
import matplotlib as _mpl
import matplotlib.pyplot as _plt

_CB_COLORS = [
    '#007BC0',  # Azul primario
    '#FF6600',  # Naranja
    '#003F6C',  # Azul oscuro
    '#66C4E8',  # Azul claro
    '#FF9933',  # Naranja claro
    '#00A8E0',  # Cian
    '#CC5200',  # Naranja oscuro
    '#004E96',  # Azul medio
]

_mpl.rcParams.update({
    'figure.facecolor':      '#FFFFFF',
    'axes.facecolor':        '#FAFCFF',
    'axes.edgecolor':        '#CBD5E0',
    'axes.labelcolor':       '#333333',
    'axes.titleweight':      'bold',
    'axes.titlecolor':       '#003F6C',
    'axes.titlesize':        14,
    'axes.labelsize':        11,
    'axes.grid':             True,
    'grid.color':            '#E2EAF4',
    'grid.linestyle':        '-',
    'grid.linewidth':        0.6,
    'grid.alpha':            0.7,
    'axes.prop_cycle':       _mpl.cycler(color=_CB_COLORS),
    'text.color':            '#333333',
    'xtick.color':           '#555555',
    'ytick.color':           '#555555',
    'xtick.labelsize':       9,
    'ytick.labelsize':       9,
    'font.family':           'sans-serif',
    'font.sans-serif':       ['Open Sans', 'Arial', 'Helvetica Neue', 'DejaVu Sans'],
    'font.size':             10,
    'figure.dpi':            120,
    'figure.figsize':        [9, 5],
    'lines.linewidth':       2,
    'lines.markersize':      6,
    'patch.linewidth':       0.5,
    'legend.framealpha':     0.9,
    'legend.edgecolor':      '#CBD5E0',
    'legend.fontsize':       9,
    'savefig.bbox':          'tight',
    'savefig.facecolor':     '#FFFFFF',
})
"""

def _process_chart_output(result, description, source_name, filterable=False):
    """Procesa la salida de un script Python de gráficos.
    Prioriza datos CHARTJS_DATA (interactivo); fallback a CHART_IDS (PNG)."""
    chartjs_entries = []
    png_ids = []
    for line in result.stdout.split('\n'):
        if line.startswith('CHARTJS_DATA:'):
            try:
                charts = json.loads(line[13:])
                chartjs_entries.extend(charts)
            except Exception:
                pass
        elif line.startswith('CHART_IDS:'):
            png_ids = [c.strip() for c in line[10:].split(',') if c.strip()]

    if not chartjs_entries and not png_ids:
        stderr_snippet = result.stderr[:600] if result.stderr else '(sin salida de error)'
        return jsonify({"error": f"No se genero ningun grafico. {stderr_snippet}"}), 400

    with open(CUSTOM_CHARTS_INDEX, 'r') as f:
        idx = json.load(f)

    published = []
    # Chart.js interactivos
    for entry in chartjs_entries:
        cid = uuid.uuid4().hex[:12]
        record = {
            "id": cid,
            "render_type": "chartjs",
            "chart_type": entry.get('chart_type', 'bar'),
            "title": entry.get('title', description),
            "description": entry.get('description', description),
            "labels": entry.get('labels', []),
            "datasets": entry.get('datasets', []),
            "year_for_labels": entry.get('year_for_labels', None),
            "filterable": filterable,
            "source": source_name,
            "created_at": datetime.now().isoformat()
        }
        idx.append(record)
        published.append(cid)
    # PNG fallback
    for cid in png_ids:
        record = {
            "id": cid,
            "render_type": "png",
            "filename": cid,
            "description": description,
            "filterable": filterable,
            "source": source_name,
            "created_at": datetime.now().isoformat()
        }
        idx.append(record)
        published.append(cid)

    with open(CUSTOM_CHARTS_INDEX, 'w') as f:
        json.dump(idx, f, indent=2)
    return jsonify({"success": True, "charts": published, "count": len(published)})


@app.route('/admin/execute-code', methods=['POST'])
def execute_code():
    """Execute raw Python chart code with automatic CaixaBank corporate styling."""
    if not session.get('admin'):
        return jsonify({"error": "No autorizado"}), 401
    data = request.get_json(silent=True) or {}
    user_code = data.get('code', '').strip()
    description = data.get('description', 'Grafico personalizado')
    if not user_code:
        return jsonify({"error": "No se recibio codigo"}), 400

    tmpdir = tempfile.mkdtemp()
    try:
        import sys as _sys
        _web_dir = os.path.dirname(os.path.abspath(__file__))
        _dataset_path = DATASET_PATH
        _preamble = f"""
import os as _os, pandas as _pd
DATASET_PATH = r'{_dataset_path}'
try:
    df = _pd.read_csv(DATASET_PATH)
except Exception:
    df = _pd.DataFrame()
"""
        wrapper = f"""import matplotlib; matplotlib.use('Agg')
{_CAIXABANK_STYLE}
{_PUBLISH_CHART_HELPER}
{_preamble}
# ─── Codigo del usuario ───────────────────────────────────────────────────────
{user_code}

# ─── Fallback: captura matplotlib si no se usó publish_chart() ───────────────
import os as _os
if not _PUBLISHED_CHARTS:
    _out = r'{CUSTOM_CHARTS_DIR}'
    _ids = []
    for _i, _fn in enumerate(_plt.get_fignums()):
        _fig = _plt.figure(_fn)
        _cid = '{uuid.uuid4().hex[:8]}_' + str(_i)
        _fig.savefig(_os.path.join(_out, _cid + '.png'), dpi=120, bbox_inches='tight')
        _ids.append(_cid + '.png')
        _plt.close(_fig)
    print('CHART_IDS:' + ','.join(_ids))
"""
        wp = os.path.join(tmpdir, '_exec.py')
        with open(wp, 'w', encoding='utf-8') as f:
            f.write(wrapper)

        result = subprocess.run(
            [_sys.executable, wp],
            capture_output=True, text=True, timeout=120, cwd=_web_dir
        )
        return _process_chart_output(result, description, 'Editor corporativo', filterable=data.get('filterable', False))

    except subprocess.TimeoutExpired:
        return jsonify({"error": "El script tardo demasiado (>120s)."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)



@app.route('/api/custom-charts')
def list_custom_charts():
    try:
        with open(CUSTOM_CHARTS_INDEX, 'r') as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify([])


@app.route('/api/custom-charts/<chart_id>', methods=['DELETE'])
def delete_custom_chart(chart_id):
    if not session.get('admin'):
        return jsonify({"error": "No autorizado"}), 401
    try:
        with open(CUSTOM_CHARTS_INDEX, 'r') as f:
            idx = json.load(f)
        item = next((i for i in idx if i['id'] == chart_id), None)
        if not item:
            return jsonify({"error": "No encontrado"}), 404
        p = os.path.join(CUSTOM_CHARTS_DIR, item['filename'])
        if os.path.exists(p):
            os.remove(p)
        idx = [i for i in idx if i['id'] != chart_id]
        with open(CUSTOM_CHARTS_INDEX, 'w') as f:
            json.dump(idx, f, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ╔══════════════════════════════════════════════╗
# ║  AI CHATBOT (global dashboard)              ║
# ╚══════════════════════════════════════════════╝

import google.generativeai as _old_genai  # kept for import compat, but logic uses new SDK below
API_KEY = os.environ.get("GEMINI_API_KEY")
if API_KEY:
    _genai_client = genai.Client(api_key=API_KEY)
    # Wrapper para mantener .generate_content como antes
    class _ModelWrapper:
        def __init__(self, client, model_name):
            self._client = client
            self._model  = model_name
        def generate_content(self, prompt, **kwargs):
            resp = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                **kwargs
            )
            return resp
    gemini_model = _ModelWrapper(_genai_client, 'gemini-2.5-flash')
else:
    gemini_model = None
    print("Warning: GEMINI_API_KEY not found.")


@app.route('/api/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').strip()
    if df.empty:
        return jsonify({"reply": "No tengo datos cargados."})
    if not gemini_model:
        return jsonify({"reply": "Asistente IA deshabilitado. Falta API Key de Gemini."})
    try:
        ctx_df = df.copy()
        ctx_tipos = df_tipos.copy() if not df_tipos.empty else pd.DataFrame()
        yrs = re.findall(r'\b20\d{2}\b', user_msg)
        if yrs:
            ctx_df = ctx_df[ctx_df['Trimestre'].str.contains('|'.join(yrs), na=False)]
            if not ctx_tipos.empty:
                ctx_tipos = ctx_tipos[ctx_tipos['TIME_PERIOD'].str.contains('|'.join(yrs), na=False)]
        
        if 'Provincia' in ctx_df.columns:
            matched = [p for p in df['Provincia'].dropna().unique() if p.lower() in user_msg.lower()]
            if matched:
                ctx_df = ctx_df[ctx_df['Provincia'].isin(matched)]
                
        if not ctx_df.empty and len(ctx_df) > 5:
            ctx_df = ctx_df.sample(5)
        if not ctx_tipos.empty and len(ctx_tipos) > 5:
            ctx_tipos = ctx_tipos.sample(5)
            
        relevant = ctx_df.to_string(index=False) if not ctx_df.empty else "(Sin datos Inmobiliarios)"
        relevant_tipos = ctx_tipos.to_string(index=False) if not ctx_tipos.empty else "(Sin datos Tipos de Interés)"
        
        prompt = f"""
Eres tu un Asistente Ejecutivo de Reporting para Directivos de CaixaBank.
Tu objetivo es responder preguntas sobre el mercado inmobiliario, macroeconomía, rentabilidad y beneficios o métricas de CaixaBank o del sector bancario.
Usa la herramienta de búsqueda en Google (cuando te pregunten cosas que no sepas de memoria o recientes) para buscar información en internet sobre beneficios de CaixaBank, noticias bancarias o datos macroeconómicos actuales.
Cruza la información de internet con los datos de nuestro dataset interno cuando sea útil.
IMPORTANTE: Si el usuario te pregunta cosas fuera de contexto (OOC - Out of Context) que no tengan que ver con macroeconomía, bancos, CaixaBank, hipotecas o el mercado inmobiliario, DEBES negarte a responder educadamente.

Datos CSV Mercado Inmobiliario (Muestra filtrada de 5 filas): {relevant}
Rango temporal del dataset completo: Desde {df['Trimestre'].min()} hasta {df['Trimestre'].max() if not df.empty and 'Trimestre' in df else '2025-Q1'}.
Precio medio m2 histórico (toda la muestra): {df['Precio_m2'].mean():.2f} EUR.

Datos CSV Tipos de Interés España (Euribor, APRC, Diferencial) (Muestra filtrada de 5 filas):
{relevant_tipos}
Rango temporal de Tipos de Interés: Desde {df_tipos['TIME_PERIOD'].min() if not df_tipos.empty else 'N/A'} hasta {df_tipos['TIME_PERIOD'].max() if not df_tipos.empty else 'N/A'}.

Análisis Econométrico VAR/VECM del mercado hipotecario español (2005-2025):
- VAR en diferencias (Δlog_Hipotecas, Δlog_Precio_m2, ΔEuribor, Δlog_PIB_pc): FEVD corto plazo → 70.3% inercia propia, 18.1% precio/tipos, 11.5% macro.
- VECM cointegrado (5 variables, añade Log_Materiales). Johansen r=1. β: Log_Hipotecas = +0.35·Log_PIB_pc +2.48·Log_Precio_m2 −0.10·Euribor −1.09·Log_Materiales.
- FEVD a 20 trimestres: Precio_m2 53.3%, Materiales 38.8%, PIB_pc 2.6%, Euribor 2.2%. El Euribor es factor transitorio; oferta y precio m2 son los conductores estructurales.
- Velocidad de ajuste: hipotecas α=−0.44 (semivida 1.2T, mercado muy reactivo); precio m2 α=−0.006 (semivida 30 años, oferta rígida).

Pregunta del directivo: "{user_msg}"
"""
        config = genai_types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.4
        )
        response = gemini_model.generate_content(prompt, config=config)
        
        # Extraer texto de respuesta
        if response.parts:
            reply_text = "".join(part.text for part in response.parts if hasattr(part, 'text') and part.text)
        else:
            reply_text = response.text or ""
            
        # Parseo basico de Markdown a HTML para frontend
        reply_html = reply_text.replace('\n', '<br>')
        reply_html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', reply_html) # Negritas
        reply_html = re.sub(r'\*(.+?)\*', r'<i>\1</i>', reply_html)     # Cursivas
        
        # Extraer fuentes desde metadata de grounding (Google Search)
        sources_html = ""
        try:
            candidates = response.candidates
            if candidates and candidates[0].grounding_metadata:
                metadata = candidates[0].grounding_metadata
                # Ver si tiene chunks/web de busqueda
                if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                    urls_vistas = set()
                    sources_list = []
                    for chunk in metadata.grounding_chunks:
                        if hasattr(chunk, 'web') and chunk.web and hasattr(chunk.web, 'uri'):
                            uri = chunk.web.uri
                            title = getattr(chunk.web, 'title', uri)
                            if uri not in urls_vistas:
                                urls_vistas.add(uri)
                                sources_list.append(f"<li><a href='{uri}' target='_blank' style='color:#007EAA;'>{title}</a></li>")
                    
                    if sources_list:
                        sources_html = "<br><br><b>Fuentes consultadas:</b><ul style='margin-top:4px; padding-left:20px; font-size:0.85rem;'>" + "".join(sources_list) + "</ul>"
        except Exception as source_e:
            print("No se pudieron extraer fuentes:", source_e)
            
        reply = reply_html + sources_html
        
    except Exception as e:
        reply = f"Error al contactar con el asistente IA: {str(e)}"
    return jsonify({"reply": reply})

# ╔══════════════════════════════════════════════╗
# ║  MORTGAGE FEASIBILITY TEST (legacy)         ║
# ╚══════════════════════════════════════════════╝

@app.route('/test-hipoteca', methods=['GET', 'POST'])
def test_hipoteca():
    result = None
    if request.method == 'POST':
        income = float(request.form.get('income', 0))
        savings = float(request.form.get('savings', 0))
        age = int(request.form.get('age', 30))
        province = request.form.get('province')
        year = request.form.get('year')
        if df.empty:
            return render_template('test_hipoteca.html', result="No hay datos cargados.")
        filtered = df[(df['Provincia'] == province) & (df['Trimestre'].str.startswith(str(year)))]
        if filtered.empty:
            result = f"No tenemos suficientes datos para {province} en {year}."
        else:
            avg_price_m2 = filtered['Precio_m2'].mean()
            avg_euribor = filtered['Euribor'].mean()
            estimated_price = avg_price_m2 * 80
            required_savings = estimated_price * 0.30
            loan_amount = estimated_price * 0.80
            monthly_installment = (loan_amount * (avg_euribor + 1.0) / 100 / 12) + (loan_amount / (30 * 12))
            if savings < required_savings:
                result = f"Muy complicado. Para 80 m2 en {province} ({year}), precio est. {estimated_price:,.0f} EUR, necesitas {required_savings:,.0f} EUR en ahorros."
            elif monthly_installment > income * 0.35:
                result = f"Complicado. Cuota estimada {monthly_installment:,.0f} EUR supera tu limite recomendado ({income * 0.35:,.0f} EUR)."
            else:
                result = f"Posible. Cuota estimada: {monthly_installment:,.0f} EUR/mes (Euribor {avg_euribor:.2f}%)."
    provinces = sorted(df['Provincia'].dropna().unique().tolist()) if not df.empty else []
    years = sorted(df['Trimestre'].str[:4].dropna().unique().tolist()) if not df.empty else []
    return render_template('test_hipoteca.html', result=result, provinces=provinces, years=years)


@app.route('/vecm')
def vecm():
    return render_template('vecm.html')


@app.route('/webscrapping')
def webscrapping():
    return render_template('webscrapping.html')


@app.route('/business_case')
def business_case():
    return render_template('business_case.html')


@app.route('/api/dashboard-extra')
def dashboard_extra():
    """Datos para los nuevos gráficos del dashboard: precio m2 provincial, PIB, paro, scatter."""
    if df.empty:
        return jsonify({"error": "No data"})
    province = request.args.get('provincia', '')
    year = request.args.get('year', '')

    base = df.copy()
    if year:
        base = base[base['Trimestre'].str[:4] == str(year)]

    # Helper: serie temporal por provincia o media nacional
    def ts_by_prov(col, prov=''):
        if prov:
            sub = df[df['Provincia'] == prov]
        else:
            sub = df
        g = sub.groupby('Trimestre')[col].mean().dropna().sort_index()
        return g.index.tolist(), [round(float(v), 2) for v in g.values]

    result = {}

    # 1. Precio m2 — series para top-5 provincias o la seleccionada
    if not province:
        top5 = (df.groupby('Provincia')['Precio_m2'].mean()
                  .nlargest(5).index.tolist())
        series = []
        for p in top5:
            lbl, vals = ts_by_prov('Precio_m2', p)
            series.append({'provincia': p, 'labels': lbl, 'values': vals})
        result['precio_prov_series'] = series
    else:
        lbl, vals = ts_by_prov('Precio_m2', province)
        result['precio_prov_series'] = [{'provincia': province, 'labels': lbl, 'values': vals}]

    # 2. PIB_pc — serie por provincia o media nacional
    pib_lbl, pib_vals = ts_by_prov('PIB_pc', province)
    result['pib_series'] = {'labels': pib_lbl, 'values': pib_vals,
                            'scope': province if province else 'Nacional'}

    # 3. Tasa de paro — serie
    paro_lbl, paro_vals = ts_by_prov('Tasa_Paro', province)
    result['paro_series'] = {'labels': paro_lbl, 'values': paro_vals,
                             'scope': province if province else 'Nacional'}

    # 4. Scatter: Precio_m2 vs PIB_pc último año disponible (o filtrado)
    last_yr = df['Trimestre'].str[:4].max() if not year else year
    scatter_df = df[df['Trimestre'].str[:4] == last_yr]
    scatter_agg = scatter_df.groupby('Provincia')[['Precio_m2', 'PIB_pc', 'Tasa_Paro']].mean().dropna()
    # If all PIB_pc are NaN for the selected year (e.g. 2025, INE pending), fall back to prior year
    if scatter_agg.empty or scatter_agg['PIB_pc'].isna().all():
        last_yr = str(int(last_yr) - 1)
        scatter_df = df[df['Trimestre'].str[:4] == last_yr]
        scatter_agg = scatter_df.groupby('Provincia')[['Precio_m2', 'PIB_pc', 'Tasa_Paro']].mean().dropna()
    result['scatter'] = {
        'labels':   scatter_agg.index.tolist(),
        'precio_m2': [round(float(v), 2) for v in scatter_agg['Precio_m2']],
        'pib_pc':   [round(float(v), 2) for v in scatter_agg['PIB_pc']],
        'tasa_paro': [round(float(v), 2) for v in scatter_agg['Tasa_Paro']],
        'year':     last_yr,
    }

    # Province list for selects
    result['provinces'] = sorted(df['Provincia'].dropna().unique().tolist())
    result['years'] = sorted(df['Trimestre'].str[:4].dropna().unique().tolist())

    return jsonify(result)


@app.route('/api/paro-model-info')
def paro_model_info():
    """Retorna info del modelo de Tasa_Paro por provincia."""
    province = request.args.get('provincia', '')
    if province:
        return jsonify(_get_paro_model_info(province))
    # Sin provincia: devuelve el mapa completo para todas
    all_provs = sorted(df['Provincia'].dropna().unique().tolist()) if not df.empty else []
    result = {}
    for p in all_provs:
        result[p] = _get_paro_model_info(p)
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=False, port=8000, threaded=False)
