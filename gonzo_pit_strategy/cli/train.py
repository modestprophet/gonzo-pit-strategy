"""
Command-line interface for training models.

This module provides a command-line interface for training machine learning models
using the data from the data pipeline.
"""
import os
import argparse
import json
from pathlib import Path

from training.trainer import train_model
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)


def main():
    """Main entry point for the training CLI."""
    parser = argparse.ArgumentParser(description='Train a model for F1 pit strategy prediction')

    parser.add_argument('--config', type=str, default='../../config/training.json',
                        help='Path to training configuration file')
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
    with open(args.config, 'r') as f:
        config = json.load(f)

    # Override configuration with command-line arguments
    if args.model_type:
        config['model_type'] = args.model_type
    if args.data_version:
        config['data_version'] = args.data_version
    if args.epochs:
        config['epochs'] = args.epochs
    if args.batch_size:
        config['batch_size'] = args.batch_size

    # Save updated configuration
    with open(args.config, 'w') as f:
        json.dump(config, f, indent=2)

    logger.info(f"Training model with configuration from {args.config}")
    logger.info(f"Model type: {config['model_type']}")
    logger.info(f"Data version: {config['data_version']}")
    logger.info(f"Epochs: {config['epochs']}")
    logger.info(f"Batch size: {config['batch_size']}")

    # Train model
    model_version, model_id, run_id = train_model(config_path=args.config)

    logger.info(f"Training complete. Model version: {model_version}")
    logger.info(f"Model ID: {model_id}, Training Run ID: {run_id}")
    logger.info(f"To use this model for prediction, use the model version: {model_version}")


if __name__ == '__main__':
    main()
