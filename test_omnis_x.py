"""
OMNIS-X Automated Unit & Integration Test Suite
Tests models, dependency graph, constraint solver, cascade simulator,
BFS outage tracer, 10C+5D+3B+2P schedule recovery, and Flask API endpoints.
"""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import app as flask_module
from backend.core.campus_store import load_campus_data
from backend.core.history_store import export_history_csv, list_history_records
from backend.core.institution_builder import build_institution
from backend.engines.cascade_simulator import CascadeSimulator
from backend.engines.conflict_detector import ConflictDetector
from backend.engines.constraint_engine import ConstraintEngine
from backend.engines.dataset_qa import answer_dataset_question, seed_initial_history_if_empty
from backend.engines.dependency_graph import (
    DISRUPTION_IMPACT_MAP,
    PRESET_SCENARIOS,
    DependencyGraph,
)
from backend.engines.recovery_planner import RecoveryPlanner
from backend.engines.schedule_solver import CampusScheduleSolver


class TestOmnisXCore(unittest.TestCase):
    def setUp(self):
        self.state = build_institution()

    def test_institution_initialization(self):
        self.assertEqual(len(self.state.modules), 13)
        self.assertEqual(len(self.state.constraints), 13)
        self.assertEqual(len(self.state.resources), 5)
        self.assertEqual(self.state.overall_health, 100.0)
        self.assertEqual(sum(1 for c in self.state.constraints if c.violated), 0)

    def test_dependency_graph_waves_and_risk(self):
        graph = DependencyGraph()
        downstream = graph.get_downstream_modules("power")
        self.assertIn("network", downstream)
        self.assertIn("examination", downstream)
        drops, waves, edges = graph.compute_cascade_trace("power", 90.0)
        self.assertGreater(len(waves), 1)
        self.assertGreater(len(edges), 0)
        self.assertGreater(drops["network"], 50.0)
        risk = graph.get_module_risk_rank()
        self.assertEqual(risk[0][0], "power")

    def test_all_disruption_types_simulate(self):
        for dtype in DISRUPTION_IMPACT_MAP:
            state = build_institution()
            sim = CascadeSimulator(state)
            disruption, _drops = sim.simulate(dtype, "high")
            self.assertGreater(len(disruption.affected_modules), 0)
            self.assertLess(state.overall_health, 100.0)
            self.assertGreater(len(disruption.cascade_waves), 0)

    def test_constraint_violations_and_competing_strategies(self):
        sim = CascadeSimulator(self.state)
        disruption, _ = sim.simulate("power_outage", "critical")
        c_summary = ConstraintEngine(self.state).evaluate_all()
        self.assertGreater(c_summary["violated_count"], 0)
        self.assertGreater(c_summary["hard_violations"], 0)

        planner = RecoveryPlanner(self.state)
        plan_exam = planner.generate_plan(disruption, strategy="exam_continuity")
        plan_safety = planner.replan_with_strategy(plan_exam.id, "life_safety")

        exam_alloc_map = {
            r["resource_id"]: {c["module"]: c["satisfaction_pct"] for c in r["consumers"]}
            for r in planner.generate_plan(disruption, strategy="exam_continuity").resource_allocations
        }
        safety_alloc_map = {
            r["resource_id"]: {c["module"]: c["satisfaction_pct"] for c in r["consumers"]}
            for r in plan_safety.resource_allocations
        }
        self.assertGreaterEqual(
            exam_alloc_map["power_kw"]["examination"],
            safety_alloc_map["power_kw"]["examination"],
        )
        self.assertGreaterEqual(
            safety_alloc_map["power_kw"]["hostel"],
            exam_alloc_map["power_kw"]["hostel"],
        )

    def test_conflict_detection_and_plan_execution(self):
        sim = CascadeSimulator(self.state)
        disruption, _ = sim.simulate("power_outage", "critical")
        detector = ConflictDetector(self.state)
        conflicts = detector.detect_all_conflicts()
        self.assertGreater(len(conflicts), 3)

        planner = RecoveryPlanner(self.state)
        plan = planner.generate_plan(disruption, strategy="exam_continuity")
        health_before = self.state.overall_health
        exec_res = planner.execute_plan(plan.id)
        self.assertGreater(exec_res["health_after"], health_before)
        self.assertEqual(plan.overall_status, "completed")
        self.assertEqual(len(self.state.active_disruptions), 0)


class TestBlueprintScheduleSolver(unittest.TestCase):
    def setUp(self):
        self.twin = load_campus_data(sync_sqlite=True)
        self.solver = CampusScheduleSolver(self.twin)

    def test_sqlite_store_synced(self):
        db_path = Path(__file__).resolve().parent.parent / "data" / "campus_twin.db"
        self.assertTrue(db_path.exists())
        with closing(sqlite3.connect(db_path)) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        self.assertEqual(cnt, len(self.twin.activities))

    def test_block_b_demo_and_time_window_rule(self):
        report = self.solver.simulate_outage("BLOCK_B", "09:00", "12:00", "power_outage")
        counts = report["impact_counts"]
        self.assertEqual(counts["classes"], 6)
        self.assertEqual(counts["labs"], 2)
        self.assertEqual(counts["exams"], 1)
        self.assertEqual(counts["students"], 180)
        self.assertEqual(counts["faculty"], 8)
        self.assertEqual(counts["hard_conflicts_after_recovery"], 0)

        # Outage only affects activities in its time window (ACT009 at 14:00-15:00 in B201 is unaffected)
        affected_ids = {a["id"] for a in report["affected_activities"]}
        outside_ids = {u["id"] for u in report["unaffected_outside_window"]}
        self.assertIn("ACT001", affected_ids)
        self.assertNotIn("ACT009", affected_ids)
        self.assertIn("ACT009", outside_ids)

        # Verify Score = 10C + 5D + 3B + 2P ranking & no undersized A201 assignment
        options = report["ranked_recovery_options"]
        self.assertGreater(len(options), 1)
        self.assertLessEqual(options[0]["score"], options[1]["score"])
        best_opt = options[0]
        for assign in best_opt["assignments"]:
            self.assertNotEqual(assign["new_room_id"], "A201")
        rejected_reasons = [r["rejection_reason"] for r in best_opt["rejected_candidates"]]
        self.assertTrue(any(r.startswith("H3:") for r in rejected_reasons))

    def test_busy_faculty_rejected(self):
        # F001 absent 09:00-12:00; F010 teaches ACT010 at 09:00-10:00 so must be rejected for 09:00-11:00
        report = self.solver.simulate_outage("F001", "09:00", "12:00", "faculty_unavailable")
        best_opt = report["ranked_recovery_options"][0]
        self.assertTrue(best_opt["feasible"])
        assigned = best_opt["assignments"][0]
        self.assertNotEqual(assigned["new_faculty_id"], "F001")
        rejected_reasons = [r["rejection_reason"] for r in best_opt["rejected_candidates"]]
        self.assertTrue(any("F010" in r and r.startswith("H2:") for r in rejected_reasons))

    def test_no_valid_replacement_flagged_unresolved(self):
        # LAB_C2 is the only room with cryo_chamber; outage across full day 08:00-19:00 leaves ACT011 unresolved
        report = self.solver.simulate_outage("LAB_C2", "08:00", "19:00", "equipment_failure")
        best_opt = report["ranked_recovery_options"][0]
        self.assertFalse(best_opt["feasible"])
        self.assertGreater(best_opt["hard_conflicts"], 0)
        unresolved_ids = {u["activity_id"] for u in best_opt["unresolved_activities"]}
        self.assertIn("ACT011", unresolved_ids)


class TestOmnisXAPI(unittest.TestCase):
    def setUp(self):
        self.client = flask_module.app.test_client()
        self.client.post("/api/reset")

    def test_clean_reset_repeatability_and_outage_apply(self):
        # Run the exact Block B demo from a clean reset twice to guarantee repeatability (Slide 15)
        for _ in range(2):
            self.assertEqual(self.client.post("/api/reset").status_code, 200)
            res = self.client.post(
                "/api/simulate-outage",
                json={"target_id": "BLOCK_B", "start_time": "09:00", "end_time": "12:00"},
            )
            self.assertEqual(res.status_code, 200)
            rep = res.get_json()["outage_report"]
            self.assertEqual(rep["impact_counts"]["classes"], 6)
            self.assertEqual(rep["impact_counts"]["labs"], 2)
            self.assertEqual(rep["impact_counts"]["exams"], 1)
            self.assertEqual(rep["impact_counts"]["students"], 180)
            self.assertEqual(rep["impact_counts"]["faculty"], 8)

            opt_id = rep["recommended_option_id"]
            apply_res = self.client.post(f"/api/recovery-options/{opt_id}/apply")
            self.assertEqual(apply_res.status_code, 200)
            apply_json = apply_res.get_json()
            self.assertEqual(apply_json["applied"]["hard_conflicts_after_recovery"], 0)
            self.assertEqual(apply_json["state"]["open_problems_count"], 0)
            self.assertEqual(apply_json["state"]["overall_health"], 100.0)

    def test_full_api_lifecycle(self):
        res = self.client.get("/api/state")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["overall_health"], 100.0)

        self.assertEqual(self.client.get("/api/campus-twin").status_code, 200)

        res = self.client.post(
            "/api/simulate",
            json={
                "disruption_type": "network_failure",
                "severity": "critical",
                "strategy": "placement_campus",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        plan_id = data["recovery_plan_id"]
        self.assertGreater(data["conflicts_detected"], 0)

        res = self.client.get("/api/constraints")
        self.assertEqual(res.status_code, 200)
        self.assertGreater(res.get_json()["summary"]["violated_count"], 0)

        res = self.client.put(
            f"/api/recovery-plans/{plan_id}/strategy",
            json={"strategy": "exam_continuity"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["plan"]["strategy"], "exam_continuity")

        res = self.client.post(f"/api/recovery-plans/{plan_id}/execute")
        self.assertEqual(res.status_code, 200)
        exec_data = res.get_json()
        self.assertGreater(exec_data["execution"]["health_after"], exec_data["execution"]["health_before"])

        res = self.client.get("/api/scenarios")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["scenarios"]), len(PRESET_SCENARIOS))

        res = self.client.post("/api/scenarios/exam_blackout/run", json={})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        self.assertEqual(self.client.get("/api/graph").status_code, 200)
        self.assertEqual(self.client.get("/api/analytics").status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_problem_solver_surfaces_and_fixes_unresolved_and_deficits(self):
        self.client.post("/api/reset")
        sim = self.client.post(
            "/api/simulate-outage",
            json={
                "target_id": "LAB_C2",
                "start_time": "08:00",
                "end_time": "19:00",
                "outage_type": "equipment_failure",
            },
        )
        self.assertEqual(sim.status_code, 200)

        prob_res = self.client.get("/api/problems")
        self.assertEqual(prob_res.status_code, 200)
        problems = prob_res.get_json()["problems"]
        unres = next((p for p in problems if p["id"] == "UNRES-ACT011"), None)
        self.assertIsNotNone(unres)
        assert unres is not None
        self.assertIn("how_to_solve", unres)

        fix_res = self.client.post(
            "/api/problems/solve",
            json={
                "solve_type": "unresolved_activity",
                "target_id": "ACT011",
                "mode": "compensatory_slot",
            },
        )
        self.assertEqual(fix_res.status_code, 200)
        fix_data = fix_res.get_json()
        self.assertTrue(fix_data["success"])
        self.assertEqual(
            fix_data["outage_report"]["impact_counts"]["hard_conflicts_after_recovery"],
            0,
        )

        solve_all_res = self.client.post("/api/problems/solve-all")
        self.assertEqual(solve_all_res.status_code, 200)
        all_data = solve_all_res.get_json()
        self.assertEqual(all_data["open_problems_count"], 0)
        self.assertGreaterEqual(all_data["state"]["overall_health"], 95.0)

    def test_historical_dataset_qa_store_and_reports_api(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_db = Path(tmpdir) / "test_hist.db"
            twin = load_campus_data(sync_sqlite=False)
            state = build_institution()
            graph = DependencyGraph()
            seed_initial_history_if_empty(state, twin, graph, db_path=temp_db)
            rec = answer_dataset_question(
                "How many students, rooms and sessions are in the dataset?",
                state,
                twin,
                None,
                graph,
                persist=True,
                db_path=temp_db,
            )
            self.assertEqual(rec["event_type"], "question_answered")
            listed = list_history_records(limit=10, db_path=temp_db)
            self.assertEqual(listed["summary"]["total_records"], 3)
            csv_txt = export_history_csv(db_path=temp_db)
            self.assertIn("question_answered", csv_txt)

        # Verify live Flask Reports endpoints preserve quantitative answers across sim -> recover
        self.client.post(
            "/api/simulate-outage",
            json={"target_id": "BLOCK_B", "start_time": "09:00", "end_time": "12:00"},
        )
        ask_res = self.client.post(
            "/api/reports/dataset-history/ask",
            json={"question": "Which students and sessions are currently affected?"},
        )
        self.assertEqual(ask_res.status_code, 200)
        ask_json = ask_res.get_json()
        self.assertTrue(ask_json["success"])
        self.assertEqual(ask_json["record"]["students_affected"], 180)
        self.assertEqual(ask_json["record"]["activities_impacted"], 9)

        hist_res = self.client.get("/api/reports/dataset-history")
        self.assertEqual(hist_res.status_code, 200)
        hist_json = hist_res.get_json()
        self.assertGreater(hist_json["summary"]["total_records"], 0)
        self.assertGreater(len(hist_json["questions_catalog"]), 0)

        csv_res = self.client.get("/api/reports/dataset-history/export?format=csv")
        self.assertEqual(csv_res.status_code, 200)
        self.assertIn("text/csv", csv_res.content_type)
        self.client.post("/api/reset")


if __name__ == "__main__":
    unittest.main(verbosity=2)
