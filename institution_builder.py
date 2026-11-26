"""
OMNIS-X Institution Builder
Constructs the complete constraint-based digital twin of the engineering college
"""
from .models import (
    ConstraintPriority,
    InstitutionalConstraint,
    InstitutionalModule,
    InstitutionState,
    SharedResource,
    SubSystem,
)


def _build_constraints() -> list:
    """Create quantitative hard and soft constraints across all 13 modules."""
    constraints = [
        InstitutionalConstraint(
            id="CON-PWR-01",
            name="Exam Hall Power Continuity",
            module="power",
            metric="Power Availability",
            operator=">=",
            threshold=80.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["examination", "laboratory", "classroom", "hostel"],
            subsystem_id="power-gen",
            penalty_weight=1.0,
            description="Minimum 80% backup/grid power required to sustain exam halls and server rooms.",
        ),
        InstitutionalConstraint(
            id="CON-NET-01",
            name="ERP & LMS Uptime SLA",
            module="network",
            metric="Network Reliability",
            operator=">=",
            threshold=85.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["academic", "examination", "placement", "administration"],
            subsystem_id="net-erp",
            penalty_weight=0.95,
            description="Core campus ERP, LMS, and authentication services must stay >= 85% healthy.",
        ),
        InstitutionalConstraint(
            id="CON-ACAD-01",
            name="Academic Schedule Continuity",
            module="academic",
            metric="Timetable Execution",
            operator=">=",
            threshold=75.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["faculty", "classroom", "examination"],
            subsystem_id="acad-timetable",
            penalty_weight=0.9,
            description="Minimum 75% curriculum & lecture continuity required per AICTE academic calendar.",
        ),
        InstitutionalConstraint(
            id="CON-FAC-01",
            name="Invigilation & Teaching Coverage",
            module="faculty",
            metric="Faculty Availability",
            operator=">=",
            threshold=75.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["examination", "academic", "laboratory"],
            subsystem_id="fac-schedule",
            penalty_weight=0.9,
            description="At least 75% faculty availability required to satisfy 1:30 exam invigilation & 18 hr/wk cap.",
        ),
        InstitutionalConstraint(
            id="CON-STU-01",
            name="Student Services & Portal Access",
            module="student",
            metric="Portal & Welfare Health",
            operator=">=",
            threshold=70.0,
            unit="%",
            priority=ConstraintPriority.SOFT,
            competing_modules=["network", "examination", "hostel"],
            subsystem_id="stu-portal",
            penalty_weight=0.75,
            description="Student portal, biometrics, and grievance response channels must remain >= 70% healthy.",
        ),
        InstitutionalConstraint(
            id="CON-CLS-01",
            name="Classroom Capacity & Smart Readiness",
            module="classroom",
            metric="Usable Room Capacity",
            operator=">=",
            threshold=75.0,
            unit="%",
            priority=ConstraintPriority.SOFT,
            competing_modules=["examination", "academic", "placement", "events"],
            subsystem_id="class-alloc",
            penalty_weight=0.8,
            description="At least 75% classroom capacity required to avoid exam vs lecture vs placement collisions.",
        ),
        InstitutionalConstraint(
            id="CON-LAB-01",
            name="Laboratory Life-Safety Interlock",
            module="laboratory",
            metric="Lab Safety Integrity",
            operator=">=",
            threshold=85.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["power", "academic"],
            subsystem_id="lab-safety",
            penalty_weight=1.0,
            description="Zero-compromise lab ventilation, chemical containment, and electrical interlock >= 85%.",
        ),
        InstitutionalConstraint(
            id="CON-EXM-01",
            name="Zero-Failure Examination Integrity",
            module="examination",
            metric="Exam System Readiness",
            operator=">=",
            threshold=85.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["power", "network", "faculty", "classroom", "events"],
            subsystem_id="exam-schedule",
            penalty_weight=1.0,
            description="Exams require >= 85% readiness across power, halls, invigilators, and question delivery.",
        ),
        InstitutionalConstraint(
            id="CON-TRN-01",
            name="Commuter Fleet Route Coverage",
            module="transportation",
            metric="Fleet Availability",
            operator=">=",
            threshold=75.0,
            unit="%",
            priority=ConstraintPriority.SOFT,
            competing_modules=["student", "faculty", "hostel"],
            subsystem_id="trans-fleet",
            penalty_weight=0.7,
            description="Minimum 75% fleet coverage so day-scholars and faculty reach campus before first period.",
        ),
        InstitutionalConstraint(
            id="CON-HST-01",
            name="Hostel Water, Mess & Medical Readiness",
            module="hostel",
            metric="Residential Habitability",
            operator=">=",
            threshold=80.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["power", "student", "cafeteria"],
            subsystem_id="hostel-water",
            penalty_weight=0.95,
            description="Uninterrupted water, safe mess operations, and <10 min medical response for residents.",
        ),
        InstitutionalConstraint(
            id="CON-PLC-01",
            name="Campus Placement Drive SLA",
            module="placement",
            metric="Recruitment Readiness",
            operator=">=",
            threshold=70.0,
            unit="%",
            priority=ConstraintPriority.SOFT,
            competing_modules=["network", "classroom", "examination"],
            subsystem_id="place-portal",
            penalty_weight=0.65,
            description="Placement portal and interview rooms must maintain >= 70% SLA during drive days.",
        ),
        InstitutionalConstraint(
            id="CON-EVT-01",
            name="Non-Exam Event Coexistence Rule",
            module="events",
            metric="Venue & Compliance Buffer",
            operator=">=",
            threshold=65.0,
            unit="%",
            priority=ConstraintPriority.SOFT,
            competing_modules=["examination", "classroom", "power"],
            subsystem_id="event-schedule",
            penalty_weight=0.45,
            description="Events yield priority to Examinations and Placements when rooms or power are constrained.",
        ),
        InstitutionalConstraint(
            id="CON-ADM-01",
            name="NAAC/AICTE Governance & Security",
            module="administration",
            metric="Compliance & Security Score",
            operator=">=",
            threshold=80.0,
            unit="%",
            priority=ConstraintPriority.HARD,
            competing_modules=["network", "academic", "faculty"],
            subsystem_id="admin-accred",
            penalty_weight=0.85,
            description="Regulatory records, payroll, and campus security systems must stay >= 80% operational.",
        ),
    ]
    for con in constraints:
        con.evaluate()
    return constraints


def _build_resources() -> dict:
    """Create shared finite institutional resources that modules compete for during disruptions."""
    return {
        "power_kw": SharedResource(
            id="power_kw",
            name="Electrical & Generator Power",
            unit="kW",
            nominal_capacity=1200.0,
            available_capacity=1200.0,
            owner_module="power",
            baseline_demand={
                "network": 180.0,
                "examination": 240.0,
                "laboratory": 260.0,
                "classroom": 190.0,
                "hostel": 200.0,
                "events": 70.0,
                "administration": 60.0,
            },
            allocated={
                "network": 180.0,
                "examination": 240.0,
                "laboratory": 260.0,
                "classroom": 190.0,
                "hostel": 200.0,
                "events": 70.0,
                "administration": 60.0,
            },
        ),
        "bandwidth_mbps": SharedResource(
            id="bandwidth_mbps",
            name="Campus Network Bandwidth",
            unit="Mbps",
            nominal_capacity=2000.0,
            available_capacity=2000.0,
            owner_module="network",
            baseline_demand={
                "examination": 450.0,
                "academic": 400.0,
                "placement": 350.0,
                "administration": 250.0,
                "student": 300.0,
                "laboratory": 150.0,
                "events": 100.0,
            },
            allocated={
                "examination": 450.0,
                "academic": 400.0,
                "placement": 350.0,
                "administration": 250.0,
                "student": 300.0,
                "laboratory": 150.0,
                "events": 100.0,
            },
        ),
        "rooms_count": SharedResource(
            id="rooms_count",
            name="Usable Halls & Classrooms",
            unit="rooms",
            nominal_capacity=60.0,
            available_capacity=60.0,
            owner_module="classroom",
            baseline_demand={
                "examination": 20.0,
                "academic": 22.0,
                "placement": 8.0,
                "events": 6.0,
                "laboratory": 4.0,
            },
            allocated={
                "examination": 20.0,
                "academic": 22.0,
                "placement": 8.0,
                "events": 6.0,
                "laboratory": 4.0,
            },
        ),
        "faculty_slots": SharedResource(
            id="faculty_slots",
            name="Active Faculty Coverage",
            unit="faculty",
            nominal_capacity=150.0,
            available_capacity=150.0,
            owner_module="faculty",
            baseline_demand={
                "examination": 45.0,
                "academic": 65.0,
                "laboratory": 25.0,
                "administration": 10.0,
                "placement": 5.0,
            },
            allocated={
                "examination": 45.0,
                "academic": 65.0,
                "laboratory": 25.0,
                "administration": 10.0,
                "placement": 5.0,
            },
        ),
        "transport_seats": SharedResource(
            id="transport_seats",
            name="Transit & Shuttle Capacity",
            unit="seats",
            nominal_capacity=1500.0,
            available_capacity=1500.0,
            owner_module="transportation",
            baseline_demand={
                "student": 1150.0,
                "faculty": 150.0,
                "hostel": 120.0,
                "events": 80.0,
            },
            allocated={
                "student": 1150.0,
                "faculty": 150.0,
                "hostel": 120.0,
                "events": 80.0,
            },
        ),
    }


def build_institution() -> InstitutionState:
    """Build and return a fully initialized institutional digital twin."""
    state = InstitutionState()

    power_module = InstitutionalModule(
        id="power",
        name="Power & Infrastructure",
        description="Electrical grid, generators, UPS systems, solar panels, and campus-wide power distribution",
        icon="⚡",
        critical_constraints=[
            "Minimum 80% power for exam halls",
            "Generator backup within 30 seconds",
            "Critical labs must have UPS coverage",
        ],
        subsystems=[
            SubSystem("power-grid", "Main Grid Connection", "power", dependencies=[]),
            SubSystem("power-gen", "Emergency Generators", "power", dependencies=["power-grid"]),
            SubSystem("power-ups", "UPS Systems", "power", dependencies=["power-gen"]),
            SubSystem("power-solar", "Solar Power Plant", "power", dependencies=[]),
            SubSystem("power-dist", "Distribution Panels", "power", dependencies=["power-grid", "power-solar"]),
        ],
    )

    network_module = InstitutionalModule(
        id="network",
        name="Network & IT Systems",
        description="Campus LAN, internet connectivity, servers, ERP, LMS, and digital services",
        icon="🌐",
        critical_constraints=[
            "99.9% uptime for ERP system",
            "Redundant internet via two ISPs",
            "LMS must be accessible 24/7",
        ],
        subsystems=[
            SubSystem("net-isp1", "Primary ISP", "network", dependencies=["power"]),
            SubSystem("net-isp2", "Backup ISP", "network", dependencies=["power"]),
            SubSystem("net-lan", "Campus LAN", "network", dependencies=["net-isp1", "power"]),
            SubSystem("net-wifi", "Wi-Fi Network", "network", dependencies=["net-lan"]),
            SubSystem("net-erp", "ERP System", "network", dependencies=["net-lan", "net-servers"]),
            SubSystem("net-lms", "Learning Management System", "network", dependencies=["net-lan", "net-servers"]),
            SubSystem("net-servers", "Campus Servers", "network", dependencies=["power", "net-lan"]),
            SubSystem("net-cctv", "CCTV & Surveillance", "network", dependencies=["net-lan", "power"]),
        ],
    )

    academic_module = InstitutionalModule(
        id="academic",
        name="Academic Systems",
        description="Curriculum management, timetabling, attendance, grading, and academic records",
        icon="📚",
        critical_constraints=[
            "No scheduling conflict between lectures",
            "Faculty-student ratio compliance",
            "Attendance threshold: 75% minimum",
        ],
        subsystems=[
            SubSystem("acad-timetable", "Timetabling Engine", "academic", dependencies=["network"]),
            SubSystem("acad-attend", "Attendance System", "academic", dependencies=["net-erp", "net-lan"]),
            SubSystem("acad-grades", "Grading & Results", "academic", dependencies=["net-erp"]),
            SubSystem("acad-curriculum", "Curriculum Manager", "academic", dependencies=["net-erp"]),
            SubSystem("acad-library", "Digital Library", "academic", dependencies=["net-lan", "power"]),
            SubSystem("acad-records", "Academic Records", "academic", dependencies=["net-erp", "net-servers"]),
        ],
    )

    faculty_module = InstitutionalModule(
        id="faculty",
        name="Faculty Management",
        description="Faculty scheduling, workload, HR, payroll, and professional development",
        icon="👨‍🏫",
        critical_constraints=[
            "No faculty double-booking",
            "Max 18 hours/week teaching load",
            "Guest lecture backups required",
        ],
        subsystems=[
            SubSystem("fac-schedule", "Faculty Scheduler", "faculty", dependencies=["acad-timetable"]),
            SubSystem("fac-hr", "HR & Payroll", "faculty", dependencies=["net-erp"]),
            SubSystem("fac-portal", "Faculty Portal", "faculty", dependencies=["net-lan", "net-erp"]),
            SubSystem("fac-leave", "Leave Management", "faculty", dependencies=["fac-hr", "fac-schedule"]),
            SubSystem("fac-research", "Research Management", "faculty", dependencies=["net-lan"]),
        ],
    )

    student_module = InstitutionalModule(
        id="student",
        name="Student Systems",
        description="Student enrollment, profiles, grievances, counseling, and student portal",
        icon="🎓",
        critical_constraints=[
            "Student data always accessible",
            "Grievance response within 48 hours",
            "Counseling available on demand",
        ],
        subsystems=[
            SubSystem("stu-enroll", "Enrollment System", "student", dependencies=["net-erp"]),
            SubSystem("stu-portal", "Student Portal", "student", dependencies=["net-lan", "net-erp"]),
            SubSystem("stu-grievance", "Grievance System", "student", dependencies=["net-lan"]),
            SubSystem("stu-counsel", "Counseling & Welfare", "student", dependencies=["stu-portal"]),
            SubSystem("stu-id", "ID Card & Biometrics", "student", dependencies=["power", "net-lan"]),
        ],
    )

    classroom_module = InstitutionalModule(
        id="classroom",
        name="Classroom & Infrastructure",
        description="Classroom allocation, AV systems, smart boards, and seating management",
        icon="🏛️",
        critical_constraints=[
            "Room capacity must not exceed 60 students",
            "Smart boards online for all sessions",
            "No room double-booking",
        ],
        subsystems=[
            SubSystem("class-alloc", "Room Allocation", "classroom", dependencies=["acad-timetable"]),
            SubSystem("class-av", "AV & Projectors", "classroom", dependencies=["power"]),
            SubSystem("class-smart", "Smart Boards", "classroom", dependencies=["power", "net-lan"]),
            SubSystem("class-ac", "HVAC Systems", "classroom", dependencies=["power"]),
            SubSystem("class-booking", "Booking Portal", "classroom", dependencies=["net-lan"]),
        ],
    )

    lab_module = InstitutionalModule(
        id="laboratory",
        name="Laboratories",
        description="Computer labs, physics, chemistry, electronics, civil, mechanical, and research labs",
        icon="🔬",
        critical_constraints=[
            "Safety protocols must be active",
            "Equipment calibration current",
            "Lab supervisor present always",
        ],
        subsystems=[
            SubSystem("lab-cs", "Computer Labs", "laboratory", dependencies=["power", "net-lan"]),
            SubSystem("lab-electronics", "Electronics Lab", "laboratory", dependencies=["power"]),
            SubSystem("lab-chem", "Chemistry Lab", "laboratory", dependencies=["power", "lab-safety"]),
            SubSystem("lab-mech", "Mechanical Workshop", "laboratory", dependencies=["power"]),
            SubSystem("lab-civil", "Civil Engineering Lab", "laboratory", dependencies=["power"]),
            SubSystem("lab-research", "Research Labs", "laboratory", dependencies=["power", "net-lan"]),
            SubSystem("lab-safety", "Safety Systems", "laboratory", dependencies=["power"]),
            SubSystem("lab-equipment", "Equipment Management", "laboratory", dependencies=["net-lan"]),
        ],
    )

    exam_module = InstitutionalModule(
        id="examination",
        name="Examination Systems",
        description="Exam scheduling, hall allocation, invigilation, results, and question banks",
        icon="📝",
        critical_constraints=[
            "Zero tolerance for question paper leaks",
            "Results within 15 days of exam",
            "Invigilation ratio: 1:30",
        ],
        subsystems=[
            SubSystem("exam-schedule", "Exam Scheduler", "examination", dependencies=["acad-timetable", "net-erp"]),
            SubSystem("exam-hall", "Hall Allocation", "examination", dependencies=["class-alloc", "exam-schedule"]),
            SubSystem("exam-invig", "Invigilation System", "examination", dependencies=["fac-schedule"]),
            SubSystem("exam-qbank", "Question Bank", "examination", dependencies=["net-servers", "net-erp"]),
            SubSystem("exam-results", "Results Processing", "examination", dependencies=["net-erp", "net-servers"]),
            SubSystem("exam-portal", "Student Exam Portal", "examination", dependencies=["net-lan", "stu-portal"]),
        ],
    )

    transport_module = InstitutionalModule(
        id="transportation",
        name="Transportation",
        description="Bus fleet management, routes, GPS tracking, and driver management",
        icon="🚌",
        critical_constraints=[
            "No student left behind",
            "GPS tracking mandatory",
            "Driver background verification current",
        ],
        subsystems=[
            SubSystem("trans-fleet", "Fleet Management", "transportation", dependencies=["power"]),
            SubSystem("trans-gps", "GPS Tracking", "transportation", dependencies=["net-lan", "trans-fleet"]),
            SubSystem("trans-route", "Route Planner", "transportation", dependencies=["net-lan"]),
            SubSystem("trans-booking", "Transport Booking", "transportation", dependencies=["net-lan", "stu-portal"]),
            SubSystem("trans-fuel", "Fuel Management", "transportation", dependencies=["trans-fleet"]),
        ],
    )

    hostel_module = InstitutionalModule(
        id="hostel",
        name="Hostel & Residential",
        description="Room allocation, mess, warden management, visitor logs, and hostel amenities",
        icon="🏠",
        critical_constraints=[
            "Water supply uninterrupted",
            "Curfew compliance monitored",
            "Medical emergencies response < 10 min",
        ],
        subsystems=[
            SubSystem("hostel-alloc", "Room Allocation", "hostel", dependencies=["net-erp"]),
            SubSystem("hostel-mess", "Mess & Cafeteria", "hostel", dependencies=["power", "hostel-water"]),
            SubSystem("hostel-water", "Water Supply", "hostel", dependencies=["power"]),
            SubSystem("hostel-security", "Hostel Security", "hostel", dependencies=["net-cctv", "power"]),
            SubSystem("hostel-warden", "Warden System", "hostel", dependencies=["net-lan"]),
            SubSystem("hostel-medical", "Medical Facility", "hostel", dependencies=["power", "net-lan"]),
        ],
    )

    placement_module = InstitutionalModule(
        id="placement",
        name="Training & Placement",
        description="Campus recruitment, company coordination, aptitude training, and alumni connect",
        icon="💼",
        critical_constraints=[
            "Placement portal 24/7 uptime",
            "No scheduling conflict on interview days",
            "NDA compliance for visiting companies",
        ],
        subsystems=[
            SubSystem("place-portal", "Placement Portal", "placement", dependencies=["net-lan", "net-servers"]),
            SubSystem(
                "place-schedule",
                "Interview Scheduler",
                "placement",
                dependencies=["place-portal", "class-booking"],
            ),
            SubSystem(
                "place-training",
                "Aptitude Training",
                "placement",
                dependencies=["net-lan", "acad-timetable"],
            ),
            SubSystem("place-alumni", "Alumni Network", "placement", dependencies=["net-lan"]),
            SubSystem("place-company", "Company Coordinator", "placement", dependencies=["net-lan"]),
        ],
    )

    events_module = InstitutionalModule(
        id="events",
        name="Events & Activities",
        description="Cultural fests, technical symposiums, sports, seminars, and venue management",
        icon="🎪",
        critical_constraints=[
            "No event during exam week",
            "Venue capacity compliance",
            "Emergency exits must be clear",
        ],
        subsystems=[
            SubSystem(
                "event-schedule",
                "Event Scheduler",
                "events",
                dependencies=["acad-timetable", "class-booking"],
            ),
            SubSystem("event-venue", "Venue Management", "events", dependencies=["class-booking", "power"]),
            SubSystem("event-tech", "Tech Support", "events", dependencies=["power", "net-lan"]),
            SubSystem("event-sports", "Sports & Ground", "events", dependencies=["power"]),
            SubSystem("event-permits", "Permits & Compliance", "events", dependencies=["net-lan"]),
        ],
    )

    admin_module = InstitutionalModule(
        id="administration",
        name="Administration",
        description="Principal office, registrar, finance, legal, accreditation, and governance",
        icon="🏢",
        critical_constraints=[
            "Financial records always accessible",
            "NAAC compliance maintained",
            "Regulatory submissions on deadline",
        ],
        subsystems=[
            SubSystem("admin-finance", "Finance & Accounts", "administration", dependencies=["net-erp"]),
            SubSystem("admin-legal", "Legal & Compliance", "administration", dependencies=["net-lan"]),
            SubSystem(
                "admin-accred",
                "Accreditation (NAAC/NBA)",
                "administration",
                dependencies=["net-erp", "acad-records"],
            ),
            SubSystem("admin-hr", "HR Department", "administration", dependencies=["fac-hr", "net-erp"]),
            SubSystem("admin-registrar", "Registrar Office", "administration", dependencies=["net-erp", "stu-enroll"]),
        ],
    )

    for mod in [
        power_module,
        network_module,
        academic_module,
        faculty_module,
        student_module,
        classroom_module,
        lab_module,
        exam_module,
        transport_module,
        hostel_module,
        placement_module,
        events_module,
        admin_module,
    ]:
        state.modules[mod.id] = mod

    state.constraints = _build_constraints()
    state.resources = _build_resources()
    state.compute_overall_health()
    return state
