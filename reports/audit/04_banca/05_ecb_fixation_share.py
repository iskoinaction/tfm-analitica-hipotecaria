"""Auditoría 04 (Banca) - Script 05. Sondeo: ¿publica el BCE (MIR) para España el desglose por periodo de fijación
del VOLUMEN de nuevas operaciones de préstamo para vivienda? (para medir el peso del tipo variable en el APRC).
Resultado (21/11/2026): solo existe el volumen total (MIR.M.ES.B.A2C.A.B.A.2250.EUR.{N,P,R}); las claves por fijación
(F, I, O, P) devuelven 404. Por tanto el peso fijo/variable debe tomarse de otra fuente (p. ej. INE, estadística de hipotecas).
Salida: out/ecb_fixation_probe.json
"""
import io, json, os
import pandas as pd, requests
OUT = os.path.join(os.path.dirname(__file__), 'out')
res = {}
url = 'https://data-api.ecb.europa.eu/service/data/MIR/M.ES.B.A2C..B..2250.EUR.?format=csvdata&startPeriod=2025-01&endPeriod=2025-01&detail=dataonly'
r = requests.get(url, timeout=120)
res['wildcard_url'] = url; res['wildcard_status'] = r.status_code
res['series_volumen_disponibles'] = sorted(pd.read_csv(io.StringIO(r.text))['KEY'].unique().tolist()) if r.ok else []
for k in ['F', 'I', 'O', 'P']:
    u = f'https://data-api.ecb.europa.eu/service/data/MIR/M.ES.B.A2C.{k}.B.A.2250.EUR.N?format=csvdata&startPeriod=2015-01&detail=dataonly'
    res[f'status_{k}'] = requests.get(u, timeout=120).status_code
json.dump(res, open(os.path.join(OUT, 'ecb_fixation_probe.json'), 'w'), indent=1)
print(json.dumps(res, indent=1))
