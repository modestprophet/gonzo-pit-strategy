"""
Command-line interface for training models using the new configuration-driven architecture.
"""

import argparse
import json
import os
import sys
import itertools
from typing import Dict, Any, List

from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.runner import run_experiment, ExperimentResult
from gonzo_pit_strategy.log.logger import get_logger
from gonzo_pit_strategy.config.config import config as app_config

logger = get_logger("gonzo_pit_strategy.cli.train")


def set_nested_value(d: Dict[str, Any], keys: List[str], value: Any):
    """Recursively set a value in a nested dictionary."""
    if len(keys) == 1:
        d[keys[0]] = value
    else:
        # Check if the key exists, if not create empty dict
        # But wait, if keys[0] exists but is not a dict (e.g. strict string from Pydantic default), we can't key into it.
        # The base_config_dict comes from json.load or config.get_config, so it's a dict.
        # But if the structure doesn't match the depth, we might overwrite.

        if keys[0] not in d or not isinstance(d[keys[0]], dict):
            d[keys[0]] = {}
        # Recurse
        set_nested_value(d[keys[0]], keys[1:], value)


def generate_grid_configs(
    base_config_dict: Dict[str, Any], sweep_params: Dict[str, List[Any]]
) -> List[TrainingConfig]:
    """Generate a list of TrainingConfig objects based on sweep parameters."""
    keys = list(sweep_params.keys())
    values_list = list(sweep_params.values())

    configs = []

    # Cartesian product of all parameter values
    import itertools

    for combination in itertools.product(*values_list):
        # Deep copy the base config dict to avoid mutation
        # Using json load/dump as simple deep copy
        import copy

        current_config_dict = copy.deepcopy(base_config_dict)

        # Apply each parameter in the combination
        param_desc = []
        for i, full_key in enumerate(keys):
            value = combination[i]
            # Handle nested keys (e.g. "model.dropout_rate")
            key_parts = full_key.split(".")
            set_nested_value(current_config_dict, key_parts, value)
            param_desc.append(f"{full_key}={value}")

        # Add a tag to identify this run as part of a sweep
        if "tags" not in current_config_dict:
            current_config_dict["tags"] = []
        if isinstance(current_config_dict["tags"], list):
            current_config_dict["tags"].append("grid_search")

        # Update description
        desc = current_config_dict.get("description", "") or "Grid Search"
        current_config_dict["description"] = f"{desc} | {', '.join(param_desc)}"

        try:
            # Migrate and validate
            migrated = migrate_config(current_config_dict)
            configs.append(TrainingConfig(**migrated))
        except Exception as e:
            logger.error(f"Failed to create config for combination {combination}: {e}")

    return configs


def migrate_config(old_config: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to migrate old flat config structure to new nested structure."""
    if "model" in old_config:
        return old_config

    logger.warning("Detected legacy configuration format. Attempting to migrate...")
    new_config = old_config.copy()
    model_type = new_config.pop("model_type", "dense")

    model_config = {"type": model_type}
    # Move known model params
    model_params = [
        "hidden_layers",
        "lstm_units",
        "dropout_rate",
        "activation",
        "dense_layers",
        "recurrent_dropout",
        "output_activation",
    ]

    for key in model_params:
        if key in new_config:
            model_config[key] = new_config.pop(key)

    new_config["model"] = model_config
    return new_config


def main():
    """Main entry point for the training CLI."""
    parser = argparse.ArgumentParser(
        description="Train a model for F1 pit strategy prediction"
    )

    parser.add_argument("--config", type=str, help="Path to training config JSON file")
    parser.add_argument(
        "--grid-search", type=str, help="Path to grid search parameters JSON file"
    )
    parser.add_argument(
        "--config-name",
        type=str,
        help="Name of the configuration to use (legacy support)",
    )
    parser.add_argument(
        "--generate-default",
        action="store_true",
        help="Generate a default configuration file",
    )

    args = parser.parse_args()

    if args.generate_default:
        config = TrainingConfig()
        output_dir = app_config.get_path("config/experiments")
        os.makedirs(output_dir, exist_ok=True)
        output_path = output_dir / "training_config_default.json"
        with open(output_path, "w") as f:
            f.write(config.model_dump_json(indent=2))
        logger.info(f"Default config written to {output_path}")
        return

    config_dict = {}

    if args.config:
        logger.info(f"Loading config from {args.config}")
        with open(args.config, "r") as f:
            config_dict = json.load(f)
    elif args.config_name:
        logger.info(f"Loading config by name: {args.config_name}")
        config_dict = app_config.get_config(args.config_name)
    else:
        # Default fallback
        logger.info("No config specified. Using default TrainingConfig defaults.")
        config_dict = {}

    # Grid Search Mode
    if args.grid_search:
        logger.info(f"Loading grid search parameters from {args.grid_search}")
        with open(args.grid_search, "r") as f:
            sweep_params = json.load(f)

        # Migrate base config just in case
        config_dict = migrate_config(config_dict)

        configs = generate_grid_configs(config_dict, sweep_params)
        logger.info(f"Generated {len(configs)} configurations for grid search.")

        results = []
        for i, config in enumerate(configs):
            logger.info(f"Running experiment {i + 1}/{len(configs)}")
            try:
                # For grid search, we use the grid search config path as the source
                result = run_experiment(config, config_path=args.grid_search)
                results.append(result)
                logger.info(
                    f"Experiment {i + 1} completed. Test Loss: {result.test_loss}"
                )
            except Exception as e:
                logger.error(f"Experiment {i + 1} failed: {e}", exc_info=True)

        # Summary
        logger.info("Grid Search Complete.")
        print("\n--- Grid Search Results ---")
        print(f"{'Run ID':<10} | {'Model Version':<30} | {'Test Loss':<15}")
        print("-" * 60)
        for res in results:
            # We need to find the config description matching the run, but ExperimentResult doesn't have it.
            # Ideally we pass it through or fetch from DB.
            # For now, just print what we have.
            print(
                f"{res.run_id:<10} | {res.model_version:<30} | {res.test_loss:<15.4f}"
            )

        return

    # Single Run Mode
    try:
        config_dict = migrate_config(config_dict)
        training_config = TrainingConfig(**config_dict)
    except Exception as e:
        logger.error(f"Invalid configuration: {e}")
        # Print validation errors details if possible
        logger.debug(f"Config dictionary: {json.dumps(config_dict, indent=2)}")
        sys.exit(1)

    logger.info(f"Starting experiment with model type: {training_config.model.type}")

    # Determine config source path
    config_source_path = None
    if args.config:
        config_source_path = args.config
    elif args.config_name:
        config_source_path = f"config_name:{args.config_name}"

    try:
        result = run_experiment(training_config, config_path=config_source_path)
        logger.info(f"Experiment completed successfully.")
        logger.info(f"Run ID: {result.run_id}")
        logger.info(f"Model Version: {result.model_version}")
        logger.info(f"Test Loss: {result.test_loss}")
    except Exception as e:
        logger.error(f"Experiment failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
