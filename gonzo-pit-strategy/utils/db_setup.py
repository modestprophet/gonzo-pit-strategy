"""
F1 Database Setup and Initialization Tool

This script performs a complete setup of the F1 database:
1. Create the database and schema
2. Run goose migrations
3. Load data from TSV files

Usage:
    python db_setup.py [options]

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
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("db_setup")

# Project structure
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

    # Read SQL template and replace placeholders
    with open(INIT_SQL_PATH, 'r') as f:
        sql_template = f.read()

    sql = sql_template.replace("{{DB_NAME}}", args.db_name)
    sql = sql.replace("{{APP_USERNAME}}", args.app_username)
    sql = sql.replace("{{APP_PASSWORD}}", args.app_password)

    # Write to temporary file
    temp_sql_path = PROJECT_ROOT / "db" / "temp_init.sql"
    with open(temp_sql_path, 'w') as f:
        f.write(sql)

    try:
        # Run psql command
        cmd = [
            "psql",
            "-h", args.db_host,
            "-p", str(args.db_port),
            "-U", args.db_admin_username,
            "-d", "postgres",
            "-f", str(temp_sql_path)
        ]

        # Set PGPASSWORD environment variable for psql
        env = os.environ.copy()
        env["PGPASSWORD"] = args.db_admin_password

        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.returncode != 0:
            logger.error(f"Database initialization failed: {result.stderr}")
            return False

        logger.info("Database initialization successful")
        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        return False

    finally:
        # Clean up temporary SQL file
        if temp_sql_path.exists():
            temp_sql_path.unlink()


def run_migrations(args: argparse.Namespace) -> bool:
    """Run goose migrations."""
    logger.info("Step 2: Running database migrations")

    if not MIGRATIONS_DIR.exists():
        logger.error(f"Migrations directory not found: {MIGRATIONS_DIR}")
        return False

    # Create connection string for goose
    connection_string = (
        f"postgres://{args.db_admin_username}:{args.db_admin_password}"
        f"@{args.db_host}:{args.db_port}/{args.db_name}?sslmode=disable"
    )

    goose_table = f"{args.db_schema}.goose_db_version"

    try:
        # Run goose up command
        cmd = [
            "goose",
            "-table", goose_table,
            "-dir", str(MIGRATIONS_DIR),
            "postgres", connection_string,
            "up"
        ]

        logger.info(f"Running: goose -dir {MIGRATIONS_DIR} postgres [connection_string] up")
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

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return False


def load_data(args: argparse.Namespace) -> bool:
    """Load data from TSV files into database tables."""
    logger.info("Step 3: Loading data from TSV files")

    data_dir = Path(args.data_directory) if args.data_directory else DATA_DIR

    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return False

    # Create temporary script directory if it doesn't exist
    temp_dir = PROJECT_ROOT / "temp"
    temp_dir.mkdir(exist_ok=True)

    # Create connection string for psql
    env = os.environ.copy()
    env["PGPASSWORD"] = args.app_password

    success_count = 0
    fail_count = 0

    for tsv_file in data_dir.glob("*.tsv"):
        # Extract base name without timestamp and extension
        base_name = tsv_file.name.split('_')[0]

        # Create a temporary SQL script
        temp_sql_path = temp_dir / f"load_{base_name}.sql"
        with open(temp_sql_path, 'w') as f:
            f.write(f"SET search_path TO {args.db_schema};\n")
            f.write(
                f"\\copy {base_name} FROM '{tsv_file}' WITH (FORMAT csv, DELIMITER E'\\t', HEADER true, NULL '');\n")

        try:
            # Run psql with the script file
            cmd = [
                "psql",
                "-h", args.db_host,
                "-p", str(args.db_port),
                "-U", args.app_username,
                "-d", args.db_name,
                "-f", str(temp_sql_path)
            ]

            logger.info(f"Loading {tsv_file.name} into f1db.{base_name}")
            result = subprocess.run(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"Loading data failed for {base_name}: {result.stderr}")
                fail_count += 1
            else:
                logger.info(f"Successfully loaded f1db.{base_name}")
                success_count += 1

        except Exception as e:
            logger.error(f"Loading data failed for {base_name}: {str(e)}")
            fail_count += 1

        # Clean up the temporary SQL file
        temp_sql_path.unlink()

    # Clean up temp directory if empty
    try:
        temp_dir.rmdir()
    except:
        pass

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
    """Main function to run the database setup process."""
    args = parse_args()

    # Get steps to run
    steps = args.steps.lower().split(',')
    if 'all' in steps:
        steps = ['init', 'migrate', 'load']

    # Validate arguments
    if not validate_args(args):
        sys.exit(1)

    # Run requested steps
    success = True

    if 'init' in steps:
        if not initialize_database(args):
            logger.error("Database initialization failed")
            success = False
            # Don't continue if initialization fails
            sys.exit(1)

    if 'migrate' in steps and success:
        if not run_migrations(args):
            logger.error("Migrations failed")
            success = False

    if 'load' in steps and success:
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