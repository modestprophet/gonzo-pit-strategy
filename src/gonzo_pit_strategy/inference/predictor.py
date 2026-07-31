"""
Model inference for F1 pit strategy prediction.

Rehydrates models from self-describing artifact directories (ADR 0002):
the Artifact Manifest supplies the feature-ordering contract, so no
database connection is required for inference.
"""

from typing import Optional, Union

import numpy as np
import pandas as pd

from gonzo_pit_strategy.config.config import PathsConfig
from gonzo_pit_strategy.training.artifact import ArtifactStore
from gonzo_pit_strategy.training.data import prepare_features
import logging

logger = logging.getLogger(__name__)


class ModelPredictor:
    """Makes predictions with a trained model rehydrated from its Artifact."""

    def __init__(self, model_version: str, store: ArtifactStore):
        self.model_version = model_version
        self.model, self.manifest = store.load(model_version)
        self.feature_columns = self.manifest.feature_names
        self.target_column = self.manifest.target_column

    def predict(self, data: Union[pd.DataFrame, np.ndarray]) -> np.ndarray:
        """Predict on a DataFrame (columns reordered to the training contract
        and encoded exactly as in training) or a numpy array (assumed already
        in training feature order and numeric)."""
        if isinstance(data, pd.DataFrame):
            missing_columns = [
                col for col in self.feature_columns if col not in data.columns
            ]
            if missing_columns:
                raise ValueError(
                    f"Feature columns not found in data: {missing_columns}"
                )
            # Same encoding as training — otherwise the model sees booleans and
            # object dtypes where it was trained on integers and floats.
            features = prepare_features(data[self.feature_columns]).values
        else:
            features = data

        return self.model.predict(features)


def load_predictor(
    model_version: str, paths: Optional[PathsConfig] = None
) -> ModelPredictor:
    """Load a predictor for a trained model from the configured artifact root."""
    paths = paths or PathsConfig()
    return ModelPredictor(model_version, ArtifactStore(paths.artifacts_root))
