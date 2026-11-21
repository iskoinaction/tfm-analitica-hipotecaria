"""Entrada de datos de la econometría v2.

Fuente preferente: ``data/processed/nacional_trimestral.csv`` y ``panel_trimestral.csv``
(Data Engineering). Mientras no existan se usa una construcción PROVISIONAL a
partir del dataset v1 con el parseo de hipotecas corregido y la serie nacional INE
de hipotecas sobre viviendas; queda marcada como ``provisional`` en los metadatos.

Las columnas de los ficheros v2 se resuelven por reglas explícitas (regex sobre el
nombre normalizado) y cualquier ambigüedad lanza un error: no se adivina.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


# --------------------------------------------------------------------------- utilidades
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def to_period(x) -> pd.PeriodIndex:
    s = pd.Series(x).astype(str).str.strip()
    out = []
    for v in s:
        m = re.match(r"^(\d{4})\s*-?\s*[QqTt]\s*([1-4])$", v)
        if m:
            out.append(pd.Period(year=int(m.group(1)), quarter=int(m.group(2)), freq="Q-DEC"))
        else:
            out.append(pd.Timestamp(v).to_period("Q-DEC"))
    return pd.PeriodIndex(out, freq="Q-DEC")


# Reglas: canónico -> (patrones que deben aparecer todos, patrones prohibidos)
NATIONAL_RULES = {
    "period": ([r"^(period|periodo|trimestre|quarter|fecha|date)$"], []),
    "hip_viv": ([r"hipotec", r"viv"], [r"importe", r"impor", r"_eur", r"tasa", r"var", r"medio", r"_sa$", r"desest"]),
    "hip_tot": ([r"hipotec", r"(total|fincas)"], [r"viv", r"importe", r"impor", r"tasa", r"var", r"medio", r"_sa$", r"desest"]),
    "precio": ([r"(precio|tinsa|imie)"], [r"ipv", r"tasad", r"mivau", r"mitma", r"var", r"indice_ipv", r"_n$", r"simple"]),
    "precio_ipv": ([r"ipv"], [r"var", r"tasa_var"]),
    "precio_tasado": ([r"(tasad|mivau|mitma)"], [r"var"]),
    "pib_pc": ([r"pib", r"(pc|per_capita|percapita)"], [r"var", r"tasa", r"real", r"anual"]),
    "pib": ([r"^pib"], [r"pc", r"per_capita", r"percapita", r"var", r"tasa", r"real", r"anual"]),
    "poblacion": ([r"^poblacion"], [r"ext", r"var"]),
    "euribor": ([r"euribor"], [r"var", r"diff", r"lag"]),
    "materiales": ([r"material"], [r"var", r"lag"]),
    "ipc": ([r"^ipc"], [r"var", r"tasa"]),
}


def resolve_columns(df: pd.DataFrame, rules: dict, required: list[str]) -> dict:
    norm = {c: _norm(c) for c in df.columns}
    out = {}
    for key, (must, forbid) in rules.items():
        cands = [c for c, n in norm.items()
                 if all(re.search(p, n) for p in must) and not any(re.search(p, n) for p in forbid)]
        if len(cands) == 1:
            out[key] = cands[0]
        elif len(cands) > 1:
            # preferir la coincidencia más corta (nombre más "canónico"); si empatan, error
            cands = sorted(cands, key=lambda c: len(norm[c]))
            if len(norm[cands[0]]) == len(norm[cands[1]]):
                raise ValueError(f"Columna ambigua para '{key}': {cands}. Pase un mapeo explícito (colmap).")
            out[key] = cands[0]
    missing = [k for k in required if k not in out]
    if missing:
        raise ValueError(f"No se encuentran columnas para {missing} en {list(df.columns)}")
    return out


@dataclass
class NationalData:
    raw: pd.DataFrame                    # índice PeriodIndex, columnas canónicas en niveles
    source: str                          # "v2" | "provisional_v1fix"
    inputs: list = field(default_factory=list)   # [{path, sha256}]
    notes: list = field(default_factory=list)
    colmap: dict = field(default_factory=dict)

    def system(self, hip: str = "hip_viv", price: str = "precio", start: str = C.START,
               end: str | None = None) -> pd.DataFrame:
        r = self.raw
        if hip not in r or price not in r:
            raise KeyError(f"Variable no disponible: {hip if hip not in r else price}")
        y = pd.DataFrame({
            "log_materiales": np.log(r["materiales"]),
            "euribor": r["euribor"],
            "log_pib_pc": np.log(r["pib_pc"]),
            "log_precio": np.log(r[price]),
            "log_hipotecas": np.log(r[hip]),
        }, index=r.index)
        y = y.loc[start:end] if end else y.loc[start:]
        # bloque contiguo sin NaN (sin imputaciones): desde el primer al último trimestre completo
        ok = y.notna().all(axis=1)
        if not ok.any():
            raise ValueError("Sistema vacío tras eliminar NaN")
        first, last = ok.idxmax(), ok[::-1].idxmax()
        y = y.loc[first:last]
        if y.isna().any().any():
            gaps = y.index[y.isna().any(axis=1)].astype(str).tolist()
            raise ValueError(f"Huecos internos en el sistema (no se interpola): {gaps}")
        return y


def _ine_monthly_to_quarter(path: Path) -> pd.Series:
    d = json.load(open(path, encoding="utf-8"))
    rows = [(int(x["Anyo"]), int(x["FK_Periodo"]), float(x["Valor"])) for x in d["Data"] if x["Valor"] is not None]
    s = pd.DataFrame(rows, columns=["y", "m", "v"])
    s["q"] = [pd.Period(year=a, quarter=(m - 1) // 3 + 1, freq="Q-DEC") for a, m in zip(s.y, s.m)]
    g = s.groupby("q")["v"].agg(["sum", "count"])
    return g.loc[g["count"] == 3, "sum"]  # solo trimestres completos


def parse_ine_thousands(v: str) -> float:
    """Parseo correcto del CSV INE exportado (miles truncados: '17.49' = 17.490; 'X.0' = X)."""
    a, b = str(v).strip().split(".")
    return float(a) if b == "0" else float(int(a) * 1000 + int(b.ljust(3, "0")))


def hip_total_provincial_fixed() -> pd.DataFrame:
    h = pd.read_csv(C.V1_HIP_RAW, sep=";", dtype=str)
    h["v"] = h["Total"].map(parse_ine_thousands)
    h["period"] = [pd.Period(year=int(p[:4]), quarter=(int(p[5:]) - 1) // 3 + 1, freq="Q-DEC") for p in h.Periodo]
    g = h.groupby(["Provincias", "period"])["v"].agg(["sum", "count"]).reset_index()
    g = g[g["count"] == 3]
    from src.common.geography import province_code
    g["prov_code"] = g.Provincias.map(province_code)
    return g[["prov_code", "period", "sum"]].rename(columns={"sum": "hip_tot"})


def _v1_inputs() -> list[Path]:
    return [C.V1FIX] if C.V1FIX.exists() else [C.V1_DATASET, C.V1_HIP_RAW]


def _v1_panel() -> pd.DataFrame:
    """Panel v1 con hipotecas (total fincas) bien parseadas: usa el v1fix de Data Engineering si existe."""
    from src.common.geography import province_code
    if C.V1FIX.exists():
        df = pd.read_csv(C.V1FIX)
        df["hip_tot"] = df["Hipotecas_Total"]
    else:
        df = pd.read_csv(C.V1_DATASET)
    df["prov_code"] = df.Provincia.map(province_code)
    df["period"] = pd.PeriodIndex(pd.to_datetime(df.Trimestre), freq="Q-DEC")
    if not C.V1FIX.exists():
        df = df.merge(hip_total_provincial_fixed(), on=["prov_code", "period"], how="left")
    return df


def load_national_provisional() -> NationalData:
    df = _v1_panel()
    g = df.groupby("period")
    w = df["Poblacion"]
    df["_p"] = df.Precio_m2 * w
    df["_y"] = df.PIB_pc * w
    raw = pd.DataFrame({
        "hip_tot": g["hip_tot"].sum(min_count=52),
        "precio": g["_p"].sum(min_count=52) / g["Poblacion"].sum(),
        "pib_pc": g["_y"].sum(min_count=52) / g["Poblacion"].sum(),
        "euribor": g["Euribor"].mean(),
        "materiales": g["Indice_Materiales"].mean(),
        "poblacion": g["Poblacion"].sum(),
    })
    raw["hip_viv"] = _ine_monthly_to_quarter(C.INE_HPT_VIV).reindex(raw.index)
    raw.index = pd.PeriodIndex(raw.index, freq="Q-DEC")
    inputs = [{"path": str(p.relative_to(C.ROOT)), "sha256": sha256(p)} for p in (*_v1_inputs(), C.INE_HPT_VIV)]
    notes = ["PROVISIONAL: construcción propia desde dataset v1 corregido (v1fix de Data Engineering si existe) + INE HPT34618 (viviendas).",
             "PIB_pc provincial ANUAL repetido en los 4 trimestres (escalón), ponderado por población; sustituir por INE CNTR en v2.",
             "Precio Tinsa ponderado por población."]
    return NationalData(raw=raw, source="provisional_v1fix", inputs=inputs, notes=notes)


def load_national_v2(path: Path = C.NATIONAL_V2, colmap: dict | None = None) -> NationalData:
    df = pd.read_csv(path)
    if colmap is None and all(c in df.columns for c in C.V2_NATIONAL_COLMAP.values()):
        colmap = dict(C.V2_NATIONAL_COLMAP)
    cm = colmap or resolve_columns(df, NATIONAL_RULES, ["period", "euribor", "materiales"])
    raw = pd.DataFrame(index=to_period(df[cm["period"]]))
    for k, c in cm.items():
        if k != "period":
            raw[k] = pd.to_numeric(df[c], errors="coerce").values
    raw = raw[~raw.index.duplicated()].sort_index()
    notes = []
    if "pib_nominal_sa" in raw and "poblacion" in raw:
        raw["pib_pc"] = raw["pib_nominal_sa"] * 1e6 / raw["poblacion"]
        notes.append("pib_pc = PIB nominal trimestral CNTR (CVEC, M€) / población ECP (stock vigente, sin interpolar)")
    if "pib_pc" not in raw:
        if "pib" in raw and "poblacion" in raw:
            raw["pib_pc"] = raw["pib"] / raw["poblacion"]
            notes.append("pib_pc = pib / poblacion (calculado)")
        else:
            raise ValueError("Falta PIB per cápita (ni pib_pc ni pib+poblacion) en nacional_trimestral.csv")
    if "hip_viv" not in raw:
        raise ValueError("Falta hipotecas sobre viviendas en nacional_trimestral.csv")
    return NationalData(raw=raw, source="v2", inputs=[{"path": str(Path(path).relative_to(C.ROOT)), "sha256": sha256(path)}],
                        notes=notes, colmap=cm)


def load_national(prefer: str = "auto", colmap: dict | None = None) -> NationalData:
    if prefer in ("auto", "v2") and C.NATIONAL_V2.exists():
        return load_national_v2(colmap=colmap)
    if prefer == "v2":
        raise FileNotFoundError(C.NATIONAL_V2)
    return load_national_provisional()


# --------------------------------------------------------------------------- panel
PANEL_RULES = {
    "prov_code": ([r"^(prov_code|cod_prov|codigo_provincia|prov)$"], []),
    "period": ([r"^(period|periodo|trimestre|quarter|fecha|date)$"], []),
    "hip_viv": ([r"hipotec", r"viv"], [r"importe", r"impor", r"var", r"medio"]),
    "hip_tot": ([r"hipotec", r"(total|fincas)"], [r"viv", r"importe", r"impor", r"var", r"medio"]),
    "precio": ([r"(precio|tinsa|imie)"], [r"ipv", r"tasad", r"mivau", r"var", r"lag"]),
    "pib_pc": ([r"pib", r"(pc|per_capita|percapita)"], [r"var", r"tasa", r"lag"]),
    "poblacion": ([r"^poblacion"], [r"ext", r"var"]),
    "euribor": ([r"euribor"], [r"var", r"lag"]),
    "materiales": ([r"material"], [r"var", r"lag"]),
}


@dataclass
class PanelData:
    df: pd.DataFrame        # columnas: prov_code, period, hip, precio, pib_pc, euribor, materiales, poblacion
    source: str
    hip_kind: str
    inputs: list
    notes: list


def load_panel(prefer: str = "auto", colmap: dict | None = None) -> PanelData:
    src = C.PANEL_MODELADO_V2 if C.PANEL_MODELADO_V2.exists() else C.PANEL_V2
    if prefer in ("auto", "v2") and src.exists():
        df = pd.read_csv(src, dtype={"prov_code": str})
        if colmap is None and all(c in df.columns for c in C.V2_PANEL_COLMAP.values()):
            colmap = dict(C.V2_PANEL_COLMAP)
        cm = colmap or resolve_columns(df, PANEL_RULES, ["prov_code", "period", "precio", "euribor", "materiales"])
        out = pd.DataFrame({"prov_code": df[cm["prov_code"]].astype(str).str.zfill(2),
                            "period": to_period(df[cm["period"]])})
        for k in ("precio", "pib_pc", "euribor", "materiales", "poblacion"):
            if k in cm:
                out[k] = pd.to_numeric(df[cm[k]], errors="coerce").values
        kind = "hip_viv" if "hip_viv" in cm else "hip_tot"
        out["hip"] = pd.to_numeric(df[cm[kind]], errors="coerce").values
        return PanelData(out, "v2", kind, [{"path": str(src.relative_to(C.ROOT)), "sha256": sha256(src)}],
                         [f"columnas: {cm}", "pib_pc provincial anual (CRE) asignado a los 4 trimestres del año de referencia"])
    if prefer == "v2":
        raise FileNotFoundError(C.PANEL_V2)
    df = _v1_panel()
    out = pd.DataFrame({"prov_code": df.prov_code, "period": df.period, "hip": df.hip_tot, "precio": df.Precio_m2,
                        "pib_pc": df.PIB_pc, "euribor": df.Euribor, "materiales": df.Indice_Materiales,
                        "poblacion": df.Poblacion})
    return PanelData(out, "provisional_v1fix", "hip_tot",
                     [{"path": str(p.relative_to(C.ROOT)), "sha256": sha256(p)} for p in _v1_inputs()],
                     ["PROVISIONAL: hipotecas provinciales = total fincas con parseo corregido (no hay viviendas provinciales en v1)."])


def seasonal_dummies(index: pd.PeriodIndex) -> pd.DataFrame:
    q = np.asarray(index.quarter)
    return pd.DataFrame({f"Q{k}": (q == k).astype(float) - 0.25 for k in (2, 3, 4)}, index=index)


def impulse_dummies(index: pd.PeriodIndex, periods: list[str]) -> pd.DataFrame:
    out = {}
    for p in periods:
        per = pd.Period(p, freq="Q-DEC")
        if per in index:
            out[f"D{p}"] = (index == per).astype(float)
    return pd.DataFrame(out, index=index)
