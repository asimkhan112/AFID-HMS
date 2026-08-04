"""
migrate_sqlite_to_postgres.py
Copy every row from the local SQLite database into the configured PostgreSQL one.

`migrate_to_postgres.py` only *installs* PostgreSQL and creates the database; it
never moves data. This script is the missing half.

    python migrate_sqlite_to_postgres.py                 # dry run: report only
    python migrate_sqlite_to_postgres.py --apply         # copy, skipping non-empty tables
    python migrate_sqlite_to_postgres.py --apply --replace   # wipe target tables first

Tables are walked in SQLAlchemy's foreign-key-sorted order so parents land before
children. Both sides share models.py's table definitions, so reading through the
source engine returns proper Python values (datetimes, dates, booleans, enum
names) and the target insert re-encodes them for PostgreSQL.

Afterwards each PostgreSQL identity sequence is bumped past the highest copied id
-- without that the first INSERT from the app would collide with a migrated row.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, select, func, text

from config import settings
from database import Base
import models  # noqa: F401  -- registers tables on Base.metadata

SQLITE_URL = "sqlite:///./afid.db"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually write (default is a dry run)")
    ap.add_argument("--replace", action="store_true", help="delete existing target rows first")
    ap.add_argument("--source", default=SQLITE_URL, help=f"source URL (default {SQLITE_URL})")
    args = ap.parse_args()

    target_url = settings.DATABASE_URL
    if target_url.startswith("sqlite"):
        print(f"Refusing to run: DATABASE_URL is still SQLite ({target_url}).")
        print("Point .env at PostgreSQL first.")
        return 1

    src_path = args.source.replace("sqlite:///", "")
    if args.source.startswith("sqlite") and not os.path.exists(src_path):
        print(f"Source database not found: {src_path}")
        return 1

    source = create_engine(args.source)
    target = create_engine(target_url)

    # The app creates these on boot, but running this script standalone should work too.
    Base.metadata.create_all(bind=target)

    copied, skipped, empty = {}, {}, []

    with source.connect() as sconn, target.begin() as tconn:
        for table in Base.metadata.sorted_tables:
            try:
                rows = [dict(r) for r in sconn.execute(select(table)).mappings()]
            except Exception as exc:                      # table absent from the old DB
                print(f"  ! {table.name}: unreadable in source ({exc.__class__.__name__}); skipped")
                continue

            if not rows:
                empty.append(table.name)
                continue

            existing = tconn.execute(select(func.count()).select_from(table)).scalar_one()
            if existing and not args.replace:
                skipped[table.name] = (len(rows), existing)
                continue

            if args.apply:
                if args.replace and existing:
                    tconn.execute(table.delete())
                tconn.execute(table.insert(), rows)
            copied[table.name] = len(rows)

        # Sequences only exist on PostgreSQL; keep them ahead of the copied ids.
        if args.apply and target.dialect.name == "postgresql":
            for table in Base.metadata.sorted_tables:
                if table.name not in copied or "id" not in table.c:
                    continue
                tconn.execute(text(
                    "SELECT setval(pg_get_serial_sequence(:t, 'id'), "
                    "COALESCE((SELECT MAX(id) FROM " + table.name + "), 1), true)"
                ), {"t": table.name})

    verb = "Copied" if args.apply else "Would copy"
    total = sum(copied.values())
    print(f"\n{verb} {total} row(s) across {len(copied)} table(s) -> {target.url.render_as_string(hide_password=True)}")
    for name, n in copied.items():
        print(f"  {verb.lower():10} {n:>5}  {name}")
    if skipped:
        print("\nSkipped (target already has rows; use --replace to overwrite):")
        for name, (n, have) in skipped.items():
            print(f"  {n:>5} source row(s), {have} already present  {name}")
    if empty:
        print(f"\nEmpty in source: {', '.join(empty)}")
    if not args.apply:
        print("\nDry run -- nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
