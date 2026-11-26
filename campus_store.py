"""
OMNIS-X Campus Data Store (Layer 1: Campus Data)
Loads structured campus resources, people, and scheduled activities from JSON and syncs to SQLite.
"""
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PowerZone:
    id: str
    name: str
    capacity_kw: float
    status: str = "operational"
    backup_generator: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "capacity_kw": self.capacity_kw,
            "status": self.status,
            "backup_generator": self.backup_generator,
        }


@dataclass
class Building:
    id: str
    name: str
    power_zone_id: str
    distance_group: int = 1
    status: str = "operational"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "power_zone_id": self.power_zone_id,
            "distance_group": self.distance_group,
            "status": self.status,
        }


@dataclass
class Room:
    id: str
    name: str
    building_id: str
    room_type: str
    capacity: int
    equipment: list[str] = field(default_factory=list)
    status: str = "operational"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "building_id": self.building_id,
            "room_type": self.room_type,
            "capacity": self.capacity,
            "equipment": self.equipment,
            "status": self.status,
        }


@dataclass
class FacultyMember:
    id: str
    name: str
    department: str
    max_hours: int = 18
    status: str = "available"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "department": self.department,
            "max_hours": self.max_hours,
            "status": self.status,
        }


@dataclass
class StudentBatch:
    id: str
    name: str
    department: str
    student_count: int
    student_set: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "department": self.department,
            "student_count": self.student_count,
            "student_set": self.student_set,
        }


@dataclass
class CampusActivity:
    id: str
    title: str
    activity_type: str
    domain: str
    faculty_id: str
    batch_id: str
    room_id: str
    start_time: str
    end_time: str
    required_equipment: list[str] = field(default_factory=list)
    priority: int = 2
    status: str = "scheduled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "activity_type": self.activity_type,
            "domain": self.domain,
            "faculty_id": self.faculty_id,
            "batch_id": self.batch_id,
            "room_id": self.room_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "required_equipment": self.required_equipment,
            "priority": self.priority,
            "status": self.status,
        }


@dataclass
class CampusTwinData:
    power_zones: dict[str, PowerZone] = field(default_factory=dict)
    buildings: dict[str, Building] = field(default_factory=dict)
    rooms: dict[str, Room] = field(default_factory=dict)
    faculty: dict[str, FacultyMember] = field(default_factory=dict)
    batches: dict[str, StudentBatch] = field(default_factory=dict)
    activities: list[CampusActivity] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "power_zones": [z.to_dict() for z in self.power_zones.values()],
            "buildings": [b.to_dict() for b in self.buildings.values()],
            "rooms": [r.to_dict() for r in self.rooms.values()],
            "faculty": [f.to_dict() for f in self.faculty.values()],
            "batches": [b.to_dict() for b in self.batches.values()],
            "activities": [a.to_dict() for a in self.activities],
            "entity_graph": self.build_entity_graph(),
        }

    def build_entity_graph(self) -> dict[str, Any]:
        """Build directed resource -> building -> room -> activity -> people graph."""
        nodes: list[dict[str, str]] = []
        edges: list[dict[str, str]] = []

        for z in self.power_zones.values():
            nodes.append({"id": z.id, "label": z.name, "kind": "power_zone", "status": z.status})
        for b in self.buildings.values():
            nodes.append({"id": b.id, "label": b.name, "kind": "building", "status": b.status})
            edges.append({"from": b.power_zone_id, "to": b.id, "relation": "powers"})
        for r in self.rooms.values():
            nodes.append({"id": r.id, "label": r.name, "kind": r.room_type, "status": r.status})
            edges.append({"from": r.building_id, "to": r.id, "relation": "contains"})
        for f in self.faculty.values():
            nodes.append({"id": f.id, "label": f.name, "kind": "faculty", "status": f.status})
        for batch in self.batches.values():
            nodes.append({"id": batch.id, "label": batch.name, "kind": "batch", "status": "operational"})
        for act in self.activities:
            nodes.append({"id": act.id, "label": act.title, "kind": act.activity_type, "status": act.status})
            edges.append({"from": act.room_id, "to": act.id, "relation": "hosts"})
            edges.append({"from": act.faculty_id, "to": act.id, "relation": "teaches"})
            edges.append({"from": act.id, "to": act.batch_id, "relation": "impacts_batch"})
            edges.append({"from": act.id, "to": act.faculty_id, "relation": "impacts_faculty"})

        return {"nodes": nodes, "edges": edges}


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data"


def load_campus_data(
    json_path: Path | None = None,
    sync_sqlite: bool = True,
) -> CampusTwinData:
    """Load structured campus dataset from JSON and persist a synchronized SQLite copy."""
    data_dir = _default_data_dir()
    src = json_path or (data_dir / "campus_data.json")
    raw = json.loads(src.read_text(encoding="utf-8"))

    twin = CampusTwinData(
        power_zones={z["id"]: PowerZone(**z) for z in raw.get("power_zones", [])},
        buildings={b["id"]: Building(**b) for b in raw.get("buildings", [])},
        rooms={r["id"]: Room(**r) for r in raw.get("rooms", [])},
        faculty={f["id"]: FacultyMember(**f) for f in raw.get("faculty", [])},
        batches={b["id"]: StudentBatch(**b) for b in raw.get("batches", [])},
        activities=[CampusActivity(**a) for a in raw.get("activities", [])],
    )

    if sync_sqlite:
        _sync_to_sqlite(twin, data_dir / "campus_twin.db")

    return twin


def _sync_to_sqlite(twin: CampusTwinData, db_path: Path) -> None:
    """Persist the campus digital twin tables to SQLite for local querying."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn, conn:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS power_zones "
            "(id TEXT PRIMARY KEY, name TEXT, capacity_kw REAL, status TEXT, backup_generator INTEGER)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS buildings "
            "(id TEXT PRIMARY KEY, name TEXT, power_zone_id TEXT, distance_group INTEGER, status TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS rooms "
            "(id TEXT PRIMARY KEY, name TEXT, building_id TEXT, room_type TEXT, "
            "capacity INTEGER, equipment TEXT, status TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS faculty "
            "(id TEXT PRIMARY KEY, name TEXT, department TEXT, max_hours INTEGER, status TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS batches "
            "(id TEXT PRIMARY KEY, name TEXT, department TEXT, student_count INTEGER, student_set TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS activities "
            "(id TEXT PRIMARY KEY, title TEXT, activity_type TEXT, domain TEXT, faculty_id TEXT, "
            "batch_id TEXT, room_id TEXT, start_time TEXT, end_time TEXT, "
            "required_equipment TEXT, priority INTEGER, status TEXT)"
        )

        cur.execute("DELETE FROM power_zones")
        cur.executemany(
            "INSERT INTO power_zones VALUES (?, ?, ?, ?, ?)",
            [
                (z.id, z.name, z.capacity_kw, z.status, int(z.backup_generator))
                for z in twin.power_zones.values()
            ],
        )
        cur.execute("DELETE FROM buildings")
        cur.executemany(
            "INSERT INTO buildings VALUES (?, ?, ?, ?, ?)",
            [(b.id, b.name, b.power_zone_id, b.distance_group, b.status) for b in twin.buildings.values()],
        )
        cur.execute("DELETE FROM rooms")
        cur.executemany(
            "INSERT INTO rooms VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (r.id, r.name, r.building_id, r.room_type, r.capacity, json.dumps(r.equipment), r.status)
                for r in twin.rooms.values()
            ],
        )
        cur.execute("DELETE FROM faculty")
        cur.executemany(
            "INSERT INTO faculty VALUES (?, ?, ?, ?, ?)",
            [(f.id, f.name, f.department, f.max_hours, f.status) for f in twin.faculty.values()],
        )
        cur.execute("DELETE FROM batches")
        cur.executemany(
            "INSERT INTO batches VALUES (?, ?, ?, ?, ?)",
            [(b.id, b.name, b.department, b.student_count, b.student_set) for b in twin.batches.values()],
        )
        cur.execute("DELETE FROM activities")
        cur.executemany(
            "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    a.id,
                    a.title,
                    a.activity_type,
                    a.domain,
                    a.faculty_id,
                    a.batch_id,
                    a.room_id,
                    a.start_time,
                    a.end_time,
                    json.dumps(a.required_equipment),
                    a.priority,
                    a.status,
                )
                for a in twin.activities
            ],
        )
