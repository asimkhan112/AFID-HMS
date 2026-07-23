"""
main.py
FastAPI application entry point.
Run with: uvicorn main:app --reload --port 8000
"""

import sys
import os
import logging
# Ensure the backend root is always on sys.path so routers can import
# config, database, models, schemas, auth regardless of CWD.
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

# Import models so SQLAlchemy registers them before create_all
import models  # noqa: F401

from routers import auth, patients, doctors, procedures, leaves, staff, hod, presets

# Doctor allocations router
from routers.doctors import router as allocations_router

# ── Create tables ─────────────────────────────────────────────────────────────
# Table creation is fully handled by SQLAlchemy models against PostgreSQL.
# For schema changes to an existing database, use Alembic migrations
# instead of ad-hoc ALTER TABLE hacks.
Base.metadata.create_all(bind=engine)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description="Backend API for AFID Hospital Management System (Orthodontics Dept)",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS – allow all origins for local development ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(doctors.router)
app.include_router(procedures.router)
app.include_router(leaves.router)
app.include_router(staff.router)
app.include_router(hod.router)
app.include_router(presets.router)
app.include_router(allocations_router)


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "app": settings.APP_TITLE, "version": settings.APP_VERSION}
