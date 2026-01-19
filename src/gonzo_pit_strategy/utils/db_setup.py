"""
F1 Database Setup and Initialization Tool

This script performs a complete setup of the F1 database:
1. Create the database and schema
2. Run goose migrations
3. Load data from Jolpica CSV files

Usage:
    python -m gonzo_pit_strategy.utils.db_setup [options]

Options:
    --db-admin-username USERNAME   Admin username for database creation
    --db-admin-password PASSWORD   Admin password for database creation
    --app-username USERNAME        Application username to create
    --app-password PASSWORD        Application password to set
    --db-host HOSTNAME             Database hostname [default: localhost]
    --db-port PORT                 Database port [default: 5432]
    --db-name NAME                 Database name [default: f1db]
    --data-directory PATH          Path to raw data directory
    --steps STEPS                  Comma-separated list of steps to run [default: all]
                                   Options: init,migrate,load
    --help                         Show this help message and exit
"""

import os
import sys
import argparse
import subprocess
import csv
from pathlib import Path
from typing import List, Dict

from gonzo_pit_strategy.log.logger import get_logger
from gonzo_pit_strategy.utils.db_utils import get_db_url

logger = get_logger("db_setup")


PROJECT_ROOT = Path(__file__).parent.parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
DATA_DIR = PROJECT_ROOT / "data" / "raw"
INIT_SQL_PATH = PROJECT_ROOT / "db" / "init_db.sql"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="F1 Database Setup Tool")

    parser.add_argument("--db-admin-username", help="Admin username for database creation")
    parser.add_argument("--db-admin-password", help="Admin password for database creation")
    parser.add_argument("--app-username", help="Application username to create")
    parser.add_argument("--app-password", help="Application password to set")
    parser.add_argument("--db-host", default="localhost", help="Database hostname")
    parser.add_argument("--db-port", type=int, default=5432, help="Database port")
    parser.add_argument("--db-name", default="f1db", help="Database name")
    parser.add_argument("--db-schema", default="f1db", help="Schema name")
    parser.add_argument("--data-directory", help="Path to raw data directory")
    parser.add_argument("--steps", default="all",
                        help="Comma-separated list of steps to run (init,migrate,load)")

    return parser.parse_args()


def initialize_database(args: argparse.Namespace) -> bool:
    """Create database, schema, and application user."""
    logger.info("Step 1: Initializing database")

    if not INIT_SQL_PATH.exists():
        logger.error(f"SQL init file not found: {INIT_SQL_PATH}")
        return False

    with open(INIT_SQL_PATH, 'r') as f:
        sql_template = f.read()

    sql = sql_template.replace("{{DB_NAME}}", args.db_name)
    sql = sql.replace("{{APP_USERNAME}}", args.app_username)
    sql = sql.replace("{{APP_PASSWORD}}", args.app_password)

    temp_sql_path = PROJECT_ROOT / "db" / "temp_init.sql"
    with open(temp_sql_path, 'w') as f:
        f.write(sql)

    try:
        cmd = [
            "psql",
            "-h", args.db_host,
            "-p", str(args.db_port),
            "-U", args.db_admin_username,
            "-d", "postgres",
            "-f", str(temp_sql_path)
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = args.db_admin_password

        logger.info(f"Running database initialization script...")
        result = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            if "already exists" in result.stderr:
                logger.warning(f"Database likely already exists: {result.stderr.strip().splitlines()[0]}")
            else:
                logger.error(f"Database initialization failed: {result.stderr}")
                return False

        logger.info("Database initialization successful")
        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        return False

    finally:
        if temp_sql_path.exists():
            temp_sql_path.unlink()


def run_migrations(args: argparse.Namespace) -> bool:
    """Run goose migrations."""
    logger.info("Step 2: Running database migrations")

    if not MIGRATIONS_DIR.exists():
        logger.error(f"Migrations directory not found: {MIGRATIONS_DIR}")
        return False

    connection_string = get_db_url(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_admin_username,
        password=args.db_admin_password
    )

    goose_table = f"{args.db_schema}.goose_db_version"

    cmd = [
        "goose",
        "-table", goose_table,
        "-dir", str(MIGRATIONS_DIR),
        "postgres", connection_string,
        "up"
    ]

    logger.info(f"Applying migrations from {MIGRATIONS_DIR}...")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        logger.error(f"Migration failed: {result.stderr}")
        return False

    logger.info("Migrations successful")
    return True


def load_csv_data(
    file_path: Path, 
    table_name: str, 
    args: argparse.Namespace
) -> bool:
    """Load a single CSV file into a table using psql \copy."""
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}. Skipping.")
        return False

    logger.info(f"Loading {file_path.name} into {args.db_schema}.{table_name}...")
    
    temp_sql = f"\\copy {args.db_schema}.{table_name} FROM '{file_path.absolute()}' WITH (FORMAT CSV, HEADER, DELIMITER ',', NULL '');"
    
    temp_file = PROJECT_ROOT / "temp" / f"load_{table_name}.sql"
    temp_file.parent.mkdir(exist_ok=True)
    temp_file.write_text(temp_sql)

    cmd = [
        "psql",
        "-h", args.db_host,
        "-p", str(args.db_port),
        "-U", args.app_username,
        "-d", args.db_name,
        "-f", str(temp_file)
    ]
    
    env = os.environ.copy()
    env["PGPASSWORD"] = args.app_password
    
    result = subprocess.run(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    if result.returncode == 0:
        logger.info(f"Successfully loaded {table_name}")
        return True
    else:
        logger.error(f"Failed to load {table_name}: {result.stderr}")
        return False
        
    if temp_file.exists():
        temp_file.unlink()


def load_data(args: argparse.Namespace) -> bool:
    """Load data from Jolpica CSV files into database tables."""
    logger.info("Step 3: Loading data from CSV files")

    data_dir = Path(args.data_directory) if args.data_directory else DATA_DIR

    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return False

    load_plan = [
        ("formula_one_baseteam.csv", "base_teams"),
        ("formula_one_championshipsystem.csv", "championship_systems"),
        ("formula_one_pointsystem.csv", "point_systems"),
        ("formula_one_season.csv", "seasons"),
        ("formula_one_circuit.csv", "circuits"),
        ("formula_one_driver.csv", "drivers"),
        ("formula_one_team.csv", "teams"),
        ("formula_one_teamdriver.csv", "team_drivers"),
        ("formula_one_round.csv", "rounds"),
        ("formula_one_session.csv", "sessions"),
        ("formula_one_roundentry.csv", "round_entries"),
        ("formula_one_sessionentry.csv", "session_entries"),
        ("formula_one_lap.csv", "laps"),
        ("formula_one_pitstop.csv", "pitstops"),
        ("formula_one_penalty.csv", "penalties"),
        ("formula_one_championshipadjustment.csv", "championship_adjustments"),
        ("formula_one_driverchampionship.csv", "driver_championships"),
        ("formula_one_teamchampionship.csv", "team_championships"),
    ]

    success_count = 0
    fail_count = 0

    for filename, table in load_plan:
        file_path = data_dir / filename
        if load_csv_data(file_path, table, args):
            success_count += 1
        else:
            fail_count += 1

    logger.info(f"Data loading complete. Success: {success_count}, Failed: {fail_count}")
    return fail_count == 0


def validate_args(args: argparse.Namespace) -> bool:
    """Validate command line arguments based on requested steps."""
    steps = args.steps.lower().split(',')
    if 'all' in steps:
        steps = ['init', 'migrate', 'load']

    missing_args = []

    if 'init' in steps:
        if not args.db_admin_username:
            missing_args.append("--db-admin-username")
        if not args.db_admin_password:
            missing_args.append("--db-admin-password")
        if not args.app_username:
            missing_args.append("--app-username")
        if not args.app_password:
            missing_args.append("--app-password")

    if 'migrate' in steps:
        if not args.db_admin_username:
            missing_args.append("--db-admin-username")
        if not args.db_admin_password:
            missing_args.append("--db-admin-password")

    if 'load' in steps:
        if not args.app_username:
            missing_args.append("--app-username")
        if not args.app_password:
            missing_args.append("--app-password")

    if missing_args:
        logger.error(f"Missing required arguments: {', '.join(missing_args)}")
        return False

    return True


def main():
    args = parse_args()

    steps = args.steps.lower().split(',')
    if 'all' in steps:
        steps = ['init', 'migrate', 'load']

    if not validate_args(args):
        sys.exit(1)

    success = True

    if 'init' in steps:
        if not initialize_database(args):
            logger.error("Database initialization failed")
            sys.exit(1)

    if 'migrate' in steps:
        if not run_migrations(args):
            logger.error("Migrations failed")
            success = False

    if 'load' in steps:
        if not load_data(args):
            logger.error("Data loading failed")
            success = False

    if success:
        logger.info("Database setup completed successfully")
        sys.exit(0)
    else:
        logger.error("Database setup failed")
        sys.exit(1)


if __name__ == "__main__":
    main()