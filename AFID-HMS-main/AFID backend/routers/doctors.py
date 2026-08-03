"""
routers/doctors.py
Doctor profiles and room allocations.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(tags=["Doctors"])


# ── Doctor user profiles ──────────────────────────────────────────────────────
@router.get("/doctors", response_model=List[schemas.UserOut])
def list_doctors(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.User).filter(models.User.role == models.UserRole.doctor).all()


@router.get("/doctors/{user_id}/profile", response_model=schemas.DoctorProfileOut)
def get_doctor_profile(user_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    profile = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Doctor profile not found")
    return profile


@router.put("/doctors/{user_id}/profile", response_model=schemas.DoctorProfileOut)
def upsert_doctor_profile(
    user_id: int,
    payload: schemas.DoctorProfileCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    profile = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == user_id).first()
    if profile:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(profile, k, v)
    else:
        profile = models.DoctorProfile(user_id=user_id, **payload.model_dump())
        db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


# ── Room allocations ──────────────────────────────────────────────────────────
@router.get("/allocations", response_model=List[schemas.DoctorAllocationOut])
def list_allocations(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(models.DoctorAllocation).order_by(models.DoctorAllocation.created_at.desc()).all()


# A doctor occupies exactly ONE room at a time, so this is an UPSERT keyed on
# doctor_name, not a blind insert. Previously, re-allocating a doctor who
# already had a room simply appended a second row, and every consumer that
# lists allocations (the staff portal's doctor matrix, the registration form's
# dentist dropdown) then showed the same doctor sitting in two rooms at once
# with the stale allocation never going away.
@router.post("/allocations", response_model=schemas.DoctorAllocationOut, status_code=201)
def create_allocation(
    payload: schemas.DoctorAllocationCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    data = payload.model_dump()
    doctor_name = (data.get("doctor_name") or "").strip()
    room = (data.get("room") or "").strip()
    if not doctor_name:
        raise HTTPException(status_code=400, detail="Doctor name is required")
    if not room:
        raise HTTPException(status_code=400, detail="Room is required")
    data["doctor_name"] = doctor_name
    data["room"] = room

    # A room is a physical resource -- refuse to seat a second doctor in one.
    room_holder = (
        db.query(models.DoctorAllocation)
        .filter(models.DoctorAllocation.room == room, models.DoctorAllocation.doctor_name != doctor_name)
        .first()
    )
    if room_holder:
        raise HTTPException(
            status_code=400,
            detail=f"{room} is already allocated to {room_holder.doctor_name}. Reassign that doctor first.",
        )

    existing = (
        db.query(models.DoctorAllocation)
        .filter(models.DoctorAllocation.doctor_name == doctor_name)
        .first()
    )
    if existing:
        for k, v in data.items():
            setattr(existing, k, v)
        db.commit()
        db.refresh(existing)
        return existing

    alloc = models.DoctorAllocation(**data)
    db.add(alloc)
    db.commit()
    db.refresh(alloc)
    return alloc


@router.put("/allocations/{alloc_id}", response_model=schemas.DoctorAllocationOut)
def update_allocation(
    alloc_id: int,
    payload: schemas.DoctorAllocationCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    alloc = db.query(models.DoctorAllocation).filter(models.DoctorAllocation.id == alloc_id).first()
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(alloc, k, v)
    db.commit()
    db.refresh(alloc)
    return alloc


@router.delete("/allocations/{alloc_id}", status_code=204)
def delete_allocation(alloc_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    alloc = db.query(models.DoctorAllocation).filter(models.DoctorAllocation.id == alloc_id).first()
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")
    db.delete(alloc)
    db.commit()
