import numpy as np
import pytest

from gonzo_pit_strategy.training.artifact import ArtifactManifest, ArtifactStore

from conftest import FEATURE_NAMES


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
