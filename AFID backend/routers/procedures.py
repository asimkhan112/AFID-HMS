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


def _resolve_doctor_id(db: Session, patient_id) -> int | None:
    """Map a patient's assigned_doctor name onto a doctor user id, if we can."""
    if not patient_id:
        return None
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient or not patient.assigned_doctor:
        return None
    doctor = (
        db.query(models.User)
        .filter(
            models.User.full_name == patient.assigned_doctor,
            models.User.role == models.UserRole.doctor,
        )
        .first()
    )
    return doctor.id if doctor else None


# ── Procedure sessions ────────────────────────────────────────────────────────
@router.get("/", response_model=List[schemas.ProcedureOut])
def list_procedures(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.Procedure).order_by(models.Procedure.session_date.desc()).all()


@router.post("/", response_model=schemas.ProcedureOut, status_code=201)
def create_procedure(
    payload: schemas.ProcedureCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    data = payload.model_dump()
    # Attribute the session to whoever is actually logged in when the client
    # doesn't name a doctor. The doctor portal used to post doctor_id: null,
    # so every saved procedure came back with no doctor attached and the
    # summary sheet fell back to a hard-coded name that was frequently not the
    # doctor who performed it.
    if not data.get("doctor_id"):
        if current_user.role == models.UserRole.doctor:
            data["doctor_id"] = current_user.id
        else:
            # A receptionist or the HOD can start a session too. Leaving
            # doctor_id NULL there drops the row out of every doctor-joined
            # report (/hod/procedure-analytics/*), so fall back to the doctor
            # the patient is already assigned to.
            data["doctor_id"] = _resolve_doctor_id(db, data.get("patient_id"))
    # Record the start time when a procedure is created
    data["start_time"] = datetime.utcnow()
    proc = models.Procedure(**data)
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
    proc.end_time = datetime.utcnow()
    # Calculate duration in minutes from start_time to end_time. Sessions
    # created before start_time existed have none, so fall back to the session
    # date -- otherwise duration_minutes stays NULL and the row is invisible to
    # the procedure analytics reports.
    started = proc.start_time or proc.session_date
    if started:
        if proc.start_time is None:
            proc.start_time = started
        delta = proc.end_time - started
        proc.duration_minutes = max(0, int(delta.total_seconds() // 60))
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


# Logging the same material twice means "I used more of it", not "there are now
# two separate line items" -- so re-posting a name that is already on this
# procedure updates the existing row's quantity instead of appending a
# duplicate entry that nobody can reconcile.
@router.post("/{proc_id}/materials", response_model=schemas.MaterialOut, status_code=201)
def add_material(proc_id: int, payload: schemas.MaterialCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    data = payload.model_dump()
    name = (data.get("material_name") or "").strip()
    if not name:
        raise HTTPException(400, "Material name is required")
    data["material_name"] = name

    existing = (
        db.query(models.ProcedureMaterial)
        .filter(
            models.ProcedureMaterial.procedure_id == proc_id,
            models.ProcedureMaterial.material_name == name,
        )
        .first()
    )
    if existing:
        existing.quantity = data.get("quantity", existing.quantity)
        if data.get("unit"):
            existing.unit = data["unit"]
        db.commit()
        db.refresh(existing)
        return existing

    item = models.ProcedureMaterial(procedure_id=proc_id, **data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{proc_id}/materials/{item_id}", response_model=schemas.MaterialOut)
def update_material(
    proc_id: int,
    item_id: int,
    payload: schemas.MaterialUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    item = db.query(models.ProcedureMaterial).filter(
        models.ProcedureMaterial.id == item_id,
        models.ProcedureMaterial.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Material not found")
    if payload.quantity < 1:
        raise HTTPException(400, "Quantity must be at least 1")
    item.quantity = payload.quantity
    if payload.unit is not None:
        item.unit = payload.unit
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


# ── Teeth treated (FDI tooth chart) ───────────────────────────────────────────
# Charted per procedure: two procedures in one session keep separate tooth sets.
def _require_procedure(db: Session, proc_id: int) -> models.Procedure:
    proc = db.query(models.Procedure).filter(models.Procedure.id == proc_id).first()
    if not proc:
        raise HTTPException(404, "Procedure not found")
    return proc


@router.get("/{proc_id}/teeth", response_model=List[schemas.ProcedureToothOut])
def get_teeth(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedureTooth).filter(models.ProcedureTooth.procedure_id == proc_id).all()


# Re-charting the same tooth means "still this tooth", not a second row -- the
# unique constraint on (procedure_id, tooth_code) is enforced here so a repeated
# save is idempotent rather than a 500 from the database.
@router.post("/{proc_id}/teeth", response_model=schemas.ProcedureToothOut, status_code=201)
def add_tooth(proc_id: int, payload: schemas.ProcedureToothCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _require_procedure(db, proc_id)
    code = (payload.tooth_code or "").strip()
    if not code:
        raise HTTPException(400, "tooth_code is required")
    existing = db.query(models.ProcedureTooth).filter(
        models.ProcedureTooth.procedure_id == proc_id,
        models.ProcedureTooth.tooth_code == code,
    ).first()
    if existing:
        if payload.arch:
            existing.arch = payload.arch
        db.commit()
        db.refresh(existing)
        return existing
    item = models.ProcedureTooth(procedure_id=proc_id, tooth_code=code, arch=payload.arch)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{proc_id}/teeth", response_model=List[schemas.ProcedureToothOut])
def set_teeth(proc_id: int, payload: List[schemas.ProcedureToothCreate], db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Replace the whole tooth chart for this procedure in one call.

    The chart is edited as a set (tick/untick teeth, then Save Chart), so the
    client should be able to send the final state rather than diffing it into
    individual POSTs and DELETEs.
    """
    _require_procedure(db, proc_id)
    db.query(models.ProcedureTooth).filter(models.ProcedureTooth.procedure_id == proc_id).delete()
    seen: set[str] = set()
    for entry in payload:
        code = (entry.tooth_code or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        db.add(models.ProcedureTooth(procedure_id=proc_id, tooth_code=code, arch=entry.arch))
    db.commit()
    return db.query(models.ProcedureTooth).filter(models.ProcedureTooth.procedure_id == proc_id).all()


@router.delete("/{proc_id}/teeth/{item_id}", status_code=204)
def delete_tooth(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureTooth).filter(
        models.ProcedureTooth.id == item_id,
        models.ProcedureTooth.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Tooth entry not found")
    db.delete(item)
    db.commit()


# ── Archwire detail ───────────────────────────────────────────────────────────
@router.get("/{proc_id}/archwire", response_model=List[schemas.ProcedureArchwireOut])
def get_archwires(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedureArchwire).filter(models.ProcedureArchwire.procedure_id == proc_id).all()


@router.post("/{proc_id}/archwire", response_model=schemas.ProcedureArchwireOut, status_code=201)
def add_archwire(proc_id: int, payload: schemas.ProcedureArchwireCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _require_procedure(db, proc_id)
    if not any([payload.arch, payload.material, payload.size, payload.date_placed]):
        raise HTTPException(400, "At least one archwire detail is required")
    item = models.ProcedureArchwire(procedure_id=proc_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{proc_id}/archwire/{item_id}", status_code=204)
def delete_archwire(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureArchwire).filter(
        models.ProcedureArchwire.id == item_id,
        models.ProcedureArchwire.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Archwire entry not found")
    db.delete(item)
    db.commit()


# ── Diagnosis findings (Tab 1) ────────────────────────────────────────────────
# Distinct from /diagnostics: a diagnosis is a FINDING about the patient, not a
# test ordered with an urgency. Both used to be written to procedure_diagnostics,
# which made the two indistinguishable in every report.
@router.get("/{proc_id}/diagnosis", response_model=List[schemas.ProcedureDiagnosisOut])
def get_diagnosis(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedureDiagnosis).filter(models.ProcedureDiagnosis.procedure_id == proc_id).all()


@router.post("/{proc_id}/diagnosis", response_model=schemas.ProcedureDiagnosisOut, status_code=201)
def add_diagnosis(proc_id: int, payload: schemas.ProcedureDiagnosisCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _require_procedure(db, proc_id)
    finding = (payload.finding or "").strip()
    if not finding:
        raise HTTPException(400, "finding is required")
    existing = db.query(models.ProcedureDiagnosis).filter(
        models.ProcedureDiagnosis.procedure_id == proc_id,
        models.ProcedureDiagnosis.finding == finding,
    ).first()
    if existing:
        return existing
    item = models.ProcedureDiagnosis(procedure_id=proc_id, category=payload.category, finding=finding)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{proc_id}/diagnosis", response_model=List[schemas.ProcedureDiagnosisOut])
def set_diagnosis(proc_id: int, payload: List[schemas.ProcedureDiagnosisCreate], db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Replace the whole diagnosis selection -- the tab is a checkbox set."""
    _require_procedure(db, proc_id)
    db.query(models.ProcedureDiagnosis).filter(models.ProcedureDiagnosis.procedure_id == proc_id).delete()
    seen: set[str] = set()
    for entry in payload:
        finding = (entry.finding or "").strip()
        if not finding or finding in seen:
            continue
        seen.add(finding)
        db.add(models.ProcedureDiagnosis(procedure_id=proc_id, category=entry.category, finding=finding))
    db.commit()
    return db.query(models.ProcedureDiagnosis).filter(models.ProcedureDiagnosis.procedure_id == proc_id).all()


@router.delete("/{proc_id}/diagnosis/{item_id}", status_code=204)
def delete_diagnosis(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureDiagnosis).filter(
        models.ProcedureDiagnosis.id == item_id,
        models.ProcedureDiagnosis.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Diagnosis finding not found")
    db.delete(item)
    db.commit()


# ── Investigations (Tab 2) ────────────────────────────────────────────────────
@router.get("/{proc_id}/investigations", response_model=List[schemas.ProcedureInvestigationOut])
def get_investigations(proc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.ProcedureInvestigation).filter(models.ProcedureInvestigation.procedure_id == proc_id).all()


@router.post("/{proc_id}/investigations", response_model=schemas.ProcedureInvestigationOut, status_code=201)
def add_investigation(proc_id: int, payload: schemas.ProcedureInvestigationCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _require_procedure(db, proc_id)
    name = (payload.investigation or "").strip()
    if not name:
        raise HTTPException(400, "investigation is required")
    existing = db.query(models.ProcedureInvestigation).filter(
        models.ProcedureInvestigation.procedure_id == proc_id,
        models.ProcedureInvestigation.investigation == name,
    ).first()
    if existing:
        return existing
    item = models.ProcedureInvestigation(procedure_id=proc_id, category=payload.category, investigation=name)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{proc_id}/investigations", response_model=List[schemas.ProcedureInvestigationOut])
def set_investigations(proc_id: int, payload: List[schemas.ProcedureInvestigationCreate], db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Replace the whole investigation selection -- the tab is a checkbox set."""
    _require_procedure(db, proc_id)
    db.query(models.ProcedureInvestigation).filter(models.ProcedureInvestigation.procedure_id == proc_id).delete()
    seen: set[str] = set()
    for entry in payload:
        name = (entry.investigation or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        db.add(models.ProcedureInvestigation(procedure_id=proc_id, category=entry.category, investigation=name))
    db.commit()
    return db.query(models.ProcedureInvestigation).filter(models.ProcedureInvestigation.procedure_id == proc_id).all()


@router.delete("/{proc_id}/investigations/{item_id}", status_code=204)
def delete_investigation(proc_id: int, item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    item = db.query(models.ProcedureInvestigation).filter(
        models.ProcedureInvestigation.id == item_id,
        models.ProcedureInvestigation.procedure_id == proc_id,
    ).first()
    if not item:
        raise HTTPException(404, "Investigation not found")
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
