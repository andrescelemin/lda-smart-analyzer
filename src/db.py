from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lda_app.db"
SAMPLE_DOP_PATH = DATA_DIR / "samples" / "DOP_Envio_Andres.xlsx"


EXTRA_SUGGESTION_COLS = [
    "evidencia_esperada", "herramienta_sistema", "entregable", "indicador", "criticidad", "automatizable", "riesgo", "dependencia"
]

EXTRA_RECORD_COLS = EXTRA_SUGGESTION_COLS + [
    "pregunta_validacion", "cumplimiento_score", "fte_pct", "riesgo_score", "potencial_ahorro_min_dia", "hallazgo"
]


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


def _table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, definition: str) -> None:
    cols = _table_columns(conn, table)
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")


def init_db() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS consultants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                sheet_name TEXT,
                organizacion TEXT,
                area TEXT,
                departamento TEXT,
                cargo TEXT NOT NULL,
                supervisor TEXT,
                condicion TEXT,
                mision TEXT,
                estado TEXT DEFAULT 'Activo',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            CREATE TABLE IF NOT EXISTS dop_functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                code TEXT,
                description TEXT NOT NULL,
                sort_order INTEGER,
                FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS suggested_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                function_id INTEGER,
                cod TEXT,
                funcion_origen TEXT,
                proceso TEXT,
                actividad TEXT,
                tipo_actividad TEXT,
                pregunta_validacion TEXT,
                evidencia_esperada TEXT,
                herramienta_sistema TEXT,
                entregable TEXT,
                indicador TEXT,
                criticidad TEXT,
                automatizable TEXT,
                riesgo TEXT,
                dependencia TEXT,
                comentarios_proyecto TEXT,
                opt TEXT,
                nivel_confianza REAL,
                supuesto_ia INTEGER DEFAULT 1,
                aprobado INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY(function_id) REFERENCES dop_functions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                consultant_id INTEGER,
                entrevistado TEXT,
                fecha TEXT,
                estado TEXT DEFAULT 'Borrador',
                conclusion TEXT,
                analysis_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(role_id) REFERENCES roles(id),
                FOREIGN KEY(consultant_id) REFERENCES consultants(id)
            );

            CREATE TABLE IF NOT EXISTS lda_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interview_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                cod TEXT,
                funcion_origen TEXT,
                proceso TEXT,
                actividad TEXT,
                tipo_actividad TEXT,
                pregunta_validacion TEXT,
                evidencia_esperada TEXT,
                herramienta_sistema TEXT,
                entregable TEXT,
                indicador TEXT,
                criticidad TEXT,
                automatizable TEXT,
                riesgo TEXT,
                dependencia TEXT,
                semana_1 INTEGER DEFAULT 0,
                semana_2 INTEGER DEFAULT 0,
                semana_3 INTEGER DEFAULT 0,
                semana_4 INTEGER DEFAULT 0,
                diario REAL DEFAULT 0,
                semanal REAL DEFAULT 0,
                quincenal REAL DEFAULT 0,
                mensual REAL DEFAULT 0,
                anual REAL DEFAULT 0,
                tiempo_x_unidad_min REAL DEFAULT 0,
                comentarios_usuario TEXT,
                comentarios_proyecto TEXT,
                opt TEXT,
                cumplimiento TEXT,
                evidencia TEXT,
                vol_mes REAL,
                val INTEGER,
                min_mes REAL,
                hrs_mes REAL,
                min_dia REAL,
                fte_pct REAL,
                cumplimiento_score REAL,
                riesgo_score REAL,
                potencial_ahorro_min_dia REAL,
                hallazgo TEXT,
                errores_validacion TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(interview_id) REFERENCES interviews(id) ON DELETE CASCADE,
                FOREIGN KEY(role_id) REFERENCES roles(id)
            );
            """
        )

        # Migraciones suaves por si se abre una base v2.
        for col in ["analysis_json"]:
            _add_column_if_missing(conn, "interviews", col, "TEXT")
        for col in EXTRA_SUGGESTION_COLS:
            _add_column_if_missing(conn, "suggested_activities", col, "TEXT")
        for col in EXTRA_RECORD_COLS:
            definition = "REAL" if col in {"cumplimiento_score", "fte_pct", "riesgo_score", "potencial_ahorro_min_dia"} else "TEXT"
            _add_column_if_missing(conn, "lda_records", col, definition)
        conn.commit()
    ensure_default_settings()
    ensure_default_consultants()


def ensure_default_settings() -> None:
    defaults = {
        "standard_daily_minutes": "360",
        "openai_model": "gpt-4o-mini",
        "use_ai": "false",
        "openai_api_key": "",
    }
    with get_conn() as conn:
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))
        conn.commit()


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: Any) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        conn.commit()


def ensure_default_consultants() -> None:
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) c FROM consultants").fetchone()["c"]
        if count == 0:
            conn.executemany(
                "INSERT INTO consultants(name, email) VALUES(?, ?)",
                [("Consultor Principal", ""), ("Andrés Celemín", "")],
            )
            conn.commit()


def get_or_create_company(name: str) -> int:
    clean = (name or "Empresa sin nombre").strip() or "Empresa sin nombre"
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO companies(name) VALUES(?)", (clean,))
        row = conn.execute("SELECT id FROM companies WHERE name=?", (clean,)).fetchone()
        conn.commit()
        return int(row["id"])


def insert_role(role: Dict[str, Any]) -> int:
    company_id = get_or_create_company(role.get("organizacion") or role.get("company") or "Empresa sin nombre")
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO roles(company_id, sheet_name, organizacion, area, departamento, cargo, supervisor, condicion, mision)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                role.get("sheet_name"),
                role.get("organizacion"),
                role.get("area"),
                role.get("departamento"),
                role.get("cargo") or role.get("sheet_name") or "Cargo sin nombre",
                role.get("supervisor"),
                role.get("condicion"),
                role.get("mision"),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def insert_function(role_id: int, code: str, description: str, sort_order: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO dop_functions(role_id, code, description, sort_order) VALUES(?, ?, ?, ?)",
            (role_id, code, description, sort_order),
        )
        conn.commit()
        return int(cur.lastrowid)


def insert_suggested_activity(role_id: int, function_id: Optional[int], item: Dict[str, Any]) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO suggested_activities(
                role_id, function_id, cod, funcion_origen, proceso, actividad, tipo_actividad,
                pregunta_validacion, evidencia_esperada, herramienta_sistema, entregable, indicador,
                criticidad, automatizable, riesgo, dependencia, comentarios_proyecto, opt,
                nivel_confianza, supuesto_ia, aprobado
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                role_id,
                function_id,
                item.get("cod"),
                item.get("funcion_origen"),
                item.get("proceso"),
                item.get("actividad"),
                item.get("tipo_actividad"),
                item.get("pregunta_validacion"),
                item.get("evidencia_esperada"),
                item.get("herramienta_sistema"),
                item.get("entregable"),
                item.get("indicador"),
                item.get("criticidad"),
                item.get("automatizable"),
                item.get("riesgo"),
                item.get("dependencia"),
                item.get("comentarios_proyecto"),
                item.get("opt"),
                float(item.get("nivel_confianza") or 0),
                1 if item.get("supuesto_ia", True) else 0,
                1,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def replace_suggestions(role_id: int, items: List[Dict[str, Any]]) -> None:
    functions = get_functions(role_id)
    function_id_by_code = {str(f.get("code", "")): f.get("id") for f in functions}
    with get_conn() as conn:
        conn.execute("DELETE FROM suggested_activities WHERE role_id=?", (role_id,))
        conn.commit()
    for item in items:
        fid = function_id_by_code.get(str(item.get("cod", "")))
        insert_suggested_activity(role_id, fid, item)


def list_companies() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM companies ORDER BY name"))


def list_consultants() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM consultants WHERE active=1 ORDER BY name"))


def add_consultant(name: str, email: str = "") -> None:
    if not name.strip():
        return
    with get_conn() as conn:
        conn.execute("INSERT INTO consultants(name, email) VALUES(?, ?)", (name.strip(), email.strip()))
        conn.commit()


def list_roles() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT r.*, c.name AS company_name,
                    (SELECT COUNT(*) FROM dop_functions f WHERE f.role_id=r.id) AS function_count,
                    (SELECT COUNT(*) FROM suggested_activities s WHERE s.role_id=r.id) AS suggestion_count
                FROM roles r
                JOIN companies c ON c.id=r.company_id
                ORDER BY r.created_at DESC, r.cargo
                """
            )
        )


def get_role(role_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT r.*, c.name AS company_name
            FROM roles r JOIN companies c ON c.id=r.company_id
            WHERE r.id=?
            """,
            (role_id,),
        ).fetchone()
        return dict(row) if row else None


def get_functions(role_id: int) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(
            conn.execute("SELECT * FROM dop_functions WHERE role_id=? ORDER BY sort_order, id", (role_id,))
        )


def get_suggestions(role_id: int) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT * FROM suggested_activities WHERE role_id=? AND aprobado=1 ORDER BY id",
                (role_id,),
            )
        )


def create_interview(role_id: int, consultant_id: Optional[int], entrevistado: str, fecha: str, estado: str = "Enviado") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO interviews(role_id, consultant_id, entrevistado, fecha, estado) VALUES(?, ?, ?, ?, ?)",
            (role_id, consultant_id, entrevistado, fecha, estado),
        )
        conn.commit()
        return int(cur.lastrowid)


def _record_tuple(interview_id: int, role_id: int, r: Dict[str, Any]) -> tuple:
    return (
        interview_id,
        role_id,
        r.get("cod"), r.get("funcion_origen"), r.get("proceso"), r.get("actividad"), r.get("tipo_actividad"),
        r.get("pregunta_validacion"), r.get("evidencia_esperada"), r.get("herramienta_sistema"), r.get("entregable"),
        r.get("indicador"), r.get("criticidad"), r.get("automatizable"), r.get("riesgo"), r.get("dependencia"),
        1 if r.get("semana_1") else 0, 1 if r.get("semana_2") else 0, 1 if r.get("semana_3") else 0, 1 if r.get("semana_4") else 0,
        r.get("diario", 0), r.get("semanal", 0), r.get("quincenal", 0), r.get("mensual", 0), r.get("anual", 0),
        r.get("tiempo_x_unidad_min", 0),
        r.get("comentarios_usuario"), r.get("comentarios_proyecto"), r.get("opt"), r.get("cumplimiento"), r.get("evidencia"),
        r.get("vol_mes", 0), r.get("val", 2), r.get("min_mes", 0), r.get("hrs_mes", 0), r.get("min_dia", 0), r.get("fte_pct", 0),
        r.get("cumplimiento_score", 0), r.get("riesgo_score", 0), r.get("potencial_ahorro_min_dia", 0), r.get("hallazgo"),
        r.get("errores_validacion"),
    )


def save_records(interview_id: int, role_id: int, records: List[Dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM lda_records WHERE interview_id=?", (interview_id,))
        sql = """
            INSERT INTO lda_records(
                interview_id, role_id, cod, funcion_origen, proceso, actividad, tipo_actividad,
                pregunta_validacion, evidencia_esperada, herramienta_sistema, entregable, indicador,
                criticidad, automatizable, riesgo, dependencia,
                semana_1, semana_2, semana_3, semana_4,
                diario, semanal, quincenal, mensual, anual, tiempo_x_unidad_min,
                comentarios_usuario, comentarios_proyecto, opt, cumplimiento, evidencia,
                vol_mes, val, min_mes, hrs_mes, min_dia, fte_pct,
                cumplimiento_score, riesgo_score, potencial_ahorro_min_dia, hallazgo, errores_validacion
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for r in records:
            conn.execute(sql, _record_tuple(interview_id, role_id, r))
        conn.commit()


def update_interview_conclusion(interview_id: int, conclusion: str, estado: str = "Analizado", analysis_json: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE interviews SET conclusion=?, analysis_json=?, estado=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (conclusion, analysis_json, estado, interview_id),
        )
        conn.commit()


def list_interviews() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(
            conn.execute(
                """
                SELECT i.*, r.cargo, r.area, c.name AS company_name, coalesce(k.name, '') AS consultant_name,
                    (SELECT COUNT(*) FROM lda_records lr WHERE lr.interview_id=i.id) AS record_count,
                    (SELECT ROUND(SUM(lr.min_dia), 2) FROM lda_records lr WHERE lr.interview_id=i.id AND lr.val=1) AS total_min_dia
                FROM interviews i
                JOIN roles r ON r.id=i.role_id
                JOIN companies c ON c.id=r.company_id
                LEFT JOIN consultants k ON k.id=i.consultant_id
                ORDER BY i.created_at DESC
                """
            )
        )


def get_interview(interview_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
                SELECT i.*, r.cargo, r.area, r.departamento, r.mision, c.name AS company_name, coalesce(k.name, '') AS consultant_name
                FROM interviews i
                JOIN roles r ON r.id=i.role_id
                JOIN companies c ON c.id=r.company_id
                LEFT JOIN consultants k ON k.id=i.consultant_id
                WHERE i.id=?
            """,
            (interview_id,),
        ).fetchone()
        return dict(row) if row else None


def get_records(interview_id: int) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM lda_records WHERE interview_id=? ORDER BY id", (interview_id,)))


def delete_database() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()


def seed_demo_interviews_if_empty() -> bool:
    """Crea entrevistas reales de ejemplo para que el dashboard no aparezca en cero."""
    if list_interviews():
        return False
    roles = list_roles()
    consultants = list_consultants()
    if not roles or not consultants:
        return False
    from .lda_rules import enrich_records_for_analysis

    for idx, role in enumerate(roles[:2], start=1):
        suggestions = get_suggestions(role["id"])
        if not suggestions:
            continue
        interview_id = create_interview(role["id"], consultants[min(idx - 1, len(consultants)-1)]["id"], "MANUEL PEREZ" if idx == 1 else "VALERIA TORRES", "2026-06-29", estado="Demo analizado")
        rows = []
        for i, s in enumerate(suggestions[:12], start=1):
            # Datos realistas solo para demo. El consultor puede borrarlos o crear una entrevista nueva.
            if i in {1, 2}:
                freq = {"mensual": 1, "semana_1": True, "tiempo_x_unidad_min": 45 + i * 5}
            elif i in {3, 7, 10}:
                freq = {"semanal": 1, "semana_1": True, "semana_2": True, "semana_3": True, "semana_4": True, "tiempo_x_unidad_min": 60 + i * 4}
            elif i in {4, 8}:
                freq = {"quincenal": 1, "semana_1": True, "semana_3": True, "tiempo_x_unidad_min": 90}
            else:
                freq = {"diario": 1, "semana_1": True, "semana_2": True, "semana_3": True, "semana_4": True, "tiempo_x_unidad_min": 25 + i * 3}
            cumplimiento = "Sí" if i not in {5, 9} else "Parcial"
            row = {
                "cod": s.get("cod"),
                "funcion_origen": s.get("funcion_origen"),
                "proceso": s.get("proceso"),
                "actividad": s.get("actividad"),
                "tipo_actividad": s.get("tipo_actividad") or "Core",
                "pregunta_validacion": s.get("pregunta_validacion"),
                "evidencia_esperada": s.get("evidencia_esperada"),
                "herramienta_sistema": s.get("herramienta_sistema"),
                "entregable": s.get("entregable"),
                "indicador": s.get("indicador"),
                "criticidad": s.get("criticidad") or "Media",
                "automatizable": s.get("automatizable") or "Media",
                "riesgo": s.get("riesgo"),
                "dependencia": s.get("dependencia"),
                "comentarios_proyecto": s.get("comentarios_proyecto"),
                "opt": s.get("opt") or "-",
                "cumplimiento": cumplimiento,
                "evidencia": s.get("evidencia_esperada") or "Entregable validado en entrevista",
                "comentarios_usuario": "Dato demo realista precargado. Reemplazar con entrevista real.",
                **freq,
            }
            rows.append(row)
        records = enrich_records_for_analysis(rows, float(get_setting("standard_daily_minutes", "360") or 360))
        save_records(interview_id, role["id"], records)
        conclusion = f"Entrevista demo cargada con volumetría realista para {role.get('cargo')}. Reemplazar por levantamiento real del consultor."
        update_interview_conclusion(interview_id, conclusion, estado="Demo analizado")
    return True
