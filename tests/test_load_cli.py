"""Provisioning validation through the real gonzo-load entry point."""

import logging
import os
import subprocess
import sys

import psycopg2
import pytest

from gonzo_pit_strategy.cli.load import main

ADMIN_ARGS = [
    "--db-admin-username", "cli-admin-user",
    "--db-admin-password", "cli-admin-secret",
]
APP_ARGS = [
    "--app-username", "cli-app-user",
    "--app-password", "cli-app-secret",
]
ALL_ARGS = ADMIN_ARGS + APP_ARGS
ADMIN_MISSING = "Admin Role username, Admin Role password"
APP_MISSING = "App Role username, App Role password"
ALL_MISSING = f"{ADMIN_MISSING}, {APP_MISSING}"


@pytest.fixture(autouse=True)
def isolated_cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in os.environ:
        if name == "LOGGING" or name.startswith("LOGGING__"):
            monkeypatch.delenv(name)
    for name in ("ADDR", "ROLE_ID", "SECRET_ID"):
        monkeypatch.setenv(f"VAULT__{name}", "")
    monkeypatch.setenv("LOGGING__LEVEL", "INFO")
    monkeypatch.setenv("LOGGING__FORMAT", "%(message)s")

    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    # Detach first: setup_logging(force=True) would close the saved handlers.
    for handler in handlers:
        root.removeHandler(handler)
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def subprocess_forbidden(*args, **kwargs):
        pytest.fail("Provisioning invoked subprocess.run before validation finished")

    def connection_forbidden(*args, **kwargs):
        pytest.fail("Provisioning invoked psycopg2.connect before validation finished")

    monkeypatch.setattr(subprocess, "run", subprocess_forbidden)
    monkeypatch.setattr(psycopg2, "connect", connection_forbidden)


def failed_cli(monkeypatch, capsys, args):
    monkeypatch.setattr(sys, "argv", ["gonzo-load", *args])
    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Provisioning complete" not in captured.err
    assert "successful" not in captured.err
    assert "Rows loaded" not in captured.err
    for credential in ALL_ARGS[1::2]:
        assert credential not in captured.err
    return captured.err


@pytest.mark.parametrize(
    "steps",
    ["unknown", "init,unknown", "unknown,load", "all,unknown", "unknown,all"],
)
def test_unknown_phase_is_rejected_even_alongside_all(monkeypatch, capsys, steps):
    error = failed_cli(monkeypatch, capsys, ["--steps", steps, *ALL_ARGS])

    assert "Unknown step: 'unknown'" in error
    assert "Missing required credentials" not in error


@pytest.mark.parametrize("steps", ["", "   ", ", ,"])
def test_empty_selection_is_rejected(monkeypatch, capsys, steps):
    error = failed_cli(monkeypatch, capsys, ["--steps", steps, *ALL_ARGS])

    assert error == "No steps requested\n"


@pytest.mark.parametrize(
    ("steps", "missing"),
    [
        (None, ALL_MISSING),
        ("all", ALL_MISSING),
        ("init", ALL_MISSING),
        ("migrate", ADMIN_MISSING),
        ("load", APP_MISSING),
        ("load,migrate", ALL_MISSING),
        ("load,init", ALL_MISSING),
        (" ALL , load ", ALL_MISSING),
    ],
)
def test_missing_credentials_name_only_required_role_fields(
    monkeypatch, capsys, tmp_path, steps, missing
):
    args = ["--data-directory", str(tmp_path)]
    if steps is not None:
        args.extend(["--steps", steps])
    error = failed_cli(monkeypatch, capsys, args)

    assert error == f"Missing required credentials: {missing}\n"


@pytest.mark.parametrize(
    ("flag", "missing"),
    [
        ("--db-admin-username", "Admin Role username"),
        ("--db-admin-password", "Admin Role password"),
        ("--app-username", "App Role username"),
        ("--app-password", "App Role password"),
    ],
)
@pytest.mark.parametrize("empty_value", [False, True], ids=["omitted", "empty"])
def test_init_reports_only_the_missing_field_without_exposing_credentials(
    monkeypatch, capsys, flag, missing, empty_value
):
    args = ["--steps", "init"]
    for supplied_flag, value in zip(ALL_ARGS[::2], ALL_ARGS[1::2]):
        if supplied_flag != flag:
            args.extend([supplied_flag, value])
        elif empty_value:
            args.extend([supplied_flag, ""])
    error = failed_cli(monkeypatch, capsys, args)

    assert error == f"Missing required credentials: {missing}\n"


@pytest.mark.parametrize(
    ("steps", "credentials", "missing"),
    [
        ("init", ADMIN_ARGS, APP_MISSING),
        ("init", APP_ARGS, ADMIN_MISSING),
        ("migrate", APP_ARGS, ADMIN_MISSING),
        ("load", ADMIN_ARGS, APP_MISSING),
        ("migrate,load", ADMIN_ARGS, APP_MISSING),
        ("load,migrate", ADMIN_ARGS, APP_MISSING),
        ("all", ADMIN_ARGS, APP_MISSING),
        ("all", APP_ARGS, ADMIN_MISSING),
    ],
)
def test_entire_requested_operation_is_validated_before_effects(
    monkeypatch, capsys, tmp_path, steps, credentials, missing
):
    error = failed_cli(
        monkeypatch,
        capsys,
        ["--steps", steps, "--data-directory", str(tmp_path), *credentials],
    )

    assert error == f"Missing required credentials: {missing}\n"


@pytest.mark.parametrize("steps", ["load", " LOAD ", "load,load"])
def test_load_needs_only_app_credentials_and_reaches_its_file_validation(
    monkeypatch, capsys, tmp_path, steps
):
    error = failed_cli(
        monkeypatch,
        capsys,
        ["--steps", steps, "--data-directory", str(tmp_path), *APP_ARGS],
    )

    assert f"Required file not found: {tmp_path / 'formula_one_baseteam.csv'}" in error
    assert "Missing required" not in error
    assert "Admin Role" not in error


def test_load_resolves_only_logging(monkeypatch, capsys):
    import hvac

    def vault_forbidden(*args, **kwargs):
        pytest.fail("Provisioning must not initialize Vault")

    monkeypatch.setattr(hvac, "Client", vault_forbidden)
    monkeypatch.setenv("DB__PORT", "invalid")
    monkeypatch.setenv("TRAINING", "not-json")
    monkeypatch.setenv("PATHS", "not-json")
    monkeypatch.setenv("VAULT__ADDR", "http://vault.invalid")
    monkeypatch.setenv("VAULT__ROLE_ID", "test-role")
    monkeypatch.setenv("VAULT__SECRET_ID", "test-secret")
    monkeypatch.setenv("LOGGING__LEVEL", "WARNING")
    monkeypatch.setenv("LOGGING__FORMAT", "load: %(message)s")

    error = failed_cli(monkeypatch, capsys, ["--steps", "unknown"])

    assert error == "load: Unknown step: 'unknown'. Valid steps: init, migrate, load\n"
    assert logging.getLogger().level == logging.WARNING


def test_help_needs_no_settings(monkeypatch, capsys):
    monkeypatch.setenv("LOGGING", "not-json")
    monkeypatch.setenv("DB__PORT", "invalid")
    monkeypatch.setattr(sys, "argv", ["gonzo-load", "--help"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0
    assert "--steps" in capsys.readouterr().out


def test_load_preserves_logging_source_precedence(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("LOGGING__LEVEL")
    monkeypatch.delenv("LOGGING__FORMAT")
    (tmp_path / ".env").write_text(
        'LOGGING={"level":"WARNING","format":"dotenv: %(message)s"}\n'
        "DB=not-json\nVAULT=not-json\nTRAINING=not-json\nPATHS=not-json\n"
    )

    error = failed_cli(monkeypatch, capsys, ["--steps", ""])
    assert error == "dotenv: No steps requested\n"
    assert logging.getLogger().level == logging.WARNING

    monkeypatch.setenv("LOGGING", '{"level":"INFO"}')
    error = failed_cli(monkeypatch, capsys, ["--steps", ""])
    assert error == "dotenv: No steps requested\n"
    assert logging.getLogger().level == logging.INFO

    monkeypatch.setenv("LOGGING__FORMAT", "env: %(message)s")
    error = failed_cli(monkeypatch, capsys, ["--steps", ""])
    assert error == "env: No steps requested\n"
