import numpy as np
import pandas as pd
import pytest

N_FEATURES = 4
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

    def __init__(self, df):
        self._df = df

    def fetch_raw_data(self):
        return self._df.copy()
