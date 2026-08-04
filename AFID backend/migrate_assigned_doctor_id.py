"""
migrate_assigned_doctor_id.py

Adds patients.assigned_doctor_id (FK -> users.id) and backfills it from the
existing free-text patients.assigned_doctor column.

Why this exists
---------------
Patient ownership used to be decided by comparing display names: the doctor
portal checked `patient.assigned_doctor == user.full_name`. Any spelling drift
broke it -- a patient stored as "Dr Hira" was invisible to the account named
"Dr. Hira Z.", who then got told "Not Your Patient" about their own patient.

Backfill strategy, in descending order of confidence:
  1. exact match on full_name
  2. case/punctuation/whitespace-insensitive match ("dr hira z" == "Dr. Hira Z.")
  3. unambiguous surname+initial match, only when it resolves to exactly ONE
     doctor -- ambiguous matches are deliberately left NULL rather than guessed

Rows that resolve to nothing keep assigned_doctor and get a NULL id. They are
reported at the end so they can be reassigned by hand. Nothing is deleted and
no existing column is dropped, so this is safe to re-run and easy to revert.

Relationship to migrations.sync_schema()
----------------------------------------
sync_schema() already adds the *column* on boot, but it is additive-only and
renders the column TYPE alone -- it emits no FOREIGN KEY constraint and no
index (see _ddl_type there, and its own docstring: "backfills are not handled
here"). So on a database that has already booted, assigned_doctor_id exists as
a bare INTEGER. This script adds the missing constraint and index, then does
the backfill sync_schema explicitly leaves alone.

Usage:
    .venv/bin/python migrate_assigned_doctor_id.py            # apply
    .venv/bin/python migrate_assigned_doctor_id.py --dry-run  # report only
"""

import re
import sys
from collections import defaultdict

from sqlalchemy import inspect, text

from database import engine, SessionLocal

DRY_RUN = "--dry-run" in sys.argv


def normalise(name: str) -> str:
    """'Dr. Hira Z.' -> 'hira z'  --  strips title, punctuation, extra spaces."""
    if not name:
        return ""
    s = name.strip().lower()
    s = re.sub(r"^(dr|doctor|prof|professor)\b\.?\s*", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def surname_key(normalised: str) -> str:
    """'hira z' -> 'hira'  --  first token, used only for the last-resort pass."""
    return normalised.split(" ")[0] if normalised else ""


def ensure_column_and_constraints() -> None:
    """Make the column, its index and its FK constraint all exist.

    sync_schema() may have created the column already, but as a bare INTEGER --
    so the index and the FK are checked independently of the column itself.
    """
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("patients")}

    if "assigned_doctor_id" not in cols:
        if DRY_RUN:
            print("· would ADD COLUMN patients.assigned_doctor_id INTEGER")
        else:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE patients ADD COLUMN assigned_doctor_id INTEGER"
                ))
            print("✓ added column patients.assigned_doctor_id")
    else:
        print("· column patients.assigned_doctor_id already present")

    index_names = {ix["name"] for ix in insp.get_indexes("patients")}
    if "ix_patients_assigned_doctor_id" not in index_names:
        if DRY_RUN:
            print("· would CREATE INDEX ix_patients_assigned_doctor_id")
        else:
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_patients_assigned_doctor_id "
                    "ON patients (assigned_doctor_id)"
                ))
            print("✓ created index ix_patients_assigned_doctor_id")
    else:
        print("· index ix_patients_assigned_doctor_id already present")

    # SQLite cannot ALTER TABLE ADD CONSTRAINT at all; the FK is only
    # enforceable on Postgres, which is what production runs.
    if engine.dialect.name != "postgresql":
        print(f"· {engine.dialect.name}: skipping FK constraint (not supported by ALTER)")
        return

    fk_cols = {tuple(fk["constrained_columns"]) for fk in insp.get_foreign_keys("patients")}
    if ("assigned_doctor_id",) in fk_cols:
        print("· FK patients.assigned_doctor_id -> users.id already present")
        return
    if DRY_RUN:
        print("· would ADD CONSTRAINT fk_patients_assigned_doctor_id -> users(id)")
        return
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE patients ADD CONSTRAINT fk_patients_assigned_doctor_id "
            "FOREIGN KEY (assigned_doctor_id) REFERENCES users(id) ON DELETE SET NULL"
        ))
    print("✓ added FK constraint fk_patients_assigned_doctor_id")


def backfill() -> None:
    db = SessionLocal()
    try:
        doctors = list(db.execute(text(
            "SELECT id, full_name FROM users WHERE role = 'doctor' AND is_active = true"
        )))
        if not doctors:
            print("! no active doctor accounts found — nothing to backfill against")
            return

        by_exact = {d[1]: d[0] for d in doctors}
        by_norm = {normalise(d[1]): d[0] for d in doctors}

        # Surname buckets: only usable when a surname maps to exactly one doctor.
        buckets = defaultdict(list)
        for d in doctors:
            buckets[surname_key(normalise(d[1]))].append(d[0])
        by_surname = {k: v[0] for k, v in buckets.items() if len(v) == 1}

        rows = list(db.execute(text(
            "SELECT id, mr_number, full_name, assigned_doctor FROM patients "
            "WHERE assigned_doctor_id IS NULL"
        )))
        if not rows:
            print("· every patient already has assigned_doctor_id — nothing to do")
            return

        resolved, unresolved = [], []
        for pid, mr, pname, assigned in rows:
            norm = normalise(assigned or "")
            doc_id = (
                by_exact.get((assigned or "").strip())
                or by_norm.get(norm)
                or by_surname.get(surname_key(norm))
            )
            (resolved if doc_id else unresolved).append((pid, mr, pname, assigned, doc_id))

        for pid, _, _, _, doc_id in resolved:
            if not DRY_RUN:
                db.execute(
                    text("UPDATE patients SET assigned_doctor_id = :d WHERE id = :p"),
                    {"d": doc_id, "p": pid},
                )
        if not DRY_RUN:
            db.commit()

        verb = "would link" if DRY_RUN else "linked"
        print(f"✓ {verb} {len(resolved)}/{len(rows)} patients to a doctor account")

        if unresolved:
            print(f"\n! {len(unresolved)} patient(s) could NOT be matched and were left NULL.")
            print("  They stay visible to HOD/staff but will not appear in any doctor's queue")
            print("  until reassigned:\n")
            for pid, mr, pname, assigned, _ in unresolved:
                print(f"    id={pid:<4} {mr:<12} {pname!r:<28} assigned_doctor={assigned!r}")
    finally:
        db.close()


if __name__ == "__main__":
    print(f"{'DRY RUN — no changes will be written' if DRY_RUN else 'APPLYING MIGRATION'}\n")
    ensure_column_and_constraints()
    print()
    backfill()
    print("\nDone.")
