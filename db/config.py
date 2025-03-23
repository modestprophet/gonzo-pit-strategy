"""
Database configuration module.

This module handles loading database configuration from JSON files and
environment variables, supporting multiple environments (dev/prod).
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration handler."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize database configuration.

        Args:
            config_path: Optional path to the config file. If not provided,
                         defaults to config/database.json relative to project root.
        """
        self.env = os.environ.get('APP_ENV', 'development')

        if config_path is None:
            # Find the project root (where .env is located)
            project_root = Path(__file__).parent.parent
            config_path = project_root / 'config' / 'database.json'

        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file.

        Returns:
            Dict containing database configuration for the current environment.

        Raises:
            FileNotFoundError: If the config file doesn't exist
            KeyError: If the current environment isn't defined in the config
        """
        try:
            with open(self.config_path, 'r') as f:
                db_config = json.load(f)

            if self.env not in db_config:
                logger.error(f"Environment '{self.env}' not found in database config")
                raise KeyError(f"Environment '{self.env}' not found in database config")

            return db_config[self.env]
        except FileNotFoundError:
            logger.error(f"Database config file not found: {self.config_path}")
            raise
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in database config file: {self.config_path}")
            raise

    def get_db_url_dict(self) -> Dict[str, Any]:
        """Get SQLAlchemy URL components as a dictionary.

        Returns:
            Dictionary with SQLAlchemy URL components
        """
        # Copy basic connection parameters
        url_dict = {
            'drivername': self.config['drivername'],
            'host': self.config['host'],
            'port': self.config['port'],
            'database': self.config['database'],
        }

        # Add credentials from vault
        from security.credentials import get_database_credentials
        try:
            creds = get_database_credentials()
            url_dict['username'] = creds.username
            url_dict['password'] = creds.password
        except Exception as e:
            logger.warning(f"Could not load credentials from vault: {e}")
            # Fallback to environment variables if vault fails
            url_dict['username'] = os.environ.get('DB_USERNAME')
            url_dict['password'] = os.environ.get('DB_PASSWORD')

        return url_dict

    def get_pool_options(self) -> Dict[str, Any]:
        """Get connection pool configuration options.

        Returns:
            Dictionary with pool configuration options
        """
        return {
            'pool_size': self.config.get('pool_size', 5),
            'max_overflow': self.config.get('max_overflow', 10),
            'pool_timeout': self.config.get('pool_timeout', 30),
            'pool_recycle': self.config.get('pool_recycle', 1800)
        }