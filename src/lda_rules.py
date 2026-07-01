from __future__ import annotations

from typing import Any, Dict, List, Tuple

WORKING_DAYS_MONTH = 22
WEEKS_MONTH = 4.3
FORTNIGHTS_MONTH = 2

FREQUENCY_FIELDS = ["diario", "semanal", "quincenal", "mensual", "anual"]
WEEK_FIELDS = ["semana_1", "semana_2", "semana_3", "semana_4"]


def to_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        text = str(value).strip().replace(",", ".")
        if text == "" or text.lower() in {"nan", "none", "null"}:
            return 0.0
        return float(text)
    except Exception:
        return 0.0


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"x", "1", "true", "sí", "si", "yes", "y", "checked", "verdadero"}


def active_weeks(row: Dict[str, Any]) -> int:
    return sum(1 for field in WEEK_FIELDS if to_bool(row.get(field)))


def selected_frequencies(row: Dict[str, Any]) -> List[str]:
    return [field for field in FREQUENCY_FIELDS if to_number(row.get(field)) > 0]


def compliance_value(value: Any) -> float:
    text = str(value or "").strip().lower()
    if text in {"sí", "si", "cumple", "yes"}:
        return 1.0
    if text in {"parcial", "parcialmente", "en proceso"}:
        return 0.5
    if text in {"no", "no cumple"}:
        return 0.0
    return 0.5


def level_value(value: Any) -> int:
    text = str(value or "").strip().lower()
    if text == "alta":
        return 3
    if text == "media":
        return 2
    if text == "baja":
        return 1
    return 2


def calculate_metrics(row: Dict[str, Any], standard_minutes: float = 360) -> Dict[str, float]:
    diario = to_number(row.get("diario"))
    semanal = to_number(row.get("semanal"))
    quincenal = to_number(row.get("quincenal"))
    mensual = to_number(row.get("mensual"))
    anual = to_number(row.get("anual"))
    tiempo = to_number(row.get("tiempo_x_unidad_min"))

    vol_mes = (
        diario * WORKING_DAYS_MONTH
        + semanal * WEEKS_MONTH
        + quincenal * FORTNIGHTS_MONTH
        + mensual
        + anual / 12
    )
    min_mes = tiempo * vol_mes
    hrs_mes = min_mes / 60 if min_mes else 0.0
    min_dia = min_mes / WORKING_DAYS_MONTH if min_mes else 0.0
    fte_pct = (min_dia / standard_minutes * 100) if standard_minutes else 0.0
    return {
        "vol_mes": round(vol_mes, 2),
        "min_mes": round(min_mes, 2),
        "hrs_mes": round(hrs_mes, 2),
        "min_dia": round(min_dia, 2),
        "fte_pct": round(fte_pct, 2),
    }


def validate_row(row: Dict[str, Any]) -> Tuple[int, List[str]]:
    errors: List[str] = []
    activity = str(row.get("actividad") or "").strip()
    if not activity:
        return 2, ["Actividad vacía"]

    weeks = active_weeks(row)
    freqs = selected_frequencies(row)
    tiempo = to_number(row.get("tiempo_x_unidad_min"))

    if weeks == 0:
        errors.append("Debe marcar al menos una semana")
    if not freqs:
        errors.append("Debe seleccionar una frecuencia")
    if len(freqs) > 1:
        errors.append("Solo debe seleccionar una frecuencia")
    if tiempo <= 0:
        errors.append("Debe indicar tiempo por unidad mayor a cero")

    if len(freqs) == 1:
        freq = freqs[0]
        if freq == "diario" and weeks != 4:
            errors.append("Si es diaria, debe estar marcada en las 4 semanas")
        elif freq == "semanal" and weeks != 4:
            errors.append("Si es semanal, debe estar marcada en las 4 semanas")
        elif freq == "quincenal" and weeks != 2:
            errors.append("Si es quincenal, debe marcar exactamente 2 semanas")
        elif freq == "mensual" and weeks != 1:
            errors.append("Si es mensual, debe marcar exactamente 1 semana")
        elif freq == "anual" and weeks > 1:
            errors.append("Si es anual, normalmente debe marcar una sola semana referencial")

    # Calidad de levantamiento: si no hay evidencia, no invalida la fórmula, pero alerta.
    cumplimiento = str(row.get("cumplimiento") or "").strip().lower()
    evidencia = str(row.get("evidencia") or "").strip()
    if cumplimiento in {"sí", "si", "parcial"} and not evidencia:
        errors.append("Debe registrar evidencia o forma de verificación")

    return (1 if not errors else 2), errors


def normalize_record(row: Dict[str, Any], standard_minutes: float = 360) -> Dict[str, Any]:
    normalized = dict(row)
    for field in WEEK_FIELDS:
        normalized[field] = bool(to_bool(normalized.get(field)))
    for field in FREQUENCY_FIELDS:
        normalized[field] = to_number(normalized.get(field))
    normalized["tiempo_x_unidad_min"] = to_number(normalized.get("tiempo_x_unidad_min"))
    for text_field in [
        "cod", "funcion_origen", "proceso", "actividad", "tipo_actividad", "cumplimiento", "evidencia",
        "comentarios_usuario", "comentarios_proyecto", "opt", "pregunta_validacion", "evidencia_esperada",
        "herramienta_sistema", "entregable", "indicador", "criticidad", "automatizable", "riesgo", "dependencia",
    ]:
        normalized[text_field] = str(normalized.get(text_field) or "").strip()
    metrics = calculate_metrics(normalized, standard_minutes)
    val, errors = validate_row(normalized)
    normalized.update(metrics)
    normalized["val"] = val
    normalized["errores_validacion"] = "; ".join(errors)
    normalized["cumplimiento_score"] = compliance_value(normalized.get("cumplimiento"))
    return normalized


def enrich_record_for_analysis(row: Dict[str, Any], standard_minutes: float = 360) -> Dict[str, Any]:
    r = normalize_record(row, standard_minutes)
    min_dia = to_number(r.get("min_dia"))
    criticidad = level_value(r.get("criticidad"))
    cumplimiento = compliance_value(r.get("cumplimiento"))
    auto = str(r.get("automatizable") or "").strip().lower()
    tipo = str(r.get("tipo_actividad") or "").strip().lower()
    opt = str(r.get("opt") or "-").strip().upper()

    risk_score = min(100, round((criticidad * 20) + ((1 - cumplimiento) * 35) + min(min_dia, 120) * 0.25, 1))
    potential = 0.0
    if opt == "A" or auto == "alta":
        potential = min_dia * 0.35
    elif opt == "R" or tipo == "no core":
        potential = min_dia * 0.25
    elif auto == "media":
        potential = min_dia * 0.15
    r["riesgo_score"] = round(risk_score, 1)
    r["potencial_ahorro_min_dia"] = round(potential, 2)
    if r.get("val") != 1:
        r["hallazgo"] = "Corregir validación LDA antes de concluir."
    elif cumplimiento < 1:
        r["hallazgo"] = "Revisar cumplimiento y evidencia."
    elif potential > 0:
        r["hallazgo"] = "Actividad con oportunidad de mejora."
    else:
        r["hallazgo"] = "Sin alerta relevante."
    return r


def enrich_records_for_analysis(records: List[Dict[str, Any]], standard_minutes: float = 360) -> List[Dict[str, Any]]:
    return [enrich_record_for_analysis(r, standard_minutes) for r in records]


def calculate_summary(records: List[Dict[str, Any]], standard_minutes: float) -> Dict[str, Any]:
    enriched = [enrich_record_for_analysis(r, standard_minutes) for r in records]
    valid = [r for r in enriched if int(r.get("val", 2)) == 1]
    invalid = [r for r in enriched if int(r.get("val", 2)) != 1]
    total_min_dia = round(sum(to_number(r.get("min_dia")) for r in valid), 2)
    total_hrs_mes = round(sum(to_number(r.get("hrs_mes")) for r in valid), 2)
    total_acts = len(enriched)
    valid_count = len(valid)

    cumple = sum(1 for r in enriched if compliance_value(r.get("cumplimiento")) == 1)
    parcial = sum(1 for r in enriched if compliance_value(r.get("cumplimiento")) == 0.5)
    no_cumple = sum(1 for r in enriched if compliance_value(r.get("cumplimiento")) == 0)

    weighted_time = sum(to_number(r.get("min_dia")) for r in valid)
    weighted_compliance = sum(to_number(r.get("min_dia")) * compliance_value(r.get("cumplimiento")) for r in valid)
    cumplimiento_ponderado_pct = round((weighted_compliance / weighted_time * 100) if weighted_time else 0, 1)

    core_minutes = round(sum(to_number(r.get("min_dia")) for r in valid if str(r.get("tipo_actividad") or "").lower() == "core"), 2)
    no_core_minutes = round(total_min_dia - core_minutes, 2)
    opportunities = [r for r in valid if str(r.get("opt") or "-").upper() in {"A", "R"} or to_number(r.get("potencial_ahorro_min_dia")) > 0]
    potential_saving = round(sum(to_number(r.get("potencial_ahorro_min_dia")) for r in opportunities), 2)
    delta = round(total_min_dia - float(standard_minutes or 0), 2)
    utilization = round(total_min_dia / float(standard_minutes) * 100, 1) if standard_minutes else 0
    avg_risk = round(sum(to_number(r.get("riesgo_score")) for r in valid) / len(valid), 1) if valid else 0
    return {
        "actividades_total": total_acts,
        "actividades_validas": valid_count,
        "actividades_invalidas": len(invalid),
        "min_dia_total": total_min_dia,
        "hrs_mes_total": total_hrs_mes,
        "tiempo_estandar": float(standard_minutes or 0),
        "brecha_min_dia": delta,
        "utilizacion_pct": utilization,
        "cumple": cumple,
        "parcial": parcial,
        "no_cumple": no_cumple,
        "cumplimiento_ponderado_pct": cumplimiento_ponderado_pct,
        "min_core_dia": core_minutes,
        "min_no_core_dia": no_core_minutes,
        "core_pct": round(core_minutes / total_min_dia * 100, 1) if total_min_dia else 0,
        "no_core_pct": round(no_core_minutes / total_min_dia * 100, 1) if total_min_dia else 0,
        "oportunidades": len(opportunities),
        "potencial_ahorro_min_dia": potential_saving,
        "riesgo_promedio": avg_risk,
    }
