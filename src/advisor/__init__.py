"""Asesor hipotecario v2 de Atalaya · Analítica Hipotecaria (motor puro, sin Flask).

API pública:
- ``simulate(payload: dict) -> dict``: simulación orientativa (tipo de mercado y rango con fuente y fecha, cuota,
  cuadro anual, gastos desglosados con norma y verificación, entrada necesaria, DSTI/LTV/LTI, estrés, semáforo,
  avisos legales y supuestos). Lanza ``AdvisorInputError`` (con ``.errors``) si la entrada no es válida.
- ``metadata() -> dict``: provincias/CCAA, parámetros de política, reglas fiscales con vigencias, aranceles,
  último periodo de mercado y escenarios.
"""
from .engine import AdvisorInputError, metadata, simulate

__all__ = ["simulate", "metadata", "AdvisorInputError"]
