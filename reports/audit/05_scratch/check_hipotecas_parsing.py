"""Cuantifica el error de parseo de Hipotecas_Total (notebook 3, limpiar_numero) y lo contrasta con la API del INE.
Uso: python check_hipotecas_parsing.py <repo_root> [--api]
- El CSV `Datos ya metidos/hipotecas_por_prov_men.csv` guarda los miles como float truncado ("17.49" = 17.490).
- `limpiar_numero` sólo trata como miles los patrones \\.ddd$ -> "17.49" se lee 17,49.
- --api descarga la serie INE (tabla 3200, series 'Total fincas. Número de hipotecas.<prov>') de Madrid, Barcelona y Alicante."""
import sys, re, pathlib
import pandas as pd
root = pathlib.Path(sys.argv[1])
h = pd.read_csv(root / 'Datos ya metidos' / 'hipotecas_por_prov_men.csv', sep=';', dtype=str)
def nb3(v):
    s = str(v).strip()
    if ',' in s: s = s.replace('.', '').replace(',', '.')
    elif re.search(r'\.[0-9]{3}$', s): s = s.replace('.', '')
    return float(s)
def fixed(v):
    a, b = v.split('.')
    return float(a) if b == '0' else float(int(a) * 1000 + int(b.ljust(3, '0')))  # 'X.0' ambiguo: se asume X
h['nb3'] = h.Total.map(nb3); h['fix'] = h.Total.map(fixed); h['wrong'] = h.nb3 != h.fix
h['Q'] = h.Periodo.str[:4] + 'Q' + ((h.Periodo.str[5:].astype(int) - 1) // 3 + 1).astype(str)
q = h.groupby(['Provincias', 'Q']).agg(nb3=('nb3', 'sum'), fix=('fix', 'sum'), w=('wrong', 'any'))
print('filas mensuales mal parseadas:', int(h.wrong.sum()), 'de', len(h))
print('provincia-trimestre afectados:', int(q.w.sum()), 'de', len(q), '| provincias:', q[q.w].index.get_level_values(0).nunique())
print('sesgo en afectados (%):', ((q[q.w].nb3 / q[q.w].fix - 1) * 100).describe().round(1).to_dict())
t = q.groupby(level=1)[['nb3', 'fix']].sum(); t['err'] = (t.nb3 / t.fix - 1) * 100
print('error nacional trimestral: min %.1f%%, media %.1f%%' % (t.err.min(), t.err.mean()))
if '--api' in sys.argv:
    import requests
    meta = requests.get('https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/3200?nult=1', timeout=120).json()
    cod = {s['Nombre'].split('.')[2].strip(): s['COD'] for s in meta if s['Nombre'].startswith('Total fincas. Número de hipotecas.')}
    for p in ['Madrid', 'Barcelona', 'Alicante/Alacant']:
        r = requests.get(f"https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/{cod[p]}?nult=300", timeout=60).json()
        api = pd.Series({f"{x['Anyo']}M{x['FK_Periodo']:02d}": x['Valor'] for x in r['Data']})
        hh = h[h.Provincias == p].set_index('Periodo')
        j = pd.DataFrame({'nb3': hh.nb3, 'fix': hh.fix, 'api': api}).dropna()
        print(p, cod[p], 'n', len(j), '| nb3 != api:', int((j.nb3 != j.api).sum()), '| fix != api:', int((j.fix != j.api).sum()),
              '(de ellos en 2025, revisiones):', int(((j.fix != j.api) & j.index.str.startswith('2025')).sum()))
