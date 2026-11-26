"""
OMNIS-X Record-Level Simulation & Constraint Schedule Solver (Layers 2, 3, 4)
- BFS Dependency Traversal across Power Zones -> Buildings -> Rooms -> Activities -> People
- Hard vs Soft Constraint Validation (Rejects double-bookings, busy faculty, undersized rooms, missing equipment)
- Ranked Recovery Plans via Score = 10C + 5D + 3B + 2P
"""
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..core.campus_store import CampusActivity, CampusTwinData, Room


def to_minutes(hhmm: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    parts = hhmm.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def to_hhmm(minutes: int) -> str:
    """Convert minutes since midnight back to 'HH:MM'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def times_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    """Strict half-open overlap check between two [start, end) time windows."""
    sa, ea = to_minutes(start_a), to_minutes(end_a)
    sb, eb = to_minutes(start_b), to_minutes(end_b)
    return sa < eb and sb < ea


@dataclass
class ScheduleAssignment:
    activity_id: str
    title: str
    activity_type: str
    batch_id: str
    student_count: int
    orig_room_id: str
    orig_building_id: str
    orig_faculty_id: str
    orig_window: str
    new_room_id: str
    new_building_id: str
    new_faculty_id: str
    new_start: str
    new_end: str
    delay_hours: float
    building_changed: bool
    preference_violated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_id": self.activity_id,
            "title": self.title,
            "activity_type": self.activity_type,
            "batch_id": self.batch_id,
            "student_count": self.student_count,
            "orig_room_id": self.orig_room_id,
            "orig_building_id": self.orig_building_id,
            "orig_faculty_id": self.orig_faculty_id,
            "orig_window": self.orig_window,
            "new_room_id": self.new_room_id,
            "new_building_id": self.new_building_id,
            "new_faculty_id": self.new_faculty_id,
            "new_window": f"{self.new_start}-{self.new_end}",
            "new_start": self.new_start,
            "new_end": self.new_end,
            "delay_hours": round(self.delay_hours, 2),
            "building_changed": self.building_changed,
            "preference_violated": self.preference_violated,
        }


@dataclass
class RankedRecoveryOption:
    id: str
    name: str
    description: str
    feasible: bool
    score: float
    c_activities_changed: int
    d_total_delay_hours: float
    b_building_changes: int
    p_preference_violations: int
    hard_conflicts: int
    assignments: list[ScheduleAssignment] = field(default_factory=list)
    unresolved_activities: list[dict[str, Any]] = field(default_factory=list)
    rejected_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "feasible": self.feasible,
            "score": round(self.score, 2),
            "formula_breakdown": {
                "C": self.c_activities_changed,
                "D": round(self.d_total_delay_hours, 2),
                "B": self.b_building_changes,
                "P": self.p_preference_violations,
                "formula": (
                    f"10({self.c_activities_changed}) + 5({self.d_total_delay_hours:.1f}) "
                    f"+ 3({self.b_building_changes}) + 2({self.p_preference_violations}) "
                    f"= {self.score:.1f}"
                ),
            },
            "hard_conflicts": self.hard_conflicts,
            "assignments": [a.to_dict() for a in self.assignments],
            "unresolved_activities": self.unresolved_activities,
            "rejected_candidates": self.rejected_candidates,
        }


class CampusScheduleSolver:
    """Performs BFS outage impact analysis and ranked constraint-based recovery planning."""

    def __init__(self, twin: CampusTwinData):
        self.twin = twin

    def simulate_outage(
        self,
        target_id: str,
        start_time: str = "09:00",
        end_time: str = "12:00",
        outage_type: str = "power_outage",
    ) -> dict[str, Any]:
        """
        Execute the 6-step BFS failure simulation and generate ranked recovery plans.
        """
        valid_targets = (
            set(self.twin.power_zones)
            | set(self.twin.buildings)
            | set(self.twin.rooms)
            | set(self.twin.faculty)
        )
        if target_id not in valid_targets:
            raise ValueError(f"Unknown campus entity target: {target_id}")
        if to_minutes(start_time) >= to_minutes(end_time):
            raise ValueError("Start time must be earlier than end time.")

        # Step 1 & 2: Receive event and mark target unavailable
        unavailable_rooms, unavailable_faculty, bfs_steps, trace_chains = self._trace_bfs(
            target_id, start_time, end_time
        )

        # Step 4: Check scheduled activities overlapping [start_time, end_time]
        affected: list[CampusActivity] = []
        unaffected_outside_window: list[CampusActivity] = []
        for act in self.twin.activities:
            depends_on_failed = (
                act.room_id in unavailable_rooms or act.faculty_id in unavailable_faculty
            )
            if not depends_on_failed:
                continue
            if times_overlap(act.start_time, act.end_time, start_time, end_time):
                affected.append(act)
            else:
                unaffected_outside_window.append(act)

        # Step 5: Calculate exact impact from records
        classes_cnt = sum(1 for a in affected if a.activity_type == "class")
        labs_cnt = sum(1 for a in affected if a.activity_type == "lab")
        exams_cnt = sum(1 for a in affected if a.activity_type == "exam")
        events_cnt = sum(1 for a in affected if a.activity_type in ("event", "placement"))
        unique_batches = {a.batch_id for a in affected}
        unique_faculty = {a.faculty_id for a in affected}
        students_cnt = sum(
            self.twin.batches[b_id].student_count
            for b_id in unique_batches
            if b_id in self.twin.batches
        )

        # Step 6: Generate ranked recovery plans under hard & soft constraints
        ranked_options = self._generate_ranked_plans(
            affected=affected,
            unavailable_rooms=unavailable_rooms,
            unavailable_faculty=unavailable_faculty,
            outage_start=start_time,
            outage_end=end_time,
        )

        best_plan = ranked_options[0] if ranked_options else None

        affected_records = []
        for act in affected:
            room = self.twin.rooms.get(act.room_id)
            fac = self.twin.faculty.get(act.faculty_id)
            batch = self.twin.batches.get(act.batch_id)
            affected_records.append({
                "id": act.id,
                "title": act.title,
                "activity_type": act.activity_type,
                "domain": act.domain,
                "faculty_id": act.faculty_id,
                "faculty_name": fac.name if fac else act.faculty_id,
                "batch_id": act.batch_id,
                "student_count": batch.student_count if batch else 0,
                "room_id": act.room_id,
                "building_id": room.building_id if room else "",
                "time_window": f"{act.start_time}-{act.end_time}",
                "required_equipment": act.required_equipment,
                "priority": act.priority,
            })

        return {
            "event": {
                "id": str(uuid.uuid4())[:8].upper(),
                "target_id": target_id,
                "outage_type": outage_type,
                "start_time": start_time,
                "end_time": end_time,
                "time_window": f"{start_time} - {end_time}",
            },
            "bfs_steps": bfs_steps,
            "trace_chains": trace_chains,
            "unavailable_rooms": sorted(unavailable_rooms),
            "unavailable_faculty": sorted(unavailable_faculty),
            "impact_counts": {
                "classes": classes_cnt,
                "labs": labs_cnt,
                "exams": exams_cnt,
                "events": events_cnt,
                "total_activities": len(affected),
                "students": students_cnt,
                "faculty": len(unique_faculty),
                "hard_conflicts_before_recovery": len(affected),
                "hard_conflicts_after_recovery": best_plan.hard_conflicts if best_plan else len(affected),
                "unaffected_outside_window": len(unaffected_outside_window),
            },
            "affected_activities": affected_records,
            "unaffected_outside_window": [
                {
                    "id": a.id,
                    "title": a.title,
                    "room_id": a.room_id,
                    "time_window": f"{a.start_time}-{a.end_time}",
                }
                for a in unaffected_outside_window
            ],
            "ranked_recovery_options": [opt.to_dict() for opt in ranked_options],
            "recommended_option_id": best_plan.id if best_plan else None,
        }

    def _trace_bfs(
        self, target_id: str, start_time: str, end_time: str
    ) -> tuple[set[str], set[str], list[dict[str, Any]], list[list[str]]]:
        """Traverse Power Zone -> Building -> Room -> Overlapping Activity -> People using BFS."""
        unavailable_rooms: set[str] = set()
        unavailable_faculty: set[str] = set()
        visited: set[str] = {target_id}
        queue: deque[tuple[str, list[str]]] = deque([(target_id, [target_id])])

        bfs_steps: list[dict[str, Any]] = []
        trace_chains: list[list[str]] = []

        while queue:
            curr, path = queue.popleft()

            if curr in self.twin.power_zones:
                zone = self.twin.power_zones[curr]
                bfs_steps.append({
                    "step": len(bfs_steps) + 1,
                    "entity": curr,
                    "kind": "power_zone",
                    "detail": f"{zone.name} offline ({start_time}-{end_time})",
                })
                for b in self.twin.buildings.values():
                    if b.power_zone_id == curr and b.id not in visited:
                        visited.add(b.id)
                        queue.append((b.id, path + [b.id]))

            elif curr in self.twin.buildings:
                bldg = self.twin.buildings[curr]
                bfs_steps.append({
                    "step": len(bfs_steps) + 1,
                    "entity": curr,
                    "kind": "building",
                    "detail": f"{bldg.name} power/facility unavailable",
                })
                for r in self.twin.rooms.values():
                    if r.building_id == curr and r.id not in visited:
                        visited.add(r.id)
                        queue.append((r.id, path + [r.id]))

            elif curr in self.twin.rooms:
                room = self.twin.rooms[curr]
                unavailable_rooms.add(curr)
                bfs_steps.append({
                    "step": len(bfs_steps) + 1,
                    "entity": curr,
                    "kind": room.room_type,
                    "detail": f"{room.name} unavailable ({start_time}-{end_time})",
                })
                for act in self.twin.activities:
                    if (
                        act.room_id == curr
                        and times_overlap(act.start_time, act.end_time, start_time, end_time)
                        and act.id not in visited
                    ):
                        visited.add(act.id)
                        queue.append((act.id, path + [f"{act.id} ({act.title})"]))

            elif curr in self.twin.faculty:
                fac = self.twin.faculty[curr]
                unavailable_faculty.add(curr)
                bfs_steps.append({
                    "step": len(bfs_steps) + 1,
                    "entity": curr,
                    "kind": "faculty",
                    "detail": f"{fac.name} unavailable ({start_time}-{end_time})",
                })
                for act in self.twin.activities:
                    if (
                        act.faculty_id == curr
                        and times_overlap(act.start_time, act.end_time, start_time, end_time)
                        and act.id not in visited
                    ):
                        visited.add(act.id)
                        queue.append((act.id, path + [f"{act.id} ({act.title})"]))

            else:
                act_obj = next((a for a in self.twin.activities if a.id == curr), None)
                if act_obj:
                    batch = self.twin.batches.get(act_obj.batch_id)
                    fac = self.twin.faculty.get(act_obj.faculty_id)
                    people_label = (
                        f"{act_obj.batch_id} ({batch.student_count if batch else 0} students) "
                        f"& {act_obj.faculty_id} ({fac.name if fac else ''})"
                    )
                    trace_chains.append(path + [people_label])
                    bfs_steps.append({
                        "step": len(bfs_steps) + 1,
                        "entity": curr,
                        "kind": act_obj.activity_type,
                        "detail": (
                            f"{act_obj.title} ({act_obj.start_time}-{act_obj.end_time}) "
                            f"impacts {people_label}"
                        ),
                    })

        return unavailable_rooms, unavailable_faculty, bfs_steps, trace_chains

    def _generate_ranked_plans(
        self,
        affected: list[CampusActivity],
        unavailable_rooms: set[str],
        unavailable_faculty: set[str],
        outage_start: str,
        outage_end: str,
    ) -> list[RankedRecoveryOption]:
        """Generate multiple constraint-validated plans and rank by 10C + 5D + 3B + 2P."""
        affected_ids = {a.id for a in affected}
        baseline_other = [a for a in self.twin.activities if a.id not in affected_ids]

        strategies = [
            (
                "OPT-RELOCATE",
                "Immediate Relocation (Lowest Delay)",
                "Moves impacted activities into valid backup rooms in nearby buildings during original slots.",
                "relocate_first",
            ),
            (
                "OPT-EXAM-HYBRID",
                "Exam & Lab Continuity Hybrid",
                "Prioritizes exams and labs for immediate relocation, shifting lower-priority classes if needed.",
                "exam_priority",
            ),
            (
                "OPT-SAME-BLDG",
                "Time-Shift Same Building (Fewest Building Changes)",
                "Keeps classes in original rooms/buildings by shifting them to post-outage free slots.",
                "delay_same_building",
            ),
        ]

        options: list[RankedRecoveryOption] = []
        seen_signatures: set[tuple[tuple[str, str, str, str], ...]] = set()

        for opt_id, name, desc, mode in strategies:
            option = self._solve_greedy_mode(
                opt_id=opt_id,
                name=name,
                description=desc,
                mode=mode,
                affected=affected,
                baseline_other=baseline_other,
                unavailable_rooms=unavailable_rooms,
                unavailable_faculty=unavailable_faculty,
                outage_start=outage_start,
                outage_end=outage_end,
            )
            sig = tuple(
                (a.activity_id, a.new_room_id, a.new_start, a.new_faculty_id)
                for a in sorted(option.assignments, key=lambda x: x.activity_id)
            )
            if sig not in seen_signatures or not options:
                seen_signatures.add(sig)
                options.append(option)

        # Sort feasible (0 unresolved, 0 hard conflicts) first, then lowest Score = 10C + 5D + 3B + 2P
        options.sort(key=lambda o: (not o.feasible, o.hard_conflicts, o.score))
        return options

    def _solve_greedy_mode(
        self,
        opt_id: str,
        name: str,
        description: str,
        mode: str,
        affected: list[CampusActivity],
        baseline_other: list[CampusActivity],
        unavailable_rooms: set[str],
        unavailable_faculty: set[str],
        outage_start: str,
        outage_end: str,
    ) -> RankedRecoveryOption:
        occupied: list[dict[str, Any]] = [
            {
                "room_id": a.room_id,
                "faculty_id": a.faculty_id,
                "batch_id": a.batch_id,
                "start": a.start_time,
                "end": a.end_time,
            }
            for a in baseline_other
        ]

        # Order activities according to scheduling mode
        if mode == "exam_priority":
            ordered = sorted(affected, key=lambda a: (a.priority, to_minutes(a.start_time)))
        else:
            ordered = sorted(affected, key=lambda a: (to_minutes(a.start_time), a.priority))

        assignments: list[ScheduleAssignment] = []
        unresolved: list[dict[str, Any]] = []
        rejected_log: list[dict[str, Any]] = []
        seen_rejections: set[tuple[str, str, str]] = set()

        total_delay = 0.0
        building_changes = 0
        pref_violations = 0

        for act in ordered:
            orig_room = self.twin.rooms[act.room_id]
            orig_bldg = orig_room.building_id
            batch = self.twin.batches[act.batch_id]
            duration_min = to_minutes(act.end_time) - to_minutes(act.start_time)

            # Candidate time starts: original start + post-outage hourly slots up to 18:00
            orig_start_min = to_minutes(act.start_time)
            outage_end_min = to_minutes(outage_end)
            slot_starts: list[int] = [orig_start_min]
            for h in range(9, 18):
                cand_min = h * 60
                if cand_min != orig_start_min and cand_min + duration_min <= 18 * 60:
                    slot_starts.append(cand_min)
            if (
                outage_end_min != orig_start_min
                and outage_end_min + duration_min <= 18 * 60
                and outage_end_min not in slot_starts
            ):
                slot_starts.append(outage_end_min)

            # Candidate faculty (original first; if unavailable, search department/other faculty)
            if act.faculty_id not in unavailable_faculty:
                cand_faculty_ids = [act.faculty_id]
            else:
                orig_dept = self.twin.faculty[act.faculty_id].department
                cand_faculty_ids = sorted(
                    [f.id for f in self.twin.faculty.values() if f.id not in unavailable_faculty],
                    key=lambda fid: (0 if self.twin.faculty[fid].department == orig_dept else 1, fid),
                )

            # Candidate rooms ordered by mode preference
            cand_rooms: list[Room] = list(self.twin.rooms.values())
            if mode == "delay_same_building":
                cand_rooms.sort(
                    key=lambda r: (
                        0 if r.id == act.room_id else (1 if r.building_id == orig_bldg else 2),
                        self.twin.buildings[r.building_id].distance_group,
                        r.capacity,
                    )
                )
            else:
                cand_rooms.sort(
                    key=lambda r: (
                        0 if r.building_id == orig_bldg else 1,
                        self.twin.buildings[r.building_id].distance_group,
                        r.capacity,
                    )
                )

            valid_candidates: list[tuple[float, ScheduleAssignment]] = []

            for start_min in slot_starts:
                cand_start = to_hhmm(start_min)
                cand_end = to_hhmm(start_min + duration_min)

                for room in cand_rooms:
                    for fid in cand_faculty_ids:
                        reason = self._check_hard_constraints(
                            act=act,
                            room=room,
                            faculty_id=fid,
                            batch_size=batch.student_count,
                            cand_start=cand_start,
                            cand_end=cand_end,
                            occupied=occupied,
                            unavailable_rooms=unavailable_rooms,
                            unavailable_faculty=unavailable_faculty,
                            outage_start=outage_start,
                            outage_end=outage_end,
                        )
                        if reason:
                            # Record meaningful rejections (undersized rooms, busy faculty, double-booked)
                            if (
                                len(rejected_log) < 25
                                and reason.startswith(("H1:", "H2:", "H3:"))
                                and (act.id, room.id, reason) not in seen_rejections
                            ):
                                seen_rejections.add((act.id, room.id, reason))
                                rejected_log.append({
                                    "activity_id": act.id,
                                    "activity_title": act.title,
                                    "candidate_room": room.id,
                                    "candidate_window": f"{cand_start}-{cand_end}",
                                    "candidate_faculty": fid,
                                    "rejection_reason": reason,
                                })
                            continue

                        delay_hrs = abs(start_min - orig_start_min) / 60.0
                        b_chg = 1 if room.building_id != orig_bldg else 0
                        pref_viol = 1 if (start_min >= 16 * 60 or room.room_type != orig_room.room_type) else 0

                        # Strategy-specific local cost for greedy selection
                        if mode == "delay_same_building":
                            step_cost = 30.0 * b_chg + 5.0 * delay_hrs + 2.0 * pref_viol
                        else:
                            step_cost = 5.0 * delay_hrs + 3.0 * b_chg + 2.0 * pref_viol

                        assignment = ScheduleAssignment(
                            activity_id=act.id,
                            title=act.title,
                            activity_type=act.activity_type,
                            batch_id=act.batch_id,
                            student_count=batch.student_count,
                            orig_room_id=act.room_id,
                            orig_building_id=orig_bldg,
                            orig_faculty_id=act.faculty_id,
                            orig_window=f"{act.start_time}-{act.end_time}",
                            new_room_id=room.id,
                            new_building_id=room.building_id,
                            new_faculty_id=fid,
                            new_start=cand_start,
                            new_end=cand_end,
                            delay_hours=delay_hrs,
                            building_changed=bool(b_chg),
                            preference_violated=bool(pref_viol),
                        )
                        valid_candidates.append((step_cost, assignment))

            if valid_candidates:
                valid_candidates.sort(key=lambda item: item[0])
                chosen = valid_candidates[0][1]
                assignments.append(chosen)
                occupied.append({
                    "room_id": chosen.new_room_id,
                    "faculty_id": chosen.new_faculty_id,
                    "batch_id": chosen.batch_id,
                    "start": chosen.new_start,
                    "end": chosen.new_end,
                })
                total_delay += chosen.delay_hours
                if chosen.building_changed:
                    building_changes += 1
                if chosen.preference_violated:
                    pref_violations += 1
            else:
                unresolved.append({
                    "activity_id": act.id,
                    "title": act.title,
                    "activity_type": act.activity_type,
                    "batch_id": act.batch_id,
                    "student_count": batch.student_count,
                    "orig_room_id": act.room_id,
                    "orig_window": f"{act.start_time}-{act.end_time}",
                    "required_equipment": act.required_equipment,
                    "reason": "No alternative room, faculty, or time slot satisfies all hard constraints.",
                })

        c_count = len(assignments)
        score = 10.0 * c_count + 5.0 * total_delay + 3.0 * building_changes + 2.0 * pref_violations
        hard_conflicts = len(unresolved)

        return RankedRecoveryOption(
            id=opt_id,
            name=name,
            description=description,
            feasible=(hard_conflicts == 0),
            score=score,
            c_activities_changed=c_count,
            d_total_delay_hours=total_delay,
            b_building_changes=building_changes,
            p_preference_violations=pref_violations,
            hard_conflicts=hard_conflicts,
            assignments=assignments,
            unresolved_activities=unresolved,
            rejected_candidates=rejected_log,
        )

    def _check_hard_constraints(
        self,
        act: CampusActivity,
        room: Room,
        faculty_id: str,
        batch_size: int,
        cand_start: str,
        cand_end: str,
        occupied: list[dict[str, Any]],
        unavailable_rooms: set[str],
        unavailable_faculty: set[str],
        outage_start: str,
        outage_end: str,
    ) -> str | None:
        """Validate the 4 Hard Constraints. Returns rejection reason or None if valid."""
        # H4a: Resource / Room unavailable during outage window
        if room.id in unavailable_rooms and times_overlap(cand_start, cand_end, outage_start, outage_end):
            return f"H4: Room {room.id} unavailable during outage window {outage_start}-{outage_end}"

        # H4b: Faculty unavailable during outage window
        if faculty_id in unavailable_faculty and times_overlap(cand_start, cand_end, outage_start, outage_end):
            return f"H4: Faculty {faculty_id} unavailable during {outage_start}-{outage_end}"

        # H3: Room capacity must fit the group
        if room.capacity < batch_size:
            return f"H3: Undersized room {room.id} (capacity {room.capacity} < batch size {batch_size})"

        # H4c: Required equipment must be available in room
        if not set(act.required_equipment).issubset(set(room.equipment)):
            missing = sorted(set(act.required_equipment) - set(room.equipment))
            return f"H4: Room {room.id} lacks required equipment {missing}"

        # H1 & H2: No room double-booking, no faculty overlap, no batch overlap
        for slot in occupied:
            if not times_overlap(cand_start, cand_end, slot["start"], slot["end"]):
                continue
            if slot["room_id"] == room.id:
                return f"H1: Room {room.id} double-booked in {cand_start}-{cand_end}"
            if slot["faculty_id"] == faculty_id:
                return f"H2: Faculty {faculty_id} already assigned in {cand_start}-{cand_end}"
            if slot["batch_id"] == act.batch_id:
                return f"H2: Batch {act.batch_id} has overlapping activity in {cand_start}-{cand_end}"

        return None

    def apply_option(self, option_data: dict[str, Any]) -> dict[str, Any]:
        """Apply a ranked recovery option to the active campus schedule records."""
        updated = 0
        for item in option_data.get("assignments", []):
            act = next((a for a in self.twin.activities if a.id == item["activity_id"]), None)
            if act:
                act.room_id = item["new_room_id"]
                act.faculty_id = item["new_faculty_id"]
                act.start_time = item["new_start"]
                act.end_time = item["new_end"]
                act.status = "recovered"
                updated += 1
        return {
            "option_id": option_data.get("id"),
            "activities_updated": updated,
            "hard_conflicts_after_recovery": option_data.get("hard_conflicts", 0),
        }
