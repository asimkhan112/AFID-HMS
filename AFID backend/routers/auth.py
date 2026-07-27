"""
routers/auth.py
POST /auth/login   – returns JWT
POST /auth/register – create new user
GET  /auth/me      – return current user profile
POST /auth/logout  – logout and export patient queue
"""

import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    get_current_user_optional,
)
from excel_exporter import generate_queue_excel
import models, schemas

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    token = create_access_token({"sub": str(user.id), "role": user.role.value})
    return {"access_token": token, "token_type": "bearer"}


# NOTE: authentication here is OPTIONAL by design. This endpoint backs two
# separate flows:
#   1. the "Registration" tab on Login.html, where the caller has no token yet
#   2. "Register Doctor" inside the staff portal, where a receptionist does
# It used to require get_current_user, so flow (1) always 401'd -- and because
# api.js treats any 401 as an expired session, the login page silently wiped
# local storage and bounced back to itself, which is what made freshly
# "registered" accounts impossible to log in with (they were never created).
@router.post("/register", response_model=schemas.UserOut, status_code=201)
def register(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    role = payload.role
    if isinstance(role, str):
        try:
            role = models.UserRole(role.strip().lower())
        except ValueError:
            valid = ", ".join(r.value for r in models.UserRole)
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid}")

    # Privileged roles can never be self-provisioned by an anonymous caller.
    if role in (models.UserRole.admin, models.UserRole.hod):
        if current_user is None or current_user.role not in (models.UserRole.admin, models.UserRole.hod):
            raise HTTPException(status_code=403, detail="Only admin/HOD can create admin or HOD accounts")

    email = (payload.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if not payload.password or len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    staff_id = (payload.staff_id or "").strip() or None
    if staff_id and db.query(models.User).filter(models.User.staff_id == staff_id).first():
        raise HTTPException(status_code=400, detail=f"Staff ID '{staff_id}' is already assigned")

    full_name = (payload.full_name or "").strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Full name is required")
    # Doctor accounts are matched to patients by full_name across the whole app
    # (patients.assigned_doctor is a name string), so two doctors sharing a name
    # would silently cross-wire each other's queues.
    if role == models.UserRole.doctor:
        clash = (
            db.query(models.User)
            .filter(models.User.role == models.UserRole.doctor, models.User.full_name == full_name)
            .first()
        )
        if clash:
            raise HTTPException(status_code=400, detail=f"A doctor named '{full_name}' already exists")

    user = models.User(
        full_name=full_name,
        email=email,
        hashed_password=hash_password(payload.password),
        role=role,
        staff_id=staff_id,
    )
    db.add(user)
    db.flush()

    # Every doctor needs a DoctorProfile row: /hod/summary and /hod/monitoring
    # both read doctor duty/leave status from that table, so a doctor without
    # one is invisible to the HOD dashboard.
    if role == models.UserRole.doctor:
        db.add(models.DoctorProfile(
            user_id=user.id,
            department="Orthodontics",
            status="Available",
        ))

    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/logout", status_code=200)
def logout(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    export_status = "no_queue"
    try:
        if current_user.role == models.UserRole.doctor:
            try:
                doctor_name = current_user.full_name
                patients = db.query(models.Patient).filter(
                    models.Patient.assigned_doctor == doctor_name,
                    models.Patient.status.in_(
                        [models.PatientStatus.waiting, models.PatientStatus.active]
                    )
                ).all()
                
                patient_data = []
                for patient in patients:
                    patient_data.append({
                        "mr_number": patient.mr_number,
                        "full_name": patient.full_name,
                        "gender": patient.gender,
                        "status": patient.status.value if patient.status else "",
                        "visit_date": patient.registered_at,
                        "visit_time": patient.registered_at,
                        "age": "N/A"
                    })
                
                if patient_data:
                    filepath = generate_queue_excel(patient_data, doctor_name)
                    export_status = f"exported:{len(patient_data)}"
                else:
                    export_status = "empty_queue"
            except Exception as export_error:
                export_status = f"error:{str(export_error)}"
    except Exception:
        pass
    
    return {"message": "Logout successful", "export_status": export_status}