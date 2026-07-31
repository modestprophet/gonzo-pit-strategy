"""Tests for the AppConfig tree, its env-var contract, and Vault injection.

The env-var contract is the fragile part: `AppConfig` nests with a `__`
delimiter, so `DB__HOST` populates `AppConfig.db.host` while a single-underscore
`DB_HOST` matches nothing and is silently dropped. These tests pin that down —
an earlier version read `os.environ` in field defaults, which froze values at
import time and made the documented `.env` workflow a no-op.

`_env_file=None` isolates each case from the repository's own `.env`.
"""


from gonzo_pit_strategy.config.config import AppConfig, LoggingConfig, setup_logging


def _config(**kwargs) -> AppConfig:
    """AppConfig built without reading the repo's .env file."""
    return AppConfig(_env_file=None, **kwargs)


class StubVault:
    """Stands in for Multipass, recording the paths it was asked for."""

    def __init__(self, secrets=None):
        self.requested = []
        self._secrets = secrets if secrets is not None else {"password": "from-vault"}

    def get_secret(self, path):
        self.requested.append(path)
        return self._secrets


def test_defaults_are_sane_without_env_or_vault(monkeypatch):
    monkeypatch.delenv("DB__HOST", raising=False)
    config = _config()

    assert config.app_env == "development"
    assert config.db.host == "localhost"
    assert config.db.port == 5432
    assert config.vault.enabled is False


def test_nested_env_var_populates_db_field(monkeypatch):
    """DB__HOST -> AppConfig.db.host. This is the documented convention."""
    monkeypatch.setenv("DB__HOST", "db.example.internal")
    monkeypatch.setenv("DB__PORT", "6543")

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

    assert _config().db.host == "localhost"


def test_config_is_not_frozen_at_import_time(monkeypatch):
    """Two instantiations under different env must differ.

    Field defaults evaluated at import (`default=os.environ.get(...)`) would
    make both calls return the first value.
    """
    monkeypatch.setenv("DB__HOST", "first.example")
    first = _config().db.host

    monkeypatch.setenv("DB__HOST", "second.example")
    second = _config().db.host

    assert (first, second) == ("first.example", "second.example")


def test_vault_settings_source_injects_password(monkeypatch):
    """A field marked with `vault_path` is fetched under the configured mount."""
    monkeypatch.setenv("VAULT__MOUNT_POINT", "secret/data/testing")
    stub = StubVault()

    config = _config(_vault_client=stub)

    assert config.db.password == "from-vault"
    assert stub.requested == ["secret/data/testing/password"]


def test_env_var_takes_precedence_over_vault(monkeypatch):
    monkeypatch.setenv("DB__PASSWORD", "from-env")
    stub = StubVault()

    assert _config(_vault_client=stub).db.password == "from-env"


def test_vault_failure_degrades_to_default(monkeypatch):
    """Vault is optional by design; a broken client must not block startup."""

    class ExplodingVault:
        def get_secret(self, path):
            raise RuntimeError("vault unreachable")

    monkeypatch.delenv("DB__PASSWORD", raising=False)

    config = _config(_vault_client=ExplodingVault())

    assert config.db.password == "local_dev_password"


def test_vault_enabled_requires_all_three_credentials(monkeypatch):
    for var in ("VAULT__ADDR", "VAULT__ROLE_ID", "VAULT__SECRET_ID"):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("VAULT__ADDR", "http://vault.example:8200")
    assert _config().vault.enabled is False

    monkeypatch.setenv("VAULT__ROLE_ID", "role")
    monkeypatch.setenv("VAULT__SECRET_ID", "secret")
    assert _config().vault.enabled is True


def test_paths_config_has_no_separate_checkpoint_dir():
    """ADR 0002: artifacts_root is the sole home for trained models."""
    paths = _config().paths

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


def test_setup_logging_applies_level_and_is_idempotent():
    import logging

    setup_logging(LoggingConfig(level="warning"))
    assert logging.getLogger().level == logging.WARNING

    setup_logging(LoggingConfig(level="DEBUG"))
    assert logging.getLogger().level == logging.DEBUG
