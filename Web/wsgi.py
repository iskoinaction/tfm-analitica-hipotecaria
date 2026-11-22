"""Punto de entrada WSGI de Atalaya v2.

Producción (desde la raíz del repositorio):
    gunicorn --chdir Web wsgi:app
La factory añade la raíz del repositorio a sys.path para importar ``src.*``.
"""
import os
import sys

_WEB_DIR = os.path.dirname(os.path.abspath(__file__))
if _WEB_DIR not in sys.path:
    sys.path.insert(0, _WEB_DIR)

try:  # variables locales opcionales en Web/.env (no versionado); el entorno real tiene prioridad
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_WEB_DIR, ".env"), override=False)
except ImportError:  # pragma: no cover
    pass

from atalaya import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":  # servidor de desarrollo: python Web/wsgi.py (sin modo debug)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8100")), debug=False)
