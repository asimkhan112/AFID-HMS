"""
routers/patients.py
CRUD for patients + status transitions (WAITING → ACTIVE → COMPLETED)
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("/", response_model=List[schemas.PatientOut])
def list_patients(
    status: Optional[models.PatientStatus] = None,
    search: Optional[str] = Query(None, description="Search by name, MR, CNIC, or file number"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(models.Patient)
    if status:
        q = q.filter(models.Patient.status == status)
    if search:
        term = f"%{search}%"
        q = q.filter(
            models.Patient.full_name.ilike(term)
            | models.Patient.mr_number.ilike(term)
            | models.Patient.cnic.ilike(term)
            | models.Patient.file_number.ilike(term)
            | models.Patient.rank.ilike(term)
        )
    return q.order_by(models.Patient.registered_at.desc()).all()


@router.post("/", response_model=schemas.PatientOut, status_code=201)
def create_patient(
    payload: schemas.PatientCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if db.query(models.Patient).filter(models.Patient.mr_number == payload.mr_number).first():
        raise HTTPException(status_code=400, detail="MR number already exists")
    patient = models.Patient(**payload.model_dump(), check_in_time=datetime.utcnow())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("/{patient_id}", response_model=schemas.PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}/procedures", response_model=schemas.PatientWithProceduresOut)
def get_patient_with_procedures(patient_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Build procedure history with counts
    procedures_out = []
    for proc in patient.procedures:
        procedures_out.append(schemas.ProcedureHistoryOut(
            id=proc.id,
            name=proc.name,
            session_date=proc.session_date,
            is_completed=proc.is_completed,
            checklist_count=len(proc.checklist),
            checked_count=sum(1 for c in proc.checklist if c.is_checked),
            materials_count=len(proc.materials),
            pharmacy_count=len(proc.pharmacy),
            diagnostics_count=len(proc.diagnostics),
            notes_count=len(proc.notes),
        ))
    
    return schemas.PatientWithProceduresOut(
        **{k: getattr(patient, k) for k in schemas.PatientOut.model_fields.keys()},
        procedures=procedures_out,
    )


@router.get("/lookup/mr/{mr_number}", response_model=schemas.PatientOut)
def get_by_mr(mr_number: str, db: Session = Depends(get_db), _=Depends(get_current_user)):
    patient = db.query(models.Patient).filter(models.Patient.mr_number == mr_number).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.put("/{patient_id}", response_model=schemas.PatientOut)
def update_patient(
    patient_id: int,
    payload: schemas.PatientCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(patient, k, v)
    db.commit()
    db.refresh(patient)
    return patient


@router.patch("/{patient_id}/status", response_model=schemas.PatientOut)
def update_status(
    patient_id: int,
    payload: schemas.PatientStatusUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient.status = payload.status
    if payload.status == models.PatientStatus.completed and not patient.check_out_time:
        patient.check_out_time = datetime.utcnow()
    db.commit()
    db.refresh(patient)
    return patient


@router.delete("/{patient_id}", status_code=204)
def delete_patient(patient_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    db.delete(patient)
    db.commit()
