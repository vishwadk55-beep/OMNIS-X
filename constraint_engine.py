"""
OMNIS-X Constraint & Resource Optimization Engine
Evaluates hard/soft constraints and allocates scarce resources under competing demands.
"""
from typing import Any

from ..core.models import ConstraintPriority, InstitutionState

STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": {
        "power": 1.0,
        "network": 0.95,
        "examination": 0.95,
        "laboratory": 0.85,
        "hostel": 0.85,
        "academic": 0.85,
        "administration": 0.80,
        "faculty": 0.80,
        "classroom": 0.75,
        "student": 0.75,
        "transportation": 0.70,
        "placement": 0.65,
        "events": 0.35,
    },
    "exam_continuity": {
        "examination": 1.0,
        "power": 0.98,
        "network": 0.95,
        "faculty": 0.92,
        "classroom": 0.90,
        "academic": 0.85,
        "administration": 0.80,
        "hostel": 0.70,
        "student": 0.70,
        "laboratory": 0.55,
        "transportation": 0.65,
        "placement": 0.35,
        "events": 0.10,
    },
    "life_safety": {
        "hostel": 1.0,
        "laboratory": 0.98,
        "power": 0.98,
        "administration": 0.92,
        "transportation": 0.90,
        "student": 0.88,
        "network": 0.80,
        "faculty": 0.65,
        "academic": 0.55,
        "examination": 0.50,
        "classroom": 0.45,
        "placement": 0.25,
        "events": 0.05,
    },
    "placement_campus": {
        "placement": 1.0,
        "network": 0.98,
        "classroom": 0.90,
        "student": 0.88,
        "power": 0.92,
        "academic": 0.80,
        "administration": 0.75,
        "examination": 0.70,
        "faculty": 0.70,
        "hostel": 0.75,
        "transportation": 0.75,
        "laboratory": 0.60,
        "events": 0.40,
    },
}


class ConstraintEngine:
    """Evaluates institutional constraints and resolves resource competition."""

    def __init__(self, state: InstitutionState):
        self.state = state

    def evaluate_all(self) -> dict[str, Any]:
        """Update live constraint values and available shared resource capacities."""
        subsys_map = {
            sub.id: sub
            for mod in self.state.modules.values()
            for sub in mod.subsystems
        }

        violated = []
        for con in self.state.constraints:
            mod = self.state.modules.get(con.module)
            if not mod:
                continue
            if con.subsystem_id and con.subsystem_id in subsys_map:
                sub_h = subsys_map[con.subsystem_id].health_score
                con.current_value = round((mod.health_score * 0.65) + (sub_h * 0.35), 2)
            else:
                con.current_value = round(mod.health_score, 2)

            if con.evaluate():
                violated.append(con)

        for res in self.state.resources.values():
            owner = self.state.modules.get(res.owner_module)
            health_factor = (owner.health_score / 100.0) if owner else 1.0
            res.available_capacity = round(res.nominal_capacity * max(0.15, health_factor), 2)

        allocation_summary = self.solve_competing_allocations(strategy="balanced")

        return {
            "total_constraints": len(self.state.constraints),
            "violated_count": len(violated),
            "hard_violations": sum(1 for c in violated if c.priority == ConstraintPriority.HARD),
            "soft_violations": sum(1 for c in violated if c.priority == ConstraintPriority.SOFT),
            "violated_constraints": [c.to_dict() for c in violated],
            "allocation_summary": allocation_summary,
        }

    def solve_competing_allocations(self, strategy: str = "balanced") -> dict[str, Any]:
        """
        Allocate scarce shared resources across competing modules according to the chosen strategy.
        Returns allocation plan + constraint trade-off explanations.
        """
        weights = STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS["balanced"])
        resource_allocations: list[dict[str, Any]] = []
        tradeoffs: list[dict[str, Any]] = []

        for res_id, res in self.state.resources.items():
            remaining = res.available_capacity
            demands = res.baseline_demand
            ordered = sorted(
                demands.items(),
                key=lambda item: (-weights.get(item[0], 0.5), item[1]),
            )

            alloc: dict[str, float] = {}
            for mod_id, needed in ordered:
                if remaining >= needed:
                    alloc[mod_id] = needed
                    remaining -= needed
                else:
                    alloc[mod_id] = round(max(0.0, remaining), 2)
                    remaining = 0.0

            res.allocated = alloc
            shortage = max(0.0, res.total_demand - res.available_capacity)

            consumer_rows = []
            for mod_id, needed in ordered:
                got = alloc.get(mod_id, 0.0)
                sat_pct = round((got / needed * 100.0) if needed > 0 else 100.0, 1)
                consumer_rows.append({
                    "module": mod_id,
                    "demanded": needed,
                    "allocated": got,
                    "deficit": round(max(0.0, needed - got), 2),
                    "satisfaction_pct": sat_pct,
                    "priority_weight": weights.get(mod_id, 0.5),
                })

                if got < needed:
                    action = (
                        "Shed / Deferred"
                        if sat_pct < 30.0
                        else "Throttled / Partial Rationing"
                    )
                    tradeoffs.append({
                        "resource": res.name,
                        "module": mod_id,
                        "decision": action,
                        "satisfaction_pct": sat_pct,
                        "reason": (
                            f"Under '{strategy.replace('_', ' ')}' policy, {res.name} "
                            f"was prioritized for higher-criticality modules."
                        ),
                    })

            resource_allocations.append({
                "resource_id": res_id,
                "resource_name": res.name,
                "unit": res.unit,
                "available": res.available_capacity,
                "demanded": res.total_demand,
                "shortage": round(shortage, 2),
                "consumers": consumer_rows,
            })

        return {
            "strategy": strategy,
            "resource_allocations": resource_allocations,
            "constraint_tradeoffs": tradeoffs,
        }
