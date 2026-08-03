"""
Postgres adapter for the Run Ledger seam (`training/ledger.py`).

This is the only module that turns a Training Run into SQL. Callers never see
a Session: they get a `RunRecorder` and the transaction shape is this module's
business. Per ADR 0002 §3 the database is a reporting mirror — the Artifact on
disk stays authoritative, and a failure here does not invalidate it.
"""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, Optional

from gonzo_pit_strategy.db.base import db_session
from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.db.models.dataset_versions import DatasetVersion
from gonzo_pit_strategy.db.models.model_metadata import ModelMetadata
from gonzo_pit_strategy.db.models.training_metrics import TrainingMetric
from gonzo_pit_strategy.db.models.training_runs import TrainingRun
from gonzo_pit_strategy.training.artifact import ArtifactManifest
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import DatasetProvenance
from gonzo_pit_strategy.training.ledger import TEST, split_metric
import logging

logger = logging.getLogger(__name__)


class _PostgresRunRecorder:
    """Handle for one Training Run row. Constructed by PostgresRunLedger."""

    def __init__(self, pool: ConnectionPool, run_id: int):
        self._pool = pool
        self._run_id = run_id
        self._model_id: Optional[int] = None
        self.completed = False

    @property
    def run_id(self) -> Optional[int]:
        return self._run_id

    @property
    def model_id(self) -> Optional[int]:
        return self._model_id

    def record_epoch(self, epoch: int, logs: Dict[str, float]) -> None:
        if not logs:
            return
        timestamp = datetime.now()
        metrics = []
        for key, value in logs.items():
            metric_name, split_type = split_metric(key)
            metrics.append(
                TrainingMetric(
                    run_id=self._run_id,
                    epoch=epoch,
                    timestamp=timestamp,
                    metric_name=metric_name,
                    metric_value=float(value),
                    split_type=split_type,
                )
            )
        with db_session(self._pool) as session:
            session.add_all(metrics)

    def complete(
        self,
        manifest: ArtifactManifest,
        artifact_path: Path,
        provenance: DatasetProvenance,
        *,
        epochs_completed: int,
        config_source_path: Optional[str] = None,
    ) -> None:
        # One transaction: the model mirror, the dataset link, the test
        # metrics, and the run's terminal state land together or not at all.
        with db_session(self._pool) as session:
            model_metadata = ModelMetadata(
                name=manifest.model_name,
                version=manifest.model_version,
                description=manifest.description or "",
                created_at=manifest.created_at,
                created_by=manifest.created_by,
                architecture=manifest.architecture,
                framework_version=manifest.framework_version,
                tags=manifest.tags,
                configuration=manifest.model_dump(mode="json"),
                config_source_path=config_source_path or "",
                artifact_path=str(artifact_path),
            )
            session.add(model_metadata)
            session.flush()

            if manifest.test_metrics:
                # epochs_completed - 1 is the last epoch index, matching the
                # 0-based `epoch` that record_epoch stores.
                session.add_all(
                    TrainingMetric(
                        run_id=self._run_id,
                        epoch=max(epochs_completed - 1, 0),
                        timestamp=datetime.now(),
                        metric_name=name,
                        metric_value=float(value),
                        split_type=TEST,
                    )
                    for name, value in manifest.test_metrics.items()
                )

            run = session.query(TrainingRun).filter_by(run_id=self._run_id).one()
            run.model_id = model_metadata.model_id
            run.dataset_version_id = self._dataset_version_id(session, provenance)
            run.end_time = datetime.now()
            run.status = "COMPLETED"
            run.epochs_completed = epochs_completed
            # Read inside the session: after commit the instance is expired and
            # touching the attribute would trigger a refresh on a closed session.
            self._model_id = model_metadata.model_id

        self.completed = True
        logger.info(
            f"Recorded run {self._run_id} as COMPLETED "
            f"(model_id={self._model_id}, artifact={artifact_path})"
        )

    def fail(self) -> None:
        """Mark the run FAILED. Best-effort: a run dies for reasons that may
        also have taken the database with it, and the original exception is
        more informative than a secondary failure to record it."""
        try:
            with db_session(self._pool) as session:
                run = session.query(TrainingRun).filter_by(run_id=self._run_id).one()
                run.end_time = datetime.now()
                run.status = "FAILED"
        except Exception as e:
            logger.warning(f"Could not mark run {self._run_id} FAILED: {e}")

    @staticmethod
    def _dataset_version_id(session, provenance: DatasetProvenance) -> int:
        """Upsert the DatasetVersion for this fingerprint, returning its id.

        `dataset_versions` is unique on (dataset_name, version), and version is
        the fingerprint's leading 16 chars — so re-training on unchanged data
        reuses the row rather than duplicating it.
        """
        version = provenance.fingerprint[:16]
        existing = (
            session.query(DatasetVersion)
            .filter_by(dataset_name=provenance.name, version=version)
            .first()
        )
        if existing:
            return existing.dataset_version_id
        dataset_version = DatasetVersion(
            dataset_name=provenance.name,
            version=version,
            description=f"Content fingerprint {provenance.fingerprint}",
            created_by="Experiment",
            record_count=provenance.record_count,
            feature_count=provenance.feature_count,
        )
        session.add(dataset_version)
        session.flush()
        return dataset_version.dataset_version_id


class PostgresRunLedger:
    """Run Ledger backed by the application database."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    @contextmanager
    def run(
        self, config: TrainingConfig, *, environment: str = "local"
    ) -> Iterator[_PostgresRunRecorder]:
        with db_session(self._pool) as session:
            training_run = TrainingRun(
                model_id=None,
                dataset_version_id=None,
                start_time=datetime.now(),
                status="RUNNING",
                epochs_completed=0,
                early_stopping=config.early_stopping_patience > 0,
                environment_id=environment,
            )
            session.add(training_run)
            session.flush()
            run_id = training_run.run_id

        recorder = _PostgresRunRecorder(self._pool, run_id)
        logger.info(f"Opened training run {run_id} (status RUNNING)")
        try:
            yield recorder
        except Exception:
            recorder.fail()
            raise
        else:
            if not recorder.completed:
                # Left the block without completing: not an exception, but not
                # a finished run either. RUNNING would be a lie.
                logger.warning(
                    f"Run {run_id} ended without complete(); marking FAILED"
                )
                recorder.fail()
