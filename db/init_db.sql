-- Create database if it does not exist
DO
$$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'f1db') THEN
      CREATE DATABASE f1db;
   END IF;
END
$$;

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS f1db;

-- Create application user if it doesn't exist
DO
$$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dbappuser') THEN
      CREATE ROLE dbappuser WITH LOGIN PASSWORD 'securepassword';
   END IF;
END
$$;

-- Grant privileges to application user
GRANT CONNECT ON DATABASE f1db TO dbappuser;
GRANT USAGE, CREATE ON SCHEMA f1db TO dbappuser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA f1db TO dbappuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA f1db TO dbappuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA f1db GRANT ALL ON TABLES TO dbappuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA f1db GRANT ALL ON SEQUENCES TO dbappuser;
