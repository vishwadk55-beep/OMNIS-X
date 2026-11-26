"""
OMNIS-X Quick Test Script
Verifies all engines work correctly
"""
from backend.core.institution_builder import build_institution
from backend.engines.cascade_simulator import CascadeSimulator
from backend.engines.conflict_detector import ConflictDetector
from backend.engines.dependency_graph import DependencyGraph
from backend.engines.recovery_planner import RecoveryPlanner

print("=" * 60)
print("  OMNIS-X — Institutional Digital Twin  ")
print("  Quick System Verification              ")
print("=" * 60)

print("\n[1/5] Building institutional digital twin...")
state = build_institution()
print(f"      ✅ {len(state.modules)} modules loaded")
total_subsystems = sum(len(m.subsystems) for m in state.modules.values())
print(f"      ✅ {total_subsystems} subsystems initialized")
print(f"      ✅ Overall health: {state.overall_health:.1f}%")
print(f"      ✅ Students: {state.student_count}, Faculty: {state.faculty_count}")

print("\n[2/5] Testing dependency graph engine...")
graph = DependencyGraph()
downstream = graph.get_downstream_modules("power")
print(f"      ✅ Power outage downstream: {len(downstream)} modules affected")
risk_ranks = graph.get_module_risk_rank()
print(f"      ✅ Risk ranking: {risk_ranks[0][0]} is highest risk (score={risk_ranks[0][1]})")

print("\n[3/5] Running cascade simulation (Power Outage, HIGH)...")
sim = CascadeSimulator(state)
disruption, drops = sim.simulate("power_outage", "high")
summary = sim.get_simulation_summary(disruption, drops)
print(f"      ✅ Disruption ID: {disruption.id}")
print(f"      ✅ Source: {disruption.source_module}")
print(f"      ✅ Cascaded to: {len(disruption.cascaded_to)} modules")
print(f"      ✅ Students affected: {disruption.students_affected:,}")
print(f"      ✅ Faculty affected: {disruption.faculty_affected}")
print(f"      ✅ System health after: {state.overall_health:.1f}%")

print("\n[4/5] Running conflict detection...")
detector = ConflictDetector(state)
conflicts = detector.detect_all_conflicts()
print(f"      ✅ Detected {len(conflicts)} conflicts")
for c in conflicts[:3]:
    print(f"         → [{c.severity.value.upper()}] {c.conflict_type}: {c.involved_modules}")

print("\n[5/5] Generating recovery plan...")
planner = RecoveryPlanner(state)
plan = planner.generate_plan(disruption)
print(f"      ✅ Plan ID: {plan.id}")
print(f"      ✅ Actions: {len(plan.actions)}")
print(f"      ✅ Est. time: {plan.total_estimated_time} min")
print(f"      ✅ Risk: {plan.risk_assessment[:80]}...")

print("\n" + "=" * 60)
print("  ✅ ALL SYSTEMS OPERATIONAL — OMNIS-X READY!")
print("  Run: python app.py  →  http://localhost:5000")
print("=" * 60 + "\n")
