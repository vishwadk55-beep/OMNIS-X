"""
OMNIS-X Persistent Quantitative Historical Dataset & Q&A Store
Stores chronological snapshots and quantitative dataset answers in SQLite.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def default_history_db_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "campus_twin.db"


_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS dataset_qa_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    question TEXT NOT NULL,
    answer_summary TEXT NOT NULL,
    overall_health_pct REAL NOT NULL,
    resilience_index REAL NOT NULL,
    open_problems_count INTEGER NOT NULL,
    active_disruptions_count INTEGER NOT NULL,
    active_conflicts_count INTEGER NOT NULL,
    hard_conflicts_count INTEGER NOT NULL,
    students_affected INTEGER NOT NULL,
    faculty_affected INTEGER NOT NULL,
    activities_impacted INTEGER NOT NULL,
    rooms_unavailable INTEGER NOT NULL,
    classes_count INTEGER NOT NULL,
    labs_count INTEGER NOT NULL,
    exams_count INTEGER NOT NULL,
    est_energy_delta_kwh REAL NOT NULL,
    est_cost_inr REAL NOT NULL,
    est_co2_kg REAL NOT NULL,
    is_simulated INTEGER NOT NULL DEFAULT 1,
    details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_qa_history_time ON dataset_qa_history(recorded_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_qa_history_type ON dataset_qa_history(event_type, id DESC);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or default_history_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_history_table(db_path: Path | None = None) -> None:
    """Create the historical quantitative Q&A table and indexes if missing."""
    with closing(_connect(db_path)) as conn, conn:
        conn.executescript(_HISTORY_DDL)


def append_history_record(
    record: dict[str, Any],
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Insert a quantitative snapshot / Q&A answer row and return the stored dict."""
    init_history_table(db_path)
    recorded_at = str(
        record.get("recorded_at")
        or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    details = record.get("details")
    details_json = json.dumps(details if isinstance(details, dict) else {})

    params = (
        recorded_at,
        str(record.get("event_type", "snapshot")),
        str(record.get("target_entity", "CAMPUS")),
        str(record.get("question", "")),
        str(record.get("answer_summary", "")),
        float(record.get("overall_health_pct", 100.0)),
        float(record.get("resilience_index", 100.0)),
        int(record.get("open_problems_count", 0)),
        int(record.get("active_disruptions_count", 0)),
        int(record.get("active_conflicts_count", 0)),
        int(record.get("hard_conflicts_count", 0)),
        int(record.get("students_affected", 0)),
        int(record.get("faculty_affected", 0)),
        int(record.get("activities_impacted", 0)),
        int(record.get("rooms_unavailable", 0)),
        int(record.get("classes_count", 0)),
        int(record.get("labs_count", 0)),
        int(record.get("exams_count", 0)),
        float(record.get("est_energy_delta_kwh", 0.0)),
        float(record.get("est_cost_inr", 0.0)),
        float(record.get("est_co2_kg", 0.0)),
        int(bool(record.get("is_simulated", True))),
        details_json,
    )

    with closing(_connect(db_path)) as conn, conn:
        cur = conn.execute(
            """
            INSERT INTO dataset_qa_history (
                recorded_at, event_type, target_entity, question, answer_summary,
                overall_health_pct, resilience_index, open_problems_count,
                active_disruptions_count, active_conflicts_count, hard_conflicts_count,
                students_affected, faculty_affected, activities_impacted,
                rooms_unavailable, classes_count, labs_count, exams_count,
                est_energy_delta_kwh, est_cost_inr, est_co2_kg,
                is_simulated, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        row_id = int(cur.lastrowid or 0)
        row = conn.execute(
            "SELECT * FROM dataset_qa_history WHERE id = ?",
            (row_id,),
        ).fetchone()

    return _row_to_dict(row) if row else {"id": row_id}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    raw_details = row["details_json"] or "{}"
    try:
        details = json.loads(raw_details)
    except json.JSONDecodeError:
        details = {}
    return {
        "id": int(row["id"]),
        "recorded_at": row["recorded_at"],
        "event_type": row["event_type"],
        "target_entity": row["target_entity"],
        "question": row["question"],
        "answer_summary": row["answer_summary"],
        "overall_health_pct": round(float(row["overall_health_pct"]), 1),
        "resilience_index": round(float(row["resilience_index"]), 1),
        "open_problems_count": int(row["open_problems_count"]),
        "active_disruptions_count": int(row["active_disruptions_count"]),
        "active_conflicts_count": int(row["active_conflicts_count"]),
        "hard_conflicts_count": int(row["hard_conflicts_count"]),
        "students_affected": int(row["students_affected"]),
        "faculty_affected": int(row["faculty_affected"]),
        "activities_impacted": int(row["activities_impacted"]),
        "rooms_unavailable": int(row["rooms_unavailable"]),
        "classes_count": int(row["classes_count"]),
        "labs_count": int(row["labs_count"]),
        "exams_count": int(row["exams_count"]),
        "est_energy_delta_kwh": round(float(row["est_energy_delta_kwh"]), 2),
        "est_cost_inr": round(float(row["est_cost_inr"]), 2),
        "est_co2_kg": round(float(row["est_co2_kg"]), 2),
        "is_simulated": bool(row["is_simulated"]),
        "details": details,
    }


def list_history_records(
    limit: int = 100,
    event_type: str | None = None,
    search: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Query historical quantitative Q&A records plus aggregate statistics."""
    init_history_table(db_path)
    clauses: list[str] = []
    args: list[Any] = []

    if event_type and event_type != "all":
        if event_type == "simulations":
            clauses.append("event_type IN ('outage_simulation', 'macro_simulation', 'preset_scenario')")
        elif event_type == "recoveries":
            clauses.append("event_type IN ('recovery_applied', 'problem_solved', 'solve_all')")
        else:
            clauses.append("event_type = ?")
            args.append(event_type)

    if search and search.strip():
        q = f"%{search.strip()}%"
        clauses.append("(question LIKE ? OR answer_summary LIKE ? OR target_entity LIKE ?)")
        args.extend([q, q, q])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(int(limit), 500))

    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            f"SELECT * FROM dataset_qa_history {where_sql} ORDER BY id DESC LIMIT ?",
            [*args, safe_limit],
        ).fetchall()

        agg = conn.execute(
            """
            SELECT
                COUNT(*) AS total_records,
                SUM(CASE WHEN event_type = 'question_answered' THEN 1 ELSE 0 END) AS questions_answered,
                SUM(CASE WHEN event_type IN ('outage_simulation', 'macro_simulation', 'preset_scenario')
                    THEN 1 ELSE 0 END) AS simulations_logged,
                SUM(CASE WHEN event_type IN ('recovery_applied', 'problem_solved', 'solve_all')
                    THEN 1 ELSE 0 END) AS recoveries_logged,
                COALESCE(MAX(students_affected), 0) AS peak_students_affected,
                COALESCE(MAX(activities_impacted), 0) AS peak_activities_impacted,
                COALESCE(ROUND(AVG(overall_health_pct), 1), 100.0) AS avg_health_pct,
                COALESCE(ROUND(AVG(resilience_index), 1), 100.0) AS avg_resilience_index,
                COALESCE(ROUND(SUM(est_cost_inr), 2), 0.0) AS cumulative_est_cost_inr,
                COALESCE(ROUND(SUM(est_energy_delta_kwh), 2), 0.0) AS cumulative_est_energy_kwh,
                COALESCE(ROUND(SUM(est_co2_kg), 2), 0.0) AS cumulative_est_co2_kg
            FROM dataset_qa_history
            """
        ).fetchone()

    summary = {
        "total_records": int(agg["total_records"] or 0),
        "questions_answered": int(agg["questions_answered"] or 0),
        "simulations_logged": int(agg["simulations_logged"] or 0),
        "recoveries_logged": int(agg["recoveries_logged"] or 0),
        "peak_students_affected": int(agg["peak_students_affected"] or 0),
        "peak_activities_impacted": int(agg["peak_activities_impacted"] or 0),
        "avg_health_pct": float(agg["avg_health_pct"] or 100.0),
        "avg_resilience_index": float(agg["avg_resilience_index"] or 100.0),
        "cumulative_est_cost_inr": float(agg["cumulative_est_cost_inr"] or 0.0),
        "cumulative_est_energy_kwh": float(agg["cumulative_est_energy_kwh"] or 0.0),
        "cumulative_est_co2_kg": float(agg["cumulative_est_co2_kg"] or 0.0),
    }

    return {
        "records": [_row_to_dict(r) for r in rows],
        "summary": summary,
    }


def export_history_csv(db_path: Path | None = None) -> str:
    """Serialize all stored quantitative dataset Q&A rows as RFC-4180 CSV."""
    data = list_history_records(limit=500, db_path=db_path)
    buf = io.StringIO()
    fields = [
        "id",
        "recorded_at",
        "event_type",
        "target_entity",
        "question",
        "answer_summary",
        "overall_health_pct",
        "resilience_index",
        "open_problems_count",
        "active_disruptions_count",
        "active_conflicts_count",
        "hard_conflicts_count",
        "students_affected",
        "faculty_affected",
        "activities_impacted",
        "rooms_unavailable",
        "classes_count",
        "labs_count",
        "exams_count",
        "est_energy_delta_kwh",
        "est_cost_inr",
        "est_co2_kg",
        "is_simulated",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for rec in data["records"]:
        writer.writerow(rec)
    return buf.getvalue()
