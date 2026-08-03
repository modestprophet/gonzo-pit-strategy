"""
The Run Ledger seam: everything the database records about a Training Run.

This module defines the interface only, in training's own vocabulary —
Artifact Manifest, Dataset Provenance, epoch metrics. It imports nothing from
`db`, so the dependency runs one way: the Postgres adapter in
`db/run_ledger.py` imports these types, not the reverse.

The interface is a context manager because a Training Run has an invariant
that is otherwise enforced only by discipline: it always reaches a terminal
status. Leaving the block — by return or by exception — closes the run.

    with ledger.run(config) as run:
        model.fit(..., callbacks=[EpochMetricsCallback(run)])
        run.complete(manifest, artifact_dir, provenance, epochs_completed=n)

Exiting without calling `complete` marks the run FAILED; that is the honest
record of a training process that died partway, and it is what keeps a crashed
Sweep iteration from leaving a row stuck at RUNNING forever.
"""

from pathlib import Path
from typing import ContextManager, Dict, Optional, Protocol, Tuple

from gonzo_pit_strategy.training.artifact import ArtifactManifest
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import DatasetProvenance

# Keras prefixes validation metrics with `val_`; everything else is training.
VALIDATION_PREFIX = "val_"

#: Split labels a metric can carry. The database CHECK constraint on
#: `training_metrics.split_type` allows exactly these three.
TRAIN, VALIDATION, TEST = "TRAIN", "VALIDATION", "TEST"


def split_metric(name: str) -> Tuple[str, str]:
    """Map a Keras log key to `(metric_name, split_type)`.

    Lives beside the `record_epoch` docstring that specifies this rule so that
    both adapters call one implementation. A second copy is how the in-memory
    and Postgres adapters would drift apart.
    """
    if name.startswith(VALIDATION_PREFIX):
        return name[len(VALIDATION_PREFIX) :], VALIDATION
    return name, TRAIN


class RunRecorder(Protocol):
    """Handle for one in-flight Training Run.

    Obtained from `RunLedger.run`; not constructed directly. The run row
    already exists by the time a caller holds one of these, so `run_id` is
    available for correlating logs while training is still going.
    """

    @property
    def run_id(self) -> Optional[int]:
        """Identity of the Training Run row, or None for adapters that do not
        assign one."""
        ...

    @property
    def model_id(self) -> Optional[int]:
        """Identity of the mirrored Model Metadata row. None until `complete`
        has run — before that there is deliberately no model row (ADR 0002 §3
        rejects placeholder rows)."""
        ...

    def record_epoch(self, epoch: int, logs: Dict[str, float]) -> None:
        """Record one epoch's metrics.

        `logs` is Keras' raw logs dict: bare names are training metrics,
        `val_`-prefixed ones are validation. Written as the epoch completes
        rather than buffered to the end, so a run that crashes still leaves
        the metrics that led up to the crash.
        """
        ...

    def complete(
        self,
        manifest: ArtifactManifest,
        artifact_path: Path,
        provenance: DatasetProvenance,
        *,
        epochs_completed: int,
        config_source_path: Optional[str] = None,
    ) -> None:
        """Close the run as COMPLETED and mirror the Artifact to the database.

        Call once, after the Artifact is on disk — the mirror records
        `artifact_path`, so writing it before the file exists would publish a
        path to nothing. The manifest's `test_metrics` are also recorded as
        TEST-split metrics for the run.
        """
        ...


class RunLedger(Protocol):
    """Owner of the database record of Training Runs."""

    def run(
        self, config: TrainingConfig, *, environment: str = "local"
    ) -> ContextManager[RunRecorder]:
        """Open a Training Run and yield its recorder.

        The run is written before the block body starts, so it is visible as
        RUNNING while training is in progress, and closed on the way out.
        """
        ...
