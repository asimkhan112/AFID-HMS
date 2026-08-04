"""
routers/patients.py
CRUD for patients + status transitions (WAITING → ACTIVE → COMPLETED)
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from doctor_matching import apply_doctor_assignment
import models, schemas

router = APIRouter(prefix="/patients", tags=["Patients"])


def _constraint_hint(exc: IntegrityError) -> str:
    """Turn a driver-level IntegrityError into something a receptionist can act on."""
    raw = str(getattr(exc, "orig", exc))
    for column, label in (("mr_number", "MR number"), ("file_number", "File number")):
        if column in raw:
            return f"{label} is already in use"
    return "a uniqueness or reference constraint was violated"


# Columns the caller may target explicitly. The portals show a "search by"
# dropdown; before this existed the dropdown was inert -- every query ran as a
# broad OR, so picking "File Number" and typing an MR number still opened the
# record, which made the selector look broken.
SEARCH_FIELDS = {
    "mr_number":   models.Patient.mr_number,
    "file_number": models.Patient.file_number,
    "name":        models.Patient.full_name,
    "full_name":   models.Patient.full_name,
    "cnic":        models.Patient.cnic,
    "rank":        models.Patient.rank,
}


@router.get("/", response_model=List[schemas.PatientOut])
def list_patients(
    status: Optional[models.PatientStatus] = None,
    search: Optional[str] = Query(None, description="Search term"),
    field: Optional[str] = Query(
        None,
        description=f"Restrict search to one column. One of: {', '.join(sorted(SEARCH_FIELDS))}. "
                    "Omit to search all of them.",
    ),
    assigned_doctor_id: Optional[int] = Query(
        None, description="Only patients assigned to this doctor account"
    ),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(models.Patient)
    if status:
        q = q.filter(models.Patient.status == status)
    if assigned_doctor_id is not None:
        q = q.filter(models.Patient.assigned_doctor_id == assigned_doctor_id)
    if search:
        term = f"%{search}%"
        if field:
            column = SEARCH_FIELDS.get(field)
            if column is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown search field '{field}'. "
                           f"Expected one of: {', '.join(sorted(SEARCH_FIELDS))}.",
                )
            q = q.filter(column.ilike(term))
        else:
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
    # file_number is UNIQUE in the schema too. Only mr_number used to be checked
    # here, so a repeated file number reached the database, raised IntegrityError
    # and surfaced to the receptionist as a bare "HTTP 500" with no clue which
    # field was at fault.
    if db.query(models.Patient).filter(models.Patient.file_number == payload.file_number).first():
        raise HTTPException(
            status_code=400,
            detail=f"File number '{payload.file_number}' is already assigned to another patient",
        )

    data = payload.model_dump()
    # Set via apply_doctor_assignment so the id/name pair cannot drift apart.
    data.pop("assigned_doctor", None)
    data.pop("assigned_doctor_id", None)
    patient = models.Patient(**data)
    apply_doctor_assignment(db, patient, payload.model_dump())

    db.add(patient)
    try:
        db.commit()
    except IntegrityError as exc:
        # Backstop for any other unique/FK constraint, so the client always gets
        # a readable 400 rather than a 500.
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not create patient: {_constraint_hint(exc)}")
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

    data = payload.model_dump(exclude_unset=True)
    if "file_number" in data and data["file_number"] != patient.file_number:
        clash = (
            db.query(models.Patient)
            .filter(models.Patient.file_number == data["file_number"],
                    models.Patient.id != patient_id)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=400,
                detail=f"File number '{data['file_number']}' is already assigned to another patient",
            )

    for k, v in data.items():
        if k in ("assigned_doctor", "assigned_doctor_id"):
            continue  # handled together below, so the pair stays consistent
        setattr(patient, k, v)
    apply_doctor_assignment(db, patient, data)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not update patient: {_constraint_hint(exc)}")
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
    if patient.status == models.PatientStatus.active and not patient.check_in_time:
        patient.check_in_time = datetime.now()
    if patient.status == models.PatientStatus.completed and not patient.check_out_time:
        patient.check_out_time = datetime.now()
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
