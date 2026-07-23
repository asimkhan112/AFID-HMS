"""
schemas.py
Pydantic schemas for request/response validation.
"""

from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


# ── Users & Auth ──────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    full_name: str
    email: str
    role: str
    staff_id: Optional[str] = None


class UserCreate(UserBase):
    password: str


class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: str
    password: str


LoginIn = UserLogin


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Patients ──────────────────────────────────────────────────────────────────

class PatientBase(BaseModel):
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


class PatientCreate(PatientBase):
    pass


class PatientOut(PatientBase):
    id: int
    status: str
    registered_at: datetime
    updated_at: datetime
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PatientWithProceduresOut(PatientOut):
    procedures: List[dict] = []


class PatientStatusUpdate(BaseModel):
    status: str


# ── Procedure Presets ────────────────────────────────────────────────────────

class PresetMaterialIn(BaseModel):
    name: str
    quantity: int = 1


class PresetPharmacyIn(BaseModel):
    medication: str
    dose: Optional[str] = None
    frequency: Optional[str] = None


class PresetDiagnosticIn(BaseModel):
    test_name: str
    urgency: str = "Routine"


class ProcedurePresetCreate(BaseModel):
    name: str
    duration: int = 30
    notes: Optional[str] = None
    materials: List[PresetMaterialIn] = []
    pharmacy: List[PresetPharmacyIn] = []
    diagnostics: List[PresetDiagnosticIn] = []


class PresetMaterialOut(PresetMaterialIn):
    id: int
    preset_id: int

    model_config = ConfigDict(from_attributes=True)


class PresetPharmacyOut(PresetPharmacyIn):
    id: int
    preset_id: int

    model_config = ConfigDict(from_attributes=True)


class PresetDiagnosticOut(PresetDiagnosticIn):
    id: int
    preset_id: int

    model_config = ConfigDict(from_attributes=True)


class ProcedurePresetOut(BaseModel):
    id: int
    name: str
    duration: int
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    materials: List[PresetMaterialOut] = []
    pharmacy: List[PresetPharmacyOut] = []
    diagnostics: List[PresetDiagnosticOut] = []

    model_config = ConfigDict(from_attributes=True)


class PresetSummaryOut(BaseModel):
    id: int
    name: str
    duration: int
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ── Procedures ────────────────────────────────────────────────────────────────

class ProcedureBase(BaseModel):
    patient_id: int
    doctor_id: Optional[int] = None
    name: str
    is_completed: bool = False


class ProcedureCreate(ProcedureBase):
    pass


class ProcedureOut(ProcedureBase):
    id: int
    session_date: datetime
    patient: Optional[PatientOut] = None
    doctor: Optional[UserOut] = None
    checklist: List[dict] = []
    materials: List[dict] = []
    pharmacy: List[dict] = []
    diagnostics: List[dict] = []
    notes: List[dict] = []

    model_config = ConfigDict(from_attributes=True)


class ProcedureHistoryOut(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


# ── Materials, Pharmacy, Diagnostics ─────────────────────────────────────────

class ProcedureMaterialIn(BaseModel):
    material_name: str
    quantity: int = 1


class ProcedureMaterialOut(BaseModel):
    id: int
    procedure_id: int
    material_name: str
    quantity: int

    model_config = ConfigDict(from_attributes=True)


MaterialCreate = ProcedureMaterialIn


class ProcedurePharmacyIn(BaseModel):
    medication: str
    dose: Optional[str] = None
    frequency: Optional[str] = None


class ProcedurePharmacyOut(BaseModel):
    id: int
    procedure_id: int
    medication: str
    dose: Optional[str] = None
    frequency: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


PharmacyCreate = ProcedurePharmacyIn


class ProcedureDiagnosticIn(BaseModel):
    test_name: str
    urgency: str = "Routine"


class ProcedureDiagnosticOut(BaseModel):
    id: int
    procedure_id: int
    test_name: str
    urgency: str

    model_config = ConfigDict(from_attributes=True)


DiagnosticCreate = ProcedureDiagnosticIn


class ClinicalNoteIn(BaseModel):
    note_text: str


class ClinicalNoteOut(BaseModel):
    id: int
    procedure_id: int
    note_text: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


ClinicalNoteCreate = ClinicalNoteIn


# ── Clinical Notes ────────────────────────────────────────────────────────────

class ClinicalNoteBase(BaseModel):
    note_text: str


class ClinicalNoteCreate(ClinicalNoteBase):
    procedure_id: int


# ── Leave Requests ────────────────────────────────────────────────────────────

class LeaveRequestBase(BaseModel):
    leave_type: str
    coverage_officer: Optional[str] = None
    reason: str
    start_date: date
    end_date: date


class LeaveRequestCreate(LeaveRequestBase):
    pass


LeaveCreate = LeaveRequestCreate


class LeaveRequestOut(LeaveRequestBase):
    id: int
    requester_id: int
    status: str
    reviewed_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    requester_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


LeaveOut = LeaveRequestOut


class LeaveStatusUpdate(BaseModel):
    status: str


# ── Staff Management ──────────────────────────────────────────────────────────

class StaffMemberBase(BaseModel):
    name: str
    role: str


class StaffMemberCreate(StaffMemberBase):
    pass


class StaffMemberOut(StaffMemberBase):
    id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Room Allocations ──────────────────────────────────────────────────────────

class RoomAllocationBase(BaseModel):
    doctor_name: str
    room: str
    department: Optional[str] = None
    chair: Optional[str] = None


class RoomAllocationCreate(RoomAllocationBase):
    pass


DoctorAllocationCreate = RoomAllocationCreate


class RoomAllocationOut(RoomAllocationBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Room Status (Operatory Rooms) ─────────────────────────────────────────────

class RoomStatusUpdate(BaseModel):
    status: Optional[str] = None
    assigned_doctor: Optional[str] = None
    current_case: Optional[str] = None
    queue_count: Optional[int] = None
    approved: Optional[bool] = None


# ── Timeline Steps ────────────────────────────────────────────────────────────

class PatientTimelineStepBase(BaseModel):
    step_order: int
    step_name: str
    status: str = "Pending"


class PatientTimelineStepCreate(PatientTimelineStepBase):
    patient_id: int


class PatientTimelineStepOut(PatientTimelineStepBase):
    id: int
    patient_id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


TimelineStepCreate = PatientTimelineStepCreate
TimelineStepUpdate = PatientStatusUpdate


# ── Dashboard & Monitoring ────────────────────────────────────────────────────

class DashboardSummaryOut(BaseModel):
    total_patients_today: int
    doctors_on_duty: int
    doctors_on_leave: int
    active_rooms: int
    pending_leaves: int = 0


HODSummary = DashboardSummaryOut


class DoctorMonitoringOut(BaseModel):
    name: str
    patients_today: int
    total_active_cases: int
    status: str
    experience: Optional[str] = None
    rating: Optional[str] = None


DoctorMonitorRow = DoctorMonitoringOut


class DoctorPresenceOut(BaseModel):
    name: str
    status: str
    experience: str
    rating: str
    patients_today: int
    total_active_cases: int


# ── Doctor Profile & Allocations ──────────────────────────────────────────────

class DoctorProfileBase(BaseModel):
    department: Optional[str] = None
    qualifications: Optional[str] = None
    shift: Optional[str] = None
    hod_on_call: Optional[str] = None
    status: Optional[str] = None


class DoctorProfileCreate(DoctorProfileBase):
    user_id: int


class DoctorProfileOut(DoctorProfileBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class DoctorAllocationOut(BaseModel):
    id: int
    doctor_name: str
    room: str
    department: Optional[str] = None
    chair: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Procedure Items ───────────────────────────────────────────────────────────

class ChecklistItemBase(BaseModel):
    step_text: str
    is_checked: bool = False
    display_order: int = 0


class ChecklistItemCreate(ChecklistItemBase):
    procedure_id: int


class ChecklistItemUpdate(BaseModel):
    is_checked: bool


class ChecklistItemOut(ChecklistItemBase):
    id: int
    procedure_id: int

    model_config = ConfigDict(from_attributes=True)


class MaterialOut(BaseModel):
    id: int
    procedure_id: int
    material_name: str
    quantity: int

    model_config = ConfigDict(from_attributes=True)


class PharmacyOut(BaseModel):
    id: int
    procedure_id: int
    medication: str
    dose: Optional[str] = None
    frequency: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DiagnosticOut(BaseModel):
    id: int
    procedure_id: int
    test_name: str
    urgency: str

    model_config = ConfigDict(from_attributes=True)


# ── Staff & Rooms ─────────────────────────────────────────────────────────────

class StaffCreate(BaseModel):
    name: str
    role: str


StaffOut = StaffMemberOut


class OperatoryRoomCreate(BaseModel):
    room_name: str
    assigned_doctor: Optional[str] = None
    current_case: Optional[str] = None
    queue_count: Optional[int] = 0
    status: Optional[str] = "Available"


class OperatoryRoomOut(BaseModel):
    id: int
    room_name: str
    assigned_doctor: Optional[str] = None
    current_case: Optional[str] = None
    queue_count: int
    status: str
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


OperatoryRoomUpdate = RoomStatusUpdate


# ── Timeline Steps ────────────────────────────────────────────────────────────

TimelineStepOut = PatientTimelineStepOut