import os
import warnings

import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.vector_ar.vecm import coint_johansen

warnings.filterwarnings('ignore')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, '..'))
OUT_DIR = os.path.join(BASE_DIR, 'static', 'img', 'econometria')
os.makedirs(OUT_DIR, exist_ok=True)

BLUE = '#003366'
SKY = '#007BC0'
GOLD = '#F0C040'
LIGHT = '#66C4E8'
GRAY = '#667085'
GRID = '#D7DEE8'
PALETTE = [BLUE, SKY, GOLD, LIGHT, '#9AA6B2']

plt.rcParams.update({
    'axes.facecolor': 'white',
    'axes.edgecolor': GRID,
    'axes.labelcolor': BLUE,
    'axes.titlecolor': BLUE,
    'figure.facecolor': 'white',
    'font.family': 'DejaVu Sans',
    'savefig.facecolor': 'white',
})


def savefig(name):
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, name), dpi=180, bbox_inches='tight')
    plt.close()


def prepare_data():
    df = pd.read_csv(os.path.join(ROOT_DIR, 'dataset_final_tfm.csv'))
    df['Trimestre'] = pd.to_datetime(df['Trimestre'])
    fill_cols = [
        'tasa_ahorro', 'Indice_Mano_Obra', 'Indice_Materiales', 'IPC',
        'PIB_pc', 'Transmisiones_Total', 'Pob_Ext'
    ]
    for col in fill_cols:
        if col in df.columns:
            df[col] = df.groupby('Provincia')[col].transform(lambda x: x.ffill().bfill())

    df = df.dropna().reset_index(drop=True)
    nacional = df.groupby('Trimestre').agg({
        'Hipotecas_Total': 'sum',
        'Transmisiones_Total': 'sum',
        'Poblacion': 'sum',
        'Euribor': 'mean',
        'Precio_m2': 'mean',
        'Tasa_Paro': 'mean',
        'PIB_pc': 'mean',
        'IPC': 'mean',
        'tasa_ahorro': 'mean',
        'Spread_Hipotecas': 'mean',
        'Edad_Media': 'mean',
        'Indice_Mano_Obra': 'mean',
        'Indice_Materiales': 'mean',
    }).sort_index()
    return nacional


def build_var_frame(nacional):
    df_var = pd.DataFrame(index=nacional.index)
    df_var['Crec_PIB'] = np.log(nacional['PIB_pc']).diff()
    df_var['Tasa_Paro'] = nacional['Tasa_Paro']
    df_var['Log_Precio_m2'] = np.log(nacional['Precio_m2'])
    df_var['Shock_Euribor'] = nacional['Euribor'].diff()
    df_var['Crec_Hipotecas'] = np.log(nacional['Hipotecas_Total']).diff()
    return df_var.dropna()


nacional = prepare_data()
df_var = build_var_frame(nacional)
res_var = VAR(df_var).fit(4)

# 1. Estacionariedad: nivel frente a diferencia logaritmica
log_hipotecas = np.log(nacional['Hipotecas_Total'])
crec_hipotecas = log_hipotecas.diff().dropna()
p_nivel = adfuller(log_hipotecas.dropna(), autolag='AIC')[1]
p_diff = adfuller(crec_hipotecas, autolag='AIC')[1]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), sharex=False)
ax1.plot(log_hipotecas.index, log_hipotecas, color=BLUE, linewidth=2.4)
ax1.set_title(f"Log hipotecas en nivel | ADF p={p_nivel:.3f}", fontsize=11, fontweight='bold')
ax1.set_ylabel("log(total hipotecas)")
ax1.grid(True, color=GRID, linewidth=0.8, alpha=0.8)

ax2.axhline(0, color=GRAY, linewidth=1)
ax2.plot(crec_hipotecas.index, crec_hipotecas, color=GOLD, linewidth=2.2)
ax2.set_title(f"Crecimiento logaritmico | ADF p={p_diff:.3f}", fontsize=11, fontweight='bold')
ax2.set_ylabel("Delta log hipotecas")
ax2.grid(True, color=GRID, linewidth=0.8, alpha=0.8)

fig.suptitle("Transformacion de estacionariedad aplicada al mercado hipotecario", fontsize=13, fontweight='bold', color=BLUE)
savefig('estacionariedad.png')

# 2. Johansen: estadistico de traza contra valor critico al 95 %
johansen_df = pd.DataFrame(index=nacional.index)
johansen_df['Log_Hipotecas'] = np.log(nacional['Hipotecas_Total'])
johansen_df['Log_PIB_pc'] = np.log(nacional['PIB_pc'])
johansen_df['Euribor'] = nacional['Euribor']
johansen_df['Log_Materiales'] = np.log(nacional['Indice_Materiales'])
johansen_df = johansen_df.dropna()
res_johansen = coint_johansen(johansen_df, det_order=0, k_ar_diff=1)
ranks = [f"r <= {i}" for i in range(len(res_johansen.lr1))]
x = np.arange(len(ranks))

fig, ax = plt.subplots(figsize=(8.8, 4.4))
bars = ax.bar(x - 0.18, res_johansen.lr1, width=0.36, color=SKY, label='Estadistico traza')
ax.bar(x + 0.18, res_johansen.cvt[:, 1], width=0.36, color=GOLD, label='Critico 95%')
for bar in bars:
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.8, f"{bar.get_height():.1f}",
            ha='center', va='bottom', color=BLUE, fontsize=9, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(ranks)
ax.set_ylabel("Valor del contraste")
ax.set_title("Test de Johansen: rango de cointegracion del sistema", fontsize=12, fontweight='bold')
ax.legend(frameon=False)
ax.grid(True, axis='y', color=GRID, linewidth=0.8, alpha=0.8)
savefig('cointegracion.png')

# 3. FEVD solo para Crec_Hipotecas
fevd = res_var.fevd(12)
target_idx = df_var.columns.get_loc('Crec_Hipotecas')
shares = fevd.decomp[target_idx] * 100
horizons = np.arange(1, shares.shape[0] + 1)

fig, ax = plt.subplots(figsize=(9.5, 4.8))
ax.stackplot(horizons, shares.T, labels=df_var.columns, colors=PALETTE, alpha=0.94)
ax.set_xlim(horizons.min(), horizons.max())
ax.set_ylim(0, 100)
ax.set_xlabel("Horizonte de prediccion (trimestres)")
ax.set_ylabel("% de varianza explicada")
ax.set_title("FEVD de Crec_Hipotecas: fuentes del error de prediccion", fontsize=12, fontweight='bold')
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.14), ncol=3, frameon=False, fontsize=9)
ax.grid(True, axis='y', color=GRID, linewidth=0.8, alpha=0.8)
savefig('fevd_crec_hipotecas.png')

# 4. IRF: respuesta de Crec_Hipotecas ante shocks estructurales
irf = res_var.irf(12)
idx_hip = df_var.columns.get_loc('Crec_Hipotecas')
std_shocks = res_var.resid.std()

fig, ax = plt.subplots(figsize=(9.5, 4.8))
for i, col in enumerate(df_var.columns):
    idx_imp = df_var.columns.get_loc(col)
    response = irf.orth_irfs[:, idx_hip, idx_imp] / std_shocks[col]
    ax.plot(np.arange(len(response)), response, color=PALETTE[i], linewidth=2.2, marker='o', markersize=4, label=col)
ax.axhline(0, color=GRAY, linewidth=1)
ax.set_xlabel("Trimestres tras el shock")
ax.set_ylabel("Impacto sobre Crec_Hipotecas")
ax.set_title("Funciones impulso-respuesta del VAR sobre la demanda hipotecaria", fontsize=12, fontweight='bold')
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.16), ncol=3, frameon=False, fontsize=9)
ax.grid(True, color=GRID, linewidth=0.8, alpha=0.8)
savefig('irf.png')

print("Charts generated successfully.")
