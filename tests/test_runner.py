"""The Artifact must be the model the reported metrics describe.

`EarlyStopping(restore_best_weights=True)` and `GonzoExperimentCallback` both act
in `on_train_end`, and Keras invokes callbacks in list order. If the artifact is
saved first it captures the *final* epoch's weights, while the test metrics —
measured after the restore — describe the best epoch instead. Nothing downstream
notices: the artifact loads fine and the numbers look plausible.

This is asserted on the callback *order* rather than on training dynamics. A test
that trains and compares losses only detects the bug when the best epoch differs
from the last one, which depends on the fixture's noise and silently passes when
val_loss happens to improve monotonically.
"""

import contextlib

import pytest

from tests.conftest import StubDataSource


class _FakeQuery:
    def __init__(self, obj):
        self._obj = obj

    def filter_by(self, **_kw):
        return self

    def distinct(self):
        return self

    def first(self):
        return None

    def one(self):
        return self._obj

    def count(self):
        return 0


class _FakeSession:
    """Just enough of a SQLAlchemy session for the reporting-mirror writes."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added.extend(objs)

    def flush(self):
        for obj in self.added:
            for pk in ("run_id", "dataset_version_id"):
                if hasattr(obj, pk) and getattr(obj, pk) is None:
                    setattr(obj, pk, 1)

    def query(self, _entity):
        return _FakeQuery(self.added[0] if self.added else None)


@pytest.fixture
def stub_db(monkeypatch):
    """Neutralize the DB reporting mirror; this test is about callback wiring."""
    session = _FakeSession()

    @contextlib.contextmanager
    def _noop_session(_pool):
        yield session

    monkeypatch.setattr("gonzo_pit_strategy.training.callbacks.db_session", _noop_session)

    class _Repo:
        def record_model(self, *_a, **_kw):
            return 1

    monkeypatch.setattr(
        "gonzo_pit_strategy.training.runner.ModelRepository", lambda *a, **k: _Repo()
    )


def test_early_stopping_restores_before_artifact_is_saved(
    stub_db, raw_dataset, tmp_path, monkeypatch
):
    pytest.importorskip("keras")
    from keras.callbacks import EarlyStopping

    from gonzo_pit_strategy.config.config import PathsConfig
    from gonzo_pit_strategy.training import runner as runner_mod
    from gonzo_pit_strategy.training.callbacks import GonzoExperimentCallback
    from gonzo_pit_strategy.training.config import TrainingConfig

    captured = {}
    real_build_model = runner_mod.build_model

    def spying_build_model(*args, **kwargs):
        model = real_build_model(*args, **kwargs)
        real_fit = model.fit

        def fit(*a, **kw):
            captured["callbacks"] = list(kw.get("callbacks") or [])
            return real_fit(*a, **kw)

        model.fit = fit
        return model

    monkeypatch.setattr(runner_mod, "build_model", spying_build_model)

    paths = PathsConfig(
        artifacts_root=str(tmp_path / "artifacts"),
        tensorboard_dir=str(tmp_path / "tb"),
    )
    config = TrainingConfig(
        target_column="finish_position",
        exclude_columns=["race_id"],
        epochs=1,
        batch_size=8,
        early_stopping_patience=1,
    )

    runner_mod.Experiment(
        config, StubDataSource(raw_dataset), db_pool=None, paths=paths
    ).run()

    types = [type(cb) for cb in captured["callbacks"]]
    assert EarlyStopping in types, "EarlyStopping was not wired in"
    assert GonzoExperimentCallback in types, "GonzoExperimentCallback was not wired in"
    assert types.index(EarlyStopping) < types.index(GonzoExperimentCallback), (
        "GonzoExperimentCallback saves the Artifact in on_train_end and must run "
        "after EarlyStopping restores the best weights; Keras calls callbacks in "
        f"list order and this order is {[t.__name__ for t in types]}"
    )
