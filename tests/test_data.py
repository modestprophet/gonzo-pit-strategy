from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import fingerprint_dataset, load_training_data

from conftest import StubDataSource


def test_fingerprint_deterministic(raw_dataset):
    assert fingerprint_dataset(raw_dataset, "q") == fingerprint_dataset(
        raw_dataset.copy(), "q"
    )


def test_fingerprint_changes_on_data_or_query(raw_dataset):
    base = fingerprint_dataset(raw_dataset, "q")
    assert fingerprint_dataset(raw_dataset, "other query") != base

    mutated = raw_dataset.copy()
    mutated.iloc[0, 2] = 999.0
    assert fingerprint_dataset(mutated, "q") != base

    reordered = raw_dataset[list(raw_dataset.columns[::-1])]
    assert fingerprint_dataset(reordered, "q") != base


def test_load_training_data_from_stub(raw_dataset):
    config = TrainingConfig(
        target_column="finish_position", exclude_columns=["race_id"]
    )
    data = load_training_data(config, StubDataSource(raw_dataset))

    assert data.feature_names == [
        c for c in raw_dataset.columns if c not in ("finish_position", "race_id")
    ]
    assert data.feature_count == len(data.feature_names)
    assert data.record_count == len(raw_dataset)
    assert data.dataset_fingerprint
    total = len(data.X_train) + len(data.X_val) + len(data.X_test)
    assert total == len(raw_dataset)
    assert data.X_train.shape[1] == data.feature_count
