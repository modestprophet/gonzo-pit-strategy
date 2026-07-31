"""
Data loading and preprocessing for training.

This module owns the seam between raw data extraction and ML-ready feature
engineering.  The `TrainingDataSource` Protocol defines the interface; concrete
adapters (e.g. `DatabaseDataSource`) satisfy it.
"""

import hashlib
from dataclasses import dataclass

import pandas as pd
import numpy as np
from sqlalchemy import text
from typing import Protocol, List

from sklearn.model_selection import train_test_split

from gonzo_pit_strategy.training.config import TrainingConfig
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
        df.attrs["source_query"] = self._query
        logger.info(f"RawDataset shape: {df.shape}")
        return df


# ---------------------------------------------------------------------------
# Dataset fingerprint
# ---------------------------------------------------------------------------


def fingerprint_dataset(df: RawDataset, query: str = "") -> str:
    """Content fingerprint of a RawDataset: same data -> same fingerprint.

    Hashes the schema (column names + dtypes), row count, a content digest,
    and the source query text. Identifies a DatasetVersion without any
    upstream (dbt) cooperation.
    """
    h = hashlib.sha256()
    h.update(query.encode())
    h.update(str(len(df)).encode())
    for col, dtype in zip(df.columns, df.dtypes):
        h.update(f"{col}:{dtype};".encode())
    h.update(str(int(pd.util.hash_pandas_object(df, index=False).sum())).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# load_training_data – the deepened module
# ---------------------------------------------------------------------------


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a RawDataset's columns into the numeric form Keras requires.

    Shared by training and inference: the Artifact Manifest pins *which*
    columns a model expects and in what order, and this function pins *how*
    their values are encoded. Applying it in only one of the two places is
    train/serve skew — the model would see booleans at inference where it saw
    integers during training.

    Postgres hands back `object` dtype for all-NULL numeric columns and `bool`
    for the dbt one-hot columns (`prep_ohe_*`), neither of which Keras accepts.
    """
    df = df.copy()

    object_cols = df.select_dtypes(include=["object"]).columns.tolist()
    if object_cols:
        logger.info(f"Coercing {len(object_cols)} object columns to numeric: {object_cols}")
        for col in object_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    bool_cols = df.select_dtypes(include=["bool", "boolean"]).columns.tolist()
    if bool_cols:
        logger.info(f"Converting {len(bool_cols)} boolean columns to integers")
        df[bool_cols] = df[bool_cols].astype(int)

    nan_count = int(df.isnull().sum().sum())
    if nan_count:
        nan_cols = df.columns[df.isnull().any()].tolist()
        logger.info(f"Filling {nan_count} NaN values with 0 in columns: {nan_cols}")
        df = df.fillna(0.0)

    return df


@dataclass
class LoadedData:
    """ML-ready splits plus the provenance needed for the Artifact Manifest
    and DatasetVersion record."""

    X_train: np.ndarray
    X_val: np.ndarray
    X_test: np.ndarray
    y_train: np.ndarray
    y_val: np.ndarray
    y_test: np.ndarray
    feature_names: List[str]
    dataset_fingerprint: str
    record_count: int
    feature_count: int


def load_training_data(
    config: TrainingConfig,
    data_source: TrainingDataSource,
) -> LoadedData:
    """
    Transform a RawDataset into train / validation / test splits.

    All data *extraction* is delegated to ``data_source``; this function is
    purely responsible for feature engineering, NaN handling, and splitting.
    It also fingerprints the RawDataset so the Experiment can record which
    data it trained on.

    Args:
        config: TrainingConfig with target column, exclusions, split sizes.
        data_source: Any object satisfying the TrainingDataSource protocol.

    Returns:
        LoadedData with splits, feature_names (training order), and the
        dataset fingerprint.
    """
    # ---- Fetch ----------------------------------------------------------
    df: RawDataset = data_source.fetch_raw_data()
    logger.info(f"Data shape: {df.shape}")

    dataset_fingerprint = fingerprint_dataset(df, df.attrs.get("source_query", ""))
    record_count = len(df)

    # ---- Feature engineering --------------------------------------------
    # Identical encoding is applied at inference time (see prepare_features).
    df = prepare_features(df)

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

    return LoadedData(
        X_train=X_train,
        X_val=X_val,
        X_test=X_test,
        y_train=y_train,
        y_val=y_val,
        y_test=y_test,
        feature_names=feature_names,
        dataset_fingerprint=dataset_fingerprint,
        record_count=record_count,
        feature_count=len(feature_names),
    )
