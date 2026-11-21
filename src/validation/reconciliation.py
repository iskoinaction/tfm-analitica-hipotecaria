"""Comparación entre versiones: snapshot nuevo vs anterior (staging) y panel v2 vs dataset v1."""
from __future__ import annotations

import numpy as np
import pandas as pd

KEY = ["variable", "geo_level", "geo_code", "ref_date"]


def diff_staging(old: pd.DataFrame | None, new: pd.DataFrame, tol: float = 1e-9) -> dict:
    """Cuenta observaciones nuevas, revisadas, eliminadas e iguales por variable."""
    if old is None or old.empty:
        return {v: {"new": int(n), "revised": 0, "removed": 0, "same": 0}
                for v, n in new.groupby("variable").size().items()}
    m = old[KEY + ["value"]].merge(new[KEY + ["value"]], on=KEY, how="outer", suffixes=("_old", "_new"), indicator=True)
    out = {}
    for v, g in m.groupby("variable"):
        both = g[g["_merge"] == "both"]
        rev = ~np.isclose(both["value_old"], both["value_new"], rtol=tol, atol=tol)
        out[v] = {"new": int((g["_merge"] == "right_only").sum()), "removed": int((g["_merge"] == "left_only").sum()),
                  "revised": int(rev.sum()), "same": int((~rev).sum())}
        if rev.any():
            ex = both[rev].head(3)
            out[v]["examples"] = [{"geo": r.geo_code, "ref": r.ref_date, "old": r.value_old, "new": r.value_new}
                                  for r in ex.itertuples()]
    return out


# Correspondencia v1 → v2 (columna v1, columna v2, comentario)
V1_TO_V2 = [
    ("Hipotecas_Total", "hipotecas_fincas_total_num", "v2 = total fincas desde la API (v1 corrupto por formato de miles)"),
    ("Transmisiones_Total", "compraventas_viviendas_num", "misma tabla ETDP (compraventas de viviendas); 2005-06 NaN en v2"),
    ("Tasa_Paro", "tasa_paro", "EPA"),
    ("IPC", "ipc_var_anual", "IPC CCAA, variación anual media"),
    ("Precio_m2", "precio_m2_tinsa", "Tinsa (mismo CSV)"),
    ("Euribor", "euribor_12m", "v1 = FM.Q (trimestral BCE); v2 = media de FM.M"),
    ("Spread_Hipotecas", "diferencial_tae_euribor", "TAE vivienda − Euríbor"),
    ("tasa_ahorro", "tasa_ahorro_hogares", "CTNFSI no ajustada"),
    ("Indice_Mano_Obra", "indice_mano_obra_construccion", "INE 8377"),
    ("Indice_Materiales", "indice_coste_construccion", "NO comparable: v1 = media de 14 subíndices; v2 = índice general Eurostat"),
    ("Poblacion", "poblacion", "v1 = Padrón (1-ene, repetido 4 trim.); v2 = ECP 1-ene (panel_modelado con regla de disponibilidad)"),
    ("Pob_Ext", "poblacion_extranjera", "v1 = Padrón + OPI (ruptura 2023); v2 = ECP homogénea"),
    ("Edad_Media", "edad_media", "INE 3199"),
    ("PIB_pc", "pib_pc", "CRE; v1 contiene 2024 imputado"),
]


def compare_v1_v2(v1: pd.DataFrame, v2_q: pd.DataFrame, v2_a: pd.DataFrame, legacy_to_code: dict) -> pd.DataFrame:
    """Compara el dataset v1 con los paneles v2 por variable (mismas provincia-trimestre o provincia-año)."""
    a = v1.copy()
    a["prov_code"] = a["Provincia"].map(legacy_to_code)
    q = pd.PeriodIndex(pd.to_datetime(a["Trimestre"]), freq="Q")
    a["period"] = [f"{p.year}Q{p.quarter}" for p in q]
    a["year"] = q.year
    rows = []
    for c1, c2, note in V1_TO_V2:
        annual = c2 in v2_a.columns and c2 not in v2_q.columns
        if annual:
            b = v2_a[["prov_code", "year", c2]]
            m = a.drop_duplicates(["prov_code", "year"])[["prov_code", "year", c1]].merge(b, on=["prov_code", "year"], how="inner")
        elif c2 in v2_q.columns:
            m = a[["prov_code", "period", c1]].merge(v2_q[["prov_code", "period", c2]], on=["prov_code", "period"], how="inner")
        else:
            rows.append({"v1": c1, "v2": c2, "nota": note, "n": 0})
            continue
        both = m.dropna(subset=[c1, c2])
        d = both[c2] - both[c1]
        rel = (d.abs() / both[c1].abs().replace(0, np.nan))
        rows.append({"v1": c1, "v2": c2, "frecuencia": "anual" if annual else "trimestral", "n_comparadas": len(both),
                     "solo_v1": int(m[c1].notna().sum() - len(both)), "solo_v2": int(m[c2].notna().sum() - len(both)),
                     "pct_iguales_0.5pct": round(float((rel <= 0.005).mean() * 100), 2) if len(both) else None,
                     "mediana_dif_rel_pct": round(float(rel.median() * 100), 3) if len(both) else None,
                     "max_dif_rel_pct": round(float(rel.max() * 100), 2) if len(both) else None,
                     "media_v1": round(float(both[c1].mean()), 4) if len(both) else None,
                     "media_v2": round(float(both[c2].mean()), 4) if len(both) else None, "nota": note})
    return pd.DataFrame(rows)
