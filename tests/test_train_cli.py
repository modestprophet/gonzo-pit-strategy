import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import text

from gonzo_pit_strategy.db.base import Base
from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.db.models.dataset_versions import DatasetVersion
from gonzo_pit_strategy.db.models.model_metadata import ModelMetadata
from gonzo_pit_strategy.db.models.training_metrics import TrainingMetric
from gonzo_pit_strategy.db.models.training_runs import TrainingRun


@pytest.fixture
def train_cli(tmp_path):
    env = {
        name: value for name, value in os.environ.items()
        if not name.startswith(("DB__", "VAULT__", "TRAINING__", "PATHS__", "LOGGING__"))
    }
    env.update(
        DB__HOST="127.0.0.1",
        DB__PORT="1",
        VAULT__ADDR="",
        VAULT__ROLE_ID="",
        VAULT__SECRET_ID="",
        PATHS__ARTIFACTS_ROOT=str(tmp_path / "artifacts"),
        PATHS__TENSORBOARD_DIR=str(tmp_path / "tb"),
        LOGGING__FORMAT="%(message)s",
        TF_NUM_INTEROP_THREADS="1",
        TF_NUM_INTRAOP_THREADS="1",
    )
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"epochs": 1, "model": {"hidden_layers": [2]}}))

    def invoke(grid, *, settings=None, database=None):
        if settings is not None:
            base.write_text(settings)
        args = [sys.executable, "-m", "gonzo_pit_strategy.cli.train", "--config", str(base)]
        if grid is not None:
            path = tmp_path / "grid.json"
            path.write_text(grid)
            args.extend(["--grid-search", str(path)])
        command_env = env | (database or {})
        return subprocess.run(
            args, cwd=tmp_path, env=command_env, capture_output=True, text=True,
            timeout=60, check=False,
        )

    return invoke


@pytest.mark.parametrize(
    ("grid", "message"),
    [
        ('{"learning_rate": [0.001], "learning_rate": [0.0003]}', "Duplicate JSON field"),
        ('{"model": {}, "model": {"dropout_rate": [0.1]}}', "Duplicate JSON field"),
        ('{"learning_rate": [}', "Invalid configuration"),
    ],
)
def test_invalid_grid_file_fails_cleanly_before_execution(train_cli, tmp_path, grid, message):
    result = train_cli(grid)

    assert result.returncode == 1
    assert message in result.stderr
    assert "Traceback" not in result.stderr
    assert "Sweep results" not in result.stdout
    assert not (tmp_path / "artifacts").exists()
    assert not (tmp_path / "tb").exists()


def test_cli_counts_all_failed_attempts_without_training_run_rows(train_cli):
    result = train_cli('{"epochs": [1, 2]}')

    assert result.returncode == 1
    assert "1/2 | FAILED" in result.stdout
    assert "2/2 | FAILED" in result.stdout
    assert "Requested: 2 | Succeeded: 0 | Failed: 2" in result.stdout


def test_invalid_later_combination_starts_no_experiments(train_cli):
    result = train_cli('{"test_size": [0.8], "validation_size": [0.1, 0.3]}')

    assert result.returncode == 1
    assert "Combination 2" in result.stderr
    assert "test_size + validation_size must be less than 1" in result.stderr
    assert "Fetching RawDataset" not in result.stderr
    assert "Traceback" not in result.stderr
    assert "Sweep results" not in result.stdout


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ('{"epoch": 2}', "Extra inputs are not permitted"),
        ('{"epochs": 1, "epochs": 2}', "Duplicate JSON field"),
    ],
)
def test_single_experiment_rejects_invalid_config_files(train_cli, settings, message):
    result = train_cli(None, settings=settings)

    assert result.returncode == 1
    assert message in result.stderr
    assert "Fetching RawDataset" not in result.stderr
    assert "Traceback" not in result.stderr


@pytest.fixture(scope="module")
def cli_database(postgres_pool):
    name = f"gonzo_sweep_{uuid4().hex}"
    with postgres_pool.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.execute(text(f'CREATE DATABASE "{name}"'))
        pool = ConnectionPool(postgres_pool.db_config.model_copy(update={"name": name}))
        try:
            with pool.engine.begin() as conn:
                conn.execute(text("CREATE SCHEMA f1db"))
                conn.execute(text("CREATE SCHEMA f1db_ml_prep"))
            Base.metadata.create_all(
                pool.engine,
                tables=[
                    model.__table__
                    for model in (DatasetVersion, ModelMetadata, TrainingRun, TrainingMetric)
                ],
            )
            yield pool
        finally:
            pool.dispose()
            admin.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))


@pytest.fixture
def training_database(cli_database, raw_dataset):
    raw_dataset.to_sql(
        "prep_training_dataset", cli_database.engine,
        schema="f1db_ml_prep", if_exists="replace", index=False,
    )
    config = cli_database.db_config
    return {
        "DB__HOST": config.host,
        "DB__PORT": str(config.port),
        "DB__NAME": config.name,
        "DB__USER": config.user,
        "DB__PASSWORD": config.password,
    }


@pytest.mark.parametrize(
    ("targets", "exit_code", "succeeded", "failed"),
    [
        (["finish_position", "finish_position"], 0, 2, 0),
        (["finish_position", "missing", "finish_position"], 1, 2, 1),
        (["missing", "absent"], 1, 0, 2),
    ],
)
def test_cli_reports_every_outcome_and_exits_after_all_experiments(
    train_cli, training_database, targets, exit_code, succeeded, failed,
):
    result = train_cli(json.dumps({"target_column": targets}), database=training_database)

    assert result.returncode == exit_code, result.stderr
    assert "Sweep results" in result.stdout
    assert (
        f"Requested: {len(targets)} | Succeeded: {succeeded} | Failed: {failed}"
        in result.stdout
    )
    for index, target in enumerate(targets, start=1):
        status = "COMPLETED" if target == "finish_position" else "FAILED"
        assert f"{index}/{len(targets)} | {status}" in result.stdout
        assert f'"target_column": "{target}"' in result.stdout
        if status == "FAILED":
            assert f"Target column '{target}' not found" in result.stdout
