"""Utilidades temporales: trimestre canónico ``YYYYQn`` y fecha de inicio de trimestre."""
from __future__ import annotations

import re

import pandas as pd


def to_quarter(value) -> pd.Period:
    """Convierte '2024-04-01', '2024Q2', '2024-Q2', '2024T2', '2024 2T', Timestamp... en Period[Q-DEC]."""
    if isinstance(value, pd.Period):
        return value.asfreq("Q-DEC")
    if isinstance(value, pd.Timestamp):
        return value.to_period("Q-DEC")
    s = str(value).strip()
    m = re.match(r"^(\d{4})\s*-?\s*[QqTt]\s*([1-4])$", s) or re.match(r"^(\d{4})\s*([1-4])\s*[Tt]$", s)
    if m:
        return pd.Period(year=int(m.group(1)), quarter=int(m.group(2)), freq="Q-DEC")
    return pd.Timestamp(s).to_period("Q-DEC")


def quarter_label(p) -> str:
    p = to_quarter(p)
    return f"{p.year}Q{p.quarter}"


def quarter_start(p) -> pd.Timestamp:
    return to_quarter(p).start_time.normalize()
