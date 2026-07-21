"""
init_db.py
Run once to create all tables and seed initial data.

Usage:
    python init_db.py
"""

from database import engine, Base, SessionLocal
import models
from auth import hash_password

def seed():
    # Create all tables
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # ── Skip if already seeded ────────────────────────────────────────────
        if db.query(models.User).count() > 0:
            print("Database already seeded. Skipping.")
            return

        # ── Users ─────────────────────────────────────────────────────────────
        users_data = [
            {"full_name": "Col. S. Hashmi",      "email": "hod@afid.mil",        "password": "admin1234",   "role": models.UserRole.hod,          "staff_id": "HMS-0001"},
            {"full_name": "Dr. Asadullah Khan",  "email": "doctor@afid.mil",     "password": "doctor1234",  "role": models.UserRole.doctor,       "staff_id": "HMS-0002"},
            {"full_name": "Dr. Rehan M.",         "email": "rehan@afid.mil",      "password": "doctor1234",  "role": models.UserRole.doctor,       "staff_id": "HMS-0003"},
            {"full_name": "Dr. Sana K.",          "email": "sana@afid.mil",       "password": "doctor1234",  "role": models.UserRole.doctor,       "staff_id": "HMS-0004"},
            {"full_name": "Dr. Tariq A.",         "email": "tariq@afid.mil",      "password": "doctor1234",  "role": models.UserRole.doctor,       "staff_id": "HMS-0005"},
            {"full_name": "Dr. Hira Z.",          "email": "hira@afid.mil",       "password": "doctor1234",  "role": models.UserRole.doctor,       "staff_id": "HMS-0006"},
            {"full_name": "Dr. Bilal S.",         "email": "bilal@afid.mil",      "password": "doctor1234",  "role": models.UserRole.doctor,       "staff_id": "HMS-0007"},
            {"full_name": "Fatima Asif",          "email": "reception@afid.mil",  "password": "staff1234",   "role": models.UserRole.receptionist, "staff_id": "HMS-0010"},
        ]
        users = {}
        for u in users_data:
            user = models.User(
                full_name=u["full_name"],
                email=u["email"],
                hashed_password=hash_password(u["password"]),
                role=u["role"],
                staff_id=u["staff_id"],
            )
            db.add(user)
            db.flush()
            users[u["email"]] = user

        # ── Doctor Profiles ───────────────────────────────────────────────────
        db.add(models.DoctorProfile(
            user_id=users["doctor@afid.mil"].id,
            department="Orthodontics",
            qualifications="FCPS (Operative Dentistry)",
            shift="Morning (0800 - 1400)",
            hod_on_call="Col. S. Hashmi",
            status="Available",
        ))
        for email in ["rehan@afid.mil", "sana@afid.mil", "tariq@afid.mil", "hira@afid.mil", "bilal@afid.mil"]:
            db.add(models.DoctorProfile(user_id=users[email].id, department="Orthodontics", status="Available"))

        # ── Staff Directory ───────────────────────────────────────────────────
        staff_data = [
            ("Sara Khan",     "Technician",      "Active"),
            ("Ali Raza",      "Nurse",           "Active"),
            ("Maha Siddiq",   "Lab Technician",  "Active"),
            ("Umar Farooq",   "Receptionist",    "Active"),
            ("Nadia Yousuf",  "On Leave",        "On Leave"),
            ("Bilal Qadir",   "Lab Technician",  "Active"),
            ("Hina Akram",    "Technician",      "Active"),
            ("Kamran Shah",   "Receptionist",    "Active"),
            ("Rabia Nawaz",   "Nurse",           "Active"),
            ("Faisal Meer",   "Lab Technician",  "Active"),
            ("Sobia Tariq",   "Technician",      "Active"),
            ("Imran Butt",    "Nurse",           "Active"),
            ("Aqsa Malik",    "Receptionist",    "Active"),
            ("Zeeshan Ali",   "Lab Technician",  "Active"),
        ]
        for name, role, status in staff_data:
            db.add(models.StaffMember(name=name, role=role, status=status))

        # ── Doctor Allocations ────────────────────────────────────────────────
        allocations = [
            ("Dr. Asadullah Khan", "Room 10", "Orthodontics",  "Dental Chair A"),
            ("Dr. Rehan M.",       "Room 11", "Orthodontics",  "Dental Chair B"),
            ("Dr. Sana K.",        "Room 12", "Orthodontics",  "Dental Chair C"),
            ("Dr. Tariq A.",       "Room 13", "Oral Surgery",  "Dental Chair D"),
            ("Dr. Hira Z.",        "Room 14", "Orthodontics",  "Dental Chair E"),
            ("Dr. Bilal S.",       "Room 15", "Orthodontics",  "Dental Chair F"),
        ]
        for name, room, dept, chair in allocations:
            db.add(models.DoctorAllocation(doctor_name=name, room=room, department=dept, chair=chair))

        # ── Operatory Rooms ───────────────────────────────────────────────────
        rooms = [
            ("Room 10", "Dr. Rehan M.",       "Bracket Placement",  3, models.RoomStatus.busy),
            ("Room 11", "Dr. Sana K.",         "Wire Adjustment",    2, models.RoomStatus.busy),
            ("Room 12", "Dr. Tariq A.",        "New Case Eval",      1, models.RoomStatus.consultation),
            ("Room 13", "Dr. Hira Z.",         "Retainer Check",     0, models.RoomStatus.available),
            ("Room 14", "Dr. Bilal S.",        "Aligner Fit",        2, models.RoomStatus.busy),
            ("Room 15", "Dr. Asadullah Khan",  "Elastics Check",     1, models.RoomStatus.consultation),
            ("Room 16", "—",                   "—",                  0, models.RoomStatus.available),
            ("Room 17", "—",                   "—",                  0, models.RoomStatus.available),
            ("Room 18", "—",                   "—",                  0, models.RoomStatus.available),
            ("Room 19", "—",                   "—",                  0, models.RoomStatus.available),
        ]
        for room_name, doc, case, queue, status in rooms:
            db.add(models.OperatoryRoom(
                room_name=room_name, assigned_doctor=doc,
                current_case=case, queue_count=queue, status=status,
            ))

        # ── Sample Patients ───────────────────────────────────────────────────
        patients_data = [
            ("MR-0201708", "F-18281", "Maj Zeeshan Khan",     "Major",     "37405-1234567-1", "Male",   "A+", "Orthodontics", "Penicillin Sensitivity", "Room 10", "Dr. Asadullah Khan", "Root Canal Therapy (RCT)", models.PatientStatus.active),
            ("MR-0201815", "F-18282", "Capt Tooba Tariq",     "Captain",   "31302-3070543-1", "Female", "B+", "Orthodontics", None,                     "Room 11", "Dr. Rehan M.",       "Composite Resin Filling",  models.PatientStatus.waiting),
            ("MR-0203114", "F-18283", "Lt. Col. Sana Rauf",   "Lt. Col.",  "42101-9047382-1", "Female", "O+", "Orthodontics", None,                     "Room 12", "Dr. Sana K.",        "Scaling & Root Planing",   models.PatientStatus.waiting),
            ("MR-1045",    "F-19001", "Ahmed Khan",           None,        None,              "Male",   None, "Orthodontics", None,                     "Room 13", "Dr. Tariq A.",       "Orthodontic Adjustment",   models.PatientStatus.active),
            ("MR-1102",    "F-19002", "Fatima Noor",          None,        None,              "Female", None, "Orthodontics", None,                     "Room 14", "Dr. Hira Z.",        "Bracket Placement",        models.PatientStatus.active),
            ("MR-0987",    "F-19003", "Usman Tariq",          None,        None,              "Male",   None, "Orthodontics", None,                     "Room 15", "Dr. Bilal S.",       "Debonding",                models.PatientStatus.active),
            ("MR-1200",    "F-19004", "Zara Siddiqui",        None,        None,              "Female", None, "Orthodontics", None,                     "Room 10", "Dr. Asadullah Khan", "Initial Consultation",     models.PatientStatus.waiting),
        ]
        patient_objs = {}
        for row in patients_data:
            mr, file, name, rank, cnic, gender, blood, svc, allergy, room, doc, proc_cat, status = row
            p = models.Patient(
                mr_number=mr, file_number=file, full_name=name, rank=rank,
                cnic=cnic, gender=gender, blood_group=blood, service_profile=svc,
                allergies=allergy, room=room, assigned_doctor=doc,
                procedure_category=proc_cat, status=status,
            )
            db.add(p)
            db.flush()
            patient_objs[mr] = p

        # ── Patient Timeline Steps ────────────────────────────────────────────
        timelines = {
            "MR-1045": [
                (1, "Cephalometric X-Ray",    models.StepStatus.completed),
                (2, "Bracket Placement",       models.StepStatus.completed),
                (3, "Archwire Adjustment",     models.StepStatus.in_progress),
                (4, "Elastics Evaluation",     models.StepStatus.pending),
                (5, "Debonding",               models.StepStatus.pending),
            ],
            "MR-1102": [
                (1, "Cephalometric X-Ray",    models.StepStatus.completed),
                (2, "Bracket Placement",       models.StepStatus.in_progress),
                (3, "Archwire Adjustment",     models.StepStatus.pending),
            ],
            "MR-0987": [
                (1, "Initial Consultation",   models.StepStatus.completed),
                (2, "Cephalometric X-Ray",    models.StepStatus.completed),
                (3, "Bracket Placement",       models.StepStatus.completed),
                (4, "Archwire Adjustment",     models.StepStatus.completed),
                (5, "Elastics Evaluation",     models.StepStatus.completed),
                (6, "Debonding",               models.StepStatus.in_progress),
                (7, "Retainer Fitting",        models.StepStatus.pending),
            ],
            "MR-1200": [
                (1, "Initial Consultation",   models.StepStatus.completed),
                (2, "Cephalometric X-Ray",    models.StepStatus.in_progress),
                (3, "Bracket Placement",       models.StepStatus.pending),
            ],
        }
        for mr, steps in timelines.items():
            if mr in patient_objs:
                for order, name, status in steps:
                    db.add(models.PatientTimelineStep(
                        patient_id=patient_objs[mr].id,
                        step_order=order,
                        step_name=name,
                        status=status,
                    ))

        db.commit()
        print("✅  Database seeded successfully!")
        print("\n  Default login credentials:")
        print("  HOD/Admin  : hod@afid.mil       / admin1234")
        print("  Doctor     : doctor@afid.mil    / doctor1234")
        print("  Reception  : reception@afid.mil / staff1234")

    except Exception as e:
        db.rollback()
        print(f"❌  Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
