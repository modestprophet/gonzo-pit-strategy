"""Pipeline step for converting data types."""
import pandas as pd
from .base_step import PipelineStep
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)


class DataTypeConverter(PipelineStep):
    """Pipeline step for converting data types."""
    step_name = "data_type_converter"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert columns to appropriate data types.

        Args:
            df: Input DataFrame

        Returns:
            Processed DataFrame with converted data types
        """
        datetime_columns = self.config.get("datetime_columns", [])
        numeric_columns = self.config.get("numeric_columns", [])

        # Convert datetime columns
        for col in datetime_columns:
            if col in df.columns:
                try:
                    df[col] = pd.to_datetime(df[col])
                    logger.debug(f"Converted {col} to datetime")
                except Exception as e:
                    logger.warning(f"Could not convert {col} to datetime: {str(e)}")

        # Convert numeric columns
        for col in numeric_columns:
            if col in df.columns:
                try:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    logger.debug(f"Converted {col} to numeric")
                except Exception as e:
                    logger.warning(f"Could not convert {col} to numeric: {str(e)}")

        return df