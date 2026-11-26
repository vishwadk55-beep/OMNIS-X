"""
OMNIS-X Core Data Models
Constraint-Based Institutional Digital Twin for an Engineering College
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SystemStatus(Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"


class SeverityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConstraintPriority(Enum):
    HARD = "hard"
    SOFT = "soft"


class DisruptionType(Enum):
    POWER_OUTAGE = "power_outage"
    NETWORK_FAILURE = "network_failure"
    FACULTY_ABSENCE = "faculty_absence"
    LAB_EQUIPMENT_FAILURE = "lab_equipment_failure"
    TRANSPORT_BREAKDOWN = "transport_breakdown"
    EXAM_SYSTEM_FAILURE = "exam_system_failure"
    HOSTEL_FACILITY_FAILURE = "hostel_facility_failure"
    CLASSROOM_UNAVAILABILITY = "classroom_unavailability"
    PLACEMENT_PORTAL_DOWN = "placement_portal_down"
    EVENT_CANCELLATION = "event_cancellation"
    WATER_SUPPLY_FAILURE = "water_supply_failure"
    CAFETERIA_FAILURE = "cafeteria_failure"
    SECURITY_BREACH = "security_breach"
    ADMIN_SYSTEM_FAILURE = "admin_system_failure"
    LIBRARY_OUTAGE = "library_outage"


@dataclass
class SubSystem:
    id: str
    name: str
    module: str
    status: SystemStatus = SystemStatus.OPERATIONAL
    health_score: float = 100.0
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "module": self.module,
            "status": self.status.value,
            "health_score": round(self.health_score, 2),
            "dependencies": self.dependencies,
            "metadata": self.metadata,
        }


@dataclass
class InstitutionalModule:
    id: str
    name: str
    description: str
    status: SystemStatus = SystemStatus.OPERATIONAL
    health_score: float = 100.0
    subsystems: list[SubSystem] = field(default_factory=list)
    critical_constraints: list[str] = field(default_factory=list)
    icon: str = "🏫"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "health_score": round(self.health_score, 2),
            "subsystems": [s.to_dict() for s in self.subsystems],
            "critical_constraints": self.critical_constraints,
            "icon": self.icon,
        }


@dataclass
class InstitutionalConstraint:
    id: str
    name: str
    module: str
    metric: str
    operator: str  # ">=" or "<="
    threshold: float
    unit: str
    current_value: float = 100.0
    priority: ConstraintPriority = ConstraintPriority.HARD
    competing_modules: list[str] = field(default_factory=list)
    subsystem_id: str | None = None
    penalty_weight: float = 1.0
    description: str = ""
    violated: bool = False

    def evaluate(self) -> bool:
        if self.operator == ">=":
            self.violated = self.current_value < self.threshold
        elif self.operator == "<=":
            self.violated = self.current_value > self.threshold
        else:
            self.violated = False
        return self.violated

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "module": self.module,
            "metric": self.metric,
            "operator": self.operator,
            "threshold": self.threshold,
            "unit": self.unit,
            "current_value": round(self.current_value, 2),
            "priority": self.priority.value,
            "competing_modules": self.competing_modules,
            "subsystem_id": self.subsystem_id,
            "penalty_weight": self.penalty_weight,
            "description": self.description,
            "violated": self.violated,
        }


@dataclass
class SharedResource:
    id: str
    name: str
    unit: str
    nominal_capacity: float
    available_capacity: float
    baseline_demand: dict[str, float] = field(default_factory=dict)
    allocated: dict[str, float] = field(default_factory=dict)
    owner_module: str = "power"

    @property
    def total_demand(self) -> float:
        return sum(self.baseline_demand.values())

    @property
    def contention_ratio(self) -> float:
        if self.available_capacity <= 0:
            return 99.0
        return round(self.total_demand / self.available_capacity, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "unit": self.unit,
            "nominal_capacity": round(self.nominal_capacity, 2),
            "available_capacity": round(self.available_capacity, 2),
            "total_demand": round(self.total_demand, 2),
            "contention_ratio": self.contention_ratio,
            "baseline_demand": self.baseline_demand,
            "allocated": {k: round(v, 2) for k, v in self.allocated.items()},
            "owner_module": self.owner_module,
            "over_subscribed": self.total_demand > self.available_capacity,
        }


@dataclass
class Disruption:
    id: str
    type: DisruptionType
    source_module: str
    affected_modules: list[str] = field(default_factory=list)
    severity: SeverityLevel = SeverityLevel.MEDIUM
    description: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    cascaded_to: list[str] = field(default_factory=list)
    cascade_waves: list[dict[str, Any]] = field(default_factory=list)
    cascade_edges: list[dict[str, Any]] = field(default_factory=list)
    impact_score: float = 0.0
    students_affected: int = 0
    faculty_affected: int = 0
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "source_module": self.source_module,
            "affected_modules": self.affected_modules,
            "severity": self.severity.value,
            "description": self.description,
            "timestamp": self.timestamp,
            "cascaded_to": self.cascaded_to,
            "cascade_waves": self.cascade_waves,
            "cascade_edges": self.cascade_edges,
            "impact_score": self.impact_score,
            "students_affected": self.students_affected,
            "faculty_affected": self.faculty_affected,
            "resolved": self.resolved,
        }


@dataclass
class Conflict:
    id: str
    conflict_type: str
    involved_modules: list[str]
    description: str
    severity: SeverityLevel
    suggested_resolution: str = ""
    constraint_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conflict_type": self.conflict_type,
            "involved_modules": self.involved_modules,
            "description": self.description,
            "severity": self.severity.value,
            "suggested_resolution": self.suggested_resolution,
            "constraint_id": self.constraint_id,
            "timestamp": self.timestamp,
        }


@dataclass
class RecoveryAction:
    id: str
    title: str
    description: str
    module: str
    priority: int  # 1=highest
    estimated_time_minutes: int
    responsible_party: str
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed
    automation_possible: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "module": self.module,
            "priority": self.priority,
            "estimated_time_minutes": self.estimated_time_minutes,
            "responsible_party": self.responsible_party,
            "dependencies": self.dependencies,
            "status": self.status,
            "automation_possible": self.automation_possible,
        }


@dataclass
class RecoveryPlan:
    id: str
    disruption_id: str
    title: str
    total_estimated_time: int
    actions: list[RecoveryAction] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    overall_status: str = "pending"
    risk_assessment: str = ""
    strategy: str = "balanced"
    resource_allocations: list[dict[str, Any]] = field(default_factory=list)
    constraint_tradeoffs: list[dict[str, Any]] = field(default_factory=list)
    expected_health_gain: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "disruption_id": self.disruption_id,
            "title": self.title,
            "total_estimated_time": self.total_estimated_time,
            "actions": [a.to_dict() for a in self.actions],
            "created_at": self.created_at,
            "overall_status": self.overall_status,
            "risk_assessment": self.risk_assessment,
            "strategy": self.strategy,
            "resource_allocations": self.resource_allocations,
            "constraint_tradeoffs": self.constraint_tradeoffs,
            "expected_health_gain": round(self.expected_health_gain, 2),
        }


@dataclass
class InstitutionState:
    """Full digital twin state of the institution"""
    modules: dict[str, InstitutionalModule] = field(default_factory=dict)
    constraints: list[InstitutionalConstraint] = field(default_factory=list)
    resources: dict[str, SharedResource] = field(default_factory=dict)
    active_disruptions: list[Disruption] = field(default_factory=list)
    active_conflicts: list[Conflict] = field(default_factory=list)
    recovery_plans: list[RecoveryPlan] = field(default_factory=list)
    overall_health: float = 100.0
    student_count: int = 3000
    faculty_count: int = 150
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def compute_overall_health(self) -> float:
        if not self.modules:
            return 100.0
        scores = [m.health_score for m in self.modules.values()]
        self.overall_health = round(sum(scores) / len(scores), 2)
        self.last_updated = datetime.now().isoformat()
        return self.overall_health

    def to_dict(self) -> dict[str, Any]:
        violated_count = sum(1 for c in self.constraints if c.violated)
        return {
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
            "constraints": [c.to_dict() for c in self.constraints],
            "violated_constraints_count": violated_count,
            "resources": {k: v.to_dict() for k, v in self.resources.items()},
            "active_disruptions": [d.to_dict() for d in self.active_disruptions],
            "active_conflicts": [c.to_dict() for c in self.active_conflicts],
            "recovery_plans": [r.to_dict() for r in self.recovery_plans],
            "overall_health": self.overall_health,
            "student_count": self.student_count,
            "faculty_count": self.faculty_count,
            "last_updated": self.last_updated,
        }
