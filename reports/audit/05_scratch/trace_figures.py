"""Busca cada cifra del README en: (a) código fuente, (b) outputs guardados de notebooks, (c) plantillas/app.
Uso: python trace_figures.py <repo_root>"""
import json, sys, pathlib, re
root = pathlib.Path(sys.argv[1])
FIGS = {
 '7,11% RF_Nac MAPE': [r'7[.,]11'], '53,3% FEVD precio': [r'53[.,]3'], '38,8% FEVD materiales': [r'38[.,]8'],
 '2,2% FEVD Euribor': [r'\b2[.,]2\d?\s*%'], '44% velocidad ajuste': [r'\b44[.,]?\d*\s*%', r'-0[.,]44'],
 '0,6% ajuste precios': [r'0[.,]6\s*%', r'0[.,]006'], 'semivida 1,2 trim': [r'1[.,]2\s*trim'],
 'beta 0.35 PIB': [r'0[.,]35\b'], 'beta 2.48 precio': [r'2[.,]48'], 'beta 1.09 materiales': [r'1[.,]09'],
 'CAGR 2,24%': [r'2[.,]24\s*%', r'0[.,]0224'], 'MAPE PIB 7,2%': [r'\b7[.,]2\s*%'], 'U Theil 0,749': [r'0[.,]749'],
 'Paro 15,7%': [r'15[.,]7'], 'Paro 12,9%': [r'12[.,]9'], 'Paro 16,9%': [r'16[.,]9'], 'U2 0,944': [r'0[.,]944'],
 'U2 0,545': [r'0[.,]545'], 'U2 0,713': [r'0[.,]713'], 'U2 1,032': [r'1[.,]032'],
 'HW gana 79%': [r'\b79\s*%'], 'HW MAPE 2,9%': [r'\b2[.,]9\s*%'], 'U2 0,634': [r'0[.,]634'], 'phi 0,94': [r'0[.,]94\b'],
 'RF prov ~18%': [r'\b18[.,]?\d*\s*%'], 'ADF p=0,989': [r'0[.,]989'], '8.320 filas': [r'8[.,]?320'],
 'paro min 7,95%': [r'7[.,]95'],
}
def nb_texts(p):
    d = json.load(open(p, encoding='utf-8'))
    for i, c in enumerate(d['cells']):
        src = ''.join(c['source'])
        yield ('code' if c['cell_type'] == 'code' else 'md', i, src)
        for o in c.get('outputs', []):
            t = o.get('text') or o.get('data', {}).get('text/plain') or ''
            t = ''.join(t) if isinstance(t, list) else t
            if t: yield ('output', i, t)
targets = list(root.glob('notebooks acabados/*.ipynb')) + list(root.glob('Web/templates/*.html')) + [root/'Web/app.py', root/'Web/demanda_models.py', root/'Web/README.md']
res = {}
for name, pats in FIGS.items():
    hits = []
    for t in targets:
        it = nb_texts(t) if t.suffix == '.ipynb' else [('file', 0, t.read_text(encoding='utf-8', errors='ignore'))]
        for kind, i, txt in it:
            for p in pats:
                if re.search(p, txt):
                    hits.append(f"{t.name}[{kind}:{i}]"); break
    res[name] = sorted(set(hits))
for k, v in res.items():
    outs = [h for h in v if ':output' in h or '[output' in h]
    print(f"{k:24s} outputs={outs[:6]}  otros={[h for h in v if h not in outs][:6]}")
