"""
cleanup_qa_test_data.py

Deletes QA/Playwright-seeded test data from the shared dev database.

WHY: every spec file in tests/ seeds patients, presets, leave requests, rooms,
allocations, and users with a "QA" / "QA-MR-" / "QA-F-" / "qa-...@afid.mil"
prefix (see uniqueId() in tests/fixtures/helpers.ts and each spec file's own
uniqueId(...) calls). None of that gets cleaned up automatically, so it piles
up across every test run in this shared dev database and eventually corrupts
tests that assert on counts or "empty queue" state (e.g. a doctor's
WAITING/ACTIVE queue is never really empty once thousands of old QA patients
have accumulated against that doctor).

This script is READ-ONLY by default -- it just reports what it *would*
delete. Nothing is deleted unless you pass --confirm.

Usage (run from the "AFID backend" folder, with the venv active, same as
you'd run any other one-off script in this folder e.g. show_tables.py):

    python cleanup_qa_test_data.py            # dry run: show counts only
    python cleanup_qa_test_data.py --confirm   # actually delete

Real accounts used by the test suite itself (doctor@afid.mil, hod@afid.mil,
reception@afid.mil -- see tests/fixtures/helpers.ts CREDS) are never touched;
their emails don't match the qa-...@afid.mil pattern this script looks for.
"""

import argparse
import sys

from sqlalchemy import create_engine, text

try:
    # Reuse the project's own settings (respects AFID backend/.env if present),
    # same as database.py / main.py do.
    from config import settings
    DATABASE_URL = settings.DATABASE_URL
except Exception:
    # Fallback to the documented default if config.py can't be imported for
    # some reason (e.g. script run from the wrong working directory).
    DATABASE_URL = "postgresql://afid_user:afid_pass@localhost:5432/afid_db"

if not DATABASE_URL.startswith("postgresql"):
    print(f"Refusing to run: DATABASE_URL does not look like Postgres ({DATABASE_URL!r}).")
    sys.exit(1)

# Each entry: (label, table, WHERE-clause SQL). Patients are deleted first --
# ON DELETE CASCADE (defined in models.py's ForeignKey(..., ondelete="CASCADE"))
# takes care of their procedures, procedure materials/pharmacy/diagnostics/
# notes, and patient_timeline_steps automatically. Same for procedure_presets
# cascading to its own materials/pharmacy/diagnostics, and users cascading to
# their own leave_requests.
TARGETS = [
    (
        "patients (and everything cascading from them: procedures, "
        "materials, pharmacy, diagnostics, notes, timeline steps)",
        "patients",
        "mr_number LIKE 'QA-MR-%' OR file_number LIKE 'QA-F-%' OR full_name LIKE 'QA %'",
    ),
    (
        "procedure_presets (and their materials/pharmacy/diagnostics)",
        "procedure_presets",
        "name LIKE 'QA %'",
    ),
    (
        "leave_requests (any not already removed via a QA user above)",
        "leave_requests",
        "reason LIKE 'QA %'",
    ),
    (
        "operatory_rooms",
        "operatory_rooms",
        "room_name LIKE 'QA-Room%' OR room_name LIKE 'QA %'",
    ),
    (
        "doctor_allocations",
        "doctor_allocations",
        "doctor_name LIKE '%QA%'",
    ),
    (
        "staff_members (tests/hod/staff-management.spec.ts already deletes "
        "its own -- this is just a safety net for any left behind by a "
        "failed run)",
        "staff_members",
        "name LIKE 'QA %'",
    ),
    (
        "users (and, via cascade, any of their own leave_requests) -- real "
        "CREDS accounts (doctor@afid.mil / hod@afid.mil / reception@afid.mil) "
        "are never touched; their emails don't match this pattern",
        "users",
        "email LIKE 'qa-%@afid.mil'",
    ),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete the matched rows. Without this flag, only counts are shown.",
    )
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)

    print(f"Database: {DATABASE_URL.split('@')[-1]}")
    print(f"Mode: {'DELETE (--confirm passed)' if args.confirm else 'DRY RUN (pass --confirm to actually delete)'}")
    print()

    total = 0
    with engine.connect() as conn:
        for label, table, where in TARGETS:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {where}")).scalar()
            total += count
            print(f"  {table:<20} {count:>6} row(s) matched  -- {label}")

        print()
        if not args.confirm:
            print(f"Total: {total} row(s) would be deleted. Re-run with --confirm to actually delete them.")
            return

        if total == 0:
            print("Nothing to delete.")
            return

    # Separate connection/transaction for the delete step: engine.begin()
    # opens a fresh connection and transaction, auto-committing on a clean
    # exit or auto-rolling-back on any exception -- avoids mixing with the
    # read-only connection above, which SQLAlchemy 2.x's "autobegin" had
    # already put into its own (uncommitted) implicit transaction.
    try:
        with engine.begin() as conn:
            for label, table, where in TARGETS:
                result = conn.execute(text(f"DELETE FROM {table} WHERE {where}"))
                print(f"  Deleted {result.rowcount} row(s) from {table}")
        print()
        print(f"Done. Deleted {total} row(s) total (some may have already cascaded away with an earlier table).")
    except Exception:
        print("Error during delete -- rolled back, nothing was changed.")
        raise


if __name__ == "__main__":
    main()
