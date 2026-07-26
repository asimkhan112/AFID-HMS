"""
seed_demo_data.py
Wipe the database and reseed it with a full, realistic demo clinic.

Every panel on every portal is populated: doctor queues, room allocations,
operatory status, completed procedures with their materials/pharmacy/
diagnostics/notes, patient timelines, leave requests in all three states, the
staff directory, and the procedure preset catalogue.

Patient activity is deliberately spread across the last ~120 days so the
doctor portal's "Reporting period" selector (This Week / This Month / Last 90
Days / All Time) shows genuinely different numbers for each option.

Usage:
    python seed_demo_data.py            # wipe + reseed (asks for confirmation)
    python seed_demo_data.py --yes      # wipe + reseed, no prompt
"""

import sys
import os
import random
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(__file__))

from database import engine, Base, SessionLocal
import models
from auth import hash_password

# Deterministic output: re-running produces the same clinic, so screenshots and
# manual walkthroughs stay comparable between runs.
random.seed(20260726)

NOW = datetime.now()
TODAY = date.today()


# ── Reference data ────────────────────────────────────────────────────────────

USERS = [
    # full_name,             email,                password,     role,          staff_id
    ("Col. S. Hashmi",       "hod@afid.mil",       "admin1234",  "hod",          "HMS-0001"),
    ("Dr. Asadullah Khan",   "doctor@afid.mil",    "doctor1234", "doctor",       "HMS-0002"),
    ("Dr. Rehan Mahmood",    "rehan@afid.mil",     "doctor1234", "doctor",       "HMS-0003"),
    ("Dr. Sana Kamal",       "sana@afid.mil",      "doctor1234", "doctor",       "HMS-0004"),
    ("Dr. Tariq Aziz",       "tariq@afid.mil",     "doctor1234", "doctor",       "HMS-0005"),
    ("Dr. Hira Zaman",       "hira@afid.mil",      "doctor1234", "doctor",       "HMS-0006"),
    ("Dr. Bilal Saeed",      "bilal@afid.mil",     "doctor1234", "doctor",       "HMS-0007"),
    ("Fatima Asif",          "reception@afid.mil", "staff1234",  "receptionist", "HMS-0010"),
    ("Kamran Shah",          "kamran@afid.mil",    "staff1234",  "receptionist", "HMS-0011"),
    ("Ali Raza",             "ali@afid.mil",       "nurse1234",  "nurse",        "HMS-0012"),
]

# doctor full_name -> (room, department, chair, qualifications, shift, status)
DOCTORS = {
    "Dr. Asadullah Khan": ("Room 10", "Orthodontics", "Dental Chair A",
                           "FCPS (Orthodontics)", "Morning (0800 - 1400)", "Available"),
    "Dr. Rehan Mahmood":  ("Room 11", "Orthodontics", "Dental Chair B",
                           "BDS, MDS (Orthodontics)", "Morning (0800 - 1400)", "Available"),
    "Dr. Sana Kamal":     ("Room 12", "Orthodontics", "Dental Chair C",
                           "BDS, FCPS-II Trainee", "Morning (0800 - 1400)", "Available"),
    "Dr. Tariq Aziz":     ("Room 13", "Oral Surgery", "Dental Chair D",
                           "FCPS (Oral & Maxillofacial Surgery)", "Evening (1400 - 2000)", "Available"),
    "Dr. Hira Zaman":     ("Room 14", "Orthodontics", "Dental Chair E",
                           "BDS, MSc (Orthodontics)", "Evening (1400 - 2000)", "Available"),
    "Dr. Bilal Saeed":    ("Room 15", "Orthodontics", "Dental Chair F",
                           "BDS, MDS", "Morning (0800 - 1400)", "On Leave"),
}

STAFF = [
    ("Sara Khan",    "Technician",     "Active"),
    ("Ali Raza",     "Nurse",          "Active"),
    ("Maha Siddiq",  "Lab Technician", "Active"),
    ("Umar Farooq",  "Receptionist",   "Active"),
    ("Nadia Yousuf", "Nurse",          "On Leave"),
    ("Bilal Qadir",  "Lab Technician", "Active"),
    ("Hina Akram",   "Technician",     "Active"),
    ("Kamran Shah",  "Receptionist",   "Active"),
    ("Rabia Nawaz",  "Nurse",          "Active"),
    ("Faisal Meer",  "Lab Technician", "Active"),
    ("Sobia Tariq",  "Technician",     "Active"),
    ("Imran Butt",   "Nurse",          "Active"),
    ("Aqsa Malik",   "Receptionist",   "Active"),
    ("Zeeshan Ali",  "Lab Technician", "Active"),
]

SERVICE_PROFILES = [
    "Serving Officer", "Serving Soldier / JCO", "Retired Officer",
    "Retired Soldier / JCO", "Family / Dependent", "Civilian (Entitled)",
]
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
ALLERGIES = [None, None, None, None, "Penicillin Sensitivity", "Latex",
             "Lignocaine (local anaesthetic)", "Sulpha drugs", "Ibuprofen / NSAIDs"]

# (rank, first-name pool) so names read as a real military dental register.
MALE_NAMES = ["Zeeshan Khan", "Ahmed Raza", "Usman Tariq", "Bilal Ahmad", "Kashif Mehmood",
              "Adnan Sheikh", "Faisal Iqbal", "Imran Yousaf", "Nauman Ali", "Waqar Hussain",
              "Salman Rashid", "Junaid Aslam", "Rizwan Haider", "Shahid Nazir", "Asif Mahmood",
              "Tahir Mehboob", "Umair Farooq", "Danish Qureshi"]
FEMALE_NAMES = ["Tooba Tariq", "Sana Rauf", "Fatima Noor", "Zara Siddiqui", "Ayesha Malik",
                "Hina Bashir", "Mehwish Anwar", "Sadia Kamran", "Rabia Sultan", "Amna Javed",
                "Nimra Shafiq", "Iqra Nadeem", "Saima Riaz", "Komal Zafar"]
OFFICER_RANKS = ["Maj", "Capt", "Lt Col", "Col", "Brig", "Lt"]
SOLDIER_RANKS = ["Hav", "Nk", "Sep", "Sub", "L/Nk"]

PROCEDURE_CATEGORIES = [
    "Consultation", "ORAL EXAM", "U/L Bracketing", "Fixed retainer", "De bonding",
    "Fixed adjustment (Wire/Bends/IPR/Traction/Implant)", "Molar bands / VFR",
    "Treatment planning / File analysis / Tracing", "Impression / O/E / Separator / Removable adj",
    "Space maintainer / Photography / Digital Scan", "Loose band / Button / Bracket / Tubes",
    "Nance LLA / Hyrax / Quad Helix / TPA / Pendulum",
]

# Procedure presets: name -> (duration, notes, materials, pharmacy, diagnostics)
PRESETS = {
    "Consultation": (15,
        "Initial specialist consultation conducted. Chief complaints documented and a preliminary treatment plan discussed with the patient.",
        [("Mouth mirror & Probe set", 1), ("Cotton rolls", 2)], [], []),
    "ORAL EXAM": (10,
        "Full intraoral and extraoral examination completed. Charting updated.",
        [("Mouth mirror & Probe set", 1), ("Napkin", 1)], [], []),
    "U/L Bracketing": (45,
        "Upper and lower bracket placement completed. Archwire secured. Patient instructed on oral hygiene with fixed appliances.",
        [("Brackets", 20), ("Composite", 1), ("Etchant", 1), ("Primer", 1)],
        [("Paracetamol 500mg", "500mg", "TDS x 3 days"),
         ("Orthodontic Relief Wax", "1 Box", "Apply as needed")],
        [("OPG", "Routine"), ("Lateral cephalogram", "Routine")]),
    "Bonding of brackets": (40,
        "Direct bonding completed across the planned arch. Occlusion verified.",
        [("Brackets", 10), ("Composite", 1), ("Etchant", 1), ("Primer", 1)],
        [("Paracetamol 500mg", "500mg", "BD PRN pain")], []),
    "Fixed retainer": (40,
        "Lingual bonded fixed retainer wire placed and verified. Occlusion checked.",
        [("Retainer wire", 1), ("Composite", 1), ("Etchant", 1), ("Primer", 1)],
        [], [("Intraoral - frontal photo", "Routine")]),
    "De bonding": (30,
        "All fixed appliances removed. Residual adhesive polished off. Retention protocol explained.",
        [("Debonding pliers kit", 1), ("Polishing burs", 2), ("Prophy paste", 1)],
        [("Chlorhexidine Mouth Wash 0.2%", "15ml", "BD x 7 days")],
        [("Intraoral - frontal photo", "Routine"), ("OPG", "Routine")]),
    "Fixed adjustment (Wire/Bends/IPR/Traction/Implant)": (20,
        "Archwire changed and active bends placed. Elastic wear reinforced with the patient.",
        [("0.016 NiTi Archwire", 1), ("Steel ligatures", 8), ("Orthodontic Elastics Bag", 1)],
        [("Paracetamol 500mg", "500mg", "PRN pain")], []),
    "Molar bands / VFR": (20,
        "Molar bands trial-fitted and cemented cleanly. Vacuum-formed retainer issued.",
        [("Molar bands", 4), ("GIC", 1), ("Cotton rolls", 2)], [], []),
    "Treatment planning / File analysis / Tracing": (20,
        "Cephalometric tracing completed and treatment objectives finalised.",
        [("Tracing paper", 1), ("Acetate sheet", 1)],
        [],
        [("Lateral cephalogram", "Routine"), ("Bolton analysis", "Routine"),
         ("Arch length analysis", "Routine"), ("Study cast", "Routine")]),
    "Impression / O/E / Separator / Removable adj": (10,
        "Impressions recorded and separators placed. Removable appliance adjusted.",
        [("Alginate", 1), ("Impression trays", 2), ("Separators", 8)], [], []),
    "Space maintainer / Photography / Digital Scan": (10,
        "Digital scan captured and clinical photography series recorded.",
        [("Scanner tips", 2), ("Cheek retractors", 1)],
        [],
        [("Digital intraoral scan", "Routine"), ("Extra oral photos", "Routine"),
         ("Intraoral photos", "Routine")]),
    "Loose band / Button / Bracket / Tubes": (20,
        "Loose attachment re-bonded and archwire re-engaged.",
        [("Brackets", 1), ("Composite", 1), ("Etchant", 1)], [], []),
    "Nance LLA / Hyrax / Quad Helix / TPA / Pendulum": (20,
        "Auxiliary appliance checked and cemented. Activation schedule explained.",
        [("Molar bands", 2), ("GIC", 1), ("Cotton rolls", 2)], [], []),
    "Root Canal Treatment": (60,
        "Access cavity established under rubber dam isolation. Working length confirmed via apex locator. Canals cleaned and shaped, irrigated with 2.5% NaOCl.",
        [("Gutta-Percha Points (ISO 30)", 6), ("AH Plus Sealer (1.5g)", 1), ("Rubber dam kit", 1)],
        [("Amoxicillin 500mg", "500mg", "TDS x 5 days"),
         ("Ibuprofen 400mg", "400mg", "BD PRN pain"),
         ("Chlorhexidine Mouth Wash 0.2%", "15ml", "BD x 7 days")],
        [("Full Mouth Periapical X-rays", "Urgent"), ("CBCT", "Routine")]),
    "Surgical exposure of impacted tooth": (60,
        "Surgical exposure completed under LA. Gold chain bonded and ligated to the archwire.",
        [("Gold Chain", 1), ("Surgical blade", 1), ("Sutures 3-0", 2)],
        [("Amoxicillin 500mg", "500mg", "TDS x 5 days"),
         ("Ibuprofen 400mg", "400mg", "TDS x 3 days")],
        [("CBCT", "Urgent"), ("Occlusal radiograph", "Routine")]),
}

TIMELINE_TEMPLATE = [
    "Initial Consultation", "Records & Cephalometric X-Ray", "Treatment Planning",
    "Bracket Placement", "Archwire Adjustment", "Elastics Evaluation",
    "Debonding", "Retainer Fitting",
]

CLINICAL_NOTES_EXTRA = [
    "Patient tolerated the procedure well. No intra-operative complications.",
    "Oral hygiene reinforced. Recall scheduled in 4 weeks.",
    "Mild tenderness expected for 48 hours; analgesia advised.",
    "Compliance with elastics discussed at length with the patient and attendant.",
]


# ── Wipe ──────────────────────────────────────────────────────────────────────

def wipe(db):
    """Delete all domain rows, children before parents to respect FKs."""
    order = [
        models.ProcedureChecklist, models.ProcedureMaterial, models.ProcedurePharmacy,
        models.ProcedureDiagnostic, models.ClinicalNote, models.Procedure,
        models.PatientTimelineStep, models.Patient,
        models.PresetMaterial, models.PresetPharmacy, models.PresetDiagnostic,
        models.ProcedurePreset,
        models.LeaveRequest, models.DoctorProfile, models.DoctorAllocation,
        models.OperatoryRoom, models.StaffMember, models.User,
    ]
    for model in order:
        db.query(model).delete(synchronize_session=False)
    db.commit()


# ── Seed ──────────────────────────────────────────────────────────────────────

def seed(db):
    # ── Users + doctor profiles ───────────────────────────────────────────────
    users = {}
    for full_name, email, password, role, staff_id in USERS:
        user = models.User(
            full_name=full_name,
            email=email,
            hashed_password=hash_password(password),
            role=models.UserRole(role),
            staff_id=staff_id,
            is_active=True,
            created_at=NOW - timedelta(days=200),
        )
        db.add(user)
        db.flush()
        users[full_name] = user

    for name, (_room, dept, _chair, quals, shift, status) in DOCTORS.items():
        db.add(models.DoctorProfile(
            user_id=users[name].id,
            department=dept,
            qualifications=quals,
            shift=shift,
            hod_on_call="Col. S. Hashmi",
            status=status,
        ))

    # ── Staff directory ───────────────────────────────────────────────────────
    for name, role, status in STAFF:
        db.add(models.StaffMember(name=name, role=role, status=status))

    # ── Room allocations (one doctor per room) ────────────────────────────────
    for name, (room, dept, chair, *_rest) in DOCTORS.items():
        db.add(models.DoctorAllocation(
            doctor_name=name, room=room, department=dept, chair=chair,
            created_at=NOW - timedelta(days=30),
        ))

    # ── Procedure presets ─────────────────────────────────────────────────────
    for name, (duration, notes, materials, pharmacy, diagnostics) in PRESETS.items():
        preset = models.ProcedurePreset(name=name, duration=duration, notes=notes, is_active=True)
        db.add(preset)
        db.flush()
        for m_name, qty in materials:
            db.add(models.PresetMaterial(preset_id=preset.id, name=m_name, quantity=qty))
        for med, dose, freq in pharmacy:
            db.add(models.PresetPharmacy(preset_id=preset.id, medication=med, dose=dose, frequency=freq))
        for test, urgency in diagnostics:
            db.add(models.PresetDiagnostic(
                preset_id=preset.id, test_name=test,
                urgency=models.DiagnosticUrgency(urgency),
            ))

    # ── Patients ──────────────────────────────────────────────────────────────
    doctor_names = list(DOCTORS.keys())
    patients = []
    mr_seq = 1700
    file_seq = 18300

    def make_patient(status, days_ago, doctor, gender_pool):
        nonlocal mr_seq, file_seq
        mr_seq += random.randint(3, 19)
        file_seq += random.randint(1, 7)

        is_male = gender_pool == "Male"
        base = random.choice(MALE_NAMES if is_male else FEMALE_NAMES)
        profile = random.choice(SERVICE_PROFILES)
        if "Officer" in profile:
            rank = random.choice(OFFICER_RANKS)
        elif "Soldier" in profile:
            rank = random.choice(SOLDIER_RANKS)
        else:
            rank = None
        full_name = f"{rank} {base}" if rank else base

        registered = NOW - timedelta(days=days_ago,
                                     hours=random.randint(0, 6),
                                     minutes=random.randint(0, 59))
        check_in = check_out = None
        if status in (models.PatientStatus.active, models.PatientStatus.completed):
            check_in = registered + timedelta(minutes=random.randint(5, 45))
        if status == models.PatientStatus.completed:
            check_out = check_in + timedelta(minutes=random.randint(12, 95))

        room = DOCTORS[doctor][0]
        p = models.Patient(
            mr_number=f"MR-2026-{mr_seq:04d}",
            file_number=f"F-{file_seq}",
            full_name=full_name,
            rank=rank,
            cnic=f"{random.randint(31000, 42101)}-{random.randint(1000000, 9999999)}-{random.randint(1, 9)}",
            gender=gender_pool,
            blood_group=random.choice(BLOOD_GROUPS),
            service_profile=profile,
            allergies=random.choice(ALLERGIES),
            room=room,
            assigned_doctor=doctor,
            procedure_category=random.choice(PROCEDURE_CATEGORIES),
            status=status,
            registered_at=registered,
            updated_at=check_out or check_in or registered,
            check_in_time=check_in,
            check_out_time=check_out,
        )
        db.add(p)
        db.flush()
        patients.append(p)
        return p

    genders = ["Male", "Female"]

    # Today's live queue -- what reception and the doctors work from right now.
    # Weighted toward Dr. Asadullah Khan (the demo login) so his dashboard is full.
    todays_doctors = ["Dr. Asadullah Khan"] * 4 + doctor_names[:5]
    for i, doc in enumerate(todays_doctors):
        make_patient(models.PatientStatus.waiting, 0, doc, genders[i % 2])
    for i, doc in enumerate(["Dr. Asadullah Khan", "Dr. Rehan Mahmood", "Dr. Sana Kamal",
                             "Dr. Tariq Aziz", "Dr. Hira Zaman"]):
        make_patient(models.PatientStatus.active, 0, doc, genders[i % 2])
    for i, doc in enumerate(["Dr. Asadullah Khan", "Dr. Asadullah Khan",
                             "Dr. Rehan Mahmood", "Dr. Sana Kamal"]):
        make_patient(models.PatientStatus.completed, 0, doc, genders[i % 2])

    # Historical completed cases, spread so each analytics period differs:
    # this week, this month, and the 30-120 day tail.
    for band, count in [((1, 6), 8), ((7, 29), 12), ((30, 120), 14)]:
        for i in range(count):
            days_ago = random.randint(*band)
            doc = doctor_names[i % len(doctor_names)] if i % 3 else "Dr. Asadullah Khan"
            make_patient(models.PatientStatus.completed, days_ago, doc, genders[i % 2])

    # ── Procedures for completed patients ─────────────────────────────────────
    preset_names = list(PRESETS.keys())
    completed = [p for p in patients if p.status == models.PatientStatus.completed]

    for idx, patient in enumerate(completed):
        # Most completed cases have one procedure; some have a short history.
        for n in range(random.choice([1, 1, 1, 2, 2, 3])):
            name = preset_names[(idx + n * 5) % len(preset_names)]
            duration, notes, materials, pharmacy, diagnostics = PRESETS[name]
            session_date = (patient.check_in_time or patient.registered_at) - timedelta(days=n * 21)

            proc = models.Procedure(
                patient_id=patient.id,
                doctor_id=users[patient.assigned_doctor].id,
                name=name,
                session_date=session_date,
                is_completed=True,
            )
            db.add(proc)
            db.flush()

            for order, (m_name, qty) in enumerate(materials, start=1):
                db.add(models.ProcedureMaterial(
                    procedure_id=proc.id, material_name=m_name, quantity=qty))
            # Every session also consumes the standard barrier/disposable set.
            for m_name in ("Napkin", "Sterilization pouch", "Suction tip"):
                db.add(models.ProcedureMaterial(
                    procedure_id=proc.id, material_name=m_name, quantity=1))

            for med, dose, freq in pharmacy:
                db.add(models.ProcedurePharmacy(
                    procedure_id=proc.id, medication=med, dose=dose, frequency=freq))

            for test, urgency in diagnostics:
                db.add(models.ProcedureDiagnostic(
                    procedure_id=proc.id, test_name=test,
                    urgency=models.DiagnosticUrgency(urgency)))

            db.add(models.ClinicalNote(
                procedure_id=proc.id,
                note_text=f"{notes}\n\n{random.choice(CLINICAL_NOTES_EXTRA)}",
                created_at=session_date,
            ))

            for order, step in enumerate(
                ["Consent obtained", "Anaesthesia / isolation", "Procedure performed",
                 "Occlusion verified", "Post-op instructions given"], start=1):
                db.add(models.ProcedureChecklist(
                    procedure_id=proc.id, step_text=step,
                    is_checked=True, display_order=order))

    # ── Patient timelines ─────────────────────────────────────────────────────
    # Completed cases get a fully-walked timeline; in-progress ones stop partway
    # so the HOD and doctor timeline views show all three step states.
    for patient in patients:
        if patient.status == models.PatientStatus.completed:
            done_upto = len(TIMELINE_TEMPLATE)
        elif patient.status == models.PatientStatus.active:
            done_upto = random.randint(2, 5)
        else:
            done_upto = random.randint(0, 2)

        for order, step_name in enumerate(TIMELINE_TEMPLATE, start=1):
            if order <= done_upto:
                status = models.StepStatus.completed
            elif order == done_upto + 1 and patient.status != models.PatientStatus.waiting:
                status = models.StepStatus.in_progress
            else:
                status = models.StepStatus.pending
            db.add(models.PatientTimelineStep(
                patient_id=patient.id, step_order=order,
                step_name=step_name, status=status,
                updated_at=patient.updated_at,
            ))

    # ── Operatory rooms ───────────────────────────────────────────────────────
    active_by_room = {}
    for p in patients:
        if p.status == models.PatientStatus.active:
            active_by_room[p.room] = p
    queue_by_room = {}
    for p in patients:
        if p.status == models.PatientStatus.waiting:
            queue_by_room[p.room] = queue_by_room.get(p.room, 0) + 1

    for room_no in range(10, 20):
        room_name = f"Room {room_no}"
        doctor = next((n for n, cfg in DOCTORS.items() if cfg[0] == room_name), None)
        occupant = active_by_room.get(room_name)
        if occupant:
            status = models.RoomStatus.busy
            current_case = occupant.procedure_category
        elif doctor and queue_by_room.get(room_name):
            status = models.RoomStatus.consultation
            current_case = "Consultation in progress"
        else:
            status = models.RoomStatus.available
            current_case = "Idle / Preparing Chair"
        db.add(models.OperatoryRoom(
            room_name=room_name,
            assigned_doctor=doctor or "—",
            current_case=current_case,
            queue_count=queue_by_room.get(room_name, 0),
            status=status,
        ))

    # ── Leave requests (all three states) ─────────────────────────────────────
    leaves = [
        ("Dr. Bilal Saeed",   models.LeaveType.medical, "Maj. T. Farooq",
         "Post-operative recovery following minor surgery.", -3, 11, models.LeaveStatus.approved, "Col. S. Hashmi"),
        ("Dr. Hira Zaman",    models.LeaveType.annual,  "Dr. Sana Kamal",
         "Annual family leave — station leave to Lahore.", 12, 19, models.LeaveStatus.pending, None),
        ("Dr. Rehan Mahmood", models.LeaveType.casual,  "Dr. Asadullah Khan",
         "Attending nephew's wedding (one day).", 5, 5, models.LeaveStatus.pending, None),
        ("Dr. Tariq Aziz",    models.LeaveType.casual,  "Dr. Bilal Saeed",
         "Personal errand — half day requested.", 8, 8, models.LeaveStatus.pending, None),
        ("Dr. Sana Kamal",    models.LeaveType.annual,  "Dr. Hira Zaman",
         "Annual leave request for Eid holidays.", 25, 32, models.LeaveStatus.rejected, "Col. S. Hashmi"),
        ("Dr. Asadullah Khan", models.LeaveType.casual, "Dr. Rehan Mahmood",
         "Course attendance at AFID Rawalpindi.", -20, -18, models.LeaveStatus.approved, "Col. S. Hashmi"),
    ]
    for doctor, ltype, officer, reason, start_off, end_off, status, reviewer in leaves:
        db.add(models.LeaveRequest(
            requester_id=users[doctor].id,
            leave_type=ltype,
            coverage_officer=officer,
            reason=reason,
            start_date=TODAY + timedelta(days=start_off),
            end_date=TODAY + timedelta(days=end_off),
            status=status,
            reviewed_by=reviewer,
            created_at=NOW - timedelta(days=abs(start_off) + 2),
            updated_at=NOW - timedelta(days=1),
        ))

    db.commit()
    return patients


def summarise(db):
    counts = [
        ("Users", models.User), ("Doctor profiles", models.DoctorProfile),
        ("Staff members", models.StaffMember), ("Room allocations", models.DoctorAllocation),
        ("Operatory rooms", models.OperatoryRoom), ("Procedure presets", models.ProcedurePreset),
        ("Patients", models.Patient), ("Procedures", models.Procedure),
        ("Materials logged", models.ProcedureMaterial), ("Medications logged", models.ProcedurePharmacy),
        ("Diagnostics logged", models.ProcedureDiagnostic), ("Clinical notes", models.ClinicalNote),
        ("Timeline steps", models.PatientTimelineStep), ("Leave requests", models.LeaveRequest),
    ]
    print("\n  Seeded:")
    for label, model in counts:
        print(f"    {label:<20} {db.query(model).count():>5}")

    print("\n  Patients by status:")
    for status in models.PatientStatus:
        n = db.query(models.Patient).filter(models.Patient.status == status).count()
        print(f"    {status.value:<20} {n:>5}")

    print("\n  Login credentials:")
    print("    HOD        : hod@afid.mil       / admin1234")
    print("    Doctor     : doctor@afid.mil    / doctor1234   (Dr. Asadullah Khan)")
    print("    Reception  : reception@afid.mil / staff1234")
    print("    Other doctors use <first-name>@afid.mil / doctor1234")


def main():
    Base.metadata.create_all(bind=engine)

    if "--yes" not in sys.argv:
        print("This DELETES every row in the AFID database and reseeds demo data.")
        if input("Type 'yes' to continue: ").strip().lower() != "yes":
            print("Aborted.")
            return

    db = SessionLocal()
    try:
        wipe(db)
        seed(db)
        print("Demo clinic seeded successfully.")
        summarise(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
