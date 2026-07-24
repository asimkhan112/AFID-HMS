"""
routers/leaves.py
Leave requests: submit, list, approve/reject (HOD).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(prefix="/leaves", tags=["Leave Management"])


def serialize_leave(leave: models.LeaveRequest) -> dict:
    return {
        "id": leave.id,
        "requester_id": leave.requester_id,
        "leave_type": leave.leave_type.value if leave.leave_type else None,
        "coverage_officer": leave.coverage_officer,
        "reason": leave.reason,
        "start_date": leave.start_date.isoformat() if leave.start_date else None,
        "end_date": leave.end_date.isoformat() if leave.end_date else None,
        "status": leave.status.value if leave.status else None,
        "reviewed_by": leave.reviewed_by,
        "created_at": leave.created_at.isoformat() if leave.created_at else None,
        "updated_at": leave.updated_at.isoformat() if leave.updated_at else None,
        "requester_name": leave.requester.full_name if leave.requester else None,
    }


@router.get("/")
def list_leaves(
    status: Optional[models.LeaveStatus] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.LeaveRequest).options(joinedload(models.LeaveRequest.requester))

    if current_user.role not in (models.UserRole.hod, models.UserRole.admin):
        query = query.filter(models.LeaveRequest.requester_id == current_user.id)

    if status:
        query = query.filter(models.LeaveRequest.status == status)

    leaves = query.order_by(models.LeaveRequest.created_at.desc()).all()
    return [serialize_leave(leave) for leave in leaves]


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


@router.get("/{leave_id}")
def get_leave(leave_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    leave = db.query(models.LeaveRequest).options(joinedload(models.LeaveRequest.requester)).filter(models.LeaveRequest.id == leave_id).first()
    if not leave:
        raise HTTPException(404, "Leave request not found")
    return serialize_leave(leave)


@router.patch("/{leave_id}/status")
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
    leave.reviewed_by = current_user.full_name
    db.commit()

    leave = db.query(models.LeaveRequest).options(joinedload(models.LeaveRequest.requester)).filter(models.LeaveRequest.id == leave_id).first()
    return serialize_leave(leave)


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
