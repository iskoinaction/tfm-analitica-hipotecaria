"""Especificación de "vistas" que los pipelines escriben en ``artifacts/`` y la UI pinta.

La app no conoce modelos: sólo valida y normaliza estas vistas declarativas. Así ninguna
cifra se teclea en plantillas y cualquier vista inválida se muestra como tal (no se inventa).

Tipos soportados (``type``):

* ``metrics``     {items: [{label, value, unit?, note?, period?}]}
* ``timeseries``  {x: [str], series: [{name, values: [num|null], role?: historical|forecast|lower|upper|scenario}], unit?}
* ``bar``         {labels: [str], series: [{name, values}], stacked?: bool, horizontal?: bool, unit?}
* ``table``       {columns: [str], rows: [[str|num|null]]}
* ``choropleth``  {values: {prov_code(01-52): num|null}, unit?, period?}
* ``note``        {text: str}   (texto plano; nunca HTML)

Campos comunes: ``title`` (obligatorio), ``id``, ``subtitle``, ``description``, ``unit``, ``source``.
"""
from __future__ import annotations

import math
import re

VIEW_TYPES = {"metrics", "timeseries", "bar", "table", "choropleth", "note"}
SERIES_ROLES = {"historical", "forecast", "lower", "upper", "scenario", "observed", "fitted"}
MAX_POINTS = 5000
MAX_ROWS = 2000
PROV_RE = re.compile(r"^(0[1-9]|[1-4][0-9]|5[0-2])$")


class ViewError(ValueError):
    pass


def _text(v, field: str, required: bool = False, max_len: int = 2000) -> str | None:
    if v is None:
        if required:
            raise ViewError(f"falta '{field}'")
        return None
    if not isinstance(v, (str, int, float)):
        raise ViewError(f"'{field}' debe ser texto")
    s = str(v).strip()
    if required and not s:
        raise ViewError(f"'{field}' vacío")
    return s[:max_len]


def _num(v):
    """Número finito o None. Rechaza booleanos y textos."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ViewError("valor booleano donde se esperaba número")
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and not math.isfinite(v)) else v
    raise ViewError(f"valor no numérico: {v!r}")


def _cell(v):
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "sí" if v else "no"
    return _num(v)


def _numbers(values, field: str, n: int | None = None) -> list:
    if not isinstance(values, list):
        raise ViewError(f"'{field}' debe ser una lista")
    if len(values) > MAX_POINTS:
        raise ViewError(f"'{field}' supera {MAX_POINTS} puntos")
    if n is not None and len(values) != n:
        raise ViewError(f"'{field}' tiene {len(values)} valores y se esperaban {n}")
    return [_num(v) for v in values]


def _labels(values, field: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ViewError(f"'{field}' debe ser una lista no vacía")
    if len(values) > MAX_POINTS:
        raise ViewError(f"'{field}' supera {MAX_POINTS} elementos")
    return [str(v) for v in values]


def _series(raw, n: int) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ViewError("'series' debe ser una lista no vacía")
    out = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise ViewError(f"series[{i}] no es un objeto")
        role = s.get("role", "historical")
        if role not in SERIES_ROLES:
            raise ViewError(f"series[{i}].role desconocido: {role!r}")
        out.append({
            "name": _text(s.get("name"), f"series[{i}].name", required=True, max_len=120),
            "values": _numbers(s.get("values"), f"series[{i}].values", n),
            "role": role,
        })
    return out


def validate_view(raw) -> dict:
    if not isinstance(raw, dict):
        raise ViewError("la vista no es un objeto JSON")
    vtype = raw.get("type")
    if vtype not in VIEW_TYPES:
        raise ViewError(f"tipo de vista desconocido: {vtype!r}")
    v = {
        "type": vtype,
        "id": _text(raw.get("id"), "id", max_len=80),
        "title": _text(raw.get("title"), "title", required=True, max_len=200),
        "subtitle": _text(raw.get("subtitle"), "subtitle", max_len=300),
        "description": _text(raw.get("description"), "description"),
        "unit": _text(raw.get("unit"), "unit", max_len=40),
        "source": _text(raw.get("source"), "source", max_len=300),
    }
    if vtype == "metrics":
        items = raw.get("items")
        if not isinstance(items, list) or not items:
            raise ViewError("'items' debe ser una lista no vacía")
        v["items"] = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                raise ViewError(f"items[{i}] no es un objeto")
            val = it.get("value")
            val = _text(val, f"items[{i}].value", max_len=60) if isinstance(val, str) else _num(val)
            v["items"].append({
                "label": _text(it.get("label"), f"items[{i}].label", required=True, max_len=120),
                "value": val,
                "unit": _text(it.get("unit"), f"items[{i}].unit", max_len=40),
                "note": _text(it.get("note"), f"items[{i}].note", max_len=300),
                "period": _text(it.get("period"), f"items[{i}].period", max_len=40),
            })
    elif vtype == "timeseries":
        x = _labels(raw.get("x"), "x")
        v["x"] = x
        v["series"] = _series(raw.get("series"), len(x))
    elif vtype == "bar":
        labels = _labels(raw.get("labels"), "labels")
        v["labels"] = labels
        v["series"] = _series(raw.get("series"), len(labels))
        v["stacked"] = bool(raw.get("stacked", False))
        v["horizontal"] = bool(raw.get("horizontal", False))
    elif vtype == "table":
        cols = _labels(raw.get("columns"), "columns")
        rows = raw.get("rows")
        if not isinstance(rows, list):
            raise ViewError("'rows' debe ser una lista")
        if len(rows) > MAX_ROWS:
            raise ViewError(f"'rows' supera {MAX_ROWS} filas")
        out_rows = []
        for i, r in enumerate(rows):
            if not isinstance(r, list) or len(r) != len(cols):
                raise ViewError(f"rows[{i}] no tiene {len(cols)} celdas")
            out_rows.append([_cell(c) for c in r])
        v["columns"], v["rows"] = cols, out_rows
    elif vtype == "choropleth":
        vals = raw.get("values")
        if not isinstance(vals, dict) or not vals:
            raise ViewError("'values' debe ser un objeto {prov_code: valor}")
        clean = {}
        for k, val in vals.items():
            code = str(k).zfill(2)
            if not PROV_RE.match(code):
                raise ViewError(f"código de provincia no válido: {k!r}")
            clean[code] = _num(val)
        v["values"] = clean
        v["period"] = _text(raw.get("period"), "period", max_len=40)
    elif vtype == "note":
        v["text"] = _text(raw.get("text"), "text", required=True, max_len=4000)
    return {k: val for k, val in v.items() if val is not None}


def validate_views(raw_list) -> list[dict]:
    """Valida una lista de vistas; las inválidas se sustituyen por una vista de error explícita."""
    if isinstance(raw_list, dict) and "views" in raw_list:
        raw_list = raw_list["views"]
    if not isinstance(raw_list, list):
        return [{"type": "invalid", "title": "Fichero de vistas no válido",
                 "error": "se esperaba una lista de vistas o {\"views\": [...]}"}]
    out = []
    for i, raw in enumerate(raw_list):
        try:
            out.append(validate_view(raw))
        except ViewError as e:
            title = raw.get("title") if isinstance(raw, dict) else None
            out.append({"type": "invalid", "title": str(title or f"Vista {i + 1}")[:200], "error": str(e)})
    return out
