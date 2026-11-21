"""Vuelca las celdas de código de todos los notebooks a ficheros .py numerados por celda (solo lectura)."""
import json, sys, pathlib
root = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
for nb in sorted(list(root.rglob('*.ipynb'))):
    if '.git' in nb.parts: continue
    d = json.load(open(nb, encoding='utf-8'))
    lines = []
    for i, c in enumerate(d['cells']):
        src = ''.join(c['source'])
        if c['cell_type'] == 'code':
            lines.append(f"# ===== CELL {i} [code] exec_count={c.get('execution_count')} =====\n{src}\n")
        else:
            lines.append(f"# ===== CELL {i} [{c['cell_type']}] =====\n" + '\n'.join('# '+l for l in src.splitlines()) + '\n')
    (out / (nb.stem.replace(' ', '_') + '.py')).write_text('\n'.join(lines), encoding='utf-8')
    print(nb, len(d['cells']), 'cells', d.get('metadata',{}).get('kernelspec',{}).get('name'))
