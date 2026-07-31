"""
Unified application configuration using Pydantic Settings.

This module provides the AppConfig tree, populated via Environment Variables,
a `.env` file, and the Vault Settings Source.

Environment variables use pydantic-settings' nested delimiter `__`, so a field
at `AppConfig.db.host` is set by `DB__HOST`. This is the single mechanism —
nothing in this tree reads `os.environ` directly (ADR 0001 §1).
"""

from typing import Any, Dict, Optional, Tuple, Type, get_origin
import inspect

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from sqlalchemy.engine.url import URL

from gonzo_pit_strategy.security.vault import Multipass
from gonzo_pit_strategy.training.config import TrainingConfig
import logging

logger = logging.getLogger(__name__)


class VaultConfig(BaseModel):
    """HashiCorp Vault connection settings.

    Vault is optional: when `addr`, `role_id`, or `secret_id` is unset, the
    Vault Settings Source disables itself and every field falls through to its
    environment value or default.
    """

    addr: Optional[str] = None
    role_id: Optional[str] = None
    secret_id: Optional[str] = None
    mount_point: str = "secret/data/development"

    @property
    def enabled(self) -> bool:
        return bool(self.addr and self.role_id and self.secret_id)


class VaultSettingsSource(PydanticBaseSettingsSource):
    """Adapter pattern for fetching secrets from HashiCorp Vault.

    This acts as a SettingsSource for Pydantic BaseSettings. If a field
    has a vault path defined in its json_schema_extra (or equivalent),
    this adapter will fetch the secret and inject it into the Pydantic model
    during initialization. It recurses into nested BaseModels.
    """

    def __init__(
        self,
        settings_cls: Type[BaseSettings],
        vault_config: VaultConfig,
        vault_client: Optional[Any] = None,
    ):
        super().__init__(settings_cls)

        if vault_client is not None:
            self.vault = vault_client
        elif vault_config.enabled:
            try:
                self.vault = Multipass(
                    url=vault_config.addr,
                    role_id=vault_config.role_id,
                    secret_id=vault_config.secret_id,
                )
            except Exception as e:
                logger.warning(f"Vault initialization failed; using defaults: {e}")
                self.vault = None
        else:
            logger.debug("Vault not configured; skipping secret injection.")
            self.vault = None

        self.mount_point = vault_config.mount_point.strip("/")

    def _get_vault_secrets(self, model_cls: Type[BaseModel]) -> Dict[str, Any]:
        """Recursively fetch vault secrets for a model's fields."""
        d = {}
        for field_name, field in model_cls.model_fields.items():
            # Check if this field has a vault path
            vault_path = None
            extra = field.json_schema_extra
            if isinstance(extra, dict):
                 vault_path = extra.get("vault_path")
            elif callable(extra):
                 e = extra()
                 if isinstance(e, dict):
                     vault_path = e.get("vault_path")

            if vault_path and self.vault:
                full_path = f"{self.mount_point}/{vault_path.strip('/')}"
                try:
                    secret_data = self.vault.get_secret(full_path)
                    if isinstance(secret_data, dict):
                        if field_name in secret_data:
                            d[field_name] = secret_data[field_name]
                        elif "value" in secret_data:
                             d[field_name] = secret_data["value"]
                    elif secret_data is not None:
                        d[field_name] = secret_data
                except Exception as e:
                    logger.warning(f"Failed to fetch vault secret at {full_path}: {e}")

            # Recurse into nested models
            origin = get_origin(field.annotation) or field.annotation
            if inspect.isclass(origin) and issubclass(origin, BaseModel):
                nested_secrets = self._get_vault_secrets(origin)
                if nested_secrets:
                    d[field_name] = nested_secrets

        return d

    def get_field_value(
        self, field: Any, field_name: str
    ) -> Tuple[Any, str, bool]:
        # Handled dynamically in __call__ via _get_vault_secrets
        pass

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        return value

    def __call__(self) -> Dict[str, Any]:
        if not self.vault:
            return {}
        return self._get_vault_secrets(self.settings_cls)


class DatabaseConfig(BaseModel):
    """Database configuration segment.

    Set via `DB__HOST`, `DB__PORT`, `DB__NAME`, `DB__USER`, `DB__PASSWORD`.
    Defaults below are plain literals: reading `os.environ` here would freeze
    values at import time and bypass the settings sources entirely.
    """
    host: str = "localhost"
    port: int = 5432
    name: str = "gonzo"
    user: str = "gonzo_user"

    # Path relative to VaultConfig.mount_point.
    password: str = Field(
        default="local_dev_password",
        json_schema_extra={"vault_path": "password"},
    )


    def get_db_url(self) -> Any:
        """Get SQLAlchemy URL."""
        return URL.create(
            drivername='postgresql',
            host=self.host,
            port=self.port,
            database=self.name,
            username=self.user,
            password=self.password,
        )

    def get_pool_options(self) -> Dict[str, Any]:
        """Get connection pool configuration options."""
        return {
            'pool_size': 5,
            'max_overflow': 10,
            'pool_timeout': 30,
            'pool_recycle': 1800
        }

class PathsConfig(BaseModel):
    """Filesystem locations for training outputs. Injected per ADR 0001 —
    no component should derive these from os.getcwd().

    `artifacts_root` is the sole home for trained models: an Artifact directory
    holds the model plus its manifest (ADR 0002), so there is no separate
    checkpoint location.
    """
    artifacts_root: str = "models/artifacts"
    tensorboard_dir: str = "logs/tensorboard"
    experiments_dir: str = "config/experiments"


class LoggingConfig(BaseModel):
    """Logging configuration segment. Set via `LOGGING__LEVEL`."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(config: LoggingConfig) -> None:
    """Configure root logging once, at the entry point.

    Every module logs through `logging.getLogger(__name__)`; without this call
    those records have nowhere to go and are silently discarded.
    """
    logging.basicConfig(
        level=config.level.upper(),
        format=config.format,
        force=True,
    )


class AppConfig(BaseSettings):
    """Master application configuration hierarchy.
    
    This pulls from Environment Variables, then `.env` files, then Vault.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__", 
        extra="ignore"
    )

    app_env: str = Field(default="development", description="Environment: development, testing, production")

    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Inject Vault as a settings source.

        Priority:
        1. Explicitly passed kwargs (init_settings)
        2. Environment variables (env_settings), then `.env` (dotenv_settings)
        3. Vault secrets (VaultSettingsSource)

        Vault's own connection settings must be resolved before the Vault
        source can be built, so the earlier sources are consulted here to
        assemble `AppConfig.vault` (ADR 0001 §1 — no `os.environ` reads).
        """
        vault_client = init_settings.init_kwargs.get('_vault_client')

        merged: Dict[str, Any] = {}
        for source in (dotenv_settings, env_settings, init_settings):
            try:
                merged.update(source() or {})
            except Exception as e:  # a malformed source must not block startup
                logger.warning(f"Settings source {source.__class__.__name__} failed: {e}")

        raw_vault = merged.get("vault") or {}
        if isinstance(raw_vault, str):
            raw_vault = {}
        try:
            vault_config = VaultConfig(**raw_vault)
        except Exception as e:
            logger.warning(f"Invalid vault configuration, Vault disabled: {e}")
            vault_config = VaultConfig()

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            VaultSettingsSource(
                settings_cls, vault_config=vault_config, vault_client=vault_client
            ),
            file_secret_settings,
        )
