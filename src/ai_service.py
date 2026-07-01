from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .lda_rules import calculate_summary, enrich_records_for_analysis, to_number

load_dotenv()


def get_runtime_api_key(explicit_key: str | None = None) -> str:
    return (explicit_key or os.getenv("OPENAI_API_KEY") or "").strip()


def get_runtime_model(explicit_model: str | None = None) -> str:
    return (explicit_model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()


def ai_enabled(explicit_key: str | None = None, use_ai: bool = True) -> bool:
    return bool(use_ai and get_runtime_api_key(explicit_key))


def _safe_json_loads(text: str) -> Any:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.lower().startswith("json"):
            clean = clean[4:].strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    return json.loads(clean)


def _chat_json(prompt: str, api_key: str, model: str, temperature: float = 0.1) -> Dict[str, Any]:
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
    response = llm.invoke(prompt)
    return _safe_json_loads(response.content)


def local_activity_suggestion(function_code: str, function_text: str) -> Dict[str, Any]:
    text = " ".join(str(function_text or "").replace("\n", " ").split()).strip().rstrip(".")
    lower = text.lower()

    def has(*words: str) -> bool:
        return any(w in lower for w in words)

    if has("sgi", "ssoma", "políticas", "politicas", "seguridad", "capacitaciones"):
        proceso = "Gestión de cumplimiento"
        tipo = "No core"
        criticidad = "Media"
        automatizable = "Baja"
        indicador = "Cumplimiento de capacitaciones / requisitos"
        evidencia = "Registro, acta, certificado o checklist de cumplimiento"
        herramienta = "Documentación interna / correo / sistema SGI"
    elif has("diseñ", "gráfic", "visual", "arte", "imagen", "marca", "mockup"):
        proceso = "Diseño y comunicación visual"
        tipo = "Core"
        criticidad = "Alta"
        automatizable = "Media"
        indicador = "Número de piezas entregadas / retrabajos / cumplimiento de línea gráfica"
        evidencia = "Piezas finales, archivos editables, enlaces o aprobaciones"
        herramienta = "Adobe, Canva, Figma, Drive u otra herramienta de diseño"
    elif has("contenido", "copy", "copys", "editorial", "redact", "blog", "newsletter"):
        proceso = "Gestión de contenido"
        tipo = "Core"
        criticidad = "Alta"
        automatizable = "Alta"
        indicador = "Contenidos producidos / contenidos aprobados / engagement"
        evidencia = "Calendario editorial, copy aprobado, publicación o enlace"
        herramienta = "Planner, Meta Business Suite, Drive, CMS"
    elif has("comunidad", "redes", "publicación", "publicacion", "plataformas", "comentarios"):
        proceso = "Gestión de comunidad digital"
        tipo = "Core"
        criticidad = "Alta"
        automatizable = "Media"
        indicador = "Publicaciones realizadas / respuesta a comunidad / interacción"
        evidencia = "Capturas, enlaces, reportes de plataforma o bitácora"
        herramienta = "Meta Business Suite, TikTok, LinkedIn, herramienta social"
    elif has("indicador", "desempeño", "dashboard", "analytics", "reporte", "benchmark", "tendencias"):
        proceso = "Analítica y optimización"
        tipo = "Core"
        criticidad = "Media"
        automatizable = "Alta"
        indicador = "Reportes generados / insights aplicados / frecuencia de análisis"
        evidencia = "Dashboard, informe, benchmark o matriz de hallazgos"
        herramienta = "Excel, Looker Studio, Analytics, Meta Insights"
    elif has("proveedor", "impresión", "impresion", "coordinar"):
        proceso = "Coordinación operativa"
        tipo = "Core"
        criticidad = "Media"
        automatizable = "Media"
        indicador = "Entregables coordinados sin retraso / aprobaciones"
        evidencia = "Correo, orden, cronograma o confirmación de entrega"
        herramienta = "Correo, WhatsApp, calendario, gestor de tareas"
    elif has("otras actividades", "jefe inmediato"):
        proceso = "Soporte al cargo"
        tipo = "No core"
        criticidad = "Baja"
        automatizable = "Baja"
        indicador = "Solicitudes atendidas"
        evidencia = "Solicitud del jefe inmediato o bitácora"
        herramienta = "Correo / WhatsApp / tareas"
    else:
        proceso = "Proceso operativo del cargo"
        tipo = "Core"
        criticidad = "Media"
        automatizable = "Media"
        indicador = "Actividad ejecutada conforme a requerimiento"
        evidencia = "Entregable, registro o aprobación"
        herramienta = "Herramienta propia del área"

    opt = "-"
    if tipo == "No core":
        opt = "R"
    if has("reporte", "dashboard", "programar", "publicación", "publicacion", "monitorear", "actualizado", "banco", "adaptar"):
        opt = "A"

    pregunta = "¿Con qué frecuencia realiza esta actividad, cuánto demora y qué evidencia demuestra que se ejecutó?"
    if tipo == "Core":
        pregunta = "¿Qué volumen produce, qué herramienta usa, cuánto demora por unidad y cómo se verifica la calidad del entregable?"

    return {
        "cod": str(function_code or "").strip(),
        "funcion_origen": text,
        "proceso": proceso,
        "actividad": text[:240],
        "tipo_actividad": tipo,
        "pregunta_validacion": pregunta,
        "evidencia_esperada": evidencia,
        "herramienta_sistema": herramienta,
        "entregable": evidencia,
        "indicador": indicador,
        "criticidad": criticidad,
        "automatizable": automatizable,
        "riesgo": "Riesgo de incumplimiento o baja trazabilidad si no existe evidencia verificable.",
        "dependencia": "Validar dependencias con áreas internas, aprobadores o plataformas.",
        "comentarios_proyecto": "Sugerida desde DOP. Validar frecuencia, tiempo, evidencia y cumplimiento en entrevista.",
        "opt": opt,
        "nivel_confianza": 0.78 if tipo == "Core" else 0.68,
        "supuesto_ia": True,
    }


def local_generate_activities(functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [local_activity_suggestion(f.get("code") or f.get("cod"), f.get("description") or f.get("funcion")) for f in functions]


def ai_generate_activities(
    role: Dict[str, Any],
    functions: List[Dict[str, Any]],
    api_key: str | None = None,
    model: str | None = None,
    use_ai: bool = True,
) -> List[Dict[str, Any]]:
    key = get_runtime_api_key(api_key)
    model_name = get_runtime_model(model)
    if not ai_enabled(key, use_ai):
        return local_generate_activities(functions)

    payload = {
        "cargo": role.get("cargo"),
        "area": role.get("area"),
        "departamento": role.get("departamento"),
        "empresa": role.get("company_name") or role.get("organizacion"),
        "mision": role.get("mision"),
        "funciones": functions,
    }
    prompt = f"""
Eres consultor senior en Levantamiento de Actividades (LDA), DOP, análisis organizacional y eficiencia operacional.
Tu tarea es convertir funciones de una descripción de puesto en actividades operativas medibles para entrevista LDA.

Contexto del cargo:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Devuelve SOLO JSON válido con esta estructura:
{{
  "actividades": [
    {{
      "cod": "código de función",
      "funcion_origen": "función original resumida",
      "proceso": "proceso o subproceso recomendado",
      "actividad": "actividad operativa en verbo infinitivo o sustantivo de acción",
      "tipo_actividad": "Core | No core | Soporte | Control",
      "pregunta_validacion": "pregunta concreta para el consultor",
      "evidencia_esperada": "qué prueba debe pedir el consultor",
      "herramienta_sistema": "herramientas/sistemas probables a validar",
      "entregable": "entregable observable",
      "indicador": "KPI o métrica útil",
      "criticidad": "Alta | Media | Baja",
      "automatizable": "Alta | Media | Baja",
      "riesgo": "riesgo si no se ejecuta o no se evidencia",
      "dependencia": "área/persona/sistema del que depende",
      "comentarios_proyecto": "nota para el consultor",
      "opt": "A | R | -",
      "nivel_confianza": número entre 0 y 1,
      "supuesto_ia": true
    }}
  ]
}}

Reglas:
- No inventes actividades fuera del alcance del cargo; si haces un supuesto, dilo en comentarios_proyecto.
- "A" significa oportunidad de automatización; "R" redistribución/rediseño; "-" sin oportunidad inmediata.
- Prioriza actividades que el consultor pueda medir con frecuencia, volumen, tiempo y evidencia.
""".strip()

    try:
        data = _chat_json(prompt, key, model_name, temperature=0.05)
        items = data.get("actividades", []) if isinstance(data, dict) else []
        if not items:
            raise ValueError("La IA no devolvió actividades")
        normalized = []
        fallback = local_generate_activities(functions)
        for idx, item in enumerate(items):
            base = fallback[idx] if idx < len(fallback) else {}
            merged = {**base, **(item or {})}
            merged["supuesto_ia"] = True
            try:
                merged["nivel_confianza"] = float(merged.get("nivel_confianza") or base.get("nivel_confianza") or 0.7)
            except Exception:
                merged["nivel_confianza"] = 0.7
            normalized.append(merged)
        return normalized
    except Exception as exc:
        items = local_generate_activities(functions)
        for it in items:
            it["comentarios_proyecto"] = f"Fallback local por error IA: {exc}. Validar manualmente."
        return items


def local_analyze_interview(role: Dict[str, Any], records: List[Dict[str, Any]], standard_minutes: float) -> Dict[str, Any]:
    records = enrich_records_for_analysis(records, standard_minutes)
    summary = calculate_summary(records, standard_minutes)
    cargo = role.get("cargo") or "cargo evaluado"
    total = summary["min_dia_total"]
    std = summary["tiempo_estandar"]
    brecha = summary["brecha_min_dia"]
    invalid = summary["actividades_invalidas"]
    compliance = summary.get("cumplimiento_ponderado_pct", 0)

    if total <= 0:
        conclusion = (
            f"Todavía no hay volumetría real suficiente para concluir sobre {cargo}. "
            "El consultor debe completar frecuencia, semanas y tiempo por unidad."
        )
    elif invalid:
        conclusion = (
            f"El levantamiento de {cargo} contiene {invalid} actividades con errores LDA. "
            "La conclusión debe considerarse preliminar hasta corregirlas."
        )
    elif brecha > 30:
        conclusion = (
            f"{cargo} presenta sobrecarga operativa: {total:.0f} min/día frente a {std:.0f} min/día. "
            f"La brecha es de {brecha:.0f} min/día. Cumplimiento ponderado: {compliance:.1f}%."
        )
    elif brecha < -60:
        conclusion = (
            f"{cargo} presenta holgura o subregistro: {total:.0f} min/día frente a {std:.0f} min/día. "
            "Conviene validar si faltan actividades, si las frecuencias fueron subestimadas o si el puesto tiene capacidad disponible."
        )
    else:
        conclusion = (
            f"{cargo} muestra una carga cercana al estándar: {total:.0f} min/día frente a {std:.0f} min/día. "
            f"Cumplimiento ponderado: {compliance:.1f}%."
        )

    top = sorted(records, key=lambda x: to_number(x.get("min_dia")), reverse=True)[:5]
    opportunities = [r for r in records if str(r.get("opt") or "-").upper() in {"A", "R"} or to_number(r.get("potencial_ahorro_min_dia")) > 0]

    return {
        "conclusion": conclusion,
        "resumen_ejecutivo": conclusion,
        "hallazgos": [
            f"Tiempo diario calculado: {total:.0f} min/día.",
            f"Tiempo estándar: {std:.0f} min/día.",
            f"Cumplimiento ponderado: {compliance:.1f}%.",
            f"Actividades con errores LDA: {invalid}.",
        ],
        "preguntas_pendientes": [
            "Validar evidencias de las actividades de mayor consumo.",
            "Confirmar actividades no core marcadas como redistribuibles.",
        ],
        "oportunidades": [
            {
                "cod": r.get("cod"),
                "actividad": r.get("actividad"),
                "tipo": r.get("opt"),
                "razon": r.get("comentarios_proyecto") or r.get("riesgo") or "Revisar oportunidad.",
                "ahorro_estimado_min_dia": r.get("potencial_ahorro_min_dia", 0),
            }
            for r in opportunities[:8]
        ],
        "top_consumo": [
            {
                "cod": r.get("cod"),
                "actividad": r.get("actividad"),
                "min_dia": r.get("min_dia", 0),
                "proceso": r.get("proceso"),
            }
            for r in top
        ],
    }


def ai_analyze_interview(
    role: Dict[str, Any],
    records: List[Dict[str, Any]],
    standard_minutes: float,
    api_key: str | None = None,
    model: str | None = None,
    use_ai: bool = True,
) -> Dict[str, Any]:
    key = get_runtime_api_key(api_key)
    model_name = get_runtime_model(model)
    enriched = enrich_records_for_analysis(records, standard_minutes)
    summary = calculate_summary(enriched, standard_minutes)
    local = local_analyze_interview(role, enriched, standard_minutes)
    if not ai_enabled(key, use_ai):
        return local

    reduced_records = []
    for r in enriched:
        reduced_records.append({
            "cod": r.get("cod"),
            "proceso": r.get("proceso"),
            "actividad": r.get("actividad"),
            "tipo_actividad": r.get("tipo_actividad"),
            "cumplimiento": r.get("cumplimiento"),
            "evidencia": r.get("evidencia"),
            "criticidad": r.get("criticidad"),
            "automatizable": r.get("automatizable"),
            "opt": r.get("opt"),
            "min_dia": r.get("min_dia"),
            "hrs_mes": r.get("hrs_mes"),
            "val": r.get("val"),
            "errores_validacion": r.get("errores_validacion"),
            "comentarios_usuario": r.get("comentarios_usuario"),
            "riesgo": r.get("riesgo"),
        })

    prompt = f"""
Eres consultor senior en DOP, LDA, productividad, diseño organizacional y automatización.
Analiza una entrevista LDA real. Debes ser práctico para el consultor: no inventes datos y no ignores errores de volumetría.

Cargo:
{json.dumps(role, ensure_ascii=False, indent=2)}

Resumen calculado por la app:
{json.dumps(summary, ensure_ascii=False, indent=2)}

Actividades LDA calculadas:
{json.dumps(reduced_records, ensure_ascii=False, indent=2)}

Devuelve SOLO JSON válido con esta estructura:
{{
  "conclusion": "conclusión ejecutiva en 4-6 líneas sobre si cumple funciones, carga, brecha y calidad del levantamiento",
  "resumen_ejecutivo": "resumen breve para gerente",
  "hallazgos": ["hallazgo 1", "hallazgo 2", "hallazgo 3"],
  "preguntas_pendientes": ["pregunta para el consultor", "pregunta para el jefe"],
  "oportunidades": [
    {{"cod":"", "actividad":"", "tipo":"A/R/Quickwin/Control", "razon":"", "ahorro_estimado_min_dia":0}}
  ],
  "riesgos": ["riesgo 1", "riesgo 2"],
  "recomendaciones": ["recomendación accionable 1", "recomendación accionable 2"]
}}

Criterios:
- Si min_dia_total es 0, la conclusión debe decir que falta volumetría real.
- Si hay errores LDA, explica que el análisis es preliminar.
- Compara tiempo real contra tiempo estándar.
- Diferencia Core vs No core.
- Identifica oportunidades de automatización A y redistribución R.
- Señala si la persona parece cumplir, cumplir parcialmente o no cumplir según cumplimiento y evidencia.
""".strip()

    try:
        data = _chat_json(prompt, key, model_name, temperature=0.1)
        if not isinstance(data, dict) or not data.get("conclusion"):
            raise ValueError("Respuesta IA incompleta")
        return {**local, **data}
    except Exception as exc:
        local["hallazgos"].append(f"No se pudo usar IA externa; se aplicó análisis local. Detalle: {exc}")
        return local
