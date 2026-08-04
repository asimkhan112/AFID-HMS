"""
doctor_matching.py
Resolve a free-text doctor name to a user account.

Patient ownership is decided by patients.assigned_doctor_id. The display string
patients.assigned_doctor is still accepted on the wire (older clients, imports,
and the receptionist form all send a name), so writes have to map a name back
to an account. The matching rules here and the ones used by the one-off
backfill in migrate_assigned_doctor_id.py must agree, which is why they live in
one module rather than being written twice.

Matching is deliberately conservative: an ambiguous surname resolves to nothing
rather than guessing, because guessing wrong silently hands a patient to the
wrong clinician.
"""

import re
from collections import defaultdict
from typing import Optional

import models


def normalise_doctor_name(name: Optional[str]) -> str:
    """'Dr. Hira Z.' -> 'hira z' — strips title, punctuation and extra spaces."""
    if not name:
        return ""
    s = name.strip().lower()
    s = re.sub(r"^(dr|doctor|prof|professor)\b\.?\s*", "", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _surname_key(normalised: str) -> str:
    return normalised.split(" ")[0] if normalised else ""


def resolve_doctor(db, name: Optional[str]) -> Optional[models.User]:
    """Best-effort map of a display name to an active doctor account.

    Tries exact full_name, then a normalised comparison, then an unambiguous
    surname match. Returns None when nothing matches or the surname is shared
    by more than one doctor.
    """
    if not name or not name.strip():
        return None

    doctors = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.doctor, models.User.is_active.is_(True))
        .all()
    )
    if not doctors:
        return None

    target = name.strip()
    for doc in doctors:
        if doc.full_name == target:
            return doc

    norm = normalise_doctor_name(target)
    for doc in doctors:
        if normalise_doctor_name(doc.full_name) == norm:
            return doc

    buckets = defaultdict(list)
    for doc in doctors:
        buckets[_surname_key(normalise_doctor_name(doc.full_name))].append(doc)
    candidates = buckets.get(_surname_key(norm), [])
    return candidates[0] if len(candidates) == 1 else None


def apply_doctor_assignment(db, patient, data: dict) -> None:
    """Keep assigned_doctor_id and assigned_doctor consistent on a write.

    `data` is the validated payload dict. An explicit id wins; otherwise a name
    is resolved to an account. When a name cannot be resolved the string is
    still stored (so nothing is lost) but the id is cleared, which keeps the
    patient out of every doctor's queue rather than putting them in the wrong
    one -- a visible failure instead of a silent misassignment.
    """
    has_id = "assigned_doctor_id" in data
    has_name = "assigned_doctor" in data
    if not (has_id or has_name):
        return

    doctor_id = data.get("assigned_doctor_id")
    if has_id and doctor_id is not None:
        doctor = db.query(models.User).filter(models.User.id == doctor_id).first()
        if doctor:
            patient.assigned_doctor_id = doctor.id
            patient.assigned_doctor = doctor.full_name
            return

    if has_name:
        name = data.get("assigned_doctor")
        doctor = resolve_doctor(db, name)
        patient.assigned_doctor = name
        patient.assigned_doctor_id = doctor.id if doctor else None
