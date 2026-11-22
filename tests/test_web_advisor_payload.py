"""Regresión B1 (revisión independiente): el servicio de la app debe traducir su formulario al esquema del motor."""
from Web.atalaya.services import advisor_service as a


def test_formulario_se_traduce_al_motor():
    r = a.simulate({"prov_code": "28", "ahorro_disponible": 60000, "ingresos_netos_mensuales": 3200, "edad": 34,
                    "plazo_anios": 25, "precio_vivienda": 250000, "tipo_interes": "variable",
                    "tipo_vivienda": "segunda_mano"})
    assert r["status"] == "ok"
    assert "financiacion" in r["result"]


def test_vivienda_nueva_mapea_tipo():
    p = a.to_engine_payload(a.validate_payload({"prov_code": "08", "ahorro_disponible": 50000, "ingresos_netos_mensuales": 3000,
                                                 "edad": 30, "plazo_anios": 30, "precio_vivienda": 300000, "tipo_vivienda": "nueva"}))
    assert p["tipo_vivienda"] == "nueva" and p["provincia"] == "08" and p["aportacion"] == 50000
