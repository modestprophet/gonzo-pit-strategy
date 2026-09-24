"""
Artifact ownership: layout, save, and load of trained model artifacts.

An artifact directory is self-describing: it contains the model file plus an
Artifact Manifest (`manifest.json`) carrying everything needed to rehydrate
the model for inference — most importantly the feature-ordering contract
(`feature_names`) — with zero database calls.  The database keeps a mirror of
the manifest for reporting only (see ADR 0002).
"""

import ctypes
import errno
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Tuple

import keras
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODEL_FILENAME = "model.keras"
MANIFEST_FILENAME = "manifest.json"
_STAGING_PREFIX = ".gonzo-stage-"
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


def _rename_noreplace(source: Path, destination: Path) -> None:
    try:
        rename = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise OSError(
            errno.ENOTSUP, "Atomic Artifact publication requires Linux renameat2"
        ) from exc
    rename.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint
    ]
    rename.restype = ctypes.c_int
    if rename(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    ) != 0:
        error = ctypes.get_errno()
        raise OSError(
            error, f"Artifact publication failed: {os.strerror(error)}", destination
        )


def _reject_staging_path(path: Path) -> None:
    if any(part.startswith(_STAGING_PREFIX) for part in path.resolve().parts):
        raise ValueError("Cannot access unpublished Artifact staging")


class ArtifactManifest(BaseModel):
    """Everything inference needs to rehydrate a model, persisted next to it."""

    model_name: str
    model_version: str
    architecture: str
    feature_names: List[str] = Field(
        description="Feature columns in training order — the model's input contract."
    )
    target_column: str
    training_config: Dict[str, Any] = Field(default_factory=dict)
    framework_version: str
    dataset_name: Optional[str] = None
    dataset_fingerprint: Optional[str] = None
    epochs_completed: Optional[int] = None
    test_metrics: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Held-out metrics measured on this exact model, including loss. "
            "Published with the evaluated model under ADR 0002."
        ),
    )
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "Experiment"
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ArtifactStore:
    """Single owner of artifact directory layout under a configured root."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, version: str) -> Path:
        if version in ("", ".", "..") or "/" in version or "\0" in version:
            raise ValueError("Artifact version must be a single directory name")
        if version.startswith(_STAGING_PREFIX):
            raise ValueError("Artifact version uses the reserved staging prefix")
        _reject_staging_path(self.root)
        return self.root / version

    def save(self, model: keras.Model, manifest: ArtifactManifest) -> Path:
        """Publish a complete Artifact without replacing an occupied version."""
        artifact_dir = self.path_for(manifest.model_version)
        if os.path.lexists(artifact_dir):
            raise FileExistsError(
                errno.EEXIST, "Artifact version already exists", artifact_dir
            )
        self.root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=_STAGING_PREFIX, dir=self.root) as staging_dir:
            staging = Path(staging_dir)
            model.save(staging / MODEL_FILENAME)
            (staging / MANIFEST_FILENAME).write_text(manifest.model_dump_json(indent=2))
            _rename_noreplace(staging, artifact_dir)
        logger.info(f"Saved artifact to {artifact_dir}")
        return artifact_dir

    def load_manifest(self, version: str) -> ArtifactManifest:
        manifest_path = self.path_for(version) / MANIFEST_FILENAME
        _reject_staging_path(manifest_path)
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"Artifact manifest not found: {manifest_path}. "
                "Artifacts saved before ADR 0002 lack a manifest and cannot be rehydrated."
            )
        return ArtifactManifest(**json.loads(manifest_path.read_text()))

    def load(self, version: str) -> Tuple[keras.Model, ArtifactManifest]:
        """Rehydrate a model and its manifest from disk alone."""
        manifest = self.load_manifest(version)
        model_path = self.path_for(version) / MODEL_FILENAME
        _reject_staging_path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        model = keras.models.load_model(model_path)
        logger.info(f"Rehydrated model {manifest.model_name} v{version} from {model_path}")
        return model, manifest

    def delete(self, version: str) -> bool:
        artifact_dir = self.path_for(version)
        if not artifact_dir.exists():
            return False
        import shutil

        shutil.rmtree(artifact_dir)
        return True
