"""
routers/doctors.py
Doctor profiles and room allocations.
"""

from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
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
def list_allocations(
    allocation_date: Optional[date] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(models.DoctorAllocation)
    if allocation_date:
        q = q.filter(models.DoctorAllocation.allocation_date == allocation_date)
    return q.order_by(models.DoctorAllocation.allocation_date.desc(), models.DoctorAllocation.created_at.desc()).all()


# A doctor can have different room allocations on different days.
# The UPSERT is keyed on (doctor_name, allocation_date) so a doctor can be
# assigned Room 10 on Monday and Room 12 on Tuesday.
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

    # Default allocation_date to today if not provided
    alloc_date = data.get("allocation_date")
    if alloc_date is None:
        alloc_date = date.today()
        data["allocation_date"] = alloc_date

    # A room is a physical resource per day -- refuse to seat a second doctor in one on the same day.
    room_holder = (
        db.query(models.DoctorAllocation)
        .filter(
            models.DoctorAllocation.room == room,
            models.DoctorAllocation.allocation_date == alloc_date,
            models.DoctorAllocation.doctor_name != doctor_name
        )
        .first()
    )
    if room_holder:
        raise HTTPException(
            status_code=400,
            detail=f"{room} on {alloc_date} is already allocated to {room_holder.doctor_name}. Reassign that doctor first.",
        )

    # UPSERT: one allocation per doctor per day
    existing = (
        db.query(models.DoctorAllocation)
        .filter(
            models.DoctorAllocation.doctor_name == doctor_name,
            models.DoctorAllocation.allocation_date == alloc_date
        )
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
