"""
routers/upload.py
File upload endpoint for patient radiographs, photos, and documents.
"""

import os
import uuid
from datetime import datetime, date
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".dicom", ".dcm"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/")
async def upload_file(
    patient_id: int = Form(...),
    record_type: str = Form(...),
    file_date: str = Form(None),
    procedure_id: int = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _ = Depends(get_current_user)
):
    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max size: 50MB")

    # Generate unique filename to prevent collisions
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # Write file to disk
    with open(file_path, "wb") as f:
        f.write(content)

    # Parse date
    parsed_date = date.today()
    if file_date:
        try:
            parsed_date = datetime.strptime(file_date, "%Y-%m-%d").date()
        except ValueError:
            pass  # Use today's date if invalid

    # Save record to database
    doc = models.PatientDocument(
        patient_id=patient_id,
        procedure_id=procedure_id,
        record_type=record_type,
        file_name=file.filename,
        file_path=file_path,
        file_size=len(content),
        file_date=parsed_date
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "id": doc.id,
        "file_name": doc.file_name,
        "file_path": doc.file_path,
        "file_date": str(doc.file_date),
        "file_size": doc.file_size
    }


@router.get("/{patient_id}")
def list_patient_files(patient_id: int, db: Session = Depends(get_db), _ = Depends(get_current_user)):
    """List all uploaded documents for a patient."""
    return db.query(models.PatientDocument).filter(
        models.PatientDocument.patient_id == patient_id
    ).order_by(models.PatientDocument.uploaded_at.desc()).all()


@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db), _ = Depends(get_current_user)):
    """Delete an uploaded document (both file and database record)."""
    doc = db.query(models.PatientDocument).filter(models.PatientDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try to delete the physical file
    try:
        if os.path.exists(str(doc.file_path)):
            os.remove(str(doc.file_path))
    except Exception:
        pass  # Continue even if file deletion fails

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}