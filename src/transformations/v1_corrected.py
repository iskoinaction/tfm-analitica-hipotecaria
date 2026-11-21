"""Dataset v1 con el parseo de ``Hipotecas_Total`` corregido (para comparaciones antes/después).

El CSV v1 ``Datos ya metidos/hipotecas_por_prov_men.csv`` guarda los miles como float truncado:
``"17.49"`` = 17.490, ``"1.041"`` = 1.041, ``"398.0"`` = 398. El notebook 3 solo trataba como miles el patrón
``\\.ddd$`` y leía ``"17.49"`` como 17,49. Aquí:

* ``a.b`` con ``b`` de 1-3 dígitos distinto de ``"0"`` → ``a*1000 + b`` rellenado a 3 dígitos.
* ``a.0`` → ``a`` (entero < 1.000), EXCEPTO si ``a < 10`` y la mediana mensual de la provincia supera 100
  (un ``"1.0"`` en Alicante es 1.000: valor ambiguo, se marca en el log de correcciones).

El resto de columnas del v1 se conserva byte a byte (mismo orden de filas y columnas).
"""
from __future__ import annotations

import re

import pandas as pd

from src.common import config
from src.common.geography import PROVINCES, province_code


def parse_v1_count(text: str) -> float:
    s = str(text).strip()
    if "," in s:  # formato español explícito
        return float(s.replace(".", "").replace(",", "."))
    m = re.fullmatch(r"(\d+)\.(\d{1,3})", s)
    if not m:
        return float(s)
    a, b = m.groups()
    if b == "0":
        return float(a)
    return float(int(a) * 1000 + int(b.ljust(3, "0")))


def nb3_limpiar_numero(val) -> float:
    """Réplica exacta de ``limpiar_numero`` del notebook 3 (para documentar el error)."""
    s = str(val).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.search(r"\.[0-9]{3}$", s):
        s = s.replace(".", "")
    return float(s)


def corrected_monthly(path=None) -> pd.DataFrame:
    h = pd.read_csv(path or config.V1_INPUTS / "hipotecas_por_prov_men.csv", sep=";", dtype=str)
    h["prov_code"] = h["Provincias"].map(province_code)
    h["v_nb3"] = h["Total"].map(nb3_limpiar_numero)
    h["v_fix"] = h["Total"].map(parse_v1_count)
    med = h.groupby("prov_code")["v_fix"].transform("median")
    amb = h["Total"].str.fullmatch(r"\d\.0") & (med > 100)
    h.loc[amb, "v_fix"] = h.loc[amb, "Total"].str[0].astype(float) * 1000
    h["ambiguous_x0"] = amb
    h["quarter"] = pd.PeriodIndex(h["Periodo"].str.replace("M", "-"), freq="M").asfreq("Q").start_time.strftime("%Y-%m-%d")
    return h


def build(out_dir=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    out_dir = out_dir or (config.PROCESSED / "v1_corrected")
    out_dir.mkdir(parents=True, exist_ok=True)
    v1 = pd.read_csv(config.V1_DATASET)
    h = corrected_monthly()
    q = h.groupby(["prov_code", "quarter"]).agg(fix=("v_fix", "sum"), nb3=("v_nb3", "sum"),
                                                 n_fixed=("v_fix", lambda s: 0), amb=("ambiguous_x0", "sum"))
    q["n_fixed"] = h.assign(d=h.v_fix != h.v_nb3).groupby(["prov_code", "quarter"])["d"].sum()
    legacy = {p.legacy_name: c for c, p in PROVINCES.items()}
    key = list(zip(v1["Provincia"].map(legacy), v1["Trimestre"]))
    new = pd.Series([q["fix"].get(k) for k in key], index=v1.index)
    chk = pd.Series([q["nb3"].get(k) for k in key], index=v1.index)
    # salvaguarda: lo que el v1 calculó debe coincidir con la réplica de limpiar_numero
    assert ((chk - v1["Hipotecas_Total"]).abs() < 1e-6).all(), "la réplica del parseo v1 no coincide con el dataset v1"
    out = v1.copy()
    out["Hipotecas_Total"] = new.values
    out.to_csv(out_dir / "dataset_final_tfm_v1fix.csv", index=False, encoding="utf-8")
    log = q[q["n_fixed"] > 0].reset_index()
    log["pct_change"] = (log["fix"] / log["nb3"] - 1) * 100
    log.rename(columns={"fix": "hipotecas_v1fix", "nb3": "hipotecas_v1"}).to_csv(
        out_dir / "correcciones_hipotecas.csv", index=False, encoding="utf-8")
    return out, log


if __name__ == "__main__":
    o, l = build()
    print(len(o), "filas;", len(l), "provincia-trimestres corregidos;", int(l["amb"].sum()), "valores ambiguos X.0")
