"""Pydantic schemas for request validation and response serialization."""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr
from models import UserRole, PatientStatus, LeaveStatus, LeaveType, DiagnosticUrgency, StepStatus, RoomStatus


# ── Auth ──────────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.receptionist
    staff_id: Optional[str] = None

class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    role: UserRole
    staff_id: Optional[str]
    is_active: bool
    model_config = {"from_attributes": True}

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginIn(BaseModel):
    email: EmailStr
    password: str


# ── Doctor Profile ────────────────────────────────────────────────────────────
class DoctorProfileCreate(BaseModel):
    department: Optional[str] = None
    qualifications: Optional[str] = None
    shift: Optional[str] = None
    hod_on_call: Optional[str] = None
    status: Optional[str] = "Available"

class DoctorProfileOut(DoctorProfileCreate):
    id: int
    user_id: int
    model_config = {"from_attributes": True}


# ── Staff ─────────────────────────────────────────────────────────────────────
class StaffCreate(BaseModel):
    name: str
    role: str
    status: str = "Active"

class StaffOut(StaffCreate):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Doctor Allocations ────────────────────────────────────────────────────────
class DoctorAllocationCreate(BaseModel):
    doctor_name: str
    room: str
    department: Optional[str] = None
    chair: Optional[str] = None

class DoctorAllocationOut(DoctorAllocationCreate):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Patients ──────────────────────────────────────────────────────────────────
class PatientCreate(BaseModel):
    mr_number: str
    file_number: str
    full_name: str
    rank: Optional[str] = None
    cnic: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    service_profile: Optional[str] = None
    allergies: Optional[str] = None
    room: Optional[str] = None
    assigned_doctor: Optional[str] = None
    procedure_category: Optional[str] = None

class PatientStatusUpdate(BaseModel):
    status: PatientStatus

class PatientOut(BaseModel):
    id: int
    mr_number: str
    file_number: str
    full_name: str
    rank: Optional[str]
    cnic: Optional[str]
    gender: Optional[str]
    blood_group: Optional[str]
    service_profile: Optional[str]
    allergies: Optional[str]
    room: Optional[str]
    assigned_doctor: Optional[str]
    procedure_category: Optional[str]
    status: PatientStatus
    registered_at: datetime
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    model_config = {"from_attributes": True}


# ── Procedure History (Patient → many Procedures) ────────────────────────────
class ProcedureHistoryOut(BaseModel):
    """Summary of one procedure for display in patient history."""
    id: int
    name: str
    session_date: datetime
    is_completed: bool
    checklist_count: int = 0
    checked_count: int = 0
    materials_count: int = 0
    pharmacy_count: int = 0
    diagnostics_count: int = 0
    notes_count: int = 0
    model_config = {"from_attributes": True}

class PatientWithProceduresOut(PatientOut):
    """Patient record including their full procedure history."""
    procedures: List[ProcedureHistoryOut] = []
    model_config = {"from_attributes": True}


# ── Procedures ────────────────────────────────────────────────────────────────
class ProcedureCreate(BaseModel):
    patient_id: int
    doctor_id: Optional[int] = None
    name: str

class ProcedureOut(BaseModel):
    id: int
    patient_id: int
    doctor_id: Optional[int]
    name: str
    session_date: datetime
    is_completed: bool
    model_config = {"from_attributes": True}

class ChecklistItemCreate(BaseModel):
    step_text: str
    is_checked: bool = False
    display_order: int = 0

class ChecklistItemOut(ChecklistItemCreate):
    id: int
    procedure_id: int
    model_config = {"from_attributes": True}

class ChecklistItemUpdate(BaseModel):
    is_checked: bool

class MaterialCreate(BaseModel):
    material_name: str
    quantity: int = 1

class MaterialOut(MaterialCreate):
    id: int
    procedure_id: int
    model_config = {"from_attributes": True}

class PharmacyCreate(BaseModel):
    medication: str
    dose: Optional[str] = None
    frequency: Optional[str] = None

class PharmacyOut(PharmacyCreate):
    id: int
    procedure_id: int
    model_config = {"from_attributes": True}

class DiagnosticCreate(BaseModel):
    test_name: str
    urgency: DiagnosticUrgency = DiagnosticUrgency.routine

class DiagnosticOut(DiagnosticCreate):
    id: int
    procedure_id: int
    model_config = {"from_attributes": True}

class ClinicalNoteCreate(BaseModel):
    note_text: str

class ClinicalNoteOut(ClinicalNoteCreate):
    id: int
    procedure_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Leave ─────────────────────────────────────────────────────────────────────
class LeaveCreate(BaseModel):
    leave_type: LeaveType
    coverage_officer: Optional[str] = None
    reason: str
    start_date: date
    end_date: date

class LeaveStatusUpdate(BaseModel):
    status: LeaveStatus
    reviewed_by: Optional[str] = None

class LeaveOut(BaseModel):
    id: int
    requester_id: int
    leave_type: LeaveType
    coverage_officer: Optional[str]
    reason: str
    start_date: date
    end_date: date
    status: LeaveStatus
    reviewed_by: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Timeline Steps ────────────────────────────────────────────────────────────
class TimelineStepCreate(BaseModel):
    step_order: int
    step_name: str
    status: StepStatus = StepStatus.pending

class TimelineStepUpdate(BaseModel):
    status: StepStatus

class TimelineStepOut(TimelineStepCreate):
    id: int
    patient_id: int
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Operatory Rooms ───────────────────────────────────────────────────────────
class OperatoryRoomCreate(BaseModel):
    room_name: str
    assigned_doctor: Optional[str] = None
    current_case: Optional[str] = None
    queue_count: int = 0
    status: RoomStatus = RoomStatus.available

class OperatoryRoomUpdate(BaseModel):
    assigned_doctor: Optional[str] = None
    current_case: Optional[str] = None
    queue_count: Optional[int] = None
    status: Optional[RoomStatus] = None

class OperatoryRoomOut(OperatoryRoomCreate):
    id: int
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── HOD Dashboard Summary ─────────────────────────────────────────────────────
class DoctorMonitorRow(BaseModel):
    name: str
    patients_today: int
    status: str

class HODSummary(BaseModel):
    total_patients_today: int
    doctors_on_duty: int
    doctors_on_leave: int
    active_rooms: int
