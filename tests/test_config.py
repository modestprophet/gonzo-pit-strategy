"""
Test script for the configuration management system.

This script tests the basic functionality of the configuration management system.
"""
import os

from gonzo_pit_strategy.config.config import config


def test_config_loading():
    """Test loading configuration files."""
    print("Testing configuration loading...")

    # Test loading model configuration
    model_config = config.get_config("model")
    print(f"Model configuration loaded: {bool(model_config)}")
    print(f"Model name: {model_config.get('model_name', 'Not found')}")

    # Test loading training configuration and getting model_type
    training_config = config.get_config("training")
    print(f"Model type from training config: {training_config.get('model_type', 'Not found')}")

    # Test loading training configuration
    training_config = config.get_config("training")
    print(f"Training configuration loaded: {bool(training_config)}")
    print(f"Epochs: {training_config.get('epochs', 'Not found')}")

    # Test loading pipeline configuration
    pipeline_config = config.get_config("pipeline")
    print(f"Pipeline configuration loaded: {bool(pipeline_config)}")

    print("Configuration loading tests completed.")

def test_path_resolution():
    """Test path resolution."""
    print("\nTesting path resolution...")

    # Test resolving paths
    data_path = config.get_path("data/processed")
    print(f"Resolved data path: {data_path}")

    models_path = config.get_path("models/artifacts")
    print(f"Resolved models path: {models_path}")

    config_path = config.get_path("config")
    print(f"Resolved config path: {config_path}")

    print("Path resolution tests completed.")

def test_environment():
    """Test environment detection."""
    print("\nTesting environment detection...")

    # Get current environment
    env = config.environment
    print(f"Current environment: {env}")

    # Test changing environment
    original_env = os.environ.get("APP_ENV")

    try:
        # Test with development environment
        os.environ["APP_ENV"] = "development"
        print(f"Environment after setting to development: {config.environment}")

        # Test with production environment
        os.environ["APP_ENV"] = "production"
        print(f"Environment after setting to production: {config.environment}")

        # Test with invalid environment
        os.environ["APP_ENV"] = "invalid"
        print(f"Environment after setting to invalid: {config.environment}")
    finally:
        # Restore original environment
        if original_env is not None:
            os.environ["APP_ENV"] = original_env
        else:
            os.environ.pop("APP_ENV", None)

    print("Environment detection tests completed.")

if __name__ == "__main__":
    print("Testing configuration management system...\n")

    test_config_loading()
    test_path_resolution()
    test_environment()

    print("\nAll tests completed.")
