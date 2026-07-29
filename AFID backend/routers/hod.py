"""
routers/hod.py
HOD-specific endpoints:
  GET /hod/summary          – dashboard KPIs
  GET /hod/rooms            – operatory room list
  POST/PUT/PATCH /hod/rooms – manage rooms
  GET /hod/monitoring       – doctor patient counts & status
  GET /hod/timeline/{mr}    – patient procedure timeline
  POST/PATCH /hod/timeline  – manage timeline steps
  GET /hod/doctors/{doctor_id}/stats – doctor case stats by period (1w, 1m, all)
  GET /hod/department-summary       – AI-generated department activity summary
"""

from typing import List, Optional
from datetime import datetime, date, time as dtime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from database import get_db
from auth import get_current_user, require_role
import models, schemas

router = APIRouter(prefix="/hod", tags=["HOD Dashboard"])


# ── Summary KPIs ──────────────────────────────────────────────────────────────
@router.get("/summary", response_model=schemas.HODSummary)
def get_summary(db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    # "Patients Today" means TODAY. This counted every patient ever registered,
    # so the card climbed forever and read as a lifetime total under a
    # today-scoped label.
    start_of_today = datetime.combine(date.today(), dtime.min)
    total_patients = (
        db.query(models.Patient)
        .filter(models.Patient.registered_at >= start_of_today)
        .count()
    )
    doctors_on_duty = (
        db.query(models.DoctorProfile)
        .filter(models.DoctorProfile.status != "On Leave")
        .count()
    )
    doctors_on_leave = (
        db.query(models.DoctorProfile)
        .filter(models.DoctorProfile.status == "On Leave")
        .count()
    )
    active_rooms = (
        db.query(models.OperatoryRoom)
        .filter(models.OperatoryRoom.status != models.RoomStatus.available)
        .count()
    )
    pending_leaves = (
        db.query(models.LeaveRequest)
        .filter(models.LeaveRequest.status == models.LeaveStatus.pending)
        .count()
    )
    return schemas.HODSummary(
        total_patients_today=total_patients,
        doctors_on_duty=doctors_on_duty,
        doctors_on_leave=doctors_on_leave,
        active_rooms=active_rooms,
        pending_leaves=pending_leaves,
    )


# ── Operatory Rooms ───────────────────────────────────────────────────────────
@router.get("/rooms", response_model=List[schemas.OperatoryRoomOut])
def list_rooms(db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    return db.query(models.OperatoryRoom).order_by(models.OperatoryRoom.room_name).all()


@router.post("/rooms", response_model=schemas.OperatoryRoomOut, status_code=201)
def create_room(payload: schemas.OperatoryRoomCreate, db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    existing = db.query(models.OperatoryRoom).filter(models.OperatoryRoom.room_name == payload.room_name).first()
    if existing:
        raise HTTPException(400, f"Room '{payload.room_name}' already exists")
    room = models.OperatoryRoom(**payload.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.patch("/rooms/{room_id}", response_model=schemas.OperatoryRoomOut)
def update_room(
    room_id: int,
    payload: schemas.OperatoryRoomUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    room = db.query(models.OperatoryRoom).filter(models.OperatoryRoom.id == room_id).first()
    if not room:
        raise HTTPException(404, "Room not found")
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(room, k, v)
    db.commit()
    db.refresh(room)
    return room


# ── Doctor Monitoring Matrix ──────────────────────────────────────────────────
@router.get("/monitoring", response_model=List[schemas.DoctorMonitorRow])
def doctor_monitoring(db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    doctors = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.doctor)
        .all()
    )
    start_of_today = datetime.combine(date.today(), dtime.min)
    rows = []
    for doc in doctors:
        profile = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == doc.id).first()
        # "Patients Today" means patients registered to this doctor TODAY. This
        # counted every patient ever assigned to them, so the column grew
        # without bound and never matched its own heading.
        patient_count = (
            db.query(models.Patient)
            .filter(
                models.Patient.assigned_doctor == doc.full_name,
                models.Patient.registered_at >= start_of_today,
            )
            .count()
        )
        active_cases = (
            db.query(models.Patient)
            .filter(
                models.Patient.assigned_doctor == doc.full_name,
                models.Patient.status == models.PatientStatus.active,
            )
            .count()
        )
        rows.append(schemas.DoctorMonitorRow(
            name=doc.full_name,
            patients_today=patient_count,
            total_active_cases=active_cases,
            status=profile.status if profile else "Available",
        ))
    return rows


# ── Patient Timeline ──────────────────────────────────────────────────────────
# NOTE: receptionist is deliberately included here (unlike the POST/PATCH
# timeline-step endpoints below, which stay hod/admin/doctor-only) --
# staff.html's reception portal has its own "Patient Timeline" page that
# reads from this exact endpoint. Before this fix, a receptionist's call
# always 403'd, and the frontend's try/catch silently treated that as "no
# steps", making a patient with a real, populated timeline indistinguishable
# from one with none at all -- the read side needs to be open to whichever
# roles have a legitimate UI that displays it; only the write side
# (creating/editing steps) should stay restricted.
@router.get("/timeline/{mr_number}", response_model=List[schemas.TimelineStepOut])
def get_patient_timeline(mr_number: str, db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin, models.UserRole.doctor, models.UserRole.receptionist))):
    patient = db.query(models.Patient).filter(models.Patient.mr_number == mr_number).first()
    if not patient:
        raise HTTPException(404, f"Patient with MR {mr_number} not found")
    return (
        db.query(models.PatientTimelineStep)
        .filter(models.PatientTimelineStep.patient_id == patient.id)
        .order_by(models.PatientTimelineStep.step_order)
        .all()
    )


@router.post("/timeline/{mr_number}/steps", response_model=schemas.TimelineStepOut, status_code=201)
def add_timeline_step(
    mr_number: str,
    payload: schemas.TimelineStepCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin, models.UserRole.doctor)),
):
    patient = db.query(models.Patient).filter(models.Patient.mr_number == mr_number).first()
    if not patient:
        raise HTTPException(404, f"Patient with MR {mr_number} not found")

    data = payload.model_dump()
    # Callers that just want to append a step (e.g. the doctor portal logging a
    # completed procedure) shouldn't have to know how many steps already exist,
    # so step_order 0 means "next in sequence".
    if not data.get("step_order"):
        highest = (
            db.query(models.PatientTimelineStep.step_order)
            .filter(models.PatientTimelineStep.patient_id == patient.id)
            .order_by(models.PatientTimelineStep.step_order.desc())
            .first()
        )
        data["step_order"] = (highest[0] if highest else 0) + 1

    step = models.PatientTimelineStep(patient_id=patient.id, **data)
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@router.patch("/timeline/steps/{step_id}", response_model=schemas.TimelineStepOut)
def update_timeline_step(
    step_id: int,
    payload: schemas.TimelineStepUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin, models.UserRole.doctor)),
):
    step = db.query(models.PatientTimelineStep).filter(models.PatientTimelineStep.id == step_id).first()
    if not step:
        raise HTTPException(404, "Timeline step not found")
    step.status = payload.status
    db.commit()
    db.refresh(step)
    return step


# ── Doctor Stats (1 week, 1 month, all time) ─────────────────────────────────
@router.get("/doctors/{doctor_id}/stats")
def get_doctor_stats(
    doctor_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    """Returns case statistics for a doctor by time period: past 1 week, past 1 month, all time."""
    doctor = db.query(models.User).filter(models.User.id == doctor_id, models.User.role == models.UserRole.doctor).first()
    if not doctor:
        raise HTTPException(404, "Doctor not found")

    profile = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == doctor.id).first()

    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def count_procedures(since: Optional[datetime] = None) -> int:
        q = db.query(models.Procedure).join(models.Patient).filter(
            models.Patient.assigned_doctor == doctor.full_name
        )
        if since:
            q = q.filter(models.Procedure.session_date >= since)
        return q.count()

    def count_patients(since: Optional[datetime] = None) -> int:
        q = db.query(models.Patient).filter(
            models.Patient.assigned_doctor == doctor.full_name
        )
        if since:
            q = q.filter(models.Patient.registered_at >= since)
        return q.count()

    cases_1w = count_procedures(week_ago)
    cases_1m = count_procedures(month_ago)
    cases_all = count_procedures(None)

    patients_1w = count_patients(week_ago)
    patients_1m = count_patients(month_ago)
    patients_all = count_patients(None)

    # Active / completed / waiting counts
    active_cases = (
        db.query(models.Patient)
        .filter(
            models.Patient.assigned_doctor == doctor.full_name,
            models.Patient.status == models.PatientStatus.active,
        )
        .count()
    )
    completed_cases = (
        db.query(models.Patient)
        .filter(
            models.Patient.assigned_doctor == doctor.full_name,
            models.Patient.status == models.PatientStatus.completed,
        )
        .count()
    )
    waiting_cases = (
        db.query(models.Patient)
        .filter(
            models.Patient.assigned_doctor == doctor.full_name,
            models.Patient.status == models.PatientStatus.waiting,
        )
        .count()
    )

    # Procedures completed
    completed_procedures = (
        db.query(models.Procedure).join(models.Patient).filter(
            models.Patient.assigned_doctor == doctor.full_name,
            models.Procedure.is_completed == True,
        ).count()
    )

    # Most common procedure
    top_procedure_row = (
        db.query(models.Procedure.name, func.count(models.Procedure.name).label("cnt"))
        .join(models.Patient)
        .filter(models.Patient.assigned_doctor == doctor.full_name)
        .group_by(models.Procedure.name)
        .order_by(func.count(models.Procedure.name).desc())
        .first()
    )
    top_procedure = top_procedure_row[0] if top_procedure_row else None

    return {
        "doctor_id": doctor.id,
        "doctor_name": doctor.full_name,
        "department": profile.department if profile else "Orthodontics",
        "qualifications": profile.qualifications if profile else None,
        "status": profile.status if profile else "Available",
        "shift": profile.shift if profile else None,
        "cases_last_week": cases_1w,
        "cases_last_month": cases_1m,
        "cases_all_time": cases_all,
        "patients_last_week": patients_1w,
        "patients_last_month": patients_1m,
        "patients_all_time": patients_all,
        "active_cases": active_cases,
        "completed_cases": completed_cases,
        "waiting_cases": waiting_cases,
        "completed_procedures": completed_procedures,
        "most_common_procedure": top_procedure,
    }


# ── Department AI Summary ────────────────────────────────────────────────────
@router.get("/department-summary")
def get_department_summary(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    """Generates a summary of what the department has done as a whole."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Total procedures
    total_procedures_all = db.query(models.Procedure).count()
    total_procedures_1m = db.query(models.Procedure).filter(models.Procedure.session_date >= month_ago).count()
    total_procedures_1w = db.query(models.Procedure).filter(models.Procedure.session_date >= week_ago).count()

    # Completed procedures
    completed_all = db.query(models.Procedure).filter(models.Procedure.is_completed == True).count()
    completed_1m = db.query(models.Procedure).filter(
        models.Procedure.is_completed == True,
        models.Procedure.session_date >= month_ago,
    ).count()
    completed_1w = db.query(models.Procedure).filter(
        models.Procedure.is_completed == True,
        models.Procedure.session_date >= week_ago,
    ).count()

    # Total patients
    total_patients_all = db.query(models.Patient).count()
    total_patients_1m = db.query(models.Patient).filter(models.Patient.registered_at >= month_ago).count()
    total_patients_1w = db.query(models.Patient).filter(models.Patient.registered_at >= week_ago).count()

    # Active / waiting / completed patients now
    active_patients = db.query(models.Patient).filter(models.Patient.status == models.PatientStatus.active).count()
    waiting_patients = db.query(models.Patient).filter(models.Patient.status == models.PatientStatus.waiting).count()
    completed_patients = db.query(models.Patient).filter(models.Patient.status == models.PatientStatus.completed).count()

    # Doctor counts
    total_doctors = db.query(models.User).filter(models.User.role == models.UserRole.doctor).count()
    doctors_on_leave = db.query(models.DoctorProfile).filter(models.DoctorProfile.status == "On Leave").count()
    doctors_active = total_doctors - doctors_on_leave

    # Total rooms and active rooms
    total_rooms = db.query(models.OperatoryRoom).count()
    active_rooms = db.query(models.OperatoryRoom).filter(models.OperatoryRoom.status != models.RoomStatus.available).count()

    # Most performed procedures (top 5)
    top_procedures = (
        db.query(models.Procedure.name, func.count(models.Procedure.name).label("cnt"))
        .filter(models.Procedure.session_date >= month_ago)
        .group_by(models.Procedure.name)
        .order_by(func.count(models.Procedure.name).desc())
        .limit(5)
        .all()
    )
    top_procedures_list = [{"name": p[0], "count": p[1]} for p in top_procedures]

    # Build a natural-language summary
    summary_parts = []

    summary_parts.append(f"Over the past week, the Orthodontics Department performed {total_procedures_1w} procedures ({completed_1w} completed). ")
    summary_parts.append(f"In the past month, {total_procedures_1m} procedures were performed ({completed_1m} completed). ")
    summary_parts.append(f"All-time, the department has completed {completed_all} out of {total_procedures_all} procedures. ")

    summary_parts.append(f"Patient volume: {total_patients_1w} patients seen in the past week, {total_patients_1m} in the past month. ")
    summary_parts.append(f"Currently, {active_patients} patients are active, {waiting_patients} are waiting, and {completed_patients} have been completed. ")

    if top_procedures_list:
        top_names = [f"{p['name']} ({p['count']} times)" for p in top_procedures_list]
        summary_parts.append(f"Most common procedures this month: {', '.join(top_names)}. ")

    summary_parts.append(f"Staffing: {doctors_active} doctors actively working, {doctors_on_leave} on leave out of {total_doctors} total. ")
    summary_parts.append(f"{active_rooms} out of {total_rooms} operatory rooms are currently in use. ")

    ai_summary = "".join(summary_parts)

    return {
        "summary": ai_summary,
        "generated_at": now.isoformat(),
        "stats": {
            "procedures_last_week": total_procedures_1w,
            "procedures_last_month": total_procedures_1m,
            "procedures_all_time": total_procedures_all,
            "completed_last_week": completed_1w,
            "completed_last_month": completed_1m,
            "completed_all_time": completed_all,
            "patients_last_week": total_patients_1w,
            "patients_last_month": total_patients_1m,
            "patients_all_time": total_patients_all,
            "active_patients": active_patients,
            "waiting_patients": waiting_patients,
            "completed_patients": completed_patients,
            "total_doctors": total_doctors,
            "doctors_on_leave": doctors_on_leave,
            "doctors_active": doctors_active,
            "total_rooms": total_rooms,
            "active_rooms": active_rooms,
            "top_procedures": top_procedures_list,
        }
    }