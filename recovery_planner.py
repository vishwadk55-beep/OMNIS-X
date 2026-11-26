"""
OMNIS-X Recovery Planning Engine
Generates intelligent, prioritized recovery plans under competing constraints
"""
import uuid
from typing import Any

from ..core.models import (
    Disruption,
    InstitutionState,
    RecoveryAction,
    RecoveryPlan,
    SeverityLevel,
    SystemStatus,
)
from .constraint_engine import ConstraintEngine


def _health_to_status(health: float) -> SystemStatus:
    if health >= 80:
        return SystemStatus.OPERATIONAL
    elif health >= 50:
        return SystemStatus.DEGRADED
    elif health >= 20:
        return SystemStatus.CRITICAL
    else:
        return SystemStatus.FAILED


RECOVERY_TEMPLATES: dict[str, list[dict]] = {
    "power_outage": [
        {
            "title": "Activate Emergency Generators",
            "desc": "Start backup generators for exam halls, server room, and critical labs.",
            "responsible": "Electrical Department",
            "time": 5,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Switch to UPS Systems",
            "desc": "Activate UPS for campus servers, networking gear, and medical center.",
            "responsible": "IT Department",
            "time": 3,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Notify All Stakeholders",
            "desc": "Send SMS/Email broadcast to students and faculty on power contingencies.",
            "responsible": "Administration",
            "time": 10,
            "priority": 2,
            "auto": True,
        },
        {
            "title": "Contact Utility Provider",
            "desc": "Request grid ETA from utility board and escalate if outage exceeds 30 minutes.",
            "responsible": "Principal Office",
            "time": 15,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Load Shedding Protocol",
            "desc": "Prioritize server room, exam halls, medical bay, and hostel security.",
            "responsible": "Electrical HOD",
            "time": 20,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Postpone Online Activities",
            "desc": "Defer non-essential online classes and portal tasks until grid power returns.",
            "responsible": "Academic Section",
            "time": 30,
            "priority": 3,
            "auto": False,
        },
        {
            "title": "Post-Restoration Verification",
            "desc": "Audit servers, lab interlocks, and security gear after power restoration.",
            "responsible": "IT + Electrical",
            "time": 60,
            "priority": 4,
            "auto": False,
        },
    ],
    "network_failure": [
        {
            "title": "Activate Backup ISP",
            "desc": "Fail over DNS and core routing to redundant secondary fiber ISP.",
            "responsible": "IT Department",
            "time": 5,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Enable Offline LMS Mode",
            "desc": "Switch LMS to local caching mode so faculty can serve course packs.",
            "responsible": "IT Department",
            "time": 15,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Paper-Based Attendance",
            "desc": "Distribute physical attendance sheets for manual reconciliation later.",
            "responsible": "Academic Section",
            "time": 20,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Suspend Cloud-Dependent Exams",
            "desc": "Pause cloud CBT exams and reschedule affected batches within 48 hours.",
            "responsible": "Exam Section",
            "time": 10,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Diagnose Network Root Cause",
            "desc": "Trace fiber cut, BGP drop, or core switch fault with ISP NOC.",
            "responsible": "Network Admin",
            "time": 45,
            "priority": 3,
            "auto": False,
        },
        {
            "title": "Data Sync Post-Recovery",
            "desc": "Reconcile offline attendance, library, and portal records back to ERP.",
            "responsible": "IT Department",
            "time": 90,
            "priority": 4,
            "auto": False,
        },
    ],
    "faculty_absence": [
        {
            "title": "Identify Absent Faculty",
            "desc": "Cross-check biometric attendance and timetable to list affected courses.",
            "responsible": "HOD / Academic Section",
            "time": 10,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Assign Substitute Faculty",
            "desc": "Reassign available faculty from sister departments and update ERP timetable.",
            "responsible": "Department HOD",
            "time": 20,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Reschedule Critical Classes",
            "desc": "Move uncovered lectures and labs into compensatory afternoon slots.",
            "responsible": "Academic Section",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Notify Affected Students",
            "desc": "Push timetable adjustment notices to impacted student cohorts.",
            "responsible": "IT Department",
            "time": 15,
            "priority": 2,
            "auto": True,
        },
        {
            "title": "Engage Guest Faculty",
            "desc": "Invite empaneled industry/visiting faculty for extended shortages.",
            "responsible": "Principal Office",
            "time": 60,
            "priority": 3,
            "auto": False,
        },
        {
            "title": "Update Leave Records",
            "desc": "Log approved/emergency leaves in HRMS for AICTE load compliance.",
            "responsible": "HR Department",
            "time": 60,
            "priority": 4,
            "auto": False,
        },
    ],
    "lab_equipment_failure": [
        {
            "title": "Evacuate Lab Safely",
            "desc": "Vacate students and staff from impacted lab following safety protocol.",
            "responsible": "Lab Supervisor",
            "time": 5,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Safety Systems Check",
            "desc": "Verify chemical containment, fire suppression, and ventilation interlocks.",
            "responsible": "Safety Officer",
            "time": 10,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Contact Equipment Vendor",
            "desc": "Trigger AMC maintenance dispatch and log warranty fault ticket.",
            "responsible": "Lab In-charge",
            "time": 15,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Reschedule Lab Sessions",
            "desc": "Reassign practical batches to alternate labs or reserve timetable slots.",
            "responsible": "HOD",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Arrange Alternate Labs",
            "desc": "Coordinate cross-department lab sharing to prevent exam delays.",
            "responsible": "Principal Office",
            "time": 60,
            "priority": 3,
            "auto": False,
        },
        {
            "title": "File Incident Report",
            "desc": "Document hardware fault and submit report to Safety Committee.",
            "responsible": "Lab In-charge",
            "time": 60,
            "priority": 4,
            "auto": False,
        },
    ],
    "transport_breakdown": [
        {
            "title": "Account All Students",
            "desc": "Contact bus captains and verify passenger safety across delayed routes.",
            "responsible": "Transport Office",
            "time": 10,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Arrange Emergency Vehicles",
            "desc": "Dispatch backup shuttles and contracted cabs to stranded pickup points.",
            "responsible": "Transport Manager",
            "time": 20,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Notify Parents & Students",
            "desc": "Send automated SMS alerts on route delays and alternate pickup shuttles.",
            "responsible": "Administration",
            "time": 10,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Adjust Timetable",
            "desc": "Shift first-period start by 45 minutes so commuters avoid attendance loss.",
            "responsible": "Academic Section",
            "time": 20,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Arrange Mechanic/Tow",
            "desc": "Deploy fleet maintenance team and recovery tow for immobilized buses.",
            "responsible": "Transport Office",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "File Insurance Claim",
            "desc": "Log vehicle fault and insurance documentation if repair exceeds SLA.",
            "responsible": "Finance Department",
            "time": 120,
            "priority": 4,
            "auto": False,
        },
    ],
    "exam_system_failure": [
        {
            "title": "IMMEDIATE: Pause All Exams",
            "desc": "Freeze active CBT exams, secure exam halls, and preserve answer state.",
            "responsible": "Chief Superintendent",
            "time": 2,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Save Partial Answers",
            "desc": "Snapshot local client caches and exam DB logs before restart.",
            "responsible": "IT Department",
            "time": 10,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Switch to Paper Exam",
            "desc": "Issue sealed paper question booklets and answer sheets under Principal sign-off.",
            "responsible": "Exam Section + Principal",
            "time": 15,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Notify Exam Board/University",
            "desc": "Inform university exam controller of contingency switch and timestamps.",
            "responsible": "Controller of Examinations",
            "time": 20,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "System Diagnosis",
            "desc": "Inspect application crash, DB lock, or network timeout with exam vendor.",
            "responsible": "IT Department",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Reschedule If Needed",
            "desc": "Issue 48-hour makeup exam slot for any batch unable to transition.",
            "responsible": "Exam Section",
            "time": 60,
            "priority": 3,
            "auto": False,
        },
        {
            "title": "Post-Incident Report",
            "desc": "Submit signed root-cause audit and preventive SLA checklist.",
            "responsible": "Principal + IT",
            "time": 240,
            "priority": 4,
            "auto": False,
        },
    ],
    "hostel_facility_failure": [
        {
            "title": "Assess Facility Damage",
            "desc": "Inspect water lines, electrical risers, and structural safety across blocks.",
            "responsible": "Hostel Warden",
            "time": 10,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Ensure Student Safety",
            "desc": "Complete resident headcount and relocate students from impacted wings.",
            "responsible": "Hostel Warden + Security",
            "time": 15,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Arrange Alternative Facilities",
            "desc": "Open indoor auditorium/guest house as temporary emergency lodging.",
            "responsible": "Administration",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Contact Maintenance Contractors",
            "desc": "Dispatch on-call plumbing and electrical restoration contractors.",
            "responsible": "Estate Office",
            "time": 20,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Arrange Food & Water",
            "desc": "Procure drinking water tankers and external catering if mess is down.",
            "responsible": "Hostel Committee",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Inform Parents",
            "desc": "Send verified safety & accommodation status to parents of residents.",
            "responsible": "Student Affairs",
            "time": 45,
            "priority": 3,
            "auto": False,
        },
    ],
    "classroom_unavailability": [
        {
            "title": "Assess Available Spaces",
            "desc": "Audit unaffected seminar halls, labs, and auditorium slots.",
            "responsible": "Estate Office",
            "time": 10,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Reallocate Classes",
            "desc": "Re-map timetable prioritizing exam halls first, then core lectures.",
            "responsible": "Academic Section",
            "time": 20,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Notify Faculty & Students",
            "desc": "Publish updated room assignments via LMS and campus alerts.",
            "responsible": "Academic Section",
            "time": 15,
            "priority": 2,
            "auto": True,
        },
        {
            "title": "Emergency Repair Assessment",
            "desc": "Estimate structural/HVAC/AV restoration time with estate engineers.",
            "responsible": "Estate Office",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Flexible Scheduling",
            "desc": "Schedule compensatory evening or Saturday slots for deferred sessions.",
            "responsible": "HOD",
            "time": 60,
            "priority": 3,
            "auto": False,
        },
    ],
    "placement_portal_down": [
        {
            "title": "Notify Visiting Companies",
            "desc": "Brief campus recruiters on outage and switch interviews to manual flow.",
            "responsible": "Placement Officer",
            "time": 10,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Manual Application Backup",
            "desc": "Collect resumes and shortlists via dedicated email and shared ledger.",
            "responsible": "Placement Team",
            "time": 20,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "IT Emergency Restore",
            "desc": "Inspect DB pool, SSL certificate, and reverse proxy to restore portal.",
            "responsible": "IT Department",
            "time": 30,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Reschedule Drives",
            "desc": "Defer portal-dependent online assessments by 24 hours if outage persists.",
            "responsible": "Placement Officer",
            "time": 60,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Post-Mortem Analysis",
            "desc": "Add automated failover and health alerts to placement infrastructure.",
            "responsible": "IT Department",
            "time": 180,
            "priority": 4,
            "auto": False,
        },
    ],
    "security_breach": [
        {
            "title": "IMMEDIATE: Lockdown Protocol",
            "desc": "Enforce perimeter gate lockdown and alert local law enforcement.",
            "responsible": "Security Head + Principal",
            "time": 2,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Account All People",
            "desc": "Run department and hostel headcounts; report status to command desk.",
            "responsible": "Department Heads",
            "time": 15,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Secure Digital Systems",
            "desc": "Rotate admin credentials, revoke active tokens, and isolate servers.",
            "responsible": "IT Security",
            "time": 10,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Contact Cybercrime Cell",
            "desc": "Preserve forensic logs and file incident report if digital intrusion occurred.",
            "responsible": "Principal + Legal Cell",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Notify Stakeholders",
            "desc": "Brief Board of Governors, regulators, and parents as required.",
            "responsible": "Principal Office",
            "time": 60,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Security Audit",
            "desc": "Conduct independent physical and cyber security posture review.",
            "responsible": "Administration",
            "time": 240,
            "priority": 4,
            "auto": False,
        },
    ],
    "admin_system_failure": [
        {
            "title": "Backup to Offline Records",
            "desc": "Activate offline ledgers for registrar, finance, and HR tasks.",
            "responsible": "Registrar",
            "time": 15,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Freeze Non-Critical Transactions",
            "desc": "Pause non-urgent disbursements; protect payroll and emergency funds.",
            "responsible": "Finance Officer",
            "time": 20,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "IT System Diagnosis",
            "desc": "Isolate ERP fault across database, application tier, or storage.",
            "responsible": "IT Department",
            "time": 30,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Extend Submission Deadlines",
            "desc": "Grant 48-hour extension on fee and registration deadlines.",
            "responsible": "Principal Office",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Restore from Backup",
            "desc": "Restore ERP from verified snapshot and validate ledger checksums.",
            "responsible": "IT Department",
            "time": 120,
            "priority": 3,
            "auto": False,
        },
    ],
    "water_supply_failure": [
        {
            "title": "Emergency Water Tankers",
            "desc": "Order water tankers and establish distribution stations at hostels.",
            "responsible": "Estate Office",
            "time": 30,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Suspend Cafeteria Operations",
            "desc": "Halt open cooking until potable water resumes; issue packaged meals.",
            "responsible": "Hostel Warden",
            "time": 15,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Plumbing Emergency Repair",
            "desc": "Locate main supply break or pump failure and dispatch repair crew.",
            "responsible": "Estate Office",
            "time": 20,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Hygiene Advisory",
            "desc": "Issue campus water conservation and sanitation guidelines.",
            "responsible": "Health Center",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Contact Municipal Authority",
            "desc": "Escalate municipal water line restoration priority.",
            "responsible": "Principal Office",
            "time": 45,
            "priority": 2,
            "auto": False,
        },
    ],
    "cafeteria_failure": [
        {
            "title": "Source External Catering",
            "desc": "Engage backup approved caterers for hostel meal continuity.",
            "responsible": "Hostel Committee",
            "time": 30,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Distribute Meal Packets",
            "desc": "Serve hygienic packaged meals across hostel and academic blocks.",
            "responsible": "Student Affairs",
            "time": 45,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Food Safety Inspection",
            "desc": "Health officer inspects kitchen cause and certifies safe resumption.",
            "responsible": "Health Center",
            "time": 30,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Repair Cafeteria Equipment",
            "desc": "Service faulty boilers, refrigeration, or gas lines.",
            "responsible": "Estate Office",
            "time": 60,
            "priority": 3,
            "auto": False,
        },
    ],
    "library_outage": [
        {
            "title": "Enable Physical Book Access",
            "desc": "Open physical stacks with manual checkout ledgers.",
            "responsible": "Librarian",
            "time": 15,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Share Alternate Resources",
            "desc": "Circulate external NPTEL/SWAYAM and open-journal links.",
            "responsible": "Librarian + IT",
            "time": 20,
            "priority": 2,
            "auto": True,
        },
        {
            "title": "IT System Recovery",
            "desc": "Restore digital catalog and proxy server from backup.",
            "responsible": "IT Department",
            "time": 60,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Extend Borrowing Period",
            "desc": "Auto-extend return due dates and waive late fees during outage.",
            "responsible": "Librarian",
            "time": 10,
            "priority": 3,
            "auto": False,
        },
    ],
    "event_cancellation": [
        {
            "title": "Issue Event Cancellation Notice",
            "desc": "Publish official postponement notice across portal and boards.",
            "responsible": "Student Affairs + Events Committee",
            "time": 15,
            "priority": 1,
            "auto": True,
        },
        {
            "title": "Notify Participants & Guests",
            "desc": "Contact registered teams, speakers, and guests individually.",
            "responsible": "Events Committee",
            "time": 30,
            "priority": 1,
            "auto": False,
        },
        {
            "title": "Reschedule Date",
            "desc": "Select conflict-free post-exam date on institutional calendar.",
            "responsible": "Principal Office",
            "time": 60,
            "priority": 2,
            "auto": False,
        },
        {
            "title": "Vendor & Sponsor Communication",
            "desc": "Coordinate contract rollover with event vendors and sponsors.",
            "responsible": "Events Committee + Finance",
            "time": 60,
            "priority": 3,
            "auto": False,
        },
    ],
}


class RecoveryPlanner:
    """
    Generates intelligent recovery plans under competing institutional constraints
    """

    def __init__(self, state: InstitutionState):
        self.state = state

    def generate_plan(self, disruption: Disruption, strategy: str = "balanced") -> RecoveryPlan:
        """Generate a constraint-aware recovery plan for a disruption."""
        template_key = disruption.type.value
        templates = RECOVERY_TEMPLATES.get(template_key, [])

        actions: list[RecoveryAction] = []
        for t in templates:
            action = RecoveryAction(
                id=str(uuid.uuid4())[:8].upper(),
                title=t["title"],
                description=t["desc"],
                module=disruption.source_module,
                priority=t["priority"],
                estimated_time_minutes=t["time"],
                responsible_party=t["responsible"],
                automation_possible=t.get("auto", False),
                dependencies=[
                    actions[j].id
                    for j in range(len(actions))
                    if t["priority"] > templates[j]["priority"]
                ][:2],
            )
            actions.append(action)

        for mod_id in disruption.cascaded_to[:3]:
            mod = self.state.modules.get(mod_id)
            if mod and mod.health_score < 70:
                actions.append(
                    RecoveryAction(
                        id=str(uuid.uuid4())[:8].upper(),
                        title=f"Stabilize Downstream {mod.name}",
                        description=(
                            f"Isolate cascading impact on {mod.name} (health {mod.health_score:.0f}%) "
                            f"by applying {strategy.replace('_', ' ')} resource rationing."
                        ),
                        module=mod_id,
                        priority=2,
                        estimated_time_minutes=15,
                        responsible_party=f"{mod.name} Coordinator",
                        automation_possible=True,
                    )
                )

        actions.sort(key=lambda a: a.priority)
        total_time = max((a.estimated_time_minutes for a in actions), default=60)

        solver = ConstraintEngine(self.state)
        opt_result = solver.solve_competing_allocations(strategy=strategy)

        health_deficit = max(0.0, 100.0 - self.state.overall_health)
        expected_gain = round(health_deficit * 0.72, 2)

        plan = RecoveryPlan(
            id=str(uuid.uuid4())[:8].upper(),
            disruption_id=disruption.id,
            title=f"Recovery Plan: {disruption.type.value.replace('_', ' ').title()}",
            total_estimated_time=total_time,
            actions=actions,
            risk_assessment=self._assess_risk(disruption),
            overall_status="active",
            strategy=strategy,
            resource_allocations=opt_result["resource_allocations"],
            constraint_tradeoffs=opt_result["constraint_tradeoffs"],
            expected_health_gain=expected_gain,
        )

        self.state.recovery_plans.append(plan)
        return plan

    def replan_with_strategy(self, plan_id: str, strategy: str) -> RecoveryPlan:
        """Re-optimize an existing recovery plan under a different competing-constraint strategy."""
        plan = next((p for p in self.state.recovery_plans if p.id == plan_id), None)
        if not plan:
            raise ValueError(f"Recovery plan not found: {plan_id}")

        solver = ConstraintEngine(self.state)
        opt_result = solver.solve_competing_allocations(strategy=strategy)
        plan.strategy = strategy
        plan.resource_allocations = opt_result["resource_allocations"]
        plan.constraint_tradeoffs = opt_result["constraint_tradeoffs"]
        return plan

    def execute_plan(self, plan_id: str) -> dict[str, Any]:
        """Execute all recovery actions in a plan, restoring systems proportionally to constraints."""
        plan = next((p for p in self.state.recovery_plans if p.id == plan_id), None)
        if not plan:
            raise ValueError(f"Recovery plan not found: {plan_id}")

        for action in plan.actions:
            action.status = "completed"
        plan.overall_status = "completed"

        disruption = next(
            (d for d in self.state.active_disruptions if d.id == plan.disruption_id), None
        )
        health_before = self.state.overall_health

        if disruption:
            sat_scores: dict[str, list[float]] = {}
            for res in plan.resource_allocations:
                for row in res.get("consumers", []):
                    sat_scores.setdefault(row["module"], []).append(row["satisfaction_pct"] / 100.0)

            for mod_id in disruption.affected_modules:
                mod = self.state.modules.get(mod_id)
                if not mod:
                    continue
                mod_sats = sat_scores.get(mod_id, [0.85])
                avg_sat = sum(mod_sats) / max(len(mod_sats), 1)
                recovery_factor = 0.55 + (0.37 * avg_sat)
                mod.health_score = min(100.0, mod.health_score + (100.0 - mod.health_score) * recovery_factor)
                mod.status = _health_to_status(mod.health_score)
                for sub in mod.subsystems:
                    sub.health_score = min(
                        100.0, sub.health_score + (100.0 - sub.health_score) * recovery_factor
                    )
                    sub.status = _health_to_status(sub.health_score)

            disruption.resolved = True
            self.state.active_disruptions = [
                d for d in self.state.active_disruptions if not d.resolved
            ]

        self.state.compute_overall_health()
        ConstraintEngine(self.state).evaluate_all()

        return {
            "plan_id": plan.id,
            "strategy": plan.strategy,
            "health_before": health_before,
            "health_after": self.state.overall_health,
            "actions_completed": len(plan.actions),
        }

    def _assess_risk(self, disruption: Disruption) -> str:
        severity_map = {
            SeverityLevel.LOW: "LOW RISK",
            SeverityLevel.MEDIUM: "MODERATE RISK",
            SeverityLevel.HIGH: "HIGH RISK",
            SeverityLevel.CRITICAL: "CRITICAL RISK",
        }
        base = severity_map.get(disruption.severity, "MODERATE RISK")
        cascades = len(disruption.cascaded_to)

        if cascades >= 5:
            risk_detail = "Severe multi-system cascade. Institutional operations heavily impacted."
        elif cascades >= 3:
            risk_detail = "Moderate cascade detected. Multiple academic and operational modules affected."
        elif cascades >= 1:
            risk_detail = "Limited cascade. Recovery feasible with standard protocols."
        else:
            risk_detail = "Isolated failure. Contained recovery expected."

        return (
            f"{base}: {risk_detail} Estimated {disruption.students_affected} students and "
            f"{disruption.faculty_affected} faculty affected."
        )

    def update_action_status(self, plan_id: str, action_id: str, status: str) -> bool:
        plan = next((p for p in self.state.recovery_plans if p.id == plan_id), None)
        if not plan:
            return False
        action = next((a for a in plan.actions if a.id == action_id), None)
        if not action:
            return False
        action.status = status
        statuses = [a.status for a in plan.actions]
        if all(s == "completed" for s in statuses):
            plan.overall_status = "completed"
        elif any(s in ("in_progress", "completed") for s in statuses):
            plan.overall_status = "in_progress"
        return True
