-- db/init_db.sql
-- Template for the Init phase of Provisioning; rendered by
-- `db/provisioning.py:render_init_sql`, which supplies the quoting.
--
-- Placeholders are substituted with *already-quoted* SQL, so they must not be
-- wrapped in quotes here. A name can appear both as an identifier and as a
-- string literal, which quote differently, hence the separate placeholders:
--
--   {{DB_NAME}}                 database name, as an identifier
--   {{DB_SCHEMA}}               schema name, as an identifier
--   {{APP_USERNAME}}            App Role name, as an identifier
--   {{APP_USERNAME_LITERAL}}    App Role name, as a string literal
--   {{APP_PASSWORD_LITERAL}}    App Role password, as a string literal

-- Create database if it doesn't exist. Failing here because it already exists
-- is tolerated by the Init phase, which runs psql without ON_ERROR_STOP so the
-- grants below still apply on a re-run.
CREATE DATABASE {{DB_NAME}};

-- Connect to the database. This meta-command is why Init keeps psql.
\c {{DB_NAME}}

-- Create schema
CREATE SCHEMA IF NOT EXISTS {{DB_SCHEMA}};

-- Create application user
DO $$BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_catalog.pg_roles WHERE rolname = {{APP_USERNAME_LITERAL}}
    ) THEN
        CREATE USER {{APP_USERNAME}} WITH ENCRYPTED PASSWORD {{APP_PASSWORD_LITERAL}};
    ELSE
        ALTER USER {{APP_USERNAME}} WITH ENCRYPTED PASSWORD {{APP_PASSWORD_LITERAL}};
    END IF;
END$$;

-- Grant privileges to application user
GRANT USAGE ON SCHEMA {{DB_SCHEMA}} TO {{APP_USERNAME}};
GRANT CONNECT ON DATABASE {{DB_NAME}} TO {{APP_USERNAME}};
-- dbt materializes into its own schemas (f1db_staging, f1db_intermediate,
-- f1db_features, f1db_ml_prep) and creates them on first run, so the app role
-- needs CREATE on the database, not just on the f1db schema.
GRANT CREATE ON DATABASE {{DB_NAME}} TO {{APP_USERNAME}};
GRANT ALL PRIVILEGES ON SCHEMA {{DB_SCHEMA}} TO {{APP_USERNAME}};
ALTER DEFAULT PRIVILEGES IN SCHEMA {{DB_SCHEMA}} GRANT ALL PRIVILEGES ON TABLES TO {{APP_USERNAME}};
ALTER DEFAULT PRIVILEGES IN SCHEMA {{DB_SCHEMA}} GRANT ALL PRIVILEGES ON SEQUENCES TO {{APP_USERNAME}};
