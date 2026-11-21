"""Verifica cifras básicas del dataset maestro y del CSV de proyecciones. Uso: python verify_counts.py <repo_root>"""
import sys, pathlib, math
import pandas as pd
r = pathlib.Path(sys.argv[1])
d = pd.read_csv(r / 'notebooks acabados' / 'dataset_final_tfm.csv')
print('filas', len(d), 'cols', d.shape[1], 'provincias', d.Provincia.nunique(), 'trimestres', d.Trimestre.nunique(),
      d.Trimestre.min(), '->', d.Trimestre.max(), '| 52*84 =', 52 * 84, '| duplicados clave', d.duplicated(['Provincia', 'Trimestre']).sum())
print('NaN por columna:', {c: int(v) for c, v in d.isna().sum().items() if v})
for c in ['Euribor', 'Spread_Hipotecas', 'tasa_ahorro', 'Indice_Materiales', 'Indice_Mano_Obra', 'IPC']:
    print(f'  valores únicos por trimestre {c}: max', d.groupby('Trimestre')[c].nunique().max())
d['Y'] = d.Trimestre.str[:4]
for c in ['PIB_pc', 'Poblacion', 'Edad_Media', 'Pob_Ext']:
    print(f'  valores únicos por provincia-año {c}: max', d.groupby(['Provincia', 'Y'])[c].nunique().max())
p = pd.read_csv(r / 'notebooks acabados' / 'predicciones_provinciales_2026_2030.csv')
c = p.groupby('variable').size()
print('predicciones filas', len(p), dict(c), '| 6*52*24 + 2*52*20 =', 6 * 52 * 24 + 2 * 52 * 20, '| 8*52*20 =', 8 * 52 * 20)
print('semivida alfa=-0.44:', round(math.log(0.5) / math.log(1 - 0.44), 2), 'trim; alfa=-0.006:', round(math.log(0.5) / math.log(1 - 0.006) / 4, 1), 'años')
