"""Security module for project.

This module provides secure credential management through HashiCorp Vault integration.
It handles authentication, secret retrieval, and credential management for various
services including databases, cloud providers, and APIs.
"""

from .vault import Multipass

__all__ = [
    'Multipass',
    'VaultSecretError',
]
