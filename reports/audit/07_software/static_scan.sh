#!/usr/bin/env bash
# Análisis estático (sólo lectura) de Web/: marca, sumideros XSS, URLs externas,
# bandit (SAST) e imports no declarados en requirements.txt.
# Uso: static_scan.sh <REPO_ROOT> <PYTHON_CON_BANDIT>
set -u
R="$1"; PY="${2:-python}"
W="$R/Web"
cd "$W" || exit 1

echo "=== 1. Referencias a la marca CaixaBank / laCaixa (fichero: nº de líneas)"
grep -rliE "caixa" --include=*.html --include=*.js --include=*.css --include=*.py --include=*.md --include=.env.example . \
  | while read -r f; do echo "$f: $(grep -ciE 'caixa' "$f")"; done
echo "logo.png: $(python3 -c "from PIL import Image; im=Image.open('static/logo.png'); print(im.size, im.mode)" 2>/dev/null)"
echo "Hotlinks al CDN de caixabank.es: $(grep -rhoE 'https://www\.caixabank\.es[^\"]+' templates | wc -l)"
echo "Nombre 'Noa' (asistente) en: $(grep -rlE '\bNoa\b' templates app.py | tr '\n' ' ')"

echo; echo "=== 2. Sumideros XSS (innerHTML / |safe) por fichero"
grep -rcE "innerHTML|insertAdjacentHTML|\|safe" templates static/script.js | grep -v ":0$"
echo "-- respuestas del LLM insertadas como HTML:"
grep -nE "innerHTML = .*reply|appendMessage\(d\.reply" templates/*.html static/script.js

echo; echo "=== 3. Dominios externos cargados por las plantillas"
grep -rhoE "(src|href)=\"https?://[^/\"]+" templates | sed -E 's/(src|href)="//' | sort | uniq -c | sort -rn
echo "-- scripts sin versión fijada / sin SRI:"
grep -rnoE "src=\"https://cdn\.jsdelivr\.net/npm/chart\.js[^\"]*\"" templates
grep -rlE "integrity=" templates || echo "(ninguna plantilla usa integrity=)"

echo; echo "=== 4. Imports de terceros vs requirements.txt"
grep -hoE "^\s*(import|from) [a-zA-Z_\.]+" app.py demanda_models.py gen_charts.py | awk '{print $2}' | cut -d. -f1 | sort -u | tr '\n' ' '; echo
echo "requirements.txt: $(tr '\n' ' ' < requirements.txt)"
grep -nE "^\s+import (geopandas|seaborn|statsmodels)|^import google|^from google" app.py

echo; echo "=== 5. bandit (SAST)"
"$PY" -m bandit -q -f txt -r app.py demanda_models.py gen_charts.py 2>/dev/null | grep -E "^>> Issue|Severity|Location" | paste - - - | sed -E 's/\s+/ /g' | sort | uniq -c | sort -rn | head -40
"$PY" -m bandit -q -r app.py demanda_models.py gen_charts.py 2>/dev/null | grep -A6 "Run metrics" | head -12
