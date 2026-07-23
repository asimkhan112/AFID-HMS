"""
routers/auth.py
POST /auth/login   – returns JWT
POST /auth/register – create new user
GET  /auth/me      – return current user profile
POST /auth/logout  – logout and export patient queue
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from auth import hash_password, verify_password, create_access_token, get_current_user
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


@router.post("/register", response_model=schemas.UserOut, status_code=201)
def register(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Restrict admin account creation to admins/HOD only
    if payload.role == models.UserRole.admin and current_user.role not in (models.UserRole.admin, models.UserRole.hod):
        raise HTTPException(status_code=403, detail="Only admin/HOD can create admin accounts")
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = models.User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        staff_id=payload.staff_id,
    )
    db.add(user)
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