"""Auditoría 04 (Banca) - Script 01.
Descarga series oficiales del BCE (MIR y FM) y las compara con Web/static/tipos_hipotecas.csv.

Series (ECB Data Portal, https://data-api.ecb.europa.eu):
  APRC  MIR.M.ES.B.A2C.A.C.A.2250.EUR.N  TAE (APRC) nuevas operaciones préstamo vivienda, España
  AAR   MIR.M.ES.B.A2C.A.R.A.2250.EUR.N  Tipo anual acordado (TEDR/NDER) total vivienda, España
  AARF  MIR.M.ES.B.A2C.F.R.A.2250.EUR.N  Tipo acordado, tipo flotante y fijación inicial <=1 año (≈ variable)
  EUR12 FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA  Euríbor 12 meses, media mensual
Salida: reports/audit/04_banca/out/ecb_rates_*.csv y ecb_rates_summary.json
"""
import io, json, os, sys
import pandas as pd, requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
OUT = os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT, exist_ok=True)
SERIES = {
    'APRC': ('MIR', 'M.ES.B.A2C.A.C.A.2250.EUR.N'),
    'AAR': ('MIR', 'M.ES.B.A2C.A.R.A.2250.EUR.N'),
    'AAR_float_1y': ('MIR', 'M.ES.B.A2C.F.R.A.2250.EUR.N'),
    'EURIBOR12M': ('FM', 'M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA'),
}

def fetch(flow, key):
    url = f'https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata&startPeriod=2003-01&detail=dataonly'
    r = requests.get(url, timeout=120); r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text))
    return d.set_index('TIME_PERIOD')['OBS_VALUE'].rename(None), url

frames, urls = {}, {}
for name, (flow, key) in SERIES.items():
    s, url = fetch(flow, key); frames[name] = s; urls[name] = url
m = pd.DataFrame(frames); m.index = pd.PeriodIndex(m.index, freq='M')
m = m.sort_index(); m.to_csv(os.path.join(OUT, 'ecb_rates_monthly.csv'))
q = m.groupby(m.index.asfreq('Q')).mean()
q['APRC_minus_EUR12'] = q['APRC'] - q['EURIBOR12M']
q['AARfloat_minus_EUR12'] = q['AAR_float_1y'] - q['EURIBOR12M']
q['APRC_minus_AAR'] = q['APRC'] - q['AAR']
q.to_csv(os.path.join(OUT, 'ecb_rates_quarterly.csv'))

# Comparación con el CSV de la app
t = pd.read_csv(os.path.join(ROOT, 'Web', 'static', 'tipos_hipotecas.csv'))
t['Q'] = pd.PeriodIndex(pd.to_datetime(t['TIME_PERIOD']), freq='Q')
t = t.set_index('Q')
cmp = t.join(q, how='left')
cmp['dAPRC'] = cmp['APRC_VALUE'] - cmp['APRC']
cmp['dEUR'] = cmp['EURIBOR_VALUE'] - cmp['EURIBOR12M']
cmp.to_csv(os.path.join(OUT, 'tipos_csv_vs_ecb.csv'))
ann = q.groupby(q.index.year).mean()
summary = {
    'urls': urls,
    'ecb_last_month': {k: [str(m[k].dropna().index[-1]), float(m[k].dropna().iloc[-1])] for k in m},
    'csv_rows': int(len(t)), 'csv_first': str(t.index.min()), 'csv_last': str(t.index.max()),
    'max_abs_diff_APRC_csv_vs_ecb': float(cmp['dAPRC'].abs().max()),
    'max_abs_diff_EUR12_csv_vs_ecb': float(cmp['dEUR'].abs().max()),
    'annual_selected': ann.loc[[2013, 2017, 2021, 2022, 2023, 2024, 2025] + ([2026] if 2026 in ann.index else []),
                               ['APRC', 'AAR', 'AAR_float_1y', 'EURIBOR12M', 'APRC_minus_EUR12', 'AARfloat_minus_EUR12', 'APRC_minus_AAR']].round(3).to_dict(orient='index'),
    'quarters_with_negative_APRC_minus_EUR12': [str(i) for i in q.index[q['APRC_minus_EUR12'] < 0]],
    'last_quarters': q.tail(6).round(3).reset_index().astype(str).to_dict(orient='records'),
}
json.dump(summary, open(os.path.join(OUT, 'ecb_rates_summary.json'), 'w'), indent=2, ensure_ascii=False, default=str)
print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
