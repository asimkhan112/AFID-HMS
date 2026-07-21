# AFID HMS — Python/PostgreSQL Backend

FastAPI + SQLAlchemy + PostgreSQL backend for the AFID Hospital Management System.

---

## Quick Setup (5 steps)

### 1. Create PostgreSQL database
```sql
CREATE USER afid_user WITH PASSWORD 'afid_pass';
CREATE DATABASE afid_db OWNER afid_user;
```

### 2. Configure environment
```bash
cd "AFID backend"
copy .env.example .env
# Edit .env and set your DATABASE_URL and SECRET_KEY
```

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 4. Seed the database (creates tables + sample data)
```bash
python init_db.py
```

### 5. Start the server
```bash
uvicorn main:app --reload --port 8000
```

API docs available at: **http://127.0.0.1:8000/docs**

---

## Default Login Credentials (after seeding)

| Role       | Email                  | Password     |
|------------|------------------------|--------------|
| HOD/Admin  | hod@afid.mil           | admin1234    |
| Doctor     | doctor@afid.mil        | doctor1234   |
| Reception  | reception@afid.mil     | staff1234    |

---

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Get JWT token |
| POST | `/auth/register` | Create account |
| GET  | `/auth/me` | Current user info |
| GET/POST | `/patients/` | List / register patients |
| GET  | `/patients/lookup/mr/{mr}` | Find patient by MR number |
| PATCH | `/patients/{id}/status` | Update WAITING→ACTIVE→COMPLETED |
| GET/POST | `/procedures/` | Procedure sessions |
| POST | `/procedures/{id}/checklist` | Add checklist item |
| PATCH | `/procedures/{id}/checklist/{item_id}` | Tick/untick checklist |
| POST | `/procedures/{id}/materials` | Log material used |
| POST | `/procedures/{id}/pharmacy` | Log medication dispensed |
| POST | `/procedures/{id}/diagnostics` | Request diagnostic test |
| POST | `/procedures/{id}/notes` | Add clinical note |
| GET/POST | `/leaves/` | Submit / list leave requests |
| PATCH | `/leaves/{id}/status` | Approve or reject (HOD only) |
| GET/POST | `/staff/` | Staff directory |
| GET/POST | `/allocations` | Doctor room allocations |
| GET | `/hod/summary` | Dashboard KPIs |
| GET | `/hod/rooms` | Operatory room status |
| GET | `/hod/monitoring` | Doctor patient counts |
| GET | `/hod/timeline/{mr}` | Patient procedure timeline |

---

## Project Structure

```
AFID backend/
├── main.py               # FastAPI app + CORS + router registration
├── config.py             # Settings from .env
├── database.py           # SQLAlchemy engine + session + Base
├── models.py             # All ORM models (10 tables)
├── schemas.py            # All Pydantic request/response schemas
├── auth.py               # JWT + password hashing + dependencies
├── init_db.py            # One-time seed script
├── requirements.txt
├── .env.example
└── routers/
    ├── auth.py           # /auth/login, /register, /me
    ├── patients.py       # /patients/
    ├── doctors.py        # /doctors/, /allocations
    ├── procedures.py     # /procedures/ + sub-resources
    ├── leaves.py         # /leaves/
    ├── staff.py          # /staff/
    └── hod.py            # /hod/
```
