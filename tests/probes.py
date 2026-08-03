"""Read-back probes for Run Ledger adapters, used by the contract suite.

`RunLedger` deliberately exposes only `run_id` and `model_id` — a caller has no
business reading back what was written. The contract tests do, so each adapter
gets a probe here.

These live in `tests/` and are not part of the Protocol. A deep module can have
internal seams used by its own tests without exposing them at its interface
(DEEPENING.md); making `RunLedger` readable just to satisfy the test suite would
widen the interface for no caller's benefit.
"""

from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple

from gonzo_pit_strategy.db.base import db_session
from gonzo_pit_strategy.db.models.dataset_versions import DatasetVersion
from gonzo_pit_strategy.db.models.training_metrics import TrainingMetric
from gonzo_pit_strategy.db.models.training_runs import TrainingRun


@dataclass(frozen=True)
class MetricRow:
    """One recorded metric, normalised across adapters.

    `name` is the metric name with the `val_` prefix already stripped; the
    prefix's meaning lives in `split` instead. See `training.ledger.split_metric`.
    """

    epoch: int
    name: str
    value: float
    split: str


class LedgerProbe(Protocol):
    """Reads back what an adapter stored for a Training Run."""

    def status(self, run_id: int) -> Optional[str]: ...

    def model_id(self, run_id: int) -> Optional[int]: ...

    def metrics(self, run_id: int) -> List[MetricRow]: ...

    def dataset_versions(self) -> List[Tuple[str, str]]:
        """Every (dataset_name, version) pair on record, in insertion order."""
        ...


class InMemoryProbe:
    def __init__(self, ledger):
        self._ledger = ledger

    def _record(self, run_id: int):
        for record in self._ledger.runs:
            if record.run_id == run_id:
                return record
        return None

    def status(self, run_id: int) -> Optional[str]:
        record = self._record(run_id)
        return record.status if record else None

    def model_id(self, run_id: int) -> Optional[int]:
        record = self._record(run_id)
        return record.model_id if record else None

    def metrics(self, run_id: int) -> List[MetricRow]:
        record = self._record(run_id)
        if record is None:
            return []
        return [
            MetricRow(epoch=m.epoch, name=m.name, value=m.value, split=m.split)
            for m in record.metrics
        ]

    def dataset_versions(self) -> List[Tuple[str, str]]:
        return list(self._ledger.dataset_versions)


class PostgresProbe:
    def __init__(self, pool):
        self._pool = pool

    def status(self, run_id: int) -> Optional[str]:
        with db_session(self._pool) as session:
            run = session.query(TrainingRun).filter_by(run_id=run_id).first()
            return run.status if run else None

    def model_id(self, run_id: int) -> Optional[int]:
        with db_session(self._pool) as session:
            run = session.query(TrainingRun).filter_by(run_id=run_id).first()
            return run.model_id if run else None

    def metrics(self, run_id: int) -> List[MetricRow]:
        with db_session(self._pool) as session:
            rows = (
                session.query(TrainingMetric)
                .filter_by(run_id=run_id)
                .order_by(TrainingMetric.metric_id)
                .all()
            )
            return [
                MetricRow(
                    epoch=r.epoch,
                    name=r.metric_name,
                    value=r.metric_value,
                    split=r.split_type,
                )
                for r in rows
            ]

    def dataset_versions(self) -> List[Tuple[str, str]]:
        with db_session(self._pool) as session:
            rows = (
                session.query(DatasetVersion)
                .order_by(DatasetVersion.dataset_version_id)
                .all()
            )
            return [(r.dataset_name, r.version) for r in rows]
