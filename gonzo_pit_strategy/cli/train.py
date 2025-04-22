"""
Command-line interface for training models.

This module provides a command-line interface for training machine learning models
using the data from the data pipeline.
"""
import sys
import argparse
import json
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from training.trainer import train_model
from gonzo_pit_strategy.log.logger import get_console_logger
from config.config import config

logger = get_console_logger(__name__)


def main():
    """Main entry point for the training CLI."""
    parser = argparse.ArgumentParser(description='Train a model for F1 pit strategy prediction')

    parser.add_argument('--config-name', type=str, default='training',
                        help='Name of the configuration to use (default: training)')
    parser.add_argument('--model-type', type=str, choices=['dense', 'bilstm'],
                        help='Type of model to train (overrides config)')
    parser.add_argument('--data-version', type=str,
                        help='Version of data to use (overrides config)')
    parser.add_argument('--epochs', type=int,
                        help='Number of epochs to train (overrides config)')
    parser.add_argument('--batch-size', type=int,
                        help='Batch size for training (overrides config)')

    args = parser.parse_args()

    # Load configuration
    training_config = config.get_config(args.config_name, reload=True)

    # Override configuration with command-line arguments
    if args.model_type:
        training_config['model_type'] = args.model_type
    if args.data_version:
        training_config['data_version'] = args.data_version
    if args.epochs:
        training_config['epochs'] = args.epochs
    if args.batch_size:
        training_config['batch_size'] = args.batch_size

    # Save updated configuration
    config_path = config.get_config_path(args.config_name)
    with open(config_path, 'w') as f:
        json.dump(training_config, f, indent=2)

    logger.info(f"Training model with configuration: {args.config_name}")
    logger.info(f"Model type: {training_config['model_type']}")
    logger.info(f"Data version: {training_config['data_version']}")
    logger.info(f"Epochs: {training_config['epochs']}")
    logger.info(f"Batch size: {training_config['batch_size']}")

    # Train model
    model_version, model_id, run_id = train_model(config_name=args.config_name)

    logger.info(f"Training complete. Model version: {model_version}")
    logger.info(f"Model ID: {model_id}, Training Run ID: {run_id}")
    logger.info(f"To use this model for prediction, use the model version: {model_version}")


if __name__ == '__main__':
    main()
