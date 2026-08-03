"""
PostgreSQL Migration Script for AFID HMS
This script will:
1. Download and install PostgreSQL (if not already installed)
2. Create database and user
3. Initialize the schema
4. Provide next steps

Usage: python migrate_to_postgres.py
"""

import os
import sys
import subprocess
import platform

def print_step(step_num, total_steps, message):
    print(f"\n{'='*70}")
    print(f"Step {step_num}/{total_steps}: {message}")
    print(f"{'='*70}\n")

def check_postgres_installed():
    """Check if PostgreSQL is installed"""
    print_step(1, 5, "Checking PostgreSQL Installation")
    
    # Common PostgreSQL installation paths on Windows
    pg_paths = [
        r"C:\Program Files\PostgreSQL",
        r"C:\Program Files (x86)\PostgreSQL",
    ]
    
    for path in pg_paths:
        if os.path.exists(path):
            print(f"✓ PostgreSQL found at: {path}")
            return True
    
    print("✗ PostgreSQL not found in default locations")
    return False

def install_postgresql_windows():
    """Download and install PostgreSQL on Windows"""
    print("\nPostgreSQL is not installed. Starting installation...")
    
    # PostgreSQL installer URL
    installer_url = "https://get.enterprisedb.com/postgresql/postgresql-16.3-1-windows-x64.exe"
    installer_path = os.path.join(os.path.dirname(__file__), "postgresql-16-installer.exe")
    
    print(f"\nDownloading PostgreSQL installer from:")
    print(f"  {installer_url}")
    print(f"\nThis may take a few minutes...")
    
    try:
        # Download installer
        import urllib.request
        urllib.request.urlretrieve(installer_url, installer_path)
        print(f"✓ Download complete: {installer_path}")
    except Exception as e:
        print(f"\n✗ Failed to download PostgreSQL installer")
        print(f"  Error: {e}")
        print(f"\nPlease download manually from: https://www.postgresql.org/download/windows/")
        return False
    
    print("\nStarting PostgreSQL installer...")
    print("IMPORTANT: During installation, please note down the password you set for the 'postgres' user!")
    print("\nThe installer will now run. Please follow the setup wizard.")
    
    # Run installer
    try:
        subprocess.run([installer_path, "--mode", "unattended"], check=True)
        print("\n✓ PostgreSQL installation completed")
        return True
    except Exception as e:
        print(f"\n✗ Installation failed: {e}")
        print("\nPlease install PostgreSQL manually from: https://www.postgresql.org/download/windows/")
        return False

def start_postgresql_service():
    """Start PostgreSQL service if not running"""
    print_step(2, 5, "Starting PostgreSQL Service")
    
    try:
        # Check if PostgreSQL service exists and start it
        result = subprocess.run(
            ["sc", "query", "postgresql-16"],
            capture_output=True,
            text=True
        )
        
        if "RUNNING" in result.stdout:
            print("✓ PostgreSQL service is already running")
            return True
        
        print("Starting PostgreSQL service...")
        subprocess.run(["sc", "start", "postgresql-16"], check=True)
        print("✓ PostgreSQL service started")
        return True
        
    except Exception as e:
        print(f"⚠ Could not start PostgreSQL service automatically")
        print(f"  Error: {e}")
        print("\nPlease start PostgreSQL manually:")
        print("  1. Open Services (services.msc)")
        print("  2. Find 'postgresql-16' service")
        print("  3. Right-click → Start")
        return False

def get_postgres_credentials():
    """Prompt user for PostgreSQL credentials"""
    print_step(3, 5, "PostgreSQL Credentials Setup")
    
    print("Please provide PostgreSQL connection details:")
    print("(Default values shown in parentheses, press Enter to use them)")
    
    host = input("\nHost (localhost): ").strip() or "localhost"
    port = input("Port (5432): ").strip() or "5432"
    user = input("Superuser name (postgres): ").strip() or "postgres"
    password = input("Superuser password: ").strip()
    
    if not password:
        print("\n⚠ Warning: No password provided for postgres user")
        print("If your postgres user has no password, you can proceed.")
        print("Otherwise, please restart and enter the correct password.")
    
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password
    }

def create_database_and_user(creds):
    """Create AFID database and user"""
    print_step(4, 5, "Creating Database and User")
    
    # Create SQL commands
    create_user_sql = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'afid_user') THEN
            CREATE ROLE afid_user WITH LOGIN PASSWORD 'afid_pass';
            RAISE NOTICE 'Created user: afid_user';
        ELSE
            ALTER USER afid_user WITH PASSWORD 'afid_pass';
            RAISE NOTICE 'Updated password for user: afid_user';
        END IF;
    END
    $$;
    """
    
    create_db_sql = """
    SELECT 'CREATE DATABASE afid_db OWNER afid_user'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'afid_db')\\gexec
    """
    
    grant_sql = """
    GRANT ALL PRIVILEGES ON DATABASE afid_db TO afid_user;
    """
    
    # Execute SQL commands
    try:
        # Create/update user
        print("Creating database user 'afid_user'...")
        result = subprocess.run(
            ["psql", "-U", creds["user"], "-h", creds["host"], "-p", creds["port"], 
             "-c", create_user_sql],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✓ User 'afid_user' created/updated")
        else:
            print(f"⚠ User creation output: {result.stderr}")
        
        # Create database
        print("\nCreating database 'afid_db'...")
        result = subprocess.run(
            ["psql", "-U", creds["user"], "-h", creds["host"], "-p", creds["port"],
             "-c", create_db_sql],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 or "already exists" in result.stderr:
            print("✓ Database 'afid_db' created or already exists")
        else:
            print(f"✗ Error creating database: {result.stderr}")
            return False
        
        # Grant privileges
        print("\nGranting privileges...")
        result = subprocess.run(
            ["psql", "-U", creds["user"], "-h", creds["host"], "-p", creds["port"],
             "-d", "afid_db", "-c", grant_sql],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✓ Privileges granted")
        
        return True
        
    except FileNotFoundError:
        print("✗ psql command not found!")
        print("  Please ensure PostgreSQL is installed and psql is in PATH")
        return False
    except Exception as e:
        print(f"✗ Error creating database: {e}")
        return False

def update_env_file():
    """Update .env file with PostgreSQL URL"""
    print_step(5, 5, "Updating Configuration")
    
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env_example_path = os.path.join(os.path.dirname(__file__), ".env.example")
    
    # Read existing .env or create from .env.example
    if os.path.exists(env_path):
        print(f"Found existing .env file: {env_path}")
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Update DATABASE_URL
        import re
        content = re.sub(
            r'DATABASE_URL=.*',
            'DATABASE_URL=postgresql://afid_user:afid_pass@localhost:5432/afid_db',
            content
        )
        
        with open(env_path, 'w') as f:
            f.write(content)
        
        print("✓ Updated DATABASE_URL in .env file")
    else:
        # Create .env from .env.example
        if os.path.exists(env_example_path):
            with open(env_example_path, 'r') as f:
                content = f.read()
            
            # Uncomment PostgreSQL URL and comment SQLite
            content = content.replace(
                '# DATABASE_URL=postgresql://afid_user:afid_pass@localhost:5432/afid_db',
                'DATABASE_URL=postgresql://afid_user:afid_pass@localhost:5432/afid_db'
            )
            content = content.replace(
                'DATABASE_URL=sqlite:///./afid.db',
                '# DATABASE_URL=sqlite:///./afid.db'
            )
            
            with open(env_path, 'w') as f:
                f.write(content)
            
            print(f"✓ Created .env file from .env.example")
        else:
            print("✗ .env.example not found")
            return False
    
    print("\n✓ Configuration updated successfully!")
    print("\nYour DATABASE_URL is now:")
    print("  postgresql://afid_user:afid_pass@localhost:5432/afid_db")
    print("\n⚠ IMPORTANT: Change the password from 'afid_pass' to a secure password!")
    
    return True

def initialize_schema():
    """Initialize database schema using SQLAlchemy"""
    print_step(6, 6, "Initializing Database Schema")
    
    try:
        print("Importing models and creating tables...")
        sys.path.insert(0, os.path.dirname(__file__))
        
        # Import models to register them with Base
        import models  # noqa: F401
        from database import engine, Base
        
        print("Creating all tables...")
        Base.metadata.create_all(bind=engine)
        print("✓ Database schema created successfully!")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error creating schema: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*70)
    print("AFID HMS - PostgreSQL Migration Tool")
    print("="*70)
    
    # Check if already on PostgreSQL
    import config
    config_path = os.path.join(os.path.dirname(__file__), ".env")
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            content = f.read()
            if 'postgresql://' in content and not content.strip().startswith('#'):
                print("\n✓ PostgreSQL configuration already found in .env")
                proceed = input("Do you want to continue anyway? (y/N): ").strip().lower()
                if proceed != 'y':
                    print("\nMigration cancelled.")
                    return
    
    # Step 1: Check/Install PostgreSQL
    if not check_postgres_installed():
        response = input("\nDo you want to download and install PostgreSQL now? (y/N): ").strip().lower()
        if response == 'y':
            if not install_postgresql_windows():
                print("\n✗ Installation failed. Please install PostgreSQL manually.")
                return
        else:
            print("\nPlease install PostgreSQL first, then run this script again.")
            print("Download from: https://www.postgresql.org/download/windows/")
            return
    
    # Step 2: Start service
    start_postgresql_service()
    
    # Step 3: Get credentials
    print("\nNote: You need the postgres superuser password to proceed.")
    creds = get_postgres_credentials()
    
    # Step 4: Create database and user
    if not create_database_and_user(creds):
        print("\n✗ Database creation failed. Please check the errors above.")
        return
    
    # Step 5: Update config
    if not update_env_file():
        return
    
    # Step 6: Initialize schema
    if not initialize_schema():
        print("\n⚠ Schema initialization failed, but configuration is complete.")
        print("You can try running the backend server to see if tables are created automatically.")
        return
    
    # Success!
    print("\n" + "="*70)
    print("✓ PostgreSQL Migration Complete!")
    print("="*70)
    
    print("\nNext steps:")
    print("  1. Verify .env file has correct DATABASE_URL")
    print("  2. Restart the backend server: uvicorn main:app --reload --port 8000")
    print("  3. Check that the server starts without errors")
    print("  4. Test the API at: http://localhost:8000/docs")
    
    print("\nDefault credentials:")
    print("  Database: afid_db")
    print("  User: afid_user")
    print("  Password: afid_pass")
    print("\n⚠ IMPORTANT: Change the default password in production!")
    
    print("\nTo view database tables, run:")
    print("  psql -U afid_user -d afid_db -c '\\dt'")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)