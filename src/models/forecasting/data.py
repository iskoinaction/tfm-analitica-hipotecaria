"""Entradas del forecasting v2.

Orden de preferencia:
  1. v2 de Data Engineering: ``data/processed/panel_trimestral.csv`` (+ ``panel_anual.csv``, ``nacional_trimestral.csv``).
  2. PROVISIONAL (solo desarrollo): dataset v1 para las explicativas + INE tabla 3200 (Estadística de Hipotecas,
     número de hipotecas sobre VIVIENDAS y sobre TOTAL FINCAS, mensual por provincia) descargada de la API
     Tempus3 y cacheada con hash en ``artifacts/demand/inputs``. Evita el error de parseo de miles del v1.

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
    "precio": ([r"(precio|tinsa)"], [r"ipv", r"tasad", r"mivau", r"mitma", r"var", r"lag", r"simple"]),
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


# ------------------------------------------------------------------------------------------ INE 3200
def fetch_ine_3200(force: bool = False) -> Path:
    """Descarga (una vez) la tabla INE 3200 y guarda solo 'Número de hipotecas' de Viviendas y Total fincas."""
    C.INPUT_CACHE.mkdir(parents=True, exist_ok=True)
    out = C.INPUT_CACHE / "ine_3200_numero_hipotecas.json"
    if out.exists() and not force:
        return out
    import requests
    r = requests.get(C.INE_3200_URL, timeout=600)
    r.raise_for_status()
    sel = [s for s in r.json()
           if s["Nombre"].startswith(("Total fincas. Número de hipotecas.", "Viviendas. Número de hipotecas."))]
    payload = {"source": C.INE_3200_URL, "downloaded": dt.datetime.now().isoformat(timespec="seconds"),
               "series": sel}
    out.write_text(json.dumps(payload, ensure_ascii=False))
    return out


def ine_3200_quarterly(path: Path) -> pd.DataFrame:
    """INE 3200 -> trimestral (solo trimestres completos). Columnas prov_code ('00' = nacional), period, hip_viv, hip_tot."""
    d = json.loads(Path(path).read_text())
    rows = []
    for s in d["series"]:
        parts = [p.strip() for p in s["Nombre"].split(".")]
        kind = "hip_viv" if parts[0] == "Viviendas" else "hip_tot"
        area = parts[2]
        code = "00" if area == "Total Nacional" else province_code(area)
        for o in s["Data"]:
            if o.get("Valor") is None:
                continue
            rows.append((kind, code, int(o["Anyo"]), int(o["FK_Periodo"]), float(o["Valor"])))
    m = pd.DataFrame(rows, columns=["kind", "prov_code", "y", "m", "v"])
    m = m[m.m.between(1, 12)]
    m["period"] = pd.PeriodIndex([pd.Period(year=a, quarter=(b - 1) // 3 + 1, freq="Q-DEC") for a, b in zip(m.y, m.m)])
    g = m.groupby(["kind", "prov_code", "period"])["v"].agg(["sum", "count"]).reset_index()
    g = g[g["count"] == 3]
    return g.pivot_table(index=["prov_code", "period"], columns="kind", values="sum").reset_index()


# ------------------------------------------------------------------------------------------ cargas
def _load_provisional() -> Inputs:
    v1 = pd.read_csv(C.V1_DATASET)
    v1["prov_code"] = v1.Provincia.map(province_code)
    v1["period"] = pd.PeriodIndex(pd.to_datetime(v1.Trimestre), freq="Q-DEC")
    ren = {"Precio_m2": "precio", "Tasa_Paro": "paro", "Euribor": "euribor", "IPC": "ipc",
           "Transmisiones_Total": "transmisiones", "Poblacion": "poblacion", "Pob_Ext": "pob_ext", "PIB_pc": "pib_pc"}
    panel = v1[["prov_code", "period", *ren]].rename(columns=ren)
    ine_path = fetch_ine_3200()
    ine = ine_3200_quarterly(ine_path)
    prov_ine = ine[ine.prov_code != "00"]
    panel = panel.merge(prov_ine, on=["prov_code", "period"], how="outer")  # INE puede llegar más allá de 2025Q4
    panel = panel.sort_values(["prov_code", "period"]).reset_index(drop=True)
    annual = _annual_from_replicated(v1.assign(year=v1.period.dt.year).rename(columns=ren))
    nat_ine = ine[ine.prov_code == "00"].set_index("period")[["hip_viv", "hip_tot"]]
    national = _national_from_panel(panel, nat_ine)
    inputs = [{"path": _rel(C.V1_DATASET), "sha256": sha256(C.V1_DATASET)},
              {"path": _rel(ine_path), "sha256": sha256(ine_path), "url": C.INE_3200_URL,
               "downloaded": json.loads(ine_path.read_text())["downloaded"]}]
    notes = ["PROVISIONAL: explicativas del dataset v1 (Tinsa, EPA, BCE, INE) + hipotecas INE tabla 3200 (viviendas y "
             "total fincas, número) descargadas de la API; reemplazar por data/processed v2 cuando exista.",
             "PIB_pc, Poblacion y Pob_Ext se usan ANUALES (un valor por provincia y año; el v1 los replicaba en 4 trimestres)."]
    return Inputs(panel, annual, national, "provisional_v1+INE3200", inputs, notes)


def _annual_from_replicated(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (pc, y), g in df.groupby(["prov_code", "year"]):
        rec = {"prov_code": pc, "year": int(y)}
        for v in ("pib_pc", "poblacion", "pob_ext"):
            vals = g[v].dropna().unique()
            rec[v] = float(vals[0]) if len(vals) >= 1 else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def _national_from_panel(panel: pd.DataFrame, nat_hip: pd.DataFrame | None) -> pd.DataFrame:
    g = panel.groupby("period")
    w = panel["poblacion"]
    out = pd.DataFrame({
        "transmisiones": g["transmisiones"].sum(min_count=52),
        "euribor": g["euribor"].mean(),
        "precio": panel.assign(x=panel.precio * w).groupby("period")["x"].sum(min_count=52) / g["poblacion"].sum(min_count=52),
        "paro": panel.assign(x=panel.paro * w).groupby("period")["x"].sum(min_count=52) / g["poblacion"].sum(min_count=52),
        "ipc": panel.assign(x=panel.ipc * w).groupby("period")["x"].sum(min_count=52) / g["poblacion"].sum(min_count=52),
        "poblacion": g["poblacion"].sum(min_count=52),
    })
    hv = g["hip_viv"].sum(min_count=52) if "hip_viv" in panel else None
    ht = g["hip_tot"].sum(min_count=52) if "hip_tot" in panel else None
    if nat_hip is not None and len(nat_hip):
        out = out.join(nat_hip, how="outer")
    else:
        out["hip_viv"], out["hip_tot"] = hv, ht
    out.index = pd.PeriodIndex(out.index, freq="Q-DEC")
    return out.sort_index()


V2_PANEL_COLS = {"hip_viv": "hipotecas_viviendas_num", "hip_tot": "hipotecas_fincas_total_num",
                 "precio": "precio_m2_mivau_tasado", "precio_tinsa": "precio_m2_tinsa", "paro": "tasa_paro", "euribor": "euribor_12m", "ipc": "ipc_var_anual",
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
             "viviendas INE, precio m2 = valor tasado MIVAU (Tinsa solo como legado), EPA (paro nacional oficial en el agregado), BCE (Euribor 12M), IPC INE.",
             "Variables anuales (PIB_pc, poblacion, poblacion extranjera) desde panel_anual.csv, sin replicar."]
    return Inputs(panel, annual, national, "v2", inputs, notes)


def load_inputs(prefer: str = "auto", colmap: dict | None = None) -> Inputs:
    """prefer: 'auto' (v2 si existe), 'v2' (obligatorio) o 'provisional'."""
    if prefer in ("auto", "v2") and C.PANEL_V2.exists():
        return _load_v2(colmap)
    if prefer == "v2":
        raise FileNotFoundError(C.PANEL_V2)
    return _load_provisional()


def province_names() -> dict:
    return {c: p.name for c, p in PROVINCES.items()}
