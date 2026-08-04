"""
routers/appointments.py
Booking and listing of future visits.

The staff portal's "Next Appt" button used to write the date, time and
procedure into a browser-side array and show a success toast. Nothing was sent
anywhere, so the booking disappeared on the next refresh. These endpoints give
that button somewhere real to write to.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from doctor_matching import resolve_doctor
import models, schemas

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _to_out(appt: models.Appointment) -> schemas.AppointmentOut:
    """Attach the patient's name/MR so queue tables need no second request."""
    return schemas.AppointmentOut(
        id=appt.id,
        patient_id=appt.patient_id,
        scheduled_for=appt.scheduled_for,
        procedure=appt.procedure,
        notes=appt.notes,
        doctor_id=appt.doctor_id,
        doctor_name=appt.doctor_name,
        status=appt.status.value if hasattr(appt.status, "value") else str(appt.status),
        created_at=appt.created_at,
        patient_name=appt.patient.full_name if appt.patient else None,
        patient_mr=appt.patient.mr_number if appt.patient else None,
    )


def _assign_doctor(db: Session, appt: models.Appointment,
                   doctor_id: Optional[int], doctor_name: Optional[str]) -> None:
    """Resolve the doctor id/name pair, preferring an explicit id."""
    if doctor_id is not None:
        doctor = db.query(models.User).filter(models.User.id == doctor_id).first()
        if doctor:
            appt.doctor_id, appt.doctor_name = doctor.id, doctor.full_name
            return
    if doctor_name is not None:
        doctor = resolve_doctor(db, doctor_name)
        appt.doctor_name = doctor_name
        appt.doctor_id = doctor.id if doctor else None


@router.get("/", response_model=List[schemas.AppointmentOut])
def list_appointments(
    patient_id: Optional[int] = None,
    doctor_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = Query(None, description="Inclusive lower bound"),
    date_to: Optional[datetime] = Query(None, description="Inclusive upper bound"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(models.Appointment)
    if patient_id is not None:
        q = q.filter(models.Appointment.patient_id == patient_id)
    if doctor_id is not None:
        q = q.filter(models.Appointment.doctor_id == doctor_id)
    if status:
        q = q.filter(models.Appointment.status == status.upper())
    if date_from:
        q = q.filter(models.Appointment.scheduled_for >= date_from)
    if date_to:
        q = q.filter(models.Appointment.scheduled_for <= date_to)
    return [_to_out(a) for a in q.order_by(models.Appointment.scheduled_for.asc()).all()]


@router.post("/", response_model=schemas.AppointmentOut, status_code=201)
def create_appointment(
    payload: schemas.AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    appt = models.Appointment(
        patient_id=payload.patient_id,
        scheduled_for=payload.scheduled_for,
        procedure=payload.procedure,
        notes=payload.notes,
        status=models.AppointmentStatus.scheduled,
        created_by_id=getattr(current_user, "id", None),
    )
    # Fall back to whoever the patient is already assigned to, which is what the
    # staff portal means by "under Dr X" when it books a follow-up.
    _assign_doctor(
        db, appt,
        payload.doctor_id if payload.doctor_id is not None else patient.assigned_doctor_id,
        payload.doctor_name if payload.doctor_name is not None else patient.assigned_doctor,
    )

    db.add(appt)
    db.commit()
    db.refresh(appt)
    return _to_out(appt)


@router.patch("/{appointment_id}", response_model=schemas.AppointmentOut)
def update_appointment(
    appointment_id: int,
    payload: schemas.AppointmentUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"]:
        valid = {s.value for s in models.AppointmentStatus}
        if data["status"].upper() not in valid:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown status '{data['status']}'. Expected one of: {', '.join(sorted(valid))}.",
            )
        appt.status = models.AppointmentStatus(data["status"].upper())

    for key in ("scheduled_for", "procedure", "notes"):
        if key in data:
            setattr(appt, key, data[key])
    if "doctor_id" in data or "doctor_name" in data:
        _assign_doctor(db, appt, data.get("doctor_id"), data.get("doctor_name"))

    db.commit()
    db.refresh(appt)
    return _to_out(appt)


@router.delete("/{appointment_id}", status_code=204)
def delete_appointment(appointment_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    appt = db.query(models.Appointment).filter(models.Appointment.id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(appt)
    db.commit()
