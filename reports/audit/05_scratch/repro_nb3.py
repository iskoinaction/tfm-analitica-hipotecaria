"""Reproducción aislada del notebook 3 (data joining).

Uso:
  python repro_nb3.py <repo_root> <workdir> [--with-transm]

- Copia `Datos ya metidos/` a <workdir>/inputs (no toca el repo).
- Ejecuta las celdas de código del notebook 3 tal cual (exec), con cwd = <workdir>/inputs.
- Con --with-transm reconstruye antes `transmision_prov_trim_tot.csv` (que NO está en el repo)
  a partir de `transmision_propiedades_prov.csv` (repo, INE ETDP 'Viviendas: Total')
  + `Datos sucios/transmisiones propiedades 2005-2006.xls` usando la lógica de las celdas 59/61 del notebook 1.
- Compara el resultado con `notebooks acabados/dataset_final_tfm.csv` columna a columna.
"""
import sys, os, json, shutil, pathlib, io, contextlib
import numpy as np, pandas as pd

root = pathlib.Path(sys.argv[1]).resolve(); work = pathlib.Path(sys.argv[2]).resolve()
with_transm = '--with-transm' in sys.argv
KEEP_UNIPROV = '--keep-uniprov' in sys.argv
inp = work / 'inputs'
if inp.exists(): shutil.rmtree(inp)
shutil.copytree(root / 'Datos ya metidos', inp)

def build_transm():
    t = pd.read_csv(inp / 'transmision_propiedades_prov.csv', sep=';', encoding='latin1', dtype=str)
    t = t[t['Provincias'].notna()].copy()
    t['provincia'] = t['Provincias'].str.replace(r'^\d+\s+', '', regex=True).str.strip()
    t['año'] = t['Periodo'].str[:4].astype(int); t['trimestre'] = (t['Periodo'].str[5:].astype(int) - 1)//3 + 1
    t['transmisiones'] = t['Total'].str.replace('.', '', regex=False).astype(float)
    t = t[t['año'] <= 2025]
    t = t.groupby(['año', 'trimestre', 'provincia'], as_index=False)['transmisiones'].sum()
    x = pd.read_excel(root / 'Datos sucios' / 'transmisiones propiedades 2005-2006.xls', header=None)
    d = x.iloc[14:, 1:10].copy()
    d.columns = ['provincia', '2005T1', '2005T2', '2005T3', '2005T4', '2006T1', '2006T2', '2006T3', '2006T4']
    d = d.dropna(subset=['provincia']); d['provincia'] = d['provincia'].astype(str).str.strip()
    excl = ['TOTAL NACIONAL','Andalucía','Aragón','Asturias (Principado de)','Balears (Illes)','Canarias','Cantabria',
            'Castilla y León','Castilla-La Mancha','Cataluña','Comunitat Valenciana','Extremadura','Galicia',
            'Madrid (Comunidad de)','Murcia (Región de)','Navarra (Comunidad Foral de)','País Vasco','Rioja (La)','Ceuta y Melilla']
    if KEEP_UNIPROV:
        # Hipótesis verificada: el CSV de referencia SÍ contiene 2005-2006 para las 7 CCAA uniprovinciales,
        # que el código del notebook 1 (celda 59) excluye. Se conservan esas filas de CCAA como provincia.
        uni = {'Asturias (Principado de)': 'Asturias', 'Balears (Illes)': 'Balears, Illes', 'Cantabria': 'Cantabria',
               'Madrid (Comunidad de)': 'Madrid', 'Murcia (Región de)': 'Murcia',
               'Navarra (Comunidad Foral de)': 'Navarra', 'Rioja (La)': 'Rioja, La'}
        excl = [e for e in excl if e not in uni]
        d['provincia'] = d['provincia'].replace(uni)
    d = d[~d['provincia'].isin(excl)].dropna()
    l = d.melt(id_vars='provincia', var_name='p', value_name='transmisiones')
    l['año'] = l['p'].str[:4].astype(int); l['trimestre'] = l['p'].str[5].astype(int)
    l['provincia'] = l['provincia'].replace({'Araba/Alava': 'Araba/Álava', 'Coruña (A)': 'Coruña, A', 'Palmas (Las)': 'Palmas, Las'})
    out = pd.concat([l[['año', 'trimestre', 'provincia', 'transmisiones']], t], ignore_index=True)
    out.to_csv(inp / 'transmision_prov_trim_tot.csv', sep=';', index=False, encoding='utf-8')
    return out

if with_transm: build_transm()

nb = json.load(open(root / 'notebooks acabados' / '3. data_joining.ipynb', encoding='utf-8'))
code = [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']
os.chdir(inp)
ns = {}
log = io.StringIO()
with contextlib.redirect_stdout(log):
    for src in code:
        exec(compile(src, 'nb3', 'exec'), ns)
print(log.getvalue())
new = pd.read_csv(inp / 'dataset_final_tfm.csv')
ref = pd.read_csv(root / 'notebooks acabados' / 'dataset_final_tfm.csv')
print('shape nuevo', new.shape, 'ref', ref.shape)
print('columnas sólo en ref:', [c for c in ref.columns if c not in new.columns], ' sólo en nuevo:', [c for c in new.columns if c not in ref.columns])
key = ['Provincia', 'Trimestre']
m = ref.merge(new, on=key, how='outer', suffixes=('_ref', '_new'), indicator=True)
print('filas emparejadas:', m['_merge'].value_counts().to_dict())
rows = []
for c in ref.columns:
    if c in key or c not in new.columns: continue
    a, b = m[c + '_ref'], m[c + '_new']
    both_nan = a.isna() & b.isna()
    eq = both_nan | np.isclose(a, b, rtol=1e-9, atol=1e-9, equal_nan=False)
    diff = (~eq)
    rel = ((b - a).abs() / a.abs().replace(0, np.nan))[diff]
    rows.append(dict(columna=c, n_diff=int(diff.sum()), nan_ref=int(a.isna().sum()), nan_new=int(b.isna().sum()),
                     max_abs_diff=float((b - a).abs()[diff].max()) if diff.any() else 0.0,
                     max_rel_diff=float(rel.max()) if diff.any() else 0.0))
res = pd.DataFrame(rows)
print(res.to_string(index=False))
res.to_csv(work / ('nb3_diff' + ('_with_transm' if with_transm else '') + '.csv'), index=False)
if 'Transmisiones_Total' in new.columns:
    mm = m[['Provincia', 'Trimestre', 'Transmisiones_Total_ref', 'Transmisiones_Total_new']].copy()
    mm['ratio'] = mm['Transmisiones_Total_ref'] / mm['Transmisiones_Total_new']
    mm['year'] = mm['Trimestre'].str[:4].astype(int)
    print('ratio ref/nuevo por año (mediana):'); print(mm.groupby('year')['ratio'].median().round(3).to_string())
    mm.to_csv(work / 'transm_ref_vs_rebuilt.csv', index=False)
