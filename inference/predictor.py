"""
Model inference functionality for F1 pit strategy prediction.

This module provides classes and functions for loading trained models and making predictions.
"""
import os
import json
from typing import Dict, Any, Optional, List, Tuple, Union
import numpy as np
import pandas as pd

from models.model import get_model
from training.data_pipeline import DataPipeline
from db.repositories.model_repository import ModelRepository
from gonzo_pit_strategy.log.logger import get_logger

logger = get_logger(__name__)


class ModelPredictor:
    """Class for making predictions with trained models."""

    def __init__(self, model_version: str, model_type: str = 'dense', 
                 config_path: str = "../../config/model.json"):
        """Initialize the predictor with a trained model.

        Args:
            model_version: Version string of the model to load
            model_type: Type of model ('dense', 'bilstm', etc.)
            config_path: Path to model configuration
        """
        self.model_version = model_version
        self.model_type = model_type
        self.config_path = config_path

        # Initialize model and repository
        self.model = get_model(model_type, config_path=config_path)
        model_path = self.model.model_path
        self.model_repo = ModelRepository(model_path)

        # Load model using repository
        model_keras, self.metadata = self.model_repo.load_model(model_version, self.model.model_name)
        self.model.model = model_keras  # Set the keras model in our model wrapper
        logger.info(f"Loaded model from repository: {model_version}")

        # Extract feature columns and target column from metadata
        self.feature_columns = self.metadata.get('feature_columns', [])
        self.target_column = self.metadata.get('target_column', None)

        # Check for training metadata (for additional information)
        model_dir = os.path.join(model_path, model_version)
        training_metadata_path = os.path.join(model_dir, "training_metadata.json")
        if os.path.exists(training_metadata_path):
            with open(training_metadata_path, 'r') as f:
                self.training_metadata = json.load(f)
            # Get data version from training metadata
            self.data_version = self.training_metadata.get('data_version', None)
        else:
            # Try to get data version from model metadata
            self.training_metadata = {}
            self.data_version = self.metadata.get('data_version', None)

        # Initialize data pipeline
        self.data_pipeline = None

    def _initialize_pipeline(self, pipeline_config_path: Optional[str] = None):
        """Initialize the data pipeline.

        Args:
            pipeline_config_path: Path to pipeline configuration
        """
        if self.data_pipeline is None:
            if pipeline_config_path is None:
                pipeline_config_path = self.training_metadata.get(
                    'training_config', {}).get(
                    'pipeline_config_path', "../../config/pipeline_race_history.json")

            self.data_pipeline = DataPipeline(config_path=pipeline_config_path)

            # Load artifacts if data version is available
            if self.data_version:
                logger.info(f"Loading pipeline artifacts from version: {self.data_version}")
                self.data_pipeline.load_artifacts(self.data_version)

    def predict(self, data: Union[pd.DataFrame, np.ndarray], 
                apply_pipeline: bool = False) -> np.ndarray:
        """Make predictions with the model.

        Args:
            data: Input data (DataFrame or numpy array)
            apply_pipeline: Whether to apply pipeline transformations

        Returns:
            Predictions as numpy array
        """
        # If data is a DataFrame and we need to apply pipeline transformations
        if isinstance(data, pd.DataFrame) and apply_pipeline:
            self._initialize_pipeline()

            # Apply transformations
            for step in self.data_pipeline.steps:
                # Only apply certain steps that are needed for inference
                if step.name in ["CategoricalEncoder", "NumericalScaler"]:
                    data = step.process(data)

            # Extract features
            if self.feature_columns:
                # Check if all feature columns are in the data
                missing_columns = [col for col in self.feature_columns if col not in data.columns]
                if missing_columns:
                    raise ValueError(f"Feature columns not found in data: {missing_columns}")

                features = data[self.feature_columns].values
            else:
                # If no feature columns specified, use all columns
                features = data.values

        # If data is already a numpy array or we don't need to apply pipeline transformations
        elif isinstance(data, pd.DataFrame):
            # Extract features if feature columns are specified
            if self.feature_columns:
                # Check if all feature columns are in the data
                missing_columns = [col for col in self.feature_columns if col not in data.columns]
                if missing_columns:
                    raise ValueError(f"Feature columns not found in data: {missing_columns}")

                features = data[self.feature_columns].values
            else:
                # If no feature columns specified, use all columns
                features = data.values
        else:
            # Data is already a numpy array
            features = data

        # Make predictions
        predictions = self.model.model.predict(features)

        return predictions

    def predict_from_checkpoint(self, dataset_name: str, version: str) -> Tuple[pd.DataFrame, np.ndarray]:
        """Make predictions on data from a checkpoint.

        Args:
            dataset_name: Name of the dataset
            version: Version string of the checkpoint

        Returns:
            Tuple of (original data, predictions)
        """
        self._initialize_pipeline()

        # Load data from checkpoint
        df = self.data_pipeline.load_checkpoint(dataset_name, version)

        # Make predictions
        predictions = self.predict(df, apply_pipeline=False)

        return df, predictions


def load_predictor(model_version: str, model_type: str = 'dense') -> ModelPredictor:
    """Load a predictor for a trained model.

    Args:
        model_version: Version string of the model to load
        model_type: Type of model ('dense', 'bilstm', etc.)

    Returns:
        ModelPredictor instance
    """
    return ModelPredictor(model_version=model_version, model_type=model_type)
