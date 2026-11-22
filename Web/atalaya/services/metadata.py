"""Catálogo de fuentes (``data/metadata/sources.yaml`` o ``.json``) para la página "Datos y fuentes".

El esquema definitivo lo fija el equipo de datos; aquí se lee de forma tolerante y se
normaliza a filas de tabla con las claves que existan (nunca se rellenan valores).
"""
from __future__ import annotations

import json
from pathlib import Path

PREFERRED_COLUMNS = [
    ("dataset", "Conjunto de datos"), ("fuente", "Organismo"), ("tabla_o_clave", "Tabla / clave"),
    ("frecuencia", "Frecuencia"), ("retraso_publicacion", "Retraso de publicación"),
    ("ultima_modificacion_origen", "Última modificación en origen"), ("fecha_extraccion", "Extracción"),
    ("licencia", "Licencia"), ("url_documentacion", "Documentación"),
    ("id", "Id"), ("name", "Fuente"), ("provider", "Organismo"),
    ("series_id", "Serie / id"), ("frequency", "Frecuencia"), ("last_period", "Último periodo"),
    ("published", "Publicación"), ("downloaded_at", "Descarga"), ("license", "Licencia"),
    ("status", "Estado"), ("url", "Enlace"),
]


def _load(path: Path):
    if path.suffix in (".yaml", ".yml"):
        import yaml  # PyYAML (fijado en requirements)
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_sources(data_dir: Path) -> dict:
    base = Path(data_dir) / "metadata"
    for name in ("series_catalog.yaml", "sources.yaml", "sources.yml", "sources.json"):
        p = base / name
        if p.is_file():
            try:
                raw = _load(p)
            except Exception as e:  # noqa: BLE001 - se informa en la UI
                return {"status": "invalid", "path": f"data/metadata/{name}", "message": f"No se pudo leer: {e}",
                        "columns": [], "rows": []}
            return {"status": "ok", "path": f"data/metadata/{name}", **_to_table(raw)}
    return {"status": "missing", "path": "data/metadata/sources.yaml", "columns": [], "rows": [],
            "message": "Catálogo de fuentes no generado"}


def _to_table(raw) -> dict:
    for key in ("sources", "datasets", "series"):
        if isinstance(raw, dict) and isinstance(raw.get(key), (list, dict)):
            raw = raw[key]
            break
    if isinstance(raw, dict):
        items = [{"id": k, **(v if isinstance(v, dict) else {"name": v})} for k, v in raw.items()]
    elif isinstance(raw, list):
        items = [x if isinstance(x, dict) else {"name": x} for x in raw]
    else:
        items = []
    present = [(k, label) for k, label in PREFERRED_COLUMNS if any(k in it for it in items)][:9]
    if not present:  # esquema desconocido: columnas tal cual (primer nivel, sólo escalares)
        keys: list[str] = []
        for it in items:
            for k, v in it.items():
                if k not in keys and not isinstance(v, (dict, list)):
                    keys.append(k)
        present = [(k, k) for k in keys[:10]]
    rows = []
    for it in items:
        row = []
        for k, _ in present:
            v = it.get(k)
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)[:200]
            row.append(None if v is None else str(v)[:300])
        if any("tinsa" in str(c).lower() for c in row):
            continue  # Tinsa no se muestra en la web
        rows.append(row)
    return {"columns": [{"key": k, "label": label} for k, label in present], "rows": rows}
