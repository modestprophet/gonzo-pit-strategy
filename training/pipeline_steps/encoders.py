"""Pipeline step for categorical encoding."""
import os
import pickle
from typing import Dict, List, Any, Optional

import pandas as pd
from sklearn.preprocessing import OneHotEncoder

from .base_step import PipelineStep
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)


class CategoricalEncoder(PipelineStep):
    """Pipeline step for encoding categorical variables."""
    step_name = "categorical_encoder"

    def __init__(self, config: Dict[str, Any]):
        """Initialize the encoder step.

        Args:
            config: Configuration dictionary with encoding settings
        """
        super().__init__(config)
        self.encoders: Dict[str, OneHotEncoder] = {}
        self.encoded_columns: Dict[str, List[str]] = {}

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Encode categorical columns.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with encoded categorical columns
        """
        columns = self.config.get("columns", [])
        drop_original = self.config.get("drop_original", True)
        sparse_output = self.config.get("sparse_output", False)
        handle_unknown = self.config.get("handle_unknown", "ignore")

        if not columns:
            logger.warning("No columns specified for encoding, skipping step")
            return df

        logger.info(f"Encoding {len(columns)} categorical columns")

        result_df = df.copy()

        for col in columns:
            if col not in df.columns:
                logger.warning(f"Column {col} not found in dataframe, skipping")
                continue

            # Reshape for OneHotEncoder which expects 2D array
            X = df[col].values.reshape(-1, 1)

            # Initialize and fit encoder
            encoder = OneHotEncoder(
                sparse_output=sparse_output,
                handle_unknown=handle_unknown,
                drop='first' if self.config.get("drop_first", True) else None
            )

            # Fit and transform
            encoded = encoder.fit_transform(X)

            # Get feature names
            if hasattr(encoder, 'get_feature_names_out'):
                feature_names = encoder.get_feature_names_out([col])
            else:
                # Fallback for older scikit-learn versions
                feature_names = [f"{col}_{cat}" for cat in encoder.categories_[0][1:]]

            # Convert to DataFrame
            if sparse_output:
                encoded_df = pd.DataFrame.sparse.from_spmatrix(
                    encoded,
                    index=df.index,
                    columns=feature_names
                )
            else:
                encoded_df = pd.DataFrame(
                    encoded,
                    index=df.index,
                    columns=feature_names
                )

            # Add encoded columns to result
            result_df = pd.concat([result_df, encoded_df], axis=1)

            # Store encoder and column names for later use
            self.encoders[col] = encoder
            self.encoded_columns[col] = feature_names.tolist()

            logger.debug(f"Encoded {col} into {len(feature_names)} features")

        # Drop original columns if specified
        if drop_original:
            cols_to_drop = [col for col in columns if col in result_df.columns]
            if cols_to_drop:
                result_df = result_df.drop(columns=cols_to_drop)
                logger.debug(f"Dropped original columns: {cols_to_drop}")

        return result_df

    def save(self, path: str) -> None:
        """Save encoders to disk.

        Args:
            path: Directory path to save encoders
        """
        os.makedirs(path, exist_ok=True)

        # Save encoders
        encoder_path = os.path.join(path, 'categorical_encoders.pkl')
        with open(encoder_path, 'wb') as f:
            pickle.dump(self.encoders, f)

        # Save column mapping information
        mapping_path = os.path.join(path, 'encoder_column_mapping.pkl')
        with open(mapping_path, 'wb') as f:
            pickle.dump(self.encoded_columns, f)

        logger.info(f"Saved {len(self.encoders)} categorical encoders to {encoder_path}")

    def load(self, path: str) -> None:
        """Load encoders from disk.

        Args:
            path: Directory path to load encoders from
        """
        encoder_path = os.path.join(path, 'categorical_encoders.pkl')
        mapping_path = os.path.join(path, 'encoder_column_mapping.pkl')

        # Load encoders
        with open(encoder_path, 'rb') as f:
            self.encoders = pickle.load(f)

        # Load column mapping
        with open(mapping_path, 'rb') as f:
            self.encoded_columns = pickle.load(f)

        logger.info(f"Loaded {len(self.encoders)} categorical encoders from {encoder_path}")


class LabelEncoderStep(PipelineStep):
    """Pipeline step for label encoding categorical variables."""
    step_name = "label_encoder"

    def __init__(self, config: Dict[str, Any]):
        """Initialize the label encoder step.

        Args:
            config: Configuration dictionary with encoding settings
        """
        super().__init__(config)
        self.encoders: Dict[str, Any] = {}
        self.classes_: Dict[str, List[str]] = {}
        self.unknown_value = self.config.get("unknown_value", None)

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Label encode categorical columns.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with label encoded columns
        """
        from sklearn.preprocessing import LabelEncoder
        import numpy as np

        columns = self.config.get("columns", [])
        drop_original = self.config.get("drop_original", True)

        if not columns:
            logger.warning("No columns specified for label encoding, skipping step")
            return df

        logger.info(f"Label encoding {len(columns)} categorical columns")

        result_df = df.copy()

        for col in columns:
            if col not in result_df.columns:
                logger.warning(f"Column {col} not found in dataframe, skipping")
                continue

            # Initialize and fit encoder
            encoder = LabelEncoder()
            encoder.fit(result_df[col].astype(str).dropna())

            # Store classes for unknown handling
            self.classes_[col] = list(encoder.classes_)

            # Transform data with unknown handling
            encoded_values = []
            unknown_count = 0

            for val in result_df[col].astype(str):
                if val == 'nan' or val in encoder.classes_:
                    if val == 'nan':
                        encoded_values.append(np.nan)
                    else:
                        encoded_values.append(encoder.transform([val])[0])
                else:
                    unknown_count += 1
                    # Handle unknown based on config
                    if self.unknown_value is not None:
                        encoded_values.append(self.unknown_value)
                    else:
                        encoded_values.append(np.nan)

            if unknown_count > 0:
                logger.warning(f"Found {unknown_count} unknown values in column {col}. " +
                               (f"Replaced with {self.unknown_value}"
                                if self.unknown_value is not None
                                else "Set to NaN"))

            # Replace or add column
            new_col_name = col if drop_original else f"{col}_encoded"
            result_df[new_col_name] = encoded_values

            # Store encoder
            self.encoders[col] = encoder

            logger.debug(f"Label encoded column {col} with {len(encoder.classes_)} classes")

            # Drop original column if specified
            if drop_original and new_col_name != col:
                result_df = result_df.drop(columns=[col])

        return result_df

    def save(self, path: str) -> None:
        """Save encoders and class mappings to disk.

        Args:
            path: Directory path to save encoders
        """
        os.makedirs(path, exist_ok=True)

        # Save encoders
        encoder_path = os.path.join(path, 'label_encoders.pkl')
        with open(encoder_path, 'wb') as f:
            pickle.dump(self.encoders, f)

        # Save class mappings
        classes_path = os.path.join(path, 'label_encoder_classes.pkl')
        with open(classes_path, 'wb') as f:
            pickle.dump(self.classes_, f)

        # Save configuration settings including unknown_value
        config_path = os.path.join(path, 'label_encoder_config.pkl')
        with open(config_path, 'wb') as f:
            pickle.dump({
                'unknown_value': self.unknown_value
            }, f)

        logger.info(f"Saved {len(self.encoders)} label encoders to {encoder_path}")

    def load(self, path: str) -> None:
        """Load encoders and class mappings from disk.

        Args:
            path: Directory path to load encoders from
        """
        encoder_path = os.path.join(path, 'label_encoders.pkl')
        classes_path = os.path.join(path, 'label_encoder_classes.pkl')
        config_path = os.path.join(path, 'label_encoder_config.pkl')

        # Load encoders
        with open(encoder_path, 'rb') as f:
            self.encoders = pickle.load(f)

        # Load class mappings
        with open(classes_path, 'rb') as f:
            self.classes_ = pickle.load(f)

        # Load configuration if available
        if os.path.exists(config_path):
            with open(config_path, 'rb') as f:
                config_data = pickle.load(f)
                self.unknown_value = config_data.get('unknown_value', self.unknown_value)

        logger.info(f"Loaded {len(self.encoders)} label encoders from {encoder_path}")