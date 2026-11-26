"""
OMNIS-X Cascading Failure Simulation Engine
Simulates how a single or compound disruption propagates across the institution
"""
import random
import uuid
from typing import Any

from ..core.models import (
    Disruption,
    DisruptionType,
    InstitutionState,
    SeverityLevel,
    SystemStatus,
)
from .constraint_engine import ConstraintEngine
from .dependency_graph import DISRUPTION_IMPACT_MAP, DependencyGraph

SEVERITY_MAP = {
    "low": SeverityLevel.LOW,
    "medium": SeverityLevel.MEDIUM,
    "high": SeverityLevel.HIGH,
    "critical": SeverityLevel.CRITICAL,
}


def _health_to_status(health: float) -> SystemStatus:
    if health >= 80:
        return SystemStatus.OPERATIONAL
    elif health >= 50:
        return SystemStatus.DEGRADED
    elif health >= 20:
        return SystemStatus.CRITICAL
    else:
        return SystemStatus.FAILED


class CascadeSimulator:
    """
    Simulates cascading disruptions across the institutional digital twin
    """

    def __init__(self, state: InstitutionState):
        self.state = state
        self.graph = DependencyGraph()

    def simulate(
        self,
        disruption_type: str,
        severity: str = "high",
        source_override: str | None = None,
    ) -> tuple[Disruption, dict[str, float]]:
        """
        Run a full cascading simulation for a given disruption type.
        Returns (disruption_object, {module_id: health_drop})
        """
        impact_template = DISRUPTION_IMPACT_MAP.get(disruption_type)
        if not impact_template:
            raise ValueError(f"Unknown disruption type: {disruption_type}")

        severity_level = SEVERITY_MAP.get(severity, SeverityLevel.HIGH)
        severity_mult = {
            SeverityLevel.LOW: 0.4,
            SeverityLevel.MEDIUM: 0.65,
            SeverityLevel.HIGH: 0.85,
            SeverityLevel.CRITICAL: 1.0,
        }[severity_level]

        primary_modules = impact_template["primary"]
        source_module = source_override or primary_modules[0]

        base_drop = min(100.0 * severity_mult * impact_template["severity_multiplier"], 100.0)

        cascade_drops, waves, edges = self.graph.compute_cascade_trace(source_module, base_drop)
        all_drops: dict[str, float] = {source_module: base_drop}
        for mod, drop in cascade_drops.items():
            all_drops[mod] = min(drop, 95.0)

        extra_wave_mods = []
        for cascade_mod in impact_template["cascade_path"]:
            if cascade_mod not in all_drops:
                template_drop = min(base_drop * 0.5 * random.uniform(0.6, 1.0), 90.0)
                all_drops[cascade_mod] = round(template_drop, 2)
                extra_wave_mods.append({"module": cascade_mod, "drop": round(template_drop, 2)})
                edges.append({
                    "from": source_module,
                    "to": cascade_mod,
                    "wave": 1,
                    "weight": 0.5,
                    "drop": round(template_drop, 2),
                })

        if extra_wave_mods:
            if len(waves) > 1:
                waves[1]["modules"].extend(extra_wave_mods)
            else:
                waves.append({"wave": 1, "label": "Direct Impact (Wave 1)", "modules": extra_wave_mods})

        affected_modules = []
        cascaded_to = []
        for mod_id, drop in all_drops.items():
            if mod_id in self.state.modules:
                module = self.state.modules[mod_id]
                module.health_score = max(0.0, module.health_score - drop)
                module.status = _health_to_status(module.health_score)
                for sub in module.subsystems:
                    sub.health_score = max(0.0, sub.health_score - drop * random.uniform(0.55, 1.0))
                    sub.status = _health_to_status(sub.health_score)
                affected_modules.append(mod_id)
                if mod_id != source_module:
                    cascaded_to.append(mod_id)

        total_students = self.state.student_count
        total_faculty = self.state.faculty_count
        s_pct = impact_template["students_affected_pct"] * severity_mult
        f_pct = impact_template["faculty_affected_pct"] * severity_mult

        disruption = Disruption(
            id=str(uuid.uuid4())[:8].upper(),
            type=DisruptionType(disruption_type),
            source_module=source_module,
            affected_modules=affected_modules,
            severity=severity_level,
            description=self._generate_description(disruption_type, source_module, severity),
            cascaded_to=cascaded_to,
            cascade_waves=waves,
            cascade_edges=edges,
            impact_score=round(sum(all_drops.values()) / max(len(all_drops), 1), 2),
            students_affected=int(total_students * s_pct),
            faculty_affected=int(total_faculty * f_pct),
        )

        self.state.active_disruptions.append(disruption)
        self.state.compute_overall_health()
        ConstraintEngine(self.state).evaluate_all()

        return disruption, all_drops

    def _generate_description(self, dtype: str, source: str, severity: str) -> str:
        sev = severity.upper()
        descriptions = {
            "power_outage": (
                f"Complete power failure in {source} module. {sev} severity outage "
                "affecting campus-wide electrical systems; generators may not cover all zones."
            ),
            "network_failure": (
                f"Critical network failure in {source}. Campus LAN and internet "
                "connectivity disrupted; ERP and LMS inaccessible."
            ),
            "faculty_absence": (
                f"Mass faculty absence affecting {source} operations. Classes, labs, "
                "and exams are at risk across multiple departments."
            ),
            "lab_equipment_failure": (
                f"Critical laboratory equipment failure in {source}. Practical sessions, "
                "research, and lab exams are disrupted."
            ),
            "transport_breakdown": (
                f"Transportation fleet failure in {source}. Multiple bus routes suspended; "
                "students and faculty unable to commute."
            ),
            "exam_system_failure": (
                f"Examination system crash in {source}. Scheduled exams at risk; seating "
                "allocation and question paper delivery affected."
            ),
            "hostel_facility_failure": (
                f"Hostel facility failure in {source}. Residential students facing "
                "accommodation and essential service disruption."
            ),
            "classroom_unavailability": (
                f"Classroom infrastructure failure in {source}. Multiple rooms unavailable; "
                "lectures and exams require rescheduling."
            ),
            "placement_portal_down": (
                f"Training & placement portal offline in {source}. Recruitment drives "
                "suspended and company communications disrupted."
            ),
            "event_cancellation": (
                f"Major event infrastructure failure in {source}. Technical fests, "
                "cultural events, or seminars must be postponed."
            ),
            "water_supply_failure": (
                f"Water supply failure in {source}. Campus hygiene, cafeteria operations, "
                "and hostel amenities severely affected."
            ),
            "cafeteria_failure": (
                f"Cafeteria and mess failure in {source}. Food services disrupted "
                "for residential students and staff."
            ),
            "security_breach": (
                f"Security system compromise in {source}. Campus safety protocols "
                "activated and restricted access enforced."
            ),
            "admin_system_failure": (
                f"Administrative system failure in {source}. Finance processing, "
                "regulatory filings, and HR operations halted."
            ),
            "library_outage": (
                f"Library and academic resource systems down in {source}. Digital and "
                "physical library access disrupted."
            ),
        }
        return descriptions.get(dtype, f"Disruption detected in {source} module with {severity} severity.")

    def resolve_disruption(self, disruption_id: str) -> bool:
        """Resolve a disruption and restore module health"""
        disruption = next((d for d in self.state.active_disruptions if d.id == disruption_id), None)
        if not disruption:
            return False

        for mod_id in disruption.affected_modules:
            if mod_id in self.state.modules:
                module = self.state.modules[mod_id]
                restore_pct = random.uniform(0.75, 0.92)
                module.health_score = min(100.0, module.health_score + (100.0 - module.health_score) * restore_pct)
                module.status = _health_to_status(module.health_score)
                for sub in module.subsystems:
                    sub.health_score = min(100.0, sub.health_score + (100.0 - sub.health_score) * restore_pct)
                    sub.status = _health_to_status(sub.health_score)

        disruption.resolved = True
        self.state.active_disruptions = [d for d in self.state.active_disruptions if not d.resolved]
        self.state.compute_overall_health()
        ConstraintEngine(self.state).evaluate_all()
        return True

    def get_simulation_summary(self, disruption: Disruption, drops: dict[str, float]) -> dict[str, Any]:
        """Generate a human-readable simulation summary"""
        violated_constraints = [c.to_dict() for c in self.state.constraints if c.violated]
        return {
            "disruption_id": disruption.id,
            "type": disruption.type.value,
            "severity": disruption.severity.value,
            "source": disruption.source_module,
            "cascade_chain": disruption.cascaded_to,
            "cascade_waves": disruption.cascade_waves,
            "cascade_edges": disruption.cascade_edges,
            "modules_affected": len(disruption.affected_modules),
            "students_affected": disruption.students_affected,
            "faculty_affected": disruption.faculty_affected,
            "impact_score": disruption.impact_score,
            "top_drops": sorted(drops.items(), key=lambda x: -x[1])[:5],
            "overall_health_after": self.state.overall_health,
            "violated_constraints_count": len(violated_constraints),
            "violated_constraints": violated_constraints,
            "timestamp": disruption.timestamp,
        }
