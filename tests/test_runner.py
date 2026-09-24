"""The Artifact must be the model the reported metrics describe (ADR 0002).

This used to be asserted indirectly, on the *order* of the Keras callback list:
`EarlyStopping(restore_best_weights=True)` and the artifact-saving callback both
acted in `on_train_end`, so saving first captured the final epoch's weights while
the metrics — measured after the restore — described the best epoch instead. The
ordering assertion was a proxy, because the direct test available at the time
(train, then compare losses) only detects the bug when the best epoch differs
from the last one and passes vacuously otherwise.

`Experiment.run` now evaluates, saves, and records as straight-line code, so the
invariant can be asserted directly and unconditionally: reload the Artifact from
disk and require that it reproduces the evaluated model *exactly*. That holds
whether or not EarlyStopping restored anything, so it cannot pass vacuously.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest

from conftest import StubDataSource
from fakes import InMemoryRunLedger


def _experiment(config, raw_dataset, tmp_path, ledger):
    from gonzo_pit_strategy.config.config import PathsConfig
    from gonzo_pit_strategy.training.artifact import ArtifactStore
    from gonzo_pit_strategy.training.runner import Experiment

    return Experiment(
        config,
        StubDataSource(raw_dataset),
        ArtifactStore(tmp_path / "artifacts"),
        ledger,
        paths=PathsConfig(
            artifacts_root=str(tmp_path / "artifacts"),
            tensorboard_dir=str(tmp_path / "tb"),
        ),
    )


@pytest.fixture
def config():
    pytest.importorskip("keras")
    from gonzo_pit_strategy.training.config import TrainingConfig

    return TrainingConfig(
        target_column="finish_position",
        exclude_columns=["race_id"],
        epochs=2,
        batch_size=8,
        early_stopping_patience=1,
    )


def test_saved_artifact_is_the_evaluated_model(config, raw_dataset, tmp_path, ledger):
    from gonzo_pit_strategy.training.artifact import ArtifactStore
    from gonzo_pit_strategy.training.data import load_training_data

    result = _experiment(config, raw_dataset, tmp_path, ledger).run()

    reloaded, manifest = ArtifactStore(tmp_path / "artifacts").load(
        result.model_version
    )

    # Re-derive the same test split (same config, same seed) and require the
    # artifact on disk to score exactly what the run reported.
    data = load_training_data(config, StubDataSource(raw_dataset))
    reloaded_loss = reloaded.evaluate(data.X_test, data.y_test, verbose=0)[0]

    np.testing.assert_allclose(reloaded_loss, result.test_loss, rtol=1e-5)
    np.testing.assert_allclose(
        manifest.test_metrics["loss"], result.test_loss, rtol=1e-5
    )


def test_manifest_carries_provenance_and_metrics(config, raw_dataset, tmp_path, ledger):
    result = _experiment(config, raw_dataset, tmp_path, ledger).run()
    manifest = ledger.last.manifest

    assert manifest.dataset_name == "fixture_dataset"
    assert manifest.dataset_fingerprint
    assert manifest.test_metrics["loss"] == pytest.approx(result.test_loss)
    # Real metric names, not Keras 3's positional 'compile_metrics' label.
    assert "mae" in manifest.test_metrics
    assert manifest.epochs_completed == ledger.last.epochs_completed
    assert manifest.feature_names == [
        c for c in raw_dataset.columns if c not in ("finish_position", "race_id")
    ]


def test_completed_run_is_recorded_once_with_the_artifact_path(
    config, raw_dataset, tmp_path, ledger
):
    result = _experiment(config, raw_dataset, tmp_path, ledger).run()

    model_type, identity = result.model_version.rsplit("_", 1)
    assert model_type == config.model.type
    assert len(result.model_version) <= 50
    parsed_identity = UUID(hex=identity)
    assert parsed_identity.version == 4
    assert identity == parsed_identity.hex

    assert len(ledger.runs) == 1, "ADR 0002 §3: one record, written at train end"
    record = ledger.last
    assert record.status == "COMPLETED"
    assert record.artifact_path == result.artifact_path
    assert record.provenance.name == "fixture_dataset"
    assert record.provenance.record_count == len(raw_dataset)
    per_epoch = {m.epoch for m in record.metrics if m.split != "TEST"}
    assert per_epoch == set(
        range(record.epochs_completed)
    ), "epoch metrics stream as training proceeds"


def test_build_failure_records_nothing(
    config, raw_dataset, tmp_path, ledger, monkeypatch
):
    """Failing before the ledger block opens leaves no row at all."""
    from gonzo_pit_strategy.training import runner as runner_mod

    def exploding_build_model(*_a, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(runner_mod, "build_model", exploding_build_model)

    with pytest.raises(RuntimeError, match="boom"):
        _experiment(config, raw_dataset, tmp_path, ledger).run()

    assert ledger.runs == []


def test_run_is_closed_as_failed_when_fit_raises(
    config, raw_dataset, tmp_path, ledger, monkeypatch
):
    """A run that dies mid-training must not be left at RUNNING.

    The previous design opened the run in `on_train_begin` and closed it in
    `on_train_end`, so anything raising in between left the row RUNNING forever
    — and `Sweep.run` catches per-experiment exceptions and continues, so a
    failing sweep silently accumulated them.
    """
    from gonzo_pit_strategy.training import runner as runner_mod

    real_build_model = runner_mod.build_model

    def build_model_that_fails_to_fit(*a, **kw):
        model = real_build_model(*a, **kw)

        def fit(*_a, **_kw):
            raise RuntimeError("boom")

        model.fit = fit
        return model

    monkeypatch.setattr(runner_mod, "build_model", build_model_that_fails_to_fit)

    with pytest.raises(RuntimeError, match="boom"):
        _experiment(config, raw_dataset, tmp_path, ledger).run()

    assert len(ledger.runs) == 1
    assert ledger.last.status == "FAILED"
    assert ledger.last.manifest is None, "no model row for a run that never finished"


def test_save_failure_marks_run_failed_without_publishing_artifact(
    config, raw_dataset, tmp_path, ledger, monkeypatch
):
    import keras

    real_save = keras.Model.save

    def failing_save(model, filepath, *args, **kwargs):
        real_save(model, filepath, *args, **kwargs)
        raise OSError("Keras save failed")

    monkeypatch.setattr(keras.Model, "save", failing_save)

    with pytest.raises(OSError, match="Keras save failed"):
        _experiment(config, raw_dataset, tmp_path, ledger).run()

    assert len(ledger.runs) == 1
    assert ledger.last.status == "FAILED"
    assert ledger.last.metrics
    assert ledger.last.manifest is None
    assert ledger.last.artifact_path is None
    assert list((tmp_path / "artifacts").iterdir()) == []


def test_mirror_completion_failure_leaves_saved_artifact_loadable(
    config, raw_dataset, tmp_path, ledger
):
    from gonzo_pit_strategy.training.artifact import ArtifactStore
    from gonzo_pit_strategy.training.data import load_training_data

    class FailingMirrorLedger:
        @contextmanager
        def run(self, config, *, environment="local"):
            with ledger.run(config, environment=environment) as recorder:
                def fail_completion(*args, **kwargs):
                    raise RuntimeError("mirror completion failed")

                yield SimpleNamespace(
                    run_id=recorder.run_id,
                    model_id=recorder.model_id,
                    record_epoch=recorder.record_epoch,
                    complete=fail_completion,
                )

    with pytest.raises(RuntimeError, match="mirror completion failed"):
        _experiment(config, raw_dataset, tmp_path, FailingMirrorLedger()).run()

    assert len(ledger.runs) == 1
    assert ledger.last.status == "FAILED"
    assert ledger.last.metrics
    assert ledger.last.manifest is None
    assert ledger.last.artifact_path is None
    (artifact_dir,) = (tmp_path / "artifacts").iterdir()
    reloaded, manifest = ArtifactStore(tmp_path / "artifacts").load(artifact_dir.name)
    assert manifest.model_version == artifact_dir.name
    assert manifest.training_config == config.model_dump(mode="json")
    data = load_training_data(config, StubDataSource(raw_dataset))
    evaluation = reloaded.evaluate(
        data.X_test, data.y_test, verbose=0, return_dict=True
    )
    assert evaluation == pytest.approx(manifest.test_metrics, rel=1e-5)


def test_sweep_records_one_run_per_experiment(config, raw_dataset, tmp_path):
    from gonzo_pit_strategy.config.config import PathsConfig
    from gonzo_pit_strategy.training.artifact import ArtifactStore
    from gonzo_pit_strategy.training.data import load_training_data
    from gonzo_pit_strategy.training.sweep import Sweep, SweepConfig

    ledger = InMemoryRunLedger()
    sweep = Sweep(
        SweepConfig(
            base_config=config,
            parameters={"model.hidden_layers": [[4], [8]]},
        ),
        StubDataSource(raw_dataset),
        ArtifactStore(tmp_path / "artifacts"),
        ledger,
        paths=PathsConfig(
            artifacts_root=str(tmp_path / "artifacts"),
            tensorboard_dir=str(tmp_path / "tb"),
        ),
    )

    results = list(sweep.run())

    assert [it.error for it in results] == [None, None]
    assert len(ledger.runs) == 2
    assert {r.status for r in ledger.runs} == {"COMPLETED"}
    completed = [it.result for it in results if it.result is not None]
    assert len(completed) == 2
    assert len({result.model_version for result in completed}) == 2
    assert len({result.artifact_path for result in completed}) == 2

    store = ArtifactStore(tmp_path / "artifacts")
    for iteration, record in zip(results, ledger.runs, strict=True):
        result = iteration.result
        assert result is not None
        reloaded, manifest = store.load(result.model_version)
        assert manifest.model_version == result.model_version
        assert manifest.training_config == iteration.config.model_dump(mode="json")
        assert record.config == iteration.config
        assert record.artifact_path == result.artifact_path
        assert record.manifest == manifest

        recorded_metrics = {
            metric.name: metric.value
            for metric in record.metrics
            if metric.split == "TEST"
        }
        assert recorded_metrics == pytest.approx(
            {"loss": result.test_loss, **result.test_metrics}
        )
        assert manifest.test_metrics == pytest.approx(recorded_metrics)
        data = load_training_data(iteration.config, StubDataSource(raw_dataset))
        evaluation = reloaded.evaluate(
            data.X_test, data.y_test, verbose=0, return_dict=True
        )
        assert evaluation == pytest.approx(recorded_metrics, rel=1e-5)
