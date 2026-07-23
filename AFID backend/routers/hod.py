"""
routers/hod.py
HOD-specific endpoints:
  GET /hod/summary          – dashboard KPIs
  GET /hod/rooms            – operatory room list
  POST/PUT/PATCH /hod/rooms – manage rooms
  GET /hod/monitoring       – doctor patient counts & status
  GET /hod/timeline/{mr}    – patient procedure timeline
  POST/PATCH /hod/timeline  – manage timeline steps
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models, schemas

router = APIRouter(prefix="/hod", tags=["HOD Dashboard"])


# ── Summary KPIs ──────────────────────────────────────────────────────────────
@router.get("/summary", response_model=schemas.HODSummary)
def get_summary(db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    total_patients = db.query(models.Patient).count()
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
    return schemas.HODSummary(
        total_patients_today=total_patients,
        doctors_on_duty=doctors_on_duty,
        doctors_on_leave=doctors_on_leave,
        active_rooms=active_rooms,
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
    rows = []
    for doc in doctors:
        profile = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == doc.id).first()
        patient_count = (
            db.query(models.Patient)
            .filter(models.Patient.assigned_doctor == doc.full_name)
            .count()
        )
        rows.append(schemas.DoctorMonitorRow(
            name=doc.full_name,
            patients_today=patient_count,
            status=profile.status if profile else "Available",
        ))
    return rows


# ── Patient Timeline ──────────────────────────────────────────────────────────
@router.get("/timeline/{mr_number}", response_model=List[schemas.TimelineStepOut])
def get_patient_timeline(mr_number: str, db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin, models.UserRole.doctor))):
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
    step = models.PatientTimelineStep(patient_id=patient.id, **payload.model_dump())
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
