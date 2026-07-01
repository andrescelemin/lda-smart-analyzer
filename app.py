from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src import db
from src.ai_graph import generate_activities_from_functions, run_lda_graph
from src.dop_service import import_dop_file, seed_sample_if_empty
from src.lda_rules import calculate_summary, enrich_records_for_analysis, normalize_record, to_number
from src.reporting import export_interview_xlsx

load_dotenv()

st.set_page_config(
    page_title="LDA Smart Analyzer v3",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_app() -> None:
    db.init_db()
    seeded = seed_sample_if_empty()
    demo = db.seed_demo_interviews_if_empty()
    if seeded:
        st.toast("DOP de ejemplo importado a la base local", icon="✅")
    if demo:
        st.toast("Entrevistas demo con datos reales precargadas", icon="📊")


def get_ai_config() -> Dict[str, Any]:
    return {
        "api_key": db.get_setting("openai_api_key", ""),
        "model": db.get_setting("openai_model", "gpt-4o-mini"),
        "use_ai": db.get_setting("use_ai", "false").lower() == "true",
    }


def label_for_role(role: Dict[str, Any]) -> str:
    return f"{role['cargo']} · {role.get('area') or 'Sin área'} · {role.get('company_name') or role.get('organizacion') or ''}"


def label_for_interview(item: Dict[str, Any]) -> str:
    total = item.get("total_min_dia")
    total_txt = f" · {float(total):.0f} min/día" if total is not None else ""
    return f"#{item['id']} · {item['cargo']} · {item.get('entrevistado') or 'sin entrevistado'} · {item.get('fecha') or ''}{total_txt}"


def standard_minutes_sidebar() -> float:
    current = float(db.get_setting("standard_daily_minutes", "360") or 360)
    value = st.sidebar.number_input(
        "Tiempo estándar diario disponible (min)",
        min_value=60.0,
        max_value=720.0,
        value=current,
        step=15.0,
    )
    if value != current:
        db.set_setting("standard_daily_minutes", value)
    return float(value)


def render_sidebar() -> float:
    with st.sidebar:
        st.header("⚙️ Configuración")
        st.info("El DOP se importa una sola vez. El consultor trabaja desde formularios y la app calcula/analiza con datos reales.")
        standard = standard_minutes_sidebar()
        st.divider()
        st.subheader("🤖 Inteligencia Artificial")
        ai_cfg = get_ai_config()
        use_ai = st.checkbox("Usar OpenAI para generar y analizar", value=ai_cfg["use_ai"])
        model = st.selectbox("Modelo", ["gpt-4o-mini", "gpt-4o"], index=0 if ai_cfg["model"] == "gpt-4o-mini" else 1)
        api_key = st.text_input("OPENAI_API_KEY", value=ai_cfg["api_key"], type="password", help="Se guarda solo en la base SQLite local de este proyecto.")
        if st.button("💾 Guardar configuración IA", use_container_width=True):
            db.set_setting("use_ai", "true" if use_ai else "false")
            db.set_setting("openai_model", model)
            db.set_setting("openai_api_key", api_key.strip())
            st.success("Configuración IA guardada")
            st.rerun()
        if use_ai and api_key.strip():
            st.success("IA externa activa")
        else:
            st.warning("Modo local/reglas. Pega API key y activa IA para análisis real con modelo.")

        st.divider()
        st.markdown("**Base local**")
        st.caption(f"SQLite: `{db.DB_PATH.name}`")
        if st.button("🔄 Reiniciar base y recargar ejemplo", use_container_width=True):
            db.delete_database()
            db.init_db()
            seed_sample_if_empty()
            db.seed_demo_interviews_if_empty()
            st.rerun()
        return standard


def build_editor_dataframe(role_id: int, demo_values: bool = False) -> pd.DataFrame:
    suggestions = db.get_suggestions(role_id)
    rows = []
    for i, s in enumerate(suggestions, start=1):
        base = {
            "cod": s.get("cod") or "",
            "funcion_origen": s.get("funcion_origen") or "",
            "proceso": s.get("proceso") or "",
            "actividad": s.get("actividad") or "",
            "tipo_actividad": s.get("tipo_actividad") or "Core",
            "pregunta_validacion": s.get("pregunta_validacion") or "",
            "evidencia_esperada": s.get("evidencia_esperada") or "",
            "herramienta_sistema": s.get("herramienta_sistema") or "",
            "entregable": s.get("entregable") or "",
            "indicador": s.get("indicador") or "",
            "criticidad": s.get("criticidad") or "Media",
            "automatizable": s.get("automatizable") or "Media",
            "riesgo": s.get("riesgo") or "",
            "dependencia": s.get("dependencia") or "",
            "semana_1": False,
            "semana_2": False,
            "semana_3": False,
            "semana_4": False,
            "diario": 0.0,
            "semanal": 0.0,
            "quincenal": 0.0,
            "mensual": 0.0,
            "anual": 0.0,
            "tiempo_x_unidad_min": 0.0,
            "cumplimiento": "Sí",
            "evidencia": "",
            "comentarios_usuario": "",
            "comentarios_proyecto": s.get("comentarios_proyecto") or "",
            "opt": s.get("opt") or "-",
        }
        if demo_values:
            if i in {1, 2}:
                base.update({"mensual": 1, "semana_1": True, "tiempo_x_unidad_min": 50 + i * 5})
            elif i in {3, 6, 9}:
                base.update({"semanal": 1, "semana_1": True, "semana_2": True, "semana_3": True, "semana_4": True, "tiempo_x_unidad_min": 60 + i * 5})
            elif i in {4, 8}:
                base.update({"quincenal": 1, "semana_1": True, "semana_3": True, "tiempo_x_unidad_min": 90})
            else:
                base.update({"diario": 1, "semana_1": True, "semana_2": True, "semana_3": True, "semana_4": True, "tiempo_x_unidad_min": 25 + i * 3})
            base["evidencia"] = base["evidencia_esperada"] or "Evidencia validada en entrevista"
            base["comentarios_usuario"] = "Dato de prueba realista. Reemplazar por dato real del entrevistado."
            if i in {5, 10}:
                base["cumplimiento"] = "Parcial"
        rows.append(base)
    return pd.DataFrame(rows)


def normalize_editor_records(df: pd.DataFrame, standard_minutes: float) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return records
    for _, row in df.fillna("").iterrows():
        raw = row.to_dict()
        if not str(raw.get("actividad") or "").strip():
            continue
        records.append(normalize_record(raw, standard_minutes))
    return records


def render_header() -> None:
    st.title("📊 LDA Smart Analyzer v3")
    st.caption("Levantamiento LDA real: formularios, cálculos, validación, OpenAI opcional y análisis gerencial con LangGraph.")


def tab_base_superusuario() -> None:
    st.subheader("🏢 Base / Super Usuario")
    st.write("Carga empresas, cargos y DOP una sola vez. La IA puede enriquecer actividades con evidencias, indicadores, riesgos y oportunidades.")

    roles = db.list_roles()
    companies = db.list_companies()
    interviews = db.list_interviews()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Empresas", len(companies))
    c2.metric("Cargos DOP", len(roles))
    c3.metric("Entrevistas", len(interviews))
    c4.metric("Consultores", len(db.list_consultants()))

    st.divider()
    st.markdown("### Importar nuevo DOP a la base")
    ai_cfg = get_ai_config()
    st.caption("Usa esto solo cuando llegue un nuevo DOP. Si la IA está activa, generará actividades más completas desde el DOP.")
    uploaded = st.file_uploader("Subir DOP en Excel", type=["xlsx"], key="dop_import_once")
    use_ai_import = st.checkbox("Usar IA al importar este DOP", value=ai_cfg["use_ai"], key="use_ai_import")
    if uploaded is not None:
        if st.button("📥 Importar DOP a la base", type="primary"):
            bytes_data = BytesIO(uploaded.read())
            with st.spinner("Importando DOP y generando actividades..."):
                imported = import_dop_file(bytes_data, api_key=ai_cfg["api_key"], model=ai_cfg["model"], use_ai=use_ai_import)
            st.success(f"Se importaron {imported} cargo(s) desde el DOP.")
            st.rerun()

    st.divider()
    st.markdown("### Crear consultor")
    with st.form("form_consultor", clear_on_submit=True):
        col_a, col_b = st.columns([2, 2])
        name = col_a.text_input("Nombre del consultor")
        email = col_b.text_input("Email")
        submitted = st.form_submit_button("Agregar consultor")
        if submitted:
            db.add_consultant(name, email)
            st.success("Consultor agregado")
            st.rerun()

    st.divider()
    st.markdown("### Cargos disponibles en la base")
    if not roles:
        st.warning("No hay cargos cargados. Importa un DOP.")
        return
    df_roles = pd.DataFrame(roles)
    visible_cols = ["id", "company_name", "cargo", "area", "departamento", "function_count", "suggestion_count", "estado"]
    visible = df_roles[visible_cols].rename(columns={
        "id": "ID", "company_name": "Empresa", "cargo": "Cargo", "area": "Área",
        "departamento": "Departamento", "function_count": "Funciones DOP", "suggestion_count": "Actividades sugeridas", "estado": "Estado"
    })
    st.dataframe(visible, use_container_width=True, hide_index=True)

    selected_role_id = st.selectbox(
        "Ver detalle de cargo",
        options=[r["id"] for r in roles],
        format_func=lambda rid: label_for_role(next(r for r in roles if r["id"] == rid)),
    )
    role = db.get_role(selected_role_id)
    funcs = db.get_functions(selected_role_id)
    suggs = db.get_suggestions(selected_role_id)
    if role:
        st.markdown(f"**Misión:** {role.get('mision') or 'No especificada'}")
        if st.button("🤖 Regenerar actividades enriquecidas con IA/local para este cargo"):
            with st.spinner("Regenerando actividades..."):
                ai_cfg = get_ai_config()
                items = generate_activities_from_functions(funcs, role=role, api_key=ai_cfg["api_key"], model=ai_cfg["model"], use_ai=ai_cfg["use_ai"])
                db.replace_suggestions(selected_role_id, items)
            st.success("Actividades regeneradas")
            st.rerun()
        col_f, col_s = st.columns(2)
        with col_f:
            st.markdown("**Funciones del DOP**")
            st.dataframe(pd.DataFrame(funcs)[["code", "description"]], use_container_width=True, hide_index=True)
        with col_s:
            st.markdown("**Actividades sugeridas enriquecidas**")
            if suggs:
                cols = ["cod", "proceso", "actividad", "tipo_actividad", "criticidad", "automatizable", "opt", "indicador"]
                st.dataframe(pd.DataFrame(suggs)[cols], use_container_width=True, hide_index=True)


def tab_formulario_consultor(standard_minutes: float) -> None:
    st.subheader("🧾 Formulario Consultor")
    st.write("El consultor valida actividades, captura volumetría real, evidencia, cumplimiento y observaciones directamente en la tabla.")
    roles = db.list_roles()
    consultants = db.list_consultants()
    if not roles:
        st.warning("Primero importa o crea cargos desde Base / Super Usuario.")
        return

    col1, col2, col3 = st.columns([2, 2, 1])
    role_id = col1.selectbox("Cargo a evaluar", [r["id"] for r in roles], format_func=lambda rid: label_for_role(next(r for r in roles if r["id"] == rid)))
    consultant_id = col2.selectbox("Consultor", [c["id"] for c in consultants], format_func=lambda cid: next(c["name"] for c in consultants if c["id"] == cid))
    fecha = col3.date_input("Fecha", value=date.today())
    entrevistado = st.text_input("Nombre de la persona entrevistada / titular del puesto", placeholder="Ej. Juan Pérez")

    role = db.get_role(role_id)
    funcs = db.get_functions(role_id)
    suggestions = db.get_suggestions(role_id)

    with st.expander("Contexto del DOP del cargo", expanded=True):
        st.markdown(f"**Empresa:** {role.get('company_name') if role else ''}")
        st.markdown(f"**Cargo:** {role.get('cargo') if role else ''}")
        st.markdown(f"**Misión:** {role.get('mision') if role else ''}")
        st.markdown("**Funciones base del DOP:**")
        st.dataframe(pd.DataFrame(funcs)[["code", "description"]], use_container_width=True, hide_index=True)

    if not suggestions:
        st.error("Este cargo no tiene actividades sugeridas. Reimporta el DOP o regenera actividades desde la base.")
        return

    st.markdown("### Captura LDA enriquecida")
    st.caption("Regla LDA: marca semanas, elige una sola frecuencia y coloca tiempo por unidad. La app calcula Vol Mes, Min Mes, Hrs Mes, Min Día, % jornada, riesgo y ahorro potencial.")

    state_key = f"editor_role_{role_id}"
    if state_key not in st.session_state:
        st.session_state[state_key] = build_editor_dataframe(role_id, demo_values=False)

    c1, c2, c3 = st.columns([1, 1, 2])
    if c1.button("↩️ Recargar vacío desde DOP"):
        st.session_state[state_key] = build_editor_dataframe(role_id, demo_values=False)
        st.rerun()
    if c2.button("🧪 Precargar datos realistas"):
        st.session_state[state_key] = build_editor_dataframe(role_id, demo_values=True)
        st.rerun()
    c3.info("'Precargar datos realistas' solo es para demo/pruebas. En producción se llena con entrevista real.")

    editor_df = st.data_editor(
        st.session_state[state_key],
        key=f"lda_editor_{role_id}",
        num_rows="dynamic",
        use_container_width=True,
        height=600,
        column_config={
            "cod": st.column_config.TextColumn("Cod", width="small"),
            "funcion_origen": st.column_config.TextColumn("Función DOP", width="large"),
            "proceso": st.column_config.TextColumn("Proceso/Subproceso", width="medium"),
            "actividad": st.column_config.TextColumn("Actividad", width="large"),
            "tipo_actividad": st.column_config.SelectboxColumn("Tipo", options=["Core", "No core", "Soporte", "Control"], width="small"),
            "pregunta_validacion": st.column_config.TextColumn("Pregunta de validación", width="large"),
            "evidencia_esperada": st.column_config.TextColumn("Evidencia esperada", width="medium"),
            "herramienta_sistema": st.column_config.TextColumn("Herramienta/Sistema", width="medium"),
            "entregable": st.column_config.TextColumn("Entregable", width="medium"),
            "indicador": st.column_config.TextColumn("Indicador/KPI", width="medium"),
            "criticidad": st.column_config.SelectboxColumn("Criticidad", options=["Alta", "Media", "Baja"], width="small"),
            "automatizable": st.column_config.SelectboxColumn("Automatizable", options=["Alta", "Media", "Baja"], width="small"),
            "semana_1": st.column_config.CheckboxColumn("S1"),
            "semana_2": st.column_config.CheckboxColumn("S2"),
            "semana_3": st.column_config.CheckboxColumn("S3"),
            "semana_4": st.column_config.CheckboxColumn("S4"),
            "diario": st.column_config.NumberColumn("Diario", min_value=0.0, step=1.0),
            "semanal": st.column_config.NumberColumn("Semanal", min_value=0.0, step=1.0),
            "quincenal": st.column_config.NumberColumn("Quincenal", min_value=0.0, step=1.0),
            "mensual": st.column_config.NumberColumn("Mensual", min_value=0.0, step=1.0),
            "anual": st.column_config.NumberColumn("Anual", min_value=0.0, step=1.0),
            "tiempo_x_unidad_min": st.column_config.NumberColumn("Tiempo x unidad (min)", min_value=0.0, step=5.0),
            "cumplimiento": st.column_config.SelectboxColumn("Cumplimiento", options=["Sí", "Parcial", "No"], width="small"),
            "evidencia": st.column_config.TextColumn("Evidencia real", width="medium"),
            "opt": st.column_config.SelectboxColumn("OPT", options=["-", "A", "R", "Quickwin", "Control"], width="small"),
            "riesgo": st.column_config.TextColumn("Riesgo", width="medium"),
            "dependencia": st.column_config.TextColumn("Dependencia", width="medium"),
            "comentarios_usuario": st.column_config.TextColumn("Comentarios usuario", width="medium"),
            "comentarios_proyecto": st.column_config.TextColumn("Comentarios proyecto", width="medium"),
        },
    )
    st.session_state[state_key] = editor_df

    records_preview = enrich_records_for_analysis(normalize_editor_records(editor_df, standard_minutes), standard_minutes)
    summary_preview = calculate_summary(records_preview, standard_minutes)
    with st.expander("📌 Cálculo en vivo antes de guardar", expanded=True):
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Min/día", f"{summary_preview['min_dia_total']:.1f}")
        m2.metric("Utilización", f"{summary_preview['utilizacion_pct']:.1f}%")
        m3.metric("Cumplimiento ponderado", f"{summary_preview['cumplimiento_ponderado_pct']:.1f}%")
        m4.metric("Errores LDA", summary_preview["actividades_invalidas"])
        m5.metric("Ahorro potencial", f"{summary_preview['potencial_ahorro_min_dia']:.1f} min/día")
        cols_preview = ["cod", "actividad", "vol_mes", "min_mes", "hrs_mes", "min_dia", "fte_pct", "cumplimiento_score", "riesgo_score", "potencial_ahorro_min_dia", "val", "errores_validacion"]
        st.dataframe(pd.DataFrame(records_preview)[cols_preview], use_container_width=True, hide_index=True)

    if st.button("💾 Guardar entrevista y analizar", type="primary", use_container_width=True):
        if not entrevistado.strip():
            st.error("Indica el nombre de la persona entrevistada/titular del puesto.")
            return
        records = normalize_editor_records(editor_df, standard_minutes)
        ai_cfg = get_ai_config()
        state = run_lda_graph({
            "role": role or {},
            "functions": funcs,
            "records": records,
            "standard_minutes": standard_minutes,
            "api_key": ai_cfg["api_key"],
            "model": ai_cfg["model"],
            "use_ai": ai_cfg["use_ai"],
        })
        records_final = state.get("records", [])
        interview_id = db.create_interview(role_id, consultant_id, entrevistado.strip(), fecha.isoformat(), estado="Analizado")
        db.save_records(interview_id, role_id, records_final)
        db.update_interview_conclusion(
            interview_id,
            state.get("conclusion", ""),
            estado="Analizado con IA" if ai_cfg["use_ai"] and ai_cfg["api_key"] else "Analizado local",
            analysis_json=json.dumps(state.get("analysis", {}), ensure_ascii=False),
        )
        st.success(f"Entrevista #{interview_id} guardada y analizada.")
        st.session_state["last_interview_id"] = interview_id
        st.rerun()


def _analysis_from_interview(interview: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(interview.get("analysis_json") or "{}")
    except Exception:
        return {}


def tab_analisis(standard_minutes: float) -> None:
    st.subheader("📈 Análisis")
    interviews = db.list_interviews()
    if not interviews:
        st.info("Todavía no hay entrevistas guardadas.")
        return
    default = st.session_state.get("last_interview_id")
    ids = [i["id"] for i in interviews]
    index = ids.index(default) if default in ids else 0
    interview_id = st.selectbox("Selecciona entrevista", ids, index=index, format_func=lambda iid: label_for_interview(next(i for i in interviews if i["id"] == iid)))
    interview = db.get_interview(interview_id)
    records = db.get_records(interview_id)
    enriched = enrich_records_for_analysis(records, standard_minutes)
    summary = calculate_summary(enriched, standard_minutes)
    analysis = _analysis_from_interview(interview or {})

    st.markdown("### Conclusión rápida")
    st.success((interview or {}).get("conclusion") or analysis.get("conclusion") or "Sin conclusión guardada.")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Min/día", f"{summary['min_dia_total']:.1f}")
    c2.metric("Estándar", f"{summary['tiempo_estandar']:.1f}")
    c3.metric("Brecha", f"{summary['brecha_min_dia']:.1f}")
    c4.metric("Utilización", f"{summary['utilizacion_pct']:.1f}%")
    c5.metric("Ahorro potencial", f"{summary['potencial_ahorro_min_dia']:.1f} min/día")
    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("Cumple", summary["cumple"])
    c7.metric("Parcial", summary["parcial"])
    c8.metric("No cumple", summary["no_cumple"])
    c9.metric("Cumplimiento ponderado", f"{summary['cumplimiento_ponderado_pct']:.1f}%")
    c10.metric("Errores LDA", summary["actividades_invalidas"])

    if analysis:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("### Hallazgos IA")
            for h in analysis.get("hallazgos", []):
                st.write(f"• {h}")
            st.markdown("### Preguntas pendientes")
            for q in analysis.get("preguntas_pendientes", []):
                st.write(f"• {q}")
        with col_b:
            st.markdown("### Recomendaciones")
            for r in analysis.get("recomendaciones", []):
                st.write(f"• {r}")
            st.markdown("### Riesgos")
            for r in analysis.get("riesgos", []):
                st.write(f"• {r}")

    df = pd.DataFrame(enriched)
    if df.empty:
        st.warning("La entrevista no tiene actividades.")
        return

    st.markdown("### Distribución de tiempo por proceso")
    proc = df[df["val"] == 1].groupby("proceso", dropna=False)["min_dia"].sum().sort_values(ascending=False)
    st.bar_chart(proc)

    st.markdown("### Actividades de mayor consumo")
    top_cols = ["cod", "proceso", "actividad", "tipo_actividad", "cumplimiento", "criticidad", "automatizable", "opt", "min_dia", "hrs_mes", "riesgo_score", "potencial_ahorro_min_dia", "hallazgo"]
    st.dataframe(df.sort_values("min_dia", ascending=False)[top_cols].head(15), use_container_width=True, hide_index=True)

    st.markdown("### Oportunidades / alertas")
    alert_df = df[(df["val"] != 1) | (df["opt"].astype(str).str.upper().isin(["A", "R"])) | (df["cumplimiento"].astype(str).str.lower().isin(["parcial", "no"])) | (df["riesgo_score"] >= 65)]
    alert_cols = ["cod", "actividad", "tipo_actividad", "cumplimiento", "criticidad", "opt", "min_dia", "riesgo_score", "potencial_ahorro_min_dia", "errores_validacion", "hallazgo"]
    st.dataframe(alert_df[alert_cols], use_container_width=True, hide_index=True)

    with st.expander("Ver tabla completa LDA enriquecida"):
        st.dataframe(df, use_container_width=True, hide_index=True)


def tab_exportar(standard_minutes: float) -> None:
    st.subheader("📤 Exportar")
    interviews = db.list_interviews()
    if not interviews:
        st.info("No hay entrevistas para exportar.")
        return
    interview_id = st.selectbox("Entrevista a exportar", [i["id"] for i in interviews], format_func=lambda iid: label_for_interview(next(i for i in interviews if i["id"] == iid)))
    interview = db.get_interview(interview_id)
    records = db.get_records(interview_id)
    if st.button("📥 Generar Excel LDA enriquecido", type="primary"):
        out_path = export_interview_xlsx(interview or {}, records, standard_minutes)
        st.success(f"Excel generado: {out_path.name}")
        with open(out_path, "rb") as f:
            st.download_button(
                "Descargar Excel",
                data=f.read(),
                file_name=out_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def main() -> None:
    init_app()
    standard = render_sidebar()
    render_header()
    tabs = st.tabs(["Base / Super Usuario", "Formulario Consultor", "Análisis", "Exportar"])
    with tabs[0]:
        tab_base_superusuario()
    with tabs[1]:
        tab_formulario_consultor(standard)
    with tabs[2]:
        tab_analisis(standard)
    with tabs[3]:
        tab_exportar(standard)


if __name__ == "__main__":
    main()
