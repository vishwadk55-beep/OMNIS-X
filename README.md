# OMNIS-X — Smart Campus Digital Twin & Crisis Recovery System

> **A college that cannot afford a single operational failure.**  
> **Detect disruption. Trace impact. Recover operations.**

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Verify code quality, type safety, and all test cases
python -m ruff check .
python -m flake8 .
python -m pyright .
python test_system.py
python -m unittest tests/test_omnis_x.py -v

# 3. Run the web application
python app.py

# 4. Open browser
http://localhost:5000
```

---

## 5-Layer Architecture

1. **Campus Data Layer** ([data/campus_data.json](data/campus_data.json), [backend/core/campus_store.py](backend/core/campus_store.py))
   - Structured JSON records synced automatically to SQLite (`data/campus_twin.db`) covering Power Zones (`POWER_A`, `POWER_B`, `POWER_C`, `POWER_S`), Buildings (`BLOCK_A`, `BLOCK_B`, `BLOCK_C`, `HOSTEL_H1`, `ADMIN_BLDG`), Rooms & Labs (`B101`–`B301`, `LAB001`, `LAB002`, `A101`–`A301`, `C101`–`C103`, `LAB_A1`, `LAB_C1`, `LAB_C2`), Faculty (`F001`–`F012`), Batches (`CSE_A`–`CIVIL_A`), and Activities (`ACT001`–`ACT011`, `EXAM01`, `PLC001`, `EVT001`).
2. **Digital Twin + Dependency Graph** ([backend/core/institution_builder.py](backend/core/institution_builder.py), [backend/engines/dependency_graph.py](backend/engines/dependency_graph.py))
   - Directed entity graph (`POWER_B -> BLOCK_B -> LAB001 -> ACT001 (AI Lab) -> CSE_A & F001`) plus the 13-module institutional dependency network across Teaching & Learning, Campus Services, and Institution Operations.
3. **Analysis Engines** ([backend/engines/schedule_solver.py](backend/engines/schedule_solver.py), [backend/engines/cascade_simulator.py](backend/engines/cascade_simulator.py), [backend/engines/conflict_detector.py](backend/engines/conflict_detector.py))
   - 6-step BFS outage traversal with strict time-window overlap checks.
   - Separates **Hard Constraints** (no room double-booking, no faculty/batch overlap, `capacity >= students`, required equipment & resource availability) from **Soft Constraints**.
4. **Recovery Engine** ([backend/engines/schedule_solver.py](backend/engines/schedule_solver.py), [backend/engines/constraint_engine.py](backend/engines/constraint_engine.py), [backend/engines/recovery_planner.py](backend/engines/recovery_planner.py))
   - Rejects any candidate breaking a hard constraint, flags activities without valid substitutes as `UNRESOLVED`, and ranks valid plans using:
     $$\text{Score} = 10C + 5D + 3B + 2P$$
     (lowest score wins, where `C` = activities changed, `D` = total delay in hours, `B` = building changes, `P` = preference violations).
5. **6-Page Command Dashboard** ([frontend/templates/index.html](frontend/templates/index.html))
   - `01 Overview` • `02 Digital Twin` • `03 Conflicts` • `04 Simulator` • `05 Recovery` • `06 Reports`
   - Includes a one-click **Block B Power Failure Demo (`09:00–12:00`)** calculating exact counts dynamically (`6 classes, 2 labs, 1 exam, 180 students, 8 faculty, 0 hard conflicts after recovery`).
