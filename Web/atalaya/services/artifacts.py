"""Lectura de artefactos versionados generados por los pipelines (``artifacts/<dominio>/``).

La app NUNCA entrena modelos: sólo lee lo que dejan los pipelines. Contrato provisional
(se adaptará al esquema definitivo en esta capa, sin tocar plantillas):

    artifacts/<dominio>/manifest.json
    {
      "domain": "demand",
      "version": "2026.11.0",
      "generated_at": "2026-11-21T18:00:00Z",          # obligatorio (ISO 8601)
      "generator": "python -m src.pipelines.update_all",
      "data_cutoff": "2025Q4",
      "sources": [{"name": "INE ...", "url": "...", "series_id": "...", "published": "2026-10-30"}],  # obligatorio
      "views": ["views.json"],                          # ficheros con vistas (ver services/views.py)
      "scopes": {"provincial": "views_provincial.json"},  # opcional: {"28": [vistas], ...}
      "metrics": {...},                                 # opcional: resumen numérico
      "notes": "texto plano"
    }

Si falta el directorio o el manifest, el estado es ``missing`` y la UI muestra el comando que
lo genera; si el manifest no cumple el contrato, ``invalid`` con el motivo. Nunca hay datos de relleno.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .views import validate_views

DOMAINS = {
    "econometrics": {"label": "Econometría (VAR/VECM)", "command": "python -m src.pipelines.update_all"},
    "forecasting": {"label": "Proyecciones 2026-2030", "command": "python -m src.pipelines.generate_forecasts"},
    "demand": {"label": "Demanda hipotecaria", "command": "python -m src.pipelines.update_all"},
    "advisor": {"label": "Asesor hipotecario", "command": "python -m src.pipelines.update_all"},
    "data_quality": {"label": "Calidad de datos", "command": "python -m src.pipelines.build_master"},
}
MAX_FILE_BYTES = 20 * 1024 * 1024


class ManifestError(ValueError):
    pass


@dataclass
class ArtifactBundle:
    domain: str
    status: str                      # ok | missing | invalid
    label: str
    command: str
    message: str = ""
    manifest: dict = field(default_factory=dict)
    views: list = field(default_factory=list)
    path: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def meta(self) -> dict:
        m = self.manifest
        return {
            "domain": self.domain,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "command": m.get("generator") or self.command,
            "version": m.get("version"),
            "generated_at": m.get("generated_at"),
            "generated_at_display": _display_dt(m.get("generated_at")),
            "data_cutoff": m.get("data_cutoff"),
            "sources": m.get("sources", []),
            "notes": m.get("notes"),
        }

    def to_dict(self) -> dict:
        return {"meta": self.meta(), "views": self.views}


def _display_dt(value) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M") + (" UTC" if dt.tzinfo else "")
    except ValueError:
        return str(value)


def _safe_child(base: Path, rel: str) -> Path:
    """Resuelve un fichero declarado en el manifest impidiendo salir del directorio del dominio."""
    if not isinstance(rel, str) or not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        raise ManifestError(f"ruta de fichero no permitida en el manifest: {rel!r}")
    p = (base / rel).resolve()
    if base.resolve() not in p.parents:
        raise ManifestError(f"ruta fuera del directorio del artefacto: {rel!r}")
    return p


def _read_json(path: Path):
    if not path.is_file():
        raise ManifestError(f"no existe el fichero {path.name}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ManifestError(f"{path.name} supera el tamaño máximo")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _validate_manifest(m) -> dict:
    if not isinstance(m, dict):
        raise ManifestError("manifest.json no es un objeto")
    if not m.get("generated_at"):
        raise ManifestError("manifest sin 'generated_at' (fecha de generación)")
    try:
        datetime.fromisoformat(str(m["generated_at"]).replace("Z", "+00:00"))
    except ValueError as e:
        raise ManifestError(f"'generated_at' no es ISO 8601: {m['generated_at']!r}") from e
    sources = m.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ManifestError("manifest sin 'sources' (fuentes de los datos)")
    clean_sources = []
    for s in sources:
        if isinstance(s, str):
            s = {"name": s}
        if not isinstance(s, dict) or not s.get("name"):
            raise ManifestError("cada fuente debe tener 'name'")
        clean_sources.append({k: str(s[k])[:300] for k in ("name", "url", "series_id", "published", "license", "edition")
                              if s.get(k) is not None})
    for s in clean_sources:  # sólo enlaces http(s) en la UI
        if "url" in s and not s["url"].startswith(("https://", "http://")):
            s.pop("url")
    out = dict(m)
    out["sources"] = clean_sources
    views = m.get("views", [])
    if isinstance(views, str):
        views = [views]
    if not isinstance(views, list):
        raise ManifestError("'views' debe ser una lista de ficheros")
    out["views"] = views
    scopes = m.get("scopes", {})
    if not isinstance(scopes, dict):
        raise ManifestError("'scopes' debe ser un objeto")
    out["scopes"] = scopes
    return out


class ArtifactStore:
    def __init__(self, root: Path, ttl: int = 30, data_dir: Path | None = None) -> None:
        self.root = Path(root)
        self.data_dir = Path(data_dir) if data_dir else self.root.parent / "data"
        self.ttl = ttl
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[ArtifactBundle, float, float]] = {}
        self._scope_cache: dict[tuple, tuple[dict, float]] = {}

    # ----------------------------------------------------------------
    def _manifest_path(self, domain: str) -> Path:
        return self.root / domain / "manifest.json"

    def get(self, domain: str) -> ArtifactBundle:
        if domain not in DOMAINS:
            raise KeyError(domain)
        now = time.monotonic()
        mpath = self._manifest_path(domain)
        with self._lock:
            cached = self._cache.get(domain)
            if cached and now - cached[2] < self.ttl:
                return cached[0]
            mtime = mpath.stat().st_mtime if mpath.exists() else -1.0
            if cached and cached[1] == mtime:
                self._cache[domain] = (cached[0], mtime, now)
                return cached[0]
            bundle = self._load(domain, mpath)
            self._cache[domain] = (bundle, mtime, now)
            return bundle

    def _load(self, domain: str, mpath: Path) -> ArtifactBundle:
        info = DOMAINS[domain]
        base = dict(domain=domain, label=info["label"], command=info["command"], path=str(mpath.parent))
        if not mpath.exists():
            from .native import BUILDERS
            try:
                res = BUILDERS[domain](self.root, self.data_dir)
            except Exception as e:  # noqa: BLE001  adaptador defensivo: nunca rompe la página
                return ArtifactBundle(status="invalid", message=f"Artefacto nativo no legible: {e}", **base)
            if res:
                manifest, views = res
                return ArtifactBundle(status="ok", manifest=_validate_manifest(manifest), views=views, **base)
            return ArtifactBundle(status="missing", message="Artefacto no generado", **base)
        try:
            manifest = _validate_manifest(_read_json(mpath))
            views: list = []
            for rel in manifest["views"]:
                views.extend(validate_views(_read_json(_safe_child(mpath.parent, rel))))
        except (ManifestError, json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            return ArtifactBundle(status="invalid", message=f"Artefacto no válido: {e}", **base)
        return ArtifactBundle(status="ok", manifest=manifest, views=views, **base)

    def scope_views(self, domain: str, scope: str, key: str) -> list | None:
        """Vistas de un ámbito (p. ej. ``provincial`` / ``"28"``). None si no existen."""
        bundle = self.get(domain)
        if not bundle.ok:
            return None
        if bundle.manifest.get("native"):
            from .native import demand_scope
            if domain == "demand" and scope == "provincial":
                try:
                    return demand_scope(self.root, self.data_dir, str(key).zfill(2))
                except Exception as e:  # noqa: BLE001
                    return [{"type": "invalid", "title": "Vistas del ámbito no disponibles", "error": str(e)}]
            return None
        rel = bundle.manifest.get("scopes", {}).get(scope)
        if not rel:
            return None
        try:
            path = _safe_child(Path(bundle.path), rel)
            mtime = path.stat().st_mtime
            ck = (domain, scope)
            with self._lock:
                cached = self._scope_cache.get(ck)
            if cached and cached[1] == mtime:
                data = cached[0]
            else:
                data = _read_json(path)
                if not isinstance(data, dict):
                    raise ManifestError("el fichero de ámbito debe ser un objeto {clave: [vistas]}")
                with self._lock:
                    self._scope_cache[ck] = (data, mtime)
        except (ManifestError, json.JSONDecodeError, OSError) as e:
            return [{"type": "invalid", "title": "Vistas del ámbito no disponibles", "error": str(e)}]
        raw = data.get(key)
        return None if raw is None else validate_views(raw)

    def scope_keys(self, domain: str, scope: str) -> list[str]:
        bundle = self.get(domain)
        if bundle.ok and bundle.manifest.get("native") and domain == "demand" and scope == "provincial":
            return [f"{i:02d}" for i in range(1, 53)]
        if not bundle.ok or scope not in bundle.manifest.get("scopes", {}):
            return []
        try:
            path = _safe_child(Path(bundle.path), bundle.manifest["scopes"][scope])
            data = _read_json(path)
            return sorted(str(k) for k in data) if isinstance(data, dict) else []
        except (ManifestError, json.JSONDecodeError, OSError):
            return []

    def status_all(self) -> list[dict]:
        return [self.get(d).meta() for d in DOMAINS]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._scope_cache.clear()
