from __future__ import annotations

from typing import Any, Dict, List, TypedDict

from .ai_service import ai_analyze_interview, ai_generate_activities, local_generate_activities
from .lda_rules import calculate_summary, enrich_records_for_analysis, normalize_record, to_number


def generate_activities_from_functions(
    functions: List[Dict[str, Any]],
    role: Dict[str, Any] | None = None,
    api_key: str | None = None,
    model: str | None = None,
    use_ai: bool = False,
) -> List[Dict[str, Any]]:
    if use_ai:
        return ai_generate_activities(role or {}, functions, api_key=api_key, model=model, use_ai=True)
    return local_generate_activities(functions)


class LDAState(TypedDict, total=False):
    role: Dict[str, Any]
    functions: List[Dict[str, Any]]
    suggested_activities: List[Dict[str, Any]]
    records: List[Dict[str, Any]]
    standard_minutes: float
    summary: Dict[str, Any]
    analysis: Dict[str, Any]
    conclusion: str
    api_key: str
    model: str
    use_ai: bool


def node_generate_activities(state: LDAState) -> LDAState:
    if state.get("suggested_activities"):
        return state
    state["suggested_activities"] = generate_activities_from_functions(
        state.get("functions", []),
        role=state.get("role", {}),
        api_key=state.get("api_key"),
        model=state.get("model"),
        use_ai=bool(state.get("use_ai", False)),
    )
    return state


def node_normalize_records(state: LDAState) -> LDAState:
    standard = to_number(state.get("standard_minutes") or 360)
    state["records"] = [normalize_record(r, standard) for r in state.get("records", [])]
    return state


def node_enrich_records(state: LDAState) -> LDAState:
    standard = to_number(state.get("standard_minutes") or 360)
    state["records"] = enrich_records_for_analysis(state.get("records", []), standard)
    return state


def node_analyze(state: LDAState) -> LDAState:
    records = state.get("records", [])
    standard = to_number(state.get("standard_minutes") or 360)
    state["summary"] = calculate_summary(records, standard)
    state["analysis"] = ai_analyze_interview(
        state.get("role", {}),
        records,
        standard,
        api_key=state.get("api_key"),
        model=state.get("model"),
        use_ai=bool(state.get("use_ai", False)),
    )
    state["conclusion"] = state["analysis"].get("conclusion", "")
    return state


def build_graph():
    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(LDAState)
        graph.add_node("generar_actividades", node_generate_activities)
        graph.add_node("validar_y_calcular", node_normalize_records)
        graph.add_node("enriquecer", node_enrich_records)
        graph.add_node("analizar", node_analyze)
        graph.add_edge(START, "generar_actividades")
        graph.add_edge("generar_actividades", "validar_y_calcular")
        graph.add_edge("validar_y_calcular", "enriquecer")
        graph.add_edge("enriquecer", "analizar")
        graph.add_edge("analizar", END)
        return graph.compile()
    except Exception:
        return None


def run_lda_graph(state: LDAState) -> LDAState:
    graph = build_graph()
    if graph is not None:
        return graph.invoke(state)
    state = node_generate_activities(state)
    state = node_normalize_records(state)
    state = node_enrich_records(state)
    state = node_analyze(state)
    return state
