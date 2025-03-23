"""Credential management for various services.

This module provides structured credential objects for databases, cloud services,
and APIs, with methods to format them for different use cases.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any
from .vault import Multipass, VaultSecretError

logger = logging.getLogger(__name__)


@dataclass
class DatabaseCredentials:
    """Database connection credentials."""
    username: str
    password: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for SQLAlchemy URL."""
        return {
            'username': self.username,
            'password': self.password,
        }


def get_database_credentials() -> DatabaseCredentials:
    """Retrieve database credentials from Vault.

    Returns:
        DatabaseCredentials object with username and password

    Raises:
        VaultSecretError: If credentials cannot be retrieved
    """

    try:
        multipass = Multipass()
        username = multipass.get_secret('secret/etl/db/user', 'user')
        password = multipass.get_secret('secret/etl/db/password', 'password')
    except Exception as e:
        logger.error(f"Failed to retrieve database credentials: {str(e)}")
        raise VaultSecretError(f"Failed to retrieve database credentials: {str(e)}")

    return DatabaseCredentials(
        username=username,
        password=password
    )