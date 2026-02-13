"""
Configuration management utilities for the Gonzo Pit Strategy project.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any

# Environment variables
ENV_VAR_APP_ENV = "APP_ENV"
DEFAULT_ENV = "development"

VALID_ENVIRONMENTS = ["development", "testing", "production"]

# Map configs defined in the project to their respective configuration file names
CONFIG_FILES = {
    "database": "database.json",
    "logging": "logging.json",
}


class Config:
    """Centralized configuration management class."""

    _instance = None
    _configs = {}

    def __new__(cls):
        """Singleton pattern to ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self._project_root = self._get_project_root()
        self._config_dir = self._project_root / "config"

    def _get_project_root(self) -> Path:
        """Get the project root directory.

        Returns:
            Path to the project root directory
        """
        # Start from the current file and go up until we find the project root
        current_file = Path(__file__).resolve()
        # src/gonzo_pit_strategy/config/config.py -> root
        return current_file.parents[3]

    def get_config(self, config_name: str, reload: bool = False) -> Dict[str, Any]:
        """Get configuration by name.

        Args:
            config_name: Name of the configuration (e.g., "model", "training")
            reload: Whether to reload the configuration from disk

        Returns:
            Configuration dictionary
        """
        if reload or config_name not in self._configs:
            self._configs[config_name] = self.load_config(config_name)
        return self._configs[config_name]

    def get_path(self, path: str) -> Path:
        """Resolve a path relative to the project root.

        Args:
            path: Path relative to the project root

        Returns:
            Absolute path
        """
        return self._project_root / path

    def get_config_path(self, config_name: str) -> Path:
        """Get the path to a configuration file.

        Args:
            config_name: Name of the configuration (e.g., "model", "training")

        Returns:
            Path to the configuration file
        """
        if config_name not in CONFIG_FILES:
            raise ValueError(
                f"Unknown configuration: {config_name}. "
                f"Available configurations: {list(CONFIG_FILES.keys())}"
            )

        return self._config_dir / CONFIG_FILES[config_name]

    def load_config(self, config_name: str) -> Dict[str, Any]:
        """Load configuration from a JSON file.

        Args:
            config_name: Name of the configuration (e.g., "model", "training")

        Returns:
            Configuration dictionary
        """
        config_path = self.get_config_path(config_name)

        try:
            with open(config_path, "r") as f:
                parsed_config = json.load(f)
            return parsed_config
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in configuration file: {config_path}")

    @property
    def environment(self) -> str:
        """Get the current environment.

        Returns:
            Current environment (development, testing, or production)
        """
        env = os.environ.get(ENV_VAR_APP_ENV, DEFAULT_ENV)
        if env not in VALID_ENVIRONMENTS:
            print(
                f"Warning: Invalid environment '{env}'. Using '{DEFAULT_ENV}' instead."
            )
            env = DEFAULT_ENV
        return env

    @property
    def project_root(self) -> Path:
        """Get the project root directory.

        Returns:
            Path to the project root directory
        """
        return self._project_root

    @property
    def config_dir(self) -> Path:
        """Get the configuration directory.

        Returns:
            Path to the configuration directory
        """
        return self._config_dir


# Create a singleton instance for easy import
config = Config()
