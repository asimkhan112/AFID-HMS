"""
PostgreSQL setup script for AFID HMS
This script helps you:
1. Create the PostgreSQL database and user
2. Initialize the database schema
3. Seed initial data

Run this AFTER installing PostgreSQL and starting the PostgreSQL service.
"""

import sys
import subprocess
import os

# Add backend root to path
sys.path.insert(0, os.path.dirname(__file__))

from config import settings

def setup_postgres():
    """Create PostgreSQL user and database if they don't exist"""
    
    print("=" * 60)
    print("AFID HMS - PostgreSQL Setup")
    print("=" * 60)
    
    # Parse DATABASE_URL
    # Format: postgresql://user:password@host:port/database
    db_url = settings.DATABASE_URL
    print(f"\nDatabase URL: {db_url}")
    
    if not db_url.startswith("postgresql://"):
        print("\nERROR: DATABASE_URL is not set to PostgreSQL!")
        print("Please update your .env file with:")
        print("DATABASE_URL=postgresql://afid_user:afid_pass@localhost:5432/afid_db")
        return False
    
    # Extract connection details
    parts = db_url.replace("postgresql://", "").split("/")
    if len(parts) < 2:
        print("\nERROR: Invalid DATABASE_URL format!")
        return False
    
    user_pass_host = parts[0]
    database = parts[1].split("?")[0]  # Remove query params if any
    
    user_pass = user_pass_host.split("@")[0]
    host_port = user_pass_host.split("@")[1] if "@" in user_pass_host else "localhost:5432"
    
    username = user_pass.split(":")[0]
    password = user_pass.split(":")[1] if ":" in user_pass else ""
    host = host_port.split(":")[0] if ":" in host_port else "localhost"
    port = host_port.split(":")[1] if ":" in host_port else "5432"
    
    print(f"\nConnection Details:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  User: {username}")
    print(f"  Database: {database}")
    
    # Check if PostgreSQL is running
    print("\n" + "=" * 60)
    print("Step 1: Checking PostgreSQL connection...")
    print("=" * 60)
    
    try:
        # Try to connect to default postgres database
        result = subprocess.run(
            ["psql", "-U", "postgres", "-h", host, "-p", port, "-c", "SELECT version();"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✓ PostgreSQL is running and accessible")
        else:
            print("✗ Cannot connect to PostgreSQL")
            print(f"  Error: {result.stderr}")
            return False
    except FileNotFoundError:
        print("✗ PostgreSQL client (psql) not found!")
        print("  Please install PostgreSQL first:")
        print("  https://www.postgresql.org/download/windows/")
        return False
    except Exception as e:
        print(f"✗ Error checking PostgreSQL: {e}")
        return False
    
    # Create user if it doesn't exist
    print("\n" + "=" * 60)
    print("Step 2: Creating database user...")
    print("=" * 60)
    
    create_user_sql = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{username}') THEN
            CREATE ROLE {username} WITH LOGIN PASSWORD '{password}';
            GRANT ALL PRIVILEGES ON DATABASE postgres TO {username};
            RAISE NOTICE 'Created user: {username}';
        ELSE
            RAISE NOTICE 'User already exists: {username}';
        END IF;
    END
    $$;
    """
    
    result = subprocess.run(
        ["psql", "-U", "postgres", "-h", host, "-p", port, "-c", create_user_sql],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 or "already exists" in result.stderr:
        print(f"✓ User '{username}' ready")
    else:
        print(f"✗ Error creating user: {result.stderr}")
        return False
    
    # Create database if it doesn't exist
    print("\n" + "=" * 60)
    print("Step 3: Creating database...")
    print("=" * 60)
    
    create_db_sql = f"""
    SELECT 'CREATE DATABASE {database} OWNER {username}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{database}')\\gexec
    """
    
    result = subprocess.run(
        ["psql", "-U", "postgres", "-h", host, "-p", port, "-c", create_db_sql],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 or "already exists" in result.stderr:
        print(f"✓ Database '{database}' ready")
    else:
        print(f"✗ Error creating database: {result.stderr}")
        return False
    
    # Grant schema permissions
    print("\n" + "=" * 60)
    print("Step 4: Setting up permissions...")
    print("=" * 60)
    
    grant_sql = f"""
    GRANT ALL ON SCHEMA public TO {username};
    ALTER USER {username} SET search_path TO public;
    """
    
    result = subprocess.run(
        ["psql", "-U", "postgres", "-h", host, "-p", port, "-d", database, "-c", grant_sql],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print(f"✓ Permissions granted to '{username}'")
    else:
        print(f"✗ Error setting permissions: {result.stderr}")
        return False
    
    # Initialize database schema
    print("\n" + "=" * 60)
    print("Step 5: Initializing database schema...")
    print("=" * 60)
    
    try:
        from database import engine, Base
        from models import *  # Import all models
        
        print("Creating tables...")
        Base.metadata.create_all(bind=engine)
        print("✓ Database schema created successfully!")
    except Exception as e:
        print(f"✗ Error creating schema: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ PostgreSQL setup complete!")
    print("=" * 60)
    print(f"\nYou can now start the backend server:")
    print(f"  uvicorn main:app --reload --port 8000")
    print(f"\nAnd access the API docs at:")
    print(f"  http://localhost:8000/docs")
    print("\n")
    
    return True

if __name__ == "__main__":
    try:
        success = setup_postgres()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)