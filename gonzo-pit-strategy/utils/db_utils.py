"""
Database utilities module.

This module provides utility functions for database operations.
"""


# TODO:  flesh this out to handle DB migrations within the app,  will manually run goose migrations for now
# import logging
# import os
# import subprocess
# from pathlib import Path
#
# logger = logging.getLogger(__name__)
#
#
# def run_migrations(migrate_up: bool = True) -> bool:
#     """Run database migrations using goose.
#
#     Args:
#         migrate_up: True to migrate up, False to migrate down
#
#     Returns:
#         True if migrations were successful, False otherwise
#     """
#     # Get project root
#     project_root = Path(__file__).parent.parent
#     migrations_dir = project_root / 'db' / 'migrations'
#
#     # Get database connection string from environment
#     db_url = os.environ.get('DATABASE_URL')
#     if not db_url:
#         from .config import DatabaseConfig
#         from security.credentials import get_database_credentials
#
#         try:
#             db_config = DatabaseConfig()
#             url_dict = db_config.get_db_url_dict()
#             creds = get_database_credentials()
#
#             # Format for goose
#             db_url = f"postgres://{creds.username}:{creds.password}@{url_dict['host']}:{url_dict['port']}/{url_dict['database']}"
#         except Exception as e:
#             logger.error(f"Failed to build database URL for migrations: {str(e)}")
#             return False
#
#     # Build goose command
#     command = ['goose', '-dir', str(migrations_dir), 'postgres', db_url]
#     if migrate_up:
#         command.append('up')
#     else:
#         command.append('down')
#
#     try:
#         logger.info(f"Running migrations: {'up' if migrate_up else 'down'}")
#         result = subprocess.run(
#             command,
#             check=True,
#             capture_output=True,
#             text=True
#         )
#         logger.info(f"Migration completed successfully: {result.stdout}")
#         return True
#     except subprocess.CalledProcessError as e:
#         logger.error(f"Migration failed: {e.stderr}")
#         return False