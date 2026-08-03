"""
Command-line interface for training models using the new configuration-driven architecture.
"""

import argparse
import json
import os
import sys

from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.runner import Experiment
from gonzo_pit_strategy.training.sweep import SweepConfig, Sweep
from gonzo_pit_strategy.training.data import DatabaseDataSource
from gonzo_pit_strategy.training.artifact import ArtifactStore
import logging
from gonzo_pit_strategy.config.config import AppConfig, setup_logging
from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.db.run_ledger import PostgresRunLedger

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the training CLI."""
    app_config = AppConfig()
    setup_logging(app_config.logging)

    parser = argparse.ArgumentParser(
        description="Train a model for F1 pit strategy prediction"
    )

    parser.add_argument("--config", type=str, help="Path to training config JSON file")
    parser.add_argument(
        "--grid-search", type=str, help="Path to grid search parameters JSON file"
    )
    parser.add_argument(
        "--generate-default",
        action="store_true",
        help="Generate a default configuration file",
    )

    args = parser.parse_args()

    # Generating a template needs no database, so this runs before the pool.
    if args.generate_default:
        config = TrainingConfig()
        output_dir = app_config.paths.experiments_dir
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "training_config_default.json")
        with open(output_path, "w") as f:
            f.write(config.model_dump_json(indent=2))
        logger.info(f"Default config written to {output_path}")
        return

    # The entry point owns the wiring (ADR 0001 §4): it builds the adapters and
    # injects them, so nothing downstream constructs its own collaborators.
    pool = ConnectionPool(app_config.db)
    data_source = DatabaseDataSource(pool.engine)
    artifact_store = ArtifactStore(app_config.paths.artifacts_root)
    ledger = PostgresRunLedger(pool)

    config_dict = {}

    if args.config:
        logger.info(f"Loading config from {args.config}")
        with open(args.config, "r") as f:
            config_dict = json.load(f)
    else:
        logger.info("No config specified. Using default TrainingConfig defaults.")

    # Grid Search Mode
    if args.grid_search:
        logger.info(f"Loading grid search parameters from {args.grid_search}")
        with open(args.grid_search, "r") as f:
            sweep_params = json.load(f)

        try:
            base_config = TrainingConfig(**config_dict)
            sweep_config = SweepConfig(
                base_config=base_config,
                parameters=sweep_params,
                sweep_name="Grid Search"
            )
        except Exception as e:
            logger.error(f"Invalid base configuration for sweep: {e}")
            sys.exit(1)

        sweep = Sweep(
            sweep_config,
            data_source,
            artifact_store,
            ledger,
            config_path=args.grid_search,
            paths=app_config.paths,
        )

        results = []
        for iteration in sweep.run():
            if iteration.error:
                logger.error(f"Experiment {iteration.index}/{iteration.total} failed: {iteration.error}")
            else:
                logger.info(f"Experiment {iteration.index}/{iteration.total} completed. Test Loss: {iteration.result.test_loss:.4f}")
                results.append(iteration.result)

        logger.info("Grid Search Complete.")
        print("\n--- Grid Search Results ---")
        print(f"{'Run ID':<10} | {'Model Version':<30} | {'Test Loss':<15}")
        print("-" * 60)
        for res in results:
            run_id_str = str(res.run_id) if res.run_id is not None else "N/A"
            print(f"{run_id_str:<10} | {res.model_version:<30} | {res.test_loss:<15.4f}")

        return

    # Single Run Mode
    try:
        training_config = TrainingConfig(**config_dict)
    except Exception as e:
        logger.error(f"Invalid configuration: {e}")
        logger.debug(f"Config dictionary: {json.dumps(config_dict, indent=2)}")
        sys.exit(1)

    logger.info(f"Starting experiment with model type: {training_config.model.type}")

    config_source_path = args.config if args.config else None

    try:
        experiment = Experiment(
            training_config,
            data_source,
            artifact_store,
            ledger,
            config_path=config_source_path,
            paths=app_config.paths,
        )
        result = experiment.run()
        logger.info("Experiment completed successfully.")
        logger.info(f"Run ID: {result.run_id}")
        logger.info(f"Model Version: {result.model_version}")
        logger.info(f"Test Loss: {result.test_loss}")
    except Exception as e:
        logger.error(f"Experiment failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
