"""Construcción de los paneles v2 a partir de staging (sin red).

Salidas (data/processed/):
- panel_trimestral.csv  clave (prov_code, period): variables con referencia mensual/trimestral. Las variables
  autonómicas (IPC, IPV) y nacionales (tipos, costes, ahorro) se repiten por provincia y su ámbito se declara
  en el diccionario (geo_level).
- panel_anual.csv       clave (prov_code, year): variables anuales SIN repetir ni interpolar.
- panel_modelado.csv    vista: trimestral + anual según regla de disponibilidad (``<var>_ref_year``).
- nacional_trimestral.csv agregados nacionales (totales oficiales del INE cuando existen).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import config
from src.common.geography import CCAA, PROVINCES

from . import temporal

PROV_CODES = sorted(PROVINCES)


def _prov_frame(periods: list[str]) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product([PROV_CODES, periods], names=["prov_code", "period"]).to_frame(index=False)
    idx["provincia"] = idx["prov_code"].map(lambda c: PROVINCES[c].name)
    idx["ccaa_code"] = idx["prov_code"].map(lambda c: PROVINCES[c].ccaa_code)
    idx["quarter_start"] = idx["period"].map(lambda p: pd.Period(p, freq="Q").start_time.strftime("%Y-%m-%d"))
    return idx


def quarterly_long(staging: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Todas las variables a frecuencia trimestral en formato largo (variable, geo_level, geo_code, period, value)."""
    parts = []
    for key, df in staging.items():
        spec = config.DATASET_BY_KEY[key]
        for vs in spec.variables:
            d = df[df["variable"] == vs.name]
            if d.empty:
                continue
            if vs.agg_q == "annual":
                continue
            if spec.freq == "M":
                parts.append(temporal.monthly_to_quarterly(d, vs.agg_q))
            else:
                parts.append(temporal.quarterly_obs(d))
    q = pd.concat(parts, ignore_index=True)
    # derivadas nacionales
    w = q[q["geo_level"].isin(["nacional", "zona_euro"])].pivot_table(index="period", columns="variable", values="value")
    for name, (expr, _, _) in config.DERIVED.items():
        a, b = [s.strip() for s in expr.split("-")]
        if a in w and b in w:
            s = (w[a] - w[b]).dropna()
            q = pd.concat([q, pd.DataFrame({"variable": name, "geo_level": "nacional", "geo_code": "00",
                                            "period": s.index, "value": s.values})], ignore_index=True)
    return q


def build_panel_trimestral(q: pd.DataFrame, start: str = config.PERIOD_START) -> pd.DataFrame:
    prov = q[q["geo_level"] == "provincia"]
    last = prov["period"].max()
    periods = [f"{p.year}Q{p.quarter}" for p in pd.period_range(start, last, freq="Q")]
    base = _prov_frame(periods)
    # provinciales
    wp = prov.pivot_table(index=["geo_code", "period"], columns="variable", values="value").reset_index()
    wp = wp.rename(columns={"geo_code": "prov_code"})
    out = base.merge(wp, on=["prov_code", "period"], how="left")
    # autonómicas → provincias de la CCAA
    cc = q[q["geo_level"] == "ccaa"]
    if not cc.empty:
        wc = cc.pivot_table(index=["geo_code", "period"], columns="variable", values="value").reset_index()
        wc = wc.rename(columns={"geo_code": "ccaa_code"})
        out = out.merge(wc, on=["ccaa_code", "period"], how="left")
    # nacionales / zona euro → todas las provincias
    na = q[q["geo_level"].isin(["nacional", "zona_euro"])]
    na = na[~na["variable"].isin(prov["variable"].unique()) & ~na["variable"].isin(cc["variable"].unique())]
    wn = na.pivot_table(index="period", columns="variable", values="value").reset_index()
    out = out.merge(wn, on="period", how="left")
    return out.sort_values(["prov_code", "period"]).reset_index(drop=True)


def build_panel_anual(staging: dict[str, pd.DataFrame], start_year: int = 2002) -> pd.DataFrame:
    parts = []
    for key, df in staging.items():
        spec = config.DATASET_BY_KEY[key]
        for vs in spec.variables:
            if vs.agg_q != "annual":
                continue
            d = df[(df["variable"] == vs.name) & (df["geo_level"] == "provincia")]
            if spec.freq == "S":
                a = temporal.stock_at_january(d)
            else:
                a = d.assign(year=pd.to_datetime(d["ref_date"]).dt.year)[["variable", "geo_level", "geo_code", "year", "value", "status"]]
            parts.append(a)
    a = pd.concat(parts, ignore_index=True)
    last = int(a["year"].max())
    base = pd.MultiIndex.from_product([PROV_CODES, range(start_year, last + 1)], names=["prov_code", "year"]).to_frame(index=False)
    base["provincia"] = base["prov_code"].map(lambda c: PROVINCES[c].name)
    base["ccaa_code"] = base["prov_code"].map(lambda c: PROVINCES[c].ccaa_code)
    w = a.pivot_table(index=["geo_code", "year"], columns="variable", values="value").reset_index().rename(columns={"geo_code": "prov_code"})
    st = a.pivot_table(index=["geo_code", "year"], columns="variable", values="status", aggfunc="first").reset_index()
    st = st.rename(columns={"geo_code": "prov_code"}).rename(columns=lambda c: c if c in ("prov_code", "year") else f"{c}_status")
    return base.merge(w, on=["prov_code", "year"], how="left").merge(st, on=["prov_code", "year"], how="left")


def build_panel_modelado(pt: pd.DataFrame, pa: pd.DataFrame) -> pd.DataFrame:
    out = pt.copy()
    qend = pd.PeriodIndex(out["period"], freq="Q").end_time.normalize()
    ann = pa.set_index(["prov_code", "year"])
    for var, lag in temporal.AVAILABILITY_LAG_MONTHS.items():
        if var not in pa.columns:
            continue
        ref_year = np.array([temporal.available_ref_year(e, lag) for e in qend])
        # si el año disponible no existe en el panel anual (p.ej. aún no publicado), se busca el último con dato
        series = pa.dropna(subset=[var]).groupby("prov_code")
        last_by_prov = series["year"].max().to_dict()
        ry = np.array([min(y, last_by_prov.get(p, y)) for p, y in zip(out["prov_code"], ref_year)])
        out[f"{var}_ref_year"] = ry
        out[var] = [ann[var].get((p, y), np.nan) for p, y in zip(out["prov_code"], ry)]
    return out


def build_nacional(q: pd.DataFrame, pt: pd.DataFrame, staging: dict[str, pd.DataFrame]) -> pd.DataFrame:
    na = q[q["geo_level"].isin(["nacional", "zona_euro"])]
    w = na.pivot_table(index="period", columns="variable", values="value")
    # suma de provincias (reconciliación) para flujos
    for v in ["hipotecas_viviendas_num", "hipotecas_fincas_total_num", "hipotecas_viviendas_importe", "compraventas_viviendas_num"]:
        if v in pt:
            s = pt.groupby("period")[v].sum(min_count=52)
            w[f"{v}_suma_prov"] = s
    # población nacional (ECP) en la fecha de stock más reciente <= inicio del trimestre (sin interpolar)
    pop = staging.get("ine_ecp_poblacion")
    if pop is not None:
        p = pop[(pop["variable"] == "poblacion") & (pop["geo_level"] == "nacional")].copy()
        p["ref_date"] = pd.to_datetime(p["ref_date"]).astype("datetime64[ns]")
        p = p.sort_values("ref_date")
        qs = pd.DataFrame({"period": w.index, "qs": pd.PeriodIndex(w.index, freq="Q").start_time.astype("datetime64[ns]")})
        m = pd.merge_asof(qs.sort_values("qs"), p[["ref_date", "value"]], left_on="qs", right_on="ref_date")
        w["poblacion_ecp"] = m.set_index("period")["value"]
        w["poblacion_ecp_fecha"] = m.set_index("period")["ref_date"].dt.strftime("%Y-%m-%d")
        if "pib_nominal_meur" in w:
            w["pib_pc_trimestral_eur"] = w["pib_nominal_meur"] * 1e6 / w["poblacion_ecp"]
    # medias ponderadas por población (1-ene del año, ECP provincial) de variables provinciales de nivel
    pa_pop = staging.get("ine_ecp_poblacion")
    if pa_pop is not None and "precio_m2_tinsa" in pt:
        a = temporal.stock_at_january(pa_pop[(pa_pop["variable"] == "poblacion") & (pa_pop["geo_level"] == "provincia")])
        wts = a.set_index(["geo_code", "year"])["value"]
        d = pt[["prov_code", "period", "precio_m2_tinsa"]].dropna().copy()
        d["year"] = d["period"].str[:4].astype(int)
        d["w"] = [wts.get((c, y), np.nan) for c, y in zip(d["prov_code"], d["year"])]
        d = d.dropna()
        g = d.groupby("period")
        w["precio_m2_tinsa_pond_pob"] = g.apply(lambda x: np.average(x["precio_m2_tinsa"], weights=x["w"]) if len(x) == 52 else np.nan)
    w = w.reset_index()
    first = config.PERIOD_START
    return w[w["period"] >= "2002Q1"].sort_values("period").reset_index(drop=True)
