"""
OMNIS-X Quantitative Dataset Q&A & Snapshot Extractor
Answers operational questions directly from live campus records and metrics.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.campus_store import CampusTwinData
from ..core.history_store import append_history_record, list_history_records
from ..core.models import InstitutionState
from .dependency_graph import DependencyGraph
from .problem_solver import ProblemResolver

PRESET_DATASET_QUESTIONS: list[dict[str, str]] = [
    {
        "id": "q_readiness",
        "label": "Readiness & Resilience?",
        "question": "What is the current campus readiness, overall health, and resilience index?",
    },
    {
        "id": "q_impact",
        "label": "Affected Assets & Students?",
        "question": "Which buildings, rooms, students, and sessions are currently affected?",
    },
    {
        "id": "q_problems",
        "label": "Problems & Conflicts?",
        "question": "How many open problems and hard rule conflicts exist in the dataset right now?",
    },
    {
        "id": "q_risk",
        "label": "Highest Risk System?",
        "question": "Which campus system carries the highest dependency cascade risk right now?",
    },
    {
        "id": "q_recovery",
        "label": "Recovery & Savings (Sim)?",
        "question": "What is the current recovery status and simulated energy, cost, and CO2 impact?",
    },
    {
        "id": "q_inventory",
        "label": "Full Twin Capacity?",
        "question": "What is the complete campus digital twin dataset capacity across buildings and rooms?",
    },
]


def build_quantitative_snapshot(
    state: InstitutionState,
    campus_twin: CampusTwinData,
    last_outage_report: dict[str, Any] | None = None,
    graph: DependencyGraph | None = None,
) -> dict[str, Any]:
    """Compute a consistent, exact quantitative feature vector from current campus state."""
    state.compute_overall_health()
    problems = ProblemResolver(state, campus_twin, last_outage_report).collect_problems()
    g = graph or DependencyGraph()
    risk_ranking = g.get_module_risk_rank()
    top_risk_mod, top_risk_score = risk_ranking[0] if risk_ranking else ("power", 0.0)

    has_active_outage = bool(last_outage_report and not last_outage_report.get("applied_option"))
    applied_outage = bool(last_outage_report and last_outage_report.get("applied_option"))
    impact_counts = (last_outage_report or {}).get("impact_counts", {})

    if has_active_outage:
        students_affected = int(impact_counts.get("students", 0))
        faculty_affected = int(impact_counts.get("faculty", 0))
        activities_impacted = int(impact_counts.get("total_activities", 0))
        classes_cnt = int(impact_counts.get("classes", 0))
        labs_cnt = int(impact_counts.get("labs", 0))
        exams_cnt = int(impact_counts.get("exams", 0))
        hard_conflicts = max(
            sum(1 for c in state.constraints if c.violated and c.priority.value == "hard"),
            int(impact_counts.get("hard_conflicts_after_recovery", 0)),
        )
        target_entity = str((last_outage_report or {}).get("event", {}).get("target_id", "CAMPUS"))
    elif applied_outage:
        students_affected = 0 if len(problems) == 0 else int(impact_counts.get("students", 0))
        faculty_affected = 0 if len(problems) == 0 else int(impact_counts.get("faculty", 0))
        activities_impacted = int(impact_counts.get("total_activities", 0))
        classes_cnt = int(impact_counts.get("classes", 0))
        labs_cnt = int(impact_counts.get("labs", 0))
        exams_cnt = int(impact_counts.get("exams", 0))
        hard_conflicts = int(impact_counts.get("hard_conflicts_after_recovery", 0))
        target_entity = str((last_outage_report or {}).get("event", {}).get("target_id", "CAMPUS"))
    else:
        students_affected = min(
            state.student_count,
            sum(d.students_affected for d in state.active_disruptions),
        )
        faculty_affected = min(
            state.faculty_count,
            sum(d.faculty_affected for d in state.active_disruptions),
        )
        activities_impacted = 0
        classes_cnt = 0
        labs_cnt = 0
        exams_cnt = 0
        hard_conflicts = sum(
            1
            for c in state.constraints
            if c.violated and c.priority.value == "hard"
        )
        target_entity = (
            state.active_disruptions[0].affected_modules[0].upper()
            if state.active_disruptions and state.active_disruptions[0].affected_modules
            else "CAMPUS"
        )

    rooms_unavail = sum(1 for r in campus_twin.rooms.values() if r.status != "operational")
    open_cnt = len(problems)
    disrupt_cnt = len(state.active_disruptions)
    active_conflicts_cnt = len(state.active_conflicts)

    # Prototype composite resilience index (0-100; non-certified heuristic)
    infra = float(state.overall_health)
    dep_risk = min(100.0, disrupt_cnt * 18.0 + open_cnt * 1.8)
    readiness = 100.0 if open_cnt == 0 else max(20.0, 95.0 - hard_conflicts * 14.0 - open_cnt * 1.5)
    resource_eff = max(35.0, 100.0 - rooms_unavail * 5.0 - active_conflicts_cnt * 3.0)
    resilience_index = round(
        max(0.0, min(100.0, 0.35 * infra + 0.25 * (100.0 - dep_risk) + 0.25 * readiness + 0.15 * resource_eff)),
        1,
    )

    # Simulated tariff/CO2 projection aligned with frontend _estimateCampusRoi()
    if open_cnt > 0 or has_active_outage:
        est_cost_inr = round(max(1, open_cnt) * 4850.0 + students_affected * 22.0, 2)
        est_energy_kwh = round(est_cost_inr / 15.0, 2)
        est_co2_kg = round(est_energy_kwh * 0.72, 2)
        roi_mode = "crisis_exposure_per_hr_sim"
    elif applied_outage and open_cnt == 0:
        rec_acts = max(1, activities_impacted)
        rec_stu = int(impact_counts.get("students", 180))
        est_cost_inr = round(rec_acts * 11500.0 + rec_stu * 110.0, 2)
        est_energy_kwh = round(180.0 + rec_acts * 42.0, 2)
        est_co2_kg = round(est_energy_kwh * 0.72, 2)
        roi_mode = "continuity_savings_sim"
    else:
        est_energy_kwh = 0.0
        est_cost_inr = 0.0
        est_co2_kg = 0.0
        roi_mode = "baseline_nominal"

    return {
        "target_entity": target_entity,
        "overall_health_pct": round(float(state.overall_health), 1),
        "resilience_index": resilience_index,
        "open_problems_count": open_cnt,
        "active_disruptions_count": disrupt_cnt,
        "active_conflicts_count": active_conflicts_cnt,
        "hard_conflicts_count": hard_conflicts,
        "students_affected": students_affected,
        "faculty_affected": faculty_affected,
        "activities_impacted": activities_impacted,
        "rooms_unavailable": rooms_unavail,
        "classes_count": classes_cnt,
        "labs_count": labs_cnt,
        "exams_count": exams_cnt,
        "est_energy_delta_kwh": est_energy_kwh,
        "est_cost_inr": est_cost_inr,
        "est_co2_kg": est_co2_kg,
        "is_simulated": True,
        "details": {
            "roi_mode": roi_mode,
            "top_risk_module": top_risk_mod,
            "top_risk_score": round(float(top_risk_score), 3),
            "total_modules": len(state.modules),
            "healthy_modules": sum(1 for m in state.modules.values() if m.health_score >= 80.0),
            "total_buildings": len(campus_twin.buildings),
            "total_rooms": len(campus_twin.rooms),
            "total_seat_capacity": sum(r.capacity for r in campus_twin.rooms.values()),
            "total_activities": len(campus_twin.activities),
            "problems_sample": [p["id"] for p in problems[:5]],
        },
    }


def answer_dataset_question(
    question: str,
    state: InstitutionState,
    campus_twin: CampusTwinData,
    last_outage_report: dict[str, Any] | None = None,
    graph: DependencyGraph | None = None,
    persist: bool = True,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Answer an operational question quantitatively using live twin records."""
    q_clean = question.strip() or PRESET_DATASET_QUESTIONS[0]["question"]
    q_low = q_clean.lower()
    snap = build_quantitative_snapshot(state, campus_twin, last_outage_report, graph)
    det = snap["details"]

    down_zones = [z.id for z in campus_twin.power_zones.values() if z.status != "operational"]
    down_bldgs = [b.id for b in campus_twin.buildings.values() if b.status != "operational"]
    down_rooms = [r.id for r in campus_twin.rooms.values() if r.status != "operational"]
    hard_violated = [c.id for c in state.constraints if c.violated and c.priority.value == "hard"]

    if any(
        k in q_low
        for k in ("capacity", "inventory", "how many buildings", "how many rooms", "dataset size", "twin")
    ):
        answer = (
            f"Campus twin contains {len(campus_twin.power_zones)} power zones, "
            f"{det['total_buildings']} buildings, {det['total_rooms']} rooms "
            f"({det['total_seat_capacity']:,} total seats), {len(campus_twin.faculty)} faculty, "
            f"{len(campus_twin.batches)} batches ({state.student_count:,} enrolled students), and "
            f"{det['total_activities']} scheduled activities across {det['total_modules']} institutional domains."
        )
    elif any(k in q_low for k in ("risk", "cascade", "vulnerab", "dependen")):
        g = graph or DependencyGraph()
        top3 = ", ".join(f"{m} ({s:.3f})" for m, s in g.get_module_risk_rank()[:3])
        downstream = g.get_downstream_modules(det["top_risk_module"])
        answer = (
            f"Highest cascade risk module is '{det['top_risk_module']}' (score {det['top_risk_score']:.3f}, "
            f"{len(downstream)} downstream systems). Top 3: {top3}. Current open conflicts: "
            f"{snap['active_conflicts_count']} (hard={snap['hard_conflicts_count']})."
        )
    elif any(k in q_low for k in ("problem", "conflict", "violation", "fix", "rule")):
        top_ids = ", ".join(det["problems_sample"]) if det["problems_sample"] else "none"
        viol_str = ", ".join(hard_violated) if hard_violated else "none"
        answer = (
            f"Dataset currently records {snap['open_problems_count']} open problem(s) (sample: {top_ids}), "
            f"{snap['active_conflicts_count']} operational conflict(s), and {snap['hard_conflicts_count']} "
            f"hard rule violation(s) ({viol_str}); {snap['rooms_unavailable']} room(s) unavailable."
        )
    elif any(k in q_low for k in ("energy", "cost", "co2", "carbon", "saving", "recover", "financial", "inr")):
        rec_opt = (last_outage_report or {}).get("applied_option")
        mode_note = "Simulated failover recovery applied" if rec_opt else "Simulated live assessment"
        answer = (
            f"{mode_note} ({det['roi_mode']}): health={snap['overall_health_pct']}%, "
            f"CRI={snap['resilience_index']}/100, est. energy={snap['est_energy_delta_kwh']} kWh, "
            f"est. INR={snap['est_cost_inr']:,.2f}, est. CO2={snap['est_co2_kg']} kg (Simulated estimates)."
        )
    elif any(
        k in q_low
        for k in ("affect", "impact", "student", "faculty", "room", "building", "session", "exam", "block")
    ):
        b_str = ", ".join(down_bldgs) if down_bldgs else "none"
        r_str = ", ".join(down_rooms) if down_rooms else "none"
        z_str = ", ".join(down_zones) if down_zones else "none"
        answer = (
            f"Affected scope: {snap['students_affected']} student(s), {snap['faculty_affected']} faculty, "
            f"{snap['activities_impacted']} session(s) ({snap['classes_count']} classes, {snap['labs_count']} labs, "
            f"{snap['exams_count']} exams). Down zones=[{z_str}], buildings=[{b_str}], rooms=[{r_str}]."
        )
    else:
        answer = (
            f"Readiness={snap['overall_health_pct']}% ({det['healthy_modules']}/"
            f"{det['total_modules']} healthy modules), Resilience Index={snap['resilience_index']}/100, "
            f"active disruptions={snap['active_disruptions_count']}, open problems="
            f"{snap['open_problems_count']}, students affected={snap['students_affected']}, "
            f"hard conflicts={snap['hard_conflicts_count']}."
        )

    payload = {
        **snap,
        "event_type": "question_answered",
        "question": q_clean,
        "answer_summary": answer,
    }
    if persist:
        return append_history_record(payload, db_path=db_path)
    return payload


def seed_initial_history_if_empty(
    state: InstitutionState,
    campus_twin: CampusTwinData,
    graph: DependencyGraph | None = None,
    db_path: Path | None = None,
) -> None:
    """Populate initial quantitative dataset Q&A records if the persistent history table is empty."""
    existing = list_history_records(limit=1, db_path=db_path)
    if existing["summary"]["total_records"] > 0:
        return
    answer_dataset_question(
        PRESET_DATASET_QUESTIONS[5]["question"],
        state,
        campus_twin,
        None,
        graph,
        persist=True,
        db_path=db_path,
    )
    answer_dataset_question(
        PRESET_DATASET_QUESTIONS[0]["question"],
        state,
        campus_twin,
        None,
        graph,
        persist=True,
        db_path=db_path,
    )


def record_event_snapshot(
    event_type: str,
    question: str,
    answer_summary: str,
    state: InstitutionState,
    campus_twin: CampusTwinData,
    last_outage_report: dict[str, Any] | None = None,
    graph: DependencyGraph | None = None,
    target_override: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Persist a quantitative dataset snapshot + Q&A summary triggered by a workflow action."""
    snap = build_quantitative_snapshot(state, campus_twin, last_outage_report, graph)
    if target_override:
        snap["target_entity"] = target_override
    return append_history_record(
        {
            **snap,
            "event_type": event_type,
            "question": question,
            "answer_summary": answer_summary,
        },
        db_path=db_path,
    )
