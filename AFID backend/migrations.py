"""
migrations.py
Additive schema sync for databases that already exist.

`Base.metadata.create_all` creates *missing tables*, but it never touches a
table that is already there -- so a column added to models.py is silently
absent from every existing database (local afid.db, Railway/Neon Postgres).
Every read of that table then dies with "no such column".

`sync_schema()` closes that gap: it compares the ORM metadata against the live
tables and issues `ALTER TABLE ... ADD COLUMN` for anything missing. It is
idempotent, so it is safe on every boot, and it works on both SQLite and
PostgreSQL.

Scope is deliberately narrow -- *additive only*. Dropped columns, renames, type
changes and backfills are not handled here; those need Alembic.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from database import Base, engine
import models  # noqa: F401  -- registers the tables on Base.metadata

logger = logging.getLogger(__name__)


def _ddl_type(column) -> str:
    """Render a model column's type as DDL for the connected dialect."""
    return column.type.compile(dialect=engine.dialect)


def sync_schema() -> list[str]:
    """Add any model columns that are missing from existing tables.

    Returns the list of "table.column" names that were added.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all() will build it in full

        live_columns = {c["name"] for c in inspector.get_columns(table.name)}

        for column in table.columns:
            if column.name in live_columns:
                continue

            # ADD COLUMN cannot satisfy a NOT NULL column on a populated table
            # unless the DDL carries a default. Skip and shout rather than
            # crash the whole boot.
            if not column.nullable and column.server_default is None:
                logger.warning(
                    "Cannot auto-add NOT NULL column %s.%s (no server_default); "
                    "needs a manual migration.",
                    table.name, column.name,
                )
                continue

            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {_ddl_type(column)}'
            if column.server_default is not None:
                ddl += f" DEFAULT {column.server_default.arg}"
            if not column.nullable:
                ddl += " NOT NULL"

            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except SQLAlchemyError as exc:
                logger.error("Failed to add %s.%s: %s", table.name, column.name, exc)
                continue

            added.append(f"{table.name}.{column.name}")
            logger.info("Schema sync: added column %s.%s", table.name, column.name)

    return added


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    changes = sync_schema()
    if changes:
        print(f"Added {len(changes)} column(s): {', '.join(changes)}")
    else:
        print("Schema already up to date.")
