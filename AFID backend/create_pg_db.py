"""
Create PostgreSQL database and user using Python
"""
import sys
import os

# Add backend root to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    print("ERROR: psycopg2 is not installed. Installing now...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "psycopg2-binary"], check=True)
    import psycopg2
    from psycopg2 import sql

# Connect to default postgres database to create user and database
print("Connecting to PostgreSQL (postgres database)...")
try:
    # Try connecting without password first (trust auth)
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="postgres",
        user="postgres"
    )
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("✓ Connected to PostgreSQL")
    
    # Create user
    print("\nCreating user 'afid_user'...")
    try:
        cursor.execute("CREATE ROLE afid_user WITH LOGIN PASSWORD 'afid_pass';")
        print("✓ User 'afid_user' created")
    except psycopg2.errors.DuplicateObject:
        cursor.execute("ALTER USER afid_user WITH PASSWORD 'afid_pass';")
        print("✓ User 'afid_user' already exists, password updated")
    
    # Create database
    print("\nCreating database 'afid_db'...")
    try:
        cursor.execute("CREATE DATABASE afid_db OWNER afid_user;")
        print("✓ Database 'afid_db' created")
    except psycopg2.errors.DuplicateDatabase:
        print("✓ Database 'afid_db' already exists")
    
    # Grant privileges
    print("\nGranting privileges...")
    cursor.execute("GRANT ALL PRIVILEGES ON DATABASE afid_db TO afid_user;")
    print("✓ Privileges granted")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*60)
    print("✓ PostgreSQL database and user created successfully!")
    print("="*60)
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)