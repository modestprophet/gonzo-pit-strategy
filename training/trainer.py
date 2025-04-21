"""
Model training functionality for F1 pit strategy prediction.

This module provides classes and functions for training machine learning models
using the processed data from the data pipeline.
"""
import os
import json
import time
from typing import Dict, Any, Optional, List, Tuple, Union
import numpy as np
import pandas as pd
import keras
from keras import callbacks
from pathlib import Path
from datetime import datetime

from models.model import get_model, ModelBase
from training.data_pipeline import DataPipeline
from gonzo_pit_strategy.log.logger import get_console_logger
from db.base import db_session
from db.models.model_metadata import ModelMetadata
from db.models.training_runs import TrainingRun
from db.models.training_metrics import TrainingMetric
from db.repositories.model_repository import ModelRepository
from training.callbacks import MetricsLoggingCallback

logger = get_console_logger(__name__)


class ModelTrainer:
    """Class for training machine learning models."""

    def __init__(self, config_path: str = "../../config/training.json"):
        """Initialize the trainer with configuration.

        Args:
            config_path: Path to training configuration JSON file
        """
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Store config path for reference
        self.config_path = config_path

        # Initialize model and data pipeline
        self.model = None
        self.data_pipeline = None

    def _prepare_data(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Prepare data for training.

        Returns:
            Tuple of (X_train, X_val, X_test, y_train, y_val, y_test)
        """
        # Get configuration parameters
        data_version = self.config.get('data_version')
        dataset_name = self.config.get('dataset_name', 'f1_race_data')
        target_column = self.config.get('target_column', 'finishpositiontext')
        feature_columns = self.config.get('feature_columns')
        test_size = self.config.get('test_size', 0.2)
        validation_size = self.config.get('validation_size', 0.1)
        random_state = self.config.get('random_state', 42)

        # Initialize data pipeline
        pipeline_config_path = self.config.get('pipeline_config_path', '../../config/pipeline_race_history.json')
        self.data_pipeline = DataPipeline(config_path=pipeline_config_path)

        # Load data
        if data_version:
            logger.info(f"Loading data version: {data_version}")
            df = self.data_pipeline.load_checkpoint(dataset_name, data_version)
        else:
            logger.info("Processing new data")
            df = self.data_pipeline.process()
            # Store the data version in the config for later use
            self.config['data_version'] = self.data_pipeline.version

        logger.info(f"Data shape: {df.shape}")

        # Split features and target
        if target_column not in df.columns:
            raise ValueError(f"Target column '{target_column}' not found in data")

        y = df[target_column].values

        if feature_columns:
            # Use specified feature columns
            missing_columns = [col for col in feature_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(f"Feature columns not found in data: {missing_columns}")
            X = df[feature_columns].values
        else:
            # Use all columns except target
            X = df.drop(columns=[target_column]).values
            # Store the feature columns in the config for later use
            self.config['feature_columns'] = [col for col in df.columns if col != target_column]
            feature_columns = self.config['feature_columns']

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
            X_train_val, y_train_val, test_size=val_size_adjusted, random_state=random_state
        )

        logger.info(f"Train set: {X_train.shape[0]} samples")
        logger.info(f"Validation set: {X_val.shape[0]} samples")
        logger.info(f"Test set: {X_test.shape[0]} samples")

        return X_train, X_val, X_test, y_train, y_val, y_test

    def _setup_callbacks(self, model_version: str) -> List[callbacks.Callback]:
        """Set up training callbacks.

        Args:
            model_version: Version string for the model

        Returns:
            List of Keras callbacks
        """
        cb_list = []

        # Get configuration parameters
        tensorboard_log_dir = self.config.get('tensorboard_log_dir', '../../logs/tensorboard')
        checkpoint_dir = self.config.get('checkpoint_dir', '../../models/checkpoints')
        save_best_only = self.config.get('save_best_only', True)
        early_stopping = self.config.get('early_stopping', True)
        patience = self.config.get('patience', 10)

        # TensorBoard callback
        log_dir = os.path.join(tensorboard_log_dir, model_version)
        os.makedirs(log_dir, exist_ok=True)
        tb_callback = callbacks.TensorBoard(
            log_dir=log_dir,
            histogram_freq=1,
            write_graph=True,
            update_freq='epoch'
        )
        cb_list.append(tb_callback)

        # Model checkpoint callback
        if checkpoint_dir:
            checkpoint_path = os.path.join(checkpoint_dir, model_version, 'model_checkpoint.h5')
            os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
            checkpoint_callback = callbacks.ModelCheckpoint(
                filepath=checkpoint_path,
                save_best_only=save_best_only,
                monitor='val_loss',
                mode='min',
                verbose=1
            )
            cb_list.append(checkpoint_callback)

        # Early stopping callback
        if early_stopping:
            early_stopping_callback = callbacks.EarlyStopping(
                monitor='val_loss',
                patience=patience,
                restore_best_weights=True,
                verbose=1
            )
            cb_list.append(early_stopping_callback)

        # CSV logger
        csv_log_path = os.path.join(tensorboard_log_dir, model_version, 'training_log.csv')
        csv_logger = callbacks.CSVLogger(csv_log_path, append=True)
        cb_list.append(csv_logger)

        return cb_list

    def train(self) -> Tuple[keras.Model, Dict[str, Any], str, int, int]:
        """Train the model.

        Returns:
            Tuple of (trained model, training history, model version, model_id, run_id)
        """
        # Get configuration parameters
        model_type = self.config.get('model_type', 'dense')
        model_config_path = self.config.get('model_config_path', '../../config/model.json')
        batch_size = self.config.get('batch_size', 32)
        epochs = self.config.get('epochs', 100)
        early_stopping = self.config.get('early_stopping', True)

        # Prepare data
        X_train, X_val, X_test, y_train, y_val, y_test = self._prepare_data()

        # Get feature_columns and target_column from config (updated by _prepare_data)
        feature_columns = self.config.get('feature_columns', [])
        target_column = self.config.get('target_column', 'finishpositiontext')
        data_version = self.config.get('data_version')

        # Get input and output shapes
        input_shape = X_train.shape[1:]
        if len(input_shape) == 0:
            input_shape = (X_train.shape[1],)

        if len(y_train.shape) == 1:
            output_shape = 1
        else:
            output_shape = y_train.shape[1]

        # Update model config with shapes
        with open(model_config_path, 'r') as f:
            model_config = json.load(f)

        model_config['input_shape'] = input_shape
        model_config['output_shape'] = output_shape
        model_config['feature_columns'] = feature_columns
        model_config['target_column'] = target_column

        with open(model_config_path, 'w') as f:
            json.dump(model_config, f, indent=2)

        # Initialize model
        self.model = get_model(model_type, config_path=model_config_path)

        # Build model
        model = self.model.build()
        model.summary()

        # Generate model version
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        model_version = f"{model_type}_{timestamp}"

        # Initialize model repository
        model_repo = ModelRepository(self.model.model_path)

        # Record the start time for the training run
        start_time = datetime.now()

        # Set up callbacks
        cb_list = self._setup_callbacks(model_version)

        # Train model
        logger.info(f"Starting training for {epochs} epochs")
        history = model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=cb_list,
            verbose=1
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
            "config_path": model_config_path,
            "feature_columns": feature_columns,
            "target_column": target_column,
            "input_shape": input_shape,
            "output_shape": output_shape,
            "train_samples": X_train.shape[0],
            "val_samples": X_val.shape[0],
            "test_samples": X_test.shape[0],
            "test_loss": float(test_loss),
            "test_metrics": {metric_name: float(test_metrics[i]) for i, metric_name in enumerate(model.metrics_names[1:])},
            "training_config": self.config
        }

        # Save model and metadata
        model_id = model_repo.save_model(model, model_version, metadata)
        logger.info(f"Model saved with ID {model_id} and version {model_version}")

        # Create training run with the real model_id
        with db_session() as session:
            training_run = TrainingRun(
                model_id=model_id,
                dataset_version_id=None,  # TODO: Get dataset version ID if available
                start_time=start_time,
                end_time=datetime.now(),
                status="COMPLETED",
                epochs_completed=len(history.history.get('loss', [])),
                early_stopping=early_stopping,
                environment_id="local"  # TODO: Get actual environment ID
            )
            session.add(training_run)
            session.commit()
            session.refresh(training_run)
            run_id = training_run.run_id
            logger.info(f"Created training run with ID {run_id} for model ID {model_id}")

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
                    split_type="TEST"
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
                        split_type="TEST"
                    )
                )

            # Save all metrics in a single transaction
            session.add_all(test_metrics_entries)
            session.commit()
            logger.info(f"Logged {len(test_metrics_entries)} test metrics for training run {run_id}")

        return model, history.history, model_version, model_id, run_id


def train_model(config_path: str = "../../config/training.json") -> Tuple[str, int, int]:
    """Train a model using the specified configuration.

    Args:
        config_path: Path to training configuration

    Returns:
        Tuple of (model_version, model_id, run_id)
    """
    trainer = ModelTrainer(config_path=config_path)
    _, _, model_version, model_id, run_id = trainer.train()
    return model_version, model_id, run_id
