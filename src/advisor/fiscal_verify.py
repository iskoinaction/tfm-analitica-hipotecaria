"""Verificación de la tabla fiscal contra la legislación consolidada del BOE (API de datos abiertos).

Para cada fila de ``data/metadata/fiscalidad_vigencias.csv`` con ``boe_id``:
1. Descarga el texto consolidado (``/datosabiertos/api/legislacion-consolidada/id/{id}/texto``, XML).
2. Localiza los artículos de ``articulo`` (separados por ';') y toma la VERSIÓN VIGENTE (última ``<version>``).
3. Comprueba que cada fragmento de ``texto_clave`` (separados por ' || ') aparece literalmente (espacios normalizados).
4. ``vigente_desde`` = fecha de vigencia de la versión más antigua de la racha final de versiones que contienen el
   fragmento (máximo entre artículos). ``verificado = true`` solo si todos los fragmentos aparecen.
Escribe la evidencia (fragmentos con contexto, fechas de versión, sha256 del XML) en
``artifacts/advisor/fiscal_verification.json`` y actualiza las columnas de la tabla.

Uso: ``python -m src.advisor.fiscal_verify`` (caché de XML en ``$ATALAYA_BOE_CACHE`` o ~/.cache/atalaya_boe).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .fiscal import FISCAL_CSV, ROOT

API = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{}/texto"
CACHE = Path(os.environ.get("ATALAYA_BOE_CACHE", Path.home() / ".cache" / "atalaya_boe"))
EVIDENCE = ROOT / "artifacts" / "advisor" / "fiscal_verification.json"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def fetch_xml(boe_id: str) -> tuple[ET.Element, str]:
    import requests
    CACHE.mkdir(parents=True, exist_ok=True)
    fn = CACHE / f"{boe_id}.xml"
    if not fn.exists():
        r = requests.get(API.format(boe_id), timeout=120,
                         headers={"Accept": "application/xml", "User-Agent": "atalaya-advisor/2.0 (academico; lectura)"})
        r.raise_for_status()
        fn.write_bytes(r.content)
    b = fn.read_bytes()
    return ET.fromstring(b), hashlib.sha256(b).hexdigest()


def article_versions(root: ET.Element, art: str) -> list[tuple[str, str]]:
    pat = re.compile(rf"^Art[íi]culo {re.escape(art)}(\.|$|\s)")
    for b in root.iter("bloque"):
        t = _norm(b.get("titulo") or "")
        vs = b.findall("version")
        if vs and pat.match(t):
            return [(v.get("fecha_vigencia"), _norm(" ".join(x.strip() for x in v.itertext() if x.strip()))) for v in vs]
    return []


def verify_row(row: dict, today: str) -> dict:
    ev = {"id": row["id"], "boe_id": row["boe_id"], "articulos": {}, "fragmentos": [], "verificado": False}
    if not row["boe_id"] or not row["texto_clave"]:
        ev["motivo"] = "sin fuente oficial consultable en la API del BOE"
        return ev
    root, sha = fetch_xml(row["boe_id"])
    ev["xml_sha256"] = sha
    frags = [_norm(f) for f in row["texto_clave"].split("||") if f.strip()]
    arts = {a.strip(): article_versions(root, a.strip()) for a in row["articulo"].split(";") if a.strip()}
    desde = []
    for f in frags:
        hit = None
        for a, vs in arts.items():
            if vs and f in vs[-1][1]:
                k = len(vs) - 1
                while k > 0 and f in vs[k - 1][1]:
                    k -= 1
                txt = vs[-1][1]
                i = txt.find(f)
                hit = {"fragmento": f, "articulo": a, "version_vigente": vs[-1][0], "presente_desde_version": vs[k][0],
                       "contexto": txt[max(0, i - 160): i + len(f) + 120]}
                desde.append(vs[k][0])
                break
        ev["fragmentos"].append(hit or {"fragmento": f, "encontrado": False})
    ev["articulos"] = {a: [v[0] for v in vs] for a, vs in arts.items()}
    ok = all(h and h.get("encontrado", True) for h in ev["fragmentos"]) and bool(frags)
    ev["verificado"] = ok
    if ok:
        d = max(desde)
        ev["vigente_desde"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        ev["fecha_verificacion"] = today
    return ev


def main(path: Path = FISCAL_CSV) -> dict:
    today = dt.date.today().isoformat()
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    evidence = []
    for r in rows:
        ev = verify_row(r, today)
        evidence.append(ev)
        r["verificado"] = "true" if ev["verificado"] else "false"
        r["vigente_desde"] = ev.get("vigente_desde", "") if ev["verificado"] else r["vigente_desde"]
        r["fecha_verificacion"] = ev.get("fecha_verificacion", "") if ev["verificado"] else ""
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    out = {"generado": today, "api": API, "n_filas": len(rows), "n_verificadas": sum(e["verificado"] for e in evidence),
           "no_verificadas": [e["id"] for e in evidence if not e["verificado"]], "evidencias": evidence}
    EVIDENCE.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = main()
    print(o["n_verificadas"], "/", o["n_filas"], "verificadas; no verificadas:", o["no_verificadas"])
    for e in o["evidencias"]:
        for h in e["fragmentos"]:
            if h and h.get("encontrado") is False:
                print("  FALLA", e["id"], "->", h["fragmento"][:90])
