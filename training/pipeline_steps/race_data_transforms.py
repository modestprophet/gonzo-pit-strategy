"""Pipeline step for race history data specific transforms."""
import pandas as pd
import numpy as np
from .base_step import PipelineStep
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)

def z_clip_cols(col):
  Q1 = col.quantile(0.25)
  Q3 = col.quantile(0.75)
  IQR = Q3 - Q1
  lower_range = Q1 - (1.5 * IQR)
  upper_range = Q3 + (1.5 * IQR)
  col[col < lower_range] = lower_range
  col[col > upper_range] = upper_range
  return col

class QualifyingTimeConverter(PipelineStep):
    """Pipeline step to convert qualifying times to seconds."""
    step_name = "qualifying_time_converter"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert qualifying time columns to seconds.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with added qualifying time columns in seconds.
        """
        columns = self.config.get("columns", ['q1', 'q2', 'q3']) # Allow columns to be configured.

        for col in columns:
            if col in df.columns: # Handle case where column might not be present
                # Replace whitespace-only strings with NaN
                df[col] = df[col].replace(r'^\s*$', np.nan, regex=True)
                # Create a missing indicator column
                df[f'{col}_missing'] = np.where(df[col].isnull(), 1, 0)
                # Convert to datetime objects
                try:
                    df[col] = pd.to_datetime(df[col], format='%M:%S.%f')
                    # Calculate seconds
                    df[f'{col}_seconds'] = df[col].dt.minute * 60 + df[col].dt.second + (df[col].dt.microsecond / 1000000)
                except ValueError as e:
                    logger.warning(f"Error converting column {col}: {e}. Skipping this column.")
                    # Potentially raise exception or return df as is
                    continue # For now, return df as is.  skip to next column
            else:
                logger.warning(f"Column '{col}' not found in DataFrame. Skipping.")

        return df