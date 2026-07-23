"""
routers/staff.py
Staff directory CRUD (non-doctor clinical staff).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user, require_role
import models, schemas

router = APIRouter(prefix="/staff", tags=["Staff Directory"])


@router.get("/", response_model=List[schemas.StaffOut])
def list_staff(
    role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
    __=Depends(require_role(models.UserRole.hod, models.UserRole.admin)),
):
    q = db.query(models.StaffMember)
    if role:
        q = q.filter(models.StaffMember.role == role)
    return q.order_by(models.StaffMember.name).all()


@router.post("/", response_model=schemas.StaffOut, status_code=201)
def create_staff(payload: schemas.StaffCreate, db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    member = models.StaffMember(**payload.model_dump())
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.get("/{staff_id}", response_model=schemas.StaffOut)
def get_staff(staff_id: int, db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    member = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
    if not member:
        raise HTTPException(404, "Staff member not found")
    return member


@router.put("/{staff_id}", response_model=schemas.StaffOut)
def update_staff(staff_id: int, payload: schemas.StaffCreate, db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    member = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
    if not member:
        raise HTTPException(404, "Staff member not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(member, k, v)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{staff_id}", status_code=204)
def delete_staff(staff_id: int, db: Session = Depends(get_db), _=Depends(get_current_user), __=Depends(require_role(models.UserRole.hod, models.UserRole.admin))):
    member = db.query(models.StaffMember).filter(models.StaffMember.id == staff_id).first()
    if not member:
        raise HTTPException(404, "Staff member not found")
    db.delete(member)
    db.commit()
