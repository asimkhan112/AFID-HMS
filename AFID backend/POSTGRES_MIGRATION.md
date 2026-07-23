# PostgreSQL Migration Guide - Step by Step

## Prerequisites
- PostgreSQL is already installed at `C:\Program Files\PostgreSQL`
- Backend is running on SQLite (data is safe)

## Step 1: Start PostgreSQL Service

1. Press `Windows + R` keys together
2. Type `services.msc` and press Enter
3. Find **postgresql-16** (or postgresql-x64-16) in the list
4. Right-click on it → **Start**
5. If it's already running, you'll see "Running" status

## Step 2: Get PostgreSQL Superuser Password

You need the password you set during PostgreSQL installation. This is the **postgres** user password.

If you forgot it, you'll need to reset it using pgAdmin or psql.

## Step 3: Open Terminal and Run These Commands

Open **PowerShell** or **Command Prompt** and run:

```bash
# Navigate to backend folder
cd "d:\AFID-HMS\AFID backend"

# Create database user (enter postgres password when prompted)
psql -U postgres -c "CREATE USER afid_user WITH PASSWORD 'afid_pass';"

# Create database
psql -U postgres -c "CREATE DATABASE afid_db OWNER afid_user;"

# Grant privileges
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE afid_db TO afid_user;"
```

**Note:** When you run these commands, it will ask for the postgres password. Type it carefully (it won't show on screen) and press Enter.

## Step 4: Create .env File

In the `AFID backend` folder, create a new file named `.env` with this content:

```env
DATABASE_URL=postgresql://afid_user:afid_pass@localhost:5432/afid_db
SECRET_KEY=CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
CORS_ORIGINS=["http://localhost","http://127.0.0.1","null","http://localhost:5173","http://localhost:3000","http://localhost:3001","http://localhost:3002"]
```

## Step 5: Restart Backend

Stop the current backend server (CTRL+C in the terminal where it's running) and start it again:

```bash
cd "d:\AFID-HMS\AFID backend"
uvicorn main:app --reload --port 8000
```

## Step 6: Verify Migration

Check the terminal output - you should see:
```
INFO:     Application startup complete.
```

And no PostgreSQL connection errors.

Visit `http://localhost:8000/docs` in your browser to test the API.

## Troubleshooting

### If you see "password authentication failed":
- Make sure you entered the correct postgres password in Step 3
- If you reset the password, update it: `psql -U postgres -c "ALTER USER afid_user WITH PASSWORD 'afid_pass';"`

### If psql command is not found:
- Add PostgreSQL to PATH:
  1. Search "Edit environment variables" in Windows
  2. Add `C:\Program Files\PostgreSQL\16\bin` to the PATH
  3. Restart terminal and try again

### If tables don't exist:
The backend will automatically create tables on first run when it connects to PostgreSQL.

## Default Credentials
- Database: afid_db
- User: afid_user  
- Password: afid_pass

## Need Help?
If you get stuck on any step, let me know the exact error message and I'll help you fix it.