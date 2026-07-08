"""
Data loading and preprocessing for training.

This module owns the seam between raw data extraction and ML-ready feature
engineering.  The `TrainingDataSource` Protocol defines the interface; concrete
adapters (e.g. `DatabaseDataSource`) satisfy it.
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL
from typing import Protocol, Tuple, List

from sklearn.model_selection import train_test_split

from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.config.config import DatabaseConfig
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

RawDataset = pd.DataFrame
"""Untransformed data fetched from a source before any ML-specific feature
engineering, NaN filling, or dataset splitting occurs."""


# ---------------------------------------------------------------------------
# TrainingDataSource – the seam
# ---------------------------------------------------------------------------


class TrainingDataSource(Protocol):
    """Interface boundary that provides a RawDataset to the training pipeline.

    Any object with a ``fetch_raw_data`` method returning a ``pd.DataFrame``
    satisfies this Protocol – no inheritance required.
    """

    def fetch_raw_data(self) -> RawDataset: ...


# ---------------------------------------------------------------------------
# DatabaseDataSource – the concrete adapter
# ---------------------------------------------------------------------------


class DatabaseDataSource:
    """Adapter that fetches a RawDataset from a PostgreSQL database.

    The caller (typically the CLI entry point) is responsible for providing
    a SQLAlchemy Engine, keeping the connection lifecycle contained
    within the application boundaries.
    """

    _DEFAULT_QUERY = "SELECT * FROM f1db_ml_prep.prep_training_dataset"

    def __init__(self, engine, *, query: str | None = None) -> None:
        self._engine = engine
        self._query = query or self._DEFAULT_QUERY

    def fetch_raw_data(self) -> RawDataset:
        logger.info(f"Fetching RawDataset via: {self._query}")
        df = pd.read_sql(text(self._query), self._engine)
        logger.info(f"RawDataset shape: {df.shape}")
        return df


# ---------------------------------------------------------------------------
# load_training_data – the deepened module
# ---------------------------------------------------------------------------


def load_training_data(
    config: TrainingConfig,
    data_source: TrainingDataSource,
) -> Tuple[
    np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str]
]:
    """
    Transform a RawDataset into train / validation / test splits.

    All data *extraction* is delegated to ``data_source``; this function is
    purely responsible for feature engineering, NaN handling, and splitting.

    Args:
        config: TrainingConfig with target column, exclusions, split sizes.
        data_source: Any object satisfying the TrainingDataSource protocol.

    Returns:
        (X_train, X_val, X_test, y_train, y_val, y_test, feature_names)
    """
    # ---- Fetch ----------------------------------------------------------
    df: RawDataset = data_source.fetch_raw_data()
    logger.info(f"Data shape: {df.shape}")

    # ---- Feature engineering --------------------------------------------
    # Convert object dtype columns (typically all-NULL scaled columns) to float
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
        if col.startswith(("circuit_", "team_", "driver_"))  # TODO: maybe append _ohe in the dbt pipeline
        and not col.endswith("_scaled")
    ]
    if ohe_cols:
        logger.info(f"Converting {len(ohe_cols)} one-hot encoded columns to integers")
        df[ohe_cols] = df[ohe_cols].astype(int)

    # ---- Target / feature selection ------------------------------------
    if config.target_column not in df.columns:
        raise ValueError(f"Target column '{config.target_column}' not found in data")

    y = df[config.target_column].values

    cols_to_drop = [config.target_column] + config.exclude_columns
    cols_to_drop = [col for col in cols_to_drop if col in df.columns]

    X_df = df.drop(columns=cols_to_drop)
    feature_names = X_df.columns.tolist()
    X = X_df.values

    logger.info(f"Features shape: {X.shape}, Target shape: {y.shape}")
    logger.info(f"Excluded columns: {config.exclude_columns}")
    logger.info(f"Selected {len(feature_names)} features")

    # ---- Train / val / test split --------------------------------------
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=config.test_size, random_state=config.random_state
    )

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
