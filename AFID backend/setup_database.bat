@echo off
chcp 65001 >nul
echo.
echo ========================================
echo AFID HMS - Database Setup (PostgreSQL)
echo ========================================
echo.

REM Find PostgreSQL bin directory
set PSQL_PATH=
if exist "C:\Program Files\PostgreSQL\16\bin\psql.exe" (
    set PSQL_PATH=C:\Program Files\PostgreSQL\16\bin
) else if exist "C:\Program Files\PostgreSQL\15\bin\psql.exe" (
    set PSQL_PATH=C:\Program Files\PostgreSQL\15\bin
) else if exist "C:\Program Files\PostgreSQL\14\bin\psql.exe" (
    set PSQL_PATH=C:\Program Files\PostgreSQL\14\bin
)

if "%PSQL_PATH%"=="" (
    echo ERROR: PostgreSQL not found in default locations
    echo Please install PostgreSQL from: https://www.postgresql.org/download/windows/
    pause
    exit /b 1
)

echo Found PostgreSQL at: %PSQL_PATH%
echo.

REM Add to PATH for this session
set PATH=%PATH%;%PSQL_PATH%

REM Get postgres password
set /p POSTGRES_PASSWORD="Enter postgres superuser password: "
echo.

REM Set PGPASSWORD environment variable for this session
set PGPASSWORD=%POSTGRES_PASSWORD%

REM Create user (suppress errors if exists)
echo Creating database user...
"%PSQL_PATH%\psql.exe" -U postgres -c "CREATE USER afid_user WITH PASSWORD 'afid_pass';" 2>&1
echo.

REM Create database (suppress errors if exists)
echo Creating database...
"%PSQL_PATH%\psql.exe" -U postgres -c "CREATE DATABASE afid_db OWNER afid_user;" 2>&1
echo.

REM Grant privileges
echo Granting privileges...
"%PSQL_PATH%\psql.exe" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE afid_db TO afid_user;" 2>&1
echo.

echo ========================================
echo Database setup completed!
echo ========================================
echo.
echo Now creating .env file...

REM Create .env file
(
echo DATABASE_URL=postgresql://afid_user:afid_pass@localhost:5432/afid_db
echo SECRET_KEY=CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING
echo ALGORITHM=HS256
echo ACCESS_TOKEN_EXPIRE_MINUTES=480
echo CORS_ORIGINS=["http://localhost","http://127.0.0.1","null","http://localhost:5173","http://localhost:3000","http://localhost:3001","http://localhost:3002"]
) > .env

echo .env file created successfully!
echo.
echo ========================================
echo Next steps:
echo ========================================
echo 1. Restart the backend server (if running)
echo 2. Visit http://localhost:8000/docs to test
echo.
echo Default credentials:
echo   Database: afid_db
echo   User: afid_user
echo   Password: afid_pass
echo.
echo IMPORTANT: Change the default password in production!
echo.
pause