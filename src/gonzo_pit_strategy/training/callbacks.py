"""Custom TensorFlow callbacks for model training."""

from typing import Dict, Any, Optional
import keras
from datetime import datetime
import json

from gonzo_pit_strategy.db.models.training_metrics import TrainingMetric
from gonzo_pit_strategy.db.models.training_runs import TrainingRun
from gonzo_pit_strategy.db.models.dataset_versions import DatasetVersion  # Needed for FK resolution
from gonzo_pit_strategy.db.repositories.model_repository import ModelRepository
from gonzo_pit_strategy.db.base import db_session
from gonzo_pit_strategy.training.config import TrainingConfig
import logging

logger = logging.getLogger(__name__)


from gonzo_pit_strategy.db.connection_pool import ConnectionPool

class MetricsLoggingCallback(keras.callbacks.Callback):
    """Logs training metrics to the database at each epoch end."""
    
    def __init__(self, run_id: int, db_pool: ConnectionPool, split_types: Optional[Dict[str, str]] = None):
        super().__init__()
        self.run_id = run_id
        self.db_pool = db_pool
        self.split_types = split_types or {"val_": "VALIDATION", "": "TRAIN"}

    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        if not logs:
            return
        metrics = []
        timestamp = datetime.now()
        for metric_name, metric_value in logs.items():
            split_type = "TRAIN"
            for prefix, split in self.split_types.items():
                if metric_name.startswith(prefix):
                    split_type = split
                    if prefix and prefix != "":
                        metric_name = metric_name[len(prefix):]
                    break
            metrics.append(TrainingMetric(
                run_id=self.run_id, epoch=epoch, timestamp=timestamp,
                metric_name=metric_name, metric_value=float(metric_value),
                split_type=split_type,
            ))
        with db_session(self.db_pool) as session:
            session.add_all(metrics)


class ConsoleMetricsCallback(keras.callbacks.Callback):
    """Pretty-prints metrics to stdout at each epoch end."""
    
    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        if not logs:
            return
        epoch_str = f"Epoch {epoch + 1}"
        print(f"\n{epoch_str}")
        print("-" * len(epoch_str))
        train_metrics = {k: v for k, v in logs.items() if not k.startswith("val_")}
        val_metrics = {k.replace("val_", ""): v for k, v in logs.items() if k.startswith("val_")}
        if train_metrics:
            print("Training:")
            for name, value in train_metrics.items():
                print(f"  {name}: {value:.4f}")
        if val_metrics:
            print("Validation:")
            for name, value in val_metrics.items():
                print(f"  {name}: {value:.4f}")
        print()


class GonzoExperimentCallback(keras.callbacks.Callback):
    """Full experiment lifecycle manager as a Keras callback.
    - Creates placeholder model record on_train_begin
    - Creates TrainingRun record on_train_begin
    - Delegates per-epoch metric logging to MetricsLoggingCallback
    - Updates run status and saves artifacts on_train_end
    """
    
    def __init__(self, config: TrainingConfig, model_repo: ModelRepository,
                 model_version: str, db_pool: ConnectionPool, config_path: Optional[str] = None):
        super().__init__()
        self.config = config
        self.repo = model_repo
        self.model_version = model_version
        self.db_pool = db_pool
        self.config_path = config_path
        self.run_id = None
        self.model_id = None
        self.start_time = None
        self.metric_logger = None

    def on_train_begin(self, logs=None):
        self.start_time = datetime.now()
        metadata = {
            "model_name": "f1_pit_strategy_model.keras",
            "model_version": self.model_version,
            "description": self.config.description or f"{self.config.model.type} model",
            "created_by": "GonzoExperimentCallback",
            "architecture": self.config.model.type,
            "tags": self.config.tags,
            "config": self.config.model_dump(),
            "config_path": self.config_path,
        }
        with db_session(self.db_pool) as session:
            self.model_id = self.repo.create_placeholder_model(self.model_version, metadata, session)
            run = TrainingRun(
                model_id=self.model_id, dataset_version_id=None,
                start_time=self.start_time, status="RUNNING",
                epochs_completed=0, early_stopping=True, environment_id="local",
            )
            session.add(run)
            session.flush()
            self.run_id = run.run_id
        self.metric_logger = MetricsLoggingCallback(run_id=self.run_id, db_pool=self.db_pool)

    def on_epoch_end(self, epoch, logs=None):
        if self.metric_logger and logs:
            self.metric_logger.on_epoch_end(epoch, logs)

    def on_train_end(self, logs=None):
        if self.run_id is None or self.model_id is None:
            return
        with db_session(self.db_pool) as session:
            run = session.query(TrainingRun).filter_by(run_id=self.run_id).one()
            run.end_time = datetime.now()
            run.status = "COMPLETED"
            epochs_completed = (session.query(TrainingMetric.epoch)
                .filter_by(run_id=self.run_id).distinct().count())
            run.epochs_completed = epochs_completed
            
            metadata = {
                "model_name": "f1_pit_strategy_model.keras",
                "model_version": self.model_version,
                "description": self.config.description or f"{self.config.model.type} model",
                "created_by": "GonzoExperimentCallback",
                "architecture": self.config.model.type,
                "tags": self.config.tags,
                "config": self.config.model_dump(),
            }
            self.repo.update_model(self.model_id, self.model, self.model_version, metadata, session)
