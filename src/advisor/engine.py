"""Motor del asesor hipotecario v2 (puro, sin Flask).

Es un SIMULADOR de capacidad de pago y gastos con un ESTIMADOR de tipo de mercado. No es un modelo de pricing ni un
motor de admisión: no emite "aprobada/denegada" ni evalúa la solvencia en el sentido de la Ley 5/2019.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from src.common import geography as geo

from . import fiscal
from .amortization import capital_maximo_por_cuota, cuadro_anual, cuota_francesa, saldo_tras
from .market import load_market, load_scenarios, market_reference

ROOT = Path(__file__).resolve().parents[2]
POLICY_YAML = ROOT / "data" / "metadata" / "advisor_policy.yaml"
PANEL_PROV = ROOT / "data" / "processed" / "panel_trimestral.csv"
VERSION = "2.0.0"

AVISOS_LEGALES = [
    "Simulación orientativa con fines académicos (Atalaya · Analítica Hipotecaria). No es una oferta vinculante, ni una "
    "evaluación de solvencia, ni asesoramiento en el sentido del art. 19 de la Ley 5/2019.",
    "Los tipos de referencia son medias de mercado publicadas por el BCE (se indica el periodo), no el precio que "
    "ofrecería una entidad concreta. La TAE de una oferta real depende de comisiones y productos vinculados.",
    "Los umbrales de esfuerzo (DSTI), LTV, LTI, estrés de tipos y edad máxima son parámetros ILUSTRATIVOS y "
    "configurables; no son límites legales.",
    "Los gastos de notaría y registro de la escritura de préstamo, la gestoría y el AJD del préstamo corresponden a la "
    "entidad prestamista (Ley 5/2019, art. 14.1.e; art. 29 TRLITPAJD tras el RDL 17/2018). La tasación corre a cargo "
    "del cliente.",
    "Los impuestos dependen de la CCAA y de circunstancias personales; los tipos reducidos (jóvenes, familia numerosa, "
    "discapacidad, renta) no se aplican automáticamente. Compruebe la normativa vigente.",
]


class AdvisorInputError(ValueError):
    """Error de validación de la entrada. ``errors`` = [{"campo":..., "mensaje":...}]."""

    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("; ".join(f"{e['campo']}: {e['mensaje']}" for e in errors))


@lru_cache(maxsize=1)
def load_policy(path: str | None = None) -> dict:
    return yaml.safe_load(open(path or POLICY_YAML, encoding="utf-8"))


@lru_cache(maxsize=1)
def _market() -> pd.DataFrame:
    return load_market()


@lru_cache(maxsize=1)
def _scenarios() -> dict:
    return load_scenarios()


@lru_cache(maxsize=1)
def mivau_prices() -> dict:
    """Último precio m² MIVAU (valor tasado de vivienda libre) por provincia: {code: (valor, periodo)}."""
    if not PANEL_PROV.exists():
        return {}
    d = pd.read_csv(PANEL_PROV, usecols=["prov_code", "period", "precio_m2_mivau_tasado"]).dropna()
    d = d.sort_values("period").groupby("prov_code").tail(1)
    return {str(int(r.prov_code)).zfill(2): (float(r.precio_m2_mivau_tasado), r.period) for r in d.itertuples()}


# ───────────────────────── Validación ─────────────────────────
def _num(p, k, errs, req=False, lo=None, hi=None, default=None, integer=False):
    v = p.get(k, None)
    if v is None or v == "":
        if req:
            errs.append({"campo": k, "mensaje": "obligatorio"})
        return default
    try:
        v = float(v)
    except (TypeError, ValueError):
        errs.append({"campo": k, "mensaje": f"debe ser numérico (recibido {v!r})"})
        return default
    if v != v or v in (float("inf"), float("-inf")):
        errs.append({"campo": k, "mensaje": "valor no finito"})
        return default
    if integer and v != int(v):
        errs.append({"campo": k, "mensaje": "debe ser entero"})
    if lo is not None and v < lo:
        errs.append({"campo": k, "mensaje": f"debe ser >= {lo}"})
    if hi is not None and v > hi:
        errs.append({"campo": k, "mensaje": f"debe ser <= {hi}"})
    return int(v) if integer else v


def validate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise AdvisorInputError([{"campo": "payload", "mensaje": "debe ser un objeto JSON"}])
    p, errs = payload, []
    pol = load_policy()
    out = {}
    try:
        out["prov_code"] = geo.province_code(p.get("provincia", ""))
    except KeyError:
        errs.append({"campo": "provincia", "mensaje": f"provincia no reconocida: {p.get('provincia')!r} (use código INE 01-52 o nombre oficial)"})
    out["precio_vivienda"] = _num(p, "precio_vivienda", errs, lo=1000, hi=50_000_000)
    out["superficie_m2"] = _num(p, "superficie_m2", errs, lo=10, hi=2000)
    if out["precio_vivienda"] is None and out["superficie_m2"] is None:
        errs.append({"campo": "precio_vivienda", "mensaje": "indique precio_vivienda o superficie_m2 (estimación con precio m² MIVAU)"})
    out["tipo_vivienda"] = p.get("tipo_vivienda", "usada")
    if out["tipo_vivienda"] not in ("usada", "nueva"):
        errs.append({"campo": "tipo_vivienda", "mensaje": "valores: 'usada' | 'nueva'"})
    out["vivienda_habitual"] = bool(p.get("vivienda_habitual", True))
    out["aportacion"] = _num(p, "aportacion", errs, req=True, lo=0)
    out["valor_tasacion"] = _num(p, "valor_tasacion", errs, lo=1000)
    out["numero_pagas"] = _num(p, "numero_pagas", errs, lo=12, hi=14, default=12, integer=True)
    if out["numero_pagas"] not in (12, 14, None):
        errs.append({"campo": "numero_pagas", "mensaje": "valores: 12 | 14"})
    out["ingresos_netos_mensuales"] = _num(p, "ingresos_netos_mensuales", errs, req=True, lo=0, hi=1_000_000)
    out["otras_deudas_mensuales"] = _num(p, "otras_deudas_mensuales", errs, lo=0, default=0.0)
    out["edad"] = _num(p, "edad", errs, req=True, lo=18, hi=100, integer=True)
    out["plazo_anios"] = _num(p, "plazo_anios", errs, lo=1, hi=40, default=25, integer=True)
    out["modalidad"] = p.get("modalidad", "fijo")
    if out["modalidad"] not in ("fijo", "variable", "mixto"):
        errs.append({"campo": "modalidad", "mensaje": "valores: 'fijo' | 'variable' | 'mixto'"})
    out["tin_pct"] = _num(p, "tin_pct", errs, lo=-1, hi=20)
    out["diferencial_pct"] = _num(p, "diferencial_pct", errs, lo=-1, hi=10)
    out["anios_fijos"] = _num(p, "anios_fijos", errs, lo=1, hi=30, integer=True,
                              default=pol["mercado"]["mixto_anios_fijos_por_defecto"])
    out["gastos_tasacion"] = _num(p, "gastos_tasacion", errs, lo=0, hi=10000, default=pol["gastos_supuestos"]["tasacion_eur"])
    out["gestoria_compraventa"] = _num(p, "gestoria_compraventa", errs, lo=0, hi=10000,
                                       default=pol["gastos_supuestos"]["gestoria_compraventa_eur"])
    f = p.get("fecha_operacion")
    try:
        out["fecha_operacion"] = dt.date.fromisoformat(f) if f else dt.date.today()
    except (TypeError, ValueError):
        errs.append({"campo": "fecha_operacion", "mensaje": "formato AAAA-MM-DD"})
    out["escenario_anio"] = _num(p, "escenario_anio", errs, lo=2026, hi=2035, integer=True)
    out["escenario"] = p.get("escenario", "base")
    if out["escenario"] not in ("base", "adverso", "favorable"):
        errs.append({"campo": "escenario", "mensaje": "valores: 'base' | 'adverso' | 'favorable'"})
    unknown = set(p) - {"provincia", "precio_vivienda", "superficie_m2", "tipo_vivienda", "vivienda_habitual", "aportacion",
                        "valor_tasacion", "numero_pagas", "ingresos_netos_mensuales", "otras_deudas_mensuales", "edad",
                        "plazo_anios", "modalidad", "tin_pct", "diferencial_pct", "anios_fijos", "gastos_tasacion",
                        "gestoria_compraventa", "fecha_operacion", "escenario_anio", "escenario"}
    if unknown:
        errs.append({"campo": ",".join(sorted(unknown)), "mensaje": "campos no reconocidos"})
    if errs:
        raise AdvisorInputError(errs)
    return out


# ───────────────────────── Gastos ─────────────────────────
def _linea(concepto, importe, rule=None, base=None, a_cargo="cliente", **kw):
    d = {"concepto": concepto, "importe": round(importe, 2), "a_cargo": a_cargo}
    if base is not None:
        d["base"] = round(base, 2)
    if rule is not None:
        d.update({"tipo_efectivo_pct": round(fiscal.effective_rate_pct(rule, base), 4) if base else None,
                  "regla_id": rule.id, "norma": f"{rule.norma}, art. {rule.articulo}" if rule.articulo else rule.norma,
                  "url_fuente": rule.url_fuente, "verificado": rule.verificado,
                  "vigente_desde": rule.vigente_desde.isoformat() if rule.vigente_desde else None})
    d.update(kw)
    return d


def compute_gastos(precio: float, ccaa: str, tipo_vivienda: str, vivienda_habitual: bool, fecha: dt.date,
                   tasacion: float, gestoria: float) -> tuple[list, list]:
    lineas, avisos = [], []
    cond = {"vivienda_habitual"} if vivienda_habitual else set()
    if tipo_vivienda == "usada":
        r = fiscal.select_rule(ccaa, "ITP", "vivienda_usada", fecha, cond)
        if r is None:
            avisos.append("No hay regla de ITP vigente para la fecha indicada: impuesto no calculado.")
        else:
            lineas.append(_linea("ITP (transmisiones patrimoniales onerosas)", fiscal.tax_amount(r, precio), r, precio))
    else:
        ind = None
        for imp in ("IGIC", "IPSI", "IVA"):
            ind = fiscal.select_rule(ccaa, imp, "vivienda_nueva", fecha, cond)
            if ind:
                break
        if ind is None or not ind.modelado:
            avisos.append(f"Impuesto indirecto de la vivienda nueva NO MODELADO en este territorio ({ind.impuesto if ind else 'sin regla'}): "
                          "el total de gastos lo excluye.")
        else:
            lineas.append(_linea(f"{ind.impuesto} vivienda nueva", fiscal.tax_amount(ind, precio), ind, precio))
        r = fiscal.select_rule(ccaa, "AJD", "vivienda_nueva", fecha, cond)
        if r is None:
            avisos.append("No hay regla de AJD vigente para la fecha indicada: impuesto no calculado.")
        else:
            lineas.append(_linea("AJD (escritura de compraventa)", fiscal.tax_amount(r, precio), r, precio))
    # Aranceles base de la compraventa + IVA
    ar = fiscal.load_aranceles()
    iva = fiscal.select_rule(ccaa, "IVA_honorarios", "aranceles", fecha)
    iva_pct = iva.tramos[0].tipo_pct if (iva and ccaa not in ("05", "18", "19")) else 0.0
    for tipo, nombre in (("notaria", "Notaría compraventa (arancel base)"), ("registro", "Registro de la Propiedad compraventa (arancel base)")):
        base_ar = fiscal.arancel(tipo, precio)
        lineas.append(_linea(nombre, base_ar * (1 + iva_pct / 100), base=precio, a_cargo="cliente",
                             arancel_sin_iva=round(base_ar, 2), iva_pct=iva_pct, norma=ar[tipo]["norma"],
                             url_fuente=ar[tipo]["url_fuente"], verificado=ar[tipo]["verificado"],
                             nota="Cota inferior: no incluye folios, copias ni suplidos"))
    if ccaa in ("05", "18", "19"):
        avisos.append("Fuera del territorio IVA no se suma IVA a los aranceles (IGIC/IPSI no modelados).")
    lineas.append(_linea("Tasación (a cargo del cliente, Ley 5/2019 art. 14.1.e)", tasacion, a_cargo="cliente",
                         norma=ar["reparto_gastos_prestamo"]["norma"], url_fuente=ar["reparto_gastos_prestamo"]["url_fuente"],
                         verificado=True, nota="importe = supuesto editable"))
    if gestoria:
        lineas.append(_linea("Gestoría de la compraventa (opcional)", gestoria, a_cargo="cliente", nota="supuesto editable"))
    for l in lineas:
        if l.get("verificado") is False:
            avisos.append(f"'{l['concepto']}': tipo NO VERIFICADO en boletín oficial ({l.get('norma')}). Use el resultado con cautela.")
    return lineas, avisos


# ───────────────────────── Tipo de interés ─────────────────────────
def resolve_rate(v: dict, pol: dict) -> tuple[dict, list]:
    avisos = []
    mk = market_reference(v["modalidad"], _market(), pol["mercado"]["ventana_trimestres"])
    info = {"modalidad": v["modalidad"], "referencia_mercado": mk}
    eur_ref = mk["euribor_12m"]["ultimo"]
    dif = v["diferencial_pct"] if v["diferencial_pct"] is not None else mk.get("diferencial_referencia")
    if v["escenario_anio"]:
        sc = _scenarios()
        vals = sc["valores"].get(str(v["escenario_anio"]))
        if not vals or v["escenario"] not in vals:
            raise AdvisorInputError([{"campo": "escenario_anio", "mensaje": f"sin escenario para {v['escenario_anio']}/{v['escenario']}"}])
        eur = vals[v["escenario"]]
        info["escenario"] = {"anio": v["escenario_anio"], "nombre": v["escenario"], "euribor_12m": eur,
                             "fuente": sc["fuente"], "nota": sc.get("nota", ""),
                             "etiqueta": f"ESCENARIO {v['escenario'].upper()} {v['escenario_anio']} (supuesto, no predicción)"}
        avisos.append(f"Tipo construido sobre un ESCENARIO de Euríbor {v['escenario_anio']} ({v['escenario']}); no es una predicción.")
    else:
        eur = eur_ref
    if v["modalidad"] == "fijo":
        if v["tin_pct"] is not None:
            tin, origen = v["tin_pct"], "usuario"
        elif v["escenario_anio"]:
            j = _market()[["tedr_vivienda", "euribor_12m"]].dropna().iloc[-pol["mercado"]["ventana_trimestres"]:]
            tin, origen = eur + float((j["tedr_vivienda"] - j["euribor_12m"]).mean()), "escenario"
            avisos.append("Fijo en escenario: Euríbor del escenario + diferencial medio reciente TEDR−Euríbor (aproximación).")
        else:
            tin, origen = mk["tin_referencia"], "mercado"
        info.update({"tin_inicial_pct": round(tin, 4), "origen": origen})
    else:
        tin_var = (eur + dif) if (v["tin_pct"] is None or v["modalidad"] == "mixto") else v["tin_pct"]
        if v["modalidad"] == "variable":
            origen = "usuario" if v["tin_pct"] is not None else ("escenario" if v["escenario_anio"] else "mercado")
            info.update({"tin_inicial_pct": round(tin_var, 4), "euribor_usado": eur, "diferencial_usado": dif, "origen": origen})
        else:  # mixto
            tin_fijo = v["tin_pct"] if v["tin_pct"] is not None else mk["tin_referencia"]
            info.update({"tin_inicial_pct": round(tin_fijo, 4), "tin_tramo_variable_pct": round(eur + dif, 4),
                         "euribor_usado": eur, "diferencial_usado": dif, "anios_fijos": v["anios_fijos"],
                         "origen": "usuario" if v["tin_pct"] is not None else "mercado"})
        if v["diferencial_pct"] is None:
            avisos.append("Diferencial de mercado de referencia (proxy BCE); introduzca el de su oferta para afinar.")
    if info["origen"] == "mercado":
        avisos.append("TIN = referencia de mercado (media BCE); la oferta de una entidad puede ser distinta.")
    return info, avisos


# ───────────────────────── Simulación ─────────────────────────
def simulate(payload: dict) -> dict:
    v = validate(payload)
    pol = load_policy()
    prov = geo.PROVINCES[v["prov_code"]]
    ccaa = prov.ccaa_code
    avisos, supuestos = [], []

    # Precio
    mv = mivau_prices().get(v["prov_code"])
    if v["precio_vivienda"] is not None:
        precio, precio_origen = v["precio_vivienda"], "usuario"
    else:
        if not mv:
            raise AdvisorInputError([{"campo": "superficie_m2", "mensaje": "no hay precio m² MIVAU para la provincia"}])
        precio, precio_origen = mv[0] * v["superficie_m2"], "estimado_mivau"
        supuestos.append(f"Precio estimado = {v['superficie_m2']:.0f} m² × {mv[0]:.1f} €/m² (MIVAU valor tasado vivienda libre, {mv[1]}).")
    tasacion = v["valor_tasacion"] if v["valor_tasacion"] is not None else precio
    if v["valor_tasacion"] is None:
        supuestos.append("Valor de tasación = precio (no indicado).")
    base_garantia = min(precio, tasacion)

    lineas, av = compute_gastos(precio, ccaa, v["tipo_vivienda"], v["vivienda_habitual"], v["fecha_operacion"],
                                v["gastos_tasacion"], v["gestoria_compraventa"])
    avisos += av
    gastos_cliente = sum(l["importe"] for l in lineas if l["a_cargo"] == "cliente")

    # Financiación
    capital = max(precio + gastos_cliente - v["aportacion"], 0.0)
    ltv_ref = pol["ltv"]["referencia"]
    entrada_ltv = max(precio + gastos_cliente - ltv_ref * base_garantia, 0.0)
    ingresos = v["ingresos_netos_mensuales"] * v["numero_pagas"] / 12
    if v["numero_pagas"] == 14:
        supuestos.append("Ingresos mensuales indicados por paga; se prorratean 14 pagas en 12 meses.")
    ltv = capital / base_garantia if base_garantia else None
    lti = capital / (12 * ingresos) if ingresos > 0 else None
    edad_max = pol["edad"]["maxima_al_vencimiento"]
    plazo_max = min(pol["plazo"]["maximo_anios"], edad_max - v["edad"])
    plazo = v["plazo_anios"]
    if plazo > pol["plazo"]["maximo_anios"]:
        avisos.append(f"Plazo solicitado superior al máximo ilustrativo ({pol['plazo']['maximo_anios']} años): se mantiene, revise.")
    if v["edad"] + plazo > edad_max:
        if plazo_max >= 1:
            avisos.append(f"Con {v['edad']} años y {plazo} años de plazo se superarían los {edad_max} años al vencimiento "
                          f"(práctica de mercado, no límite legal): se simula con {plazo_max} años.")
            plazo = plazo_max
        else:
            avisos.append(f"La edad supera la referencia de {edad_max} años al vencimiento (práctica de mercado): "
                          "se simula con el plazo solicitado, pero es poco habitual en el mercado.")
    n = plazo * 12

    rate, av = resolve_rate(v, pol)
    avisos += av
    est_pp = pol["estres"]["incremento_tipo_pp"]
    if v["modalidad"] == "mixto":
        nf = min(v["anios_fijos"] * 12, n)
        tramos = [(nf, rate["tin_inicial_pct"]), (n - nf, rate["tin_tramo_variable_pct"])] if n > nf else [(n, rate["tin_inicial_pct"])]
        cuota = cuota_francesa(capital, rate["tin_inicial_pct"], n)
        saldo = saldo_tras(capital, rate["tin_inicial_pct"], cuota, nf)
        cuota_post = cuota_francesa(saldo, rate["tin_tramo_variable_pct"], n - nf) if n > nf else cuota
        cuota_estres = cuota_francesa(saldo, rate["tin_tramo_variable_pct"] + est_pp, n - nf) if n > nf else cuota
        rate["cuota_tras_periodo_fijo"] = round(cuota_post, 2)
    else:
        tramos = [(n, rate["tin_inicial_pct"])]
        cuota = cuota_francesa(capital, rate["tin_inicial_pct"], n)
        cuota_estres = cuota_francesa(capital, rate["tin_inicial_pct"] + est_pp, n) if v["modalidad"] == "variable" else cuota
    cuadro = cuadro_anual(capital, tramos) if capital > 0 else []
    intereses = sum(f["intereses"] for f in cuadro)
    deudas = v["otras_deudas_mensuales"]
    dsti = (cuota + deudas) / ingresos if ingresos > 0 else None
    dsti_e = (cuota_estres + deudas) / ingresos if ingresos > 0 else None
    aplica_estres = v["modalidad"] in pol["estres"]["aplica_a"]
    dsti_eval = dsti_e if aplica_estres else dsti
    ref, alto = pol["dsti"]["referencia"], pol["dsti"]["esfuerzo_elevado"]
    if dsti_eval is None:
        color, motivo = "rojo", "Ingresos nulos: no es posible calcular el esfuerzo."
    elif dsti_eval > alto:
        color, motivo = "rojo", f"Esfuerzo elevado: DSTI{' con estrés' if aplica_estres else ''} {dsti_eval:.1%} > {alto:.0%} (umbral ilustrativo)."
    elif dsti_eval > ref:
        color, motivo = "ambar", f"Esfuerzo por encima de la referencia: DSTI{' con estrés' if aplica_estres else ''} {dsti_eval:.1%} entre {ref:.0%} y {alto:.0%}."
    else:
        color, motivo = "verde", f"Esfuerzo dentro de la referencia ilustrativa: DSTI{' con estrés' if aplica_estres else ''} {dsti_eval:.1%} <= {ref:.0%}."
    if ltv is not None and ltv > ltv_ref:
        avisos.append(f"LTV {ltv:.1%} > {ltv_ref:.0%} (referencia de mercado sobre min(precio, tasación)): la financiación "
                      "por encima suele requerir garantías adicionales (p. ej. Línea de Avales ICO para jóvenes, con requisitos).")
    if lti is not None and lti > pol["lti"]["referencia"]:
        avisos.append(f"LTI {lti:.1f} veces los ingresos netos anuales > {pol['lti']['referencia']} (orientativo).")
    if v["aportacion"] < gastos_cliente:
        avisos.append("La aportación no cubre los gastos de compra: las entidades no suelen financiarlos.")
    if capital == 0:
        avisos.append("La aportación cubre el precio y los gastos: no se necesita préstamo.")
    cuota_max = max(ref * ingresos - deudas, 0.0)
    cap_max = capital_maximo_por_cuota(cuota_max, (rate.get("tin_tramo_variable_pct", rate["tin_inicial_pct"]) + est_pp)
                                       if aplica_estres else rate["tin_inicial_pct"], n)

    return {
        "version_motor": VERSION, "naturaleza": "simulador orientativo (no oferta, no evaluación de solvencia)",
        "provincia": {"code": prov.code, "nombre": prov.name, "ccaa_code": ccaa, "ccaa": geo.CCAA[ccaa]},
        "fecha_operacion": v["fecha_operacion"].isoformat(),
        "precio": {"precio_vivienda": round(precio, 2), "origen": precio_origen, "valor_tasacion": round(tasacion, 2),
                   "referencia_mivau_m2": {"valor": mv[0], "periodo": mv[1], "fuente": "MIVAU, valor tasado medio de vivienda libre (panel_trimestral)"} if mv else None},
        "tipo_interes": rate,
        "gastos": {"lineas": lineas, "total_cliente": round(gastos_cliente, 2),
                   "a_cargo_del_banco": fiscal.load_aranceles()["reparto_gastos_prestamo"]["a_cargo_del_banco"],
                   "norma_reparto": fiscal.load_aranceles()["reparto_gastos_prestamo"]["norma"]},
        "financiacion": {"capital_prestamo": round(capital, 2), "aportacion": round(v["aportacion"], 2),
                         "entrada_necesaria_para_ltv_referencia": round(entrada_ltv, 2), "ltv_referencia": ltv_ref,
                         "ltv": round(ltv, 4) if ltv is not None else None, "lti": round(lti, 3) if lti is not None else None,
                         "plazo_anios": plazo, "plazo_meses": n, "edad_al_vencimiento": v["edad"] + plazo},
        "cuota": {"mensual_inicial": round(cuota, 2), "total_intereses": round(intereses, 2),
                  "total_pagado": round(intereses + capital, 2), "cuadro_anual": cuadro},
        "esfuerzo": {"ingresos_netos_mensuales_equivalentes": round(ingresos, 2), "otras_deudas_mensuales": deudas,
                     "dsti": round(dsti, 4) if dsti is not None else None,
                     "estres_aplicado": aplica_estres, "incremento_tipo_pp": est_pp if aplica_estres else 0.0,
                     "cuota_estres": round(cuota_estres, 2), "dsti_estres": round(dsti_e, 4) if dsti_e is not None else None,
                     "dsti_referencia": ref, "dsti_esfuerzo_elevado": alto,
                     "capital_maximo_en_referencia_dsti": round(cap_max, 2)},
        "semaforo": {"color": color, "motivo": motivo,
                     "nota": "Indicador de capacidad de pago con umbrales ilustrativos; no es una decisión de concesión."},
        "avisos": avisos, "avisos_legales": AVISOS_LEGALES, "supuestos": supuestos,
        "parametros": {"naturaleza": pol["naturaleza"], "dsti": ref, "dsti_esfuerzo_elevado": alto, "estres_pp": est_pp,
                       "edad_max_vencimiento": edad_max, "ltv_referencia": ltv_ref, "lti_referencia": pol["lti"]["referencia"]},
    }


def metadata() -> dict:
    pol = load_policy()
    mv = mivau_prices()
    rules = fiscal.load_rules()
    mk = _market()
    sc = _scenarios()
    return {
        "version_motor": VERSION,
        "provincias": [{"code": p.code, "nombre": p.name, "ccaa_code": p.ccaa_code, "ccaa": geo.CCAA[p.ccaa_code],
                        "precio_m2_mivau": mv.get(c, (None, None))[0], "periodo_precio_m2": mv.get(c, (None, None))[1]}
                       for c, p in geo.PROVINCES.items()],
        "ccaa": [{"code": k, "nombre": n} for k, n in geo.CCAA.items()],
        "parametros": pol,
        "fiscalidad": {"reglas": [r.to_dict() for r in rules],
                       "n_verificadas": sum(r.verificado for r in rules), "n_reglas": len(rules)},
        "aranceles": fiscal.load_aranceles(),
        "mercado": {"ultimo_periodo": str(mk["tedr_vivienda"].dropna().index[-1]),
                    "ultimo_periodo_tedr_variable": (str(mk["tedr_variable"].dropna().index[-1]) if mk["tedr_variable"].notna().any() else None)},
        "escenarios": sc,
        "entrada": {"obligatorios": ["provincia", "aportacion", "ingresos_netos_mensuales", "edad", "precio_vivienda|superficie_m2"],
                    "opcionales": {"tipo_vivienda": "usada|nueva", "vivienda_habitual": True, "valor_tasacion": None,
                                   "numero_pagas": 12, "otras_deudas_mensuales": 0, "plazo_anios": 25,
                                   "modalidad": "fijo|variable|mixto", "tin_pct": None, "diferencial_pct": None,
                                   "anios_fijos": pol["mercado"]["mixto_anios_fijos_por_defecto"],
                                   "gastos_tasacion": pol["gastos_supuestos"]["tasacion_eur"], "gestoria_compraventa": 0,
                                   "fecha_operacion": "AAAA-MM-DD (hoy)", "escenario_anio": None, "escenario": "base|adverso|favorable"}},
        "avisos_legales": AVISOS_LEGALES,
    }
