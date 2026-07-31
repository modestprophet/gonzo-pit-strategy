"""Custom TensorFlow callbacks for model training."""

from typing import Dict, Any, Optional
import keras
from datetime import datetime

from gonzo_pit_strategy.db.models.training_metrics import TrainingMetric
from gonzo_pit_strategy.db.models.training_runs import TrainingRun
from gonzo_pit_strategy.db.models.dataset_versions import DatasetVersion
from gonzo_pit_strategy.db.repositories.model_repository import ModelRepository
from gonzo_pit_strategy.db.base import db_session
from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.artifact import ArtifactManifest, ArtifactStore
from gonzo_pit_strategy.training.data import LoadedData
import logging

logger = logging.getLogger(__name__)


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
    """Experiment lifecycle manager as a Keras callback (ADR 0002).
    - Creates a TrainingRun record on_train_begin (status RUNNING, no model row yet)
    - Delegates per-epoch metric logging to MetricsLoggingCallback
    - On train end: saves the self-describing Artifact (model + manifest),
      then mirrors it to the database once (ModelMetadata + DatasetVersion),
      and finalizes the TrainingRun.
    """

    def __init__(self, config: TrainingConfig, model_repo: ModelRepository,
                 artifact_store: ArtifactStore, loaded_data: LoadedData,
                 model_version: str, db_pool: ConnectionPool, config_path: Optional[str] = None):
        super().__init__()
        self.config = config
        self.repo = model_repo
        self.artifact_store = artifact_store
        self.loaded_data = loaded_data
        self.model_version = model_version
        self.db_pool = db_pool
        self.config_path = config_path
        self.run_id = None
        self.model_id = None
        self.start_time = None
        self.metric_logger = None

    def on_train_begin(self, logs=None):
        self.start_time = datetime.now()
        with db_session(self.db_pool) as session:
            run = TrainingRun(
                model_id=None, dataset_version_id=None,
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

    def _upsert_dataset_version(self, session) -> int:
        fingerprint = self.loaded_data.dataset_fingerprint
        version = fingerprint[:16]
        existing = (session.query(DatasetVersion)
                    .filter_by(dataset_name="prep_training_dataset", version=version)
                    .first())
        if existing:
            return existing.dataset_version_id
        dv = DatasetVersion(
            dataset_name="prep_training_dataset",
            version=version,
            description=f"Content fingerprint {fingerprint}",
            created_by="GonzoExperimentCallback",
            record_count=self.loaded_data.record_count,
            feature_count=self.loaded_data.feature_count,
        )
        session.add(dv)
        session.flush()
        return dv.dataset_version_id

    def on_train_end(self, logs=None):
        if self.run_id is None:
            return

        manifest = ArtifactManifest(
            model_name="f1_pit_strategy_model",
            model_version=self.model_version,
            architecture=self.config.model.type,
            feature_names=self.loaded_data.feature_names,
            target_column=self.config.target_column,
            training_config=self.config.model_dump(mode="json"),
            framework_version=keras.__version__,
            dataset_fingerprint=self.loaded_data.dataset_fingerprint,
            created_by="GonzoExperimentCallback",
            description=self.config.description or f"{self.config.model.type} model",
            tags=self.config.tags,
        )
        artifact_dir = self.artifact_store.save(self.model, manifest)

        with db_session(self.db_pool) as session:
            self.model_id = self.repo.record_model(
                manifest, str(artifact_dir), session, config_source_path=self.config_path
            )
            run = session.query(TrainingRun).filter_by(run_id=self.run_id).one()
            run.model_id = self.model_id
            run.dataset_version_id = self._upsert_dataset_version(session)
            run.end_time = datetime.now()
            run.status = "COMPLETED"
            run.epochs_completed = (session.query(TrainingMetric.epoch)
                .filter_by(run_id=self.run_id).distinct().count())
