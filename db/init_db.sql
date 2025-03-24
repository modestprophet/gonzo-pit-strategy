-- db/init_db.sql
-- SQL template for initializing F1 database
-- {{DB_NAME}} will be replaced with the actual database name
-- {{APP_USERNAME}} will be replaced with the application username
-- {{APP_PASSWORD}} will be replaced with the application password

-- Create database if it doesn't exist
CREATE DATABASE {{DB_NAME}};

-- Connect to the database
\c {{DB_NAME}}

-- Create schema
CREATE SCHEMA IF NOT EXISTS f1db;

-- Create application user
DO $$BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = '{{APP_USERNAME}}'
    ) THEN
        CREATE USER {{APP_USERNAME}} WITH ENCRYPTED PASSWORD '{{APP_PASSWORD}}';
    ELSE
        ALTER USER {{APP_USERNAME}} WITH ENCRYPTED PASSWORD '{{APP_PASSWORD}}';
    END IF;
END$$;

-- Grant privileges to application user
GRANT USAGE ON SCHEMA f1db TO {{APP_USERNAME}};
GRANT CONNECT ON DATABASE {{DB_NAME}} TO {{APP_USERNAME}};
GRANT ALL PRIVILEGES ON SCHEMA f1db TO {{APP_USERNAME}};
ALTER DEFAULT PRIVILEGES IN SCHEMA f1db GRANT ALL PRIVILEGES ON TABLES TO {{APP_USERNAME}};
ALTER DEFAULT PRIVILEGES IN SCHEMA f1db GRANT ALL PRIVILEGES ON SEQUENCES TO {{APP_USERNAME}};