"""
Data processing pipeline for F1 race data.

This module provides a modular, configurable pipeline for cleaning,
transforming, and preparing F1 race data for model training.
"""
import os
import json
from datetime import datetime
from typing import List, Optional
import pandas as pd
from pathlib import Path
import hashlib

from db.base import db_session
from db.models.dataset_versions import DatasetVersion
from db.repositiries.data_repository import F1DataRepository
from gonzo_pit_strategy.log.logger import get_console_logger
from training.pipeline_steps.base_step import PipelineStep

logger = get_console_logger(__name__)


class DataPipeline:
    """Main data processing pipeline."""

    def __init__(self, config_path: str = "../../config/pipeline.json"):
        """Initialize the data pipeline.

        Args:
            config_path: Path to pipeline configuration JSON file
        """
        with open(config_path, 'r') as f:
            self.config = json.load(f)['pipeline']

        self.name = self.config.get('name', 'f1_data_pipeline')
        self.version = self.config.get('version', '0.1.0')
        self.steps = []
        self.save_checkpoints = self.config.get('save_checkpoints', True)
        self.checkpoint_dir = self.config.get('checkpoint_dir', '../../data/processed')
        self.checkpoint_format = self.config.get('checkpoint_format', 'tsv')
        self.artifacts_dir = self.config.get('artifacts_dir', '../../models/artifacts')

        # Initialize pipeline steps
        self._init_steps()

        logger.info(f"Initialized {self.name} pipeline v{self.version} with {len(self.steps)} steps")

    def _init_steps(self):
        """Initialize pipeline steps from configuration using the registry."""
        step_configs = self.config.get('steps', [])

        for step_config in step_configs:
            step_name = step_config.get('name')
            enabled = step_config.get('enabled', True)

            if not enabled:
                logger.debug(f"Skipping disabled step: {step_name}")
                continue

            if step_name not in PipelineStep.registry:
                logger.warning(f"Unknown step type: {step_name}, skipping")
                logger.warning((f"Pipeline registry contains: {PipelineStep.registry}"))
                continue

            step_class = PipelineStep.registry[step_name]
            step = step_class(step_config.get('config', {}))
            self.steps.append(step)
            logger.debug(f"Added step: {step_name}")

    def _generate_checkpoint_path(self, dataset_name: str, version: str) -> str:
        """Generate path for saving checkpoint data.

        Args:
            dataset_name: Name of the dataset
            version: Version string

        Returns:
            Path to save the checkpoint file
        """
        Path(self.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        return os.path.join(self.checkpoint_dir, f"{dataset_name}_{version}.{self.checkpoint_format}")

    def _generate_artifacts_path(self, version: str) -> str:
        """Generate path for saving pipeline artifacts (encoders, scalers).

        Args:
            version: Version string

        Returns:
            Path to save artifacts
        """
        artifacts_path = os.path.join(self.artifacts_dir, version)
        Path(artifacts_path).mkdir(parents=True, exist_ok=True)
        return artifacts_path

    def _compute_data_hash(self, df: pd.DataFrame) -> str:
        """Compute a hash of the dataframe content.

        Args:
            df: DataFrame to hash

        Returns:
            SHA256 hash string of dataframe content
        """
        # Convert to string and hash
        data_str = df.to_string().encode('utf-8')
        return hashlib.sha256(data_str).hexdigest()[:12]

    def _save_dataset_version(self, dataset_name: str, version: str, df: pd.DataFrame,
                              description: str, steps_applied: List[str], file_path: str):
        """Save dataset version metadata to the database.

        Args:
            dataset_name: Name of the dataset
            version: Version string
            df: The processed DataFrame
            description: Description of the dataset version
            steps_applied: List of processing steps applied
            file_path: Path where the data file is saved
        """
        with db_session() as session:
            # Check if this dataset version already exists
            existing = session.query(DatasetVersion).filter_by(
                dataset_name=dataset_name,
                version=version
            ).first()

            if existing:
                # Update the existing record with new values
                existing.description = description
                existing.created_at = datetime.now()
                existing.created_by = 'data_pipeline'
                existing.data_path = file_path
                existing.record_count = len(df)
                existing.feature_count = len(df.columns)
                existing.preprocessing_steps = steps_applied
                logger.info(f"Updated existing dataset version: {dataset_name} v{version}")
            else:
                # Create new record if it doesn't exist
                dataset_version = DatasetVersion(
                    dataset_name=dataset_name,
                    version=version,
                    description=description,
                    created_at=datetime.now(),
                    created_by='data_pipeline',
                    data_path=file_path,
                    record_count=len(df),
                    feature_count=len(df.columns),
                    preprocessing_steps=steps_applied
                )
                session.add(dataset_version)
                logger.info(f"Saved new dataset version metadata: {dataset_name} v{version}")

    def _save_artifacts(self, version: str):
        """Save pipeline artifacts like encoders and scalers.

        Args:
            version: Version string for the artifacts directory
        """
        artifacts_path = self._generate_artifacts_path(version)

        # Save artifacts from each step
        for step in self.steps:
            step.save(artifacts_path)

        logger.info(f"Saved pipeline artifacts to {artifacts_path}")

        # Create a manifest file with information about the artifacts
        manifest = {
            "pipeline_version": self.version,
            "dataset_version": version,
            "created_at": datetime.now().isoformat(),
            "steps": [step.name for step in self.steps],
            "artifacts_path": artifacts_path
        }

        with open(os.path.join(artifacts_path, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)

        return artifacts_path

    def load_artifacts(self, version: str):
        """Load pipeline artifacts for a specific version.

        Args:
            version: Version string for the artifacts directory

        Returns:
            True if artifacts were loaded successfully
        """
        artifacts_path = self._generate_artifacts_path(version)

        if not os.path.exists(artifacts_path):
            logger.error(f"Artifacts directory not found: {artifacts_path}")
            return False

        # Check if manifest exists
        manifest_path = os.path.join(artifacts_path, "manifest.json")
        if not os.path.exists(manifest_path):
            logger.error(f"Manifest file not found: {manifest_path}")
            return False

        # Load manifest
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        logger.info(
            f"Loading artifacts for pipeline version {manifest['pipeline_version']}, dataset version {manifest['dataset_version']}")

        # Load artifacts for each step
        for step in self.steps:
            step.load(artifacts_path)

        logger.info(f"Loaded pipeline artifacts from {artifacts_path}")
        return True

    def process(self, year: Optional[int] = None, save_version: Optional[str] = None) -> pd.DataFrame:
        """Process F1 race data through the pipeline.

        Args:
            year: Optional year to filter data
            save_version: Optional explicit version string for saving

        Returns:
            Processed DataFrame
        """
        # Get raw data from repository
        logger.info(f"Fetching race history data{' for year ' + str(year) if year else ''}")
        df = F1DataRepository.get_all_race_history(year)
        initial_shape = df.shape
        logger.info(f"Initial data shape: {initial_shape}")

        # Apply each pipeline step
        steps_applied = []
        for step in self.steps:
            logger.info(f"Applying {step.name}")
            df = step.process(df)
            steps_applied.append(step.get_description())
            logger.info(f"Shape after {step.name}: {df.shape}")
            logger.debug(f"Cols after step: {[f'{col}' for col in df.columns.tolist()]}")

        # Generate version if not provided
        if save_version is None:
            timestamp = datetime.now().strftime("%Y%m%d")  #  "%Y%m%d%H%M"
            data_hash = self._compute_data_hash(df)
            save_version = f"{timestamp}_{data_hash}"

        dataset_name = f"f1_race_data{'_' + str(year) if year else ''}"

        # Save checkpoint if enabled
        file_path = ""
        if self.save_checkpoints:
            file_path = self._generate_checkpoint_path(dataset_name, save_version)

            if self.checkpoint_format == 'tsv':
                df.to_csv(file_path, sep='\t', index=False)
            elif self.checkpoint_format == 'csv':
                df.to_csv(file_path, index=False)
            elif self.checkpoint_format == 'parquet':
                df.to_parquet(file_path, index=False)
            else:
                logger.warning(f"Unsupported checkpoint format: {self.checkpoint_format}")

            logger.info(f"Saved processed data to {file_path}")

        # Save artifacts (encoders, scalers)
        artifacts_path = self._save_artifacts(save_version)

        # Create description
        description = (
            f"F1 race data{'for year ' + str(year) if year else ''} processed with "
            f"{len(self.steps)} pipeline steps. Initial shape: {initial_shape}, "
            f"Final shape: {df.shape}. Artifacts saved to {artifacts_path}."
        )

        # Save metadata to database
        self._save_dataset_version(
            dataset_name=dataset_name,
            version=save_version,
            df=df,
            description=description,
            steps_applied=steps_applied,
            file_path=file_path
        )

        return df

    def load_checkpoint(self, dataset_name: str, version: str) -> pd.DataFrame:
        """Load a saved checkpoint file.

        Args:
            dataset_name: Name of the dataset
            version: Version string

        Returns:
            DataFrame loaded from checkpoint
        """
        file_path = self._generate_checkpoint_path(dataset_name, version)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Checkpoint file not found: {file_path}")

        logger.info(f"Loading checkpoint from {file_path}")

        if file_path.endswith('.tsv'):
            return pd.read_csv(file_path, sep='\t')
        elif file_path.endswith('.csv'):
            return pd.read_csv(file_path)
        elif file_path.endswith('.parquet'):
            return pd.read_parquet(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_path}")