import ctypes
import errno
from pathlib import Path

import numpy as np
import pytest

from conftest import FEATURE_NAMES
from gonzo_pit_strategy.training.artifact import ArtifactManifest, ArtifactStore


def make_manifest(version="dense_test"):
    return ArtifactManifest(
        model_name="f1_pit_strategy_model",
        model_version=version,
        architecture="dense",
        feature_names=FEATURE_NAMES,
        target_column="finish_position",
        framework_version="test",
        dataset_fingerprint="abc123",
        tags=["test"],
    )


def test_save_load_round_trip(tmp_path, tiny_model):
    store = ArtifactStore(tmp_path)
    manifest = make_manifest()
    artifact_dir = store.save(tiny_model, manifest)

    assert (artifact_dir / "model.keras").exists()
    assert (artifact_dir / "manifest.json").exists()

    model, loaded = store.load("dense_test")
    assert loaded.feature_names == FEATURE_NAMES
    assert loaded.target_column == "finish_position"
    assert loaded.dataset_fingerprint == "abc123"

    x = np.random.default_rng(1).random((3, len(FEATURE_NAMES)))
    np.testing.assert_allclose(
        model.predict(x, verbose=0), tiny_model.predict(x, verbose=0), rtol=1e-5
    )


@pytest.mark.parametrize("replace_model", [False, True])
def test_save_rejects_occupied_version_without_changing_artifact(
    tmp_path, tiny_model, replace_model
):
    store = ArtifactStore(tmp_path)
    manifest = make_manifest()
    store.save(tiny_model, manifest)
    original_weights = tiny_model.get_weights()
    replacement = manifest
    if replace_model:
        tiny_model.set_weights([np.ones_like(w) for w in original_weights])
        replacement = manifest.model_copy(update={"description": "replacement"})

    with pytest.raises(FileExistsError):
        store.save(tiny_model, replacement)

    reloaded, saved_manifest = store.load(manifest.model_version)
    assert saved_manifest == manifest
    for actual, expected in zip(reloaded.get_weights(), original_weights):
        np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize(
    "entry", ["empty-directory", "file", "symlink", "dangling-symlink"]
)
def test_save_rejects_every_occupied_destination(tmp_path, tiny_model, entry):
    store = ArtifactStore(tmp_path)
    destination = store.path_for("v1")
    target = tmp_path / "existing"
    if entry == "empty-directory":
        destination.mkdir()
    elif entry == "file":
        destination.write_text("existing content")
    else:
        if entry == "symlink":
            target.mkdir()
        destination.symlink_to(target, target_is_directory=True)
    original = destination.lstat()

    with pytest.raises(FileExistsError):
        store.save(tiny_model, make_manifest("v1"))

    assert destination.lstat() == original
    if entry == "empty-directory":
        assert list(destination.iterdir()) == []
    elif entry == "file":
        assert destination.read_text() == "existing content"
    else:
        assert destination.readlink() == target
        assert target.exists() == (entry == "symlink")


@pytest.mark.parametrize("failure_at", ["model", "manifest"])
@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_failed_save_cleans_up_without_publishing(
    tmp_path, tiny_model, monkeypatch, failure_at, failure
):
    store = ArtifactStore(tmp_path)
    manifest = make_manifest()
    if failure_at == "model":
        save_model = tiny_model.save

        def fail_save(path):
            save_model(path)
            raise failure("interrupted write")

        monkeypatch.setattr(tiny_model, "save", fail_save)
    else:
        write_text = Path.write_text

        def fail_write(path, data, *args, **kwargs):
            if path.name == "manifest.json":
                write_text(path, data[:10])
                raise failure("interrupted write")
            return write_text(path, data, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_write)

    with pytest.raises(failure, match="interrupted write"):
        store.save(tiny_model, manifest)

    assert list(tmp_path.iterdir()) == []
    with pytest.raises(FileNotFoundError):
        store.load(manifest.model_version)


def test_save_preserves_destination_created_during_serialization(
    tmp_path, tiny_model, monkeypatch
):
    store = ArtifactStore(tmp_path)
    manifest = make_manifest()
    destination = store.path_for(manifest.model_version)
    save_model = tiny_model.save

    def competing_save(path):
        save_model(path)
        destination.mkdir()

    monkeypatch.setattr(tiny_model, "save", competing_save)

    with pytest.raises(FileExistsError):
        store.save(tiny_model, manifest)

    assert list(destination.iterdir()) == []
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize(
    "version", ["", ".", "..", "../outside", "/absolute", "a/b", "a\0b"]
)
def test_store_rejects_versions_that_are_not_single_directory_names(tmp_path, version):
    with pytest.raises(ValueError, match="version"):
        ArtifactStore(tmp_path).path_for(version)


@pytest.mark.parametrize("access", ["direct", "alias", "root", "payload"])
def test_loaders_reject_complete_but_unpublished_artifacts(tmp_path, tiny_model, access):
    staging = tmp_path / ".gonzo-stage-abandoned"
    staging.mkdir()
    directory = staging / "v1" if access == "root" else staging
    directory.mkdir(exist_ok=True)
    tiny_model.save(directory / "model.keras")
    (directory / "manifest.json").write_text(make_manifest("v1").model_dump_json())
    store = ArtifactStore(tmp_path)
    version = staging.name
    if access == "alias":
        (tmp_path / "alias").symlink_to(staging, target_is_directory=True)
        version = "alias"
    elif access == "root":
        store = ArtifactStore(staging)
        version = "v1"
    elif access == "payload":
        (tmp_path / "v1").mkdir()
        for filename in ("model.keras", "manifest.json"):
            (tmp_path / "v1" / filename).symlink_to(staging / filename)
        version = "v1"

    with pytest.raises(ValueError, match="staging|unpublished"):
        store.load_manifest(version)
    with pytest.raises(ValueError, match="staging|unpublished"):
        store.load(version)


def test_load_rejects_unpublished_model_even_with_a_regular_manifest(tmp_path, tiny_model):
    staging = tmp_path / ".gonzo-stage-abandoned"
    staging.mkdir()
    tiny_model.save(staging / "model.keras")
    directory = tmp_path / "v1"
    directory.mkdir()
    manifest = make_manifest("v1")
    (directory / "manifest.json").write_text(manifest.model_dump_json())
    (directory / "model.keras").symlink_to(staging / "model.keras")
    store = ArtifactStore(tmp_path)

    assert store.load_manifest("v1") == manifest
    with pytest.raises(ValueError, match="staging|unpublished"):
        store.load("v1")


@pytest.mark.parametrize("error", [errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.EIO])
def test_native_publication_failure_cleans_staging_without_fallback(
    tmp_path, tiny_model, monkeypatch, error
):
    get_symbol = ctypes.CDLL.__getitem__

    class FailedRename:
        def __call__(self, *args):
            ctypes.set_errno(error)
            return -1

    def lookup(library, name):
        return FailedRename() if name == "renameat2" else get_symbol(library, name)

    monkeypatch.setattr(ctypes.CDLL, "__getitem__", lookup)
    store = ArtifactStore(tmp_path)
    with pytest.raises(OSError) as caught:
        store.save(tiny_model, make_manifest())
    assert caught.value.errno == error
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(FileNotFoundError):
        store.load("dense_test")


def test_legacy_artifacts_load_without_native_publication_support(
    tmp_path, tiny_model, monkeypatch
):
    version = "dense_20260729_153000"
    directory = tmp_path / version
    directory.mkdir()
    manifest = make_manifest(version)
    tiny_model.save(directory / "model.keras")
    (directory / "manifest.json").write_text(manifest.model_dump_json())
    (tmp_path / "legacy-alias").symlink_to(directory, target_is_directory=True)
    get_symbol = ctypes.CDLL.__getitem__

    def missing_symbol(library, name):
        if name == "renameat2":
            raise AttributeError(name)
        return get_symbol(library, name)

    monkeypatch.setattr(ctypes.CDLL, "__getitem__", missing_symbol)
    store = ArtifactStore(tmp_path)
    for name in (version, "legacy-alias"):
        model, loaded = store.load(name)
        assert loaded == manifest
        for actual, expected in zip(model.get_weights(), tiny_model.get_weights()):
            np.testing.assert_array_equal(actual, expected)

    with pytest.raises(OSError) as caught:
        store.save(tiny_model, make_manifest("new_version"))
    assert caught.value.errno == errno.ENOTSUP
    assert {path.name for path in tmp_path.iterdir()} == {version, "legacy-alias"}


def test_load_missing_manifest_raises(tmp_path):
    store = ArtifactStore(tmp_path)
    (tmp_path / "orphan").mkdir()
    with pytest.raises(FileNotFoundError, match="manifest"):
        store.load("orphan")


def test_delete(tmp_path, tiny_model):
    store = ArtifactStore(tmp_path)
    store.save(tiny_model, make_manifest("v1"))
    assert store.delete("v1") is True
    assert not store.path_for("v1").exists()
    assert store.delete("v1") is False
