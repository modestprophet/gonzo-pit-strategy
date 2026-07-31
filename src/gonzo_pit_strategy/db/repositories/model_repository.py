"""
Repository for the Model Metadata reporting mirror.

Disk artifacts are owned by `gonzo_pit_strategy.training.artifact.ArtifactStore`
(ADR 0002). This repository only mirrors the Artifact Manifest into the
relational database for reporting — it never touches the filesystem and is
never consulted for inference rehydration.
"""

from typing import Optional, List

from sqlalchemy.orm import Session

from gonzo_pit_strategy.db.models.model_metadata import ModelMetadata
from gonzo_pit_strategy.training.artifact import ArtifactManifest
import logging

logger = logging.getLogger(__name__)


class ModelRepository:
    """Repository for model metadata reporting queries and writes."""

    def record_model(
        self,
        manifest: ArtifactManifest,
        artifact_path: str,
        session: Session,
        config_source_path: Optional[str] = None,
    ) -> int:
        """Mirror an Artifact Manifest into the database, once, at train end."""
        model_metadata = ModelMetadata(
            name=manifest.model_name,
            version=manifest.model_version,
            description=manifest.description or "",
            created_at=manifest.created_at,
            created_by=manifest.created_by,
            architecture=manifest.architecture,
            framework_version=manifest.framework_version,
            tags=manifest.tags,
            configuration=manifest.model_dump(mode="json"),
            config_source_path=config_source_path or "",
            artifact_path=artifact_path,
        )
        session.add(model_metadata)
        session.flush()
        return model_metadata.model_id

    def get_model_metadata(self, model_id: int, session: Session) -> Optional[ModelMetadata]:
        return session.query(ModelMetadata).filter_by(model_id=model_id).first()

    def get_model_metadata_by_version(
        self, version: str, session: Session, name: Optional[str] = None
    ) -> Optional[ModelMetadata]:
        query = session.query(ModelMetadata).filter_by(version=version)
        if name:
            query = query.filter_by(name=name)
        return query.first()

    def list_models(
        self,
        session: Session,
        architecture: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ModelMetadata]:
        query = session.query(ModelMetadata)
        if architecture:
            query = query.filter_by(architecture=architecture)
        if tags:
            for tag in tags:
                query = query.filter(ModelMetadata.tags.contains([tag]))
        return query.order_by(ModelMetadata.created_at.desc()).all()

    def delete_model_record(
        self, version: str, session: Session, name: Optional[str] = None
    ) -> bool:
        """Delete the reporting row only; disk cleanup is ArtifactStore.delete."""
        metadata = self.get_model_metadata_by_version(version, session, name)
        if not metadata:
            logger.warning(f"Model metadata not found for version {version}")
            return False
        session.query(ModelMetadata).filter_by(model_id=metadata.model_id).delete()
        session.flush()
        return True
