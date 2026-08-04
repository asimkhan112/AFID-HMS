"""
routers/lab.py
Lab appliance orders: what was ordered from the lab for a patient, and when it is
due to be inserted.

Sits at patient level rather than under /procedures because a lab order outlives
the session that raised it -- the appliance is ordered at one visit and inserted
at another, and the front desk needs to see what is outstanding without knowing
which procedure it came from.
"""

from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(prefix="/lab", tags=["Lab Orders"])


@router.get("/", response_model=List[schemas.LabOrderOut])
def list_lab_orders(
    patient_id: Optional[int] = Query(None, description="Filter to one patient"),
    pending_only: bool = Query(False, description="Only orders not yet inserted (insertion date in the future or unset)"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(models.LabOrder)
    if patient_id:
        q = q.filter(models.LabOrder.patient_id == patient_id)
    if pending_only:
        q = q.filter(
            (models.LabOrder.date_of_insertion.is_(None))
            | (models.LabOrder.date_of_insertion >= date.today())
        )
    return q.order_by(models.LabOrder.created_at.desc()).all()


@router.post("/", response_model=schemas.LabOrderOut, status_code=201)
def create_lab_order(
    payload: schemas.LabOrderCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    appliance = (payload.appliance_ordered or "").strip()
    if not appliance:
        raise HTTPException(400, "appliance_ordered is required")
    if not db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first():
        raise HTTPException(404, "Patient not found")
    if payload.procedure_id and not db.query(models.Procedure).filter(
        models.Procedure.id == payload.procedure_id
    ).first():
        raise HTTPException(404, "Procedure not found")

    order = models.LabOrder(
        patient_id=payload.patient_id,
        procedure_id=payload.procedure_id,
        appliance_ordered=appliance,
        date_of_insertion=payload.date_of_insertion,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/{order_id}", response_model=schemas.LabOrderOut)
def get_lab_order(order_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(models.LabOrder).filter(models.LabOrder.id == order_id).first()
    if not order:
        raise HTTPException(404, "Lab order not found")
    return order


@router.patch("/{order_id}", response_model=schemas.LabOrderOut)
def update_lab_order(
    order_id: int,
    payload: schemas.LabOrderUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    order = db.query(models.LabOrder).filter(models.LabOrder.id == order_id).first()
    if not order:
        raise HTTPException(404, "Lab order not found")
    data = payload.model_dump(exclude_unset=True)
    if "appliance_ordered" in data:
        appliance = (data["appliance_ordered"] or "").strip()
        if not appliance:
            raise HTTPException(400, "appliance_ordered cannot be blank")
        order.appliance_ordered = appliance
    if "date_of_insertion" in data:
        order.date_of_insertion = data["date_of_insertion"]
    db.commit()
    db.refresh(order)
    return order


@router.delete("/{order_id}", status_code=204)
def delete_lab_order(order_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    order = db.query(models.LabOrder).filter(models.LabOrder.id == order_id).first()
    if not order:
        raise HTTPException(404, "Lab order not found")
    db.delete(order)
    db.commit()
