"""
Unified application configuration using Pydantic Settings.

This module provides the AppConfig tree, populated via Environment Variables
and the Vault Settings Source.
"""

import os
from typing import Any, Dict, Optional, Tuple, Type, get_origin, get_args
import inspect

from pydantic import BaseModel, Field, PrivateAttr
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


class VaultSettingsSource(PydanticBaseSettingsSource):
    """Adapter pattern for fetching secrets from HashiCorp Vault.

    This acts as a SettingsSource for Pydantic BaseSettings. If a field
    has a vault path defined in its json_schema_extra (or equivalent),
    this adapter will fetch the secret and inject it into the Pydantic model
    during initialization. It recurses into nested BaseModels.
    """

    def __init__(self, settings_cls: Type[BaseSettings], vault_client: Optional[Any] = None):
        super().__init__(settings_cls)
        
        if vault_client is not None:
            self.vault = vault_client
        else:
            try:
                if all([os.environ.get("VAULT_ADDR"), os.environ.get("VAULT_ROLE_ID"), os.environ.get("VAULT_SECRET_ID")]):
                   self.vault = Multipass()
                else:
                   self.vault = None
            except Exception as e:
                logger.warning(f"Vault initialization skipped or failed: {e}")
                self.vault = None

        self.mount_point = os.environ.get("VAULT_MOUNT_POINT", "secret/data/development").strip("/")

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
    """Database configuration segment."""
    host: str = Field(default=os.environ.get("DB_HOST", "localhost"))
    port: int = Field(default=int(os.environ.get("DB_PORT", "5432")))
    name: str = Field(default=os.environ.get("DB_NAME", "gonzo"))
    user: str = Field(default=os.environ.get("DB_USER", "gonzo_user"))
    
    # Path relative to VAULT_MOUNT_POINT.
    password: str = Field(
        default=os.environ.get("DB_PASSWORD", "local_dev_password"), 
        json_schema_extra={"vault_path": "database"}
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

class LoggingConfig(BaseModel):
    """Logging configuration segment."""
    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


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
    training: TrainingConfig = Field(default_factory=TrainingConfig)

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
        2. Environment variables (env_settings / dotenv_settings)
        3. Vault secrets (VaultSettingsSource)
        """
        vault_client = init_settings.init_kwargs.get('_vault_client')
        
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            VaultSettingsSource(settings_cls, vault_client=vault_client),
            file_secret_settings,
        )
