"""Adaptador: construye vistas a partir de los artefactos reales (CSV/JSON) cuando no hay ``manifest.json``.

Si un pipeline escribe ``manifest.json`` + ``views.json`` se usa ese contrato; si no, este módulo lee los
ficheros nativos de cada dominio. Ninguna cifra se inventa: todo sale de ``artifacts/`` y ``data/``.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .views import validate_views


def _clean(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(f) else round(f, 4)


def _mtime_iso(paths) -> str | None:
    ts = [p.stat().st_mtime for p in paths if p.exists()]
    return datetime.fromtimestamp(max(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def _table(title, df, cols=None, rename=None, nd=3, subtitle=None):
    d = df[cols] if cols else df
    rows = [[(_clean(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else (None if pd.isna(x) else str(x))) for x in r]
            for r in d.itertuples(index=False)]
    return {"type": "table", "title": title, "subtitle": subtitle,
            "columns": [(rename or {}).get(c, c) for c in d.columns], "rows": rows}


def _fc(data_dir: Path) -> pd.DataFrame | None:
    p = data_dir / "forecasts" / "proyecciones_2026_2030_v2.csv"
    return pd.read_csv(p, dtype={"prov_code": str}) if p.exists() else None


def _nat(data_dir: Path) -> pd.DataFrame | None:
    p = data_dir / "processed" / "nacional_trimestral.csv"
    return pd.read_csv(p) if p.exists() else None


def _periods(a, b):
    out = []
    y, q = int(a[:4]), int(a[5])
    while f"{y}Q{q}" <= b:
        out.append(f"{y}Q{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def _series_view(title, obs: pd.Series | None, fc: pd.DataFrame, unit, start="2018Q1", subtitle=None, scen_note=""):
    """obs: serie observada indexada por periodo; fc: filas (period, escenario, valor, p10, p90) de UN ámbito."""
    last = max(fc.period)
    first_obs = start
    x = _periods(first_obs, last)
    hist = [(_clean(obs.get(p)) if obs is not None else None) for p in x]
    series = [{"name": "Observado", "values": hist, "role": "historical"}]
    for esc, label in (("base", "Escenario base"), ("adverso", "Escenario adverso"), ("favorable", "Escenario favorable")):
        g = fc[fc.escenario == esc].set_index("period")
        if g.empty:
            continue
        series.append({"name": label, "values": [_clean(g.valor.get(p)) for p in x],
                       "role": "forecast" if esc == "base" else "scenario"})
        if esc == "base" and g.p10.notna().any():
            series.append({"name": "Intervalo 10-90 % (base)", "values": [_clean(g.p10.get(p)) for p in x], "role": "lower"})
            series.append({"name": "Intervalo 10-90 % (base) ", "values": [_clean(g.p90.get(p)) for p in x], "role": "upper"})
    ref = fc[fc.escenario == "referencia_naive"].set_index("period")
    if not ref.empty:
        series.append({"name": "Referencia naive", "values": [_clean(ref.valor.get(p)) for p in x], "role": "scenario"})
    return {"type": "timeseries", "title": title, "unit": unit, "x": x, "series": series,
            "subtitle": subtitle or "Línea continua: observado. Discontinua: escenarios condicionados a supuestos (no son predicciones oficiales)." + scen_note}


def _annual_view(title, fc, unit):
    x = sorted(fc.period.unique())
    series = []
    for esc in ("base", "adverso", "favorable"):
        g = fc[fc.escenario == esc].set_index("period")
        if not g.empty:
            series.append({"name": f"Escenario {esc}", "values": [_clean(g.valor.get(p)) for p in x],
                           "role": "forecast" if esc == "base" else "scenario"})
    return {"type": "timeseries", "title": title, "unit": unit, "x": x, "series": series}


def _read(p: Path):
    return pd.read_csv(p) if p.exists() else None


# ───────────────────────────── dominios ─────────────────────────────
def demand(root: Path, data: Path):
    d = root / "demand"
    meta = d / "metadata.json"
    if not meta.exists():
        return None
    md = json.loads(meta.read_text(encoding="utf-8"))
    cut = (md.get("datos", {}).get("panel_period_range") or [None, None])[1]
    views = []
    sel = md.get("demanda", {}).get("hipotecas_viviendas", {}).get("seleccionado_por_h", {})
    met = _read(d / "hipotecas_viviendas_nacional_metricas.csv")
    if met is not None:
        ho = met[met.window == "holdout"]
        items = []
        for h in (1, 4):
            m = sel.get(str(h))
            r = ho[(ho.h == h) & (ho.model == m)]
            if m and not r.empty:
                items.append({"label": f"MASE hold-out h={h} ({m})", "value": _clean(r.MASE.iloc[0]), "note": f"MAPE {_clean(r.MAPE.iloc[0])} %"})
        if items:
            views.append({"type": "metrics", "title": "Modelo de demanda: error fuera de muestra (nacional)", "items": items,
                          "subtitle": "Hold-out 2022T1-2025T4; MASE < 1 mejora al naive."})
    fc, nat = _fc(data), _nat(data)
    if fc is not None:
        g = fc[(fc.variable == "hipotecas_viviendas") & (fc.prov_code == "00")]
        if not g.empty:
            obs = nat.set_index("period").hipotecas_viviendas_num.dropna() if nat is not None else None
            views.append(_series_view("Hipotecas sobre viviendas: España (trimestral)", obs, g, "nº"))
    if met is not None:
        ho = met[(met.window == "holdout")].pivot(index="model", columns="h", values="MASE").round(3).reset_index()
        ho.columns = ["Modelo"] + [f"MASE h={c}" for c in ho.columns[1:]]
        views.append(_table("Benchmark nacional (MASE, hold-out)", ho, subtitle="Menor es mejor; incluye referencias naive y estacional."))
    dm = _read(d / "hipotecas_viviendas_nacional_dm.csv")
    if dm is not None:
        dm = dm[dm.window == "seleccion"][["model", "benchmark", "h", "n", "DM_sq", "p_sq"]]
        views.append(_table("Contraste Diebold-Mariano frente al benchmark", dm.round(3),
                            rename={"model": "Modelo", "benchmark": "Benchmark", "h": "h", "n": "n", "DM_sq": "DM", "p_sq": "p-valor"}))
    pm = _read(d / "hipotecas_viviendas_provincial_metricas.csv")
    if pm is not None:
        p = pm[pm.window == "holdout"][["model", "h", "n_unidades", "MASE", "MAPE", "pct_unidades_U_menor_1"]].round(3)
        views.append(_table("Panel provincial (hold-out)", p, rename={"model": "Modelo", "n_unidades": "Provincias", "pct_unidades_U_menor_1": "% provincias con U<1"}))
    return _bundle(root, "demand", md, views, cut, [meta], [{"name": "INE: Estadística de Hipotecas (tabla 3200)", "url": "https://www.ine.es/"}],
                   "Proyección condicional a escenarios de Euríbor y paro; asociación estadística, no causalidad.")


def demand_scope(root: Path, data: Path, code: str):
    fc, panel = _fc(data), data / "processed" / "panel_trimestral.csv"
    if fc is None:
        return None
    g = fc[(fc.variable == "hipotecas_viviendas") & (fc.prov_code == code)]
    if g.empty:
        return None
    obs = None
    if panel.exists():
        p = pd.read_csv(panel, usecols=["prov_code", "period", "hipotecas_viviendas_num"], dtype={"prov_code": str})
        p["prov_code"] = p.prov_code.str.zfill(2)
        obs = p[p.prov_code == code].set_index("period").hipotecas_viviendas_num.dropna()
    return validate_views([_series_view("Hipotecas sobre viviendas (provincia)", obs, g, "nº",
                                        scen_note=" Reparto top-down de la senda nacional.")])


def forecasting(root: Path, data: Path):
    d = root / "forecasting"
    meta = d / "metadata.json"
    fc = _fc(data)
    if not meta.exists() or fc is None:
        return None
    md = json.loads(meta.read_text(encoding="utf-8"))
    nat = _nat(data)
    cut = (md.get("datos", {}).get("panel_period_range") or [None, None])[1]
    views = []
    g = fc[(fc.variable == "euribor_12m")]
    obs = nat.set_index("period").euribor_12m.dropna() if nat is not None else None
    e = g[g.modelo.str.startswith("escenario")]
    if not e.empty:
        views.append(_series_view("Euríbor 12M: observado y escenarios", obs, e, "%", subtitle="Escenarios: BCE sep-2026 3M + diferencial 12M-3M (supuesto, no predicción)."))
    g = fc[(fc.variable == "hipotecas_viviendas") & (fc.prov_code == "00")]
    if not g.empty:
        views.append(_series_view("Hipotecas sobre viviendas: España", nat.set_index("period").hipotecas_viviendas_num.dropna() if nat is not None else None, g, "nº"))
    for var, title, unit in (("ipc_iapc_espana", "IPC (IAPC) España: escenarios anuales", "%"), ("paro_nacional", "Paro nacional: escenarios anuales", "%"),
                             ("pib_pc_crecimiento_nominal", "PIB per cápita: crecimiento nominal (escenarios)", "%")):
        g = fc[fc.variable == var]
        if not g.empty:
            views.append(_annual_view(title, g, unit))
    rows = []
    for var, m in md.get("macro", {}).items():
        mt = _read(d / f"{var}_metricas.csv")
        row = [var, m.get("seleccionado")]
        if mt is not None:
            r = mt[(mt.window == "holdout") & (mt.model == m.get("seleccionado")) & (mt.h == 1)]
            row.append(_clean(r.MASE.iloc[0]) if not r.empty else None)
        else:
            row.append(None)
        rows.append(row)
    if rows:
        views.append({"type": "table", "title": "Modelos seleccionados por variable (MASE hold-out h=1)", "columns": ["Variable", "Modelo", "MASE"], "rows": rows,
                      "subtitle": "Precio por m²: valor tasado MIVAU (Ministerio de Vivienda y Agenda Urbana). Intervalos: cuantiles empíricos 10-90 % del error de backtest."})
    return _bundle(root, "forecasting", md, views, cut, [meta, data / "forecasts" / "proyecciones_2026_2030_v2.csv"],
                   [{"name": "INE, BCE, Eurostat, Comisión Europea, MIVAU (valor tasado)", "url": "https://www.ine.es/"}],
                   "Los años futuros son escenarios condicionados a supuestos publicados, no previsiones oficiales.")


def econometrics(root: Path, data: Path):
    d = root / "econometrics"
    f = d / "econometrics_v2.json"
    if not f.exists():
        return None
    j = json.loads(f.read_text(encoding="utf-8"))
    mt = j.get("metadatos", {})
    views = []
    dec, rg = j.get("decision", {}), j.get("rango_principal", {})
    items = [{"label": "Modelo principal", "value": dec.get("modelo_principal", "—")},
             {"label": "p bootstrap rango (H0: r=0)", "value": _clean(dec.get("p_bootstrap_r0")), "note": f"umbral {dec.get('umbral')}"},
             {"label": "Observaciones efectivas", "value": rg.get("T_efectiva")}]
    va = j.get("VAR_diferencias", {})
    if "raiz_max" in va:
        items.append({"label": "Raíz máxima VAR (estable si < 1)", "value": va["raiz_max"]})
    views.append({"type": "metrics", "title": "Resumen de la especificación", "items": items,
                  "subtitle": f"Muestra {mt.get('muestra', ['', ''])[0]}-{mt.get('muestra', ['', ''])[-1]}; precio principal: {mt.get('precio_principal', 'MIVAU')}."})
    if dec.get("regla"):
        views.append({"type": "note", "title": "Regla de decisión", "text": dec["regla"]})
    views.append({"type": "table", "title": "Orden de integración (dictamen)", "columns": ["Serie", "Dictamen"],
                  "rows": [[k, v] for k, v in j.get("raices_unitarias_dictamen", {}).items() if "tinsa" not in k.lower()]})
    irf = _read(d / "irf_hipotecas.csv")
    if irf is not None:
        s = irf[(irf.modelo == "VAR_diferencias") & (irf.identificacion == "cholesky")]
        for shock in s.shock.unique():
            g = s[s.shock == shock].sort_values("horizonte")
            if shock == "hipotecas":
                continue
            views.append({"type": "timeseries", "title": f"Respuesta de hipotecas a un impulso en {shock.replace('_', ' ')}",
                          "subtitle": "VAR en diferencias, Cholesky; IRF acumulada (log). Banda: percentiles 5-95 del bootstrap. Asociación dinámica, no causalidad.",
                          "x": [f"h{int(h)}" for h in g.horizonte],
                          "series": [{"name": "IRF", "values": [_clean(v) for v in g.valor], "role": "historical"},
                                     {"name": "p5", "values": [_clean(v) for v in g.p5], "role": "lower"},
                                     {"name": "p95", "values": [_clean(v) for v in g.p95], "role": "upper"}]})
    ad = j.get("antes_despues", {})
    if ad:
        views.append({"type": "note", "title": "Antes y después (v1 frente a v2)",
                      "text": "La cointegración de la v1 no se sostiene tras corregir los datos y usar contrastes con bootstrap (p r=0 = "
                              f"{dec.get('p_bootstrap_r0')}). Ver detalle en el informe de econometría."})
    ur = _read(d / "unit_root.csv")
    if ur is not None:
        u = ur[ur.det == "c"][["serie", "transf", "T", "adf_bic_p", "kpss_p"]].round(3)
        views.append(_table("Raíces unitarias (constante)", u, rename={"transf": "Transf.", "adf_bic_p": "ADF p", "kpss_p": "KPSS p"}))
    return _bundle(root, "econometrics", {"generado": mt.get("generado")}, views, (mt.get("muestra") or [None, None])[-1], [f],
                   [{"name": "Panel Atalaya v2 (INE, BCE, MIVAU, Eurostat)", "url": "https://www.ine.es/"}],
                   "Modelos VAR/VECM sobre series nacionales trimestrales.")


def advisor(root: Path, data: Path):
    d = root / "advisor"
    f = d / "estimator_validation.json"
    if not f.exists():
        return None
    j = json.loads(f.read_text(encoding="utf-8"))
    views = []
    t = j.get("tedr_todas_fijaciones", {})
    items = [{"label": f"Error absoluto medio h={h[1:]} trim.", "value": _clean(t[h]["mae_pp"]), "unit": "pp"} for h in ("h1", "h4") if h in t]
    views.append({"type": "metrics", "title": "Estimador de tipo de mercado: validación", "items": items,
                  "subtitle": f"Evaluación desde {j.get('periodo_evaluado_desde')}; último dato {j.get('ultimo_dato')}."})
    rows = [[k, h[1:], v["n"], _clean(v["mae_pp"]), _clean(v["rmse_pp"]), _clean(v["cobertura_rango_4t"])]
            for k, tt in (("TEDR todas fijaciones", t), ("TEDR variable", j.get("tedr_variable", {}))) for h, v in tt.items()]
    views.append({"type": "table", "title": "Error del tipo de referencia (pp)", "columns": ["Serie", "h", "n", "MAE", "RMSE", "Cobertura rango 4T"], "rows": rows})
    if j.get("lectura"):
        views.append({"type": "note", "title": "Lectura", "text": j["lectura"]})
    return _bundle(root, "advisor", {"generado": None}, views, j.get("ultimo_dato"), [f, d / "fiscal_tables.json"],
                   [{"name": "BCE: tipos de interés bancarios (MIR)", "url": "https://data-api.ecb.europa.eu/"},
                    {"name": "BOE: legislación consolidada", "url": "https://www.boe.es/"}],
                   "Parámetros de política ilustrativos; el asesor no emite decisiones de concesión.")


def data_quality(root: Path, data: Path):
    d = root / "data_quality"
    f = d / "build_issues.json"
    if not f.exists():
        return None
    views = []
    iss = json.loads(f.read_text(encoding="utf-8"))
    iss = [i for i in iss if "tinsa" not in json.dumps(i).lower()] if isinstance(iss, list) else iss  # sin series Tinsa en la UI
    if isinstance(iss, list) and iss:
        views.append({"type": "table", "title": "Incidencias de construcción del panel", "columns": ["Control", "Gravedad", "Objetivo", "Detalle", "n"],
                      "rows": [[i.get("check"), i.get("severity"), i.get("target"), i.get("detail"), i.get("n")] for i in iss[:200]]})
    v = _read(d / "v1_vs_v2.csv")
    if v is not None:
        v = v[~v.apply(lambda r: "tinsa" in " ".join(map(str, r)).lower(), axis=1)]
        views.append(_table("Panel v1 frente a v2", v, cols=["v1", "v2", "n_comparadas", "pct_iguales_0.5pct", "max_dif_rel_pct", "nota"]))
    return _bundle(root, "data_quality", {}, views, None, [f], [{"name": "Pipeline Atalaya (build_master)"}], None)


def _bundle(root, domain, md, views, cutoff, files, sources, notes):
    gen = (md or {}).get("generado")
    if gen and len(gen) == 19:
        gen += "Z"
    manifest = {"domain": domain, "native": True, "generated_at": gen or _mtime_iso(files) or datetime.now(timezone.utc).isoformat(),
                "data_cutoff": cutoff, "sources": sources, "notes": notes, "views": [], "scopes": {}}
    return manifest, validate_views(views)


BUILDERS = {"demand": demand, "forecasting": forecasting, "econometrics": econometrics, "advisor": advisor, "data_quality": data_quality}
