"""Read-only database credential snapshots from HashiCorp Vault."""

from .vault import Multipass, VaultAuthenticationError, VaultError, VaultSecretError

__all__ = [
    "Multipass",
    "VaultAuthenticationError",
    "VaultError",
    "VaultSecretError",
]
