"""
models.py
All SQLAlchemy ORM models for the AFID HMS.

Tables
------
users               – authentication + role (doctor / hod / admin / receptionist / nurse)
doctor_profiles     – extended info for users with role=doctor
staff_members       – non-doctor clinical staff directory
patients            – patient master record
doctor_allocations  – room/chair assignments for doctors
procedures          – a single procedure session tied to a patient + doctor
procedure_checklist – individual checklist items inside a procedure
procedure_materials – materials/consumables used in a procedure
procedure_pharmacy  – medications dispensed during a procedure
procedure_diagnostics – diagnostic tests ordered in a procedure
clinical_notes      – free-text notes attached to a procedure
leave_requests      – leave applications submitted by users
patient_timeline    – ordered procedure steps for HOD timeline view
operatory_rooms     – live room status tracked by HOD
"""

import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    ForeignKey, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship

from database import Base


# ── Enumerations ──────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    doctor       = "doctor"
    hod          = "hod"
    admin        = "admin"
    receptionist = "receptionist"
    nurse        = "nurse"


class PatientStatus(str, enum.Enum):
    waiting   = "WAITING"
    active    = "ACTIVE"
    completed = "COMPLETED"


class LeaveStatus(str, enum.Enum):
    pending  = "PENDING"
    approved = "APPROVED"
    rejected = "REJECTED"


class LeaveType(str, enum.Enum):
    casual   = "Casual Leave"
    annual   = "Annual Leave"
    medical  = "Medical Allocation"


class DiagnosticUrgency(str, enum.Enum):
    routine = "Routine"
    urgent  = "Urgent"
    stat    = "STAT"


class StepStatus(str, enum.Enum):
    pending     = "Pending"
    in_progress = "In Progress"
    completed   = "Completed"


class RoomStatus(str, enum.Enum):
    available   = "Available"
    busy        = "Busy (In-Procedure)"
    consultation = "Consultation"


# ── Users & Auth ──────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    full_name     = Column(String(120), nullable=False)
    email         = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role          = Column(SAEnum(UserRole), nullable=False, default=UserRole.receptionist)
    staff_id      = Column(String(30), unique=True, nullable=True)   # e.g. HMS-0001
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    # relationships
    doctor_profile  = relationship("DoctorProfile", back_populates="user", uselist=False)
    leave_requests  = relationship("LeaveRequest", back_populates="requester")
    procedures      = relationship("Procedure", back_populates="doctor")


class DoctorProfile(Base):
    """Extended clinical profile for users with role=doctor."""
    __tablename__ = "doctor_profiles"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    department     = Column(String(80))
    qualifications = Column(String(255))
    shift          = Column(String(80))           # e.g. "Morning (0800-1400)"
    hod_on_call    = Column(String(120))
    status         = Column(String(30), default="Available")   # Available / On Leave

    user = relationship("User", back_populates="doctor_profile")


# ── Staff Directory ───────────────────────────────────────────────────────────

class StaffMember(Base):
    """Non-doctor clinical staff tracked by HOD (nurses, technicians, receptionists)."""
    __tablename__ = "staff_members"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(120), nullable=False)
    role       = Column(String(80), nullable=False)   # Nurse / Technician / etc.
    status     = Column(String(30), default="Active") # Active / On Leave
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Doctor Room Allocations ───────────────────────────────────────────────────

class DoctorAllocation(Base):
    """Maps a doctor to a clinic room, chair, and department for the day."""
    __tablename__ = "doctor_allocations"

    id          = Column(Integer, primary_key=True, index=True)
    doctor_name = Column(String(120), nullable=False)
    room        = Column(String(30), nullable=False)   # e.g. "Room 10"
    department  = Column(String(80))
    chair       = Column(String(80))                   # e.g. "Dental Chair A"
    created_at  = Column(DateTime, default=datetime.utcnow)


# ── Patients ──────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    id               = Column(Integer, primary_key=True, index=True)
    mr_number        = Column(String(30), unique=True, index=True, nullable=False)
    file_number      = Column(String(30), unique=True, index=True, nullable=False)
    full_name        = Column(String(120), nullable=False)
    rank             = Column(String(60))
    cnic             = Column(String(20), index=True)
    gender           = Column(String(10))
    blood_group      = Column(String(10))
    service_profile  = Column(String(120))
    allergies        = Column(Text)                     # free-text allergy notes
    room             = Column(String(30))
    assigned_doctor  = Column(String(120))
    procedure_category = Column(String(120))
    status           = Column(SAEnum(PatientStatus), default=PatientStatus.waiting)
    registered_at    = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    check_in_time    = Column(DateTime, nullable=True)
    check_out_time   = Column(DateTime, nullable=True)

    procedures       = relationship("Procedure", back_populates="patient")
    timeline_steps   = relationship("PatientTimelineStep", back_populates="patient")


# ── Procedures ────────────────────────────────────────────────────────────────

class Procedure(Base):
    """One procedure session performed on a patient by a doctor."""
    __tablename__ = "procedures"

    id           = Column(Integer, primary_key=True, index=True)
    patient_id   = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"))
    doctor_id    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name         = Column(String(120), nullable=False)  # e.g. "Root Canal Treatment"
    session_date = Column(DateTime, default=datetime.utcnow)
    is_completed = Column(Boolean, default=False)

    patient      = relationship("Patient", back_populates="procedures")
    doctor       = relationship("User", back_populates="procedures")
    checklist    = relationship("ProcedureChecklist", back_populates="procedure", cascade="all, delete-orphan")
    materials    = relationship("ProcedureMaterial", back_populates="procedure", cascade="all, delete-orphan")
    pharmacy     = relationship("ProcedurePharmacy", back_populates="procedure", cascade="all, delete-orphan")
    diagnostics  = relationship("ProcedureDiagnostic", back_populates="procedure", cascade="all, delete-orphan")
    notes        = relationship("ClinicalNote", back_populates="procedure", cascade="all, delete-orphan")


class ProcedureChecklist(Base):
    __tablename__ = "procedure_checklist"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"))
    step_text    = Column(String(255), nullable=False)
    is_checked   = Column(Boolean, default=False)
    display_order = Column(Integer, default=0)

    procedure    = relationship("Procedure", back_populates="checklist")


class ProcedureMaterial(Base):
    __tablename__ = "procedure_materials"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"))
    material_name = Column(String(255), nullable=False)
    quantity     = Column(Integer, default=1)

    procedure    = relationship("Procedure", back_populates="materials")


class ProcedurePharmacy(Base):
    __tablename__ = "procedure_pharmacy"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"))
    medication   = Column(String(255), nullable=False)
    dose         = Column(String(80))
    frequency    = Column(String(120))

    procedure    = relationship("Procedure", back_populates="pharmacy")


class ProcedureDiagnostic(Base):
    __tablename__ = "procedure_diagnostics"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"))
    test_name    = Column(String(255), nullable=False)
    urgency      = Column(SAEnum(DiagnosticUrgency), default=DiagnosticUrgency.routine)

    procedure    = relationship("Procedure", back_populates="diagnostics")


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"))
    note_text    = Column(Text, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)

    procedure    = relationship("Procedure", back_populates="notes")


# ── Leave Requests ────────────────────────────────────────────────────────────

class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id               = Column(Integer, primary_key=True, index=True)
    requester_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    leave_type       = Column(SAEnum(LeaveType), nullable=False)
    coverage_officer = Column(String(120))
    reason           = Column(String(255), nullable=False)
    start_date       = Column(Date, nullable=False)
    end_date         = Column(Date, nullable=False)
    status           = Column(SAEnum(LeaveStatus), default=LeaveStatus.pending)
    reviewed_by      = Column(String(120), nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    requester        = relationship("User", back_populates="leave_requests")


# ── Patient Timeline (HOD view) ───────────────────────────────────────────────

class PatientTimelineStep(Base):
    """Ordered procedure steps for a patient shown in the HOD timeline."""
    __tablename__ = "patient_timeline_steps"

    id            = Column(Integer, primary_key=True, index=True)
    patient_id    = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"))
    step_order    = Column(Integer, nullable=False)
    step_name     = Column(String(255), nullable=False)
    status        = Column(SAEnum(StepStatus), default=StepStatus.pending)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient       = relationship("Patient", back_populates="timeline_steps")


# ── Operatory Rooms ───────────────────────────────────────────────────────────

class OperatoryRoom(Base):
    """Live status of each clinic room (managed by HOD / staff)."""
    __tablename__ = "operatory_rooms"

    id              = Column(Integer, primary_key=True, index=True)
    room_name       = Column(String(30), unique=True, nullable=False)  # "Room 10"
    assigned_doctor = Column(String(120))
    current_case    = Column(String(120))
    queue_count     = Column(Integer, default=0)
    status          = Column(SAEnum(RoomStatus), default=RoomStatus.available)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
