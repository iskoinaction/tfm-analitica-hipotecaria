#!/usr/bin/env bash
# Arranca la app v1 (copia en sandbox) en el puerto 8100 con el servidor de desarrollo
# de Werkzeug tal y como la lanza app.py (threaded=False), mide el arranque y las
# latencias con curl, comprueba el bloqueo por petición lenta y mata el servidor.
#
# Uso: serve_probe.sh <PYTHON> <SANDBOX_WEB_DIR> <OUT_DIR>
#   PYTHON           intérprete con flask, pandas, sklearn, shap, statsmodels, geopandas,
#                    google-genai y google-generativeai (p. ej. un venv de scratch)
#   SANDBOX_WEB_DIR  copia de Web/ (con "../notebooks acabados/" copiado al lado)
set -u
PY="$1"; WEB="$2"; OUT="$3"
PORT=8100
BASE="http://127.0.0.1:${PORT}"
JAR="$OUT/cookies.txt"
mkdir -p "$OUT"; rm -f "$JAR"
export PYTHONDONTWRITEBYTECODE=1 LOKY_MAX_CPU_COUNT=2 OMP_NUM_THREADS=2
export FLASK_SECRET_KEY=audit-test-secret APP_USERNAME=audit_user APP_PASSWORD=audit_pass_123
unset GEMINI_API_KEY
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost

cd "$WEB"
T0=$(date +%s.%N)
"$PY" -c "import app; app.app.run(host='127.0.0.1', port=${PORT}, debug=False, threaded=False)" \
    > "$OUT/server.log" 2>&1 &
PID=$!
echo "server pid=$PID"
for i in $(seq 1 600); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/login" || true)
  [ "$code" = "200" ] && break
  sleep 0.1
done
T1=$(date +%s.%N)
echo "startup_to_first_200_s=$(echo "$T1 - $T0" | bc)"

curl -s -c "$JAR" -b "$JAR" -o /dev/null -w 'login %{http_code}\n' \
     --data 'username=audit_user&password=audit_pass_123' "$BASE/login"

probe() { # método ruta [datos-json]
  if [ "$1" = "POST" ]; then
    curl -s -b "$JAR" -o /dev/null -w "$1 $2 %{http_code} %{time_total}s\n" \
         -H 'Content-Type: application/json' --data "$3" "$BASE$2"
  else
    curl -s -b "$JAR" -o /dev/null -w "$1 $2 %{http_code} %{time_total}s\n" "$BASE$2"
  fi
}

probe GET /
probe GET /hipotecas
probe GET /api/paro-model-info
probe GET /api/dashboard-extra
probe GET "/api/hipoteca-context?year=2020"
probe GET "/api/hipoteca-context?year=2027"

# Bloqueo: /api/demanda-data (entrena RF en frío) en paralelo con una petición trivial
( probe GET /api/demanda-data > "$OUT/slow.txt" ) &
SLOW=$!
sleep 0.5
echo "--- petición trivial lanzada mientras /api/demanda-data entrena:"
probe GET /api/paro-model-info
wait "$SLOW"   # ¡no usar wait sin argumentos: esperaría también al servidor!
cat "$OUT/slow.txt"
probe GET /api/demanda-data
probe GET /api/data
probe GET /api/data
probe POST /api/hipoteca-recomendacion '{"year":"2024","tipo":"variable","income":3000,"savings":60000,"age":32,"province":"Madrid","other_debts":200,"price_mode":"auto","tenure_years":30}'
probe GET /api/mapa/tension
probe POST /api/chat '{"message":"hola"}'

# Cabeceras de seguridad de una página
echo "--- cabeceras de /:"
curl -s -b "$JAR" -D - -o /dev/null "$BASE/" | tr -d '\r'

kill "$PID" 2>/dev/null; sleep 1; kill -9 "$PID" 2>/dev/null
echo "server killed"
echo "--- RSS/errores en log del servidor:"
grep -cE "Traceback" "$OUT/server.log" | sed 's/^/tracebacks_in_log=/'
