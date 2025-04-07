"""Base classes for pipeline steps."""
import json
from typing import Dict, Any

import pandas as pd


class PipelineStep:
    """Base class for all data pipeline steps."""

    # Registry to store all pipeline step classes
    registry = {}

    def __init_subclass__(cls, **kwargs):
        """Register all subclasses automatically."""
        super().__init_subclass__(**kwargs)
        step_name = cls.__name__.lower()
        if hasattr(cls, 'step_name'):
            step_name = cls.step_name
        cls.registry[step_name] = cls

    def __init__(self, config: Dict[str, Any]):
        """Initialize the pipeline step with configuration.

        Args:
            config: Dictionary containing step configuration
        """
        self.config = config or {}
        self.name = self.__class__.__name__

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process the dataframe.

        Args:
            df: Input DataFrame

        Returns:
            Processed DataFrame
        """
        raise NotImplementedError("Each pipeline step must implement process method")

    def get_description(self) -> str:
        """Get a string description of the processing step with config.

        Returns:
            String description for versioning/logging
        """
        return f"{self.name}: {json.dumps(self.config)}"

    def save(self, path: str) -> None:
        """Save any artifacts created by this step.

        Args:
            path: Directory path to save artifacts
        """
        pass

    def load(self, path: str) -> None:
        """Load any artifacts needed by this step.

        Args:
            path: Directory path to load artifacts from
        """
        pass