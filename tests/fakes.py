"""In-memory adapters for the seams the training pipeline depends on.

The Run Ledger's second adapter. It exists so tests can drive a real
`Experiment` end to end without a database and without patching module
globals — the thing that made the previous `_FakeSession` necessary was that
the seam was a SQLAlchemy Session rather than the ledger interface.

It stores what the Postgres adapter stores, in the same shape: metrics split by
`val_` prefix, test metrics recorded on `complete`, one DatasetVersion per
fingerprint. Those are not conveniences — they are the interface as specified in
`training/ledger.py`, and `tests/test_run_ledger_contract.py` holds both
adapters to them. A fake that accepts what Postgres rejects is worse than no
fake at all.
"""

from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from gonzo_pit_strategy.training.artifact import ArtifactManifest
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import DatasetProvenance
from gonzo_pit_strategy.training.ledger import TEST, split_metric


@dataclass(frozen=True)
class RecordedMetric:
    """One metric row, mirroring `training_metrics`."""

    epoch: int
    name: str
    value: float
    split: str


@dataclass
class RecordedRun:
    """What the ledger would have written for one Training Run."""

    config: TrainingConfig
    status: str = "RUNNING"
    run_id: int = 1
    model_id: Optional[int] = None
    metrics: List[RecordedMetric] = field(default_factory=list)
    manifest: Optional[ArtifactManifest] = None
    artifact_path: Optional[str] = None
    provenance: Optional[DatasetProvenance] = None
    epochs_completed: Optional[int] = None
    config_source_path: Optional[str] = None


class InMemoryRunRecorder:
    def __init__(self, record: RecordedRun, ledger: "InMemoryRunLedger"):
        self._record = record
        self._ledger = ledger

    @property
    def run_id(self) -> Optional[int]:
        return self._record.run_id

    @property
    def model_id(self) -> Optional[int]:
        return self._record.model_id

    def record_epoch(self, epoch: int, logs: Dict[str, float]) -> None:
        if not logs:
            return
        for key, value in logs.items():
            metric_name, split_type = split_metric(key)
            self._record.metrics.append(
                RecordedMetric(
                    epoch=epoch,
                    name=metric_name,
                    value=float(value),
                    split=split_type,
                )
            )

    def complete(
        self,
        manifest: ArtifactManifest,
        artifact_path: Path,
        provenance: DatasetProvenance,
        *,
        epochs_completed: int,
        config_source_path: Optional[str] = None,
    ) -> None:
        self._record.manifest = manifest
        self._record.artifact_path = str(artifact_path)
        self._record.provenance = provenance
        self._record.epochs_completed = epochs_completed
        self._record.config_source_path = config_source_path
        self._record.model_id = self._record.run_id
        self._record.status = "COMPLETED"

        # epochs_completed - 1 is the last epoch index, matching the 0-based
        # `epoch` that record_epoch stores (db/run_ledger.py does the same).
        last_epoch = max(epochs_completed - 1, 0)
        for name, value in manifest.test_metrics.items():
            self._record.metrics.append(
                RecordedMetric(
                    epoch=last_epoch, name=name, value=float(value), split=TEST
                )
            )

        self._ledger.register_dataset_version(provenance)


class InMemoryRunLedger:
    """Run Ledger that keeps its records in a list."""

    def __init__(self) -> None:
        self.runs: List[RecordedRun] = []
        self.dataset_versions: List[Tuple[str, str]] = []

    @property
    def last(self) -> RecordedRun:
        return self.runs[-1]

    def register_dataset_version(self, provenance: DatasetProvenance) -> None:
        """Upsert on (dataset_name, version), as `dataset_versions`' unique
        constraint requires — version being the fingerprint's leading 16 chars.
        Re-training on unchanged data reuses the entry."""
        key = (provenance.name, provenance.fingerprint[:16])
        if key not in self.dataset_versions:
            self.dataset_versions.append(key)

    @contextmanager
    def run(self, config: TrainingConfig):
        record = RecordedRun(config=config, run_id=len(self.runs) + 1)
        self.runs.append(record)
        recorder = InMemoryRunRecorder(record, self)
        try:
            yield recorder
        except Exception:
            record.status = "FAILED"
            raise
        else:
            if record.status != "COMPLETED":
                record.status = "FAILED"
