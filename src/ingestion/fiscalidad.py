"""Fiscalidad: carga/validación de la tabla curada ``data/metadata/fiscalidad_vigencias.csv`` (propiedad del
agente de Banca; aquí NO se escribe ni se cambian tipos) y *watcher* de la API de legislación consolidada del BOE.

Watcher: para cada ``boe_id`` citado consulta
``https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{boe_id}/metadatos`` y compara
``fecha_actualizacion`` con ``fecha_verificacion`` de la tabla. Si la norma se ha actualizado después de la
verificación → "revisión fiscal requerida" en el informe de update_all.
"""
from __future__ import annotations

import pandas as pd

from src.common import config, http

TABLE = config.METADATA / "fiscalidad_vigencias.csv"
BOE_META = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{}/metadatos"
REQUIRED = ["ccaa_code", "impuesto", "vigente_desde", "vigente_hasta", "norma", "url_fuente", "verificado"]


def load(path=TABLE) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str)


def validate(df: pd.DataFrame) -> list[dict]:
    out = []
    miss = [c for c in REQUIRED if c not in df.columns]
    if miss:
        return [{"check": "fiscal_schema", "severity": "error", "target": "fiscalidad_vigencias", "detail": f"faltan {miss}", "n": None}]
    bad_v = ~df["verificado"].str.lower().isin(["true", "false"])
    if bad_v.any():
        out.append({"check": "fiscal_schema", "severity": "error", "target": "fiscalidad_vigencias",
                    "detail": f"{int(bad_v.sum())} filas con 'verificado' no booleano", "n": int(bad_v.sum())})
    d = df.copy()
    d["desde"] = pd.to_datetime(d["vigente_desde"], errors="coerce")
    d["hasta"] = pd.to_datetime(d["vigente_hasta"], errors="coerce")
    inv = d["desde"].notna() & d["hasta"].notna() & (d["hasta"] < d["desde"])
    if inv.any():
        out.append({"check": "fiscal_vigencia", "severity": "error", "target": "fiscalidad_vigencias",
                    "detail": f"{int(inv.sum())} filas con vigente_hasta < vigente_desde", "n": int(inv.sum())})
    keys = [c for c in ["ccaa_code", "impuesto", "ambito", "condicion"] if c in d.columns]
    n_ov = 0
    for _, g in d.groupby(keys, dropna=False):
        g = g.sort_values("desde")
        for a, b in zip(g.itertuples(), list(g.itertuples())[1:]):
            end_a = a.hasta if pd.notna(a.hasta) else pd.Timestamp.max
            if pd.notna(b.desde) and b.desde <= end_a:
                n_ov += 1
    if n_ov:
        out.append({"check": "fiscal_vigencia", "severity": "warning", "target": "fiscalidad_vigencias",
                    "detail": f"{n_ov} solapes de vigencia en la misma (CCAA, impuesto, ámbito, condición)", "n": n_ov})
    nv = int((df["verificado"].str.lower() == "false").sum())
    out.append({"check": "fiscal_verificacion", "severity": "info", "target": "fiscalidad_vigencias",
                "detail": f"{nv} de {len(df)} filas sin verificar", "n": nv})
    return out


def boe_watch(df: pd.DataFrame) -> list[dict]:
    """Devuelve, por norma, la fecha de última actualización consolidada del BOE y si requiere revisión."""
    res = []
    if "boe_id" not in df.columns:
        return res
    for bid, g in df.dropna(subset=["boe_id"]).groupby("boe_id"):
        fv = pd.to_datetime(g.get("fecha_verificacion"), errors="coerce").min()
        try:
            j, _ = http.get(BOE_META.format(bid), headers={"Accept": "application/json"}, retries=2)
            data = j.get("data") or [{}]
            fa = data[0].get("fecha_actualizacion")
            fa_ts = pd.to_datetime(fa[:8], format="%Y%m%d") if fa else None
            res.append({"boe_id": bid, "norma": g["norma"].iloc[0], "fecha_actualizacion_boe": str(fa_ts.date()) if fa_ts is not None else None,
                        "fecha_verificacion": str(fv.date()) if pd.notna(fv) else None,
                        "revision_requerida": bool(fa_ts is not None and (pd.isna(fv) or fa_ts > fv))})
        except http.HttpError as e:
            res.append({"boe_id": bid, "norma": g["norma"].iloc[0], "error": str(e)[:200], "revision_requerida": None})
    return res
