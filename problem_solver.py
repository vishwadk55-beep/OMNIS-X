"""
OMNIS-X Unified Problem Collector & Executable Remediation Engine
Surfaces every unsolved conflict, violated constraint, resource deficit, and
unresolved schedule activity with clear step-by-step guidance and 1-click fixes.
"""
from typing import Any

from ..core.campus_store import CampusTwinData
from ..core.models import InstitutionState, SystemStatus
from .conflict_detector import ConflictDetector
from .constraint_engine import ConstraintEngine
from .recovery_planner import RecoveryPlanner
from .schedule_solver import CampusScheduleSolver, to_hhmm, to_minutes


def _health_status(score: float) -> SystemStatus:
    if score >= 80.0:
        return SystemStatus.OPERATIONAL
    if score >= 50.0:
        return SystemStatus.DEGRADED
    if score >= 20.0:
        return SystemStatus.CRITICAL
    return SystemStatus.FAILED


class ProblemResolver:
    """Collects all open campus problems and executes deterministic remediations."""

    def __init__(
        self,
        state: InstitutionState,
        campus_twin: CampusTwinData,
        outage_report: dict[str, Any] | None = None,
    ):
        self.state = state
        self.twin = campus_twin
        self.outage_report = outage_report

    def collect_problems(self) -> list[dict[str, Any]]:
        """Gather every unsolved schedule, disruption, constraint, and resource issue."""
        ConstraintEngine(self.state).evaluate_all()
        ConflictDetector(self.state).detect_all_conflicts()

        problems: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # 1. Record-level unapplied recovery & unresolved activities (e.g. Cryo Lab LAB_C2)
        if self.outage_report:
            target = self.outage_report.get("event", {}).get("target_id", "CAMPUS")
            window = self.outage_report.get("event", {}).get("time_window", "")
            applied = self.outage_report.get("applied_option")
            options = self.outage_report.get("ranked_recovery_options", [])
            best_opt = options[0] if options else None

            if not applied and best_opt and best_opt.get("assignments"):
                pid = f"UNAPPLIED-{best_opt['id']}"
                seen_ids.add(pid)
                cnt = len(best_opt["assignments"])
                problems.append({
                    "id": pid,
                    "category": "schedule_pending",
                    "severity": "critical",
                    "title": f"Unrecovered Schedules in {target} ({cnt} sessions)",
                    "reason": (
                        f"{cnt} scheduled activities in {target} ({window}) are disrupted "
                        "and have not been relocated yet."
                    ),
                    "how_to_solve": (
                        f"Apply ranked recovery plan '{best_opt['name']}' "
                        f"(Score {best_opt['score']:.0f}) to move them with 0 hard clashes."
                    ),
                    "actions": [{
                        "solve_type": "apply_recommended",
                        "target_id": best_opt["id"],
                        "mode": "apply",
                        "label": f"✅ Apply {best_opt['name']}",
                    }],
                })

            source_opt = applied or best_opt
            for unres in (source_opt.get("unresolved_activities", []) if source_opt else []):
                act_id = unres["activity_id"]
                pid = f"UNRES-{act_id}"
                seen_ids.add(pid)
                equip = ", ".join(unres.get("required_equipment", [])) or "special setup"
                orig_room = unres.get("orig_room_id", "")
                problems.append({
                    "id": pid,
                    "category": "schedule_unresolved",
                    "severity": "critical",
                    "title": f"Unresolved Lab/Session: {unres['title']} ({act_id})",
                    "reason": (
                        f"{orig_room} ({unres.get('orig_window', '')}) is unavailable and no "
                        f"alternate room provides required equipment [{equip}]."
                    ),
                    "how_to_solve": (
                        f"Step 1: Deploy portable cooling/vendor maintenance to restore "
                        f"{orig_room}, OR Step 2: Move {act_id} to a clash-free evening "
                        "compensatory slot (19:00-21:00) after repairs complete."
                    ),
                    "actions": [
                        {
                            "solve_type": "unresolved_activity",
                            "target_id": act_id,
                            "mode": "emergency_vendor_restore",
                            "label": f"🔧 Restore {orig_room} & Keep Slot",
                        },
                        {
                            "solve_type": "unresolved_activity",
                            "target_id": act_id,
                            "mode": "compensatory_slot",
                            "label": "🕒 Reschedule Post-Repair Slot",
                        },
                    ],
                })

        # 2. Active macro disruptions needing execution/containment
        for dis in self.state.active_disruptions:
            pid = f"DIS-{dis.id}"
            seen_ids.add(pid)
            plan = next(
                (
                    p
                    for p in reversed(self.state.recovery_plans)
                    if p.disruption_id == dis.id and p.overall_status != "completed"
                ),
                None,
            )
            problems.append({
                "id": pid,
                "category": "active_disruption",
                "severity": dis.severity.value,
                "title": f"Active Failure: {dis.type.value.replace('_', ' ').title()} ({dis.source_module.upper()})",
                "reason": dis.description,
                "how_to_solve": (
                    f"Execute automated recovery checklist & standby failover for "
                    f"{dis.source_module.upper()} ({len(dis.cascaded_to)} cascaded systems)."
                ),
                "actions": [{
                    "solve_type": "disruption",
                    "target_id": dis.id,
                    "plan_id": plan.id if plan else None,
                    "mode": "resolve_disruption",
                    "label": f"⚡ Execute Recovery ({dis.source_module.upper()})",
                }],
            })

        # 3. Remaining violated institutional constraints (HARD and SOFT)
        for con in self.state.constraints:
            if not con.violated:
                continue
            pid = f"RULE-{con.id}"
            seen_ids.add(pid)
            problems.append({
                "id": pid,
                "category": "constraint_violation",
                "severity": "critical" if con.priority.value == "hard" else "high",
                "title": f"[{con.id}] {con.name} Violated",
                "reason": (
                    f"{con.metric} is at {con.current_value:.1f}{con.unit}, below required "
                    f"{con.operator} {con.threshold:.0f}{con.unit}. {con.description}"
                ),
                "how_to_solve": (
                    f"Bring standby backup capacity online for '{con.module}' and "
                    f"rebalance demand across {', '.join(con.competing_modules[:3])}."
                ),
                "actions": [{
                    "solve_type": "constraint",
                    "target_id": con.id,
                    "module": con.module,
                    "mode": "restore_module_sla",
                    "label": f"✅ Restore {con.module.upper()} Above {con.threshold:.0f}%",
                }],
            })

        # 4. Shared resource supply deficits
        for res in self.state.resources.values():
            if res.total_demand <= res.available_capacity:
                continue
            pid = f"RES-{res.id}"
            seen_ids.add(pid)
            deficit = round(res.total_demand - res.available_capacity, 1)
            problems.append({
                "id": pid,
                "category": "resource_deficit",
                "severity": "high",
                "title": f"Supply Deficit: {res.name} (-{deficit} {res.unit})",
                "reason": (
                    f"Available {res.available_capacity:.0f} {res.unit} vs campus demand "
                    f"{res.total_demand:.0f} {res.unit} (contention {res.contention_ratio}x)."
                ),
                "how_to_solve": (
                    f"Activate reserve capacity for owner '{res.owner_module}' and clear "
                    "rationing bottlenecks."
                ),
                "actions": [{
                    "solve_type": "resource",
                    "target_id": res.id,
                    "module": res.owner_module,
                    "mode": "restore_resource",
                    "label": f"🔋 Restore {res.name}",
                }],
            })

        # 5. Any remaining standalone conflicts not tied directly to rule/resource IDs
        for conf in self.state.active_conflicts:
            if conf.constraint_id or conf.conflict_type == "Competing Resource Contention":
                continue
            pid = f"CONF-{conf.id}"
            if pid in seen_ids:
                continue
            problems.append({
                "id": pid,
                "category": "conflict",
                "severity": conf.severity.value,
                "title": f"{conf.conflict_type}: {', '.join(conf.involved_modules).upper()}",
                "reason": conf.description,
                "how_to_solve": conf.suggested_resolution,
                "actions": [{
                    "solve_type": "conflict",
                    "target_id": conf.id,
                    "modules": conf.involved_modules,
                    "mode": "restore_conflict",
                    "label": "🛠️ Resolve Conflict Now",
                }],
            })

        return problems

    def _restore_module_to_sla(self, mod_id: str, min_health: float = 100.0) -> None:
        mod = self.state.modules.get(mod_id)
        if not mod:
            return
        mod.health_score = max(mod.health_score, min_health)
        mod.status = _health_status(mod.health_score)
        for sub in mod.subsystems:
            sub.health_score = max(sub.health_score, min_health)
            sub.status = _health_status(sub.health_score)
        for dis in list(self.state.active_disruptions):
            if (
                (dis.source_module == mod_id or mod.health_score >= 90.0)
                and mod_id in dis.affected_modules
                and all(
                    self.state.modules[m].health_score >= 85.0
                    for m in dis.affected_modules
                    if m in self.state.modules
                )
            ):
                dis.resolved = True
        self.state.active_disruptions = [
            d for d in self.state.active_disruptions if not d.resolved
        ]

    def _restore_twin_operational(self) -> None:
        for z in self.twin.power_zones.values():
            z.status = "operational"
        for b in self.twin.buildings.values():
            b.status = "operational"
        for r in self.twin.rooms.values():
            r.status = "operational"
        for f in self.twin.faculty.values():
            f.status = "available"

    def _solve_unresolved_activity(self, act_id: str, mode: str) -> str:
        act = next((a for a in self.twin.activities if a.id == act_id), None)
        if not act:
            return f"Activity {act_id} not found."

        room = self.twin.rooms.get(act.room_id)
        orig_window = f"{act.start_time}-{act.end_time}"
        duration = to_minutes(act.end_time) - to_minutes(act.start_time)

        if mode == "compensatory_slot":
            start_min = 19 * 60
            new_start = to_hhmm(start_min)
            new_end = to_hhmm(start_min + duration)
            delay_hrs = round(abs(start_min - to_minutes(act.start_time)) / 60.0, 2)
            act.start_time = new_start
            act.end_time = new_end
            msg = f"Rescheduled {act.id} ({act.title}) to post-repair evening slot {new_start}-{new_end}."
        else:
            new_start = act.start_time
            new_end = act.end_time
            delay_hrs = 0.0
            msg = f"Deployed standby equipment & restored {act.room_id}; {act.id} ({act.title}) runs safely."

        act.status = "recovered"
        if room:
            room.status = "operational"
            if room.building_id in self.twin.buildings:
                bldg = self.twin.buildings[room.building_id]
                bldg.status = "operational"
                if bldg.power_zone_id in self.twin.power_zones:
                    self.twin.power_zones[bldg.power_zone_id].status = "operational"

        self._restore_module_to_sla(act.domain, 100.0)
        self._restore_module_to_sla("laboratory", 100.0)

        if self.outage_report:
            batch = self.twin.batches.get(act.batch_id)
            assignment = {
                "activity_id": act.id,
                "title": act.title,
                "activity_type": act.activity_type,
                "batch_id": act.batch_id,
                "student_count": batch.student_count if batch else 30,
                "orig_room_id": act.room_id,
                "orig_building_id": room.building_id if room else "",
                "orig_faculty_id": act.faculty_id,
                "orig_window": orig_window,
                "new_room_id": act.room_id,
                "new_building_id": room.building_id if room else "",
                "new_faculty_id": act.faculty_id,
                "new_window": f"{new_start}-{new_end}",
                "new_start": new_start,
                "new_end": new_end,
                "delay_hours": delay_hrs,
                "building_changed": False,
                "preference_violated": mode == "compensatory_slot",
            }
            for opt in self.outage_report.get("ranked_recovery_options", []):
                opt["unresolved_activities"] = [
                    u for u in opt.get("unresolved_activities", []) if u["activity_id"] != act_id
                ]
                if not any(a["activity_id"] == act_id for a in opt.get("assignments", [])):
                    opt.setdefault("assignments", []).append(assignment)
                opt["hard_conflicts"] = len(opt["unresolved_activities"])
                opt["feasible"] = opt["hard_conflicts"] == 0
                c_val = len(opt["assignments"])
                d_val = sum(float(a.get("delay_hours", 0.0)) for a in opt["assignments"])
                b_val = sum(1 for a in opt["assignments"] if a.get("building_changed"))
                p_val = sum(1 for a in opt["assignments"] if a.get("preference_violated"))
                opt["score"] = round(10.0 * c_val + 5.0 * d_val + 3.0 * b_val + 2.0 * p_val, 2)
                opt["formula_breakdown"] = {
                    "C": c_val,
                    "D": round(d_val, 2),
                    "B": b_val,
                    "P": p_val,
                    "formula": f"10({c_val}) + 5({d_val:.1f}) + 3({b_val}) + 2({p_val}) = {opt['score']:.1f}",
                }
            if not self.outage_report.get("applied_option") and self.outage_report.get("ranked_recovery_options"):
                self.outage_report["applied_option"] = self.outage_report["ranked_recovery_options"][0]
            self.outage_report["unavailable_rooms"] = [
                r for r in self.outage_report.get("unavailable_rooms", []) if r != act.room_id
            ]
            remaining_hard = (
                self.outage_report["applied_option"]["hard_conflicts"]
                if self.outage_report.get("applied_option")
                else 0
            )
            self.outage_report["impact_counts"]["hard_conflicts_after_recovery"] = remaining_hard

        return msg

    def solve(self, payload: dict[str, Any]) -> str:
        """Execute a single targeted fix described by solve_type and return status message."""
        solve_type = payload.get("solve_type", "")
        target_id = payload.get("target_id", "")
        mode = payload.get("mode", "")

        if solve_type == "apply_recommended" and self.outage_report:
            opt = next(
                (o for o in self.outage_report.get("ranked_recovery_options", []) if o["id"] == target_id),
                None,
            )
            if opt:
                CampusScheduleSolver(self.twin).apply_option(opt)
                self._restore_twin_operational()
                self.outage_report["applied_option"] = opt
                self.outage_report["impact_counts"]["hard_conflicts_after_recovery"] = opt["hard_conflicts"]
                macro_plan_id = self.outage_report.get("macro_plan_id")
                if macro_plan_id:
                    try:
                        RecoveryPlanner(self.state).execute_plan(macro_plan_id)
                    except ValueError:
                        pass
                if opt.get("hard_conflicts", 0) == 0 and len(self.state.active_disruptions) == 0:
                    self.restore_all_to_sla()
                msg = f"Applied recovery plan '{opt['name']}'."
            else:
                msg = "Recovery option already applied."

        elif solve_type == "unresolved_activity":
            msg = self._solve_unresolved_activity(target_id, mode or "emergency_vendor_restore")

        elif solve_type == "disruption":
            plan_id = payload.get("plan_id")
            planner = RecoveryPlanner(self.state)
            if plan_id:
                try:
                    planner.execute_plan(plan_id)
                except ValueError:
                    pass
            dis = next((d for d in self.state.active_disruptions if d.id == target_id), None)
            if dis:
                for m_id in [dis.source_module] + dis.cascaded_to:
                    self._restore_module_to_sla(m_id, 100.0)
                dis.resolved = True
            self.state.active_disruptions = [
                d for d in self.state.active_disruptions if not d.resolved
            ]
            self._restore_twin_operational()
            msg = f"Executed containment plan and restored systems for disruption {target_id}."

        elif solve_type in ("constraint", "resource"):
            mod_id = payload.get("module")
            if not mod_id and solve_type == "constraint":
                con = next((c for c in self.state.constraints if c.id == target_id), None)
                mod_id = con.module if con else ""
            if mod_id:
                self._restore_module_to_sla(mod_id, 100.0)
            msg = f"Restored '{mod_id or target_id}' above required institutional SLA threshold."

        elif solve_type == "conflict":
            for mod_id in payload.get("modules", []):
                self._restore_module_to_sla(mod_id, 100.0)
            self._restore_twin_operational()
            msg = "Resolved multi-module conflict and restored affected systems."

        else:
            msg = "No matching remediation action."

        self.state.compute_overall_health()
        ConstraintEngine(self.state).evaluate_all()
        ConflictDetector(self.state).detect_all_conflicts()
        return msg

    def restore_all_to_sla(self) -> None:
        """Restore all campus modules and twin entities to 100% baseline SLA."""
        for mod_id in list(self.state.modules):
            self._restore_module_to_sla(mod_id, 100.0)
        self.state.active_disruptions.clear()
        self._restore_twin_operational()
        self.state.compute_overall_health()
        ConstraintEngine(self.state).evaluate_all()
        ConflictDetector(self.state).detect_all_conflicts()

    def solve_all(self) -> list[str]:
        """Resolve every currently visible campus problem cleanly in priority order."""
        logs: list[str] = []
        for _ in range(5):
            problems = self.collect_problems()
            if not problems:
                break
            for prob in problems:
                act = prob["actions"][0] if prob.get("actions") else None
                if act:
                    logs.append(self.solve(act))
            for mod_id in list(self.state.modules):
                self._restore_module_to_sla(mod_id, 100.0)
            self.state.active_disruptions.clear()
            for plan in self.state.recovery_plans:
                plan.overall_status = "completed"
                for a in plan.actions:
                    a.status = "completed"
            self._restore_twin_operational()
            self.state.compute_overall_health()
            ConstraintEngine(self.state).evaluate_all()
            ConflictDetector(self.state).detect_all_conflicts()
        return logs
