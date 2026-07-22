"""
routers/procedures.py
Full procedure workflow: create session, checklist, materials,
pharmacy dispensing, diagnostics ordering, clinical notes.
"""

from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(prefix="/procedures", tags=["Procedures"])


# ── Procedure sessions ────────────────────────────────────────────────────────
@router.get("/", response_model=List[schemas.ProcedureOut])
def list_procedures(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.Procedure).order_by(models.Procedure.session_date.desc()).all()


@router.post("/", response_model=schemas.ProcedureOut, status_code=201)
def create_procedure(payload: schemas.ProcedureCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    proc = models.Procedure(**payload.model_dump())
    db.add(proc)
    db.commit()
    db.refresh(proc)
    return proc


@router.get("/{proc_id}", response_model=schemas.ProcedureOut)
def get_procedure(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    proc = db.query(models.Procedure).filter(models.Procedure.id == proc_id).first()
    if not proc:
        raise HTTPException(404, "Procedure not found")
    return proc


@router.patch("/{proc_id}/complete", response_model=schemas.ProcedureOut)
def complete_procedure(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    proc = db.query(models.Procedure).filter(models.Procedure.id == proc_id).first()
    if not proc:
        raise HTTPException(404, "Procedure not found")
    proc.is_completed = True
    if proc.patient and not proc.patient.check_out_time:
        proc.patient.check_out_time = datetime.now()
    db.commit()
    db.refresh(proc)
    return proc


# ── Checklist ─────────────────────────────────────────────────────────────────
@router.get("/{proc_id}/checklist", response_model=List[schemas.ChecklistItemOut])
def get_checklist(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedureChecklist).filter(
        models.ProcedureChecklist.procedure_id == proc_id
    ).order_by(models.ProcedureChecklist.display_order).all()


@router.post("/{proc_id}/checklist", response_model=schemas.ChecklistItemOut, status_code=201)
def add_checklist_item(proc_id: int, payload: schemas.ChecklistItemCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = models.ProcedureChecklist(procedure_id=proc_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{proc_id}/checklist/{item_id}", response_model=schemas.ChecklistItemOut)
def update_checklist_item(proc_id: int, item_id: int, payload: schemas.ChecklistItemUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureChecklist).filter(
        models.ProcedureChecklist.id == item_id,
        models.ProcedureChecklist.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Checklist item not found")
    item.is_checked = payload.is_checked
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{proc_id}/checklist/{item_id}", status_code=204)
def delete_checklist_item(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureChecklist).filter(
        models.ProcedureChecklist.id == item_id,
        models.ProcedureChecklist.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Checklist item not found")
    db.delete(item)
    db.commit()


# ── Materials ─────────────────────────────────────────────────────────────────
@router.get("/{proc_id}/materials", response_model=List[schemas.MaterialOut])
def get_materials(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedureMaterial).filter(models.ProcedureMaterial.procedure_id == proc_id).all()


@router.post("/{proc_id}/materials", response_model=schemas.MaterialOut, status_code=201)
def add_material(proc_id: int, payload: schemas.MaterialCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = models.ProcedureMaterial(procedure_id=proc_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{proc_id}/materials/{item_id}", status_code=204)
def delete_material(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureMaterial).filter(
        models.ProcedureMaterial.id == item_id,
        models.ProcedureMaterial.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Material not found")
    db.delete(item)
    db.commit()


# ── Pharmacy ──────────────────────────────────────────────────────────────────
@router.get("/{proc_id}/pharmacy", response_model=List[schemas.PharmacyOut])
def get_pharmacy(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedurePharmacy).filter(models.ProcedurePharmacy.procedure_id == proc_id).all()


@router.post("/{proc_id}/pharmacy", response_model=schemas.PharmacyOut, status_code=201)
def add_pharmacy(proc_id: int, payload: schemas.PharmacyCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = models.ProcedurePharmacy(procedure_id=proc_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{proc_id}/pharmacy/{item_id}", status_code=204)
def delete_pharmacy(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedurePharmacy).filter(
        models.ProcedurePharmacy.id == item_id,
        models.ProcedurePharmacy.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Pharmacy entry not found")
    db.delete(item)
    db.commit()


# ── Diagnostics ───────────────────────────────────────────────────────────────
@router.get("/{proc_id}/diagnostics", response_model=List[schemas.DiagnosticOut])
def get_diagnostics(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedureDiagnostic).filter(models.ProcedureDiagnostic.procedure_id == proc_id).all()


@router.post("/{proc_id}/diagnostics", response_model=schemas.DiagnosticOut, status_code=201)
def add_diagnostic(proc_id: int, payload: schemas.DiagnosticCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = models.ProcedureDiagnostic(procedure_id=proc_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{proc_id}/diagnostics/{item_id}", status_code=204)
def delete_diagnostic(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureDiagnostic).filter(
        models.ProcedureDiagnostic.id == item_id,
        models.ProcedureDiagnostic.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Diagnostic not found")
    db.delete(item)
    db.commit()


# ── Clinical Notes ────────────────────────────────────────────────────────────
@router.get("/{proc_id}/notes", response_model=List[schemas.ClinicalNoteOut])
def get_notes(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ClinicalNote).filter(models.ClinicalNote.procedure_id == proc_id).order_by(models.ClinicalNote.created_at).all()


@router.post("/{proc_id}/notes", response_model=schemas.ClinicalNoteOut, status_code=201)
def add_note(proc_id: int, payload: schemas.ClinicalNoteCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    note = models.ClinicalNote(procedure_id=proc_id, **payload.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{proc_id}/notes/{note_id}", status_code=204)
def delete_note(proc_id: int, note_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    note = db.query(models.ClinicalNote).filter(
        models.ClinicalNote.id == note_id,
        models.ClinicalNote.procedure_id == proc_id,
    ).first()
    if not note:
        raise HTTPException(404, "Note not found")
    db.delete(note)
    db.commit()
