"""Reconstruye los paneles v2 a partir de data/staging (SIN red).

    python -m src.pipelines.build_master [--from-raw]

--from-raw: regenera antes staging a partir del último snapshot raw de cada dataset (rebuild sin descargas).
"""
from __future__ import annotations

import argparse
import json
import logging

import pandas as pd
import yaml

from src.common import config, io
from src.ingestion import get_connector
from src.transformations import panels, temporal
from src.validation import checks

log = logging.getLogger("etl.build")


def stage_all_from_raw(keys=None) -> dict:
    issues = {}
    for spec in config.DATASETS:
        if keys and spec.key not in keys:
            continue
        df = get_connector(spec.source).stage_from_latest(spec)
        issues[spec.key] = checks.check_staging(df, spec.key)
        io.write_staging(df, spec.key)
    return issues


def load_staging() -> dict[str, pd.DataFrame]:
    out = {}
    for spec in config.DATASETS:
        p = config.STAGING / f"{spec.key}.csv"
        if p.exists():
            out[spec.key] = io.read_staging(spec.key)
        elif not spec.optional:
            raise FileNotFoundError(f"Falta staging de {spec.key}: ejecuta update_all o build_master --from-raw")
    return out


def _dictionary(pt, pa, pm, nac) -> pd.DataFrame:
    rows = []
    var_ds = {v.name: (d, v) for d in config.DATASETS for v in d.variables}
    lvl = {}
    for d in config.DATASETS:
        st = config.STAGING / f"{d.key}.csv"
    for panel_name, df in [("panel_trimestral", pt), ("panel_anual", pa), ("panel_modelado", pm), ("nacional_trimestral", nac)]:
        for c in df.columns:
            base = c.replace("_suma_prov", "").replace("_status", "").replace("_ref_year", "")
            d, v = var_ds.get(base, (None, None))
            geo = ""
            if d is not None:
                geo = ("ccaa" if d.geo_vars and d.geo_vars[0].startswith("Comunidades") else
                       "nacional" if (d.source in ("ecb", "eurostat") or d.geo_vars == ("Total Nacional",)) else "provincia")
                if v.name == "euribor_12m":
                    geo = "zona_euro"
            elif base in config.DERIVED:
                geo = "nacional"
            desc = v.description if v else config.DERIVED.get(base, (None, None, ""))[2]
            if c.endswith("_ref_year"):
                desc = f"Año de referencia de {base} disponible (publicado) al cierre del trimestre; regla: 1-ene-Y + {temporal.AVAILABILITY_LAG_MONTHS.get(base)} meses"
            elif c.endswith("_suma_prov"):
                desc = f"Suma de las 52 provincias de {base} (reconciliación con el total nacional oficial)"
            elif c.endswith("_status"):
                desc = f"Estado INE del dato de {base} (Definitivo/Provisional/Avance)"
            rows.append({"panel": panel_name, "columna": c, "geo_level": geo if panel_name != "nacional_trimestral" or not geo else ("nacional" if geo == "provincia" else geo),
                         "unidad": v.unit if v else config.DERIVED.get(base, ("", "", ""))[1],
                         "frecuencia_origen": d.freq if d else "", "agregacion_trimestral": v.agg_q if v else "",
                         "fuente": d.source if d else ("derivada" if base in config.DERIVED else "clave/estructura"),
                         "dataset": d.key if d else "", "tabla_o_serie": d.ref if d else "", "descripcion": desc})
    extra = {"prov_code": "Código INE de provincia (01-52)", "provincia": "Nombre oficial INE", "ccaa_code": "Código INE de CCAA",
             "period": "Trimestre YYYYQn", "quarter_start": "Fecha de inicio del trimestre", "year": "Año de referencia",
             "poblacion_ecp": "Población ECP nacional en la fecha de stock más reciente <= inicio del trimestre (sin interpolar)",
             "poblacion_ecp_fecha": "Fecha de referencia del stock de población usado",
             "pib_pc_trimestral_eur": "PIB nominal trimestral (no ajustado) / población ECP (euros por habitante y trimestre)"}
    df = pd.DataFrame(rows)
    for k, v in extra.items():
        df.loc[df["columna"] == k, "descripcion"] = v
    return df


def build(write: bool = True) -> dict:
    stg = load_staging()
    q = panels.quarterly_long(stg)
    pt = panels.build_panel_trimestral(q)
    pa = panels.build_panel_anual(stg)
    pm = panels.build_panel_modelado(pt, pa)
    nac = panels.build_nacional(q, pt, stg)
    issues = []
    issues += checks.check_panel(pt, ["prov_code", "period"], "panel_trimestral")
    issues += checks.check_panel(pa, ["prov_code", "year"], "panel_anual")
    issues += checks.check_integer_format(
        pt.melt(id_vars=["prov_code", "period"], value_vars=[c for c in pt if c.endswith("_num")], var_name="variable").dropna(), "panel_trimestral")
    issues += checks.check_jumps(pt, "prov_code", "period", ["hipotecas_viviendas_num", "compraventas_viviendas_num", "precio_m2_mivau_tasado"], "panel_trimestral")
    issues += checks.check_jumps(pa, "prov_code", "year", ["poblacion", "poblacion_extranjera", "pib_pc"], "panel_anual")
    issues += checks.reconcile_totals(nac, [(v, f"{v}_suma_prov") for v in
                                            ["hipotecas_viviendas_num", "hipotecas_fincas_total_num", "compraventas_viviendas_num", "hipotecas_viviendas_importe"]])
    result = {"panel_trimestral": pt, "panel_anual": pa, "panel_modelado": pm, "nacional_trimestral": nac, "issues": issues}
    if write:
        config.PROCESSED.mkdir(parents=True, exist_ok=True)
        for name in ("panel_trimestral", "panel_anual", "panel_modelado", "nacional_trimestral"):
            result[name].to_csv(config.PROCESSED / f"{name}.csv", index=False, encoding="utf-8", float_format="%.10g")
        dic = _dictionary(pt, pa, pm, nac)
        config.METADATA.mkdir(parents=True, exist_ok=True)
        dic.to_csv(config.METADATA / "data_dictionary.csv", index=False, encoding="utf-8")
        write_metadata()
        config.ARTIFACTS_DQ.mkdir(parents=True, exist_ok=True)
        (config.ARTIFACTS_DQ / "build_issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return result


def write_metadata():
    """Catálogo de series y procedencia (a partir de config + metadatos de los snapshots)."""
    cat, prov = [], []
    for d in config.DATASETS:
        snap = io.latest_snapshot(d.source, d.key)
        meta = snap[1] if snap else {}
        cat.append({"dataset": d.key, "fuente": d.source, "tabla_o_clave": d.ref, "frecuencia": d.freq,
                    "operacion_ine": d.operation or None, "metodologia": d.methodology, "retraso_publicacion": d.publication_lag,
                    "url_documentacion": d.url_doc or None, "opcional": d.optional,
                    "ultima_modificacion_origen": meta.get("table_last_modified") or meta.get("updated"),
                    "fecha_extraccion": meta.get("retrieved_at") or meta.get("retrieved_at_note"),
                    "series_ids": meta.get("series_ids"),
                    "vintages": "No disponibles vía API: el INE/BCE solo sirven la última versión; cada snapshot raw es nuestro vintage. "
                                "El INE marca cada dato como Provisional/Definitivo/Avance (columna status).",
                    "fecha_referencia_vs_publicacion": "ref_date = periodo de referencia; la fecha de publicación no la da la API (se aproxima con retraso_publicacion)",
                    "variables": [{"nombre": v.name, "unidad": v.unit, "agregacion_trimestral": v.agg_q, "rango_valido": list(v.valid_range),
                                   "filtro_origen": v.match, "descripcion": v.description} for v in d.variables]})
        if snap:
            prov.append({"dataset": d.key, "fuente": d.source, "snapshot": str(snap[0].relative_to(config.ROOT)),
                         "sha256_fichero": meta.get("file_sha256"), "sha256_contenido": meta.get("content_sha256"),
                         "fecha_extraccion": meta.get("retrieved_at"), "n_series": meta.get("n_series"), "n_obs": meta.get("n_obs"),
                         "bytes": meta.get("bytes"), "snapshot_anterior": meta.get("previous_snapshot")})
    (config.METADATA / "series_catalog.yaml").write_text(yaml.safe_dump(cat, allow_unicode=True, sort_keys=False, width=140), encoding="utf-8")
    pd.DataFrame(prov).to_csv(config.METADATA / "provenance.csv", index=False, encoding="utf-8")
    (config.METADATA / "model_dependencies.yaml").write_text(
        yaml.safe_dump(config.MODEL_DEPENDENCIES, allow_unicode=True, sort_keys=True), encoding="utf-8")
    (config.METADATA / "availability_rules.yaml").write_text(yaml.safe_dump(
        {"descripcion": "panel_modelado: para el trimestre que termina en E se usa el año de referencia Y más reciente con "
                        "1-ene-Y + lag_meses <= E; si ese año aún no tiene dato, el último disponible. Sin interpolación.",
         "lag_meses": temporal.AVAILABILITY_LAG_MONTHS}, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-raw", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if a.from_raw:
        st = stage_all_from_raw()
        for k, v in st.items():
            for i in v:
                log.info("staging %s: %s", k, i)
    r = build()
    for k in ("panel_trimestral", "panel_anual", "panel_modelado", "nacional_trimestral"):
        log.info("%s: %s", k, r[k].shape)
    for i in r["issues"]:
        if i["severity"] != "info":
            log.warning("%s", i)


if __name__ == "__main__":
    main()
