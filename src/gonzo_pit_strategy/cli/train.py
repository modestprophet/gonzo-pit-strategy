"""
Command-line interface for training models using the new configuration-driven architecture.
"""

import argparse
import json
import logging
import os
import sys
from typing import Any

from pydantic import ValidationError
from pydantic_settings import SettingsError

from gonzo_pit_strategy.config.config import (
    AppConfig,
    GenerateDefaultSettings,
    setup_logging,
)
from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.db.run_ledger import PostgresRunLedger
from gonzo_pit_strategy.security import VaultError
from gonzo_pit_strategy.training.artifact import ArtifactStore
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import DatabaseDataSource
from gonzo_pit_strategy.training.runner import Experiment
from gonzo_pit_strategy.training.sweep import Sweep, SweepConfig

logger = logging.getLogger(__name__)


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key!r}")
        result[key] = value
    return result


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
        "--generate-default",
        action="store_true",
        help="Generate a default configuration file",
    )

    args = parser.parse_args()

    if args.generate_default:
        config = TrainingConfig()
        output_dir = GenerateDefaultSettings().paths.experiments_dir
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "training_config_default.json")
        with open(output_path, "w") as f:
            f.write(config.model_dump_json(indent=2))
        print(f"Default config written to {output_path}")
        return

    try:
        app_config = AppConfig()  # pyright: ignore[reportCallIssue]
    except (VaultError, ValidationError, SettingsError) as exc:
        print(f"Invalid settings: {exc}", file=sys.stderr)
        sys.exit(1)
    setup_logging(app_config.logging)

    try:
        config_dict = {}
        if args.config:
            logger.info(f"Loading config from {args.config}")
            with open(args.config) as f:
                config_dict = json.load(f, object_pairs_hook=_unique_json_object)
        training_config = TrainingConfig.model_validate(config_dict)

        sweep_config = None
        if args.grid_search:
            logger.info(f"Loading grid search parameters from {args.grid_search}")
            with open(args.grid_search) as f:
                sweep_params = json.load(f, object_pairs_hook=_unique_json_object)
            sweep_config = SweepConfig(
                base_config=training_config,
                parameters=sweep_params,
                sweep_name="Grid Search",
            )
    except (OSError, ValueError) as exc:
        logger.error(f"Invalid configuration: {exc}")
        sys.exit(1)

    # The entry point owns the wiring (ADR 0001 §4).
    pool = ConnectionPool(app_config.db)
    data_source = DatabaseDataSource(pool.engine)
    artifact_store = ArtifactStore(app_config.paths.artifacts_root)
    ledger = PostgresRunLedger(pool)

    if sweep_config is not None:
        sweep = Sweep(
            sweep_config,
            data_source,
            artifact_store,
            ledger,
            config_path=args.grid_search,
            paths=app_config.paths,
        )

        outcomes = []
        try:
            for iteration in sweep.run():
                outcomes.append(iteration)
                if iteration.result is not None:
                    logger.info(
                        f"Experiment {iteration.index}/{iteration.total} completed. "
                        f"Test loss: {iteration.result.test_loss:.4f}"
                    )
                else:
                    logger.error(
                        f"Experiment {iteration.index}/{iteration.total} failed: {iteration.error}"
                    )
        finally:
            pool.dispose()

        print("\nSweep results")
        for iteration in outcomes:
            label = f"{iteration.index}/{iteration.total}"
            if iteration.result is not None:
                result = iteration.result
                print(
                    f"{label} | COMPLETED | Run ID: {result.run_id} | "
                    f"{result.model_version} | Test loss: {result.test_loss:.4f}"
                )
            else:
                print(f"{label} | FAILED | {iteration.error}")
            print(f"  Configuration: {json.dumps(iteration.config.model_dump(mode='json'))}")

        summary = outcomes[-1]
        print(
            f"Requested: {summary.total} | Succeeded: {summary.succeeded} | "
            f"Failed: {summary.failed}"
        )
        if summary.failed:
            sys.exit(1)
        return

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
    except Exception:
        logger.exception("Experiment failed")
        sys.exit(1)
    finally:
        pool.dispose()


if __name__ == "__main__":
    main()
