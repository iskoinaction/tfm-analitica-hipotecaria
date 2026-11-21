"""Reproduce las celdas 49 (proyecciones 2026-2030) y 50 (extensión 2025) del notebook 5
en un directorio de trabajo aislado y compara con notebooks acabados/predicciones_provinciales_2026_2030.csv.
Uso: python repro_nb5_forecasts.py <repo_root> <workdir>"""
import sys, os, json, shutil, pathlib, io, contextlib, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
root = pathlib.Path(sys.argv[1]).resolve(); work = pathlib.Path(sys.argv[2]).resolve(); work.mkdir(parents=True, exist_ok=True)
shutil.copy(root / 'notebooks acabados' / 'dataset_final_tfm.csv', work / 'dataset_final_tfm.csv')
nb = json.load(open(root / 'notebooks acabados' / '5. HIPOTECA_PERSONALIZADA_provincial.ipynb', encoding='utf-8'))
cells = nb['cells']
os.chdir(work)
log = io.StringIO()
for idx in (49, 50):
    src = ''.join(cells[idx]['source'])
    with contextlib.redirect_stdout(log):
        exec(compile(src, f'nb5_cell{idx}', 'exec'), {})
print(log.getvalue()[-1500:])
new = pd.read_csv(work / 'predicciones_provinciales_2026_2030.csv')
ref = pd.read_csv(root / 'notebooks acabados' / 'predicciones_provinciales_2026_2030.csv')
k = ['variable', 'provincia', 'trimestre']
m = ref.merge(new, on=k, how='outer', suffixes=('_ref', '_new'), indicator=True)
print('shape ref', ref.shape, 'new', new.shape, m['_merge'].value_counts().to_dict())
m['absdiff'] = (m.valor_ref - m.valor_new).abs(); m['reldiff'] = m.absdiff / m.valor_ref.abs()
s = m.groupby('variable').agg(n=('absdiff', 'size'), n_diff=('absdiff', lambda x: int((x > 1e-6).sum())),
                              max_abs=('absdiff', 'max'), mean_rel_pct=('reldiff', lambda x: 100 * x.mean()),
                              max_rel_pct=('reldiff', lambda x: 100 * x.max()))
print(s.to_string())
s.to_csv(work / 'nb5_forecast_diff.csv')
