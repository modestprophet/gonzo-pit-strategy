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

from gonzo_pit_strategy.db.base import db_session
from gonzo_pit_strategy.db.models.model_metadata import ModelMetadata
from gonzo_pit_strategy.log.logger import get_logger

logger = get_logger(__name__)


class ModelRepository:
    """Repository for managing machine learning models."""

    def __init__(self, model_path: str = "models/artifacts"):
        """Initialize the model repository.

        Args:
            model_path: Base path for storing model artifacts
        """
        self.model_path = model_path

    def save_model(
        self, model: tf.keras.Model, version: str, metadata: Dict[str, Any]
    ) -> int:
        """Save a model and its metadata.

        Args:
            model: The TensorFlow model to save
            version: Version string for the model
            metadata: Dictionary of model metadata

        Returns:
            model_id: The ID of the saved model metadata
        """
        # Save model to disk
        save_path = os.path.join(self.model_path, version)
        os.makedirs(save_path, exist_ok=True)
        model_file_path = os.path.join(
            save_path, metadata.get("model_name", "model.keras")
        )
        model.save(model_file_path)

        # Save metadata to database
        with db_session() as session:
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
            session.commit()
            session.refresh(model_metadata)

            # Save metadata to JSON file
            with open(os.path.join(save_path, "model_metadata.json"), "w") as f:
                json.dump(
                    {
                        **metadata,
                        "model_id": model_metadata.model_id,
                        "saved_at": datetime.now().isoformat(),
                    },
                    f,
                    indent=2,
                )

            return model_metadata.model_id

    def create_placeholder_model(self, version: str, metadata: Dict[str, Any]) -> int:
        """Create a placeholder model metadata record.

        Args:
            version: Version string for the model
            metadata: Dictionary of model metadata

        Returns:
            model_id: The ID of the created model metadata
        """
        with db_session() as session:
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
            session.commit()
            session.refresh(model_metadata)
            return model_metadata.model_id

    def update_model(
        self,
        model_id: int,
        model: tf.keras.Model,
        version: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Update an existing model record and save artifacts.

        Args:
            model_id: The ID of the model to update
            model: The TensorFlow model to save
            version: Version string for the model
            metadata: Dictionary of updated model metadata
        """
        # Save model to disk
        save_path = os.path.join(self.model_path, version)
        os.makedirs(save_path, exist_ok=True)
        model_file_path = os.path.join(
            save_path, metadata.get("model_name", "model.keras")
        )
        model.save(model_file_path)

        # Update metadata in database
        with db_session() as session:
            model_metadata = (
                session.query(ModelMetadata).filter_by(model_id=model_id).first()
            )
            if model_metadata:
                # Update fields
                if "description" in metadata:
                    model_metadata.description = metadata["description"]
                if "tags" in metadata:
                    model_metadata.tags = metadata["tags"]
                if "config" in metadata:
                    model_metadata.configuration = metadata["config"]
                # Add other fields updates as necessary

                session.commit()

        # Save metadata to JSON file
        with open(os.path.join(save_path, "model_metadata.json"), "w") as f:
            json.dump(
                {
                    **metadata,
                    "model_id": model_id,
                    "saved_at": datetime.now().isoformat(),
                },
                f,
                indent=2,
            )

    def load_model(
        self, version: str, model_name: Optional[str] = None
    ) -> Tuple[tf.keras.Model, Dict[str, Any]]:
        """Load a model and its metadata.

        Args:
            version: Version string for the model
            model_name: Optional model filename (if not provided, will load from metadata)

        Returns:
            Tuple of (model, metadata)
        """
        model_dir = os.path.join(self.model_path, version)

        # Check if model directory exists
        if not os.path.exists(model_dir):
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        metadata_path = os.path.join(model_dir, "model_metadata.json")

        # Check if metadata file exists
        if not os.path.exists(metadata_path):
            logger.warning(
                f"Model metadata not found at {metadata_path}, will use minimal metadata"
            )
            metadata = {"model_name": model_name or "model.keras"}
        else:
            # Load metadata
            with open(metadata_path, "r") as f:
                metadata = json.load(f)

        # Determine model path
        if model_name is None:
            model_name = metadata.get("model_name", "model.keras")

        model_path = os.path.join(model_dir, model_name)

        # Check if model file exists
        if not os.path.exists(model_path):
            # Try alternative model formats if the specified one doesn't exist
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

        # Load model
        try:
            model = tf.keras.models.load_model(model_path)
            logger.info(f"Successfully loaded model from {model_path}")
        except Exception as e:
            logger.error(f"Error loading model from {model_path}: {str(e)}")
            raise

        return model, metadata

    def get_model_metadata(self, model_id: int) -> Optional[ModelMetadata]:
        """Get model metadata by ID.

        Args:
            model_id: The model ID

        Returns:
            ModelMetadata object or None if not found
        """
        with db_session() as session:
            return session.query(ModelMetadata).filter_by(model_id=model_id).first()

    def get_model_metadata_by_version(
        self, version: str, name: Optional[str] = None
    ) -> Optional[ModelMetadata]:
        """Get model metadata by version and optionally name.

        Args:
            version: Version string for the model
            name: Optional model name

        Returns:
            ModelMetadata object or None if not found
        """
        with db_session() as session:
            query = session.query(ModelMetadata).filter_by(version=version)
            if name:
                query = query.filter_by(name=name)
            return query.first()

    def list_models(
        self, architecture: Optional[str] = None, tags: Optional[List[str]] = None
    ) -> List[ModelMetadata]:
        """List available models, optionally filtered by architecture or tags.

        Args:
            architecture: Optional architecture to filter by
            tags: Optional list of tags to filter by

        Returns:
            List of ModelMetadata objects
        """
        with db_session() as session:
            query = session.query(ModelMetadata)

            if architecture:
                query = query.filter_by(architecture=architecture)

            if tags:
                # Filter by tags (requires all tags to be present)
                for tag in tags:
                    query = query.filter(ModelMetadata.tags.contains([tag]))

            return query.order_by(ModelMetadata.created_at.desc()).all()

    def delete_model(self, version: str, name: Optional[str] = None) -> bool:
        """Delete a model and its metadata.

        Args:
            version: Version string for the model
            name: Optional model name

        Returns:
            True if deletion was successful
        """
        # Get metadata
        metadata = self.get_model_metadata_by_version(version, name)
        if not metadata:
            logger.warning(f"Model metadata not found for version {version}")
            return False

        # Delete from database
        with db_session() as session:
            session.query(ModelMetadata).filter_by(model_id=metadata.model_id).delete()
            session.commit()

        # Delete files
        model_dir = os.path.join(self.model_path, version)
        if os.path.exists(model_dir):
            import shutil

            shutil.rmtree(model_dir)

        return True
