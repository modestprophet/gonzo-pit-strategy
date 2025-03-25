"""Vault integration for secure secrets management.

This module provides a client for interacting with HashiCorp Vault, including
authentication, secret retrieval, and renewal of credentials.
"""

import os
import hvac
from hvac import exceptions
from pathlib import Path
from dotenv import load_dotenv
from functools import wraps
from typing import Optional, Dict, List, Any

from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)


class VaultError(Exception):
    """Base exception for Vault-related errors."""
    pass


class VaultAuthenticationError(VaultError):
    """Raised when authentication with Vault fails."""
    pass


class VaultSecretError(VaultError):
    """Raised when a secret cannot be retrieved."""
    pass


def handle_vault_errors(func):
    """Decorator to handle Vault client errors."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except hvac.exceptions.Unauthorized as e:
            logger.error(f"Vault authentication failed: {str(e)}")
            raise VaultAuthenticationError(f"Vault authentication failed: {str(e)}")
        except hvac.exceptions.InvalidPath as e:
            logger.error(f"Invalid Vault path: {str(e)}")
            raise VaultSecretError(f"Invalid Vault path: {str(e)}")
        except hvac.exceptions.VaultError as e:
            logger.error(f"Vault operation failed: {str(e)}")
            raise VaultError(f"Vault operation failed: {str(e)}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")
            raise VaultError(f"An unexpected error occurred: {str(e)}")

    return wrapper


class Multipass:
    """Client for interacting with HashiCorp Vault.

    This class provides a singleton interface to Vault operations,
    handling authentication, token renewal, and secret retrieval.
    """
    _instance: Optional['Multipass'] = None

    def __new__(cls) -> 'Multipass':
        if cls._instance is None:
            cls._instance = super(Multipass, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        # Load environment variables
        env_file = Path(__file__).parent.parent / '.env'
        load_dotenv(env_file)

        # Vault configuration
        self.vault_addr: str = os.environ.get("VAULT_ADDR")
        self.vault_role_id: str = os.environ.get("VAULT_ROLE_ID")
        self.vault_secret_id: str = os.environ.get("VAULT_SECRET_ID")

        if not all([self.vault_addr, self.vault_role_id, self.vault_secret_id]):
            logger.error("Vault environment variables not set")
            raise VaultAuthenticationError(
                "Missing required environment variables: "
                "VAULT_ADDR, VAULT_ROLE_ID, VAULT_SECRET_ID"
            )

        # Initialize Vault client
        self.client: hvac.Client = hvac.Client(url=self.vault_addr)
        self._authenticate()

        # Start token renewal process
        self._token_expires_at: Optional[int] = None  # Will be set during authentication

        self._initialized = True
        logger.info("Vault client initialized successfully")

    def _authenticate(self) -> None:
        """Authenticate with Vault using AppRole."""
        try:
            auth_response: Dict[str, Any] = self.client.auth.approle.login(
                role_id=self.vault_role_id,
                secret_id=self.vault_secret_id
            )

            # Store token expiry for renewal
            if 'lease_duration' in auth_response['auth']:
                self._token_expires_at = auth_response['auth']['lease_duration']

            logger.debug("Successfully authenticated with Vault")
        except Exception as e:
            logger.error(f"Failed to authenticate with Vault: {str(e)}")
            raise VaultAuthenticationError(f"Failed to authenticate with Vault: {str(e)}")

    @handle_vault_errors
    def get_secret(self, path: str, key: Optional[str] = None) -> Any:
        """Retrieve a secret from Vault.

        Args:
            path: Path to the secret in Vault
            key: Optional specific key to retrieve from the secret

        Returns:
            The secret value or dict of values

        Raises:
            VaultSecretError: If the secret cannot be retrieved
        """
        try:
            response: Dict[str, Any] = self.client.read(path)

            if not response or 'data' not in response:
                raise VaultSecretError(f"No secret found at {path}")

            if key:
                if key not in response['data']:
                    raise VaultSecretError(f"Key '{key}' not found in secret at {path}")
                return response['data'][key]

            return response['data']
        except hvac.exceptions.InvalidPath:
            raise VaultSecretError(f"Secret not found at path: {path}")

    @handle_vault_errors
    def list_secrets(self, path: str) -> List[str]:
        """List secrets at a given path.

        Args:
            path: Path in Vault to list

        Returns:
            List of secret names
        """
        try:
            response: Dict[str, Any] = self.client.list(path)
            if not response or 'data' not in response or 'keys' not in response['data']:
                return []
            return response['data']['keys']
        except hvac.exceptions.InvalidPath:
            return []

    def is_authenticated(self) -> bool:
        """Check if the client is authenticated with Vault."""
        return self.client.is_authenticated()