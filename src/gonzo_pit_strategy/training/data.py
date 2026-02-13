"""
Data loading and preprocessing for training.
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from typing import Tuple, List
from sklearn.model_selection import train_test_split

from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.db.config import DatabaseConfig
from gonzo_pit_strategy.log.logger import get_logger

logger = get_logger(__name__)


def load_training_data(config: TrainingConfig,) -> Tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]
]:
    """
    Load and prepare data for training based on the provided configuration.

    Args:
        config: TrainingConfig object containing data parameters.

    Returns:
        Tuple containing:
        - X_train, X_val, X_test (features)
        - y_train, y_val, y_test (targets)
        - feature_names (list of column names used as features)
    """
    # Connect to database and load dbt-generated training dataset
    logger.info("Loading training dataset from f1db_ml_prep.prep_training_dataset")
    db_config = DatabaseConfig()
    url_dict = db_config.get_db_url_dict()
    engine = create_engine(URL.create(**url_dict))

    try:
        df = pd.read_sql("SELECT * FROM f1db_ml_prep.prep_training_dataset", engine)
    finally:
        engine.dispose()

    logger.info(f"Data shape: {df.shape}")

    # Convert object dtype columns (typically all-NULL scaled columns) to float, filling NaN with 0
    object_cols = df.select_dtypes(include=["object"]).columns.tolist()
    if object_cols:
        logger.info(
            f"Converting {len(object_cols)} object columns to float and filling NaN with 0: {object_cols}"
        )
        for col in object_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Fill any remaining NaN values with 0
    nan_count = df.isnull().sum().sum()
    if nan_count > 0:
        nan_cols = df.columns[df.isnull().any()].tolist()
        logger.info(f"Filling {nan_count} NaN values with 0 in columns: {nan_cols}")
        df = df.fillna(0.0)

    # Convert boolean OHE columns to integers for Keras
    ohe_cols = [
        col
        for col in df.columns
        if col.startswith(("circuit_", "team_", "driver_"))   # TODO: maybe append _ohe in the dbt pipeline to identify OHE columns instead of hard coding known OHE columns
        and not col.endswith("_scaled")
    ]
    if ohe_cols:
        logger.info(f"Converting {len(ohe_cols)} one-hot encoded columns to integers")
        df[ohe_cols] = df[ohe_cols].astype(int)

    # Target handling
    if config.target_column not in df.columns:
        raise ValueError(f"Target column '{config.target_column}' not found in data")

    y = df[config.target_column].values

    # Feature selection (Exclude logic)
    cols_to_drop = [config.target_column] + config.exclude_columns

    # Filter out columns that might not exist to avoid errors
    cols_to_drop = [col for col in cols_to_drop if col in df.columns]

    X_df = df.drop(columns=cols_to_drop)
    feature_names = X_df.columns.tolist()
    X = X_df.values

    logger.info(f"Features shape: {X.shape}, Target shape: {y.shape}")
    logger.info(f"Excluded columns: {config.exclude_columns}")
    logger.info(f"Selected {len(feature_names)} features")

    # Split data
    # First split off the test set
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=config.test_size, random_state=config.random_state
    )

    # Then split the remaining data into train and validation sets
    # Adjust validation size relative to the remaining data
    val_size_adjusted = config.validation_size / (1 - config.test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val,
        y_train_val,
        test_size=val_size_adjusted,
        random_state=config.random_state,
    )

    logger.info(f"Train set: {X_train.shape[0]} samples")
    logger.info(f"Validation set: {X_val.shape[0]} samples")
    logger.info(f"Test set: {X_test.shape[0]} samples")

    return X_train, X_val, X_test, y_train, y_val, y_test, feature_names
