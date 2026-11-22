"""Geografía canónica: provincias (código INE 01-52) y comunidades autónomas.

Sustituye al *fuzzy matching* (difflib, cutoff=0.5) del notebook original por una
resolución determinista basada en alias explícitos. Un nombre desconocido
lanza ``KeyError`` en lugar de asignarse silenciosamente a la provincia más
parecida.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Province:
    code: str          # código INE de provincia, "01".."52"
    name: str          # nombre oficial INE (forma castellana/cooficial)
    legacy_name: str   # nombre usado en el dataset v1 (compatibilidad)
    ccaa_code: str     # código INE de CCAA, "01".."19"


CCAA = {
    "01": "Andalucía", "02": "Aragón", "03": "Principado de Asturias", "04": "Illes Balears",
    "05": "Canarias", "06": "Cantabria", "07": "Castilla y León", "08": "Castilla-La Mancha",
    "09": "Cataluña", "10": "Comunitat Valenciana", "11": "Extremadura", "12": "Galicia",
    "13": "Comunidad de Madrid", "14": "Región de Murcia", "15": "Comunidad Foral de Navarra",
    "16": "País Vasco", "17": "La Rioja", "18": "Ceuta", "19": "Melilla",
}

_P = [
    ("01", "Araba/Álava", "Álava", "16"), ("02", "Albacete", "Albacete", "08"),
    ("03", "Alicante/Alacant", "Alicante", "10"), ("04", "Almería", "Almería", "01"),
    ("05", "Ávila", "Ávila", "07"), ("06", "Badajoz", "Badajoz", "11"),
    ("07", "Illes Balears", "Islas Baleares", "04"), ("08", "Barcelona", "Barcelona", "09"),
    ("09", "Burgos", "Burgos", "07"), ("10", "Cáceres", "Cáceres", "11"),
    ("11", "Cádiz", "Cádiz", "01"), ("12", "Castellón/Castelló", "Castellón", "10"),
    ("13", "Ciudad Real", "Ciudad Real", "08"), ("14", "Córdoba", "Córdoba", "01"),
    ("15", "A Coruña", "A Coruña", "12"), ("16", "Cuenca", "Cuenca", "08"),
    ("17", "Girona", "Girona", "09"), ("18", "Granada", "Granada", "01"),
    ("19", "Guadalajara", "Guadalajara", "08"), ("20", "Gipuzkoa", "Guipúzcoa", "16"),
    ("21", "Huelva", "Huelva", "01"), ("22", "Huesca", "Huesca", "02"),
    ("23", "Jaén", "Jaén", "01"), ("24", "León", "León", "07"),
    ("25", "Lleida", "Lleida", "09"), ("26", "La Rioja", "La Rioja", "17"),
    ("27", "Lugo", "Lugo", "12"), ("28", "Madrid", "Comunidad de Madrid", "13"),
    ("29", "Málaga", "Málaga", "01"), ("30", "Murcia", "Región de Murcia", "14"),
    ("31", "Navarra", "Comunidad Foral de Navarra", "15"), ("32", "Ourense", "Ourense", "12"),
    ("33", "Asturias", "Principado de Asturias", "03"), ("34", "Palencia", "Palencia", "07"),
    ("35", "Las Palmas", "Las Palmas", "05"), ("36", "Pontevedra", "Pontevedra", "12"),
    ("37", "Salamanca", "Salamanca", "07"), ("38", "Santa Cruz de Tenerife", "Santa Cruz de Tenerife", "05"),
    ("39", "Cantabria", "Cantabria", "06"), ("40", "Segovia", "Segovia", "07"),
    ("41", "Sevilla", "Sevilla", "01"), ("42", "Soria", "Soria", "07"),
    ("43", "Tarragona", "Tarragona", "09"), ("44", "Teruel", "Teruel", "02"),
    ("45", "Toledo", "Toledo", "08"), ("46", "Valencia/València", "Valencia", "10"),
    ("47", "Valladolid", "Valladolid", "07"), ("48", "Bizkaia", "Vizcaya", "16"),
    ("49", "Zamora", "Zamora", "07"), ("50", "Zaragoza", "Zaragoza", "02"),
    ("51", "Ceuta", "Ceuta", "18"), ("52", "Melilla", "Melilla", "19"),
]
PROVINCES: dict[str, Province] = {c: Province(c, n, l, a) for c, n, l, a in _P}


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni signos; corrige mojibake latin-1→utf-8 habitual."""
    s = str(text)
    try:  # p.ej. 'MÃ¡laga' -> 'Málaga'
        repaired = s.encode("latin-1").decode("utf-8")
        s = repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z]", "", s)


# Alias explícitos (normalizados) -> código. Se generan desde nombres oficiales,
# legacy y las formas cooficiales/variantes observadas en INE, MIVAU, BCE.
_EXTRA_ALIASES = {
    "01": ["alava", "araba", "arabaalava"], "03": ["alicante", "alacant"],
    "07": ["baleares", "balears", "illesbalears", "balearsilles", "islasbaleares"],
    "12": ["castellon", "castello", "castellondelaplana"], "15": ["coruna", "lacoruna", "corunaa", "acoruna"],
    "20": ["guipuzcoa", "gipuzkoa"], "26": ["rioja", "riojala"], "28": ["madrid", "comunidaddemadrid", "madridcomunidadde"],
    "30": ["murcia", "regiondemurcia", "murciaregionde"],
    "31": ["navarra", "comunidadforaldenavarra", "navarracomunidadforalde"],
    "33": ["asturias", "principadodeasturias", "asturiasprincipadode"],
    "35": ["laspalmas", "palmaslas"], "38": ["santacruzdetenerife", "tenerife"],
    "46": ["valencia", "valenciavalencia"], "48": ["bizkaia", "vizcaya"],
    "26b": [],
}
ALIASES: dict[str, str] = {}
for _code, _p in PROVINCES.items():
    for _n in (_p.name, _p.legacy_name, *_p.name.split("/")):
        ALIASES[normalize(_n)] = _code
for _code, _al in _EXTRA_ALIASES.items():
    if _code in PROVINCES:
        for _a in _al:
            ALIASES[_a] = _code


def province_code(name_or_code: str) -> str:
    """Devuelve el código INE (2 dígitos) de una provincia. ``KeyError`` si no se reconoce.

    Acepta: código ("8", "08", "08 Barcelona"), nombre oficial, legacy o alias.
    """
    raw = str(name_or_code).strip()
    m = re.match(r"^(\d{1,2})(?:\s+|$)(.*)$", raw)
    if m:
        code = m.group(1).zfill(2)
        if code in PROVINCES:
            if m.group(2):  # comprobar coherencia código-nombre si viene nombre
                rest = normalize(m.group(2))
                if rest and ALIASES.get(rest, code) != code:
                    raise KeyError(f"Código y nombre incoherentes: {raw!r}")
            return code
    key = normalize(raw)
    if key in ALIASES:
        return ALIASES[key]
    raise KeyError(f"Provincia no reconocida: {raw!r}")


def ccaa_of(prov_code: str) -> str:
    return PROVINCES[prov_code].ccaa_code


def provinces_of_ccaa(ccaa_code: str) -> list[str]:
    return [c for c, p in PROVINCES.items() if p.ccaa_code == ccaa_code]


_CCAA_ALIASES = {normalize(v): k for k, v in CCAA.items()}
_CCAA_ALIASES.update({
    "andalucia": "01", "aragon": "02", "asturias": "03", "asturiasprincipadode": "03", "baleares": "04",
    "balearsilles": "04", "islasbaleares": "04", "canarias": "05", "cantabria": "06",
    "castillayleon": "07", "castillalamancha": "08", "castillalamanchaa": "08", "cataluna": "09", "catalunya": "09",
    "comunitatvalenciana": "10", "comunidadvalenciana": "10", "valencianacomunitat": "10",
    "extremadura": "11", "galicia": "12", "madrid": "13", "madridcomunidadde": "13",
    "murcia": "14", "murciaregionde": "14", "navarra": "15", "navarracomunidadforalde": "15",
    "paisvasco": "16", "euskadi": "16", "rioja": "17", "riojala": "17", "larioja": "17",
    "ceuta": "18", "melilla": "19",
})


def ccaa_code(name_or_code: str) -> str:
    raw = str(name_or_code).strip()
    m = re.match(r"^(\d{1,2})(?:\s+|$)", raw)
    if m and m.group(1).zfill(2) in CCAA:
        return m.group(1).zfill(2)
    key = normalize(raw)
    if key in _CCAA_ALIASES:
        return _CCAA_ALIASES[key]
    raise KeyError(f"CCAA no reconocida: {raw!r}")
