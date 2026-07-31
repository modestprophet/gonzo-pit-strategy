import numpy as np
import pandas as pd
import pytest

from gonzo_pit_strategy.inference.predictor import ModelPredictor
from gonzo_pit_strategy.training.artifact import ArtifactManifest, ArtifactStore

from conftest import FEATURE_NAMES


@pytest.fixture
def store_with_artifact(tmp_path, tiny_model):
    store = ArtifactStore(tmp_path)
    store.save(
        tiny_model,
        ArtifactManifest(
            model_name="f1_pit_strategy_model",
            model_version="v1",
            architecture="dense",
            feature_names=FEATURE_NAMES,
            target_column="finish_position",
            framework_version="test",
        ),
    )
    return store


def test_rehydrates_without_db(store_with_artifact):
    predictor = ModelPredictor("v1", store_with_artifact)
    assert predictor.feature_columns == FEATURE_NAMES
    assert predictor.target_column == "finish_position"


def test_predict_reorders_columns(store_with_artifact):
    predictor = ModelPredictor("v1", store_with_artifact)
    df = pd.DataFrame(
        np.random.default_rng(2).random((5, len(FEATURE_NAMES))),
        columns=FEATURE_NAMES,
    )
    shuffled = df[list(reversed(FEATURE_NAMES))].copy()
    shuffled["extra_column"] = 1.0

    np.testing.assert_allclose(predictor.predict(df), predictor.predict(shuffled))


def test_predict_missing_column_raises(store_with_artifact):
    predictor = ModelPredictor("v1", store_with_artifact)
    df = pd.DataFrame({FEATURE_NAMES[0]: [0.1]})
    with pytest.raises(ValueError, match="not found"):
        predictor.predict(df)


def test_predict_accepts_raw_dataset_dtypes(store_with_artifact, raw_dataset):
    """No train/serve skew: a raw dbt row must predict without manual coercion.

    `prep_training_dataset` yields boolean one-hot columns and `object` dtype
    for all-NULL numerics. Training coerces both via prepare_features; if
    inference does not, Keras raises `ValueError: Invalid dtype: object`.
    """
    predictor = ModelPredictor("v1", store_with_artifact)

    # Mirror what Postgres hands back: bool OHE plus an all-NULL object column.
    raw = raw_dataset.copy()
    assert raw[["circuit_a", "team_b"]].dtypes.map(str).eq("bool").all()
    raw["lap_time_scaled"] = pd.Series([None] * len(raw), dtype="object")

    preds = predictor.predict(raw)

    assert preds.shape == (len(raw), 1)
    assert np.isfinite(preds).all()
