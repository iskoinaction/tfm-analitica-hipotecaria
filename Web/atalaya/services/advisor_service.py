"""Fachada del asesor hipotecario.

La lógica de cálculo (cuota, DTI, fiscalidad, pricing) NO vive en la app: está en el motor puro
``src.advisor`` (propiedad del equipo de Banca). Esta capa sólo:

1. valida y normaliza la entrada (rangos, tipos, provincia canónica INE);
2. llama a ``src.advisor.simulate(payload: dict) -> dict``;
3. devuelve un estado ``pending`` explícito si el motor aún no existe.

Los datos personales del formulario (ingresos, ahorro, edad…) no se registran en logs, no se
guardan y nunca se envían al asistente LLM.
"""
from __future__ import annotations

import importlib
import json
import logging
import math

from .geo import province_name, resolve

log = logging.getLogger(__name__)

ENGINE_MODULE = "src.advisor"
ENGINE_FUNCTION = "simulate"
METADATA_FUNCTION = "metadata"

# campo -> (tipo, mínimo, máximo, obligatorio)
NUMERIC_FIELDS = {
    "ingresos_netos_mensuales": (float, 0, 100_000, True),
    "ahorro_disponible": (float, 0, 5_000_000, True),
    "edad": (int, 18, 80, True),
    "plazo_anios": (int, 5, 40, True),
    "otras_deudas_mensuales": (float, 0, 50_000, False),
    "precio_vivienda": (float, 10_000, 10_000_000, False),
    "superficie_m2": (float, 15, 1_000, False),
    "anio": (int, 2005, 2035, False),
}
CHOICE_FIELDS = {
    "tipo_interes": ({"variable", "fijo", "mixto"}, "variable"),
    "tipo_vivienda": ({"segunda_mano", "nueva"}, "segunda_mano"),
    "escenario": ({"base", "adverso", "favorable"}, "base"),
}
BOOL_FIELDS = {"primera_vivienda": True}


class AdvisorEngineError(ValueError):
    """El motor rechazó la entrada (sus propios errores de validación, con mensaje claro)."""


class AdvisorInputError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def validate_payload(raw) -> dict:
    if not isinstance(raw, dict):
        raise AdvisorInputError({"_": "Se esperaba un objeto JSON"})
    errors: dict[str, str] = {}
    out: dict = {}
    try:
        code = resolve(raw.get("prov_code") or raw.get("provincia"))
        if code is None:
            errors["prov_code"] = "Selecciona una provincia"
        else:
            out["prov_code"] = code
            out["provincia"] = province_name(code)
    except KeyError:
        errors["prov_code"] = "Provincia no reconocida"

    for name, (typ, lo, hi, required) in NUMERIC_FIELDS.items():
        val = raw.get(name)
        if val in (None, ""):
            if required:
                errors[name] = "Campo obligatorio"
            continue
        try:
            num = float(val)
            if not math.isfinite(num):
                raise ValueError
            if typ is int:
                if num != int(num):
                    raise ValueError
                num = int(num)
        except (TypeError, ValueError):
            errors[name] = "Debe ser un número" + (" entero" if typ is int else "")
            continue
        if not lo <= num <= hi:
            errors[name] = f"Debe estar entre {lo:,} y {hi:,}".replace(",", ".")
            continue
        out[name] = num

    if "precio_vivienda" not in out and "superficie_m2" not in out and "precio_vivienda" not in errors:
        errors["precio_vivienda"] = "Indica el precio de la vivienda o su superficie"

    for name, (choices, default) in CHOICE_FIELDS.items():
        val = raw.get(name, default) or default
        if val not in choices:
            errors[name] = f"Valor no permitido (opciones: {', '.join(sorted(choices))})"
        else:
            out[name] = val
    for name, default in BOOL_FIELDS.items():
        val = raw.get(name, default)
        out[name] = val if isinstance(val, bool) else str(val).lower() in {"1", "true", "on", "si", "sí"}

    if errors:
        raise AdvisorInputError(errors)
    return out


def engine_status() -> dict:
    """¿Está disponible el motor ``src.advisor``? No ejecuta cálculos."""
    try:
        mod = importlib.import_module(ENGINE_MODULE)
    except ModuleNotFoundError as e:
        if e.name and (e.name == ENGINE_MODULE or ENGINE_MODULE.startswith(e.name + ".")):
            return {"available": False, "reason": "Módulo src.advisor pendiente de implementación."}
        return {"available": False, "reason": f"Dependencia ausente del motor: {e.name}"}
    except Exception as e:  # noqa: BLE001 - un motor roto no debe tumbar la app
        log.exception("Error importando el motor del asesor")
        return {"available": False, "reason": f"El motor no se pudo cargar ({type(e).__name__})."}
    fn = getattr(mod, ENGINE_FUNCTION, None)
    if not callable(fn):
        return {"available": False, "reason": f"src.advisor no expone '{ENGINE_FUNCTION}(payload)'."}
    return {"available": True, "reason": None, "version": getattr(mod, "__version__", None)}


def _jsonable(obj):
    """Convierte la salida del motor a JSON puro (numpy, NaN -> None)."""
    def default(o):
        for attr in ("item", "tolist"):
            if hasattr(o, attr):
                return getattr(o, attr)()
        return str(o)

    txt = json.dumps(obj, default=default, allow_nan=True)
    data = json.loads(txt)

    def clean(x):
        if isinstance(x, float) and not math.isfinite(x):
            return None
        if isinstance(x, dict):
            return {str(k): clean(v) for k, v in x.items()}
        if isinstance(x, list):
            return [clean(v) for v in x]
        return x

    return clean(data)


def simulate(payload: dict) -> dict:
    """Valida ``payload`` y delega en ``src.advisor.simulate``.

    Devuelve ``{"status": "ok", "input": ..., "result": ...}`` o
    ``{"status": "pending", "reason": ...}`` si el motor no está disponible.
    Lanza ``AdvisorInputError`` ante una entrada inválida.
    """
    clean = validate_payload(payload)
    status = engine_status()
    if not status["available"]:
        return {"status": "pending", "reason": status["reason"], "input": clean}
    fn = getattr(importlib.import_module(ENGINE_MODULE), ENGINE_FUNCTION)
    try:
        result = fn(dict(clean))
    except (ValueError, KeyError, TypeError) as e:  # errores de validación del motor -> 400
        raise AdvisorEngineError(str(e)[:500]) from e
    if not isinstance(result, dict):
        raise TypeError("src.advisor.simulate debe devolver un dict")
    return {"status": "ok", "input": clean, "result": _jsonable(result), "engine_version": status.get("version")}


def metadata() -> dict | None:
    """``src.advisor.metadata()`` (provincias/CCAA, parámetros, vigencias) o None si no existe."""
    if not engine_status()["available"]:
        return None
    fn = getattr(importlib.import_module(ENGINE_MODULE), METADATA_FUNCTION, None)
    if not callable(fn):
        return None
    try:
        return _jsonable(fn())
    except Exception:  # noqa: BLE001
        log.exception("src.advisor.metadata() falló")
        return None
