"""
OMNIS-X Flask API Server
Constraint-Based Institutional Digital Twin & Crisis Recovery System
"""
from typing import Any

from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

from backend.core.campus_store import CampusTwinData, load_campus_data
from backend.core.history_store import export_history_csv, list_history_records
from backend.core.institution_builder import build_institution
from backend.core.models import InstitutionState
from backend.engines.cascade_simulator import CascadeSimulator
from backend.engines.conflict_detector import ConflictDetector
from backend.engines.constraint_engine import STRATEGY_WEIGHTS, ConstraintEngine
from backend.engines.dataset_qa import (
    PRESET_DATASET_QUESTIONS,
    answer_dataset_question,
    record_event_snapshot,
    seed_initial_history_if_empty,
)
from backend.engines.dependency_graph import (
    DISRUPTION_IMPACT_MAP,
    PRESET_SCENARIOS,
    DependencyGraph,
)
from backend.engines.problem_solver import ProblemResolver
from backend.engines.recovery_planner import RecoveryPlanner
from backend.engines.schedule_solver import CampusScheduleSolver

app = Flask(
    __name__,
    template_folder="frontend/templates",
    static_folder="frontend/static",
)
CORS(app)

# ── Global State ─────────────────────────────────────────────────────────────
state: InstitutionState = build_institution()
campus_twin: CampusTwinData = load_campus_data(sync_sqlite=True)
graph = DependencyGraph()
last_outage_report: dict[str, Any] | None = None
seed_initial_history_if_empty(state, campus_twin, graph)


def _log_dataset_event(
    event_type: str,
    question: str,
    answer_summary: str,
    target_override: str | None = None,
) -> dict[str, Any]:
    return record_event_snapshot(
        event_type=event_type,
        question=question,
        answer_summary=answer_summary,
        state=state,
        campus_twin=campus_twin,
        last_outage_report=last_outage_report,
        graph=graph,
        target_override=target_override,
    )


def get_simulator():
    return CascadeSimulator(state)


def get_detector():
    return ConflictDetector(state)


def get_planner():
    return RecoveryPlanner(state)


def get_constraint_engine():
    return ConstraintEngine(state)


def get_schedule_solver():
    return CampusScheduleSolver(campus_twin)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state", methods=["GET"])
def get_state():
    """Get full institution state"""
    state.compute_overall_health()
    get_constraint_engine().evaluate_all()
    payload = state.to_dict()
    payload["last_outage_report"] = last_outage_report
    problems = ProblemResolver(state, campus_twin, last_outage_report).collect_problems()
    payload["open_problems"] = problems
    payload["open_problems_count"] = len(problems)
    return jsonify(payload)


def _state_with_problems() -> dict[str, Any]:
    """Build institution state dict enriched with live open problems list."""
    payload = state.to_dict()
    problems = ProblemResolver(state, campus_twin, last_outage_report).collect_problems()
    payload["open_problems"] = problems
    payload["open_problems_count"] = len(problems)
    return payload


@app.route("/api/campus-twin", methods=["GET"])
def get_campus_twin():
    """Get record-level digital twin data (power zones, buildings, rooms, faculty, batches, activities)."""
    payload = campus_twin.to_dict()
    payload["last_outage_report"] = last_outage_report
    return jsonify(payload)


@app.route("/api/modules", methods=["GET"])
def get_modules():
    """Get all module statuses"""
    return jsonify({k: v.to_dict() for k, v in state.modules.items()})


@app.route("/api/modules/<module_id>", methods=["GET"])
def get_module(module_id):
    """Get a specific module"""
    if module_id not in state.modules:
        return jsonify({"error": "Module not found"}), 404
    return jsonify(state.modules[module_id].to_dict())


@app.route("/api/constraints", methods=["GET"])
def get_constraints():
    """Get live constraint evaluations and competing resource contention"""
    strategy = request.args.get("strategy", "balanced")
    engine = get_constraint_engine()
    summary = engine.evaluate_all()
    if strategy in STRATEGY_WEIGHTS:
        summary["allocation_summary"] = engine.solve_competing_allocations(strategy=strategy)
    return jsonify({
        "constraints": [c.to_dict() for c in state.constraints],
        "resources": {k: v.to_dict() for k, v in state.resources.items()},
        "summary": summary,
        "available_strategies": list(STRATEGY_WEIGHTS.keys()),
    })


@app.route("/api/simulate-outage", methods=["POST"])
def simulate_record_outage():
    """Run 6-step BFS record-level outage simulation and rank recovery options (Score = 10C+5D+3B+2P)."""
    global last_outage_report
    data = request.json or {}
    target_id = data.get("target_id", "BLOCK_B")
    start_time = data.get("start_time", "09:00")
    end_time = data.get("end_time", "12:00")
    outage_type = data.get("outage_type", "power_outage")
    strategy = data.get("strategy", "exam_continuity")
    sync_macro = bool(data.get("sync_macro", True))

    try:
        report = get_schedule_solver().simulate_outage(
            target_id=target_id,
            start_time=start_time,
            end_time=end_time,
            outage_type=outage_type,
        )

        # Mark failed entities in campus twin status
        if target_id in campus_twin.power_zones:
            campus_twin.power_zones[target_id].status = "outage"
        elif target_id in campus_twin.buildings:
            campus_twin.buildings[target_id].status = "outage"
        elif target_id in campus_twin.faculty:
            campus_twin.faculty[target_id].status = "unavailable"
        for r_id in report["unavailable_rooms"]:
            if r_id in campus_twin.rooms:
                campus_twin.rooms[r_id].status = "unavailable"

        macro_disruption = None
        macro_plan = None
        if sync_macro:
            macro_map = {
                "power_outage": ("power_outage", "high"),
                "room_unavailable": ("classroom_unavailability", "high"),
                "faculty_unavailable": ("faculty_absence", "medium"),
                "equipment_failure": ("lab_equipment_failure", "high"),
            }
            m_type, m_sev = macro_map.get(outage_type, ("power_outage", "high"))
            macro_disruption, _ = get_simulator().simulate(m_type, m_sev)
            get_detector().detect_all_conflicts()
            macro_plan = get_planner().generate_plan(macro_disruption, strategy=strategy)

        report["macro_disruption_id"] = macro_disruption.id if macro_disruption else None
        report["macro_plan_id"] = macro_plan.id if macro_plan else None
        last_outage_report = report

        st_payload = _state_with_problems()
        ic = report["impact_counts"]
        _log_dataset_event(
            event_type="outage_simulation",
            question=f"What is the quantitative impact of {target_id} {outage_type} ({start_time}-{end_time})?",
            answer_summary=(
                f"{ic['total_activities']} session(s) ({ic['classes']} classes, {ic['labs']} labs, "
                f"{ic['exams']} exams), {ic['students']} student(s) & {ic['faculty']} faculty impacted; "
                f"{st_payload['open_problems_count']} open problem(s); health={st_payload['overall_health']:.1f}%."
            ),
            target_override=str(target_id),
        )

        return jsonify({
            "success": True,
            "outage_report": report,
            "state": st_payload,
            "campus_twin": campus_twin.to_dict(),
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/recovery-options/<option_id>/apply", methods=["POST"])
def apply_recovery_option(option_id):
    """Apply a ranked schedule recovery option (Score = 10C+5D+3B+2P) to the live campus twin."""
    if not last_outage_report:
        return jsonify({"success": False, "error": "No active outage simulation to recover."}), 400

    option = next(
        (o for o in last_outage_report.get("ranked_recovery_options", []) if o["id"] == option_id),
        None,
    )
    if not option:
        return jsonify({"success": False, "error": "Recovery option not found"}), 404
    if option.get("hard_conflicts", 0) > 0 and not option.get("assignments"):
        return jsonify({
            "success": False,
            "error": (
                "This option cannot auto-relocate without alternate hardware; "
                "use Auto-Solve or Restore Room directly."
            ),
        }), 400

    applied = get_schedule_solver().apply_option(option)

    # Restore entity statuses in campus twin when recovered
    for z in campus_twin.power_zones.values():
        z.status = "operational"
    for b in campus_twin.buildings.values():
        b.status = "operational"
    for r in campus_twin.rooms.values():
        r.status = "operational"
    for f in campus_twin.faculty.values():
        f.status = "available"

    # Also execute linked macro plan if present
    macro_plan_id = last_outage_report.get("macro_plan_id")
    if macro_plan_id:
        try:
            get_planner().execute_plan(macro_plan_id)
        except ValueError:
            pass

    last_outage_report["applied_option"] = option
    last_outage_report["impact_counts"]["hard_conflicts_after_recovery"] = option["hard_conflicts"]

    # If the applied plan solved all hard schedule conflicts cleanly, finish grid/SLA restoration
    if option.get("hard_conflicts", 0) == 0:
        ProblemResolver(state, campus_twin, last_outage_report).solve_all()
    else:
        get_detector().detect_all_conflicts()

    st_payload = _state_with_problems()
    tgt = str(last_outage_report.get("event", {}).get("target_id", "CAMPUS"))
    _log_dataset_event(
        event_type="recovery_applied",
        question=f"Can recovery option '{option.get('name', option_id)}' restore {tgt} service?",
        answer_summary=(
            f"Updated {applied['activities_updated']} activity slots; remaining hard conflicts="
            f"{option.get('hard_conflicts', 0)}; open problems={st_payload['open_problems_count']}; "
            f"health={st_payload['overall_health']:.1f}%."
        ),
        target_override=tgt,
    )

    return jsonify({
        "success": True,
        "applied": applied,
        "outage_report": last_outage_report,
        "state": st_payload,
        "campus_twin": campus_twin.to_dict(),
    })


@app.route("/api/simulate", methods=["POST"])
def simulate_disruption():
    """Trigger a cascading failure simulation"""
    data = request.json or {}
    disruption_type = data.get("disruption_type", "power_outage")
    severity = data.get("severity", "high")
    strategy = data.get("strategy", "balanced")
    if strategy not in STRATEGY_WEIGHTS:
        strategy = "balanced"

    try:
        sim = get_simulator()
        disruption, drops = sim.simulate(disruption_type, severity)
        summary = sim.get_simulation_summary(disruption, drops)

        detector = get_detector()
        conflicts = detector.detect_all_conflicts()

        planner = get_planner()
        plan = planner.generate_plan(disruption, strategy=strategy)
        st_payload = _state_with_problems()
        _log_dataset_event(
            event_type="macro_simulation",
            question=f"What cascaded across the campus dataset under {disruption_type} ({severity})?",
            answer_summary=(
                f"{summary['modules_affected']} domains hit, {disruption.students_affected} students affected, "
                f"{len(conflicts)} conflicts, health={st_payload['overall_health']:.1f}%."
            ),
            target_override=disruption_type.upper(),
        )

        return jsonify({
            "success": True,
            "disruption": disruption.to_dict(),
            "summary": summary,
            "cascade_drops": {k: round(v, 2) for k, v in drops.items()},
            "conflicts_detected": len(conflicts),
            "recovery_plan_id": plan.id,
            "recovery_plan": plan.to_dict(),
            "state": st_payload,
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/scenarios", methods=["GET"])
def get_scenarios():
    """List pre-built compound institutional crisis scenarios"""
    return jsonify({"scenarios": list(PRESET_SCENARIOS.values())})


@app.route("/api/scenarios/<scenario_id>/run", methods=["POST"])
def run_scenario(scenario_id):
    """Run a multi-disruption compound scenario preset"""
    preset = PRESET_SCENARIOS.get(scenario_id)
    if not preset:
        return jsonify({"success": False, "error": "Scenario not found"}), 404

    data = request.json or {}
    strategy = data.get("strategy") or preset.get("recommended_strategy", "balanced")
    if strategy not in STRATEGY_WEIGHTS:
        strategy = "balanced"

    sim = get_simulator()
    planner = get_planner()
    disruptions = []
    plans = []
    combined_drops = {}

    for ev in preset["events"]:
        disruption, drops = sim.simulate(ev["disruption_type"], ev["severity"])
        disruptions.append(disruption)
        for mod, val in drops.items():
            combined_drops[mod] = round(min(100.0, combined_drops.get(mod, 0.0) + val), 2)
        plan = planner.generate_plan(disruption, strategy=strategy)
        plans.append(plan)

    detector = get_detector()
    conflicts = detector.detect_all_conflicts()

    primary_disruption = disruptions[0]
    summary = sim.get_simulation_summary(primary_disruption, combined_drops)
    summary["scenario_name"] = preset["name"]
    summary["events_count"] = len(disruptions)
    summary["modules_affected"] = len(combined_drops)
    summary["students_affected"] = min(state.student_count, sum(d.students_affected for d in disruptions))
    summary["faculty_affected"] = min(state.faculty_count, sum(d.faculty_affected for d in disruptions))

    st_payload = _state_with_problems()
    _log_dataset_event(
        event_type="preset_scenario",
        question=f"What is the multi-disruption impact of scenario '{preset['name']}'?",
        answer_summary=(
            f"{summary['events_count']} crisis events hit {summary['modules_affected']} modules, "
            f"{summary['students_affected']} students, {len(conflicts)} conflicts; "
            f"health={st_payload['overall_health']:.1f}%."
        ),
        target_override=scenario_id.upper(),
    )

    return jsonify({
        "success": True,
        "scenario": preset,
        "disruption": primary_disruption.to_dict(),
        "summary": summary,
        "cascade_drops": combined_drops,
        "conflicts_detected": len(conflicts),
        "recovery_plan_id": plans[-1].id,
        "state": st_payload,
    })


@app.route("/api/conflicts", methods=["GET"])
def get_conflicts():
    """Get all active conflicts"""
    detector = get_detector()
    conflicts = detector.detect_all_conflicts()
    return jsonify({
        "count": len(conflicts),
        "conflicts": [c.to_dict() for c in conflicts],
    })


@app.route("/api/disruptions", methods=["GET"])
def get_disruptions():
    """Get all active disruptions"""
    return jsonify({
        "count": len(state.active_disruptions),
        "disruptions": [d.to_dict() for d in state.active_disruptions],
    })


@app.route("/api/disruptions/<disruption_id>/resolve", methods=["POST"])
def resolve_disruption(disruption_id):
    """Resolve a specific disruption"""
    sim = get_simulator()
    success = sim.resolve_disruption(disruption_id)
    if success:
        get_detector().detect_all_conflicts()
        return jsonify({"success": True, "state": _state_with_problems()})
    return jsonify({"success": False, "error": "Disruption not found"}), 404


@app.route("/api/recovery-plans", methods=["GET"])
def get_recovery_plans():
    """Get all recovery plans"""
    return jsonify({
        "count": len(state.recovery_plans),
        "plans": [p.to_dict() for p in state.recovery_plans],
    })


@app.route("/api/recovery-plans/<plan_id>/strategy", methods=["PUT"])
def update_plan_strategy(plan_id):
    """Re-optimize a recovery plan under a different competing-constraint strategy"""
    data = request.json or {}
    strategy = data.get("strategy", "balanced")
    if strategy not in STRATEGY_WEIGHTS:
        return jsonify({"success": False, "error": "Invalid strategy"}), 400
    try:
        plan = get_planner().replan_with_strategy(plan_id, strategy)
        return jsonify({"success": True, "plan": plan.to_dict(), "state": _state_with_problems()})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404


@app.route("/api/recovery-plans/<plan_id>/execute", methods=["POST"])
def execute_recovery_plan(plan_id):
    """Execute a recovery plan to mitigate disruptions and restore constraints"""
    try:
        if (
            last_outage_report
            and last_outage_report.get("macro_plan_id") == plan_id
            and not last_outage_report.get("applied_option")
        ):
            rec_id = last_outage_report.get("recommended_option_id")
            rec_opt = next(
                (o for o in last_outage_report.get("ranked_recovery_options", []) if o["id"] == rec_id),
                None,
            )
            if rec_opt and rec_opt.get("hard_conflicts", 0) == 0:
                get_schedule_solver().apply_option(rec_opt)
                last_outage_report["applied_option"] = rec_opt
                last_outage_report["impact_counts"]["hard_conflicts_after_recovery"] = 0

        result = get_planner().execute_plan(plan_id)
        if len(state.active_disruptions) == 0:
            ProblemResolver(state, campus_twin, last_outage_report).solve_all()
            result["health_after"] = state.overall_health
        get_detector().detect_all_conflicts()
        st_payload = _state_with_problems()
        _log_dataset_event(
            event_type="recovery_applied",
            question=f"What was the verified quantitative effect of executing recovery plan {plan_id}?",
            answer_summary=(
                f"Health moved from {result['health_before']}% to {result['health_after']}%; "
                f"open problems={st_payload['open_problems_count']}; active conflicts="
                f"{len(state.active_conflicts)}."
            ),
            target_override=str(plan_id),
        )
        return jsonify({
            "success": True,
            "execution": result,
            "state": st_payload,
            "campus_twin": campus_twin.to_dict(),
            "outage_report": last_outage_report,
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404


@app.route("/api/recovery-plans/<plan_id>/actions/<action_id>", methods=["PUT"])
def update_action(plan_id, action_id):
    """Update a recovery action status"""
    data = request.json or {}
    status = data.get("status", "completed")
    planner = get_planner()
    success = planner.update_action_status(plan_id, action_id, status)
    if success:
        return jsonify({"success": True, "state": _state_with_problems()})
    return jsonify({"success": False, "error": "Plan or action not found"}), 404


@app.route("/api/graph", methods=["GET"])
def get_graph():
    """Get dependency graph data for visualization"""
    graph_data = graph.to_graph_data()
    risk_rank = graph.get_module_risk_rank()
    downstream_map = {
        mod_id: graph.get_downstream_modules(mod_id)
        for mod_id in graph.dependencies
    }
    return jsonify({
        "graph": graph_data,
        "risk_ranking": [{"module": m, "score": s} for m, s in risk_rank],
        "downstream_map": downstream_map,
    })


@app.route("/api/disruption-types", methods=["GET"])
def get_disruption_types():
    """Get available disruption types"""
    return jsonify({
        "types": [
            {
                "id": k,
                "label": k.replace("_", " ").title(),
                "primary_module": v["primary"][0],
                "cascade_path": v["cascade_path"],
                "severity_multiplier": v["severity_multiplier"],
            }
            for k, v in DISRUPTION_IMPACT_MAP.items()
        ]
    })


@app.route("/api/problems", methods=["GET"])
def get_open_problems():
    """Return all currently unsolved problems with step-by-step fix instructions."""
    problems = ProblemResolver(state, campus_twin, last_outage_report).collect_problems()
    return jsonify({"count": len(problems), "problems": problems})


@app.route("/api/problems/solve", methods=["POST"])
def solve_single_problem():
    """Execute a specific remediation action for an unsolved campus problem."""
    data = request.json or {}
    resolver = ProblemResolver(state, campus_twin, last_outage_report)
    msg = resolver.solve(data)
    st_payload = _state_with_problems()
    problems = st_payload["open_problems"]
    tgt = str(data.get("target_id", "CAMPUS"))
    _log_dataset_event(
        event_type="problem_solved",
        question=f"What changed in the dataset after fixing '{data.get('solve_type', 'issue')}' on {tgt}?",
        answer_summary=f"{msg}. Remaining open problems={len(problems)}; health={st_payload['overall_health']:.1f}%.",
        target_override=tgt,
    )
    return jsonify({
        "success": True,
        "message": msg,
        "problems": problems,
        "open_problems_count": len(problems),
        "state": st_payload,
        "campus_twin": campus_twin.to_dict(),
        "outage_report": last_outage_report,
    })


@app.route("/api/problems/solve-all", methods=["POST"])
def solve_all_problems():
    """Automatically solve every remaining open problem across schedule, constraints, and modules."""
    resolver = ProblemResolver(state, campus_twin, last_outage_report)
    logs = resolver.solve_all()
    st_payload = _state_with_problems()
    problems = st_payload["open_problems"]
    _log_dataset_event(
        event_type="solve_all",
        question="Did Auto-Solve resolve all open problems and restore campus SLA compliance?",
        answer_summary=(
            f"Executed {len(logs)} automated fix(es); open problems={len(problems)}; "
            f"health={st_payload['overall_health']:.1f}%."
        ),
        target_override="CAMPUS",
    )
    return jsonify({
        "success": True,
        "actions_executed": len(logs),
        "logs": logs,
        "problems": problems,
        "open_problems_count": len(problems),
        "state": st_payload,
        "campus_twin": campus_twin.to_dict(),
        "outage_report": last_outage_report,
    })


@app.route("/api/reset", methods=["POST"])
def reset_state():
    """Reset institution and campus records to full operational baseline"""
    global state, campus_twin, last_outage_report
    state = build_institution()
    campus_twin = load_campus_data(sync_sqlite=True)
    last_outage_report = None
    st_payload = _state_with_problems()
    _log_dataset_event(
        event_type="reset",
        question="What is the verified campus baseline after resetting the digital twin dataset?",
        answer_summary=(
            f"Baseline verified: health={st_payload['overall_health']:.1f}%, "
            f"{len(campus_twin.activities)} scheduled activities across {len(campus_twin.rooms)} rooms, "
            f"0 open problems."
        ),
        target_override="CAMPUS",
    )
    return jsonify({
        "success": True,
        "state": st_payload,
        "campus_twin": campus_twin.to_dict(),
    })


@app.route("/api/reports/dataset-history", methods=["GET"])
def get_dataset_history():
    """Return persistent SQLite quantitative dataset & Q&A records plus aggregate KPIs."""
    limit = request.args.get("limit", default=100, type=int)
    event_type = request.args.get("event_type", default="all", type=str)
    search = request.args.get("search", default="", type=str)
    payload = list_history_records(limit=limit, event_type=event_type, search=search)
    payload["questions_catalog"] = PRESET_DATASET_QUESTIONS
    return jsonify(payload)


@app.route("/api/reports/dataset-history/ask", methods=["POST"])
def ask_dataset_history():
    """Answer an operational question quantitatively from the live dataset and persist it to history."""
    data = request.json or {}
    question = str(data.get("question", "")).strip()
    if not question:
        return jsonify({"success": False, "error": "Question text is required."}), 400
    rec = answer_dataset_question(
        question=question,
        state=state,
        campus_twin=campus_twin,
        last_outage_report=last_outage_report,
        graph=graph,
        persist=True,
    )
    history = list_history_records(limit=100)
    return jsonify({
        "success": True,
        "record": rec,
        "summary": history["summary"],
        "records": history["records"],
    })


@app.route("/api/reports/dataset-history/export", methods=["GET"])
def export_dataset_history():
    """Export the full historical quantitative dataset & Q&A log as CSV or JSON."""
    fmt = (request.args.get("format", "json") or "json").lower()
    if fmt == "csv":
        return Response(
            export_history_csv(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=omnis-x-dataset-history.csv"},
        )
    data = list_history_records(limit=500)
    return jsonify(data)


@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """Get analytics summary"""
    state.compute_overall_health()
    c_summary = get_constraint_engine().evaluate_all()
    module_health = {k: v.health_score for k, v in state.modules.items()}
    critical_modules = [
        k for k, v in state.modules.items() if v.status.value in ["critical", "failed"]
    ]
    degraded_modules = [
        k for k, v in state.modules.items() if v.status.value == "degraded"
    ]

    return jsonify({
        "overall_health": state.overall_health,
        "module_health": module_health,
        "critical_modules": critical_modules,
        "degraded_modules": degraded_modules,
        "active_disruptions": len(state.active_disruptions),
        "active_conflicts": len(state.active_conflicts),
        "recovery_plans": len(state.recovery_plans),
        "violated_constraints": c_summary["violated_count"],
        "hard_violations": c_summary["hard_violations"],
        "total_students_affected": sum(d.students_affected for d in state.active_disruptions),
        "total_faculty_affected": sum(d.faculty_affected for d in state.active_disruptions),
        "risk_ranking": graph.get_module_risk_rank(),
    })


if __name__ == "__main__":
    print("🏫 OMNIS-X Smart Campus Digital Twin & Crisis Recovery System Starting...")
    print("📡 Server: http://localhost:5000")
    app.run(debug=True, port=5000, use_reloader=False)
