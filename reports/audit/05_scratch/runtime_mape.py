"""Calcula las métricas que la app Flask calcula en runtime (demanda_models._train_artifacts) sin arrancar Flask.
Fuerza n_jobs=2. Uso: python runtime_mape.py <repo_root>"""
import sys, pathlib, importlib
import pandas as pd
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'Web'))
import sklearn.ensemble as se
_RF = se.RandomForestRegressor
import functools
def RF2(*a, **k):
    k['n_jobs'] = 2
    return _RF(*a, **k)
import demanda_models as dm
dm.RandomForestRegressor = RF2
df = pd.read_csv(root / 'notebooks acabados' / 'dataset_final_tfm.csv')
pp = pd.read_csv(root / 'notebooks acabados' / 'predicciones_provinciales_2026_2030.csv')
art = dm._train_artifacts(df, pp)
q = sorted(art['panel']['Trimestre'].unique())
print('panel rows', len(art['panel']), 'quarters', str(q[0])[:10], '->', str(q[-1])[:10], 'test from', str(q[-8])[:10])
print('nac_df rows', len(art['nac_df']), 'last', str(art['nac_df'].index[-1] if not hasattr(art['nac_df'],'Trimestre') else art['nac_df']['Trimestre'].iloc[-1])[:10])
print('RUNTIME prov_mape', art['prov_mape'], 'prov_r2', art['prov_r2'], '| nac_mape', art['nac_mape'], 'nac_r2', art['nac_r2'])
