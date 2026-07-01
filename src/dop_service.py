from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import pandas as pd

from . import db
from .ai_graph import generate_activities_from_functions

WorkbookInput = Union[str, Path, BytesIO, Any]


def _non_empty_values(row) -> List[Tuple[int, str]]:
    values = []
    for idx, value in enumerate(row):
        if pd.notna(value) and str(value).strip():
            values.append((idx, str(value).strip()))
    return values


def _row_contains(values: List[Tuple[int, str]], needle: str) -> bool:
    n = needle.lower()
    return any(n in text.lower() for _, text in values)


def _first_text_after_label(rows: List[List[Any]], label: str, start: int = 0, max_lookahead: int = 3) -> str:
    label_l = label.lower()
    for i in range(start, len(rows)):
        values = _non_empty_values(rows[i])
        if _row_contains(values, label_l):
            for j in range(i + 1, min(i + 1 + max_lookahead, len(rows))):
                candidates = [text for _, text in _non_empty_values(rows[j])]
                candidates = [c for c in candidates if c.lower() != label_l and len(c) > 1]
                if candidates:
                    return candidates[0]
    return ""


def parse_dop_workbook(workbook: WorkbookInput) -> List[Dict[str, Any]]:
    xl = pd.ExcelFile(workbook)
    roles: List[Dict[str, Any]] = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(workbook, sheet_name=sheet, header=None, dtype=object)
        rows = df.values.tolist()
        role = _parse_dop_sheet(rows, sheet)
        if role.get("cargo") or role.get("functions"):
            roles.append(role)
    return roles


def _parse_dop_sheet(rows: List[List[Any]], sheet_name: str) -> Dict[str, Any]:
    role: Dict[str, Any] = {
        "sheet_name": sheet_name,
        "organizacion": "",
        "area": "",
        "departamento": "",
        "cargo": "",
        "supervisor": "",
        "condicion": "",
        "mision": "",
        "functions": [],
    }

    for i, row in enumerate(rows):
        values = _non_empty_values(row)
        if _row_contains(values, "ORGANIZACIÓN") or _row_contains(values, "ORGANIZACION"):
            if i + 1 < len(rows):
                next_values = _non_empty_values(rows[i + 1])
                texts = [text for _, text in next_values]
                if len(texts) >= 1:
                    role["organizacion"] = texts[0]
                if len(texts) >= 2:
                    role["area"] = texts[1]
                if len(texts) >= 3:
                    role["departamento"] = texts[2]
            break

    role["cargo"] = _first_text_after_label(rows, "DENOMINACION DEL PUESTO") or _first_text_after_label(rows, "DENOMINACIÓN DEL PUESTO") or sheet_name
    role["mision"] = _first_text_after_label(rows, "MISION DEL PUESTO", max_lookahead=2) or _first_text_after_label(rows, "MISIÓN DEL PUESTO", max_lookahead=2)

    for i, row in enumerate(rows):
        values = _non_empty_values(row)
        if _row_contains(values, "PUESTO DEL SUPERVISOR"):
            if i + 1 < len(rows):
                texts = [text for _, text in _non_empty_values(rows[i + 1])]
                if texts:
                    role["supervisor"] = texts[0]
                if len(texts) >= 2:
                    role["condicion"] = texts[-1]
            break

    start_idx = None
    for i, row in enumerate(rows):
        values = _non_empty_values(row)
        if _row_contains(values, "PRINCIPALES FUNCIONES"):
            start_idx = i + 1
            break

    functions: List[Dict[str, Any]] = []
    if start_idx is not None:
        order = 1
        for i in range(start_idx, len(rows)):
            values = _non_empty_values(rows[i])
            if not values:
                continue
            joined = " ".join(text for _, text in values)
            if "COMENTARIOS ADICIONALES" in joined.upper():
                break
            if len(values) >= 2:
                code = values[0][1]
                description = values[1][1]
            else:
                code = str(order)
                description = values[0][1]
            if len(description.strip()) >= 12:
                functions.append({"code": code, "description": description.strip(), "sort_order": order})
                order += 1
    role["functions"] = functions
    return role


def import_roles_to_database(
    roles: List[Dict[str, Any]],
    api_key: str | None = None,
    model: str | None = None,
    use_ai: bool = False,
) -> int:
    imported = 0
    for role in roles:
        role_id = db.insert_role(role)
        stored_role = db.get_role(role_id) or role
        function_id_by_code = {}
        functions = role.get("functions", [])
        for f in functions:
            fid = db.insert_function(role_id, f.get("code", ""), f.get("description", ""), int(f.get("sort_order") or 0))
            function_id_by_code[str(f.get("code", ""))] = fid

        suggestions = generate_activities_from_functions(functions, role=stored_role, api_key=api_key, model=model, use_ai=use_ai)
        for item in suggestions:
            fid = function_id_by_code.get(str(item.get("cod", "")))
            db.insert_suggested_activity(role_id, fid, item)
        imported += 1
    return imported


def import_dop_file(
    workbook: WorkbookInput,
    api_key: str | None = None,
    model: str | None = None,
    use_ai: bool = False,
) -> int:
    roles = parse_dop_workbook(workbook)
    return import_roles_to_database(roles, api_key=api_key, model=model, use_ai=use_ai)


def seed_sample_if_empty() -> bool:
    if db.list_roles():
        return False
    if not db.SAMPLE_DOP_PATH.exists():
        return False
    imported = import_dop_file(db.SAMPLE_DOP_PATH, use_ai=False)
    return imported > 0
