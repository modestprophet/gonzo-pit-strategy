import gc
import logging
import traceback
import weakref
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock

import hvac.exceptions
import pytest
import requests.exceptions

from gonzo_pit_strategy.security import (
    Multipass,
    VaultAuthenticationError,
    VaultError,
    VaultSecretError,
)

URL = "https://vault.invalid"
ROLE_ID = "role-sentinel"
SECRET_ID = "secret-id-sentinel"


def fetch_snapshot(mount_point="/secret/application/"):
    return Multipass.from_vault(
        url=URL,
        role_id=ROLE_ID,
        secret_id=SECRET_ID,
        mount_point=mount_point,
    )


@pytest.fixture
def vault_sdk(monkeypatch):
    login = Mock(return_value={"auth": {"client_token": "token-sentinel"}})
    client = SimpleNamespace(
        auth=SimpleNamespace(approle=SimpleNamespace(login=login)),
        read=Mock(return_value={"data": {"password": "password-sentinel"}}),
        token=None,
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr("gonzo_pit_strategy.security.vault.hvac.Client", factory)
    return factory, client


def test_fetches_database_password_from_kv_v1(vault_sdk):
    snapshot = fetch_snapshot()

    assert snapshot.db_password == "password-sentinel"
    assert type(snapshot.db_password) is str


@pytest.mark.parametrize(
    "response, expected",
    [
        ({"data": {"value": "fallback"}}, "fallback"),
        ({"data": {"password": "primary", "value": "fallback"}}, "primary"),
        (
            {"data": {"data": {"password": "v2"}, "metadata": {"version": 1}}},
            "v2",
        ),
        (
            {"data": {"data": {"value": "v2-fallback"}, "metadata": {"version": 2}}},
            "v2-fallback",
        ),
        (
            {"data": {"password": "  significant whitespace  "}},
            "  significant whitespace  ",
        ),
    ],
)
def test_accepts_real_kv_envelopes_and_legacy_value(vault_sdk, response, expected):
    _, client = vault_sdk
    client.read.return_value = response

    assert fetch_snapshot().db_password == expected


@pytest.mark.parametrize(
    "mount", ["secret/data/app", "/secret/data/app/", "///secret/data/app///"]
)
def test_exact_login_and_raw_prefix_path(vault_sdk, mount):
    factory, client = vault_sdk

    fetch_snapshot(mount)

    factory.assert_called_once_with(url="https://vault.invalid")
    client.auth.approle.login.assert_called_once_with(
        role_id="role-sentinel", secret_id="secret-id-sentinel", use_token=False
    )
    assert client.token == "token-sentinel"
    client.read.assert_called_once_with("secret/data/app/password")


@pytest.mark.parametrize("mount", ["", "/", "///"])
def test_empty_secret_prefix_fails_before_authentication(vault_sdk, mount):
    factory, _ = vault_sdk

    with pytest.raises(VaultSecretError, match="mount point"):
        fetch_snapshot(mount)

    factory.assert_not_called()


def test_snapshot_is_immutable_redacted_and_does_not_refetch(vault_sdk, caplog):
    _, client = vault_sdk
    caplog.set_level(logging.DEBUG)
    snapshot = fetch_snapshot()
    client.read.return_value["data"]["password"] = "changed"
    client.read.side_effect = AssertionError("must not fetch again")

    assert snapshot.db_password == "password-sentinel"
    assert snapshot.db_password == "password-sentinel"
    with pytest.raises(FrozenInstanceError):
        snapshot.db_password = "replacement"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(FrozenInstanceError):
        delattr(snapshot, "db_password")
    assert "password-sentinel" not in repr(snapshot)
    assert "password-sentinel" not in str(snapshot)
    client.read.assert_called_once()
    assert caplog.text == ""


def test_snapshot_does_not_keep_client_or_credentials_alive(monkeypatch):
    class ClientDouble(SimpleNamespace):
        pass

    class Credential(str):
        pass

    role = Credential("role-sentinel")
    secret = Credential("secret-id-sentinel")
    url = Credential("https://vault.invalid")
    token = Credential("token-sentinel")
    client = ClientDouble(
        auth=SimpleNamespace(
            approle=SimpleNamespace(
                login=Mock(return_value={"auth": {"client_token": token}})
            )
        ),
        read=Mock(return_value={"data": {"password": "password-sentinel"}}),
        token=None,
    )
    references = [weakref.ref(value) for value in (client, role, secret, url, token)]
    with monkeypatch.context() as patch:
        patch.setattr(
            "gonzo_pit_strategy.security.vault.hvac.Client",
            lambda client=client, **kwargs: client,
        )
        snapshot = Multipass.from_vault(
            url=url, role_id=role, secret_id=secret, mount_point="secret/app"
        )
    del client, role, secret, url, token
    gc.collect()

    assert snapshot.db_password == "password-sentinel"
    assert all(reference() is None for reference in references)


def assert_sanitized(error, caplog):
    rendered = "".join(traceback.format_exception(error))
    for sentinel in (
        "password-sentinel",
        "role-sentinel",
        "secret-id-sentinel",
        "token-sentinel",
        "https://vault.invalid",
        "underlying-sentinel",
    ):
        assert sentinel not in str(error)
        assert sentinel not in repr(error)
        assert sentinel not in rendered
        assert sentinel not in caplog.text
    assert error.__cause__ is None
    assert error.__suppress_context__


@pytest.mark.parametrize("phase", ["construction", "login", "read"])
@pytest.mark.parametrize(
    "failure",
    [
        hvac.exceptions.Unauthorized,
        hvac.exceptions.Forbidden,
        hvac.exceptions.InvalidPath,
        hvac.exceptions.InternalServerError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.InvalidURL,
    ],
)
def test_sdk_and_transport_failures_are_sanitized(vault_sdk, caplog, phase, failure):
    factory, client = vault_sdk
    caplog.set_level(logging.DEBUG)
    operation = {
        "construction": factory,
        "login": client.auth.approle.login,
        "read": client.read,
    }[phase]
    operation.side_effect = failure(
        "underlying-sentinel password-sentinel role-sentinel secret-id-sentinel "
        "token-sentinel https://vault.invalid"
    )
    expected = VaultSecretError if phase == "read" else VaultAuthenticationError

    with pytest.raises(expected) as caught:
        fetch_snapshot()

    assert isinstance(caught.value, VaultError)
    assert_sanitized(caught.value, caplog)
    if phase != "read":
        client.read.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        [],
        "token-sentinel",
        requests.Response(),
        {"auth": None},
        {"auth": []},
        {"auth": {}},
        {"auth": {"client_token": None}},
        {"auth": {"client_token": ""}},
        {"auth": {"client_token": False}},
        {"auth": {"client_token": 123}},
        {"auth": {"client_token": {"token-sentinel": "password-sentinel"}}},
    ],
)
def test_invalid_authentication_response_is_safe(vault_sdk, caplog, response):
    _, client = vault_sdk
    client.auth.approle.login.return_value = response

    with pytest.raises(VaultAuthenticationError, match="malformed") as caught:
        fetch_snapshot()

    assert_sanitized(caught.value, caplog)
    client.read.assert_not_called()
    assert client.token is None


@pytest.mark.parametrize(
    "response, message",
    [
        (None, "not found"),
        ({}, "malformed"),
        ([], "malformed"),
        ("password-sentinel", "malformed"),
        (requests.Response(), "malformed"),
        ({"data": None}, "malformed"),
        ({"data": []}, "malformed"),
        ({"data": "password-sentinel"}, "malformed"),
        ({"data": {}}, "missing"),
        ({"data": {"unrelated": "password-sentinel"}}, "missing"),
        ({"data": {"data": None, "metadata": {"version": 1}}}, "malformed"),
        ({"data": {"data": [], "metadata": {"version": 1}}}, "malformed"),
        ({"data": {"data": {}, "metadata": {"version": 1}}}, "missing"),
    ],
)
def test_missing_and_malformed_secret_responses_are_distinct(
    vault_sdk, caplog, response, message
):
    _, client = vault_sdk
    client.read.return_value = response

    with pytest.raises(VaultSecretError, match=message) as caught:
        fetch_snapshot()

    assert_sanitized(caught.value, caplog)


def test_nested_v1_data_is_not_mistaken_for_a_v2_password(vault_sdk):
    _, client = vault_sdk
    client.read.return_value = {"data": {"data": {"password": "nested-only"}}}

    with pytest.raises(VaultSecretError):
        fetch_snapshot()


@pytest.mark.parametrize(
    "metadata",
    [None, [], "private-metadata", {}, {"version": "1"}, {"version": 0}, {"version": False}],
)
def test_v2_metadata_must_identify_a_secret_version(vault_sdk, metadata):
    _, client = vault_sdk
    client.read.return_value = {
        "data": {"data": {"password": "password-sentinel"}, "metadata": metadata}
    }

    with pytest.raises(VaultSecretError, match="malformed") as caught:
        fetch_snapshot()

    assert "private-metadata" not in str(caught.value)


@pytest.mark.parametrize(
    "value",
    [None, "", False, True, 0, 42, 3.14, [], {"password-sentinel": "token-sentinel"}],
)
@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("key", ["password", "value"])
def test_invalid_password_is_not_coerced_or_replaced(
    vault_sdk, caplog, value, version, key
):
    _, client = vault_sdk
    data = {key: value}
    if key == "password":
        data["value"] = "password-sentinel"
    client.read.return_value = {
        "data": data if version == 1 else {"data": data, "metadata": {"version": 1}}
    }

    with pytest.raises(VaultSecretError, match="nonempty string") as caught:
        fetch_snapshot()

    assert_sanitized(caught.value, caplog)


@pytest.mark.parametrize("phase", ["login", "read"])
def test_json_decoding_failure_is_sanitized(vault_sdk, caplog, phase):
    _, client = vault_sdk
    operation = client.auth.approle.login if phase == "login" else client.read
    operation.side_effect = requests.exceptions.JSONDecodeError(
        "underlying-sentinel", "password-sentinel", 0
    )
    expected = VaultAuthenticationError if phase == "login" else VaultSecretError

    with pytest.raises(expected) as caught:
        fetch_snapshot()

    assert_sanitized(caught.value, caplog)


def test_programming_errors_are_not_swallowed(vault_sdk):
    _, client = vault_sdk
    client.read.side_effect = RuntimeError("programming error")

    with pytest.raises(RuntimeError, match="programming error"):
        fetch_snapshot()
