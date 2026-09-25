"""Command settings from environment variables, .env files, and optional Vault.

Nested environment variables use ``__``, such as ``DB__HOST``.
Training parameters belong to TrainingConfig and come from JSON or defaults.
"""

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    SettingsError,
)
from sqlalchemy.engine.url import URL

from gonzo_pit_strategy.security.vault import Multipass, VaultError


class _CommandSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        hide_input_in_errors=True,
    )


class VaultConfig(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    addr: str = Field(min_length=1, repr=False)
    role_id: str = Field(min_length=1, repr=False)
    secret_id: str = Field(min_length=1, repr=False)
    mount_point: str = "secret/data/development"


class _VaultSettings(_CommandSettings):
    vault: VaultConfig


class VaultSettingsSource(PydanticBaseSettingsSource):
    def __init__(
        self,
        settings_cls: type[BaseSettings],
        init: PydanticBaseSettingsSource,
        env: PydanticBaseSettingsSource,
        dotenv: PydanticBaseSettingsSource,
    ):
        super().__init__(settings_cls)
        self._sources = init, env, dotenv

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        db = self.current_state.get("db", {})
        if not isinstance(db, dict) or "password" in db:
            return {}

        init, env, dotenv = self._sources
        if not (
            isinstance(init, InitSettingsSource)
            and isinstance(env, EnvSettingsSource)
            and isinstance(dotenv, DotEnvSettingsSource)
        ):
            raise TypeError("Vault bootstrap requires Pydantic init, env, and dotenv sources")

        bootstrap_kwargs = {
            **init.init_kwargs,
            "_env_file": dotenv.env_file,
            "_env_file_encoding": dotenv.env_file_encoding,
            "_case_sensitive": env.case_sensitive,
            "_env_prefix": env.env_prefix,
            "_env_prefix_target": env.env_prefix_target,
            "_env_nested_delimiter": env.env_nested_delimiter,
            "_env_nested_max_split": env.env_nested_max_split,
            "_env_ignore_empty": env.env_ignore_empty,
            "_env_parse_none_str": env.env_parse_none_str,
            "_env_parse_enums": env.env_parse_enums,
        }
        try:
            vault = _VaultSettings(**bootstrap_kwargs).vault
        except ValidationError as exc:
            fields = []
            for error in exc.errors(include_input=False, include_context=False):
                if error["loc"] == ("vault",):
                    fields.extend(("VAULT__ADDR", "VAULT__ROLE_ID", "VAULT__SECRET_ID"))
                else:
                    fields.append("__".join(str(part).upper() for part in error["loc"]))
            raise VaultError(
                f"Invalid or missing Vault settings: {', '.join(fields)}. "
                "Set DB__PASSWORD to supply the database password without Vault."
            ) from None
        except SettingsError:
            raise VaultError("Invalid Vault settings. Check VAULT and VAULT__* values.") from None

        multipass = Multipass.from_vault(
            url=vault.addr,
            role_id=vault.role_id,
            secret_id=vault.secret_id,
            mount_point=vault.mount_point,
        )
        return {"db": {"password": multipass.db_password}}


class DatabaseConfig(BaseModel):
    """Database configuration segment.

    Set via `DB__HOST`, `DB__PORT`, `DB__NAME`, `DB__USER`, `DB__PASSWORD`.
    Defaults below are plain literals: reading `os.environ` here would freeze
    values at import time and bypass the settings sources entirely.
    """
    model_config = ConfigDict(hide_input_in_errors=True)

    host: str = "localhost"
    port: int = 5432
    name: str = "gonzo"
    user: str = "gonzo_user"

    password: str = Field(min_length=1, strict=True, repr=False)


    def get_db_url(self) -> URL:
        """Get SQLAlchemy URL."""
        return URL.create(
            drivername='postgresql',
            host=self.host,
            port=self.port,
            database=self.name,
            username=self.user,
            password=self.password,
        )

    def get_pool_options(self) -> dict[str, Any]:
        """Get connection pool configuration options."""
        return {
            'pool_size': 5,
            'max_overflow': 10,
            'pool_timeout': 30,
            'pool_recycle': 1800
        }

class DefaultConfigPaths(BaseModel):
    experiments_dir: str = "config/experiments"


class PathsConfig(DefaultConfigPaths):
    """Filesystem locations for training outputs."""
    artifacts_root: str = "models/artifacts"
    tensorboard_dir: str = "logs/tensorboard"


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


class GenerateDefaultSettings(_CommandSettings):
    paths: DefaultConfigPaths = Field(default_factory=DefaultConfigPaths)


class LoadSettings(_CommandSettings):
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class AppConfig(_CommandSettings):
    """Training infrastructure settings, including optional Vault secrets."""

    db: DatabaseConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            VaultSettingsSource(
                settings_cls, init_settings, env_settings, dotenv_settings,
            ),
            file_secret_settings,
        )
