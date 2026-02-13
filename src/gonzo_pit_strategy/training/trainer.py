"""
Model training functionality for F1 pit strategy prediction.

This module provides classes and functions for training machine learning models
using the processed data from the data pipeline.
"""

import os
import json
import time
from typing import Dict, Any, List, Tuple
import numpy as np
import keras
from keras import callbacks
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

from gonzo_pit_strategy.models.model import get_model
from gonzo_pit_strategy.log.logger import get_logger
from gonzo_pit_strategy.db.base import db_session
from gonzo_pit_strategy.db.config import DatabaseConfig
from gonzo_pit_strategy.db.models.training_runs import TrainingRun
from gonzo_pit_strategy.db.models.training_metrics import TrainingMetric
from gonzo_pit_strategy.training.callbacks import (
    MetricsLoggingCallback,
    ConsoleMetricsCallback,
)
from gonzo_pit_strategy.db.models.dataset_versions import DatasetVersion  # noqa: F401 - Import needed for FK resolution
from gonzo_pit_strategy.db.repositories.model_repository import ModelRepository
from gonzo_pit_strategy.config.config import config

logger = get_logger(__name__)


class ModelTrainer:
    """Class for training machine learning models."""

    def __init__(self, config_name: str = "training"):
        """Initialize the trainer with configuration.

        Args:
            config_name: Name of the configuration to use (default: "training")
        """
        self.config = config.get_config(config_name)

        # Store config name for reference
        self.config_name = config_name

        # Initialize model
        self.model = None

    def _prepare_data(
        self,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Prepare data for training by loading from dbt-generated table.

        Returns:
            Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
        """
        # Get configuration parameters
        target_column = self.config.get("target_column", "finish_position")
        feature_columns = self.config.get("feature_columns")
        test_size = self.config.get("test_size", 0.2)
        validation_size = self.config.get("validation_size", 0.1)
        random_state = self.config.get("random_state", 42)

        # Connect to database and load dbt-generated training dataset
        logger.info("Loading training dataset from f1db_ml_prep.prep_training_dataset")
        db_config = DatabaseConfig()
        url_dict = db_config.get_db_url_dict()
        engine = create_engine(URL.create(**url_dict))

        df = pd.read_sql("SELECT * FROM f1db_ml_prep.prep_training_dataset", engine)
        engine.dispose()

        logger.info(f"Data shape: {df.shape}")

        # Convert object dtype columns (typically all-NULL scaled columns) to float, filling NaN with 0
        object_cols = df.select_dtypes(include=["object"]).columns.tolist()
        if object_cols:
            logger.info(
                f"Converting {len(object_cols)} object columns to float and filling NaN with 0: {object_cols}"
            )
            for col in object_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        # Fill any remaining NaN values with 0 (from scaled columns where stddev=0)
        nan_count = df.isnull().sum().sum()
        if nan_count > 0:
            nan_cols = df.columns[df.isnull().any()].tolist()
            logger.info(f"Filling {nan_count} NaN values with 0 in columns: {nan_cols}")
            df = df.fillna(0.0)

        # Convert boolean OHE columns to integers for Keras
        # OHE columns start with circuit_, team_, or driver_ but NOT ending with _scaled
        ohe_cols = [
            col
            for col in df.columns
            if col.startswith(("circuit_", "team_", "driver_"))
            and not col.endswith("_scaled")
        ]
        if ohe_cols:
            logger.info(
                f"Converting {len(ohe_cols)} one-hot encoded columns to integers"
            )
            df[ohe_cols] = df[ohe_cols].astype(int)

        # Split features and target
        if target_column not in df.columns:
            raise ValueError(f"Target column '{target_column}' not found in data")

        y = df[target_column].values

        if feature_columns:
            # Use specified feature columns
            missing_columns = [col for col in feature_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(
                    f"Feature columns not found in data: {missing_columns}"
                )
            X = df[feature_columns].values
        else:
            # Use all columns except target
            X = df.drop(columns=[target_column]).values
            # Store the feature columns in the config for later use
            self.config["feature_columns"] = [
                col for col in df.columns if col != target_column
            ]
            feature_columns = self.config["feature_columns"]

        logger.info(f"Features shape: {X.shape}, Target shape: {y.shape}")

        # Split data into train, validation, and test sets
        from sklearn.model_selection import train_test_split

        # First split off the test set
        X_train_val, X_test, y_train_val, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state
        )

        # Then split the remaining data into train and validation sets
        val_size_adjusted = validation_size / (1 - test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_train_val,
            y_train_val,
            test_size=val_size_adjusted,
            random_state=random_state,
        )

        logger.info(f"Train set: {X_train.shape[0]} samples")
        logger.info(f"Validation set: {X_val.shape[0]} samples")
        logger.info(f"Test set: {X_test.shape[0]} samples")

        return X_train, X_val, X_test, y_train, y_val, y_test

    def _setup_callbacks(
        self, model_version: str, run_id: int
    ) -> List[callbacks.Callback]:
        """Set up training callbacks.

        Args:
            model_version: Version string for the model

        Returns:
            List of Keras callbacks
        """
        cb_list = []

        # Get configuration parameters
        tensorboard_log_dir = self.config.get("tensorboard_log_dir", "logs/tensorboard")
        checkpoint_dir = self.config.get("checkpoint_dir", "models/checkpoints")
        save_best_only = self.config.get("save_best_only", True)
        early_stopping = self.config.get("early_stopping", True)
        patience = self.config.get("patience", 10)

        # Resolve paths relative to project root
        tensorboard_log_dir = str(config.get_path(tensorboard_log_dir))
        checkpoint_dir = (
            str(config.get_path(checkpoint_dir)) if checkpoint_dir else None
        )

        # TensorBoard callback
        log_dir = os.path.join(tensorboard_log_dir, model_version)
        os.makedirs(log_dir, exist_ok=True)
        tb_callback = callbacks.TensorBoard(
            log_dir=log_dir, histogram_freq=1, write_graph=True, update_freq="epoch"
        )
        cb_list.append(tb_callback)

        # Model checkpoint callback
        if checkpoint_dir:
            checkpoint_path = os.path.join(
                checkpoint_dir, model_version, "model_checkpoint.h5"
            )
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            checkpoint_callback = callbacks.ModelCheckpoint(
                filepath=checkpoint_path,
                save_best_only=save_best_only,
                monitor="val_loss",
                mode="min",
                verbose=1,
            )
            cb_list.append(checkpoint_callback)

        # Early stopping callback
        if early_stopping:
            early_stopping_callback = callbacks.EarlyStopping(
                monitor="val_loss",
                patience=patience,
                restore_best_weights=True,
                verbose=1,
            )
            cb_list.append(early_stopping_callback)

        # CSV logger
        csv_log_path = os.path.join(
            tensorboard_log_dir, model_version, "training_log.csv"
        )
        csv_logger = callbacks.CSVLogger(csv_log_path, append=True)
        cb_list.append(csv_logger)

        # Custom callbacks for database and console logging
        cb_list.append(MetricsLoggingCallback(run_id=run_id))
        cb_list.append(ConsoleMetricsCallback())

        return cb_list

    def train(self) -> Tuple[keras.Model, Dict[str, Any], str, int, int]:
        """Train the model.

        Returns:
            Tuple of (trained model, training history, model version, model_id, run_id)
        """
        # Get configuration parameters
        model_type = self.config.get("model_type", "dense")
        model_config_name = self.config.get("model_config_name", "model")
        batch_size = self.config.get("batch_size", 32)
        epochs = self.config.get("epochs", 100)
        early_stopping = self.config.get("early_stopping", True)

        # Prepare data
        X_train, X_val, X_test, y_train, y_val, y_test = self._prepare_data()

        # Get feature_columns and target_column from config (updated by _prepare_data)
        feature_columns = self.config.get("feature_columns", [])
        target_column = self.config.get("target_column", "finish_position")
        data_version = None  # No longer using data versioning - dbt handles this

        # Get input and output shapes
        input_shape = X_train.shape[1:]
        if len(input_shape) == 0:
            input_shape = (X_train.shape[1],)

        if len(y_train.shape) == 1:
            output_shape = 1
        else:
            output_shape = y_train.shape[1]

        # Update model config with shapes
        model_config = config.get_config(model_config_name, reload=True)

        model_config["input_shape"] = input_shape
        model_config["output_shape"] = output_shape
        model_config["feature_columns"] = feature_columns
        model_config["target_column"] = target_column

        # Save updated configuration
        config_path = config.get_config_path(model_config_name)
        with open(config_path, "w") as f:
            json.dump(model_config, f, indent=2)

        # Initialize model
        self.model = get_model(model_type, config_name=model_config_name)

        # Build model
        model = self.model.build()
        model.summary()

        # Generate model version
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        model_version = f"{model_type}_{timestamp}"

        # Initialize model repository
        model_repo = ModelRepository(self.model.model_path)

        # Prepare initial metadata for placeholder creation
        initial_metadata = {
            "model_name": self.model.model_name,
            "model_version": model_version,
            "description": f"{model_type} model for {target_column} prediction (Training in progress)",
            "created_by": "ModelTrainer",
            "architecture": model_type,
            "tags": ["f1", "pit_strategy", model_type, "training_in_progress"],
            "config": model_config,
            "config_path": str(config_path),
        }

        # Create placeholder model record
        model_id = model_repo.create_placeholder_model(model_version, initial_metadata)
        logger.info(f"Created placeholder model record with ID {model_id}")

        # Record the start time and create a RUNNING training run
        start_time = datetime.now()
        with db_session() as session:
            # Create a preliminary run entry with RUNNING status
            training_run = TrainingRun(
                model_id=model_id,
                dataset_version_id=None,
                start_time=start_time,
                end_time=None,
                status="RUNNING",  # Set initial status to RUNNING
                epochs_completed=0,
                early_stopping=early_stopping,
                environment_id="local",
            )
            session.add(training_run)
            session.commit()
            session.refresh(training_run)
            run_id = training_run.run_id
            logger.info(f"Created training run with ID {run_id} (Status: RUNNING)")

        # Set up callbacks, now passing the run_id
        cb_list = self._setup_callbacks(model_version, run_id)

        # Train model
        logger.info(f"Starting training for {epochs} epochs")
        history = model.fit(
            X_train,
            y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=cb_list,
            verbose=1,
        )

        # Evaluate on test set
        test_loss, *test_metrics = model.evaluate(X_test, y_test, verbose=1)
        logger.info(f"Test loss: {test_loss}")
        for i, metric_name in enumerate(model.metrics_names[1:]):
            logger.info(f"Test {metric_name}: {test_metrics[i]}")

        # Prepare metadata
        metadata = {
            "model_name": self.model.model_name,
            "model_type": model_type,
            "model_version": model_version,
            "data_version": data_version,
            "description": f"{model_type} model for {target_column} prediction",
            "created_by": "ModelTrainer",
            "architecture": model_type,
            "tags": ["f1", "pit_strategy", model_type],
            "config": model_config,
            "config_name": model_config_name,
            "feature_columns": feature_columns,
            "target_column": target_column,
            "input_shape": input_shape,
            "output_shape": output_shape,
            "train_samples": X_train.shape[0],
            "val_samples": X_val.shape[0],
            "test_samples": X_test.shape[0],
            "test_loss": float(test_loss),
            "test_metrics": {
                metric_name: float(test_metrics[i])
                for i, metric_name in enumerate(model.metrics_names[1:])
            },
            "training_config": self.config,
            "environment": config.environment,
            "config_path": str(config_path),
        }

        # Save model artifacts and update metadata
        model_repo.update_model(model_id, model, model_version, metadata)
        logger.info(f"Model artifacts saved and metadata updated for ID {model_id}")

        # Update the training run status
        with db_session() as session:
            # Fetch the existing run to update
            training_run = session.query(TrainingRun).filter_by(run_id=run_id).one()

            # Update fields
            training_run.end_time = datetime.now()
            training_run.status = "COMPLETED"
            training_run.epochs_completed = len(history.history.get("loss", []))

            session.commit()
            logger.info(f"Updated training run {run_id} to COMPLETED")

            # Log test metrics
            test_metrics_entries = []
            # Add loss metric
            test_metrics_entries.append(
                TrainingMetric(
                    run_id=run_id,
                    epoch=-1,  # Use -1 to indicate test metrics
                    timestamp=datetime.now(),
                    metric_name="loss",
                    metric_value=float(test_loss),
                    split_type="TEST",
                )
            )

            # Add other metrics
            for i, metric_name in enumerate(model.metrics_names[1:]):
                test_metrics_entries.append(
                    TrainingMetric(
                        run_id=run_id,
                        epoch=-1,  # Use -1 to indicate test metrics
                        timestamp=datetime.now(),
                        metric_name=metric_name,
                        metric_value=float(test_metrics[i]),
                        split_type="TEST",
                    )
                )

            # Save all metrics in a single transaction
            session.add_all(test_metrics_entries)
            session.commit()
            logger.info(
                f"Logged {len(test_metrics_entries)} test metrics for training run {run_id}"
            )

        return model, history.history, model_version, model_id, run_id


def train_model(config_name: str = "training") -> Tuple[str, int, int]:
    """Train a model using the specified configuration.

    Args:
        config_name: Name of the configuration to use (default: "training")

    Returns:
        Tuple of (model_version, model_id, run_id)
    """
    trainer = ModelTrainer(config_name=config_name)
    _, _, model_version, model_id, run_id = trainer.train()
    return model_version, model_id, run_id
