"""Sondea tablas INE: nº series, primeras series, última fecha (nult=1). Uso: python probe_ine_tables.py id1 id2 ..."""
import sys
from common import *
for t in sys.argv[1:]:
    try:
        df = ine_table(t, nult=1)
    except Exception as e:
        print('==', t, 'ERR', e); continue
    print(f'== {t}: {df.cod.nunique()} series; última fecha {df.fecha.max()}')
    for n in df.drop_duplicates('cod').nombre.head(int(__import__("os").environ.get("NSHOW", 3))):
        print('    ', n)
