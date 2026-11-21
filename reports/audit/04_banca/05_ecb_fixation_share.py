"""Auditoría 04 (Banca) - Script 05. Peso del tipo variable (flotante / fijación <=1 año) en las nuevas
operaciones de préstamo para vivienda en España (BCE MIR, volúmenes de nuevo negocio, EUR millones).
Claves: MIR.M.ES.B.A2C.{F,I,O,P}.B.A.2250.EUR.N  (F: flotante y fijación<=1a; I: 1-5a; O: 5-10a; P: >10a)
Salida: out/ecb_fixation_share.csv / .json
"""
import io, json, os
import pandas as pd, requests
OUT = os.path.join(os.path.dirname(__file__), 'out')
vols = {}
for k in ['F', 'I', 'O', 'P']:
    url = f'https://data-api.ecb.europa.eu/service/data/MIR/M.ES.B.A2C.{k}.B.A.2250.EUR.N?format=csvdata&startPeriod=2015-01&detail=dataonly'
    r = requests.get(url, timeout=120); r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text)); vols[k] = d.set_index('TIME_PERIOD')['OBS_VALUE']
v = pd.DataFrame(vols).dropna(); v.index = pd.to_datetime(v.index)
ann = v.groupby(v.index.year).sum()
share = (ann['F'] / ann.sum(axis=1) * 100).round(1)
share.to_csv(os.path.join(OUT, 'ecb_fixation_share.csv'), header=['pct_variable_fijacion_hasta_1a'])
res = {'pct_nuevo_negocio_variable_por_anio': share.to_dict(), 'ultimo_mes': str(v.index.max().date()),
       'nota': '2026 = meses disponibles'}
json.dump(res, open(os.path.join(OUT, 'ecb_fixation_share.json'), 'w'), indent=1)
print(json.dumps(res, indent=1))
