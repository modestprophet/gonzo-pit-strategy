"""One contract, both Run Ledger adapters.

`RunLedger` has two adapters — `db/run_ledger.py` against Postgres and
`tests/fakes.py` in memory — and ADR 0002 records the risk they carry: a fake
that accepts what Postgres would reject, or records what Postgres would not,
lets a green suite assert things that are false in production.

Every test here runs twice, once per adapter. The Protocol in
`training/ledger.py` is the arbiter: where the two disagree, the adapter that
departs from its docstrings is the one that is wrong.

The tests are written against the interface only. Reading back what an adapter
stored goes through a probe (`tests/probes.py`), never through `RunLedger`.
"""

import pytest

from gonzo_pit_strategy.training.artifact import ArtifactManifest
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import DatasetProvenance

from probes import InMemoryProbe, PostgresProbe

PROVENANCE = DatasetProvenance(
    name="contract_dataset",
    fingerprint="abcdef0123456789fedcba9876543210",
    record_count=50,
    feature_count=4,
)


def _config() -> TrainingConfig:
    return TrainingConfig(
        target_column="finish_position",
        exclude_columns=["race_id"],
        epochs=2,
        batch_size=8,
        early_stopping_patience=1,
    )


def _manifest(version: str = "contract_v1", **overrides) -> ArtifactManifest:
    fields = dict(
        model_name="contract_model",
        model_version=version,
        architecture="dense",
        feature_names=["a", "b", "c", "d"],
        target_column="finish_position",
        framework_version="3.0.0",
        dataset_name=PROVENANCE.name,
        dataset_fingerprint=PROVENANCE.fingerprint,
        epochs_completed=2,
    )
    fields.update(overrides)
    return ArtifactManifest(**fields)


@pytest.fixture(params=["memory", "postgres"])
def ledger_and_probe(request):
    """Yield (ledger, probe) for each adapter behind the Run Ledger seam."""
    if request.param == "memory":
        from fakes import InMemoryRunLedger

        ledger = InMemoryRunLedger()
        return ledger, InMemoryProbe(ledger)

    from gonzo_pit_strategy.db.run_ledger import PostgresRunLedger

    pool = request.getfixturevalue("clean_postgres")
    return PostgresRunLedger(pool), PostgresProbe(pool)


# ---------------------------------------------------------------------------
# Lifecycle: a Training Run always reaches a terminal status
# ---------------------------------------------------------------------------


def test_run_id_is_available_inside_the_block(ledger_and_probe):
    """The row exists before the body runs, so logs can be correlated while
    training is still in progress (ledger.RunRecorder docstring)."""
    ledger, _ = ledger_and_probe
    with ledger.run(_config()) as run:
        assert run.run_id is not None


def test_model_id_is_none_until_complete(ledger_and_probe):
    """ADR 0002 §3 rejects placeholder rows: there is deliberately no model
    row before `complete`."""
    ledger, probe = ledger_and_probe
    with ledger.run(_config()) as run:
        assert run.model_id is None
        run_id = run.run_id
        run.complete(_manifest(), "/tmp/artifacts/contract_v1", PROVENANCE, epochs_completed=2)
        assert run.model_id is not None

    assert probe.model_id(run_id) is not None


def test_complete_closes_the_run(ledger_and_probe):
    ledger, probe = ledger_and_probe
    with ledger.run(_config()) as run:
        run_id = run.run_id
        run.complete(_manifest(), "/tmp/artifacts/contract_v1", PROVENANCE, epochs_completed=2)

    assert probe.status(run_id) == "COMPLETED"


def test_leaving_the_block_without_completing_marks_failed(ledger_and_probe):
    """Not an exception, but not a finished run either — RUNNING would be a lie."""
    ledger, probe = ledger_and_probe
    with ledger.run(_config()) as run:
        run_id = run.run_id

    assert probe.status(run_id) == "FAILED"


def test_exception_marks_failed_and_propagates(ledger_and_probe):
    """A crashed Sweep iteration must not leave a row stuck at RUNNING."""
    ledger, probe = ledger_and_probe
    run_id = None

    with pytest.raises(RuntimeError, match="training blew up"):
        with ledger.run(_config()) as run:
            run_id = run.run_id
            raise RuntimeError("training blew up")

    assert probe.status(run_id) == "FAILED"


# ---------------------------------------------------------------------------
# Metric recording
# ---------------------------------------------------------------------------


def test_val_prefix_becomes_the_validation_split(ledger_and_probe):
    """`record_epoch` takes Keras' raw logs dict: bare names are training
    metrics, `val_`-prefixed ones are validation (ledger.RunRecorder). The
    prefix is meaning, not part of the name — it must land in the split."""
    ledger, probe = ledger_and_probe
    with ledger.run(_config()) as run:
        run_id = run.run_id
        run.record_epoch(0, {"loss": 0.5, "val_loss": 0.7})

    recorded = {(m.name, m.split): m.value for m in probe.metrics(run_id)}
    assert recorded == {("loss", "TRAIN"): 0.5, ("loss", "VALIDATION"): 0.7}


def test_epochs_are_recorded_as_they_complete(ledger_and_probe):
    """Written per epoch rather than buffered, so a run that crashes still
    leaves the metrics that led up to the crash."""
    ledger, probe = ledger_and_probe
    with ledger.run(_config()) as run:
        run_id = run.run_id
        run.record_epoch(0, {"loss": 0.9})
        run.record_epoch(1, {"loss": 0.4})

    assert {m.epoch for m in probe.metrics(run_id)} == {0, 1}


def test_empty_logs_record_nothing(ledger_and_probe):
    ledger, probe = ledger_and_probe
    with ledger.run(_config()) as run:
        run_id = run.run_id
        run.record_epoch(0, {})

    assert probe.metrics(run_id) == []


def test_test_metrics_are_recorded_on_complete(ledger_and_probe):
    """"The manifest's `test_metrics` are also recorded as TEST-split metrics
    for the run" — `RunRecorder.complete`."""
    ledger, probe = ledger_and_probe
    manifest = _manifest(test_metrics={"loss": 0.31, "mae": 0.22})

    with ledger.run(_config()) as run:
        run_id = run.run_id
        run.complete(manifest, "/tmp/artifacts/contract_v1", PROVENANCE, epochs_completed=2)

    test_rows = {m.name: m.value for m in probe.metrics(run_id) if m.split == "TEST"}
    assert test_rows == {"loss": 0.31, "mae": 0.22}


# ---------------------------------------------------------------------------
# Dataset Provenance
# ---------------------------------------------------------------------------


def test_same_fingerprint_reuses_one_dataset_version(ledger_and_probe):
    """`dataset_versions` is unique on (dataset_name, version), and version is
    the fingerprint's leading 16 chars — so re-training on unchanged data
    reuses the row rather than duplicating it. On Postgres, getting this wrong
    is a constraint violation; the in-memory adapter has to model it too or the
    suite cannot catch the mistake before it reaches a real database."""
    ledger, probe = ledger_and_probe

    for version in ("contract_v1", "contract_v2"):
        with ledger.run(_config()) as run:
            run.complete(
                _manifest(version), f"/tmp/artifacts/{version}", PROVENANCE, epochs_completed=2
            )

    assert probe.dataset_versions() == [(PROVENANCE.name, PROVENANCE.fingerprint[:16])]


def test_different_fingerprints_get_separate_dataset_versions(ledger_and_probe):
    ledger, probe = ledger_and_probe
    other = DatasetProvenance(
        name=PROVENANCE.name,
        fingerprint="0000111122223333444455556666777788",
        record_count=60,
        feature_count=4,
    )

    for version, provenance in (("contract_v1", PROVENANCE), ("contract_v2", other)):
        with ledger.run(_config()) as run:
            run.complete(
                _manifest(version), f"/tmp/artifacts/{version}", provenance, epochs_completed=2
            )

    assert probe.dataset_versions() == [
        (PROVENANCE.name, PROVENANCE.fingerprint[:16]),
        (other.name, other.fingerprint[:16]),
    ]
