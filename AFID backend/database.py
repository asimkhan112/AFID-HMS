"""
database.py
SQLAlchemy engine, session factory, and Base declarative class.
All models import Base from here; all route handlers use get_db().
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# Supports both SQLite (local dev) and PostgreSQL (production).
# Normalize the legacy "postgres://" scheme that some hosts hand out to the
# "postgresql://" scheme SQLAlchemy 2.0 requires.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgres://"):
    _db_url = "postgresql://" + _db_url[len("postgres://"):]

# SQLite needs check_same_thread=False for FastAPI's threaded request handling
_connect_args = {}
if _db_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    _db_url,
    connect_args=_connect_args if _connect_args else {},
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Declarative base shared by all ORM models ─────────────────────────────────
Base = declarative_base()


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db():
    """Yield a database session, rolling back on exceptions."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
