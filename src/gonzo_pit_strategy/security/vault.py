"""Fetch a database credential from Vault as a read-only snapshot."""

from dataclasses import dataclass, field

import hvac
from hvac.exceptions import InvalidPath
from hvac.exceptions import VaultError as HvacError
from requests.exceptions import RequestException


class VaultError(Exception):
    """Base exception for Vault-related errors."""


class VaultAuthenticationError(VaultError):
    """Raised when authentication with Vault fails."""


class VaultSecretError(VaultError):
    """Raised when a secret cannot be retrieved."""


@dataclass(frozen=True, slots=True)
class Multipass:
    """An immutable password snapshot; its representation omits the password."""

    db_password: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.db_password, str) or not self.db_password:
            raise VaultSecretError(
                "Vault database password must be a nonempty string; "
                "check the password field in the configured secret."
            ) from None

    @classmethod
    def from_vault(
        cls, *, url: str, role_id: str, secret_id: str, mount_point: str
    ) -> "Multipass":
        """Authenticate once and read the password using hvac's 30-second timeout."""
        prefix = mount_point.strip("/")
        if not prefix:
            raise VaultSecretError("Vault mount point must contain a secret path.")

        try:
            client = hvac.Client(url=url)
            response = client.auth.approle.login(
                role_id=role_id, secret_id=secret_id, use_token=False
            )
        except (HvacError, RequestException):
            raise VaultAuthenticationError(
                "Vault AppRole authentication failed; check connection settings, "
                "credentials, and AppRole permissions."
            ) from None

        auth = response.get("auth") if isinstance(response, dict) else None
        token = auth.get("client_token") if isinstance(auth, dict) else None
        if not isinstance(token, str) or not token:
            raise VaultAuthenticationError(
                "Vault returned a malformed authentication response; "
                "expected a nonempty client token from AppRole login."
            ) from None
        client.token = token

        try:
            response = client.read(f"{prefix}/password")
        except InvalidPath:
            raise VaultSecretError(
                "Vault database secret was not found; check the configured "
                "mount point and password path."
            ) from None
        except (HvacError, RequestException):
            raise VaultSecretError(
                "Vault database secret read failed; check connectivity "
                "and read permissions for the configured password path."
            ) from None

        if response is None:
            raise VaultSecretError(
                "Vault database secret was not found; check the configured "
                "mount point and password path."
            ) from None
        data = response.get("data") if isinstance(response, dict) else None
        if (
            isinstance(data, dict)
            and "password" not in data
            and "value" not in data
            and "data" in data
        ):
            metadata = data.get("metadata")
            version = metadata.get("version") if isinstance(metadata, dict) else None
            if type(version) is not int or version < 1:
                raise VaultSecretError(
                    "Vault returned a malformed KV v2 response. "
                    "Expected metadata identifying a positive secret version."
                ) from None
            data = data["data"]
        if not isinstance(data, dict):
            raise VaultSecretError(
                "Vault returned a malformed secret response; "
                "expected a KV v1 or KV v2 data object."
            ) from None
        if "password" not in data and "value" not in data:
            raise VaultSecretError(
                "Vault database secret is missing the password field; "
                "provide password or the legacy value field."
            ) from None
        password = data["password"] if "password" in data else data["value"]
        return cls(db_password=password)
