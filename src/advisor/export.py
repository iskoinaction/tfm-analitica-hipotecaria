"""Exporta artefactos para la web de presentación (validación de su implementación JS del simulador).

- ``artifacts/advisor/test_vectors.json``: casos (entrada -> salidas numéricas clave) generados por ``simulate``.
- ``artifacts/advisor/fiscal_tables.json``: reglas fiscales con vigencias + aranceles + política.
Uso: ``python -m src.advisor.export``.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import fiscal
from .engine import load_policy, simulate

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "advisor"
FECHA = "2026-11-22"   # fecha de operación fija para que los vectores sean reproducibles

CASES = [
    ("madrid_usada_fija_usuario", dict(provincia="28", precio_vivienda=250000, aportacion=60000, ingresos_netos_mensuales=3000, edad=32, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("madrid_nueva_variable_usuario", dict(provincia="28", precio_vivienda=250000, tipo_vivienda="nueva", aportacion=70000, ingresos_netos_mensuales=3000, edad=32, plazo_anios=30, modalidad="variable", tin_pct=3.2)),
    ("madrid_nueva_ajd_tramo_120k", dict(provincia="28", precio_vivienda=110000, tipo_vivienda="nueva", aportacion=40000, ingresos_netos_mensuales=1800, edad=28, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("barcelona_usada_tramos_itp", dict(provincia="08", precio_vivienda=700000, aportacion=250000, ingresos_netos_mensuales=8000, edad=45, plazo_anios=25, modalidad="fijo", tin_pct=2.9)),
    ("baleares_usada_tramos_itp", dict(provincia="07", precio_vivienda=650000, aportacion=200000, ingresos_netos_mensuales=7000, edad=40, plazo_anios=25, modalidad="fijo", tin_pct=3.1)),
    ("valencia_nueva_vivienda_habitual_ajd_0_1", dict(provincia="46", precio_vivienda=200000, tipo_vivienda="nueva", vivienda_habitual=True, aportacion=60000, ingresos_netos_mensuales=2600, edad=35, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("valencia_nueva_no_habitual_ajd_1_4", dict(provincia="46", precio_vivienda=200000, tipo_vivienda="nueva", vivienda_habitual=False, aportacion=60000, ingresos_netos_mensuales=2600, edad=35, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("valencia_usada_mas_1M_11pct", dict(provincia="46", precio_vivienda=1200000, aportacion=500000, ingresos_netos_mensuales=15000, edad=50, plazo_anios=20, modalidad="fijo", tin_pct=3.0)),
    ("cyl_usada_exceso_250k", dict(provincia="47", precio_vivienda=300000, aportacion=90000, ingresos_netos_mensuales=4000, edad=38, plazo_anios=30, modalidad="variable", tin_pct=3.3)),
    ("ceuta_usada_bonificada", dict(provincia="51", precio_vivienda=150000, aportacion=40000, ingresos_netos_mensuales=2200, edad=30, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("canarias_nueva_igic_no_modelado", dict(provincia="35", precio_vivienda=200000, tipo_vivienda="nueva", aportacion=60000, ingresos_netos_mensuales=2500, edad=33, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("navarra_no_verificado", dict(provincia="31", precio_vivienda=220000, aportacion=60000, ingresos_netos_mensuales=2800, edad=36, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("mixto_5_anios", dict(provincia="41", precio_vivienda=200000, aportacion=60000, ingresos_netos_mensuales=2500, edad=34, plazo_anios=30, modalidad="mixto", tin_pct=2.5, tin_variable_pct=3.8, anios_fijos=5)),
    ("variable_semaforo_rojo", dict(provincia="08", precio_vivienda=400000, aportacion=110000, ingresos_netos_mensuales=3200, edad=35, plazo_anios=30, modalidad="variable", tin_pct=3.4, otras_deudas_mensuales=300)),
    ("edad_60_plazo_recortado", dict(provincia="18", precio_vivienda=180000, aportacion=80000, ingresos_netos_mensuales=3000, edad=60, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("14_pagas_y_tasacion_inferior", dict(provincia="15", precio_vivienda=200000, valor_tasacion=180000, aportacion=50000, numero_pagas=14, ingresos_netos_mensuales=2000, edad=31, plazo_anios=30, modalidad="fijo", tin_pct=3.0)),
    ("tin_cero", dict(provincia="50", precio_vivienda=150000, aportacion=50000, ingresos_netos_mensuales=2000, edad=30, plazo_anios=10, modalidad="fijo", tin_pct=0.0)),
    ("aportacion_cubre_todo", dict(provincia="28", precio_vivienda=150000, aportacion=200000, ingresos_netos_mensuales=2000, edad=40, plazo_anios=20, modalidad="fijo", tin_pct=3.0)),
]


def _key(r: dict) -> dict:
    return {
        "capital_prestamo": r["financiacion"]["capital_prestamo"], "plazo_meses": r["financiacion"]["plazo_meses"],
        "tin_inicial_pct": r["tipo_interes"]["tin_inicial_pct"], "cuota_mensual": r["cuota"]["mensual_inicial"],
        "cuota_estres": r["esfuerzo"]["cuota_estres"], "total_intereses": r["cuota"]["total_intereses"],
        "gastos": {l["concepto"]: l["importe"] for l in r["gastos"]["lineas"]},
        "gastos_total_cliente": r["gastos"]["total_cliente"],
        "entrada_necesaria_para_ltv_referencia": r["financiacion"]["entrada_necesaria_para_ltv_referencia"],
        "ltv": r["financiacion"]["ltv"], "lti": r["financiacion"]["lti"], "dsti": r["esfuerzo"]["dsti"],
        "dsti_estres": r["esfuerzo"]["dsti_estres"], "semaforo": r["semaforo"]["color"],
        "tin_tramo_variable_pct": r["tipo_interes"].get("tin_tramo_variable_pct"),
        "cuota_tras_periodo_fijo": r["tipo_interes"].get("cuota_tras_periodo_fijo"),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    vectors = []
    for name, payload in CASES:
        p = dict(payload, fecha_operacion=FECHA)
        vectors.append({"id": name, "entrada": p, "salida": _key(simulate(p))})
    meta = {"generado": dt.date.today().isoformat(), "motor": "src.advisor.simulate", "tolerancia_eur": 0.01,
            "nota": "Todos los casos usan tin_pct explícito para no depender del dato de mercado; fecha_operacion fija.",
            "politica": load_policy()}
    (OUT / "test_vectors.json").write_text(json.dumps({"meta": meta, "casos": vectors}, indent=1, ensure_ascii=False), encoding="utf-8")
    rules = fiscal.load_rules()
    ft = {"generado": dt.date.today().isoformat(),
          "fuente": "data/metadata/fiscalidad_vigencias.csv (verificada contra la API de legislación consolidada del BOE; ver fiscal_verification.json)",
          "formato_tramos": "modo unico_por_valor: un tipo según el valor total sobre toda la base; modo marginal: cada tramo a su tipo",
          "reglas": [r.to_dict() for r in rules], "aranceles": fiscal.load_aranceles()}
    (OUT / "fiscal_tables.json").write_text(json.dumps(ft, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(vectors), "vectores;", len(rules), "reglas")


if __name__ == "__main__":
    main()
