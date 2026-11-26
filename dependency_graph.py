"""
OMNIS-X Dependency Graph Engine
Maps inter-module dependencies, propagation waves, and compound crisis scenarios.
"""
from collections import deque
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# INTER-MODULE DEPENDENCY MAP
# key = module_id -> list of module_ids it depends on
# ─────────────────────────────────────────────────────────────────────────────
MODULE_DEPENDENCIES: dict[str, list[str]] = {
    "power": [],
    "network": ["power"],
    "academic": ["network", "faculty"],
    "faculty": ["network", "academic"],
    "student": ["network", "academic"],
    "classroom": ["power", "network", "academic"],
    "laboratory": ["power", "network", "academic", "classroom"],
    "examination": ["academic", "faculty", "classroom", "network"],
    "transportation": ["network", "power"],
    "hostel": ["power", "network"],
    "placement": ["network", "academic", "student", "classroom"],
    "events": ["power", "network", "academic", "classroom"],
    "administration": ["network", "academic", "faculty", "student"],
}

# ─────────────────────────────────────────────────────────────────────────────
# CASCADING IMPACT WEIGHTS
# How much does a failure in module A impact module B? (0-1 scale)
# ─────────────────────────────────────────────────────────────────────────────
IMPACT_WEIGHTS: dict[str, dict[str, float]] = {
    "power": {
        "network": 0.95,
        "classroom": 0.90,
        "laboratory": 0.95,
        "hostel": 0.85,
        "transportation": 0.60,
        "examination": 0.90,
        "events": 0.80,
    },
    "network": {
        "academic": 0.80,
        "faculty": 0.70,
        "student": 0.75,
        "examination": 0.85,
        "placement": 0.90,
        "administration": 0.80,
        "events": 0.60,
        "hostel": 0.50,
    },
    "academic": {
        "examination": 0.95,
        "faculty": 0.60,
        "student": 0.70,
        "placement": 0.65,
        "events": 0.55,
        "administration": 0.70,
    },
    "faculty": {
        "academic": 0.80,
        "examination": 0.85,
        "laboratory": 0.75,
        "classroom": 0.70,
    },
    "classroom": {
        "examination": 0.80,
        "events": 0.70,
        "placement": 0.65,
        "academic": 0.60,
    },
    "laboratory": {
        "academic": 0.50,
        "examination": 0.45,
        "placement": 0.55,
    },
    "transportation": {
        "hostel": 0.40,
        "student": 0.55,
        "faculty": 0.45,
        "events": 0.35,
    },
    "hostel": {
        "student": 0.60,
        "academic": 0.40,
        "examination": 0.50,
    },
    "examination": {
        "academic": 0.70,
        "student": 0.80,
        "administration": 0.75,
        "faculty": 0.60,
    },
    "placement": {
        "student": 0.65,
        "administration": 0.50,
        "events": 0.40,
    },
    "events": {
        "student": 0.40,
        "academic": 0.35,
    },
    "administration": {
        "academic": 0.55,
        "faculty": 0.60,
        "student": 0.50,
    },
}

MODULE_CRITICALITY: dict[str, float] = {
    "power": 1.0,
    "network": 0.95,
    "academic": 0.90,
    "examination": 0.95,
    "faculty": 0.85,
    "student": 0.80,
    "laboratory": 0.75,
    "classroom": 0.75,
    "administration": 0.80,
    "hostel": 0.70,
    "transportation": 0.65,
    "placement": 0.60,
    "events": 0.45,
}

DISRUPTION_IMPACT_MAP: dict[str, dict[str, Any]] = {
    "power_outage": {
        "primary": ["power"],
        "cascade_path": ["network", "classroom", "laboratory", "hostel", "examination", "events"],
        "severity_multiplier": 1.5,
        "students_affected_pct": 0.95,
        "faculty_affected_pct": 0.90,
    },
    "network_failure": {
        "primary": ["network"],
        "cascade_path": ["academic", "examination", "placement", "administration", "student"],
        "severity_multiplier": 1.3,
        "students_affected_pct": 0.80,
        "faculty_affected_pct": 0.75,
    },
    "faculty_absence": {
        "primary": ["faculty"],
        "cascade_path": ["academic", "examination", "laboratory"],
        "severity_multiplier": 0.9,
        "students_affected_pct": 0.40,
        "faculty_affected_pct": 0.15,
    },
    "lab_equipment_failure": {
        "primary": ["laboratory"],
        "cascade_path": ["academic", "examination", "placement"],
        "severity_multiplier": 0.8,
        "students_affected_pct": 0.30,
        "faculty_affected_pct": 0.20,
    },
    "transport_breakdown": {
        "primary": ["transportation"],
        "cascade_path": ["student", "faculty", "hostel"],
        "severity_multiplier": 0.7,
        "students_affected_pct": 0.35,
        "faculty_affected_pct": 0.25,
    },
    "exam_system_failure": {
        "primary": ["examination"],
        "cascade_path": ["academic", "student", "administration"],
        "severity_multiplier": 1.4,
        "students_affected_pct": 0.70,
        "faculty_affected_pct": 0.50,
    },
    "hostel_facility_failure": {
        "primary": ["hostel"],
        "cascade_path": ["student", "academic", "examination"],
        "severity_multiplier": 0.85,
        "students_affected_pct": 0.45,
        "faculty_affected_pct": 0.05,
    },
    "classroom_unavailability": {
        "primary": ["classroom"],
        "cascade_path": ["academic", "examination", "events", "placement"],
        "severity_multiplier": 0.9,
        "students_affected_pct": 0.60,
        "faculty_affected_pct": 0.55,
    },
    "placement_portal_down": {
        "primary": ["placement"],
        "cascade_path": ["student", "administration"],
        "severity_multiplier": 0.75,
        "students_affected_pct": 0.25,
        "faculty_affected_pct": 0.10,
    },
    "event_cancellation": {
        "primary": ["events"],
        "cascade_path": ["student", "academic"],
        "severity_multiplier": 0.5,
        "students_affected_pct": 0.15,
        "faculty_affected_pct": 0.10,
    },
    "water_supply_failure": {
        "primary": ["hostel"],
        "cascade_path": ["student", "events", "academic"],
        "severity_multiplier": 0.95,
        "students_affected_pct": 0.50,
        "faculty_affected_pct": 0.30,
    },
    "cafeteria_failure": {
        "primary": ["hostel"],
        "cascade_path": ["student", "faculty"],
        "severity_multiplier": 0.70,
        "students_affected_pct": 0.40,
        "faculty_affected_pct": 0.35,
    },
    "security_breach": {
        "primary": ["administration"],
        "cascade_path": ["student", "faculty", "examination", "hostel"],
        "severity_multiplier": 1.2,
        "students_affected_pct": 0.80,
        "faculty_affected_pct": 0.70,
    },
    "admin_system_failure": {
        "primary": ["administration"],
        "cascade_path": ["academic", "faculty", "student"],
        "severity_multiplier": 0.85,
        "students_affected_pct": 0.50,
        "faculty_affected_pct": 0.60,
    },
    "library_outage": {
        "primary": ["academic"],
        "cascade_path": ["student", "examination", "faculty"],
        "severity_multiplier": 0.65,
        "students_affected_pct": 0.35,
        "faculty_affected_pct": 0.30,
    },
}

# Pre-configured multi-disruption stress scenarios
PRESET_SCENARIOS: dict[str, dict[str, Any]] = {
    "exam_blackout": {
        "id": "exam_blackout",
        "name": "End-Sem Exam Grid Blackout",
        "description": "Main grid fails during morning end-semester exams while CBT exam servers stall.",
        "recommended_strategy": "exam_continuity",
        "events": [
            {"disruption_type": "power_outage", "severity": "critical"},
            {"disruption_type": "exam_system_failure", "severity": "high"},
        ],
    },
    "placement_cyber_crash": {
        "id": "placement_cyber_crash",
        "name": "Placement Drive Network Crash",
        "description": "Campus fiber & placement portal fail simultaneously on peak Day-1 recruitment.",
        "recommended_strategy": "placement_campus",
        "events": [
            {"disruption_type": "network_failure", "severity": "critical"},
            {"disruption_type": "placement_portal_down", "severity": "high"},
        ],
    },
    "monsoon_campus_crisis": {
        "id": "monsoon_campus_crisis",
        "name": "Monsoon Storm Multi-System Crisis",
        "description": "Heavy storm disrupts bus routes, trips campus substation, and halts hostel water.",
        "recommended_strategy": "life_safety",
        "events": [
            {"disruption_type": "transport_breakdown", "severity": "high"},
            {"disruption_type": "power_outage", "severity": "medium"},
            {"disruption_type": "water_supply_failure", "severity": "high"},
        ],
    },
    "lab_safety_staff_crunch": {
        "id": "lab_safety_staff_crunch",
        "name": "Lab Safety + Faculty Crunch",
        "description": "Lab ventilation/safety interlock fails alongside acute faculty shortage during practicals.",
        "recommended_strategy": "life_safety",
        "events": [
            {"disruption_type": "lab_equipment_failure", "severity": "critical"},
            {"disruption_type": "faculty_absence", "severity": "high"},
        ],
    },
}


class DependencyGraph:
    """Manages the institutional dependency graph"""

    def __init__(self):
        self.dependencies = MODULE_DEPENDENCIES
        self.impact_weights = IMPACT_WEIGHTS
        self.criticality = MODULE_CRITICALITY

    def get_downstream_modules(
        self, module_id: str, visited: set[str] | None = None
    ) -> list[str]:
        """Get all modules that depend (directly/indirectly) on the given module"""
        if visited is None:
            visited = set()
        result = []
        for mod, deps in self.dependencies.items():
            if module_id in deps and mod not in visited:
                visited.add(mod)
                result.append(mod)
                result.extend(self.get_downstream_modules(mod, visited))
        return list(set(result))

    def get_upstream_modules(self, module_id: str) -> list[str]:
        """Get all modules this module depends on"""
        return self.dependencies.get(module_id, [])

    def compute_cascade_trace(
        self, source_module: str, health_drop: float
    ) -> tuple[dict[str, float], list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Compute wave-by-wave cascading health drops from source_module.
        Returns (drops_map, waves, edges).
        """
        cascade: dict[str, float] = {}
        edges: list[dict[str, Any]] = []
        waves: list[dict[str, Any]] = [
            {
                "wave": 0,
                "label": "Origin Failure",
                "modules": [{"module": source_module, "drop": round(health_drop, 2)}],
            }
        ]

        visited: set[str] = {source_module}
        queue: deque[tuple[int, str, str, float, float]] = deque()

        for target, w in self.impact_weights.get(source_module, {}).items():
            drop = health_drop * w
            if drop >= 3.0:
                queue.append((1, source_module, target, drop, w))

        wave_buckets: dict[int, dict[str, float]] = {}

        while queue:
            wave_idx, parent, target, impact, weight = queue.popleft()
            if target in visited or wave_idx > 3:
                continue
            visited.add(target)

            capped = min(round(impact, 2), 95.0)
            cascade[target] = capped
            wave_buckets.setdefault(wave_idx, {})[target] = capped
            edges.append({
                "from": parent,
                "to": target,
                "wave": wave_idx,
                "weight": weight,
                "drop": capped,
            })

            attenuation = 0.40 if wave_idx == 1 else 0.30
            for next_mod, next_w in self.impact_weights.get(target, {}).items():
                if next_mod not in visited:
                    next_impact = capped * next_w * attenuation
                    if next_impact >= 4.0:
                        queue.append((wave_idx + 1, target, next_mod, next_impact, next_w))

        wave_labels = {
            1: "Direct Impact (Wave 1)",
            2: "Secondary Cascade (Wave 2)",
            3: "Tertiary Ripple (Wave 3)",
        }
        for w_idx in sorted(wave_buckets.keys()):
            waves.append({
                "wave": w_idx,
                "label": wave_labels.get(w_idx, f"Wave {w_idx}"),
                "modules": [
                    {"module": m, "drop": d}
                    for m, d in sorted(wave_buckets[w_idx].items(), key=lambda x: -x[1])
                ],
            })

        return cascade, waves, edges

    def compute_cascade_impact(self, source_module: str, health_drop: float) -> dict[str, float]:
        """Compute cascading health drops across modules when source loses health."""
        cascade, _, _ = self.compute_cascade_trace(source_module, health_drop)
        return cascade

    def get_critical_path(self, source: str, target: str) -> list[str]:
        """Find dependency path from source to target"""
        def dfs(current, goal, path, visited):
            if current == goal:
                return path
            for dep in self.get_downstream_modules(current):
                if dep not in visited:
                    visited.add(dep)
                    result = dfs(dep, goal, path + [dep], visited)
                    if result:
                        return result
            return None
        return dfs(source, target, [source], {source}) or []

    def get_module_risk_rank(self) -> list[tuple[str, float]]:
        """Rank modules by their failure risk impact on the whole system"""
        ranks = []
        for mod_id in self.dependencies:
            downstream = self.get_downstream_modules(mod_id)
            risk_score = self.criticality.get(mod_id, 0.5)
            risk_score += len(downstream) * 0.05
            ranks.append((mod_id, round(risk_score, 3)))
        return sorted(ranks, key=lambda x: -x[1])

    def to_graph_data(self) -> dict[str, Any]:
        """Export graph as nodes/edges for visualization"""
        nodes = []
        edges = []
        for mod_id, crit in self.criticality.items():
            nodes.append({
                "id": mod_id,
                "label": mod_id.replace("_", " ").title(),
                "criticality": crit,
                "group": self._get_group(mod_id),
                "downstream_count": len(self.get_downstream_modules(mod_id)),
            })
        for mod_id, deps in self.dependencies.items():
            for dep in deps:
                weight = self.impact_weights.get(dep, {}).get(mod_id, 0.5)
                edges.append({
                    "from": dep,
                    "to": mod_id,
                    "weight": weight,
                })
        return {"nodes": nodes, "edges": edges}

    def _get_group(self, mod_id: str) -> str:
        groups = {
            "power": "infrastructure",
            "network": "infrastructure",
            "academic": "academic",
            "faculty": "academic",
            "student": "academic",
            "classroom": "facility",
            "laboratory": "facility",
            "examination": "academic",
            "transportation": "facility",
            "hostel": "residential",
            "placement": "career",
            "events": "activities",
            "administration": "governance",
        }
        return groups.get(mod_id, "other")
