"""Tabla fiscal con vigencias (ITP, AJD, IVA) y aranceles de notaría y registro.

Fuentes de datos (propiedad del asesor):
- ``data/metadata/fiscalidad_vigencias.csv``: una fila por regla (CCAA, impuesto, ámbito, condición, tramos,
  vigencia, norma, artículo, id BOE, texto clave verificado, estado de verificación).
- ``data/metadata/aranceles.yaml``: escalas del Número 2 del Anexo I del RD 1426/1989 (notarios) y del
  RD 1427/1989 (registradores).

Formato de ``tramos``: ``desde-hasta:tipo|desde-hasta:tipo|desde-:tipo`` (euros, tipo en %).
``modo``: ``unico_por_valor`` (un único tipo, elegido según el valor total, sobre toda la base) o
``marginal`` (cada tramo de base tributa a su tipo; equivale a las tarifas "cuota íntegra + resto").
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FISCAL_CSV = ROOT / "data" / "metadata" / "fiscalidad_vigencias.csv"
ARANCELES_YAML = ROOT / "data" / "metadata" / "aranceles.yaml"

INF = float("inf")


@dataclass(frozen=True)
class Tramo:
    desde: float
    hasta: float
    tipo_pct: float


@dataclass(frozen=True)
class ReglaFiscal:
    id: str
    ccaa_code: str
    impuesto: str
    ambito: str
    condicion: str
    modo: str
    tramos: tuple
    vigente_desde: dt.date | None
    vigente_hasta: dt.date | None
    norma: str
    articulo: str
    boe_id: str
    url_fuente: str
    verificado: bool
    fecha_verificacion: str
    notas: str
    raw: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def modelado(self) -> bool:
        return bool(self.tramos)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "ccaa_code": self.ccaa_code, "impuesto": self.impuesto, "ambito": self.ambito,
            "condicion": self.condicion, "modo": self.modo,
            "tramos": [{"desde": t.desde, "hasta": (None if t.hasta == INF else t.hasta), "tipo_pct": t.tipo_pct}
                       for t in self.tramos],
            "vigente_desde": self.vigente_desde.isoformat() if self.vigente_desde else None,
            "vigente_hasta": self.vigente_hasta.isoformat() if self.vigente_hasta else None,
            "norma": self.norma, "articulo": self.articulo, "boe_id": self.boe_id, "url_fuente": self.url_fuente,
            "verificado": self.verificado, "fecha_verificacion": self.fecha_verificacion or None, "notas": self.notas,
        }


def parse_tramos(s: str) -> tuple:
    s = (s or "").strip()
    if not s:
        return ()
    out = []
    for part in s.split("|"):
        rng, tipo = part.split(":")
        lo, hi = rng.split("-")
        out.append(Tramo(float(lo), float(hi) if hi else INF, float(tipo)))
    out.sort(key=lambda t: t.desde)
    if out[0].desde != 0:
        raise ValueError(f"Los tramos deben empezar en 0: {s!r}")
    for a, b in zip(out, out[1:]):
        if a.hasta != b.desde:
            raise ValueError(f"Tramos no contiguos: {s!r}")
    if out[-1].hasta != INF:
        raise ValueError(f"El último tramo debe ser abierto: {s!r}")
    return tuple(out)


def _date(s):
    return dt.date.fromisoformat(s) if s else None


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> tuple:
    p = Path(path) if path else FISCAL_CSV
    rules = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rules.append(ReglaFiscal(
                id=r["id"], ccaa_code=r["ccaa_code"], impuesto=r["impuesto"], ambito=r["ambito"],
                condicion=r["condicion"], modo=r["modo"], tramos=parse_tramos(r["tramos"]),
                vigente_desde=_date(r["vigente_desde"]), vigente_hasta=_date(r["vigente_hasta"]),
                norma=r["norma"], articulo=r["articulo"], boe_id=r["boe_id"], url_fuente=r["url_fuente"],
                verificado=r["verificado"].strip().lower() == "true", fecha_verificacion=r["fecha_verificacion"],
                notas=r["notas"], raw=dict(r)))
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("ids duplicados en la tabla fiscal")
    return tuple(rules)


def _vigente(rule: ReglaFiscal, fecha: dt.date) -> bool:
    # Una regla sin vigente_desde (no verificada) se considera vigente pero se marca como no verificada.
    if rule.vigente_desde and fecha < rule.vigente_desde:
        return False
    if rule.vigente_hasta and fecha > rule.vigente_hasta:
        return False
    return True


def select_rule(ccaa_code: str, impuesto: str, ambito: str, fecha: dt.date, condiciones: set[str] | None = None,
                rules: tuple | None = None) -> ReglaFiscal | None:
    """Regla aplicable. Entre las condiciones cumplidas se elige la específica (p. ej. ``vivienda_habitual``)
    frente a ``general``. Devuelve None si no hay regla para ese territorio/impuesto."""
    rules = rules if rules is not None else load_rules()
    condiciones = set(condiciones or set()) | {"general"}
    cand = [r for r in rules if r.impuesto == impuesto and r.ambito == ambito
            and r.ccaa_code in (ccaa_code, "*") and r.condicion in condiciones and _vigente(r, fecha)]
    if not cand:
        return None
    # preferencia: territorio específico > comodín; condición específica > general
    cand.sort(key=lambda r: (r.ccaa_code == "*", r.condicion == "general"))
    best = cand[0]
    same = [r for r in cand if (r.ccaa_code == "*") == (best.ccaa_code == "*") and r.condicion == best.condicion]
    if len(same) > 1:
        raise LookupError(f"Varias reglas vigentes solapadas: {[r.id for r in same]}")
    return best


def tax_amount(rule: ReglaFiscal, base: float) -> float:
    if not rule.tramos:
        raise ValueError(f"La regla {rule.id} no está modelada (sin tramos)")
    if base <= 0:
        return 0.0
    if rule.modo == "unico_por_valor":
        for t in rule.tramos:
            if base <= t.hasta:
                return base * t.tipo_pct / 100
        return base * rule.tramos[-1].tipo_pct / 100
    if rule.modo == "marginal":
        total = 0.0
        for t in rule.tramos:
            if base <= t.desde:
                break
            total += (min(base, t.hasta) - t.desde) * t.tipo_pct / 100
        return total
    raise ValueError(f"modo desconocido: {rule.modo}")


def effective_rate_pct(rule: ReglaFiscal, base: float) -> float:
    return tax_amount(rule, base) / base * 100 if base > 0 else 0.0


# ───────────────────────── Aranceles ─────────────────────────
@lru_cache(maxsize=2)
def load_aranceles(path: str | None = None) -> dict:
    with open(Path(path) if path else ARANCELES_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _escala(base: float, cfg: dict) -> float:
    importe = cfg["cuota_fija_hasta"]["importe"]
    inf = cfg["cuota_fija_hasta"]["limite"]
    for tr in cfg["tramos"]:
        sup = INF if tr["hasta"] is None else tr["hasta"]
        if base <= inf:
            break
        importe += (min(base, sup) - inf) * tr["por_mil"] / 1000
        inf = sup
    return importe


def arancel(tipo: str, base: float, prestamo_hipotecario: bool = False, cfg: dict | None = None) -> float:
    """Derechos arancelarios base (Número 2), con reducciones y rebaja general del 5 %.
    ``tipo``: 'notaria' | 'registro'. No incluye folios, copias, suplidos ni IVA."""
    cfg = (cfg or load_aranceles())[tipo]
    limite_libre = cfg.get("limite_superior_regulado")
    if limite_libre and base > limite_libre:
        raise ValueError(f"Base {base} por encima del máximo regulado del arancel de {tipo}")
    imp = _escala(base, cfg)
    if prestamo_hipotecario:
        imp *= cfg["reduccion_prestamo_hipotecario_factor"]
    if cfg.get("minimo") is not None:
        imp = max(imp, cfg["minimo"])
    if cfg.get("maximo") is not None:
        imp = min(imp, cfg["maximo"])
    return imp * (1 - cfg["rebaja_general_pct"] / 100)
