"""Pipeline step for handling null values."""
import pandas as pd
import numpy as np
from .base_step import PipelineStep
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)


class NullValueCleaner(PipelineStep):
    """Pipeline step for handling null/missing values."""
    step_name = "null_value_cleaner"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean null values from dataframe.

        Args:
            df: Input DataFrame

        Returns:
            Processed DataFrame with null values handled
        """
        strategy = self.config.get("strategy", "drop_rows")
        columns = self.config.get("columns", df.columns.tolist())
        threshold = self.config.get("threshold", 0.5)

        logger.info(f"Handling null values with strategy: {strategy}")

        if strategy == "drop_rows":
            # Only drop rows where specified columns have nulls
            if columns:
                initial_len = len(df)
                df = df.dropna(subset=columns)
                dropped = initial_len - len(df)
                logger.info(f"Dropped {dropped} rows with null values in specified columns.")

        elif strategy == "drop_columns":
            # Drop columns with more than threshold% nulls
            null_counts = df[columns].isnull().mean()
            cols_to_drop = null_counts[null_counts > threshold].index.tolist()
            if cols_to_drop:
                logger.info(f"Dropping columns with >={threshold * 100}% nulls: {cols_to_drop}")
                df = df.drop(columns=cols_to_drop)

        elif strategy == "fill_mean":
            # Fill numeric columns with mean
            numeric_cols = df[columns].select_dtypes(include=np.number).columns
            for col in numeric_cols:
                df[col] = df[col].fillna(df[col].mean())
            logger.info(f"Filled null values with mean in numeric columns: {numeric_cols.tolist()}")

        elif strategy == "fill_median":
            # Fill numeric columns with median
            numeric_cols = df[columns].select_dtypes(include=np.number).columns
            for col in numeric_cols:
                df[col] = df[col].fillna(df[col].median())
            logger.info(f"Filled null values with median in numeric columns: {numeric_cols.tolist()}")

        elif strategy == "fill_mode":
            # Fill categorical columns with mode
            cat_cols = df[columns].select_dtypes(exclude=np.number).columns
            for col in cat_cols:
                df[col] = df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else "UNKNOWN")
            logger.info(f"Filled null values with mode in categorical columns: {cat_cols.tolist()}")

        elif strategy == "fill_custom":
            # Fill with custom values from config
            fill_values = self.config.get("fill_values", {})
            for col, value in fill_values.items():
                if col in df.columns:
                    df[col] = df[col].fillna(value)
                else:
                    logger.warning(f"Column not found in dataframe:v{col}")
            logger.info(f"Filled null values with custom values in columns: {list(fill_values.keys())}")

        return df