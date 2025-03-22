# credential management for various services
"""Credential management for various services.

This module provides structured credential objects for databases, cloud services,
and APIs, with methods to format them for different use cases.
"""

import logging
from dataclasses import dataclass
from sqlalchemy.engine.url import URL
from typing import Dict, Any
from .vault import Multipass, VaultSecretError

logger = logging.getLogger(__name__)


@dataclass
class DatabaseCredentials:
    """Database connection credentials."""
    drivername: str
    username: str
    password: str
    host: str
    port: int
    database: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SQLAlchemy URL."""
        return {
            'drivername': self.drivername,
            'username': self.username,
            'password': self.password,
            'host': self.host,
            'port': self.port,
            'database': self.database
        }

    def get_connection_string(self) -> str:
        """Get connection string in format driver://user:pass@host:port/db."""
        return f"{self.drivername}://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


def get_database_credentials() -> DatabaseCredentials:
    """Retrieve database credentials from Vault.

    Returns:
        DatabaseCredentials object with connection information

    Raises:
        VaultSecretError: If credentials cannot be retrieved
    """
    multipass = Multipass()

    try:
        username = multipass.get_secret('secret/etl/db/user', 'user')
        password = multipass.get_secret('secret/etl/db/password', 'password')

        # Additional database configuration could also be stored in Vault
        # or in application config
        return DatabaseCredentials(
            drivername='postgresql+psycopg2',
            username=username,
            password=password,
            host='10.0.20.18',
            port=5432,
            database='f1db'
        )
    except VaultSecretError as e:
        logger.error(f"Failed to retrieve database credentials: {str(e)}")
        raise


def get_database_url() -> URL:
    """Get SQLAlchemy URL object for database connection.

    Returns:
        SQLAlchemy URL object
    """
    credentials = get_database_credentials()
    return URL.create(**credentials.to_dict())
