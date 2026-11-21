"""Utilidades comunes para los scripts de verificación de fuentes (auditoría 10_fuentes).

Solo lectura de APIs públicas. Sin credenciales.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]          # raíz del repo
HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples"
SAMPLES.mkdir(exist_ok=True)

UA = {"User-Agent": "tfm-audit-source-check/0.1 (academic, read-only)"}
INE = "https://servicios.ine.es/wstempus/js/ES"


def get(url, params=None, timeout=120, retries=3, as_json=True, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=h)
            r.raise_for_status()
            return r.json() if as_json else r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def ine_ts_to_date(ms):
    """Fecha INE (ms epoch, medianoche hora de Madrid) -> date local."""
    # INE devuelve medianoche Europe/Madrid expresada en UTC (p.ej. 23:00 del día anterior).
    d = dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc) + dt.timedelta(hours=3)
    return d.date()


def ine_table(table_id, nult=None, date=None, tip=None):
    """Descarga DATOS_TABLA del INE -> DataFrame largo (cod, nombre, fecha, anyo, periodo, valor)."""
    params = {}
    if nult:
        params["nult"] = nult
    if date:
        params["date"] = date
    if tip:
        params["tip"] = tip
    data = get(f"{INE}/DATOS_TABLA/{table_id}", params=params)
    rows = []
    for s in data:
        for o in s.get("Data", []):
            rows.append(
                {
                    "cod": s["COD"],
                    "nombre": s["Nombre"].strip(),
                    "fecha": ine_ts_to_date(o["Fecha"]),
                    "anyo": o.get("Anyo"),
                    "fk_periodo": o.get("FK_Periodo"),
                    "tipo_dato": o.get("FK_TipoDato"),
                    "valor": o.get("Valor"),
                }
            )
    return pd.DataFrame(rows)


def ine_series(cod, nult=None, date=None):
    params = {}
    if nult:
        params["nult"] = nult
    if date:
        params["date"] = date
    s = get(f"{INE}/DATOS_SERIE/{cod}", params=params)
    df = pd.DataFrame(s["Data"])
    df["fecha"] = df["Fecha"].map(ine_ts_to_date)
    return s, df


def ecb(flow_key, start=None, end=None):
    """ECB Data Portal API (SDMX 2.1) en CSV."""
    url = f"https://data-api.ecb.europa.eu/service/data/{flow_key}"
    params = {"format": "csvdata"}
    if start:
        params["startPeriod"] = start
    if end:
        params["endPeriod"] = end
    r = get(url, params=params, as_json=False)
    from io import StringIO

    return pd.read_csv(StringIO(r.text))


def eurostat(dataset, **filters):
    url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"
    params = {"format": "JSON", "lang": "EN"}
    params.update(filters)
    return get(url, params=params)


def eurostat_to_df(js):
    """JSON-stat 2.0 de Eurostat -> DataFrame largo."""
    import itertools

    ids = js["id"]
    sizes = js["size"]
    cats = []
    for d in ids:
        idx = js["dimension"][d]["category"]["index"]
        inv = sorted(idx, key=lambda k: idx[k])
        cats.append(inv)
    vals = js["value"]
    rows = []
    for flat, combo in enumerate(itertools.product(*cats)):
        v = vals.get(str(flat))
        if v is not None:
            rows.append(dict(zip(ids, combo), value=v))
    return pd.DataFrame(rows)


def save_sample(name, obj):
    p = SAMPLES / name
    if isinstance(obj, pd.DataFrame):
        obj.to_csv(p, index=False)
    else:
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    return p


def load_panel():
    return pd.read_csv(ROOT / "notebooks acabados" / "dataset_final_tfm.csv")


# ---------------------------------------------------------------------------
# Provincias: código INE (2 dígitos) <-> nombre INE <-> nombre usado en el panel v1
# ---------------------------------------------------------------------------
PROV = {
    "01": ("Araba/Álava", "Álava"), "02": ("Albacete", "Albacete"), "03": ("Alicante/Alacant", "Alicante"),
    "04": ("Almería", "Almería"), "05": ("Ávila", "Ávila"), "06": ("Badajoz", "Badajoz"),
    "07": ("Balears, Illes", "Islas Baleares"), "08": ("Barcelona", "Barcelona"), "09": ("Burgos", "Burgos"),
    "10": ("Cáceres", "Cáceres"), "11": ("Cádiz", "Cádiz"), "12": ("Castellón/Castelló", "Castellón"),
    "13": ("Ciudad Real", "Ciudad Real"), "14": ("Córdoba", "Córdoba"), "15": ("Coruña, A", "A Coruña"),
    "16": ("Cuenca", "Cuenca"), "17": ("Girona", "Girona"), "18": ("Granada", "Granada"),
    "19": ("Guadalajara", "Guadalajara"), "20": ("Gipuzkoa", "Guipúzcoa"), "21": ("Huelva", "Huelva"),
    "22": ("Huesca", "Huesca"), "23": ("Jaén", "Jaén"), "24": ("León", "León"), "25": ("Lleida", "Lleida"),
    "26": ("Rioja, La", "La Rioja"), "27": ("Lugo", "Lugo"), "28": ("Madrid", "Comunidad de Madrid"),
    "29": ("Málaga", "Málaga"), "30": ("Murcia", "Región de Murcia"), "31": ("Navarra", "Comunidad Foral de Navarra"),
    "32": ("Ourense", "Ourense"), "33": ("Asturias", "Principado de Asturias"), "34": ("Palencia", "Palencia"),
    "35": ("Palmas, Las", "Las Palmas"), "36": ("Pontevedra", "Pontevedra"), "37": ("Salamanca", "Salamanca"),
    "38": ("Santa Cruz de Tenerife", "Santa Cruz de Tenerife"), "39": ("Cantabria", "Cantabria"),
    "40": ("Segovia", "Segovia"), "41": ("Sevilla", "Sevilla"), "42": ("Soria", "Soria"),
    "43": ("Tarragona", "Tarragona"), "44": ("Teruel", "Teruel"), "45": ("Toledo", "Toledo"),
    "46": ("Valencia/València", "Valencia"), "47": ("Valladolid", "Valladolid"), "48": ("Bizkaia", "Vizcaya"),
    "49": ("Zamora", "Zamora"), "50": ("Zaragoza", "Zaragoza"), "51": ("Ceuta", "Ceuta"), "52": ("Melilla", "Melilla"),
}
INE_ALIASES = {"Alacant/Alicante": "03", "A Coruña": "15", "Coruña (A)": "15", "Palmas (Las)": "35",
               "Rioja (La)": "26", "Balears (Illes)": "07", "Castelló/Castellón": "12", "València/Valencia": "46"}
PANEL2CODE = {v[1]: k for k, v in PROV.items()}
INE2CODE = {v[0]: k for k, v in PROV.items()}
INE2CODE.update(INE_ALIASES)


def prov_code_from_ine_name(nombre):
    """Devuelve el código de provincia si algún token (separado por '. ') es un nombre INE de provincia."""
    toks = [t.strip().rstrip(".") for t in nombre.split(". ")]
    for t in toks:
        t2 = __import__("re").sub(r"^\d{2}\s+", "", t)
        if t2 in INE2CODE:
            return INE2CODE[t2]
    return None


def quarter_start(d):
    d = pd.Timestamp(d)
    return pd.Timestamp(year=d.year, month=3 * ((d.month - 1) // 3) + 1, day=1)
