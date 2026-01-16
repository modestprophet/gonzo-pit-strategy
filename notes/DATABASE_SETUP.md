# Database Setup Guide

This guide explains how to initialize the PostgreSQL database for the F1 Pit Strategy application.

## Prerequisites

- PostgreSQL 12+ installed and running
- `psql` command-line client available
- `goose` migration tool installed
- Python 3.8+ with required project dependencies

## Database Architecture Overview

The database initialization process consists of three main steps:

1. **Database Initialization** (`init`) - Creates database, schema, and application user
2. **Migrations** (`migrate`) - Runs Goose migrations to create tables and indexes
3. **Data Loading** (`load`) - Imports Jolpica F1 CSV data into the database

## Database Configuration

The application uses a configuration file at `config/database.json` for runtime database settings. However, initialization requires command-line arguments for security.

Sample database configuration format:
```json
{
  "development": {
    "drivername": "postgresql",
    "host": "localhost",
    "port": 5432,
    "database": "f1db",
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800
  },
  "production": {
    "drivername": "postgresql",
    "host": "your-production-host",
    "port": 5432,
    "database": "f1db",
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30,
    "pool_recycle": 1800
  }
}
```

## Connection Strings

### PostgreSQL Connection String Format:
```
postgresql://username:password@host:port/database
```

### Sample Connection Strings:

**Local Development:**
```
postgresql://postgres:admin123@localhost:5432/f1db
```

**Remote Production:**
```
postgresql://f1app_user:secure_password@db.example.com:5432/f1db_production
```

## Setup Instructions

### 1. Complete Database Setup (All Steps)

For a fresh installation, run all steps:

```bash
python -m gonzo_pit_strategy.utils.db_setup \
  --db-admin-username postgres \
  --db-admin-password your_admin_password \
  --app-username f1app_user \
  --app-password your_app_password \
  --db-host localhost \
  --db-port 5432 \
  --db-name f1db \
  --data-directory ./data/raw
```

### 2. Individual Steps

You can run individual steps using the `--steps` parameter:

#### Initialize Database Only:
```bash
python -m gonzo_pit_strategy.utils.db_setup \
  --steps init \
  --db-admin-username postgres \
  --db-admin-password your_admin_password \
  --app-username f1app_user \
  --app-password your_app_password \
  --db-host localhost \
  --db-name f1db
```

#### Run Migrations Only:
```bash
python -m gonzo_pit_strategy.utils.db_setup \
  --steps migrate \
  --db-admin-username postgres \
  --db-admin-password your_admin_password \
  --db-host localhost \
  --db-name f1db
```

#### Load CSV Data Only:
```bash
python -m gonzo_pit_strategy.utils.db_setup \
  --steps load \
  --app-username f1app_user \
  --app-password your_app_password \
  --db-host localhost \
  --db-name f1db \
  --data-directory ./data/raw
```

#### Multiple Selected Steps:
```bash
python -m gonzo_pit_strategy.utils.db_setup \
  --steps init,migrate \
  --db-admin-username postgres \
  --db-admin-password your_admin_password \
  --app-username f1app_user \
  --app-password your_app_password \
  --db-host localhost \
  --db-name f1db
```

## Command Line Arguments

### Required Arguments

| argument | Description | Example |
|----------|-------------|---------|
| `--db-admin-username` | PostgreSQL admin user with database creation privileges | `postgres` |
| `--db-admin-password` | Password for admin user | `admin123` |
| `--app-username` | Application database user to create | `f1app_user` |
| `--app-password` | Password for application user | `app_password123` |

### Optional Arguments

| argument | Description | Default | Example |
|----------|-------------|---------|---------|
| `--db-host` | Database hostname | `localhost` | `db.example.com` |
| `--db-port` | Database port | `5432` | `5433` |
| `--db-name` | Database name | `f1db` | `f1db_production` |
| `--db-schema` | Schema name | `f1db` | `f1db` |
| `--data-directory` | Path to CSV data files | `./data/raw` | `/path/to/csv/files` |
| `--steps` | Steps to run (init,migrate,load) | `all` | `init,migrate` |

## Database Schema

The database contains two main schema areas:

### Application Management Tables
- `application_logs` - Application logging and errors
- `dataset_versions` - ML dataset versioning
- `model_metadata` - ML model tracking
- `training_runs` - Training run metadata
- `training_metrics` - Model performance metrics

### F1 Data Tables (via Jolpica CSV import)
- `base_teams`, `teams` - F1 team information
- `drivers`, `team_drivers` - Driver data
- `circuits`, `rounds`, `sessions` - Race information
- `sessions`, `laps`, `pitstops` - Race session data
- `championship_systems`, `point_systems` - Scoring systems
- `driver_championships`, `team_championships` - Championship standings

## Data Loading Requirements

For CSV data loading, ensure you have the Jolpica F1 CSV files in the specified data directory:

```
data/raw/
├── formula_one_baseteam.csv
├── formula_one_championshipsystem.csv
├── formula_one_pointsystem.csv
├── formula_one_season.csv
├── formula_one_circuit.csv
├── formula_one_driver.csv
├── formula_one_team.csv
├── formula_one_teamdriver.csv
├── formula_one_round.csv
├── formula_one_session.csv
├── formula_one_roundentry.csv
├── formula_one_sessionentry.csv
├── formula_one_lap.csv
├── formula_one_pitstop.csv
├── formula_one_penalty.csv
├── formula_one_championshipadjustment.csv
├── formula_one_driverchampionship.csv
└── formula_one_teamchampionship.csv
```

## Security Configuration

### Database User Permissions

The setup script creates an application user with the following permissions:
- `CONNECT` to the specified database
- `USAGE` on the `f1db` schema
- `ALL PRIVILEGES` on all tables in the `f1db` schema
- Default privileges for future tables and sequences

### Environment Variables

For runtime configuration, you can set these environment variables:
- `APP_ENV` - Environment (development/production)
- `DB_USERNAME` - Application database username
- `DB_PASSWORD` - Application database password
- `PGPASSWORD` - PostgreSQL password for psql commands

## Troubleshooting

### Common Issues

1. **Database Already Exists**: The script handles this gracefully and continues with user creation.

2. **Permission Denied**: Ensure your admin user has `CREATEDB` privileges.

3. **Goose Not Found**: Install goose migration tool:
   ```bash
   go install github.com/pressly/goose/v3/cmd/goose@latest
   ```

4. **CSV Files Not Found**: Verify the `--data-directory` path is correct and all CSV files exist.

5. **Connection Failed**: Check PostgreSQL is running and credentials are correct.

### Verification

After setup, verify the database:

```bash
# Connect as application user
psql -h localhost -U f1app_user -d f1db

# List tables
\dt f1db.*

# Check user connections
SELECT datname, usename FROM pg_stat activity WHERE datname = 'f1db';
```

## Production Considerations

1. **Use Environment Variables**: Avoid hardcoding passwords in scripts
2. **SSL Connections**: Add `sslmode=require` to connection strings for production
3. **Connection Pooling**: Adjust pool settings based on your application load
4. **Backup Strategy**: Implement regular database backups
5. **Security**: Use PostgreSQL's row-level security if needed for multi-tenancy