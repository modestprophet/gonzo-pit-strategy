import ctypes
import multiprocessing
import signal
import sys
import traceback
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty
from unittest.mock import patch

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux publication contract"
)

TIMEOUT = 90
JOIN_TIMEOUT = 10
VERSION = "contended-version"
FEATURE_NAMES = ["lap_time_scaled", "tyre_age_scaled"]
CANDIDATES = {
    "alpha": ([[2.0], [-1.0]], [3.0], [[3.0], [3.0], [10.0]]),
    "beta": ([[-3.0], [4.0]], [-2.0], [[-2.0], [3.0], [-10.0]]),
}


def _manifest(candidate):
    import keras

    from gonzo_pit_strategy.training.artifact import ArtifactManifest

    return ArtifactManifest(
        model_name="publication_test",
        model_version=VERSION,
        architecture="dense",
        feature_names=FEATURE_NAMES,
        target_column="finish_position",
        framework_version=keras.__version__,
        dataset_fingerprint=f"dataset-{candidate}",
        description=candidate,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _model(candidate):
    import keras

    model = keras.Sequential([keras.layers.Input(shape=(2,)), keras.layers.Dense(1)])
    kernel, bias, _ = CANDIDATES[candidate]
    model.set_weights(
        [np.array(kernel, dtype="float32"), np.array(bias, dtype="float32")]
    )
    return model


class _AfterRename:
    """Forward the ctypes signature and real syscall, then hold a successful rename."""

    def __init__(self, native, hold):
        object.__setattr__(self, "native", native)
        object.__setattr__(self, "hold", hold)

    def __getattr__(self, name):
        return getattr(self.native, name)

    def __setattr__(self, name, value):
        setattr(self.native, name, value)

    def __call__(self, *args):
        result = self.native(*args)
        if result == 0:
            self.hold()
        return result


def _save_in_process(root, candidate, pause_at, release, messages):
    # Install at the SDK boundary before importing ArtifactStore, including if
    # a future binding caches the native symbol at module import time.
    def hold():
        messages.put(("ready", candidate))
        if not release.wait(TIMEOUT):
            raise TimeoutError(f"{candidate}: parent did not release {pause_at}")

    write_text = Path.write_text

    def write_and_hold(path, *args, **kwargs):
        result = write_text(path, *args, **kwargs)
        if path.name == "manifest.json" and path.parent.parent == root:
            hold()
        return result

    get_symbol = ctypes.CDLL.__getitem__

    def get_symbol_and_hold(library, name):
        native = get_symbol(library, name)
        return _AfterRename(native, hold) if name == "renameat2" else native

    boundary = (
        patch.object(Path, "write_text", write_and_hold)
        if pause_at == "before"
        else patch.object(ctypes.CDLL, "__getitem__", get_symbol_and_hold)
    )
    try:
        with boundary:
            from gonzo_pit_strategy.training.artifact import ArtifactStore

            directory = ArtifactStore(root).save(
                _model(candidate), _manifest(candidate)
            )
        messages.put(("saved", candidate, str(directory)))
    except FileExistsError:
        messages.put(("exists", candidate))
    except BaseException:
        messages.put(("error", candidate, traceback.format_exc()))
        raise


@contextmanager
def _writers(root, candidates, pause_at):
    context = multiprocessing.get_context("spawn")
    release = context.Event()
    messages = context.Queue()
    processes = []
    try:
        for candidate in candidates:
            process = context.Process(
                target=_save_in_process,
                args=(root, candidate, pause_at, release, messages),
                name=f"artifact-writer-{candidate}",
            )
            process.start()
            processes.append(process)
        yield processes, release, messages
    finally:
        for process in processes:
            if process.is_alive():
                process.kill()
        for process in processes:
            process.join(JOIN_TIMEOUT)
        survivors = [process.name for process in processes if process.is_alive()]
        for process in processes:
            if not process.is_alive():
                process.close()
        messages.close()
        messages.join_thread()
        assert not survivors, f"Writers survived SIGKILL: {survivors}"


def _receive(messages):
    try:
        message = messages.get(timeout=TIMEOUT)
    except Empty:
        pytest.fail("Timed out waiting for Artifact writer")
    assert message[0] != "error", message[-1]
    return message


def _assert_missing(store):
    assert not store.path_for(VERSION).exists()
    for loader in (store.load_manifest, store.load):
        with pytest.raises(FileNotFoundError):
            loader(VERSION)


def _assert_artifact(store, candidate):
    model, manifest = store.load(VERSION)
    assert manifest == _manifest(candidate)
    assert store.load_manifest(VERSION) == manifest
    kernel, bias, predictions = CANDIDATES[candidate]
    weights = model.get_weights()
    assert len(weights) == 2
    np.testing.assert_array_equal(weights[0], kernel)
    np.testing.assert_array_equal(weights[1], bias)
    inputs = np.array([[0, 0], [1, 2], [4, 1]], dtype="float32")
    np.testing.assert_allclose(model(inputs, training=False).numpy(), predictions)


def _payload(directory):
    return {
        name: (directory / name).read_bytes()
        for name in ("model.keras", "manifest.json")
    }


def _kill(process):
    process.kill()
    process.join(JOIN_TIMEOUT)
    assert process.exitcode == -signal.SIGKILL


def test_concurrent_saves_publish_exactly_one_complete_artifact(tmp_path):
    from gonzo_pit_strategy.training.artifact import ArtifactStore

    store = ArtifactStore(tmp_path)
    with _writers(tmp_path, ("alpha", "beta"), "before") as (
        processes,
        release,
        messages,
    ):
        ready = [_receive(messages), _receive(messages)]
        assert set(ready) == {("ready", "alpha"), ("ready", "beta")}
        staging = list(tmp_path.glob(".gonzo-stage-*"))
        assert len(staging) == 2
        for directory in staging:
            assert all(_payload(directory).values())
        _assert_missing(store)

        release.set()
        outcomes = [_receive(messages), _receive(messages)]
        assert sorted(outcome[0] for outcome in outcomes) == ["exists", "saved"]
        assert {outcome[1] for outcome in outcomes} == {"alpha", "beta"}
        winner = next(outcome for outcome in outcomes if outcome[0] == "saved")
        assert Path(winner[2]) == store.path_for(VERSION)
        _assert_artifact(store, winner[1])
        for process in processes:
            process.join(JOIN_TIMEOUT)
            assert process.exitcode == 0
        assert list(tmp_path.iterdir()) == [store.path_for(VERSION)]


def test_sigkill_before_publication_leaves_only_unloadable_staging_and_allows_retry(
    tmp_path,
):
    from gonzo_pit_strategy.training.artifact import ArtifactStore

    store = ArtifactStore(tmp_path)
    with _writers(tmp_path, ("alpha",), "before") as (processes, _, messages):
        assert _receive(messages) == ("ready", "alpha")
        _assert_missing(store)
        staging = list(tmp_path.glob(".gonzo-stage-*"))
        assert len(staging) == 1
        orphan = staging[0]
        original = _payload(orphan)
        assert all(original.values())
        expected_manifest = _manifest("alpha")
        assert (
            type(expected_manifest).model_validate_json(original["manifest.json"])
            == expected_manifest
        )

        _kill(processes[0])
        _assert_missing(store)
        assert _payload(orphan) == original
        alias = tmp_path / "orphan-alias"
        alias.symlink_to(orphan, target_is_directory=True)
        try:
            for version in (orphan.name, alias.name):
                for loader in (store.load_manifest, store.load):
                    with pytest.raises(ValueError, match="staging|unpublished"):
                        loader(version)
        finally:
            alias.unlink()

        assert store.save(_model("beta"), _manifest("beta")) == store.path_for(VERSION)
        _assert_artifact(store, "beta")
        assert _payload(orphan) == original
        assert set(tmp_path.iterdir()) == {orphan, store.path_for(VERSION)}


def test_sigkill_after_publication_preserves_artifact_and_rejects_retry(tmp_path):
    from gonzo_pit_strategy.training.artifact import ArtifactStore

    store = ArtifactStore(tmp_path)
    with _writers(tmp_path, ("alpha",), "after") as (processes, _, messages):
        assert _receive(messages) == ("ready", "alpha")
        _assert_artifact(store, "alpha")
        original = _payload(store.path_for(VERSION))

        _kill(processes[0])
        _assert_artifact(store, "alpha")
        assert _payload(store.path_for(VERSION)) == original
        with pytest.raises(FileExistsError):
            store.save(_model("beta"), _manifest("beta"))
        _assert_artifact(store, "alpha")
        assert _payload(store.path_for(VERSION)) == original
        assert list(tmp_path.iterdir()) == [store.path_for(VERSION)]
