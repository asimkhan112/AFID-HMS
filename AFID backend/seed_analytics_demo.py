"""
seed_analytics_demo.py
Generate demo data for the HOD "Procedure Analytics" screen.

The analytics screen draws four things off two endpoints:

  /hod/procedure-analytics/doctor-times  -> bar chart  (avg duration per doctor)
                                         -> stats table (count / avg / min / max)
  /hod/procedure-analytics/completions   -> line chart (duration trend over time)
                                         -> completions table (one row per session)

Both endpoints inner-join procedures to users on doctor_id and require
duration_minutes IS NOT NULL, so demo rows need a real doctor, a real patient,
and start/end times. This script creates all three.

Runs against whatever DATABASE_URL points at (Postgres or SQLite) -- it goes
through SQLAlchemy, never raw dialect-specific SQL.

Usage
-----
    python seed_analytics_demo.py                 # use .env DATABASE_URL
    python seed_analytics_demo.py --wipe          # remove previous demo rows first
    DATABASE_URL="postgresql://user:pw@host/db" python seed_analytics_demo.py

Every row it creates is tagged (patients get MR numbers starting "MR-DEMO"),
so --wipe can remove exactly what this script added and nothing else.
"""

import argparse
import random
import sys
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
from migrations import sync_schema
import models

# Deterministic output -- rerunning gives the same numbers, so a reviewer
# comparing two runs sees real changes rather than reshuffled noise.
RANDOM_SEED = 20260730

DEMO_MR_PREFIX = "MR-DEMO"
DEMO_FILE_PREFIX = "F-DEMO"

# Procedure name -> (typical minutes, spread). Names match the seeded presets in
# seed_presets.py so they line up with the dropdown on the analytics screen.
PROCEDURE_PROFILES = {
    "Consultation":                         (15, 5),
    "U/L Bracketing":                       (45, 12),
    "Fixed Retainer":                       (40, 10),
    "Orthodontic Adjustment":               (25, 8),
    "Root Canal Treatment":                 (60, 18),
    "Band cementation / Banding of molars": (30, 9),
}

# Each doctor gets a consistent speed multiplier so the bar chart shows a clear
# ranking instead of near-identical bars.
#
# These are assigned by position, not by name: the seeded doctor names differ
# between databases (a fresh init_db.py creates "Dr. Rehan Mahmood" while some
# existing databases hold "Dr. Rehan M."), and keying on names meant only the
# one doctor whose name happened to match got any data.
SPEED_FACTORS = [0.85, 1.00, 1.15, 0.95, 1.25, 1.05]

DEMO_PATIENTS = [
    ("Maj Imran Shah",      "Major",     "Male",   "A+"),
    ("Capt Ayesha Noor",    "Captain",   "Female", "B+"),
    ("Lt Col Faisal Iqbal", "Lt. Col.",  "Male",   "O+"),
    ("Sgt Naveed Anwar",    "Sergeant",  "Male",   "AB+"),
    ("Ms Hina Rauf",        None,        "Female", "A-"),
    ("Maj Saad Mehmood",    "Major",     "Male",   "O-"),
    ("Capt Rabia Khan",     "Captain",   "Female", "B-"),
    ("Mr Zubair Ahmed",     None,        "Male",   "A+"),
    ("Lt Sana Javed",       "Lieutenant","Female", "O+"),
    ("Col Arif Nawaz",      "Colonel",   "Male",   "AB-"),
    ("Ms Komal Bashir",     None,        "Female", "B+"),
    ("Maj Danish Ali",      "Major",     "Male",   "A+"),
]

# How many completed sessions to generate per procedure name. Six doctors share
# these, so keep it a healthy multiple of 6 -- roughly 5 sessions each is enough
# for per-doctor averages to settle into a readable ranking on the bar chart and
# to give the trend line a decent number of points.
SESSIONS_PER_PROCEDURE = 30

# Spread sessions across this many days back from now.
DAYS_OF_HISTORY = 75


def wipe_demo_data(db: Session) -> tuple[int, int]:
    """Delete only the rows this script created."""
    demo_patients = (
        db.query(models.Patient)
        .filter(models.Patient.mr_number.like(f"{DEMO_MR_PREFIX}%"))
        .all()
    )
    patient_ids = [p.id for p in demo_patients]

    proc_count = 0
    if patient_ids:
        proc_count = (
            db.query(models.Procedure)
            .filter(models.Procedure.patient_id.in_(patient_ids))
            .delete(synchronize_session=False)
        )
    for p in demo_patients:
        db.delete(p)
    db.commit()
    return len(demo_patients), proc_count


def get_doctors(db: Session) -> list[models.User]:
    """Every doctor in the database, oldest account first (stable ordering)."""
    return (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.doctor)
        .order_by(models.User.id)
        .all()
    )


def speed_for(index: int) -> float:
    """Pace multiplier for the Nth doctor -- see SPEED_FACTORS."""
    return SPEED_FACTORS[index % len(SPEED_FACTORS)]


def ensure_demo_patients(db: Session, doctors: list[models.User]) -> list[models.Patient]:
    """Create the demo patient roster if it isn't there already."""
    existing = {
        p.mr_number: p
        for p in db.query(models.Patient)
        .filter(models.Patient.mr_number.like(f"{DEMO_MR_PREFIX}%"))
        .all()
    }

    patients = []
    for i, (name, rank, gender, blood) in enumerate(DEMO_PATIENTS, start=1):
        mr = f"{DEMO_MR_PREFIX}-{i:04d}"
        if mr in existing:
            patients.append(existing[mr])
            continue

        doctor = doctors[i % len(doctors)]
        patient = models.Patient(
            mr_number=mr,
            file_number=f"{DEMO_FILE_PREFIX}-{i:04d}",
            full_name=name,
            rank=rank,
            gender=gender,
            blood_group=blood,
            service_profile="Orthodontics",
            room=f"Room {10 + (i % 6)}",
            assigned_doctor=doctor.full_name,
            procedure_category="Orthodontics",
            status=models.PatientStatus.completed,
            registered_at=datetime.utcnow() - timedelta(days=DAYS_OF_HISTORY + 5),
        )
        db.add(patient)
        patients.append(patient)

    db.flush()
    return patients


def build_sessions(db: Session, doctors: list[models.User], patients: list[models.Patient],
                   profiles: dict | None = None, sessions_each: int | None = None) -> int:
    """Create completed procedures with realistic start/end times and durations."""
    rng = random.Random(RANDOM_SEED)
    now = datetime.utcnow()
    created = 0
    profiles = PROCEDURE_PROFILES if profiles is None else profiles
    sessions_each = SESSIONS_PER_PROCEDURE if sessions_each is None else sessions_each

    for proc_name, (base_minutes, spread) in profiles.items():
        for n in range(sessions_each):
            # Round-robin the doctors so every one of them gets a comparable
            # sample; pick patients at random so the completions table isn't the
            # same handful of names repeating in order.
            doctor_index = n % len(doctors)
            doctor = doctors[doctor_index]
            patient = rng.choice(patients)
            speed = speed_for(doctor_index)

            # Duration: procedure baseline, scaled by the doctor's pace, plus
            # per-session jitter. Floor at 5 so nothing lands at zero.
            jitter = rng.uniform(-spread, spread)
            duration = max(5, round((base_minutes * speed) + jitter))

            # Scatter across clinic hours (08:00-16:00) over the history window.
            days_ago = rng.randint(0, DAYS_OF_HISTORY)
            start = (now - timedelta(days=days_ago)).replace(
                hour=rng.randint(8, 15),
                minute=rng.choice([0, 10, 15, 20, 30, 40, 45, 50]),
                second=0,
                microsecond=0,
            )
            end = start + timedelta(minutes=duration)

            db.add(models.Procedure(
                patient_id=patient.id,
                doctor_id=doctor.id,
                name=proc_name,
                session_date=start,
                is_completed=True,
                start_time=start,
                end_time=end,
                duration_minutes=duration,
            ))
            created += 1

    db.commit()
    return created


def resolve_profiles(db: Session, requested: list[str] | None, everything: bool) -> dict:
    """Decide which procedure names to seed, and with what duration profile.

    Defaults to PROCEDURE_PROFILES (the seeded presets). The analytics dropdown
    is wider than that -- it merges presets with the distinct names of every
    completed procedure -- so a name a doctor has actually performed once, such
    as "Aligner treatment planning", appears in the list with nothing behind it
    to plot. --procedure and --all cover those.
    """
    if not requested and not everything:
        return dict(PROCEDURE_PROFILES)

    names: set[str] = set(requested or [])
    if everything:
        names |= set(PROCEDURE_PROFILES)
        names |= {
            r[0] for r in db.query(models.ProcedurePreset.name)
            .filter(models.ProcedurePreset.is_active == True)  # noqa: E712
            .all()
        }
        names |= {
            r[0] for r in db.query(models.Procedure.name)
            .filter(models.Procedure.is_completed == True)  # noqa: E712
            .distinct().all()
        }

    # Unknown names get a middle-of-the-road profile rather than being skipped.
    return {n: PROCEDURE_PROFILES.get(n, (30, 9)) for n in sorted(names)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wipe", action="store_true",
        help="delete previously generated demo rows, THEN seed. Combining this "
             "with --procedure/--all wipes everything and re-seeds only what you "
             "named -- use --wipe-only if you just want the rows gone.",
    )
    parser.add_argument(
        "--wipe-only", action="store_true",
        help="delete previously generated demo rows and stop. Seeds nothing.",
    )
    parser.add_argument(
        "--procedure", action="append", dest="procedures", metavar="NAME",
        help="seed this procedure name too. Repeatable. "
             'e.g. --procedure "Aligner treatment planning"',
    )
    parser.add_argument(
        "--all", action="store_true", dest="everything",
        help="seed every name the analytics dropdown offers: the presets plus "
             "the distinct names of all completed procedures",
    )
    parser.add_argument(
        "--sessions", type=int, default=SESSIONS_PER_PROCEDURE, metavar="N",
        help=f"completed sessions per procedure (default {SESSIONS_PER_PROCEDURE})",
    )
    args = parser.parse_args()

    print(f"Target database: {engine.url.render_as_string(hide_password=True)}")

    # Make sure the tables and the duration columns exist before writing.
    Base.metadata.create_all(bind=engine)
    added = sync_schema()
    if added:
        print(f"Schema sync added: {', '.join(added)}")

    db = SessionLocal()
    try:
        if args.wipe or args.wipe_only:
            pats, procs = wipe_demo_data(db)
            print(f"Wiped {pats} demo patients and {procs} demo procedures.")
        if args.wipe_only:
            print("--wipe-only: stopping without seeding.")
            return 0

        doctors = get_doctors(db)
        if not doctors:
            print("No doctors found -- run 'python init_db.py' first.")
            return 1

        profiles = resolve_profiles(db, args.procedures, args.everything)
        if not profiles:
            print("Nothing to seed -- no presets, no completed procedures, and no "
                  "--procedure given.")
            return 1

        # The bail-out only applies to a plain re-run. Asking for specific names
        # (or --all) is a deliberate top-up, so only skip the names that already
        # have demo rows rather than refusing outright.
        explicit = bool(args.procedures or args.everything)
        already = {
            r[0] for r in db.query(models.Procedure.name)
            .join(models.Patient)
            .filter(models.Patient.mr_number.like(f"{DEMO_MR_PREFIX}%"))
            .distinct().all()
        }
        if already and not explicit:
            print(
                f"{len(already)} procedure type(s) already seeded. "
                "Re-run with --wipe to regenerate, or --all / --procedure to top up."
            )
            return 0

        skipped = sorted(already & set(profiles))
        profiles = {k: v for k, v in profiles.items() if k not in already}
        for name in skipped:
            print(f"  skipping (already seeded): {name}")
        if not profiles:
            print("Every requested procedure already has demo rows. Nothing to do.")
            return 0

        patients = ensure_demo_patients(db, doctors)
        count = build_sessions(db, doctors, patients, profiles, args.sessions)

        print(f"Created {len(patients)} demo patients and {count} completed procedures")
        print(f"across {len(profiles)} procedure types and {len(doctors)} doctors:")
        for name in profiles:
            print(f"    {args.sessions:>4} × {name}")
        print("\nOpen the HOD portal -> Procedure Analytics and pick any procedure.")
        print("Undo everything this script added with:  python seed_analytics_demo.py --wipe")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Seeding failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
