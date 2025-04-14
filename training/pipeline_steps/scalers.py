"""Pipeline step for scaling numerical features."""
import os
import pickle
from typing import Dict, Any

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler

from .base_step import PipelineStep
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)


class NumericalScaler(PipelineStep):
    """Pipeline step for scaling numerical variables."""
    step_name = "numerical_scaler"

    def __init__(self, config: Dict[str, Any]):
        """Initialize the scaler step.

        Args:
            config: Configuration dictionary with scaling settings
        """
        super().__init__(config)
        self.scalers: Dict[str, Any] = {}

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Scale numerical columns.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with scaled numerical columns
        """
        columns = self.config.get("columns", [])
        scaler_type = self.config.get("scaler", "standard")

        if not columns:
            logger.warning("No columns specified for scaling, skipping step")
            return df

        logger.info(f"Scaling {len(columns)} numerical columns with {scaler_type} scaler")

        result_df = df.copy()

        # Initialize the appropriate scaler
        if scaler_type == "standard":
            scaler_class = StandardScaler
        elif scaler_type == "minmax":
            scaler_class = MinMaxScaler
        elif scaler_type == "robust":
            scaler_class = RobustScaler
        else:
            logger.warning(f"Unknown scaler type: {scaler_type}, defaulting to StandardScaler")
            scaler_class = StandardScaler

        # Filter to only include columns that exist and are numeric
        valid_columns = [col for col in columns if col in df.columns]
        logger.debug(f"'valid_columns': {valid_columns}")
        numeric_columns = df[valid_columns].select_dtypes(include=np.number).columns.tolist()
        logger.debug(f"'numeric_columns': {numeric_columns}")

        if not numeric_columns:
            logger.warning("No valid numeric columns found for scaling")
            return df

        # For each numeric column, create and apply a scaler
        for col in numeric_columns:
            # Handle NaN values
            col_data = df[col].fillna(df[col].median())

            # Reshape for scikit-learn which expects 2D array
            X = col_data.values.reshape(-1, 1)

            # Initialize, fit, and transform
            scaler = scaler_class()
            scaled_values = scaler.fit_transform(X).flatten()

            # Store the scaler for later use
            self.scalers[col] = scaler

            # Update the result dataframe
            result_df[col] = scaled_values
            logger.debug(f"Scaled column: {col}")

        return result_df

    def save(self, path: str) -> None:
        """Save scalers to disk.

        Args:
            path: Directory path to save scalers
        """
        os.makedirs(path, exist_ok=True)

        # Save scalers
        scaler_path = os.path.join(path, 'numerical_scalers.pkl')
        with open(scaler_path, 'wb') as f:
            pickle.dump(self.scalers, f)

        logger.info(f"Saved {len(self.scalers)} numerical scalers to {scaler_path}")

    def load(self, path: str) -> None:
        """Load scalers from disk.

        Args:
            path: Directory path to load scalers from
        """
        scaler_path = os.path.join(path, 'numerical_scalers.pkl')

        # Load scalers
        with open(scaler_path, 'rb') as f:
            self.scalers = pickle.load(f)

        logger.info(f"Loaded {len(self.scalers)} numerical scalers from {scaler_path}")