import os
from unittest.mock import Mock

import hvac
import pytest
from pydantic import ValidationError

from gonzo_pit_strategy.config.config import AppConfig, DatabaseConfig
from gonzo_pit_strategy.security import VaultError


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in os.environ:
        if name in {"DB", "VAULT", "PATHS", "LOGGING"} or name.startswith(
            ("DB__", "VAULT__", "PATHS__", "LOGGING__")
        ):
            monkeypatch.delenv(name)


@pytest.fixture
def vault_sdk(monkeypatch):
    client = Mock()
    client.auth.approle.login.return_value = {"auth": {"client_token": "test-token"}}
    client.read.return_value = {
        "data": {"data": {"password": "from-vault"}, "metadata": {"version": 1}}
    }
    factory = Mock(return_value=client)
    monkeypatch.setattr(hvac, "Client", factory)
    return client, factory


def test_bootstrap_merges_dotenv_environment_and_arguments(monkeypatch, tmp_path, vault_sdk):
    client, factory = vault_sdk
    (tmp_path / ".env").write_text(
        'VAULT={"addr":"https://vault.invalid","role_id":"dotenv-role",'
        '"secret_id":"dotenv-secret","mount_point":"secret/data/dotenv"}\n'
    )
    monkeypatch.setenv("VAULT__ROLE_ID", "env-role")

    config = AppConfig(vault={"mount_point": "/secret/data/explicit/"})

    assert config.db.password == "from-vault"
    factory.assert_called_once_with(url="https://vault.invalid")
    client.auth.approle.login.assert_called_once_with(
        role_id="env-role", secret_id="dotenv-secret", use_token=False,
    )
    client.read.assert_called_once_with("secret/data/explicit/password")


@pytest.mark.parametrize("source", ["arguments", "model", "environment", "dotenv"])
def test_supplied_password_bypasses_even_malformed_vault_settings(
    monkeypatch, tmp_path, vault_sdk, source,
):
    _, factory = vault_sdk
    monkeypatch.setenv("VAULT", "not-json")
    (tmp_path / ".env").write_text("VAULT=not-json\n")
    kwargs = {"vault": {"role_id": []}}
    if source == "arguments":
        kwargs["db"] = {"password": "supplied-password"}
    elif source == "model":
        kwargs["db"] = DatabaseConfig(password="supplied-password")
    elif source == "environment":
        monkeypatch.setenv("DB__PASSWORD", "supplied-password")
    else:
        (tmp_path / ".env").write_text("VAULT=not-json\nDB__PASSWORD=supplied-password\n")

    config = AppConfig(**kwargs)

    assert config.db.password == "supplied-password"
    assert "supplied-password" not in repr(config)
    factory.assert_not_called()


@pytest.mark.parametrize("password", [None, "", 42, {"private": "sentinel-password"}])
def test_invalid_supplied_password_fails_without_vault(vault_sdk, password):
    _, factory = vault_sdk

    with pytest.raises(ValidationError) as error:
        AppConfig(db={"password": password})

    assert "db.password" in str(error.value)
    assert "sentinel-password" not in str(error.value)
    factory.assert_not_called()


@pytest.mark.parametrize("db", [None, "invalid", []])
def test_invalid_database_settings_fail_without_fetching_a_secret(vault_sdk, db):
    _, factory = vault_sdk

    with pytest.raises(ValidationError, match="db"):
        AppConfig(db=db)

    factory.assert_not_called()


@pytest.mark.parametrize(
    ("vault", "missing"),
    [
        ({}, ("VAULT__ADDR", "VAULT__ROLE_ID", "VAULT__SECRET_ID")),
        ({"addr": "https://vault.invalid"}, ("VAULT__ROLE_ID", "VAULT__SECRET_ID")),
        ({"role_id": "private-role", "secret_id": "private-secret"}, ("VAULT__ADDR",)),
        ({"addr": "https://vault.invalid", "role_id": "private-role", "secret_id": ""},
         ("VAULT__SECRET_ID",)),
    ],
)
def test_required_vault_settings_fail_with_field_names(vault_sdk, vault, missing):
    _, factory = vault_sdk

    with pytest.raises(VaultError) as error:
        AppConfig(vault=vault)

    assert all(name in str(error.value) for name in missing)
    assert "DB__PASSWORD" in str(error.value)
    assert "private-role" not in str(error.value)
    assert "private-secret" not in str(error.value)
    factory.assert_not_called()


def test_no_password_and_no_vault_is_an_error(vault_sdk):
    _, factory = vault_sdk
    with pytest.raises(VaultError, match="DB__PASSWORD"):
        AppConfig()
    factory.assert_not_called()


def test_malformed_vault_json_fails_without_exposing_input(monkeypatch, vault_sdk):
    _, factory = vault_sdk
    monkeypatch.setenv("VAULT", "private-malformed-json")

    with pytest.raises(VaultError, match="Invalid Vault settings") as error:
        AppConfig()

    assert "private-malformed-json" not in str(error.value)
    factory.assert_not_called()


@pytest.mark.parametrize("stage", ["authentication", "read", "response"])
def test_vault_failures_do_not_fall_back_or_expose_secrets(vault_sdk, stage, caplog):
    client, _ = vault_sdk
    if stage == "authentication":
        client.auth.approle.login.side_effect = hvac.exceptions.Forbidden("private-error")
    elif stage == "read":
        client.read.side_effect = hvac.exceptions.InvalidPath("private-error")
    else:
        client.read.return_value = {"data": {"other": "private-error"}}

    with pytest.raises(VaultError) as error:
        AppConfig(vault={
            "addr": "https://vault.invalid",
            "role_id": "private-role",
            "secret_id": "private-secret",
        })

    for secret in ("private-error", "private-role", "private-secret"):
        assert secret not in str(error.value)
        assert secret not in caplog.text


def test_bootstrap_honors_custom_dotenv_and_disabled_dotenv(tmp_path, vault_sdk):
    client, factory = vault_sdk
    (tmp_path / ".env").write_text("VAULT=invalid-default-file\n")
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "VAULT__ADDR=https://vault.invalid\n"
        "VAULT__ROLE_ID=custom-role\n"
        "VAULT__SECRET_ID=custom-secret\n"
    )
    kwargs = {"_env_file": env_file}

    assert AppConfig(**kwargs).db.password == "from-vault"
    client.auth.approle.login.assert_called_once_with(
        role_id="custom-role", secret_id="custom-secret", use_token=False,
    )
    factory.reset_mock()
    kwargs["_env_file"] = None
    with pytest.raises(VaultError, match="DB__PASSWORD"):
        AppConfig(**kwargs)
    factory.assert_not_called()
