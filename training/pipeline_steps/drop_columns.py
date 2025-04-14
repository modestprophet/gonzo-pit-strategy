import pandas as pd
import numpy as np
from .base_step import PipelineStep
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)


class DropColumns(PipelineStep):
    """
    Drops the columns specified in the config.
    Config should include a 'columns' key with a list of column names to drop.
    """
    step_name = "drop_columns"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop specified columns from the DataFrame.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with specified columns removed
        """
        columns_to_drop = self.config.get('columns', [])

        if not columns_to_drop:
            logger.warning("No columns specified to drop in config")
            return df

        # Check if any specified columns don't exist in the DataFrame
        missing_columns = set(columns_to_drop) - set(df.columns)
        if missing_columns:
            logger.warning(f"Columns not found in DataFrame: {missing_columns}")

        # Drop only columns that exist in the DataFrame
        columns_to_drop = [col for col in columns_to_drop if col in df.columns]
        logger.debug(f"Columns dropped: {columns_to_drop}")
        logger.debug(f"Numeric columns: {df.select_dtypes(include=np.number).columns.tolist()}")

        return df.drop(columns=columns_to_drop, errors='ignore')