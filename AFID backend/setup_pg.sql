-- Create user if not exists
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

-- Create database if not exists
SELECT 'CREATE DATABASE afid_db OWNER afid_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'afid_db')\gexec

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE afid_db TO afid_user;