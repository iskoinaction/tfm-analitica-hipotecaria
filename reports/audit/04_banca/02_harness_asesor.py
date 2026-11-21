"""Auditoría 04 (Banca) - Script 02. Harness del asesor hipotecario de Web/app.py.
- Importa la app con stubs (sin GEMINI_API_KEY), usa el test client de Flask.
- Verifica la cuota francesa contra un cálculo independiente (bisección sobre el cuadro de amortización).
- Detecta incoherencias entre el tipo mostrado (ml_rate / applied_rate) y el tipo usado para cuota y DTI.
- Comprueba el mapeo provincia -> CCAA para las 52 provincias del dataset.
Salida: out/harness_profiles.csv, out/harness_summary.json
"""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from _app_loader import load_app, client, patch_shap_scalar

OUT = os.path.join(os.path.dirname(__file__), 'out')
m = load_app(); patch_shap_scalar(m); c = client(m)

def cuota_independiente(P, tin_pct, n):
    """Cuota constante obtenida por bisección: el saldo tras n pagos debe ser 0 (sin usar la fórmula cerrada)."""
    r = tin_pct / 100 / 12
    lo, hi = P / n * 0.5, P  # cotas
    for _ in range(200):
        mid = (lo + hi) / 2; bal = P
        for _k in range(n):
            bal = bal * (1 + r) - mid
        if bal > 0: lo = mid
        else: hi = mid
    return (lo + hi) / 2

PROFILES = [
    dict(id='P01_madrid_var', year='2025', tipo='variable', income=2500, savings=60000, age=32, province='Comunidad de Madrid', other_debts=0, price_mode='manual', custom_price=250000, tenure_years=30),
    dict(id='P02_madrid_fijo', year='2025', tipo='fijo', income=2500, savings=60000, age=32, province='Comunidad de Madrid', other_debts=0, price_mode='manual', custom_price=250000, tenure_years=30),
    dict(id='P03_coruna_joven', year='2025', tipo='variable', income=2200, savings=30000, age=30, province='A Coruña', other_debts=0, price_mode='manual', custom_price=180000, tenure_years=30),
    dict(id='P04_valladolid_nb', year='2023', tipo='variable', income=1300, savings=35000, age=30, province='Valladolid', other_debts=0, price_mode='auto', custom_price=0, tenure_years=30),
    dict(id='P05_barcelona_alta', year='2024', tipo='variable', income=8000, savings=150000, age=45, province='Barcelona', other_debts=500, price_mode='manual', custom_price=450000, tenure_years=25),
    dict(id='P06_edad60', year='2025', tipo='fijo', income=3000, savings=80000, age=60, province='Sevilla', other_debts=0, price_mode='manual', custom_price=200000, tenure_years=30),
    dict(id='P07_barato_jaen', year='2025', tipo='variable', income=1500, savings=20000, age=40, province='Jaén', other_debts=0, price_mode='manual', custom_price=90000, tenure_years=30),
    dict(id='P08_futuro_2026', year='2026', tipo='variable', income=2500, savings=60000, age=32, province='Comunidad de Madrid', other_debts=0, price_mode='manual', custom_price=250000, tenure_years=30),
    dict(id='P09_murcia_joven100', year='2025', tipo='variable', income=2000, savings=12000, age=28, province='Región de Murcia', other_debts=0, price_mode='manual', custom_price=150000, tenure_years=30),
    dict(id='P10_sin_ingresos', year='2025', tipo='variable', income=0, savings=60000, age=32, province='Comunidad de Madrid', other_debts=0, price_mode='manual', custom_price=250000, tenure_years=30),
    dict(id='P11_umbral_dti', year='2025', tipo='fijo', income=2050, savings=60000, age=35, province='Comunidad de Madrid', other_debts=0, price_mode='manual', custom_price=250000, tenure_years=30),
    dict(id='P13_flip_dti', year='2025', tipo='variable', income=2800, savings=60000, age=32, province='Comunidad de Madrid', other_debts=0, price_mode='manual', custom_price=250000, tenure_years=30),
    dict(id='P14_coruna_auto', year='2024', tipo='variable', income=2200, savings=40000, age=30, province='A Coruña', other_debts=0, price_mode='auto', custom_price=0, tenure_years=30),
    dict(id='P12_ahorro_extra', year='2025', tipo='variable', income=3000, savings=200000, age=40, province='Comunidad de Madrid', other_debts=0, price_mode='manual', custom_price=250000, tenure_years=30),
]

rows = []
for p in PROFILES:
    body = {k: v for k, v in p.items() if k != 'id'}
    r = c.post('/api/hipoteca-recomendacion', json=body)
    d = r.get_json() or {}
    if r.status_code != 200:
        rows.append({'id': p['id'], 'http': r.status_code}); continue
    n = d['tenure_years'] * 12
    # Tipo realmente usado para la cuota: se reconstruye como en app.py (max(rate,0.5)) -> 'rate' interno.
    # El JSON devuelve rate=0 si no aprobado, así que reconstruimos con differential/aprc
    rate_int = (d['euribor'] + d['differential']) if d['tipo'] == 'variable' else None
    if d['tipo'] == 'fijo':
        rate_int = round(d['aprc'] + 0.50 + (0.75 if d['estimated_price'] < 100000 else 0), 2)
    else:
        rate_int = round(rate_int, 2)
    cuota_ind = cuota_independiente(d['loan_amount'], max(rate_int, 0.5), n) if d['loan_amount'] > 0 else 0
    cuota_app_ind = cuota_independiente(d['loan_amount'], d['applied_rate'], n) if d['loan_amount'] > 0 else 0
    dti_applied = (cuota_app_ind + p['other_debts']) / p['income'] * 100 if p['income'] > 0 else None
    st_applied = None if dti_applied is None else ('approved' if dti_applied < 35 else ('analyst' if dti_applied <= 45 else 'denied'))
    t = d['taxes']; mt = d.get('ml_transparency') or {}
    rows.append({
        'id': p['id'], 'http': r.status_code, 'province': p['province'], 'ccaa': d['ccaa'] or '(vacía)', 'year': d['year'], 'tipo': d['tipo'],
        'income': p['income'], 'age': p['age'], 'status': d['status'],
        'euribor': round(d['euribor'], 3), 'aprc': round(d['aprc'], 3), 'diferencia_base': round(d['diferencia'], 3), 'differential': d['differential'],
        'rate_used_for_cuota': rate_int, 'ml_rate_shown': d['ml_rate'], 'applied_rate': d['applied_rate'], 'applied_type': d['applied_type'],
        'ml_spread_base': mt.get('spread_base'), 'profile_adj': mt.get('profile_adj'), 'income_ratio': mt.get('income_ratio'),
        'r2_train_shown_as_CV_accuracy': d['ml_r2'], 'rmse_cv': mt.get('rmse_cv'), 'n_samples': mt.get('n_samples'),
        'price': d['estimated_price'], 'loan': d['loan_amount'], 'ltv_pct': round(d['loan_amount'] / d['estimated_price'] * 100, 1) if d['estimated_price'] else None,
        'max_fin_pct': d['max_financing_pct'], 'is_young_buyer': d['is_young_buyer'], 'tenure_years': d['tenure_years'],
        'cuota_app': d['monthly_installment'], 'cuota_indep_same_rate': round(cuota_ind, 2), 'abs_err_cuota': round(abs(cuota_ind - d['monthly_installment']), 6),
        'cuota_at_applied_rate': round(cuota_app_ind, 2), 'dti_app': d['dti_ratio'], 'dti_at_applied_rate': None if dti_applied is None else round(dti_applied, 1),
        'status_if_applied_rate': st_applied,
        'itp_rate': t['itp_rate'], 'itp': t['itp'], 'notaria': t['notaria'], 'registro': t['registro'], 'taxes_total': t['total'],
        'effective_savings': d['effective_savings'], 'min_down_payment': d['min_down_payment'],
        'cash_needed_real': round(d['estimated_price'] - d['loan_amount'] + t['total'], 0),
    })

dfp = pd.DataFrame(rows)
dfp.to_csv(os.path.join(OUT, 'harness_profiles.csv'), index=False)

# Mapeo provincia -> CCAA para las 52 provincias del dataset
provs = sorted(m.df['Provincia'].dropna().unique())
mapping = {p: m._get_ccaa(p) for p in provs}
unmapped = [p for p, v in mapping.items() if not v]

# Edad / plazo
plazos = {a: max(5, min(30, 75 - a)) for a in (25, 45, 50, 60, 65, 66, 70)}

# /api/hipoteca-context: métricas mostradas
ctx = c.get('/api/hipoteca-context?year=2024').get_json()
ctx_prov = {q: c.get(q).get_json() for q in ['/api/hipoteca-context?year=2025&provincia=Comunidad%20de%20Madrid','/api/hipoteca-context?year=2026&provincia=Comunidad%20de%20Madrid']}

# /test-hipoteca (legacy): fórmula de cuota
P = 200000 * 0.8; eur = 2.2
cuota_legacy = P * (eur + 1.0) / 100 / 12 + P / (30 * 12)
cuota_fr = cuota_independiente(P, eur + 1.0, 360)

summary = {
    'profiles': dfp.to_dict(orient='records'),
    'max_abs_err_cuota_vs_independiente': float(dfp['abs_err_cuota'].max()),
    'n_provincias_dataset': len(provs), 'n_sin_ccaa': len(unmapped), 'provincias_sin_ccaa': unmapped,
    'mapping': mapping,
    'plazo_max_por_edad': plazos,
    'context_metrics_hardcoded': ctx.get('metrics'),
    'context_prov_2025_2026': {k: {kk: v.get(kk) for kk in ('error','euribor','aprc','diferencia','pib_pc','precio_m2','data_period')} for k, v in ctx_prov.items()},
    'legacy_test_hipoteca': {'loan': P, 'tin': eur + 1.0, 'cuota_legacy_formula': round(cuota_legacy, 2), 'cuota_francesa': round(cuota_fr, 2),
                             'sobreestimacion_pct': round((cuota_legacy / cuota_fr - 1) * 100, 1)},
}
json.dump(summary, open(os.path.join(OUT, 'harness_summary.json'), 'w'), indent=1, ensure_ascii=False, default=str)
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60)
print(dfp.T.to_string())
print(json.dumps({k: v for k, v in summary.items() if k not in ('profiles', 'mapping')}, indent=1, ensure_ascii=False, default=str))
