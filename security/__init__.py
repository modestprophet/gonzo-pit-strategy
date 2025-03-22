"""Security module for project.

This module provides secure credential management through HashiCorp Vault integration.
It handles authentication, secret retrieval, and credential management for various
services including databases, cloud providers, and APIs.
"""

from .vault import Multipass
from .credentials import (
    DatabaseCredentials,
    get_database_url
)

# Create a singleton multipass instance for the application
multipass = Multipass()

__all__ = [
    'vault',
    'DatabaseCredentials',
    'get_database_url'
]