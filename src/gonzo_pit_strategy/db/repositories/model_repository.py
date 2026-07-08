"""
Repository for machine learning model management.

This module provides a repository pattern implementation for managing machine learning models,
including saving, loading, and retrieving model metadata.
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import json
from datetime import datetime
import tensorflow as tf
from sqlalchemy.orm import Session

from gonzo_pit_strategy.db.models.model_metadata import ModelMetadata
import logging

logger = logging.getLogger(__name__)


class ModelRepository:
    """Repository for managing machine learning models."""

    def __init__(self, model_path: str = "models/artifacts"):
        self.model_path = model_path

    def save_model(
        self, model: tf.keras.Model, version: str, metadata: Dict[str, Any], session: Session
    ) -> int:
        # Save model to disk
        save_path = os.path.join(self.model_path, version)
        os.makedirs(save_path, exist_ok=True)
        model_file_path = os.path.join(
            save_path, metadata.get("model_name", "model.keras")
        )
        model.save(model_file_path)

        # Save metadata to database
        model_metadata = ModelMetadata(
            name=metadata.get("model_name", "unnamed_model"),
            version=version,
            description=metadata.get("description", ""),
            created_at=datetime.now(),
            created_by=metadata.get("created_by", "ModelRepository"),
            architecture=metadata.get("architecture", "unknown"),
            framework_version=tf.__version__,
            tags=metadata.get("tags", []),
            configuration=metadata.get("config", {}),
            config_source_path=metadata.get("config_path", ""),
        )
        session.add(model_metadata)
        session.flush()

        return model_metadata.model_id

    def create_placeholder_model(self, version: str, metadata: Dict[str, Any], session: Session) -> int:
        model_metadata = ModelMetadata(
            name=metadata.get("model_name", "unnamed_model"),
            version=version,
            description=metadata.get("description", ""),
            created_at=datetime.now(),
            created_by=metadata.get("created_by", "ModelRepository"),
            architecture=metadata.get("architecture", "unknown"),
            framework_version=tf.__version__,
            tags=metadata.get("tags", []),
            configuration=metadata.get("config", {}),
            config_source_path=metadata.get("config_path", ""),
        )
        session.add(model_metadata)
        session.flush()
        return model_metadata.model_id

    def update_model(
        self,
        model_id: int,
        model: tf.keras.Model,
        version: str,
        metadata: Dict[str, Any],
        session: Session
    ) -> None:
        # Save model to disk
        save_path = os.path.join(self.model_path, version)
        os.makedirs(save_path, exist_ok=True)
        model_file_path = os.path.join(
            save_path, metadata.get("model_name", "model.keras")
        )
        model.save(model_file_path)

        # Update metadata in database
        model_metadata = (
            session.query(ModelMetadata).filter_by(model_id=model_id).first()
        )
        if model_metadata:
            if "description" in metadata:
                model_metadata.description = metadata["description"]
            if "tags" in metadata:
                model_metadata.tags = metadata["tags"]
            if "config" in metadata:
                model_metadata.configuration = metadata["config"]
            session.flush()

    def load_model(
        self, version: str, model_name: Optional[str] = None
    ) -> tf.keras.Model:
        model_dir = os.path.join(self.model_path, version)
        if not os.path.exists(model_dir):
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        if model_name is None:
            model_name = "model.keras"

        model_path = os.path.join(model_dir, model_name)
        if not os.path.exists(model_path):
            alternative_paths = [
                os.path.join(model_dir, "model.keras"),
                os.path.join(model_dir, "model.h5"),
                os.path.join(model_dir, "saved_model"),
            ]
            for alt_path in alternative_paths:
                if os.path.exists(alt_path):
                    logger.info(f"Using alternative model path: {alt_path}")
                    model_path = alt_path
                    break
            else:
                raise FileNotFoundError(
                    f"Model not found at {model_path} or any alternative locations"
                )

        try:
            model = tf.keras.models.load_model(model_path)
            logger.info(f"Successfully loaded model from {model_path}")
        except Exception as e:
            logger.error(f"Error loading model from {model_path}: {str(e)}")
            raise

        return model

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
        self, session: Session, architecture: Optional[str] = None, tags: Optional[List[str]] = None
    ) -> List[ModelMetadata]:
        query = session.query(ModelMetadata)
        if architecture:
            query = query.filter_by(architecture=architecture)
        if tags:
            for tag in tags:
                query = query.filter(ModelMetadata.tags.contains([tag]))
        return query.order_by(ModelMetadata.created_at.desc()).all()

    def delete_model(self, version: str, session: Session, name: Optional[str] = None) -> bool:
        metadata = self.get_model_metadata_by_version(version, session, name)
        if not metadata:
            logger.warning(f"Model metadata not found for version {version}")
            return False

        session.query(ModelMetadata).filter_by(model_id=metadata.model_id).delete()
        session.flush()

        model_dir = os.path.join(self.model_path, version)
        if os.path.exists(model_dir):
            import shutil
            shutil.rmtree(model_dir)

        return True
