"""
backfill_durations.py
Populate duration_minutes for existing completed procedures.
Run with: python backfill_durations.py
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base, get_db
import models

# Default durations by procedure name when start/end times are unavailable
DEFAULT_DURATIONS = {
    "Consultation": 15,
    "U/L Bracketing": 45,
    "Fixed Retainer": 40,
    "Orthodontic Adjustment": 25,
    "Root Canal Treatment": 60,
    "Band cementation / Banding of molars": 30,
    "De bonding": 30,
    "Cast Surgery / Prediction / VTO / Morphing": 150,
    "Fixed adjustment (Wire/Bends/IPR/Traction/Implant)": 20,
    "Loose band / Button / Bracket / Tubes": 20,
    "Fixed functional appliance Adj / EOT / Face mask": 20,
    "Molar bands / VFR": 20,
    "NAM (First time prep + First time app)": 60,
    "Treatment planning / File analysis / Tracing": 20,
    "Space maintainer / Photography / Digital Scan": 10,
    "Nance LLA / Hyrax / Quad Helix / TPA / Pendulum": 20,
    "Impression / O/E / Separator / Removable adj": 10,
    "ORAL EXAM": 10,
}

def backfill_doctor_ids(db: Session) -> int:
    """Attach a doctor to procedures saved with doctor_id NULL.

    The analytics endpoints inner-join procedures to users on doctor_id, so a
    NULL there makes the row invisible. The patient's assigned_doctor already
    records who was responsible; map that name back onto the doctor's user row.
    """
    doctors = {
        u.full_name: u.id
        for u in db.query(models.User).filter(models.User.role == models.UserRole.doctor).all()
    }

    orphans = (
        db.query(models.Procedure)
        .filter(models.Procedure.doctor_id == None)  # noqa: E711 -- SQL NULL test
        .all()
    )

    updated = 0
    for p in orphans:
        patient = p.patient
        if not patient or not patient.assigned_doctor:
            continue
        doctor_id = doctors.get(patient.assigned_doctor)
        if doctor_id:
            p.doctor_id = doctor_id  # type: ignore
            updated += 1
    return updated


def backfill():
    db = SessionLocal()
    try:
        # Attribute orphaned procedures before computing durations, so the
        # analytics reports have both halves of the data they need.
        attributed = backfill_doctor_ids(db)

        # Use the same DB configured for the app from .env via database.py
        procedures = db.query(models.Procedure).filter(
            models.Procedure.is_completed == True,
            models.Procedure.duration_minutes == None
        ).all()

        updated = 0
        for p in procedures:
            duration = None

            # Prefer explicit start/end times if present
            if getattr(p, 'start_time', None) and getattr(p, 'end_time', None):
                try:
                    start = p.start_time
                    end = p.end_time
                    duration = max(0, round((end - start).total_seconds() / 60))
                except Exception:
                    duration = None

            # Fallback to procedure preset duration by name
            if duration is None:
                duration = DEFAULT_DURATIONS.get(getattr(p, 'name', ''))

            # Last resort fallback
            if duration is None:
                duration = 30

            p.duration_minutes = duration  # type: ignore
            updated += 1

        db.commit()
        print(f"Attached a doctor to {attributed} previously unattributed procedures.")
        print(f"Backfilled duration_minutes for {updated} completed procedures.")
    except Exception as e:
        print(f"Error during backfill: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    backfill()