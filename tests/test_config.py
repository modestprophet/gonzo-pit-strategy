"""
Test script for the new AppConfig configuration management system.
"""
import os

from gonzo_pit_strategy.config.config import AppConfig


def test_config_loading():
    """Test loading configuration files."""
    print("Testing configuration loading...")

    config = AppConfig()

    # Test accessing training configuration
    print(f"Training configuration loaded: {bool(config.training)}")
    print(f"Epochs: {config.training.epochs}")

    # Test accessing db configuration
    print(f"Database configuration loaded: {bool(config.db)}")
    print(f"Database host: {config.db.host}")

    print("Configuration loading tests completed.")

def test_environment():
    """Test environment detection."""
    print("\nTesting environment detection...")
    config = AppConfig()

    # Get current environment
    env = config.app_env
    print(f"Current environment: {env}")

    print("Environment detection tests completed.")

if __name__ == "__main__":
    print("Testing configuration management system...\n")

    test_config_loading()
    test_environment()

    print("\nAll tests completed.")
