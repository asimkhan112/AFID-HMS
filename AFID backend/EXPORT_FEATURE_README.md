# Doctor Logout → Patient Queue Export Feature

## Overview
This feature automatically exports a doctor's patient queue to an Excel file when they log out of the system.

## Implementation Details

### Files Modified/Created:

1. **AFID backend/requirements.txt** - Added `openpyxl>=3.1.2` dependency for Excel generation
2. **AFID backend/excel_exporter.py** - New utility module for generating Excel files
3. **AFID backend/routers/auth.py** - Added `/auth/logout` endpoint with export functionality
4. **AFID backend/main.py** - Added logging configuration
5. **AFID backend/.gitignore** - Added exports folder and log files to gitignore
6. **AFID frontend/AFID frontend/api.js** - Modified `logout()` to call backend endpoint

### How It Works:

1. **Frontend (api.js)**:
   - When doctor clicks logout, `logout()` function is called
   - Makes POST request to `/auth/logout` with authentication token
   - If backend call fails, logs warning but continues with logout
   - Always clears localStorage and redirects to login page

2. **Backend (routers/auth.py)**:
   - New `POST /auth/logout` endpoint
   - Requires authentication (doctor must be logged in)
   - Checks if user is a doctor
   - Fetches all patients where `assigned_doctor` matches doctor's name
   - Generates Excel file using `excel_exporter.py`
   - Saves file to `AFID backend/exports/` folder
   - File naming: `DoctorName_YYYY-MM-DD_HH-MM.xlsx`
   - If export fails, logs error but returns success (logout not blocked)
   - Returns success message

3. **Excel Export (excel_exporter.py)**:
   - Creates formatted Excel workbook with patient queue data
   - Headers: Queue Number, Patient ID, Patient Name, Age, Gender, Visit Date, Visit Time, Status, Doctor Name
   - Professional formatting with AFID color scheme
   - Auto-adjusts column widths
   - Freezes header row for easy scrolling

### Excel File Format:

**Filename**: `Dr_Ahmed_2026-07-18_14-30.xlsx`

**Columns**:
1. Queue Number (auto-generated sequential number)
2. Patient ID (MR Number)
3. Patient Name
4. Age (N/A if not available)
5. Gender
6. Visit Date (from registered_at)
7. Visit Time (from registered_at)
8. Status (WAITING/ACTIVE/COMPLETED)
9. Doctor Name

### Error Handling:

- **Export Failure**: Logged to `app.log`, logout continues normally
- **No Patients**: Logs info message, no file created
- **Non-Doctor Users**: Logout works normally, no export attempted
- **Backend Unavailable**: Frontend logs warning, proceeds with client-side logout

### Security:

- Export only occurs for authenticated doctors
- Only exports patients assigned to the logged-in doctor
- Maintains existing JWT authentication
- No changes to existing permissions or roles

### File Structure:

```
AFID backend/
├── exports/                    # NEW: Generated Excel files stored here
│   └── Dr_Ahmed_2026-07-18_14-30.xlsx
├── excel_exporter.py          # NEW: Excel generation utility
├── routers/
│   └── auth.py                # MODIFIED: Added logout endpoint
├── main.py                    # MODIFIED: Added logging
├── requirements.txt           # MODIFIED: Added openpyxl
└── .gitignore                 # MODIFIED: Exclude exports and logs

AFID frontend/AFID frontend/
└── api.js                     # MODIFIED: Backend logout call
```

### Testing:

1. Start backend: `cd "AFID backend" && uvicorn main:app --reload --port 8000`
2. Install dependencies: `pip install -r requirements.txt`
3. Login as doctor in frontend
4. Click logout button
5. Check `AFID backend/exports/` for generated Excel file
6. Check `app.log` for export confirmation

### Logs:

All actions are logged to both console and `app.log`:
- Successful exports with file path and patient count
- Failed exports with error details
- Logout attempts and completions

### Notes:

- Age field shows "N/A" as it's not directly stored in the Patient model
- Export only includes patients with `assigned_doctor` field matching doctor's name
- File naming uses doctor's full name with special characters sanitized
- Exports folder is created automatically if it doesn't exist
- No duplicate exports for single logout (one file per logout)