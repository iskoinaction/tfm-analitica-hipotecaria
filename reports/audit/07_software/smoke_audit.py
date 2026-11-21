#!/usr/bin/env python3
"""
Auditoría dinámica de la app Flask v1 (Web/app.py) con el test client de Flask.

IMPORTANTE: se ejecuta sobre una COPIA de Web/ (sandbox), nunca sobre el repo,
porque la app escribe en disco (caché de mapas, custom_charts, subidas de admin).

Uso:
  PYTHONDONTWRITEBYTECODE=1 python smoke_audit.py --app-dir <sandbox>/run/Web --out results.json

Estructura esperada del sandbox (la app resuelve rutas relativas a Web/..):
  <sandbox>/a/run/Web/                      copia de Web/
  <sandbox>/a/run/notebooks acabados/       copia de dataset_final_tfm.csv y predicciones_provinciales_2026_2030.csv

Variables de entorno usadas (de prueba, no secretos reales):
  FLASK_SECRET_KEY=audit-test-secret  APP_USERNAME=audit_user  APP_PASSWORD=audit_pass_123
  GEMINI_API_KEY sin definir (los chatbots deben degradar sin coste).
"""
import argparse
import io
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    app_dir = os.path.abspath(args.app_dir)
    os.environ.pop("GEMINI_API_KEY", None)
    os.environ["FLASK_SECRET_KEY"] = "audit-test-secret"
    os.environ["APP_USERNAME"] = "audit_user"
    os.environ["APP_PASSWORD"] = "audit_pass_123"
    os.chdir(app_dir)  # la app calcula UPLOAD_FOLDER con abspath('..') relativo al cwd
    sys.path.insert(0, app_dir)

    out = {"app_dir": app_dir, "routes": [], "security": {}, "timings": {}}

    t0 = time.perf_counter()
    import app as appmod  # noqa: E402
    out["timings"]["import_app_s"] = round(time.perf_counter() - t0, 2)
    app = appmod.app
    # app.testing NO se activa: queremos ver los 500 reales que vería un usuario

    out["config"] = {
        "UPLOAD_FOLDER": app.config["UPLOAD_FOLDER"],
        "DATASET_PATH": appmod.DATASET_PATH,
        "df_shape": list(appmod.df.shape),
        "df_prov_preds_shape": list(appmod.df_prov_preds.shape),
        "df_tipos_shape": list(appmod.df_tipos.shape),
        "gemini_model_is_none": appmod.gemini_model is None,
        "MACRO_FORECASTS_after_import": bool(appmod._MACRO_FORECASTS),
        "PRICING_CACHE_after_import": list(appmod._PRICING_MODEL_CACHE.keys()),
        "MAX_CONTENT_LENGTH": app.config.get("MAX_CONTENT_LENGTH"),
        "SESSION_COOKIE_SECURE": app.config.get("SESSION_COOKIE_SECURE"),
        "SESSION_COOKIE_SAMESITE": app.config.get("SESSION_COOKIE_SAMESITE"),
        "SESSION_COOKIE_HTTPONLY": app.config.get("SESSION_COOKIE_HTTPONLY"),
        "url_map": sorted(
            [f"{','.join(sorted(r.methods - {'HEAD', 'OPTIONS'}))} {r.rule} -> {r.endpoint}" for r in app.url_map.iter_rules()]
        ),
    }
    import demanda_models as dm
    out["config"]["demanda_artifacts_after_import"] = dm._ARTIFACTS is not None

    anon = app.test_client()

    # ---------- 1. acceso anónimo ----------
    anon_checks = {}
    for path in ["/", "/api/data", "/api/custom-charts", "/admin", "/api/hipoteca-context"]:
        r = anon.get(path)
        anon_checks[path] = {"status": r.status_code, "location": r.headers.get("Location")}
    r = anon.post("/admin/execute-code", json={"code": "print(1)"})
    anon_checks["POST /admin/execute-code"] = {"status": r.status_code, "location": r.headers.get("Location")}
    out["security"]["anonymous_access"] = anon_checks

    # ---------- 2. login usuario + cabeceras ----------
    user = app.test_client()
    r = user.post("/login", data={"username": "audit_user", "password": "audit_pass_123"})
    out["security"]["user_login"] = {"status": r.status_code, "location": r.headers.get("Location"),
                                     "set_cookie": r.headers.get("Set-Cookie")}
    r = user.get("/")
    hdrs = {k: r.headers.get(k) for k in [
        "Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options",
        "Strict-Transport-Security", "Referrer-Policy", "Permissions-Policy", "Server"]}
    out["security"]["response_headers_on_index"] = hdrs

    # Open redirect tras login
    oc = app.test_client()
    r = oc.post("/login?next=https://evil.example/phish", data={"username": "audit_user", "password": "audit_pass_123"})
    out["security"]["open_redirect_login"] = {"status": r.status_code, "location": r.headers.get("Location")}

    # Login fallido: ¿hay bloqueo / rate limit? 30 intentos seguidos
    bf = app.test_client()
    codes = []
    t = time.perf_counter()
    for i in range(30):
        codes.append(bf.post("/login", data={"username": "audit_user", "password": f"wrong{i}"}).status_code)
    out["security"]["bruteforce_30_attempts"] = {"status_codes": sorted(set(codes)),
                                                  "total_s": round(time.perf_counter() - t, 3)}

    # ---------- 3. usuario normal -> admin (mismas credenciales) ----------
    r = user.post("/admin/execute-code", json={"code": "print(1)"})
    esc = {"user_session_execute_code_status": r.status_code}
    r = user.post("/login_admin", data={"username": "audit_user", "password": "audit_pass_123"})
    esc["login_admin_with_user_credentials_status"] = r.status_code
    esc["login_admin_location"] = r.headers.get("Location")
    out["security"]["privilege_escalation_same_credentials"] = esc

    # ---------- 4. RCE demostrativa (inocua) vía /admin/execute-code ----------
    code = ("import os, sys, platform\n"
            "sys.stderr.write('RCE_PROOF uid=%s cwd=%s py=%s' % (os.getuid(), os.getcwd(), platform.python_version()))\n")
    t = time.perf_counter()
    r = user.post("/admin/execute-code", json={"code": code, "description": "audit"})
    body = r.get_json(silent=True) or {}
    out["security"]["rce_execute_code"] = {
        "status": r.status_code, "elapsed_s": round(time.perf_counter() - t, 2),
        "stderr_echo_contains_proof": "RCE_PROOF" in json.dumps(body),
        "response_excerpt": json.dumps(body)[:300],
    }
    # Variante: ¿el código ve variables de entorno del servidor? (sólo comprobamos la clave de prueba)
    code_env = ("import os, sys\n"
                "sys.stderr.write('ENV_LEAK FLASK_SECRET_KEY=' + str(os.environ.get('FLASK_SECRET_KEY')))\n")
    r = user.post("/admin/execute-code", json={"code": code_env})
    out["security"]["rce_env_access"] = {"status": r.status_code,
                                        "secret_visible_to_user_code": "audit-test-secret" in r.get_data(as_text=True)}

    # upload-chart con un .py (misma ejecución arbitraria)
    r = user.post("/admin/upload-chart", data={
        "chart_file": (io.BytesIO(b"import sys\nsys.stderr.write('UPLOAD_RCE_PROOF')\n"), "probe.py"),
        "description": "audit"}, content_type="multipart/form-data")
    out["security"]["rce_upload_chart"] = {"status": r.status_code,
                                          "proof": "UPLOAD_RCE_PROOF" in r.get_data(as_text=True)}

    # ---------- 5. path traversal en subida CSV de /admin ----------
    upload_root = app.config["UPLOAD_FOLDER"]
    target = os.path.abspath(os.path.join(upload_root, "..", "pt_probe.csv"))
    if os.path.exists(target):
        os.remove(target)
    r = user.post("/admin", data={
        "action": "dataset",
        "file": (io.BytesIO(b"a,b\n1,2\n"), "../pt_probe.csv")}, content_type="multipart/form-data")
    out["security"]["path_traversal_admin_upload"] = {
        "status": r.status_code, "upload_folder": upload_root, "expected_escape_target": target,
        "file_written_outside_upload_folder": os.path.exists(target),
    }
    # Subida normal: ¿se puede sobrescribir cualquier CSV en la raíz del repo?
    r = user.post("/admin", data={
        "action": "dataset",
        "file": (io.BytesIO(b"x,y\n1,2\n"), "README_probe.csv")}, content_type="multipart/form-data")
    out["security"]["arbitrary_csv_in_repo_root"] = {
        "status": r.status_code, "written": os.path.exists(os.path.join(upload_root, "README_probe.csv"))}

    # CSRF: POST sin token aceptado (no existe ningún mecanismo anti-CSRF)
    out["security"]["csrf_token_present_in_admin_form"] = "csrf" in user.get("/admin").get_data(as_text=True).lower()

    # ---------- 6. borrado de chart chartjs -> KeyError ----------
    charts = user.get("/api/custom-charts").get_json()
    cj = next((c for c in charts if c.get("render_type") == "chartjs"), None)
    if cj:
        r = user.delete(f"/api/custom-charts/{cj['id']}")
        out["security"]["delete_chartjs_chart"] = {"status": r.status_code, "body": r.get_data(as_text=True)[:200]}

    # ---------- 7. rutas funcionales: estado y latencias ----------
    def timed(method, path, **kw):
        t = time.perf_counter()
        resp = getattr(user, method)(path, **kw)
        dt = time.perf_counter() - t
        js = resp.get_json(silent=True)
        info = {"method": method.upper(), "path": path, "status": resp.status_code, "elapsed_s": round(dt, 3),
                "bytes": len(resp.get_data())}
        if isinstance(js, dict):
            info["json_keys"] = sorted(js.keys())[:25]
            if "error" in js:
                info["error"] = str(js["error"])[:200]
            if "traceback" in js:
                info["leaks_traceback"] = True
        out["routes"].append(info)
        return resp, info

    for p in ["/", "/hipotecas", "/demanda", "/demanda-provincial", "/hipotecas-provincial",
              "/metodologia-ml", "/econometria", "/vecm", "/webscrapping", "/business_case",
              "/admin", "/test-hipoteca", "/login", "/login_admin"]:
        timed("get", p)

    # APIs (1ª llamada = frío, 2ª = caché)
    timed("get", "/api/custom-charts")
    timed("get", "/api/paro-model-info")
    timed("get", "/api/paro-model-info?provincia=Badajoz")
    timed("get", "/api/dashboard-extra")
    timed("get", "/api/dashboard-extra?provincia=Madrid&year=2020")
    timed("get", "/api/hipoteca-context?year=2020")
    timed("get", "/api/hipoteca-context?year=2028")  # dispara _build_forecasts (ARIMA grid)
    timed("get", "/api/hipoteca-context?year=2028")
    timed("get", "/api/hipoteca-context?year=2028&provincia=Madrid")
    r, i = timed("get", "/api/demanda-data")       # entrena RF provincial + nacional + forecast recursivo
    if r.status_code == 200 and isinstance(r.get_json(), dict) and "kpis" in r.get_json():
        js = r.get_json()
        out["demanda_runtime_metrics"] = {"kpis": js["kpis"], "benchmark": js.get("benchmark")}
    timed("get", "/api/demanda-data")
    timed("get", "/api/demanda-data?year=2028-Q2")
    timed("get", "/api/demanda-data?year=2020&provincia=Madrid")
    timed("get", "/api/data")
    timed("get", "/api/data")
    timed("get", "/api/data?year_from=2010&year_to=2015")
    profile = {"year": "2024", "tipo": "variable", "income": 3000, "savings": 60000, "age": 32,
               "province": "Madrid", "other_debts": 200, "price_mode": "auto", "tenure_years": 30}
    r, i = timed("post", "/api/hipoteca-recomendacion", json=profile)
    if r.status_code == 200:
        js = r.get_json()
        out["hipoteca_sample"] = {k: js.get(k) for k in ["status", "rate", "applied_rate", "applied_type", "ml_rate",
                                                         "ml_r2", "ml_rmse", "monthly_installment", "dti_ratio",
                                                         "estimated_price", "province", "ccaa"]}
        out["hipoteca_sample"]["ml_transparency"] = js.get("ml_transparency")
    timed("post", "/api/hipoteca-recomendacion", json=profile)
    timed("post", "/api/hipoteca-recomendacion", json={**profile, "year": "2028"})
    timed("post", "/api/hipoteca-recomendacion", json={**profile, "province": "Comunidad de Madrid"})
    timed("post", "/test-hipoteca", data={"income": "3000", "savings": "60000", "age": "30",
                                          "province": "Comunidad de Madrid", "year": "2024"})
    timed("get", "/api/mapa/tension")         # caché b64 en disco
    timed("get", "/api/mapa/accesibilidad")   # genera con geopandas+matplotlib
    timed("get", "/api/mapa/accesibilidad")
    timed("get", "/api/mapa/mina_oro")        # entrena RandomForest en la petición
    timed("get", "/api/mapa/xyz")
    timed("post", "/api/chat", json={"message": "hola"})
    timed("post", "/api/noa-chat", json={"message": "hola", "context": {}})
    timed("post", "/api/noa-strategic", json={"message": "hola", "context": {}})

    # ---------- 8. robustez de entrada ----------
    robust = {}
    for label, method, path, kw in [
        ("data_year_from_texto", "get", "/api/data?year_from=abc", {}),
        ("demanda_year_texto", "get", "/api/demanda-data?year=abc", {}),
        ("demanda_year_sin_datos", "get", "/api/demanda-data?year=1990", {}),
        ("hipoteca_ctx_year_texto", "get", "/api/hipoteca-context?year=abc", {}),
        ("recomendacion_income_texto", "post", "/api/hipoteca-recomendacion", {"json": {**profile, "income": "abc"}}),
        ("recomendacion_sin_json", "post", "/api/hipoteca-recomendacion", {"data": "x"}),
        ("chat_sin_json", "post", "/api/chat", {"data": "x"}),
        ("recomendacion_income_negativo", "post", "/api/hipoteca-recomendacion", {"json": {**profile, "income": -1000}}),
        ("recomendacion_age_200", "post", "/api/hipoteca-recomendacion", {"json": {**profile, "age": 200}}),
    ]:
        try:
            resp = getattr(user, method)(path, **kw)
            body = resp.get_data(as_text=True)
            robust[label] = {"status": resp.status_code, "leaks_traceback": "Traceback" in body,
                             "excerpt": body[:160]}
        except Exception as e:  # el test client propaga excepciones si TESTING
            robust[label] = {"status": "exception", "exception": f"{type(e).__name__}: {e}"[:200]}
    out["robustness"] = robust

    out["timings"]["caches_after_run"] = {
        "MACRO_FORECASTS_keys": sorted(appmod._MACRO_FORECASTS.keys()),
        "PRICING_CACHE_keys": sorted(appmod._PRICING_MODEL_CACHE.keys()),
        "demanda_artifacts_loaded": dm._ARTIFACTS is not None,
    }
    out["macro_forecasts_sample"] = {k: v for k, v in appmod._MACRO_FORECASTS.items()}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(json.dumps({"import_s": out["timings"]["import_app_s"], "n_routes": len(out["routes"])}))


if __name__ == "__main__":
    main()
