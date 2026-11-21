"""Importa Web/app.py sin GEMINI_API_KEY ni SDK de Google (stubs) y SIN escribir ficheros nuevos.
Uso: from _app_loader import load_app; app_mod = load_app()
"""
import os, sys, types

def load_app():
    sys.dont_write_bytecode = True  # no dejar Web/__pycache__/app.*.pyc
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    web = os.path.join(root, 'Web')
    os.environ.pop('GEMINI_API_KEY', None)
    g = types.ModuleType('google'); g.__path__ = []
    genai = types.ModuleType('google.genai'); genai.Client = object
    gtypes = types.ModuleType('google.genai.types'); gtypes.GenerateContentConfig = dict
    genai.types = gtypes
    old = types.ModuleType('google.generativeai')
    g.genai = genai; g.generativeai = old
    sys.modules.update({'google': g, 'google.genai': genai, 'google.genai.types': gtypes, 'google.generativeai': old})
    # app.py crea static/custom_charts/index.json solo si no existe; comprobamos que existe para no escribir
    assert os.path.exists(os.path.join(web, 'static', 'custom_charts', 'index.json')), 'index.json no existe: el import escribiría'
    sys.path.insert(0, web)
    cwd = os.getcwd(); os.chdir(web)
    try:
        import app as app_mod
    finally:
        os.chdir(cwd)
    return app_mod

def patch_shap_scalar(app_mod):
    """shap>=0.4x devuelve expected_value como array (1,) -> float() falla y el endpoint da HTTP 500.
    Solo para poder auditar el resto de la lógica, envolvemos TreeExplainer para devolver escalar."""
    import numpy as np
    base = app_mod.shap.TreeExplainer
    class _TE:
        def __init__(self, model):
            self._e = base(model)
            ev = np.ravel(self._e.expected_value)
            self.expected_value = float(ev[0])
        def shap_values(self, X):
            return self._e.shap_values(X)
    app_mod.shap.TreeExplainer = _TE
    app_mod._PRICING_MODEL_CACHE.clear()

def client(app_mod):
    c = app_mod.app.test_client()
    with c.session_transaction() as s:
        s['user'] = 'auditor'
    return c
