"""
Artifact ownership: layout, save, and load of trained model artifacts.

An artifact directory is self-describing: it contains the model file plus an
Artifact Manifest (`manifest.json`) carrying everything needed to rehydrate
the model for inference — most importantly the feature-ordering contract
(`feature_names`) — with zero database calls.  The database keeps a mirror of
the manifest for reporting only (see ADR 0002).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import keras
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)

MODEL_FILENAME = "model.keras"
MANIFEST_FILENAME = "manifest.json"


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
    dataset_fingerprint: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = "Experiment"
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ArtifactStore:
    """Single owner of artifact directory layout under a configured root."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path_for(self, version: str) -> Path:
        return self.root / version

    def save(self, model: keras.Model, manifest: ArtifactManifest) -> Path:
        """Write `<root>/<version>/model.keras` + `manifest.json`; return the dir."""
        artifact_dir = self.path_for(manifest.model_version)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        model.save(artifact_dir / MODEL_FILENAME)
        (artifact_dir / MANIFEST_FILENAME).write_text(
            manifest.model_dump_json(indent=2)
        )
        logger.info(f"Saved artifact to {artifact_dir}")
        return artifact_dir

    def load_manifest(self, version: str) -> ArtifactManifest:
        manifest_path = self.path_for(version) / MANIFEST_FILENAME
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
