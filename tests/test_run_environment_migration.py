import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import text

from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.db.provisioning import (
    DatabaseTarget,
    Role,
    goose_command,
    quote_identifier,
)
from gonzo_pit_strategy.db.run_ledger import PostgresRunLedger
from gonzo_pit_strategy.training.artifact import ArtifactManifest
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import DatasetProvenance
from probes import PostgresProbe


@pytest.fixture
def migration_database(postgres_pool):
    config = postgres_pool.db_config.model_copy(
        update={"name": f"gonzo_run_env_{uuid4().hex}"}
    )
    target = DatabaseTarget(
        host=config.host,
        port=config.port,
        name=config.name,
        schema="f1db",
    )
    role = Role(config.user, config.password)
    with postgres_pool.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.execute(text(f"CREATE DATABASE {quote_identifier(target.name)}"))
        try:
            pool = ConnectionPool(config)
            try:
                with pool.engine.begin() as connection:
                    connection.execute(text("CREATE SCHEMA f1db"))
                yield pool, target, role
            finally:
                pool.dispose()
        finally:
            admin.execute(text(f"DROP DATABASE {quote_identifier(target.name)} WITH (FORCE)"))


def _migrate(database, direction="up", *args):
    _, target, role = database
    result = subprocess.run(
        [*goose_command(target, role, direction=direction), *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _environment_column(pool):
    with pool.engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT data_type, character_maximum_length, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = 'f1db' AND table_name = 'training_runs' "
                "AND column_name = 'environment_id'"
            )
        ).one_or_none()


def _runs(pool):
    with pool.engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT to_jsonb(r) - 'environment_id' "
                "FROM f1db.training_runs r ORDER BY run_id"
            )
        ).scalars().all()


def test_upgrade_preserves_run_and_down_restores_empty_environment(migration_database):
    pool, _, _ = migration_database
    _migrate(migration_database, "up-to", "5")
    with pool.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO f1db.training_runs "
                "(status, epochs_completed, early_stopping, environment_id) "
                "VALUES ('FAILED', 2, TRUE, 'historical-environment')"
            )
        )
    original = _runs(pool)

    _migrate(migration_database)

    assert _environment_column(pool) is None
    assert _runs(pool) == original

    _migrate(migration_database, "down")

    assert _environment_column(pool) == ("character varying", 100, "YES", None)
    assert _runs(pool) == original
    with pool.engine.connect() as connection:
        assert connection.execute(
            text("SELECT environment_id FROM f1db.training_runs")
        ).one() == (None,)

    _migrate(migration_database)

    assert _environment_column(pool) is None
    assert _runs(pool) == original


def test_fresh_migrations_support_postgres_ledger(migration_database, tmp_path):
    pool, _, _ = migration_database
    _migrate(migration_database)
    assert _environment_column(pool) is None

    ledger = PostgresRunLedger(pool)
    probe = PostgresProbe(pool)
    config = TrainingConfig(target_column="finish_position", epochs=1)
    provenance = DatasetProvenance(
        name="migration_dataset",
        fingerprint="abcdef0123456789fedcba9876543210",
        record_count=50,
        feature_count=1,
    )
    manifest = ArtifactManifest(
        model_name="migration_model",
        model_version="migration_v1",
        architecture="dense",
        feature_names=["tyre_age"],
        target_column=config.target_column,
        framework_version="3.0.0",
        dataset_name=provenance.name,
        dataset_fingerprint=provenance.fingerprint,
        epochs_completed=1,
        test_metrics={"loss": 0.3},
    )

    with ledger.run(config) as run:
        run_id = run.run_id
        assert run_id is not None
        assert probe.status(run_id) == "RUNNING"
        run.record_epoch(0, {"loss": 0.5, "val_loss": 0.7})
        run.complete(manifest, tmp_path, provenance, epochs_completed=1)
        assert run.model_id is not None

    assert probe.status(run_id) == "COMPLETED"
    assert probe.model_id(run_id) == run.model_id
    assert {(m.name, m.split): m.value for m in probe.metrics(run_id)} == {
        ("loss", "TRAIN"): 0.5,
        ("loss", "VALIDATION"): 0.7,
        ("loss", "TEST"): 0.3,
    }
    assert probe.dataset_versions() == [(provenance.name, provenance.fingerprint[:16])]
