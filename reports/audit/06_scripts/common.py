"""Utilidades comunes de la auditoría estadística (06).

- Carga LITERALMENTE las funciones del notebook v1 `3. data_joining.ipynb`
  (celdas con provincias_limpias, limpiar_provincia, mensual_a_trimestral,
  expandir_*, limpiar_numero) ejecutando su código fuente, para auditar
  exactamente lo que se ejecutó.
- Proporciona un resolvedor "verdad terreno" de provincias/CCAA basado en
  src/common/geography.py + reparación iterativa de mojibake.
Uso: python3 -I reports/audit/06_scripts/<script>.py  (desde la raíz del repo)
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NB_DIR = ROOT / "notebooks acabados"
SRC_DIR = ROOT / "Datos ya metidos"
DIRTY_DIR = ROOT / "Datos sucios"
DATASET = NB_DIR / "dataset_final_tfm.csv"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from src.common import geography as geo  # noqa: E402


def load_nb_functions() -> dict:
    nb = json.loads((NB_DIR / "3. data_joining.ipynb").read_text(encoding="utf-8"))
    code_cells = [("".join(c["source"])) for c in nb["cells"] if c["cell_type"] == "code"]
    ns: dict = {}
    wanted = ("from difflib import", "provincias_limpias = [", "def q_to_date", "def expandir_nacional_a_prov")
    for src in code_cells:
        if any(w in src for w in wanted):
            exec(compile(src, "<nb3>", "exec"), ns)
    for k in ("limpiar_provincia", "expandir_ccaa_a_prov", "limpiar_numero",
              "mensual_a_trimestral", "expandir_anual_a_trimestral", "provincias_limpias"):
        assert k in ns, k
    return ns


def demojibake(s: str, max_rounds: int = 5) -> str:
    s = str(s)
    for _ in range(max_rounds):
        try:
            r = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if r == s:
            break
        s = r
    return s


def true_province_code(name: str) -> str:
    raw = re.sub(r"^\d+\s+", "", demojibake(name).strip())
    # formas INE invertidas "Coruña, A", "Palmas, Las", "Rioja, La"
    m = re.match(r"^(.*),\s*(A|La|Las|Los|El|Illes)$", raw)
    if m:
        raw = f"{m.group(2)} {m.group(1)}"
    extra = {"gerona": "17", "lerida": "25", "orense": "32", "lacoruna": "15"}
    k = geo.normalize(raw)
    if k in extra:
        return extra[k]
    return geo.province_code(raw)


LEGACY = {c: p.legacy_name for c, p in geo.PROVINCES.items()}
