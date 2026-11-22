"""Estimador de tipo de MERCADO (no oferta personalizada) y escenarios de tipos para años futuros.

Datos:
- Panel nacional de Data Engineering ``data/processed/nacional_trimestral.csv`` (euribor_12m, tae_vivienda = APRC,
  tedr_vivienda = tipo efectivo sin comisiones; BCE MIR/FM). Ruta parametrizable.
- Serie complementaria del asesor ``artifacts/advisor/ecb_tedr_variable_mensual.csv`` (TEDR de nuevas operaciones a
  tipo flotante o fijación inicial <= 1 año, BCE MIR ``M.ES.B.A2C.F.R.A.2250.EUR.N``), que no está en el panel.
  Se regenera con ``python -m src.advisor.market --refresh``.
- Escenarios futuros: ``artifacts/forecasting/rate_scenarios.csv`` si existe (columnas period/year, escenario,
  euribor_12m [, diferencial]); si no, ``data/metadata/escenarios_macro.yaml`` (euribor_12m.base + sensibilidades).

El estimador devuelve el ÚLTIMO dato publicado y el rango [mín, máx] de los últimos ``ventana`` trimestres.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
PANEL_CSV = ROOT / "data" / "processed" / "nacional_trimestral.csv"
TEDR_VAR_CSV = ROOT / "artifacts" / "advisor" / "ecb_tedr_variable_mensual.csv"
SCEN_CSV = ROOT / "artifacts" / "forecasting" / "rate_scenarios.csv"
SCEN_YAML = ROOT / "data" / "metadata" / "escenarios_macro.yaml"

SERIES_INFO = {
    "tae_vivienda": ("TAE (APRC) media de nuevas operaciones de préstamo para vivienda, España", "BCE MIR M.ES.B.A2C.A.C.A.2250.EUR.N"),
    "tedr_vivienda": ("TEDR (tipo sin comisiones) medio, nuevas operaciones de vivienda, todas las fijaciones, España", "BCE MIR M.ES.B.A2C.A.R.A.2250.EUR.N"),
    "tedr_variable": ("TEDR medio, nuevas operaciones de vivienda a tipo flotante o fijación inicial <= 1 año, España", "BCE MIR M.ES.B.A2C.F.R.A.2250.EUR.N"),
    "euribor_12m": ("Euríbor a 12 meses, media del periodo", "BCE FM M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA"),
}
ECB_TEDR_VAR_URL = ("https://data-api.ecb.europa.eu/service/data/MIR/M.ES.B.A2C.F.R.A.2250.EUR.N"
                    "?format=csvdata&startPeriod=2003-01&detail=dataonly")


def load_market(panel_path: str | Path | None = None, tedr_var_path: str | Path | None = None) -> pd.DataFrame:
    """DataFrame trimestral indexado por 'YYYYQn' con euribor_12m, tae_vivienda, tedr_vivienda, tedr_variable."""
    p = Path(panel_path) if panel_path else PANEL_CSV
    if not p.exists():
        raise FileNotFoundError(f"No existe el panel de tipos: {p}")
    d = pd.read_csv(p, usecols=lambda c: c in ("period", "euribor_12m", "tae_vivienda", "tedr_vivienda"))
    d = d.set_index("period").sort_index()
    v = Path(tedr_var_path) if tedr_var_path else TEDR_VAR_CSV
    if v.exists():
        m = pd.read_csv(v)
        m["period"] = pd.PeriodIndex(pd.to_datetime(m["mes"]), freq="Q").astype(str)
        q = m.groupby("period")["tedr_variable"].mean()
        d = d.join(q, how="left")
    else:
        d["tedr_variable"] = float("nan")
    return d


def _stat(s: pd.Series, ventana: int) -> dict | None:
    s = s.dropna()
    if s.empty:
        return None
    w = s.iloc[-ventana:]
    return {"ultimo": round(float(s.iloc[-1]), 4), "periodo_ultimo": str(s.index[-1]),
            "min": round(float(w.min()), 4), "max": round(float(w.max()), 4),
            "ventana": f"{w.index[0]}–{w.index[-1]}"}


def market_reference(tipo: str, market: pd.DataFrame, ventana: int = 4) -> dict:
    """Referencia de mercado del TIN para 'fijo' | 'variable' | 'mixto'."""
    eur = _stat(market["euribor_12m"], ventana)
    tae = _stat(market["tae_vivienda"], ventana)
    tedr = _stat(market["tedr_vivienda"], ventana)
    var = _stat(market["tedr_variable"], ventana)
    out = {"euribor_12m": eur, "tae_media_mercado": tae, "tedr_medio_todas_fijaciones": tedr,
           "tedr_medio_variable": var, "fuentes": {k: {"descripcion": a, "serie": b} for k, (a, b) in SERIES_INFO.items()},
           "naturaleza": "media de mercado publicada (no es una oferta personalizada)"}
    if tipo == "fijo" or tipo == "mixto":
        out["tin_referencia"] = tedr["ultimo"]
        out["tin_rango"] = [tedr["min"], tedr["max"]]
        out["metodo"] = "TEDR medio de nuevas operaciones de vivienda (todas las fijaciones), último trimestre publicado"
    if tipo in ("variable", "mixto"):
        if var:
            joined = market[["tedr_variable", "euribor_12m"]].dropna()
            dif = (joined["tedr_variable"] - joined["euribor_12m"]).iloc[-ventana:]
            out["diferencial_referencia"] = round(float(dif.mean()), 4)
            out["diferencial_rango"] = [round(float(dif.min()), 4), round(float(dif.max()), 4)]
            out["metodo_diferencial"] = ("media de (TEDR variable − Euríbor 12M) en la ventana; proxy del diferencial "
                                         "medio de mercado, que incluye el periodo inicial fijo <= 1 año")
        else:
            joined = market[["tedr_vivienda", "euribor_12m"]].dropna()
            dif = (joined["tedr_vivienda"] - joined["euribor_12m"]).iloc[-ventana:]
            out["diferencial_referencia"] = round(float(dif.mean()), 4)
            out["diferencial_rango"] = [round(float(dif.min()), 4), round(float(dif.max()), 4)]
            out["metodo_diferencial"] = "media de (TEDR todas las fijaciones − Euríbor 12M): proxy débil (serie variable no disponible)"
        if tipo == "variable":
            out["tin_referencia"] = round(eur["ultimo"] + out["diferencial_referencia"], 4)
            out["tin_rango"] = [round(eur["ultimo"] + out["diferencial_rango"][0], 4),
                                round(eur["ultimo"] + out["diferencial_rango"][1], 4)]
            out["metodo"] = "Euríbor 12M del último trimestre + diferencial de referencia"
    return out


def load_scenarios(scen_csv: str | Path | None = None, scen_yaml: str | Path | None = None) -> dict:
    """{año(str): {escenario: euribor_12m}} con metadatos de fuente."""
    c = Path(scen_csv) if scen_csv else SCEN_CSV
    if c.exists():
        d = pd.read_csv(c)
        ycol = "year" if "year" in d.columns else "period"
        d["y"] = d[ycol].astype(str).str[:4]
        tab = d.groupby(["y", "escenario"])["euribor_12m"].mean().unstack()
        return {"fuente": str(c.relative_to(ROOT)) if c.is_relative_to(ROOT) else str(c),
                "valores": {y: {k: round(float(v), 4) for k, v in r.dropna().items()} for y, r in tab.iterrows()}}
    y = Path(scen_yaml) if scen_yaml else SCEN_YAML
    cfg = yaml.safe_load(open(y, encoding="utf-8"))["euribor_12m"]
    sens = cfg.get("sensibilidades", {})
    vals = {}
    for k, v in cfg["base"].items():
        k = str(k)
        if "Q" in k:
            continue
        adv = sens.get("adverso", {}).get("desde_2027", 0.0)
        fav = sens.get("favorable", {}).get("desde_2027", 0.0)
        vals[k[:4]] = {"base": float(v), "adverso": round(float(v) + adv, 4), "favorable": round(float(v) + fav, 4)}
    return {"fuente": str(y.relative_to(ROOT)), "valores": vals,
            "nota": "Euríbor 12M; escenario base = supuestos BCE/CE documentados en el YAML; adverso/favorable = sensibilidades (supuesto)"}


def refresh_tedr_variable(out: Path = TEDR_VAR_CSV) -> Path:
    import requests
    r = requests.get(ECB_TEDR_VAR_URL, timeout=120, headers={"User-Agent": "atalaya-advisor/2.0 (academico)"})
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text))[["TIME_PERIOD", "OBS_VALUE"]]
    d.columns = ["mes", "tedr_variable"]
    out.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(out, index=False)
    meta = {"url": ECB_TEDR_VAR_URL, "descargado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "filas": len(d), "ultimo_mes": str(d["mes"].iloc[-1]), "licencia": "BCE: reutilización citando la fuente"}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    if a.refresh:
        print(refresh_tedr_variable())
    print(json.dumps(market_reference("variable", load_market()), indent=1, ensure_ascii=False))
