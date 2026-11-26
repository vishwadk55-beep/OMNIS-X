"""
OMNIS-X Conflict Detection Engine
Identifies scheduling, resource, constraint, dependency, and policy conflicts
"""
import uuid

from ..core.models import (
    Conflict,
    ConstraintPriority,
    InstitutionState,
    SeverityLevel,
)
from .constraint_engine import ConstraintEngine


class ConflictDetector:
    """
    Detects conflicts and constraint violations across institutional modules
    """

    def __init__(self, state: InstitutionState):
        self.state = state

    def detect_all_conflicts(self) -> list[Conflict]:
        """Run all conflict detectors and return consolidated list"""
        ConstraintEngine(self.state).evaluate_all()

        conflicts: list[Conflict] = []
        conflicts.extend(self._detect_resource_conflicts())
        conflicts.extend(self._detect_scheduling_conflicts())
        conflicts.extend(self._detect_capacity_conflicts())
        conflicts.extend(self._detect_dependency_conflicts())
        conflicts.extend(self._detect_compliance_conflicts())
        conflicts.extend(self._detect_operational_conflicts())
        conflicts.extend(self._detect_constraint_and_contention_conflicts())

        self.state.active_conflicts = conflicts
        return conflicts

    def _detect_resource_conflicts(self) -> list[Conflict]:
        conflicts = []
        mods = self.state.modules

        if (
            mods.get("power")
            and mods["power"].health_score < 60
            and mods.get("laboratory")
            and mods.get("examination")
        ):
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Resource Conflict",
                    involved_modules=["power", "laboratory", "examination"],
                    description=(
                        "Insufficient power supply while laboratory equipment and "
                        "examination halls both require stable electricity."
                    ),
                    severity=SeverityLevel.CRITICAL,
                    suggested_resolution=(
                        "Prioritize power to exam halls, defer lab sessions, "
                        "and activate generator bank B for critical labs."
                    ),
                )
            )

        if (
            mods.get("network")
            and mods["network"].health_score < 70
            and mods.get("examination")
            and mods.get("placement")
        ):
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Bandwidth Conflict",
                    involved_modules=["network", "examination", "placement"],
                    description=(
                        "Degraded network unable to simultaneously support online "
                        "examinations and placement portal access."
                    ),
                    severity=SeverityLevel.HIGH,
                    suggested_resolution=(
                        "Allocate dedicated bandwidth for exam portal; pause placement "
                        "portal until exams complete."
                    ),
                )
            )

        return conflicts

    def _detect_scheduling_conflicts(self) -> list[Conflict]:
        conflicts = []
        mods = self.state.modules

        if (
            mods.get("examination")
            and mods["examination"].health_score > 50
            and mods.get("events")
            and mods["events"].health_score > 50
        ):
            classroom_mod = mods.get("classroom")
            if classroom_mod and classroom_mod.health_score < 80:
                conflicts.append(
                    Conflict(
                        id=str(uuid.uuid4())[:8].upper(),
                        conflict_type="Scheduling Conflict",
                        involved_modules=["examination", "events", "classroom"],
                        description=(
                            "Examination hall booking overlaps with scheduled technical fest; "
                            "insufficient classrooms for both activities simultaneously."
                        ),
                        severity=SeverityLevel.HIGH,
                        suggested_resolution=(
                            "Postpone event to next week, notify coordinators, "
                            "and issue student advisory."
                        ),
                    )
                )

        if mods.get("faculty") and mods["faculty"].health_score < 75 and mods.get("examination"):
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Invigilation Conflict",
                    involved_modules=["faculty", "examination"],
                    description=(
                        "Faculty shortage detected during examination period; "
                        "1:30 invigilation ratio cannot be maintained."
                    ),
                    severity=SeverityLevel.CRITICAL,
                    suggested_resolution=(
                        "Recall on-leave faculty for exam duty, assign admin assistants, "
                        "or stagger exam schedules."
                    ),
                )
            )

        return conflicts

    def _detect_capacity_conflicts(self) -> list[Conflict]:
        conflicts = []
        mods = self.state.modules

        if (
            mods.get("hostel")
            and mods["hostel"].health_score < 70
            and mods.get("transportation")
            and mods["transportation"].health_score < 60
        ):
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Capacity Conflict",
                    involved_modules=["hostel", "transportation"],
                    description=(
                        "Hostel facilities degraded while transport is also failing; "
                        "commuters and residents face simultaneous disruption."
                    ),
                    severity=SeverityLevel.HIGH,
                    suggested_resolution=(
                        "Open college auditorium for emergency shelter and "
                        "charter private shuttle buses."
                    ),
                )
            )

        if (
            mods.get("placement")
            and mods["placement"].health_score > 60
            and mods.get("classroom")
            and mods["classroom"].health_score < 70
        ):
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Venue Capacity Conflict",
                    involved_modules=["placement", "classroom"],
                    description=(
                        "Campus recruitment drive requires interview rooms while "
                        "classroom availability is severely reduced."
                    ),
                    severity=SeverityLevel.MEDIUM,
                    suggested_resolution=(
                        "Use conference rooms and faculty cabins for interviews "
                        "until classrooms recover."
                    ),
                )
            )

        return conflicts

    def _detect_dependency_conflicts(self) -> list[Conflict]:
        conflicts = []
        mods = self.state.modules

        if (
            mods.get("network")
            and mods["network"].health_score < 50
            and mods.get("academic")
            and mods["academic"].health_score > 70
        ):
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Dependency Conflict",
                    involved_modules=["network", "academic"],
                    description=(
                        "Academic ERP and LMS depend on degraded network infrastructure; "
                        "risk of data inconsistency."
                    ),
                    severity=SeverityLevel.HIGH,
                    suggested_resolution=(
                        "Switch academic systems to offline mode and use paper-based "
                        "attendance until network recovers."
                    ),
                )
            )

        if (
            mods.get("power")
            and mods["power"].health_score < 50
            and mods.get("examination")
            and mods["examination"].health_score > 60
        ):
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Critical Dependency Failure",
                    involved_modules=["power", "examination"],
                    description=(
                        "Examinations are scheduled while primary power has failed; "
                        "CBT terminals and hall lighting compromised."
                    ),
                    severity=SeverityLevel.CRITICAL,
                    suggested_resolution=(
                        "Pause online exams immediately, convert to paper format on "
                        "generator backup, and notify exam controller."
                    ),
                )
            )

        return conflicts

    def _detect_compliance_conflicts(self) -> list[Conflict]:
        conflicts = []
        mods = self.state.modules

        if mods.get("administration") and mods["administration"].health_score < 60:
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Compliance Risk",
                    involved_modules=["administration", "academic"],
                    description=(
                        "Administrative failure jeopardizes NAAC/NBA regulatory "
                        "submissions and fee processing deadlines."
                    ),
                    severity=SeverityLevel.HIGH,
                    suggested_resolution=(
                        "Activate manual compliance workflow and request deadline "
                        "extension from regulatory bodies."
                    ),
                )
            )

        if mods.get("faculty") and mods["faculty"].health_score < 65:
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Regulatory Conflict",
                    involved_modules=["faculty", "academic", "administration"],
                    description=(
                        "Faculty shortage may drop instructional hours below AICTE "
                        "minimum thresholds."
                    ),
                    severity=SeverityLevel.HIGH,
                    suggested_resolution=(
                        "Engage visiting industry faculty and reallocate courses "
                        "across available departments."
                    ),
                )
            )

        return conflicts

    def _detect_operational_conflicts(self) -> list[Conflict]:
        conflicts = []
        mods = self.state.modules

        if mods.get("laboratory") and mods["laboratory"].health_score < 60:
            lab_subsystems = {s.id: s for s in mods["laboratory"].subsystems}
            safety_sys = lab_subsystems.get("lab-safety")
            if safety_sys and safety_sys.health_score < 60:
                conflicts.append(
                    Conflict(
                        id=str(uuid.uuid4())[:8].upper(),
                        conflict_type="Safety Conflict",
                        involved_modules=["laboratory"],
                        description=(
                            "Laboratory safety systems (fire suppression, fume alarms) "
                            "are degraded while labs may be active; HSE violation risk."
                        ),
                        severity=SeverityLevel.CRITICAL,
                        suggested_resolution=(
                            "Evacuate and close affected labs immediately until safety "
                            "interlocks are restored."
                        ),
                    )
                )

        if mods.get("hostel") and mods["hostel"].health_score < 55:
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type="Operational Conflict",
                    involved_modules=["hostel"],
                    description=(
                        "Hostel water disruption compromises cafeteria hygiene and "
                        "mess food-safety standards."
                    ),
                    severity=SeverityLevel.HIGH,
                    suggested_resolution=(
                        "Procure municipal water tankers, use external packaged catering, "
                        "and issue hygiene advisory."
                    ),
                )
            )

        return conflicts

    def _detect_constraint_and_contention_conflicts(self) -> list[Conflict]:
        """Surface live hard/soft institutional constraint violations & shared resource shortages."""
        conflicts = []

        for con in self.state.constraints:
            if not con.violated:
                continue
            sev = (
                SeverityLevel.CRITICAL
                if con.priority == ConstraintPriority.HARD
                else SeverityLevel.MEDIUM
            )
            involved = [con.module] + [m for m in con.competing_modules[:3] if m != con.module]
            conflicts.append(
                Conflict(
                    id=str(uuid.uuid4())[:8].upper(),
                    conflict_type=f"Constraint Violation ({con.priority.value.upper()})",
                    involved_modules=involved,
                    constraint_id=con.id,
                    description=(
                        f"[{con.id}] {con.name} violated: {con.metric} at "
                        f"{con.current_value:.1f}{con.unit} (required {con.operator} "
                        f"{con.threshold:.0f}{con.unit}). {con.description}"
                    ),
                    severity=sev,
                    suggested_resolution=(
                        f"Run recovery optimization for {con.module} and ration competing "
                        f"demands across {', '.join(con.competing_modules[:3])}."
                    ),
                )
            )

        for res in self.state.resources.values():
            if res.total_demand > res.available_capacity:
                deficit = round(res.total_demand - res.available_capacity, 1)
                consumers = sorted(res.baseline_demand.items(), key=lambda x: -x[1])
                top_consumers = [m for m, _ in consumers[:4]]
                conflicts.append(
                    Conflict(
                        id=str(uuid.uuid4())[:8].upper(),
                        conflict_type="Competing Resource Contention",
                        involved_modules=top_consumers,
                        description=(
                            f"{res.name} deficit of {deficit} {res.unit}: total demand is "
                            f"{res.total_demand:.0f} {res.unit} vs {res.available_capacity:.0f} "
                            f"{res.unit} available (contention ratio {res.contention_ratio}x)."
                        ),
                        severity=(
                            SeverityLevel.HIGH
                            if res.contention_ratio >= 1.5
                            else SeverityLevel.MEDIUM
                        ),
                        suggested_resolution=(
                            f"Apply constraint-aware allocation policy in Recovery Plans to "
                            f"ration {res.name} prioritizing mission-critical modules."
                        ),
                    )
                )

        return conflicts
