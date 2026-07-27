"""
routers/presets.py
CRUD endpoints for procedure presets.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from models import ProcedurePreset, PresetMaterial, PresetPharmacy, PresetDiagnostic
import schemas

router = APIRouter(prefix="/presets", tags=["Procedure Presets"])


@router.get("/", response_model=List[schemas.ProcedurePresetOut])
def list_presets(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Return all active procedure presets."""
    presets = db.query(ProcedurePreset).filter(ProcedurePreset.is_active == True).order_by(ProcedurePreset.name).all()
    return presets


@router.post("/", response_model=schemas.ProcedurePresetOut, status_code=201)
def create_preset(
    payload: schemas.ProcedurePresetCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Create a new procedure preset."""
    existing = db.query(ProcedurePreset).filter(ProcedurePreset.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Preset already exists")
    
    preset = ProcedurePreset(
        name=payload.name,
        duration=payload.duration,
        notes=payload.notes,
    )
    db.add(preset)
    db.flush()

    for m in payload.materials:
        pm = PresetMaterial(preset_id=preset.id, name=m.name, quantity=m.quantity)
        db.add(pm)

    for p in payload.pharmacy:
        pp = PresetPharmacy(preset_id=preset.id, medication=p.medication, dose=p.dose, frequency=p.frequency)
        db.add(pp)

    for d in payload.diagnostics:
        pd = PresetDiagnostic(preset_id=preset.id, test_name=d.test_name, urgency=d.urgency)
        db.add(pd)

    db.commit()
    db.refresh(preset)
    return preset


@router.put("/{preset_id}", response_model=schemas.ProcedurePresetOut)
def update_preset(
    preset_id: int,
    payload: schemas.ProcedurePresetCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Update a procedure preset."""
    preset = db.query(ProcedurePreset).filter(ProcedurePreset.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    
    preset.name = payload.name
    preset.duration = payload.duration
    preset.notes = payload.notes

    # Remove existing linked items
    db.query(PresetMaterial).filter(PresetMaterial.preset_id == preset.id).delete()
    db.query(PresetPharmacy).filter(PresetPharmacy.preset_id == preset.id).delete()
    db.query(PresetDiagnostic).filter(PresetDiagnostic.preset_id == preset.id).delete()

    for m in payload.materials:
        pm = PresetMaterial(preset_id=preset.id, name=m.name, quantity=m.quantity)
        db.add(pm)

    for p in payload.pharmacy:
        pp = PresetPharmacy(preset_id=preset.id, medication=p.medication, dose=p.dose, frequency=p.frequency)
        db.add(pp)

    for d in payload.diagnostics:
        pd = PresetDiagnostic(preset_id=preset.id, test_name=d.test_name, urgency=d.urgency)
        db.add(pd)

    db.commit()
    db.refresh(preset)
    return preset


@router.delete("/{preset_id}", status_code=204)
def delete_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Delete a procedure preset."""
    preset = db.query(ProcedurePreset).filter(ProcedurePreset.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    db.delete(preset)
    db.commit()