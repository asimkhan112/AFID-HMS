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
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
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
    """
    Logout endpoint that exports the doctor's patient queue to Excel.
    Export occurs only after successful logout.
    If export fails, the error is logged and logout continues.
    """
    try:
        # Only export queue for doctors
        if current_user.role == models.UserRole.doctor:
            try:
                # Fetch all patients currently in this doctor's queue
                # Queue records are patients assigned to this doctor and still waiting/active
                doctor_name = current_user.full_name
                patients = db.query(models.Patient).filter(
                    models.Patient.assigned_doctor == doctor_name,
                    models.Patient.status.in_(
                        [models.PatientStatus.waiting, models.PatientStatus.active]
                    )
                ).all()
                
                # Convert patients to list of dictionaries for Excel export
                patient_data = []
                for patient in patients:
                    patient_data.append({
                        "mr_number": patient.mr_number,
                        "full_name": patient.full_name,
                        "gender": patient.gender,
                        "status": patient.status.value if patient.status else "",
                        "visit_date": patient.registered_at,
                        "visit_time": patient.registered_at,
                        "age": "N/A"  # Age not directly stored in model
                    })
                
                # Generate Excel file
                if patient_data:
                    filepath = generate_queue_excel(patient_data, doctor_name)
                    logger.info(
                        f"Successfully exported patient queue for doctor {doctor_name} "
                        f"to {filepath}. Total patients: {len(patient_data)}"
                    )
                else:
                    logger.info(
                        f"No patients in queue for doctor {doctor_name}. "
                        "No export file generated."
                    )
                    
            except Exception as export_error:
                # Log the error but don't fail the logout
                logger.error(
                    f"Failed to export patient queue for doctor {current_user.full_name}: "
                    f"{str(export_error)}",
                    exc_info=True
                )
        
        # Return success response
        return {"message": "Logout successful"}
        
    except Exception as e:
        logger.error(f"Logout failed for user {current_user.id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed. Please try again."
        )
