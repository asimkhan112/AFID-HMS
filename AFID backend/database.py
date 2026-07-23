"""
database.py
SQLAlchemy engine, session factory, and Base declarative class.
All models import Base from here; all route handlers use get_db().
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# PostgreSQL only -- no SQLite fallback / check_same_thread shim needed.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Declarative base shared by all ORM models ─────────────────────────────────
Base = declarative_base()


# ── FastAPI dependency ────────────────────────────────────────────────────────
def get_db():
    """Yield a database session and ensure it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
