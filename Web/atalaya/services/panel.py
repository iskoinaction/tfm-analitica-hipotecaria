"""Acceso de sólo lectura al panel trimestral provincial (datos observados, no modelos).

Orden de búsqueda (una única regla, sin depender del directorio de trabajo):
1. ``data/processed/panel_trimestral.parquet`` / ``.csv`` (panel maestro v2).
2. Sólo si ``ATALAYA_ALLOW_LEGACY_PANEL``: ``notebooks acabados/dataset_final_tfm.csv`` (v1),
   que la UI etiqueta siempre como "panel v1 (legado)".

Los agregados nacionales que se calculan aquí son estadísticas descriptivas explícitas
(suma o media simple de provincias), etiquetadas como tales; no son estimaciones de modelos.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .geo import province_code, province_name

# clave canónica -> (etiqueta, unidad, agregación nacional, nota de ámbito)
VARIABLES: dict[str, dict] = {
    "hipotecas_total": {"label": "Hipotecas sobre viviendas", "unit": "nº", "agg": "sum", "scope": "provincial"},
    "transmisiones_total": {"label": "Compraventas de viviendas", "unit": "nº", "agg": "sum", "scope": "provincial"},
    "precio_m2": {"label": "Precio vivienda", "unit": "€/m²", "agg": "mean", "scope": "provincial"},
    "euribor": {"label": "Euríbor 12 meses", "unit": "%", "agg": "first", "scope": "nacional"},
    "spread_hipotecas": {"label": "Diferencial hipotecario", "unit": "p.p.", "agg": "first", "scope": "nacional"},
    "tasa_paro": {"label": "Tasa de paro", "unit": "%", "agg": "mean", "scope": "provincial"},
    "ipc": {"label": "IPC (variación anual)", "unit": "%", "agg": "mean", "scope": "autonómico"},
    "pib_pc": {"label": "PIB per cápita", "unit": "€", "agg": "mean", "scope": "provincial (anual)"},
    "poblacion": {"label": "Población", "unit": "hab.", "agg": "sum", "scope": "provincial (anual)"},
    "pob_ext": {"label": "Población extranjera", "unit": "hab.", "agg": "sum", "scope": "provincial (anual)"},
    "edad_media": {"label": "Edad media", "unit": "años", "agg": "mean", "scope": "provincial (anual)"},
    "tasa_ahorro": {"label": "Tasa de ahorro de los hogares", "unit": "%", "agg": "first", "scope": "nacional"},
    "indice_materiales": {"label": "Índice coste materiales", "unit": "índice", "agg": "first", "scope": "nacional"},
    "indice_mano_obra": {"label": "Índice coste mano de obra", "unit": "índice", "agg": "first", "scope": "nacional"},
}
AGG_LABEL = {"sum": "suma de provincias", "mean": "media simple de provincias", "first": "serie nacional"}

_LEGACY_COLUMNS = {
    "Provincia": "provincia", "Trimestre": "trimestre", "Precio_m2": "precio_m2", "Euribor": "euribor",
    "tasa_ahorro": "tasa_ahorro", "Spread_Hipotecas": "spread_hipotecas", "Hipotecas_Total": "hipotecas_total",
    "Poblacion": "poblacion", "Edad_Media": "edad_media", "PIB_pc": "pib_pc",
    "Indice_Mano_Obra": "indice_mano_obra", "Indice_Materiales": "indice_materiales", "IPC": "ipc",
    "Tasa_Paro": "tasa_paro", "Pob_Ext": "pob_ext", "Transmisiones_Total": "transmisiones_total",
}


class PanelUnavailable(RuntimeError):
    pass


@dataclass
class PanelData:
    df: pd.DataFrame          # columnas: prov_code, period (YYYYQn), <variables>
    path: Path
    is_legacy: bool
    mtime: float

    @property
    def source_label(self) -> str:
        rel = self.path.name
        return f"Panel v1 (legado): {rel}" if self.is_legacy else f"Panel maestro v2: {rel}"


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns={c: _LEGACY_COLUMNS.get(c, c) for c in raw.columns})
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "prov_code" in df.columns:
        df["prov_code"] = df["prov_code"].astype(str).str.zfill(2)
    elif "provincia" in df.columns:
        df["prov_code"] = df["provincia"].map(province_code)
    else:
        raise PanelUnavailable("el panel no tiene 'prov_code' ni 'Provincia'")
    if "period" in df.columns:
        per = pd.PeriodIndex(df["period"].astype(str).str.replace("-", "", regex=False), freq="Q-DEC")
    elif "trimestre" in df.columns:
        per = pd.to_datetime(df["trimestre"]).dt.to_period("Q-DEC")
        per = pd.PeriodIndex(per)
    else:
        raise PanelUnavailable("el panel no tiene 'period' ni 'Trimestre'")
    df["period"] = [f"{p.year}Q{p.quarter}" for p in per]
    keep = ["prov_code", "period"] + [v for v in VARIABLES if v in df.columns]
    out = df[keep].copy()
    for v in keep[2:]:
        out[v] = pd.to_numeric(out[v], errors="coerce")
    return out.sort_values(["period", "prov_code"]).reset_index(drop=True)


class PanelService:
    def __init__(self, data_dir: Path, legacy_path: Path | None, allow_legacy: bool) -> None:
        self.candidates = [data_dir / "processed" / "panel_trimestral.parquet",
                           data_dir / "processed" / "panel_trimestral.csv"]
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
            raw = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
            self._data = PanelData(_normalize(raw), path, legacy, mtime)
            return self._data

    def available(self) -> bool:
        try:
            self.load()
            return True
        except (PanelUnavailable, OSError, ValueError, KeyError, ImportError):
            return False

    # ------------------------------------------------------------------ consultas
    def variables(self) -> list[dict]:
        df = self.load().df
        return [{"key": k, **{kk: vv for kk, vv in meta.items()}, "agg_label": AGG_LABEL[meta["agg"]]}
                for k, meta in VARIABLES.items() if k in df.columns]

    def _check_var(self, var: str) -> None:
        if var not in VARIABLES or var not in self.load().df.columns:
            raise KeyError(var)

    def national_series(self, var: str) -> dict:
        self._check_var(var)
        df = self.load().df
        agg = VARIABLES[var]["agg"]
        g = df.groupby("period")[var]
        if agg == "sum":
            s = g.sum(min_count=1)
            # sólo trimestres con las 52 provincias informadas (si no, la suma sería engañosa)
            s[g.count() < 52] = np.nan
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
        return period, {r.prov_code: (None if pd.isna(getattr(r, var)) else round(float(getattr(r, var)), 4))
                        for r in sub.itertuples()}

    def periods(self) -> list[str]:
        return sorted(self.load().df["period"].unique().tolist())

    def kpis(self) -> list[dict]:
        """Último dato y variación interanual de un conjunto de indicadores (datos observados)."""
        out = []
        for var in ["hipotecas_total", "precio_m2", "euribor", "tasa_paro"]:
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
            out.append({"key": var, "label": VARIABLES[var]["label"], "unit": VARIABLES[var]["unit"],
                        "value": last, "period": period, "change": change, "change_unit": change_unit,
                        "change_ref": prev_label, "agg_label": s["agg_label"]})
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
