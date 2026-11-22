"""Features de demanda con información disponible en el origen.

Convención temporal (documentada en el informe):
  * Origen T = momento en que se publica el dato del trimestre T de hipotecas (INE H, ~2 meses tras el cierre de
    cada mes). En ese momento también se conocen: Euribor de T (BCE, diario), paro EPA de T (~4 semanas),
    precio (MIVAU valor tasado) de T y transmisiones de T (INE ETDP, ~2 meses).
  * NO se usa: Euribor/paro/precio del trimestre objetivo (salvo en el modelo *condicional*, que se declara como
    tal y en producción recibe la senda del escenario), PIB_pc/poblacion anuales del año en curso (publicación
    del INE muy posterior), ni ninguna variable contemporánea al objetivo.
  * h = 1 equivale a un *nowcast* del trimestre en curso (T+1), cuya publicación llega ~5 meses después de T.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def national_frame(national: pd.DataFrame, target: str) -> pd.DataFrame:
    """Serie objetivo + exógenas nacionales en un único frame trimestral contiguo (desde 2005Q1)."""
    f = pd.DataFrame({"y": national[target]})
    for c in ("euribor", "paro", "precio", "transmisiones", "ipc"):
        f[c] = national[c] if c in national else np.nan
    f = f.loc[f["y"].first_valid_index(): f["y"].last_valid_index()]
    f["paro_ma4"] = f["paro"].rolling(4).mean()
    return f


def origin_features(f: pd.DataFrame, i: int) -> dict | None:
    """Features con información <= posición i. None si falta algo."""
    if i < 5:
        return None
    y = f["y"].values
    ly = np.log(y)
    try:
        out = {
            "dly0": ly[i] - ly[i - 1], "dly1": ly[i - 1] - ly[i - 2], "dly2": ly[i - 2] - ly[i - 3],
            "dly3": ly[i - 3] - ly[i - 4], "d4ly": ly[i] - ly[i - 4], "d4ly_prev": ly[i - 1] - ly[i - 5],
            "gap_ma4": ly[i] - np.log(np.mean(y[i - 3:i + 1])),
            "euribor": f["euribor"].iat[i], "d4eur": f["euribor"].iat[i] - f["euribor"].iat[i - 4],
            "paro": f["paro"].iat[i], "d4paro": f["paro"].iat[i] - f["paro"].iat[i - 4],
            "d4lprecio": np.log(f["precio"].iat[i] / f["precio"].iat[i - 4]),
            "d4ltrans": np.log(f["transmisiones"].iat[i] / f["transmisiones"].iat[i - 4]),
            "l_hip_trans": np.log(y[i] / f["transmisiones"].iat[i]),
        }
    except (IndexError, ZeroDivisionError):
        return None
    if not np.all(np.isfinite(list(out.values()))):
        return None
    return out


def add_target_quarter(d: dict, period: pd.Period) -> dict:
    d = dict(d)
    for k in (2, 3, 4):
        d[f"q{k}"] = int(period.quarter == k)
    return d
