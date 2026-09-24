import subprocess
from dataclasses import replace

import psycopg2
import pytest

from gonzo_pit_strategy.db.provisioning import (
    DatabaseTarget,
    Provisioner,
    ProvisioningError,
    Role,
    Step,
)

ADMIN = Role("admin", "admin-secret")
APP = Role("app", "app-secret")


@pytest.fixture(autouse=True)
def forbid_external_effects(monkeypatch):
    def unexpected_effect(*args, **kwargs):
        pytest.fail("Preflight must reject this request before external effects")

    monkeypatch.setattr(subprocess, "run", unexpected_effect)
    monkeypatch.setattr(psycopg2, "connect", unexpected_effect)


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        ([], "No steps requested"),
        ([Step.INIT, "unknown"], "Unknown step"),
        (["unknown", Step.LOAD], "Unknown step"),
        ([None], "Unknown step"),
        (["all"], "Unknown step"),
    ],
)
def test_provision_rejects_invalid_selection_before_effects(tmp_path, steps, message):
    provisioner = Provisioner(DatabaseTarget(), admin=ADMIN, app=APP)

    with pytest.raises(ProvisioningError, match=message):
        provisioner.provision(iter(steps), data_dir=tmp_path)


def test_provision_orders_direct_selection_before_starting_a_phase(tmp_path):
    provisioner = Provisioner(
        DatabaseTarget(), admin=ADMIN, app=APP, init_sql_path=tmp_path / "missing.sql"
    )

    with pytest.raises(ProvisioningError, match="SQL init file not found"):
        provisioner.provision(
            iter([Step.LOAD, Step.MIGRATE, Step.INIT]), data_dir=tmp_path
        )


def test_provision_runs_each_selected_phase_once(monkeypatch):
    effects = []

    def completed_command(command, **kwargs):
        effects.append(command[0])
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", completed_command)
    provisioner = Provisioner(DatabaseTarget(), admin=ADMIN, app=APP)
    report = provisioner.provision(
        iter([Step.MIGRATE, Step.INIT, Step.MIGRATE, Step.INIT])
    )

    assert effects == ["psql", "goose"]
    assert report.steps_completed == [Step.INIT, Step.MIGRATE]
    assert report.load is None


@pytest.mark.parametrize(
    ("steps", "role_name"),
    [
        ([Step.INIT], "admin"),
        ([Step.INIT], "app"),
        ([Step.MIGRATE], "admin"),
        ([Step.LOAD], "app"),
        ([Step.MIGRATE, Step.LOAD], "app"),
        ([Step.LOAD, Step.MIGRATE], "admin"),
    ],
)
@pytest.mark.parametrize("field", ["username", "password"])
def test_provision_checks_all_required_credentials_before_effects(
    tmp_path, steps, role_name, field
):
    roles = {"admin": ADMIN, "app": APP}
    roles[role_name] = replace(roles[role_name], **{field: ""})
    provisioner = Provisioner(DatabaseTarget(), admin=roles["admin"], app=roles["app"])

    with pytest.raises(ProvisioningError, match=f"{role_name.title()} Role {field}") as exc:
        provisioner.provision(iter(steps), data_dir=tmp_path)

    assert ADMIN.password not in str(exc.value)
    assert APP.password not in str(exc.value)


def test_provision_reports_all_missing_credentials(tmp_path):
    provisioner = Provisioner(DatabaseTarget(), admin=Role("", ""), app=Role("", ""))

    with pytest.raises(ProvisioningError) as exc:
        provisioner.provision([Step.LOAD, Step.INIT], data_dir=tmp_path)

    assert str(exc.value) == (
        "Missing required credentials: Admin Role username, Admin Role password, "
        "App Role username, App Role password"
    )


@pytest.mark.parametrize(
    ("method", "role_name"),
    [
        ("initialize", "admin"),
        ("initialize", "app"),
        ("migrate", "admin"),
        ("load", "app"),
    ],
)
@pytest.mark.parametrize("field", ["username", "password"])
def test_standalone_phase_checks_its_required_credentials(
    tmp_path, method, role_name, field
):
    roles = {"admin": ADMIN, "app": APP}
    roles[role_name] = replace(roles[role_name], **{field: ""})
    provisioner = Provisioner(DatabaseTarget(), admin=roles["admin"], app=roles["app"])
    operation = getattr(provisioner, method)

    with pytest.raises(ProvisioningError, match=f"{role_name.title()} Role {field}"):
        if method == "load":
            operation(tmp_path)
        else:
            operation()


@pytest.mark.parametrize("standalone", [False, True])
@pytest.mark.parametrize("step", [Step.MIGRATE, Step.LOAD])
def test_phase_ignores_unused_credentials(tmp_path, standalone, step):
    provisioner = Provisioner(
        DatabaseTarget(),
        admin=ADMIN if step is Step.MIGRATE else Role("", ""),
        app=APP if step is Step.LOAD else Role("", ""),
        migrations_dir=tmp_path / "missing-migrations",
    )
    message = (
        "Migrations directory not found"
        if step is Step.MIGRATE else "Required file not found"
    )

    with pytest.raises(ProvisioningError, match=message):
        if not standalone:
            provisioner.provision([step], data_dir=tmp_path)
        elif step is Step.MIGRATE:
            provisioner.migrate()
        else:
            provisioner.load(tmp_path)


def test_file_checks_remain_local_to_the_executing_phase(tmp_path):
    provisioner = Provisioner(
        DatabaseTarget(),
        admin=ADMIN,
        app=APP,
        migrations_dir=tmp_path / "missing-migrations",
    )

    with pytest.raises(ProvisioningError, match="Migrations directory not found"):
        provisioner.provision([Step.LOAD, Step.MIGRATE], data_dir=tmp_path)


def test_missing_load_directory_is_rejected_before_earlier_phases(tmp_path):
    provisioner = Provisioner(
        DatabaseTarget(), admin=ADMIN, app=APP, init_sql_path=tmp_path / "missing.sql"
    )

    with pytest.raises(ProvisioningError, match="requires a data directory"):
        provisioner.provision([Step.INIT, Step.LOAD])
