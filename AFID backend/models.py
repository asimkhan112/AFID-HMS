"""
models.py
All SQLAlchemy ORM models for the AFID HMS.

Tables
-----
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
procedure_presets   – predefined procedure templates with materials, pharmacy, diagnostics
procedure_teeth     – teeth treated per procedure (FDI notation)
procedure_archwires – archwire placed per procedure
procedure_diagnosis – diagnosis findings ticked per procedure
procedure_investigations – investigations ordered per procedure
lab_orders          – appliance ordered from the lab + planned insertion date
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
    """Maps a doctor to a clinic room, chair, and department for a specific day."""
    __tablename__ = "doctor_allocations"

    id              = Column(Integer, primary_key=True, index=True)
    doctor_name     = Column(String(120), nullable=False)
    room            = Column(String(30), nullable=False)   # e.g. "Room 10"
    department      = Column(String(80))
    chair           = Column(String(80))                   # e.g. "Dental Chair A"
    allocation_date = Column(Date, default=date.today)     # which day this allocation is for
    created_at      = Column(DateTime, default=datetime.utcnow)


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
    diagnostic_history = Column(Text)                   # Medical Record tab -- baseline history
    systemic_status  = Column(Text)                     # Medical Record tab -- systemic findings
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
    documents        = relationship("PatientDocument", back_populates="patient", cascade="all, delete-orphan")
    lab_orders       = relationship("LabOrder", back_populates="patient", cascade="all, delete-orphan")


# ── Procedure Presets ────────────────────────────────────────────────────────

class ProcedurePreset(Base):
    """Predefined procedure templates with associated materials, pharmacy, diagnostics."""
    __tablename__ = "procedure_presets"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(120), unique=True, nullable=False)
    duration    = Column(Integer, default=30)  # in minutes
    notes       = Column(Text)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    materials   = relationship("PresetMaterial", back_populates="preset", cascade="all, delete-orphan")
    pharmacy    = relationship("PresetPharmacy", back_populates="preset", cascade="all, delete-orphan")
    diagnostics = relationship("PresetDiagnostic", back_populates="preset", cascade="all, delete-orphan")


class PresetMaterial(Base):
    __tablename__ = "preset_materials"

    id         = Column(Integer, primary_key=True, index=True)
    preset_id  = Column(Integer, ForeignKey("procedure_presets.id", ondelete="CASCADE"))
    name       = Column(String(255), nullable=False)
    quantity   = Column(Integer, default=1)

    preset = relationship("ProcedurePreset", back_populates="materials")


class PresetPharmacy(Base):
    __tablename__ = "preset_pharmacy"

    id        = Column(Integer, primary_key=True, index=True)
    preset_id = Column(Integer, ForeignKey("procedure_presets.id", ondelete="CASCADE"))
    medication = Column(String(255), nullable=False)
    dose       = Column(String(80))
    frequency   = Column(String(120))

    preset = relationship("ProcedurePreset", back_populates="pharmacy")


class PresetDiagnostic(Base):
    __tablename__ = "preset_diagnostics"

    id        = Column(Integer, primary_key=True, index=True)
    preset_id = Column(Integer, ForeignKey("procedure_presets.id", ondelete="CASCADE"))
    test_name = Column(String(255), nullable=False)
    urgency   = Column(SAEnum(DiagnosticUrgency), default=DiagnosticUrgency.routine)

    preset = relationship("ProcedurePreset", back_populates="diagnostics")


# ── Procedures ────────────────────────────────────────────────────────────────

class Procedure(Base):
    """One procedure session performed on a patient by a doctor."""
    __tablename__ = "procedures"

    id               = Column(Integer, primary_key=True, index=True)
    patient_id       = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"))
    doctor_id        = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name             = Column(String(120), nullable=False)  # e.g. "Root Canal Treatment"
    session_date     = Column(DateTime, default=datetime.utcnow)
    is_completed     = Column(Boolean, default=False)
    start_time       = Column(DateTime, nullable=True)       # when the doctor began the procedure
    end_time         = Column(DateTime, nullable=True)       # when the procedure was completed
    duration_minutes = Column(Integer, nullable=True)        # calculated duration in minutes
    complications    = Column(Text, nullable=True)           # adverse events flagged in Clinical Notes

    patient      = relationship("Patient", back_populates="procedures")
    doctor       = relationship("User", back_populates="procedures")
    checklist    = relationship("ProcedureChecklist", back_populates="procedure", cascade="all, delete-orphan")
    materials    = relationship("ProcedureMaterial", back_populates="procedure", cascade="all, delete-orphan")
    pharmacy     = relationship("ProcedurePharmacy", back_populates="procedure", cascade="all, delete-orphan")
    diagnostics  = relationship("ProcedureDiagnostic", back_populates="procedure", cascade="all, delete-orphan")
    notes        = relationship("ClinicalNote", back_populates="procedure", cascade="all, delete-orphan")
    documents    = relationship("PatientDocument", back_populates="procedure")
    teeth        = relationship("ProcedureTooth", back_populates="procedure", cascade="all, delete-orphan")
    archwires    = relationship("ProcedureArchwire", back_populates="procedure", cascade="all, delete-orphan")
    findings     = relationship("ProcedureDiagnosis", back_populates="procedure", cascade="all, delete-orphan")
    investigations = relationship("ProcedureInvestigation", back_populates="procedure", cascade="all, delete-orphan")
    lab_orders   = relationship("LabOrder", back_populates="procedure", cascade="all, delete-orphan")


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
    unit         = Column(String(40))          # "pcs", "ml", … as typed in the Materials tab

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


# ── Structured clinical detail ────────────────────────────────────────────────
# The doctor portal captures all of the below, but until now it could only be
# written into the free-text clinical note (teeth, archwire, lab, complications)
# or, worse, into procedure_diagnostics as if a diagnosis finding were an ordered
# test. None of it was queryable. These tables give each its own home.

class ProcedureTooth(Base):
    """One tooth treated in a procedure, in FDI notation (Tab 4 tooth chart).

    Charted per procedure: two procedures in the same session keep separate tooth
    sets, which is why the procedure -- not the session -- is the parent.
    """
    __tablename__ = "procedure_teeth"
    __table_args__ = (UniqueConstraint("procedure_id", "tooth_code", name="uq_procedure_tooth"),)

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False)
    tooth_code   = Column(String(4), nullable=False)   # FDI: "18".."48"
    arch         = Column(String(10))                  # "Upper" / "Lower"

    procedure    = relationship("Procedure", back_populates="teeth")


class ProcedureArchwire(Base):
    """Archwire placed during a procedure (Tab 4 archwire panel)."""
    __tablename__ = "procedure_archwires"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False)
    arch         = Column(String(20))     # Upper / Lower / Both
    material     = Column(String(80))     # Stainless steel, NiTi, Copper NiTi, TMA, …
    size         = Column(String(60))     # e.g. "0.016 x 0.022"
    date_placed  = Column(Date, nullable=True)

    procedure    = relationship("Procedure", back_populates="archwires")


class ProcedureDiagnosis(Base):
    """A diagnosis finding ticked in Tab 1 (skeletal, dental, space-related, …)."""
    __tablename__ = "procedure_diagnosis"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False)
    category     = Column(String(120))                  # e.g. "Skeletal Diagnosis — Vertical"
    finding      = Column(String(255), nullable=False)  # e.g. "Hyperdivergent (open bite tendency)"

    procedure    = relationship("Procedure", back_populates="findings")


class ProcedureInvestigation(Base):
    """An investigation ordered in Tab 2. Distinct from ProcedureDiagnostic, which
    is the pharmacy-style diagnostic order with an urgency attached."""
    __tablename__ = "procedure_investigations"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=False)
    category     = Column(String(120))                  # e.g. "Radiographic"
    investigation = Column(String(255), nullable=False) # e.g. "Lateral cephalogram"

    procedure    = relationship("Procedure", back_populates="investigations")


class LabOrder(Base):
    """Appliance ordered from the lab, with its planned insertion date (Lab tab)."""
    __tablename__ = "lab_orders"

    id                = Column(Integer, primary_key=True, index=True)
    procedure_id      = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"), nullable=True)
    patient_id        = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    appliance_ordered = Column(String(255), nullable=False)
    date_of_insertion = Column(Date, nullable=True)
    created_at        = Column(DateTime, default=datetime.utcnow)

    procedure = relationship("Procedure", back_populates="lab_orders")
    patient   = relationship("Patient", back_populates="lab_orders")


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id           = Column(Integer, primary_key=True, index=True)
    procedure_id = Column(Integer, ForeignKey("procedures.id", ondelete="CASCADE"))
    note_text    = Column(Text, nullable=False)
    created_at   = Column(DateTime, default=datetime.utcnow)

    procedure    = relationship("Procedure", back_populates="notes")


# ── Patient Documents / Uploads ────────────────────────────────────────────────

class PatientDocument(Base):
    __tablename__ = "patient_documents"

    id            = Column(Integer, primary_key=True, index=True)
    patient_id    = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    procedure_id  = Column(Integer, ForeignKey("procedures.id", ondelete="SET NULL"), nullable=True)
    record_type   = Column(String(60), nullable=False)
    file_name     = Column(String(255), nullable=False)
    file_path     = Column(String(500), nullable=False)
    file_size     = Column(Integer, default=0)
    file_date     = Column(Date, default=date.today)
    uploaded_at   = Column(DateTime, default=datetime.utcnow)

    patient   = relationship("Patient", back_populates="documents")
    procedure = relationship("Procedure", back_populates="documents")


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