"""
Custom TensorFlow callbacks for model training.
"""

from typing import Dict, Any, Optional
import keras
from datetime import datetime
import json

from gonzo_pit_strategy.db.models.training_metrics import TrainingMetric
from gonzo_pit_strategy.db.models.training_runs import TrainingRun
from gonzo_pit_strategy.db.models.dataset_versions import (
    DatasetVersion,
)  # Needed for FK resolution
from gonzo_pit_strategy.db.repositories.model_repository import ModelRepository
from gonzo_pit_strategy.db.base import db_session
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.log.logger import get_logger

logger = get_logger(__name__)


class MetricsLoggingCallback(keras.callbacks.Callback):
    """
    Callback for logging training metrics to the database.

    This callback logs metrics at the end of each epoch to the database,
    preserving the training history for later analysis.
    """

    def __init__(self, run_id: int, split_types: Optional[Dict[str, str]] = None):
        """
        Initialize the metrics logging callback.

        Args:
            run_id: The training run ID to associate metrics with
            split_types: Optional mapping of metric prefixes to split types
                         (e.g., {'val_': 'VALIDATION', '': 'TRAIN'})
        """
        super().__init__()
        self.run_id = run_id
        self.split_types = split_types or {"val_": "VALIDATION", "": "TRAIN"}

    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        """
        Log metrics at the end of each epoch.

        Args:
            epoch: Current epoch number
            logs: Dictionary containing metrics
        """
        if not logs:
            return

        metrics = []
        timestamp = datetime.now()

        for metric_name, metric_value in logs.items():
            # Determine split type
            split_type = "TRAIN"  # Default
            for prefix, split in self.split_types.items():
                if metric_name.startswith(prefix):
                    split_type = split
                    # Remove prefix from metric name if it's a validation metric
                    if prefix and prefix != "":
                        metric_name = metric_name[len(prefix) :]
                    break

            metrics.append(
                TrainingMetric(
                    run_id=self.run_id,
                    epoch=epoch,
                    timestamp=timestamp,
                    metric_name=metric_name,
                    metric_value=float(metric_value),
                    split_type=split_type,
                )
            )

        # Store all metrics for this epoch in a single transaction
        with db_session() as session:
            session.add_all(metrics)
            session.commit()


class ConsoleMetricsCallback(keras.callbacks.Callback):
    """
    Callback for pretty-printing metrics to the console.
    """

    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        """
        Print metrics at the end of each epoch.

        Args:
            epoch: Current epoch number
            logs: Dictionary containing metrics
        """
        if not logs:
            return

        # Format epoch number
        epoch_str = f"Epoch {epoch + 1}"
        print(f"\n{epoch_str}")
        print("-" * len(epoch_str))

        # Group metrics by split type
        train_metrics = {k: v for k, v in logs.items() if not k.startswith("val_")}
        val_metrics = {
            k.replace("val_", ""): v for k, v in logs.items() if k.startswith("val_")
        }

        # Print training metrics
        if train_metrics:
            print("Training:")
            for name, value in train_metrics.items():
                print(f"  {name}: {value:.4f}")

        # Print validation metrics
        if val_metrics:
            print("Validation:")
            for name, value in val_metrics.items():
                print(f"  {name}: {value:.4f}")

        print()  # Add a newline for separation


class GonzoExperimentCallback(keras.callbacks.Callback):
    """
    Callback for managing the full lifecycle of an experiment.
    - Creates placeholder model record.
    - Creates TrainingRun record.
    - Logs metrics.
    - Updates records and saves artifacts on completion.
    """

    def __init__(
        self,
        config: TrainingConfig,
        model_repo: ModelRepository,
        model_version: str,
        config_path: Optional[str] = None,
    ):
        super().__init__()
        self.config = config
        self.repo = model_repo
        self.model_version = model_version
        self.config_path = config_path
        self.run_id = None
        self.model_id = None
        self.start_time = None

        # Reuse the logging logic
        self.metric_logger = None

    def on_train_begin(self, logs=None):
        self.start_time = datetime.now()

        # Prepare metadata
        metadata = {
            "model_name": "f1_pit_strategy_model.keras",  # Could be config param
            "model_version": self.model_version,
            "description": self.config.description or f"{self.config.model.type} model",
            "created_by": "GonzoExperimentCallback",
            "architecture": self.config.model.type,
            "tags": self.config.tags,
            "config": self.config.model_dump(),
            "config_path": self.config_path,
        }

        # Create placeholder model
        self.model_id = self.repo.create_placeholder_model(self.model_version, metadata)

        # Create TrainingRun
        with db_session() as session:
            run = TrainingRun(
                model_id=self.model_id,
                dataset_version_id=None,  # TODO: Track dataset version
                start_time=self.start_time,
                status="RUNNING",
                epochs_completed=0,
                early_stopping=True,  # Config param?
                environment_id="local",
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            self.run_id = run.run_id
            logger.info(
                f"Created TrainingRun ID: {self.run_id} for Model ID: {self.model_id} with config path: {self.config_path}"
            )

        # Initialize metric logger with the new run_id
        self.metric_logger = MetricsLoggingCallback(run_id=self.run_id)

    def on_epoch_end(self, epoch, logs=None):
        # Delegate to metric logger
        if self.metric_logger and logs:
            self.metric_logger.on_epoch_end(epoch, logs)

    def on_train_end(self, logs=None):
        if self.run_id is None or self.model_id is None:
            return

        # Update run status
        with db_session() as session:
            run = session.query(TrainingRun).filter_by(run_id=self.run_id).one()
            run.end_time = datetime.now()
            run.status = "COMPLETED"

            # Update epochs_completed by counting distinct epochs from training metrics
            # TODO:  do we need a DB query to derive the last epoch or could we get that from TF/Keras?
            epochs_completed = (
                session.query(TrainingMetric.epoch)
                .filter_by(run_id=self.run_id)
                .distinct()
                .count()
            )
            run.epochs_completed = epochs_completed

            session.commit()

        # Save model artifacts
        # We need to gather metadata again or update it
        metadata = {
            "model_name": "f1_pit_strategy_model.keras",
            "model_version": self.model_version,
            "description": self.config.description or f"{self.config.model.type} model",
            "created_by": "GonzoExperimentCallback",
            "architecture": self.config.model.type,
            "tags": self.config.tags,
            "config": self.config.model_dump(),
            # Add final metrics?
        }

        self.repo.update_model(self.model_id, self.model, self.model_version, metadata)
