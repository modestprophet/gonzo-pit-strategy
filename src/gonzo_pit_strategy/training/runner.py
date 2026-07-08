"""
Experiment runner for executing training pipelines.
"""

import os
import time
import keras
from keras import callbacks
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import load_training_data, TrainingDataSource
from gonzo_pit_strategy.training.model_factory import build_model
from gonzo_pit_strategy.training.callbacks import (
    GonzoExperimentCallback,
    ConsoleMetricsCallback,
)
from gonzo_pit_strategy.db.repositories.model_repository import ModelRepository
from gonzo_pit_strategy.config.config import AppConfig
import logging

logger = logging.getLogger(__name__)


from gonzo_pit_strategy.db.connection_pool import ConnectionPool

@dataclass
class ExperimentResult:
    model_version: str
    model_id: Optional[int]
    run_id: Optional[int]
    test_loss: float
    test_metrics: Dict[str, float]
    history: Dict[str, Any]


class Experiment:
    """
    Encapsulates the full lifecycle of a single model training process.
    Provides a deep module interface to run training from a configuration.
    """

    def __init__(
        self,
        config: TrainingConfig,
        data_source: TrainingDataSource,
        db_pool: ConnectionPool,
        config_path: Optional[str] = None,
    ):
        self.config = config
        self.data_source = data_source
        self.db_pool = db_pool
        self.config_path = config_path

    def run(self) -> ExperimentResult:
        """
        Execute a full training experiment based on the configuration.

        Returns:
            ExperimentResult object.
        """
        # 1. Load Data
        logger.info("Loading training data...")
        X_train, X_val, X_test, y_train, y_val, y_test, feature_names = load_training_data(
            self.config, self.data_source
        )

        input_shape = X_train.shape[1:]
        output_shape = 1 if len(y_train.shape) == 1 else y_train.shape[1]

        logger.info(f"Input shape: {input_shape}, Output shape: {output_shape}")

        # 2. Build Model
        logger.info(f"Building {self.config.model.type} model...")
        model = build_model(self.config, input_shape, output_shape)
        model.summary()

        # 3. Setup Callbacks & Logging
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        model_version = f"{self.config.model.type}_{timestamp}"

        # Resolve paths
        model_artifacts_path = str(os.path.join(os.getcwd(), "models/artifacts"))
        tensorboard_log_dir = str(os.path.join(os.getcwd(), "logs/tensorboard"))
        checkpoint_dir = str(os.path.join(os.getcwd(), "models/checkpoints"))

        repo = ModelRepository(model_artifacts_path)

        # Main Experiment Callback (Handles DB, Artifacts)
        experiment_cb = GonzoExperimentCallback(
            self.config, repo, model_version, db_pool=self.db_pool, config_path=self.config_path
        )

        cb_list = [experiment_cb]

        # Console Logger
        cb_list.append(ConsoleMetricsCallback())

        # TensorBoard
        log_dir = os.path.join(tensorboard_log_dir, model_version)
        os.makedirs(log_dir, exist_ok=True)
        cb_list.append(
            callbacks.TensorBoard(
                log_dir=log_dir, histogram_freq=1, write_graph=True, update_freq="epoch"
            )
        )

        # Early Stopping
        if self.config.early_stopping_patience > 0:
            cb_list.append(
                callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=self.config.early_stopping_patience,
                    restore_best_weights=True,
                    verbose=1,
                )
            )

        # Checkpointing
        checkpoint_path = os.path.join(checkpoint_dir, model_version, "model_checkpoint.h5")
        os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
        cb_list.append(
            callbacks.ModelCheckpoint(
                filepath=checkpoint_path,
                save_best_only=True,
                monitor="val_loss",
                mode="min",
                verbose=1,
            )
        )

        # 4. Train
        logger.info(f"Starting training for {self.config.epochs} epochs...")
        history = model.fit(
            X_train,
            y_train,
            validation_data=(X_val, y_val),
            epochs=self.config.epochs,
            batch_size=self.config.batch_size,
            callbacks=cb_list,
            verbose=1,
        )

        # 5. Evaluate
        logger.info("Evaluating on test set...")
        test_loss, *test_metric_values = model.evaluate(X_test, y_test, verbose=1)

        test_metrics = {
            name: val for name, val in zip(model.metrics_names[1:], test_metric_values)
        }

        logger.info(f"Test Loss: {test_loss}")
        logger.info(f"Test Metrics: {test_metrics}")

        return ExperimentResult(
            model_version=model_version,
            model_id=experiment_cb.model_id,
            run_id=experiment_cb.run_id,
            test_loss=test_loss,
            test_metrics=test_metrics,
            history=history.history,
        )
