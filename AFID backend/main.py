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
from fastapi.staticfiles import StaticFiles

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

from routers import auth, patients, doctors, procedures, leaves, staff, hod, presets, procedure_analytics, lab
from routers import upload as upload_router  # noqa: E402

# ── Create tables ─────────────────────────────────────────────────────────────
# create_all() builds any table that does not exist yet, but deliberately leaves
# existing tables alone -- so a newly added model column would be missing from
# every database that predates it. sync_schema() adds those columns.
#
# Additive changes only. Renames, type changes and drops still need a real
# migration tool (Alembic).
Base.metadata.create_all(bind=engine)

from migrations import sync_schema  # noqa: E402  -- must follow create_all

_added_columns = sync_schema()
if _added_columns:
    logger.info("Schema sync added: %s", ", ".join(_added_columns))

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
    "/patients", "/procedures", "/leaves", "/staff", "/presets", "/lab", "/upload",
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
app.include_router(lab.router)
app.include_router(upload_router.router)


# ── Static uploads ─────────────────────────────────────────────────────────────
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "app": settings.APP_TITLE, "version": settings.APP_VERSION}
