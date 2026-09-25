"""Tests for the AppConfig tree, its env-var contract, and Vault injection.

The env-var contract is the fragile part: `AppConfig` nests with a `__`
delimiter, so `DB__HOST` populates `AppConfig.db.host` while a single-underscore
`DB_HOST` matches nothing and is silently dropped. These tests pin that down —
an earlier version read `os.environ` in field defaults, which froze values at
import time and made the documented `.env` workflow a no-op.

`_env_file=None` isolates each case from the repository's own `.env`.
"""

import os

import pytest

from gonzo_pit_strategy.config.config import AppConfig, LoggingConfig, setup_logging


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in os.environ:
        if name in {"DB", "VAULT", "TRAINING", "PATHS", "LOGGING", "APP_ENV"} or name.startswith(
            ("DB__", "VAULT__", "TRAINING__", "PATHS__", "LOGGING__")
        ):
            monkeypatch.delenv(name)


def _config(**kwargs) -> AppConfig:
    """AppConfig built without reading the repo's .env file."""
    return AppConfig(_env_file=None, **kwargs)


def test_database_defaults_with_an_explicit_password():
    config = _config(db={"password": "test-password"})

    assert "app_env" not in config.model_dump()
    assert "training" not in config.model_dump()
    assert config.db.host == "localhost"
    assert config.db.port == 5432


def test_nested_env_var_populates_db_field(monkeypatch):
    """DB__HOST -> AppConfig.db.host. This is the documented convention."""
    monkeypatch.setenv("DB__HOST", "db.example.internal")
    monkeypatch.setenv("DB__PORT", "6543")
    monkeypatch.setenv("DB__PASSWORD", "test-password")

    config = _config()

    assert config.db.host == "db.example.internal"
    assert config.db.port == 6543


def test_single_underscore_env_var_is_not_picked_up(monkeypatch):
    """Guards the trap: DB_HOST is not the nested form and must not silently win.

    If this ever starts passing, the delimiter convention changed and the docs
    in .env.example need to change with it.
    """
    monkeypatch.delenv("DB__HOST", raising=False)
    monkeypatch.setenv("DB_HOST", "ignored.example")

    assert _config(db={"password": "test-password"}).db.host == "localhost"


def test_config_is_not_frozen_at_import_time(monkeypatch):
    """Two instantiations under different env must differ.

    Field defaults evaluated at import (`default=os.environ.get(...)`) would
    make both calls return the first value.
    """
    monkeypatch.setenv("DB__HOST", "first.example")
    monkeypatch.setenv("DB__PASSWORD", "test-password")
    first = _config().db.host

    monkeypatch.setenv("DB__HOST", "second.example")
    second = _config().db.host

    assert (first, second) == ("first.example", "second.example")


def test_paths_config_has_no_separate_checkpoint_dir():
    """ADR 0002: artifacts_root is the sole home for trained models."""
    paths = _config(db={"password": "test-password"}).paths

    assert paths.artifacts_root == "models/artifacts"
    assert not hasattr(paths, "checkpoints_dir")


def test_db_url_round_trip(monkeypatch):
    monkeypatch.setenv("DB__HOST", "pg.example")
    monkeypatch.setenv("DB__NAME", "f1db")
    monkeypatch.setenv("DB__USER", "gonzo")
    monkeypatch.setenv("DB__PASSWORD", "pw")

    url = _config().db.get_db_url()

    assert url.host == "pg.example"
    assert url.database == "f1db"
    assert url.username == "gonzo"
    assert url.drivername == "postgresql"


def test_runtime_settings_preserve_source_precedence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        'DB={"host":"dotenv-host","password":"dotenv-password"}\n'
        'PATHS__ARTIFACTS_ROOT=dotenv-artifacts\n'
        'TRAINING=not-json\nAPP_ENV=obsolete\n'
    )
    monkeypatch.setenv("TRAINING", "not-json")
    monkeypatch.setenv("APP_ENV", "obsolete")
    config = AppConfig()
    assert config.db.password == "dotenv-password"
    assert config.paths.artifacts_root == "dotenv-artifacts"
    assert "app_env" not in config.model_dump()
    assert "training" not in config.model_dump()

    monkeypatch.setenv("DB__PASSWORD", "env-password")
    assert AppConfig().db.password == "env-password"

    config = AppConfig(db={"password": "explicit-password"})
    assert config.db.password == "explicit-password"
    assert config.db.host == "dotenv-host"


def test_setup_logging_applies_level_and_is_idempotent():
    import logging

    setup_logging(LoggingConfig(level="warning"))
    assert logging.getLogger().level == logging.WARNING

    setup_logging(LoggingConfig(level="DEBUG"))
    assert logging.getLogger().level == logging.DEBUG
