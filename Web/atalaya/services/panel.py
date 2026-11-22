"""Acceso de sólo lectura al panel trimestral provincial v2 (datos observados, no modelos).

Ficheros (contrato de datos v2, ``data/processed/``):
* ``panel_trimestral.(parquet|csv)``  provincia (``prov_code`` INE) × trimestre (``period`` YYYYQn).
* ``nacional_trimestral.csv``          series nacionales publicadas (se prefieren a agregar provincias).
* ``data/metadata/data_dictionary.csv`` unidad, fuente, dataset y tabla de cada columna (atribución).

Sólo si ``ATALAYA_ALLOW_LEGACY_PANEL`` y no existe el panel v2 se usa el dataset v1, etiquetado
como "legado" y con sus columnas renombradas a las claves v2.

Licencias: las columnas de Tinsa (``precio_m2_tinsa`` y el ``Precio_m2`` del v1, que procedía de
Tinsa) NO se exponen nunca: sus condiciones de uso prohíben explotar el contenido sin autorización.
El precio por m² que muestra la web es el valor tasado del MIVAU (``precio_m2_mivau_tasado``).
"""
from __future__ import annotations

import csv
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import province_code, province_name

# Variables expuestas (clave v2 -> etiqueta corta, agregación de respaldo si no hay serie nacional)
VARIABLES: dict[str, dict] = {
    "hipotecas_viviendas_num": {"label": "Hipotecas sobre viviendas", "unit": "nº", "agg": "sum"},
    "hipotecas_viviendas_importe": {"label": "Importe de hipotecas sobre viviendas", "unit": "miles €", "agg": "sum"},
    "compraventas_viviendas_num": {"label": "Compraventas de viviendas", "unit": "nº", "agg": "sum"},
    "precio_m2_mivau_tasado": {"label": "Valor tasado de la vivienda libre (MIVAU)", "unit": "€/m²", "agg": "mean"},
    "ipv_general_indice": {"label": "Índice de precios de vivienda (INE)", "unit": "índice", "agg": "mean"},
    "euribor_12m": {"label": "Euríbor a 12 meses", "unit": "%", "agg": "first"},
    "tae_vivienda": {"label": "TAE de préstamos para vivienda", "unit": "%", "agg": "first"},
    "diferencial_tae_euribor": {"label": "Diferencial TAE − Euríbor", "unit": "p.p.", "agg": "first"},
    "tasa_paro": {"label": "Tasa de paro (EPA)", "unit": "%", "agg": "mean"},
    "ipc_var_anual": {"label": "IPC, variación anual", "unit": "%", "agg": "mean"},
    "tasa_ahorro_hogares": {"label": "Tasa de ahorro de los hogares", "unit": "%", "agg": "first"},
    "indice_coste_construccion": {"label": "Índice de costes de construcción", "unit": "índice", "agg": "first"},
}
AGG_LABEL = {"sum": "suma de provincias", "mean": "media simple de provincias", "first": "serie nacional",
             "national": "serie nacional del panel"}
SOURCE_NAMES = {"ine": "INE", "mivau": "MIVAU", "ecb": "BCE", "eurostat": "Eurostat", "bde": "Banco de España",
                "derivada": "Derivada", "tinsa": "Tinsa"}

# Columnas que la web NO puede mostrar (licencia Tinsa). "precio_m2" es el nombre normalizado del v1.
BLOCKED_COLUMN_RE = re.compile(r"tinsa|^precio_m2$")

_LEGACY_COLUMNS = {
    "Provincia": "provincia", "Trimestre": "trimestre", "Euribor": "euribor_12m",
    "Spread_Hipotecas": "diferencial_tae_euribor", "Hipotecas_Total": "hipotecas_viviendas_num",
    "Tasa_Paro": "tasa_paro", "IPC": "ipc_var_anual", "tasa_ahorro": "tasa_ahorro_hogares",
    "Transmisiones_Total": "compraventas_viviendas_num", "Precio_m2": "precio_m2",
}


class PanelUnavailable(RuntimeError):
    pass


@dataclass
class PanelData:
    df: pd.DataFrame                 # prov_code, period, <variables>
    national: pd.DataFrame | None    # period, <variables>
    path: Path
    is_legacy: bool
    mtime: float
    dictionary: dict = field(default_factory=dict)

    @property
    def source_label(self) -> str:
        return f"Panel v1 (legado): {self.path.name}" if self.is_legacy else f"Panel maestro v2: data/processed/{self.path.name}"


def _blocked(col: str) -> bool:
    return bool(BLOCKED_COLUMN_RE.search(str(col).strip().lower()))


def _period_labels(series: pd.Series) -> list[str]:
    s = series.astype(str).str.strip()
    if s.str.match(r"^\d{4}-?Q[1-4]$").all():
        return s.str.replace("-", "", regex=False).tolist()
    per = pd.PeriodIndex(pd.to_datetime(s).dt.to_period("Q-DEC"))
    return [f"{p.year}Q{p.quarter}" for p in per]


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={c: _LEGACY_COLUMNS.get(c, c) for c in raw.columns})
    df.columns = [str(c).strip().lower() if str(c) not in VARIABLES else str(c) for c in df.columns]
    df = df[[c for c in df.columns if not _blocked(c)]]
    if "prov_code" in df.columns:
        df["prov_code"] = df["prov_code"].astype(str).str.zfill(2)
    elif "provincia" in df.columns:
        df["prov_code"] = df["provincia"].map(province_code)
    else:
        raise PanelUnavailable("el panel no tiene 'prov_code' ni 'Provincia'")
    if "period" in df.columns:
        df["period"] = _period_labels(df["period"])
    elif "trimestre" in df.columns:
        df["period"] = _period_labels(df["trimestre"])
    else:
        raise PanelUnavailable("el panel no tiene 'period' ni 'Trimestre'")
    keep = ["prov_code", "period"] + [v for v in VARIABLES if v in df.columns]
    out = df[keep].copy()
    for v in keep[2:]:
        out[v] = pd.to_numeric(out[v], errors="coerce")
    return out.sort_values(["period", "prov_code"]).reset_index(drop=True)


def _load_dictionary(path: Path) -> dict:
    """{(panel, columna): {unidad, fuente, dataset, tabla, descripcion}} desde data_dictionary.csv."""
    out: dict = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out[(row.get("panel"), row.get("columna"))] = row
    return out


class PanelService:
    def __init__(self, data_dir: Path, legacy_path: Path | None, allow_legacy: bool) -> None:
        processed = Path(data_dir) / "processed"
        self.candidates = [processed / "panel_trimestral.parquet", processed / "panel_trimestral.csv"]
        self.national_path = processed / "nacional_trimestral.csv"
        self.dictionary_path = Path(data_dir) / "metadata" / "data_dictionary.csv"
        self.legacy_path = legacy_path if allow_legacy else None
        self._lock = threading.Lock()
        self._data: PanelData | None = None

    def _locate(self) -> tuple[Path, bool]:
        for p in self.candidates:
            if p.is_file():
                return p, False
        if self.legacy_path and self.legacy_path.is_file():
            return self.legacy_path, True
        raise PanelUnavailable("No se encuentra el panel maestro (data/processed/panel_trimestral.*). "
                               "Genéralo con: python -m src.pipelines.build_master")

    def load(self) -> PanelData:
        path, legacy = self._locate()
        mtime = path.stat().st_mtime
        with self._lock:
            if self._data and self._data.path == path and self._data.mtime == mtime:
                return self._data
            raw = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, dtype={"prov_code": str})
            national = None
            if not legacy and self.national_path.is_file():
                nat = pd.read_csv(self.national_path)
                nat = nat[[c for c in nat.columns if not _blocked(c)]]
                nat["period"] = _period_labels(nat["period"])
                national = nat[["period"] + [v for v in VARIABLES if v in nat.columns]].copy()
                for v in national.columns[1:]:
                    national[v] = pd.to_numeric(national[v], errors="coerce")
            self._data = PanelData(_normalize(raw), national, path, legacy, mtime,
                                   _load_dictionary(self.dictionary_path) if not legacy else {})
            return self._data

    def available(self) -> bool:
        try:
            self.load()
            return True
        except (PanelUnavailable, OSError, ValueError, KeyError, ImportError):
            return False

    # ------------------------------------------------------------------ metadatos de variables
    def var_meta(self, var: str) -> dict:
        d = self.load()
        meta = dict(VARIABLES[var])
        row = d.dictionary.get(("panel_trimestral", var)) or {}
        if row:
            fuente = SOURCE_NAMES.get(row.get("fuente", ""), row.get("fuente", ""))
            ref = " · ".join(x for x in (row.get("dataset"), row.get("tabla_o_serie")) if x)
            meta["source"] = f"{fuente} ({ref})" if ref else fuente
            meta["unit_full"] = row.get("unidad") or meta["unit"]
            meta["geo_level"] = row.get("geo_level")
            meta["description"] = row.get("descripcion")
        return meta

    def variables(self) -> list[dict]:
        df = self.load().df
        return [{"key": k, **self.var_meta(k)} for k in VARIABLES if k in df.columns]

    def _check_var(self, var: str) -> None:
        if var not in VARIABLES or var not in self.load().df.columns:
            raise KeyError(var)

    # ------------------------------------------------------------------ consultas
    def national_series(self, var: str) -> dict:
        self._check_var(var)
        d = self.load()
        if d.national is not None and var in d.national.columns and d.national[var].notna().any():
            s = d.national[["period", var]].dropna()
            return {"x": s["period"].tolist(), "values": [round(float(v), 4) for v in s[var]],
                    "agg": "national", "agg_label": AGG_LABEL["national"]}
        agg = VARIABLES[var]["agg"]
        g = d.df.groupby("period")[var]
        if agg == "sum":
            s = g.sum(min_count=1)
            s[g.count() < 52] = np.nan  # sólo trimestres con las 52 provincias informadas
        elif agg == "first":
            s = g.median()
        else:
            s = g.mean()
        s = s.dropna()
        return {"x": s.index.tolist(), "values": [round(float(v), 4) for v in s.values],
                "agg": agg, "agg_label": AGG_LABEL[agg]}

    def province_series(self, var: str, code: str) -> dict:
        self._check_var(var)
        df = self.load().df
        sub = df[df["prov_code"] == code][["period", var]].dropna()
        return {"x": sub["period"].tolist(), "values": [round(float(v), 4) for v in sub[var].values]}

    def latest_period(self, var: str) -> str | None:
        self._check_var(var)
        df = self.load().df
        counts = df.dropna(subset=[var]).groupby("period")[var].count()
        full = counts[counts >= 26]  # al menos la mitad de provincias informadas
        return full.index.max() if not full.empty else None

    def by_province(self, var: str, period: str | None = None) -> tuple[str | None, dict]:
        self._check_var(var)
        period = period or self.latest_period(var)
        df = self.load().df
        sub = df[df["period"] == period][["prov_code", var]]
        return period, {r[0]: (None if pd.isna(r[1]) else round(float(r[1]), 4))
                        for r in sub.itertuples(index=False, name=None)}

    def periods(self) -> list[str]:
        return sorted(self.load().df["period"].unique().tolist())

    def kpis(self) -> list[dict]:
        """Último dato y variación interanual de indicadores clave (datos observados)."""
        out = []
        for var in ["hipotecas_viviendas_num", "precio_m2_mivau_tasado", "euribor_12m", "tasa_paro"]:
            try:
                s = self.national_series(var)
            except KeyError:
                continue
            if not s["x"]:
                continue
            x, v = s["x"], s["values"]
            last, period = v[-1], x[-1]
            prev_label = f"{int(period[:4]) - 1}{period[4:]}"
            prev = dict(zip(x, v)).get(prev_label)
            change, change_unit = None, None
            if prev not in (None, 0):
                if VARIABLES[var]["unit"] in ("%", "p.p."):
                    change, change_unit = round(last - prev, 2), "p.p."
                else:
                    change, change_unit = round((last / prev - 1) * 100, 1), "%"
            meta = self.var_meta(var)
            out.append({"key": var, "label": meta["label"], "unit": meta["unit"], "value": last, "period": period,
                        "change": change, "change_unit": change_unit, "change_ref": prev_label,
                        "agg_label": s["agg_label"], "source": meta.get("source")})
        return out

    def ranking(self, var: str, period: str | None = None, n: int = 10) -> dict:
        period, vals = self.by_province(var, period)
        items = sorted(((c, v) for c, v in vals.items() if v is not None), key=lambda t: -t[1])[:n]
        return {"period": period, "labels": [province_name(c) for c, _ in items], "values": [v for _, v in items]}

    def quality(self) -> dict:
        d = self.load()
        df = d.df
        return {
            "source": d.source_label,
            "is_legacy": d.is_legacy,
            "rows": int(len(df)),
            "provinces": int(df["prov_code"].nunique()),
            "periods": int(df["period"].nunique()),
            "first_period": df["period"].min(),
            "last_period": df["period"].max(),
            "missing": [{"variable": VARIABLES[v]["label"], "key": v, "nan": int(df[v].isna().sum()),
                         "pct": round(float(df[v].isna().mean() * 100), 2)}
                        for v in VARIABLES if v in df.columns],
        }
