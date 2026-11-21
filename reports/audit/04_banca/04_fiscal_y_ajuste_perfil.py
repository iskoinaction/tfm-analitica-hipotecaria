"""Auditoría 04 (Banca) - Script 04.
a) Ajuste por perfil tanh de app.py (_calc_income_adjustment): tabla de valores y discontinuidad en ratio 0,5.
b) Aranceles de la app (tabla de financialtools) vs arancel base RD 1426/1989 y RD 1427/1989.
c) ITP de la app vs tabla secundaria (bm.consulting, 29/10/2026, cita normativa) -> discrepancias a verificar.
Salida: out/fiscal_ajuste.json
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from asesor_v2_reference import arancel_notarial_base, arancel_registral_base

OUT = os.path.join(os.path.dirname(__file__), 'out')
# Copia literal de app.py (líneas 1261-1277) para no importar la app
def calc_income_adjustment(income, pib_pc):
    if pib_pc <= 0: return 0.0
    ratio = (income * 12) / pib_pc
    adj = -0.25 * np.tanh((ratio - 1.0) * 2.0)
    if ratio < 0.5: adj += 0.05
    return round(float(adj), 4)

pib = 30000.0
tabla = {f'{r:.2f}': calc_income_adjustment(r * pib / 12, pib) for r in [0, 0.25, 0.4999, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]}
salto = calc_income_adjustment(0.4999 * pib / 12, pib) - calc_income_adjustment(0.5 * pib / 12, pib)
# Mismo ingreso (2.500 €/mes) en dos provincias con PIB pc distinto (valores 2024 del dataset Madrid / Jaén aprox. via harness)
mismo_ingreso = {'pib_44749': calc_income_adjustment(2500, 44749.0), 'pib_20000': calc_income_adjustment(2500, 20000.0)}

# Aranceles: tabla app (Web/app.py::_notaria_registro)
brackets = [25000, 50000, 100000, 150000, 200000, 250000, 300000, 400000]
notaria_app = [600, 625, 675, 710, 750, 790, 830, 850]; registro_app = [395, 420, 445, 470, 510, 550, 590, 630]
def app_nr(p):
    idx = len(brackets) - 1
    for i, b in enumerate(brackets):
        if p <= b: idx = i; break
    return notaria_app[idx], registro_app[idx]
aranceles = {}
for p in [100000, 200000, 250000, 400000, 1000000]:
    n, r = app_nr(p)
    aranceles[p] = {'app_notaria': n, 'app_registro': r, 'arancel_base_notaria_RD1426': round(arancel_notarial_base(p), 2),
                    'arancel_base_registro_RD1427': round(arancel_registral_base(p), 2)}

# ITP general vivienda usada: app vs fuente secundaria (bm.consulting 29/10/2026). 'tramos' = la app usa tipo único.
APP_ITP = {"Andalucia": 7.0, "Aragon": 8.0, "Asturias": 8.0, "Baleares": 8.0, "Canarias": 6.5, "Cantabria": 10.0,
           "Castilla-La Mancha": 9.0, "Castilla y Leon": 8.0, "Cataluna": 10.0, "Comunidad Valenciana": 10.0,
           "Extremadura": 8.0, "Galicia": 10.0, "Madrid": 6.0, "Murcia": 8.0, "Navarra": 6.0, "Pais Vasco": 4.0, "La Rioja": 7.0}
SEC = {"Andalucia": ("7", "Ley 5/2021 art. 41"), "Aragon": ("8 hasta 400k; tramos hasta 10", "DLeg 1/2005 art. 121-1"),
       "Asturias": ("8 hasta 300k; 9; 10", "DLeg 2/2014 art. 26"), "Baleares": ("8 hasta 400k; tramos hasta 13", "DLeg 1/2014 art. 10"),
       "Canarias": ("6,5", "DLeg 1/2009 art. 31"), "Cantabria": ("9", "DLeg 62/2008 art. 9"), "Castilla-La Mancha": ("9", "Ley 8/2013 art. 19"),
       "Castilla y Leon": ("8; 10 exceso >250k", "DLeg 1/2013 arts. 24-25"), "Cataluna": ("10 hasta 600k; tramos hasta 13", "DLeg 1/2024 art. 641-1"),
       "Comunidad Valenciana": ("9 (desde 1/6/2026); 11 si >1M", "Ley 13/1997 art. 13"), "Extremadura": ("8 hasta 360k; 10; 11", "DLeg 1/2018 art. 36"),
       "Galicia": ("8", "DLeg 1/2011 art. 14"), "Madrid": ("6", "DLeg 1/2010 art. 28"), "Murcia": ("7,75", "DLeg 1/2010 art. 6"),
       "Navarra": ("6", "DFLeg 129/1999 art. 8"), "Pais Vasco": ("4 vivienda (normas forales)", "Normas forales"), "La Rioja": ("7", "Ley 10/2017 art. 44")}
def first_num(s):
    import re; return float(re.match(r'([0-9]+(?:,[0-9]+)?)', s).group(1).replace(',', '.'))
itp_cmp = {k: {'app': APP_ITP[k], 'secundaria': SEC[k][0], 'norma': SEC[k][1],
               'difiere_tipo_base': APP_ITP[k] != first_num(SEC[k][0]), 'app_ignora_tramos': 'tramos' in SEC[k][0] or ';' in SEC[k][0]} for k in APP_ITP}
res = {'tanh_tabla_ratio_ajuste_pp': tabla, 'salto_discontinuidad_ratio_0_5_pp': round(salto, 4), 'mismo_ingreso_distinto_pib': mismo_ingreso,
       'aranceles': aranceles, 'itp_app_vs_secundaria': itp_cmp,
       'n_ccaa_tipo_base_distinto': sum(v['difiere_tipo_base'] for v in itp_cmp.values()),
       'n_ccaa_con_tramos_ignorados': sum(v['app_ignora_tramos'] for v in itp_cmp.values()),
       'fuente_secundaria': 'https://bm.consulting/es/insights/tipos-itp-comunidad-autonoma-2026/ (consultada 21/11/2026; NO es boletín oficial)'}
json.dump(res, open(os.path.join(OUT, 'fiscal_ajuste.json'), 'w'), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False))
