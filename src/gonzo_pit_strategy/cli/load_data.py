"""
Command-line interface for data pipeline.

This script processes data through the pipeline and saves transformers.
"""
from gonzo_pit_strategy.training.data_pipeline import DataPipeline
from gonzo_pit_strategy.log.logger import get_logger

logger = get_logger(__name__)


def main():
    logger.info("Starting data pipeline processing")

    # Use the new configuration system
    pipeline = DataPipeline(config_name="pipeline")
    df = pipeline.process()

    logger.info(f"Data processing complete. Shape: {df.shape}")
    logger.info(f"Data version: {pipeline.version}")


if __name__ == "__main__":
    main()
