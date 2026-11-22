"""Actualización completa del pipeline de datos v2.

    python -m src.pipelines.update_all                 # consulta todas las fuentes, guarda novedades y reconstruye
    python -m src.pipelines.update_all --dry-run       # descarga y valida en memoria; NO escribe raw/staging/processed
    python -m src.pipelines.update_all --source ine    # solo una fuente (ine | ecb | eurostat | mivau | tinsa)
    python -m src.pipelines.update_all --dataset ine_hipotecas
    python -m src.pipelines.update_all --rebuild       # sin red: borra staging/processed y reconstruye desde el último raw
    python -m src.pipelines.update_all --rebuild --refetch   # desde cero: descarga, re-stagea todo y reconstruye

Pasos: fetch (snapshot raw versionado + sha256 + detección de cambios por hash de contenido y metadatos de
origen) → parse → reconciliación con el staging anterior (nuevas/revisadas/eliminadas) → validación → staging →
build_master → controles de calidad → informe ``artifacts/data_quality/update_report_<fecha>.{md,json}`` con la
lista de modelos a recalibrar (config.MODEL_DEPENDENCIES) según las variables cuyos valores cambiaron.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import shutil
import sys

import pandas as pd

from src.common import config, io
from src.ingestion import get_connector
from src.validation import checks, reconciliation

from . import build_master

log = logging.getLogger("etl.update")


def select(source=None, dataset=None):
    out = []
    for d in config.DATASETS:
        if source and d.source != source:
            continue
        if dataset and d.key != dataset:
            continue
        out.append(d)
    if not out:
        raise SystemExit(f"Ningún dataset coincide con source={source} dataset={dataset}")
    return out


def run(source=None, dataset=None, dry_run=False, rebuild=False, refetch=False) -> dict:
    started = dt.datetime.now(dt.timezone.utc)
    specs = select(source, dataset)
    report = {"started_at": started.isoformat(timespec="seconds"), "mode": "dry-run" if dry_run else ("rebuild" if rebuild else "update"),
              "filters": {"source": source, "dataset": dataset}, "datasets": {}, "issues": [], "changed_variables": [],
              "models_to_recalibrate": {}}
    if rebuild and not dry_run:
        for p in (config.STAGING, config.PROCESSED):
            if p.exists():
                for f in p.glob("*.csv"):
                    f.unlink()
                if (p / "v1_corrected").exists():
                    shutil.rmtree(p / "v1_corrected")
    changed_vars = set()
    for spec in specs:
        con = get_connector(spec.source)
        entry = {"source": spec.source, "ref": spec.ref}
        try:
            if rebuild and not refetch:
                new = con.stage_from_latest(spec)
                entry.update(fetched=False, changed=True)
            else:
                res = con.fetch(spec, dry_run=dry_run)
                entry.update(fetched=True, changed=res.changed, snapshot=res.snapshot,
                             origin_last_modified=res.meta.get("table_last_modified") or res.meta.get("last_modified") or res.meta.get("updated"),
                             retrieved_at=res.meta.get("retrieved_at"), notes=res.notes)
                stg_path = config.STAGING / f"{spec.key}.csv"
                if not res.changed and stg_path.exists() and not rebuild:
                    entry["staging"] = "sin cambios"
                    report["datasets"][spec.key] = entry
                    continue
                new = con.parse(res.payload, spec, res.meta)
                new["snapshot"] = str(res.snapshot) if res.snapshot else "(dry-run)"
                new["retrieved_at"] = res.meta.get("retrieved_at")
                new["dataset"] = spec.key
            old = io.read_staging(spec.key) if (config.STAGING / f"{spec.key}.csv").exists() else None
            diff = reconciliation.diff_staging(old, new)
            entry["diff_vs_staging_anterior"] = diff
            for v, d in diff.items():
                if d["new"] or d["revised"] or d["removed"]:
                    changed_vars.add(v)
            iss = checks.check_staging(new, spec.key)
            entry["issues"] = iss
            report["issues"] += iss
            if any(i["severity"] == "error" for i in iss):
                entry["staging"] = "NO actualizado: errores de validación"
                log.error("%s: errores de validación, se mantiene el staging anterior", spec.key)
            elif not dry_run:
                io.write_staging(new, spec.key)
                entry["staging"] = "actualizado"
            else:
                entry["staging"] = "dry-run (no escrito)"
        except Exception as e:  # un conector caído no debe tumbar el resto
            log.exception("%s falló", spec.key)
            entry.update(error=repr(e)[:500])
            report["issues"].append({"check": "fetch", "severity": "error", "target": spec.key, "detail": repr(e)[:300], "n": None})
        report["datasets"][spec.key] = entry
    report["changed_variables"] = sorted(changed_vars)
    recal = {}
    for v in changed_vars:
        for m in config.MODEL_DEPENDENCIES.get(v, []):
            recal.setdefault(m, []).append(v)
    report["models_to_recalibrate"] = {k: sorted(v) for k, v in sorted(recal.items())}
    if not dry_run:
        try:
            b = build_master.build(write=True)
            report["issues"] += b["issues"]
            report["outputs"] = {k: list(b[k].shape) for k in ("panel_trimestral", "panel_anual", "panel_modelado", "nacional_trimestral")}
        except FileNotFoundError as e:
            report["issues"].append({"check": "build", "severity": "error", "target": "build_master", "detail": str(e), "n": None})
    report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    write_report(report, dry_run)
    return report


def write_report(rep: dict, dry_run: bool):
    config.ARTIFACTS_DQ.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S") + ("_dryrun" if dry_run else "")
    (config.ARTIFACTS_DQ / f"update_report_{stamp}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    L = [f"# Informe de actualización de datos ({rep['mode']})", "",
         f"- Inicio: {rep['started_at']} · Fin: {rep['finished_at']}", f"- Filtros: {rep['filters']}", "",
         "## Datasets", "", "| dataset | fuente | ¿cambios en origen? | última modificación origen | staging | nuevas | revisadas | eliminadas |",
         "|---|---|---|---|---|---|---|---|"]
    for k, e in rep["datasets"].items():
        d = e.get("diff_vs_staging_anterior", {})
        tot = {x: sum(v.get(x, 0) for v in d.values()) for x in ("new", "revised", "removed")}
        L.append(f"| {k} | {e['source']} | {'sí' if e.get('changed') else 'no'} | {e.get('origin_last_modified') or ''} | "
                 f"{e.get('staging', e.get('error', ''))} | {tot['new']} | {tot['revised']} | {tot['removed']} |")
    L += ["", "## Variables con cambios", "", ", ".join(rep["changed_variables"]) or "(ninguna)", "",
          "## Modelos que requieren recalibración", ""]
    L += [f"- `{m}` ← {', '.join(v)}" for m, v in rep["models_to_recalibrate"].items()] or ["(ninguno)"]
    L += ["", "## Incidencias de calidad (error/warning)", ""]
    L += [f"- **{i['severity']}** `{i['check']}` {i['target']}: {i['detail']}" for i in rep["issues"] if i["severity"] != "info"] or ["(ninguna)"]
    if "outputs" in rep:
        L += ["", "## Salidas", ""] + [f"- `data/processed/{k}.csv`: {v[0]} filas × {v[1]} columnas" for k, v in rep["outputs"].items()]
    (config.ARTIFACTS_DQ / f"update_report_{stamp}.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--source")
    ap.add_argument("--dataset")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--refetch", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    rep = run(a.source, a.dataset, a.dry_run, a.rebuild, a.refetch)
    errs = [i for i in rep["issues"] if i["severity"] == "error"]
    print(f"Datasets: {len(rep['datasets'])} · variables con cambios: {len(rep['changed_variables'])} · errores: {len(errs)}")
    return 1 if any("error" in e for e in rep["datasets"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
