"""Entradas del forecasting v2.

Fuente: pipeline de datos v2, ``data/processed/panel_trimestral.csv`` (+ ``panel_anual.csv``, ``nacional_trimestral.csv``).

Salida común (:class:`Inputs`):
  ``panel``  trimestral: prov_code, period (Period Q-DEC) y variables canónicas
  ``annual`` anual sin replicar: prov_code, year, pib_pc, poblacion, pob_ext
  ``national`` trimestral nacional (índice Period)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.geography import PROVINCES, province_code
from src.models.econometrics.data import resolve_columns, to_period
from . import config as C

CANON_Q = ["hip_viv", "hip_tot", "precio", "paro", "euribor", "ipc", "transmisiones", "poblacion", "pob_ext", "pib_pc"]

PANEL_RULES = {
    "prov_code": ([r"^(prov_code|cod_prov|codigo_provincia)$"], []),
    "period": ([r"^(period|periodo|trimestre|quarter)$"], []),
    "hip_viv": ([r"hipotec", r"viv"], [r"importe", r"impor", r"_eur", r"tasa", r"var", r"medio", r"lag", r"_sa$"]),
    "hip_tot": ([r"hipotec", r"(total|fincas)"], [r"viv", r"importe", r"impor", r"tasa", r"var", r"medio", r"lag", r"_sa$"]),
    "precio": ([r"(tasad|mivau)"], [r"ipv", r"var", r"lag"]),
    "paro": ([r"paro"], [r"var", r"lag", r"nairu", r"parad"]),
    "euribor": ([r"euribor"], [r"var", r"diff", r"lag", r"3m"]),
    "ipc": ([r"^(ipc|iapc|hicp)"], [r"lag", r"indice_base"]),
    "transmisiones": ([r"(transmision|compraventa)"], [r"var", r"lag"]),
    "poblacion": ([r"^poblacion"], [r"ext", r"var"]),
    "pob_ext": ([r"(pob_ext|extranj)"], [r"var", r"ratio"]),
    "pib_pc": ([r"pib", r"(pc|per_capita|percapita)"], [r"var", r"tasa", r"lag", r"real"]),
}
ANNUAL_RULES = {
    "prov_code": PANEL_RULES["prov_code"],
    "year": ([r"^(year|anio|ano|anyo|periodo|period)$"], []),
    "pib_pc": PANEL_RULES["pib_pc"], "poblacion": PANEL_RULES["poblacion"], "pob_ext": PANEL_RULES["pob_ext"],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(C.ROOT))
    except ValueError:
        return str(p)


@dataclass
class Inputs:
    panel: pd.DataFrame
    annual: pd.DataFrame
    national: pd.DataFrame
    source: str
    inputs: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def metadata(self) -> dict:
        return {"source": self.source, "inputs": self.inputs, "notes": self.notes,
                "panel_period_range": [str(self.panel.period.min()), str(self.panel.period.max())],
                "national_period_range": [str(self.national.index.min()), str(self.national.index.max())]}


V2_PANEL_COLS = {"hip_viv": "hipotecas_viviendas_num", "hip_tot": "hipotecas_fincas_total_num",
                 "precio": "precio_m2_mivau_tasado", "paro": "tasa_paro", "euribor": "euribor_12m", "ipc": "ipc_var_anual",
                 "transmisiones": "compraventas_viviendas_num"}
V2_ANNUAL_COLS = {"pib_pc": "pib_pc", "poblacion": "poblacion", "pob_ext": "poblacion_extranjera"}
V2_NATIONAL_COLS = {"hip_viv": "hipotecas_viviendas_num", "hip_tot": "hipotecas_fincas_total_num",
                    "precio": "precio_m2_mivau_tasado", "paro": "tasa_paro", "euribor": "euribor_12m",
                    "ipc": "ipc_var_anual", "transmisiones": "compraventas_viviendas_num", "poblacion": "poblacion_ecp"}


def _load_v2(colmap: dict | None = None) -> Inputs:
    """v2 de Data Engineering (esquema de data/metadata/data_dictionary.csv; mapeo explícito, sin heurísticas)."""
    df = pd.read_csv(C.PANEL_V2, dtype={"prov_code": str})
    cm = colmap or V2_PANEL_COLS
    panel = pd.DataFrame({"prov_code": df["prov_code"].astype(str).str.zfill(2), "period": to_period(df["period"])})
    for k, c in cm.items():
        if c in df.columns:
            panel[k] = pd.to_numeric(df[c], errors="coerce").values
    da = pd.read_csv(C.PANEL_ANUAL_V2, dtype={"prov_code": str})
    annual = pd.DataFrame({"prov_code": da["prov_code"].astype(str).str.zfill(2), "year": da["year"].astype(int)})
    for k, c in V2_ANNUAL_COLS.items():
        annual[k] = pd.to_numeric(da[c], errors="coerce").values
    pop = annual.set_index(["prov_code", "year"])["poblacion"]
    panel["poblacion"] = [pop.get((p, y), np.nan) for p, y in zip(panel.prov_code, panel.period.dt.year)]
    panel = panel[panel.prov_code.isin(PROVINCES)].sort_values(["prov_code", "period"]).reset_index(drop=True)
    dn = pd.read_csv(C.NATIONAL_V2)
    national = pd.DataFrame(index=to_period(dn["period"]))
    for k, c in V2_NATIONAL_COLS.items():
        if c in dn.columns:
            national[k] = pd.to_numeric(dn[c], errors="coerce").values
    national = national[~national.index.duplicated()].sort_index()
    inputs = [{"path": _rel(p), "sha256": sha256(p)} for p in (C.PANEL_V2, C.PANEL_ANUAL_V2, C.NATIONAL_V2)]
    inputs[0]["colmap"], inputs[1]["colmap"], inputs[2]["colmap"] = cm, V2_ANNUAL_COLS, V2_NATIONAL_COLS
    notes = ["v2 (Data Engineering): hipotecas INE (viviendas y total fincas, parseo correcto), compraventas de "
             "viviendas INE, precio m2 = valor tasado MIVAU, EPA (paro nacional oficial en el agregado), BCE (Euribor 12M), IPC INE.",
             "Variables anuales (PIB_pc, poblacion, poblacion extranjera) desde panel_anual.csv, sin replicar."]
    return Inputs(panel, annual, national, "v2", inputs, notes)


def load_inputs(prefer: str = "auto", colmap: dict | None = None) -> Inputs:
    """prefer: 'auto' o 'v2' (ambos exigen el panel v2)."""
    if not C.PANEL_V2.exists():
        raise FileNotFoundError(C.PANEL_V2)
    return _load_v2(colmap)


def province_names() -> dict:
    return {c: p.name for c, p in PROVINCES.items()}
