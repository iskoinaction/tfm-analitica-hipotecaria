"""Catálogo provincial canónico (código INE 01-52) reutilizando ``src.common.geography``.

Sustituye los tres normalizadores de nombres de la v1 por una única resolución determinista.
"""
from __future__ import annotations

from src.common.geography import CCAA, PROVINCES, province_code  # noqa: F401  (reexport)


def province_options() -> list[dict]:
    """Lista para selectores: [{code, name, ccaa}] ordenada por nombre."""
    return sorted(
        ({"code": c, "name": p.legacy_name if "/" in p.name else p.name, "ccaa": CCAA[p.ccaa_code]}
         for c, p in PROVINCES.items()),
        key=lambda d: d["name"],
    )


def province_name(code: str) -> str:
    p = PROVINCES.get(str(code).zfill(2))
    if not p:
        raise KeyError(code)
    return p.legacy_name if "/" in p.name else p.name


def resolve(value: str | None) -> str | None:
    """Código INE a partir de código o nombre; None si vacío; KeyError si no se reconoce."""
    if value is None or str(value).strip() == "":
        return None
    return province_code(value)
