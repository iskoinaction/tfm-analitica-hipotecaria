"""Asistente conversacional OPCIONAL (desactivado por defecto).

Reglas (arbitraje del coordinador, fase IX):
* Sólo se activa con ``ASSISTANT_ENABLED=1`` **y** ``GEMINI_API_KEY``.
* El contexto son exclusivamente artefactos agregados del proyecto (métricas y metadatos de
  ``artifacts/`` y KPIs nacionales del panel). Nunca datos personales del usuario.
* Sin herramientas (sin búsqueda web), con timeout y límite de tokens.
* La respuesta se devuelve como TEXTO PLANO; el cliente la pinta con ``textContent``.
* No es asesoramiento financiero (aviso visible en la UI y en el prompt).
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

DISCLAIMER = ("Respuesta generada automáticamente a partir de los resultados agregados del proyecto. "
              "No constituye asesoramiento financiero ni una oferta de financiación.")

SYSTEM_PROMPT = """Eres el asistente de "Atalaya · Analítica Hipotecaria", un proyecto académico (TFM) de
analítica del mercado hipotecario español. Respondes en español, de forma breve y neutral.
Reglas obligatorias:
- Usa SOLO la información del bloque CONTEXTO. Si la respuesta no está en el contexto, di que no
  dispones de ese dato. No inventes cifras, fuentes ni fechas.
- Cita la fuente y la fecha de generación del artefacto cuando des una cifra.
- Distingue datos observados de proyecciones y no presentes correlaciones como causalidad.
- No des asesoramiento financiero personalizado ni recomiendes productos o entidades concretas.
- No pidas ni utilices datos personales (ingresos, ahorros, edad...).
- Responde en texto plano, sin HTML."""


class AssistantUnavailable(RuntimeError):
    pass


def is_enabled(config) -> bool:
    return bool(config.get("ASSISTANT_ENABLED") and config.get("GEMINI_API_KEY"))


def build_context(store, panel) -> str:
    """Contexto agregado y acotado (sin datos de usuario)."""
    parts: list[dict] = []
    for meta in store.status_all():
        entry = {"artefacto": meta["label"], "estado": meta["status"]}
        if meta["status"] == "ok":
            bundle = store.get(meta["domain"])
            entry.update({
                "generado": meta["generated_at"], "corte_datos": meta["data_cutoff"],
                "fuentes": [s.get("name") for s in meta["sources"]],
                "metricas": bundle.manifest.get("metrics"),
                "indicadores": [
                    {"vista": v["title"], "items": v.get("items")}
                    for v in bundle.views if v.get("type") == "metrics"
                ][:8],
            })
        parts.append(entry)
    try:
        if panel.available():
            parts.append({"panel_kpis_nacionales": panel.kpis(), "panel_fuente": panel.load().source_label})
    except Exception:  # noqa: BLE001
        log.warning("No se pudieron calcular KPIs del panel para el asistente")
    txt = json.dumps(parts, ensure_ascii=False, default=str)
    return txt[:24_000]


def ask(config, store, panel, message: str) -> str:
    if not is_enabled(config):
        raise AssistantUnavailable("El asistente está desactivado.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:  # pragma: no cover - dependencia opcional
        raise AssistantUnavailable("SDK google-genai no instalado.") from e

    client = genai.Client(
        api_key=config["GEMINI_API_KEY"],
        http_options=types.HttpOptions(timeout=int(config["ASSISTANT_TIMEOUT_S"]) * 1000),
    )
    prompt = f"CONTEXTO (JSON):\n{build_context(store, panel)}\n\nPREGUNTA DEL USUARIO:\n{message}"
    resp = client.models.generate_content(
        model=config["ASSISTANT_MODEL"],
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=int(config["ASSISTANT_MAX_OUTPUT_TOKENS"]),
        ),
    )
    text = (getattr(resp, "text", None) or "").strip()
    return text or "No he podido generar una respuesta con la información disponible."
