"""
Command-line interface for data pipeline.

This script processes data through the pipeline and saves transformers.
"""
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from training.data_pipeline import DataPipeline
from gonzo_pit_strategy.log.logger import get_logger

logger = get_logger(__name__)

logger.info("Starting data pipeline processing")

# Use the new configuration system
pipeline = DataPipeline(config_name="pipeline")
df = pipeline.process()

logger.info(f"Data processing complete. Shape: {df.shape}")
logger.info(f"Data version: {pipeline.version}")

# # Later, load transformers for inference
# pipeline = DataPipeline()
# pipeline.load_artifacts("20230415123456_abc123def456")
#
# # Load the data
# df = pipeline.load_checkpoint("f1_race_data_2021", "20230415123456_abc123def456")
#
# # Apply transformations for inference (useful in your model predictor)
# for step in pipeline.steps:
#     if step.name in ["CategoricalEncoder", "NumericalScaler"]:
#         new_data = step.process(new_data)
