"""
routers/procedure_analytics.py
HOD procedure analytics endpoints:
  GET /hod/procedure-analytics/procedure-list  – distinct procedure names
  GET /hod/procedure-analytics/doctor-times    – per-doctor stats for a procedure
  GET /hod/procedure-analytics/completions     – every completed instance with doctor + time
  GET /hod/procedure-analytics/all-summary     – summary stats for ALL procedures
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, ConfigDict

from database import get_db
from auth import get_current_user, require_role
import models, schemas

router = APIRouter(prefix="/hod/procedure-analytics", tags=["HOD Procedure Analytics"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class DoctorProcedureTimeOut(BaseModel):
    doctor_name: str
    procedure_count: int
    avg_duration_minutes: float
    total_duration_minutes: int
    min_duration_minutes: Optional[int] = None
    max_duration_minutes: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class DoctorProcedureCompletion(BaseModel):
    doctor_name: str
    patient_mr: str
    patient_name: str
    session_date: str
    duration_minutes: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AllProcedureSummaryOut(BaseModel):
    """Summary stats for a single procedure across all doctors."""
    procedure_name: str
    total_performed: int
    total_completed: int
    avg_duration_minutes: Optional[float] = None
    min_duration_minutes: Optional[int] = None
    max_duration_minutes: Optional[int] = None
    unique_doctors: int

    model_config = ConfigDict(from_attributes=True)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/procedure-list", response_model=List[str])
def list_procedure_names(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    """Return a sorted list of all procedure names from both completed procedures and presets."""
    # Get procedure names from completed procedures
    proc_names = set(
        r[0] for r in db.query(models.Procedure.name)
        .filter(models.Procedure.is_completed == True)
        .distinct()
        .all()
    )
    # Get procedure names from presets
    preset_names = set(
        r[0] for r in db.query(models.ProcedurePreset.name)
        .filter(models.ProcedurePreset.is_active == True)
        .all()
    )
    # Merge both sets and sort
    all_names = sorted(proc_names | preset_names)
    return all_names


@router.get("/doctor-times", response_model=List[DoctorProcedureTimeOut])
def get_doctor_procedure_times(
    procedure_name: str = Query(..., description="The procedure name to analyse"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    """Return per-doctor statistics for a given procedure name."""
    if not procedure_name or not procedure_name.strip():
        raise HTTPException(400, "procedure_name query parameter is required")

    # Query completed procedures with the given name, joined with users for doctor name
    normalized_name = procedure_name.strip()
    results = (
        db.query(
            models.User.full_name,
            func.count(models.Procedure.id).label("procedure_count"),
            func.avg(models.Procedure.duration_minutes).label("avg_duration"),
            func.sum(models.Procedure.duration_minutes).label("total_duration"),
            func.min(models.Procedure.duration_minutes).label("min_duration"),
            func.max(models.Procedure.duration_minutes).label("max_duration"),
        )
        .join(models.Procedure, models.Procedure.doctor_id == models.User.id)
        .filter(
            func.lower(models.Procedure.name) == func.lower(normalized_name),
            models.Procedure.is_completed == True,
            models.Procedure.duration_minutes.isnot(None),
        )
        .group_by(models.User.id, models.User.full_name)
        .order_by(models.User.full_name)
        .all()
    )

    return [
        DoctorProcedureTimeOut(
            doctor_name=row.full_name,
            procedure_count=row.procedure_count,
            avg_duration_minutes=round(float(row.avg_duration), 1) if row.avg_duration else 0.0,
            total_duration_minutes=row.total_duration or 0,
            min_duration_minutes=row.min_duration,
            max_duration_minutes=row.max_duration,
        )
        for row in results
    ]


@router.get("/completions", response_model=List[DoctorProcedureCompletion])
def get_procedure_completions(
    procedure_name: str = Query(..., description="The procedure name to analyse"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    """Return every completed instance of a procedure with doctor name and duration."""
    if not procedure_name or not procedure_name.strip():
        raise HTTPException(400, "procedure_name query parameter is required")

    normalized_name = procedure_name.strip()
    results = (
        db.query(
            models.User.full_name.label("doctor_name"),
            models.Patient.mr_number,
            models.Patient.full_name.label("patient_name"),
            models.Procedure.session_date,
            models.Procedure.duration_minutes,
            models.Procedure.start_time,
            models.Procedure.end_time,
        )
        .join(models.Procedure, models.Procedure.doctor_id == models.User.id)
        .join(models.Patient, models.Procedure.patient_id == models.Patient.id)
        .filter(
            func.lower(models.Procedure.name) == func.lower(normalized_name),
            models.Procedure.is_completed == True,
            models.Procedure.duration_minutes.isnot(None),
        )
        .order_by(models.Procedure.session_date.desc())
        .all()
    )

    return [
        DoctorProcedureCompletion(
            doctor_name=row.doctor_name,
            patient_mr=row.mr_number,
            patient_name=row.patient_name,
            session_date=row.session_date.strftime("%Y-%m-%d %H:%M") if row.session_date else "—",
            duration_minutes=row.duration_minutes or 0,
            start_time=row.start_time.strftime("%H:%M") if row.start_time else None,
            end_time=row.end_time.strftime("%H:%M") if row.end_time else None,
        )
        for row in results
    ]


@router.get("/all-summary", response_model=List[AllProcedureSummaryOut])
def get_all_procedures_summary(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    """Return summary statistics for ALL procedures across all doctors."""
    results = (
        db.query(
            models.Procedure.name.label("procedure_name"),
            func.count(models.Procedure.id).label("total_performed"),
            func.sum(
                func.cast(models.Procedure.is_completed, func.Integer())
            ).label("total_completed"),
            func.avg(models.Procedure.duration_minutes).label("avg_duration"),
            func.min(models.Procedure.duration_minutes).label("min_duration"),
            func.max(models.Procedure.duration_minutes).label("max_duration"),
            func.count(func.distinct(models.Procedure.doctor_id)).label("unique_doctors"),
        )
        .group_by(models.Procedure.name)
        .order_by(models.Procedure.name)
        .all()
    )

    return [
        AllProcedureSummaryOut(
            procedure_name=row.procedure_name,
            total_performed=row.total_performed,
            total_completed=row.total_completed or 0,
            avg_duration_minutes=round(float(row.avg_duration), 1) if row.avg_duration else None,
            min_duration_minutes=row.min_duration,
            max_duration_minutes=row.max_duration,
            unique_doctors=row.unique_doctors,
        )
        for row in results
    ]