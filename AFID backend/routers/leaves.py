"""
routers/leaves.py
Leave requests: submit, list, approve/reject (HOD).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(prefix="/leaves", tags=["Leave Management"])


@router.get("/", response_model=List[schemas.LeaveOut])
def list_leaves(
    status: Optional[models.LeaveStatus] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.LeaveRequest)
    # Doctors/nurses see only their own; HOD/admin see all
    if current_user.role not in (models.UserRole.hod, models.UserRole.admin):
        q = q.filter(models.LeaveRequest.requester_id == current_user.id)
    if status:
        q = q.filter(models.LeaveRequest.status == status)
    return q.order_by(models.LeaveRequest.created_at.desc()).all()


@router.post("/", response_model=schemas.LeaveOut, status_code=201)
def submit_leave(
    payload: schemas.LeaveCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")
    leave = models.LeaveRequest(requester_id=current_user.id, **payload.model_dump())
    db.add(leave)
    db.commit()
    db.refresh(leave)
    return leave


@router.get("/{leave_id}", response_model=schemas.LeaveOut)
def get_leave(leave_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    leave = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(404, "Leave request not found")
    return leave


@router.patch("/{leave_id}/status", response_model=schemas.LeaveOut)
def update_leave_status(
    leave_id: int,
    payload: schemas.LeaveStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role not in (models.UserRole.hod, models.UserRole.admin):
        raise HTTPException(403, "Only HOD or Admin can approve/reject leave")
    leave = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(404, "Leave request not found")
    leave.status = payload.status
    leave.reviewed_by = payload.reviewed_by or current_user.full_name
    db.commit()
    db.refresh(leave)
    return leave


@router.delete("/{leave_id}", status_code=204)
def delete_leave(
    leave_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    leave = db.query(models.LeaveRequest).filter(models.LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(404, "Leave request not found")
    if leave.requester_id != current_user.id and current_user.role not in (models.UserRole.hod, models.UserRole.admin):
        raise HTTPException(403, "Not authorized")
    db.delete(leave)
    db.commit()
