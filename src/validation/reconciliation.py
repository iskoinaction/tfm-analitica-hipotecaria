"""Comparación entre versiones: snapshot nuevo vs anterior (staging)."""
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

