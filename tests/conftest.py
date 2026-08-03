import os

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

N_FEATURES = 4

# Tables the Run Ledger writes, ordered so TRUNCATE ... CASCADE is unambiguous.
_LEDGER_TABLES = (
    "f1db.training_metrics",
    "f1db.training_runs",
    "f1db.model_metadata",
    "f1db.dataset_versions",
)
FEATURE_NAMES = ["circuit_a", "team_b", "lap_time_scaled", "tyre_age_scaled"]


@pytest.fixture
def tiny_model():
    # Imported inside the fixture so tests that need no model (config, data
    # splitting) run without pulling in TensorFlow.
    keras = pytest.importorskip("keras")

    model = keras.Sequential(
        [
            keras.layers.Input(shape=(N_FEATURES,)),
            keras.layers.Dense(2, activation="relu"),
            keras.layers.Dense(1),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    return model


@pytest.fixture
def raw_dataset():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.random((50, N_FEATURES)), columns=FEATURE_NAMES)
    df["circuit_a"] = df["circuit_a"] > 0.5
    df["team_b"] = df["team_b"] > 0.5
    df["finish_position"] = rng.integers(1, 20, 50)
    df["race_id"] = np.arange(50)
    df.attrs["source_query"] = "SELECT * FROM fixture"
    return df


class StubDataSource:
    """Satisfies the TrainingDataSource Protocol with a fixture RawDataset."""

    def __init__(self, df, dataset_name="fixture_dataset"):
        self._df = df
        self._dataset_name = dataset_name

    @property
    def dataset_name(self):
        return self._dataset_name

    def fetch_raw_data(self):
        return self._df.copy()


@pytest.fixture
def ledger():
    from fakes import InMemoryRunLedger

    return InMemoryRunLedger()


# ---------------------------------------------------------------------------
# Scratch Postgres, for the Run Ledger contract suite
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_pool():
    """A ConnectionPool against the scratch database, or skip.

    Skips rather than fails when no database is reachable: the core suite needs
    neither a database nor a GPU, and that stays true. When one *is* reachable
    the contract tests run by default, so adapter drift is caught without
    anyone having to remember a flag.
    """
    url = os.environ.get("DEV_POSTGRES_URL")
    if not url:
        pytest.skip("DEV_POSTGRES_URL not set")

    from gonzo_pit_strategy.config.config import DatabaseConfig
    from gonzo_pit_strategy.db.base import Base
    from gonzo_pit_strategy.db.connection_pool import ConnectionPool

    parsed = make_url(url)
    pool = ConnectionPool(
        DatabaseConfig(
            host=parsed.host,
            port=parsed.port or 5432,
            name=parsed.database,
            user=parsed.username,
            password=parsed.password,
        )
    )

    try:
        with pool.engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS f1db"))
    except Exception as exc:  # unreachable, wrong credentials, no CREATE grant
        pool.dispose()
        pytest.skip(f"scratch Postgres unusable: {exc}")

    # The ORM carries the UNIQUE and CHECK constraints, so creating from
    # metadata gives the real constraint surface — which is the whole reason
    # for testing an adapter against Postgres rather than against a fake.
    Base.metadata.create_all(pool.engine)
    yield pool
    pool.dispose()


@pytest.fixture
def clean_postgres(postgres_pool):
    """Empty the ledger tables before each test that touches them."""
    statement = text(
        f"TRUNCATE {', '.join(_LEDGER_TABLES)} RESTART IDENTITY CASCADE"
    )
    with postgres_pool.engine.begin() as conn:
        conn.execute(statement)
    return postgres_pool
