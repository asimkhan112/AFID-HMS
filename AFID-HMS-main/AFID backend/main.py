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

from routers import auth, patients, doctors, procedures, leaves, staff, hod, presets, procedure_analytics

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

# ── Collection-path slash normalisation ───────────────────────────────────────
# Routers expose their list/create endpoints at "/patients/", "/leaves/", … but
# clients (and edge proxies that normalise URLs) frequently send the bare
# "/patients". Starlette's default answer is a 307 redirect to the slashed form.
#
# That redirect is actively harmful here: the browser talks to the Vercel edge,
# so a redirect pointing at the Railway origin is CROSS-ORIGIN, and browsers
# strip the Authorization header on cross-origin redirects. The retried request
# arrives unauthenticated, comes back 401, and api.js reads that as an expired
# session and logs the user out.
#
# Rewriting the path in the ASGI scope resolves both spellings to the same
# endpoint with no redirect at all.
_COLLECTION_PATHS = frozenset({
    "/patients", "/procedures", "/leaves", "/staff", "/presets",
})


class CollectionSlashMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") in _COLLECTION_PATHS:
            scope = dict(scope)
            scope["path"] = scope["path"] + "/"
            raw = scope.get("raw_path")
            if raw:
                scope["raw_path"] = raw + b"/"
        await self.app(scope, receive, send)


app.add_middleware(CollectionSlashMiddleware)

# ── CORS – allow all origins for local development ────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
# NOTE: doctors.router carries BOTH the /doctors and /allocations endpoints.
# It used to be included a second time under the alias `allocations_router`,
# which registered every one of those routes twice and produced duplicate
# operation IDs in the OpenAPI schema (and duplicate entries in /docs).
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(doctors.router)
app.include_router(procedures.router)
app.include_router(leaves.router)
app.include_router(staff.router)
app.include_router(hod.router)
app.include_router(presets.router)
app.include_router(procedure_analytics.router)


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "app": settings.APP_TITLE, "version": settings.APP_VERSION}
