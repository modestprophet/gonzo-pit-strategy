"""Pipeline step for race history data specific transforms."""
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from .base_step import PipelineStep
from gonzo_pit_strategy.log.logger import get_console_logger

logger = get_console_logger(__name__)



class SeasonProgress(PipelineStep):
    """
    Calculates the round number as a percentage of the relative season complete
    """
    step_name = "season_progress"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        df['season_progress_percent'] = df['roundnumber'] / df.groupby(['raceyear'])['roundnumber'].transform('max')
        return df


class QualifyingTimeConverter(PipelineStep):
    """
    Converts qualifying time columns from string format to seconds.
    Configurable Options:
        - columns (List[str]): List of qualifying time columns to process (default: ['q1', 'q2', 'q3']).
            These should be in 'M:S.fff' format (e.g., '1:23.456').

    Creates:
        For each qualifying time column:
        - {col}_seconds: Numeric column containing the time in seconds
        - {col}_missing: Binary indicator (1 = missing, 0 = present)
        """
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
                # df[f'{col}_missing'] = np.where(df[col].isnull(), 1, 0)
                df[f'{col}_missing'] = np.where(df[col] == "0:00.000", 1, 0)
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


class LaggedFeatureGenerator(PipelineStep):
    """
    Generates lagged features based on grouping and sorting criteria.

    This step shifts specified columns by a defined period within groups,
    useful for creating features based on previous time steps (e.g., previous race results).

    Configurable Options:
        - lag_columns (List[str]): Columns to shift.
        - group_columns (List[str]): Columns to group by before shifting.
        - sort_column (str): Column to sort by within groups before shifting (e.g., 'roundnumber').
        - shift_period (int): Number of periods to shift (default: 1). Positive shifts data backward (past values).
        - fill_value (Any): Value to fill NaNs introduced by the shift (default: 0).
        - new_col_prefix (str): Prefix for the newly created lagged columns (default: "lagged_").
        - numeric_lagged_cols (List[str]): Original column names (subset of lag_columns) whose
                                           lagged versions should be explicitly converted to numeric.
    """
    step_name = "lagged_feature_generator"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies the lagging operation to the DataFrame.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with new lagged feature columns added.

        Raises:
            ValueError: If required configuration keys are missing.
            KeyError: If specified columns are not found in the DataFrame.
        """
        lag_cols: List[str] = self.config.get("lag_columns")
        group_cols: List[str] = self.config.get("group_columns")
        sort_cols: str = self.config.get("sort_columns")
        shift_period: int = self.config.get("shift_period", 1)
        fill_value: Any = self.config.get("fill_value", 0)
        new_col_prefix: str = self.config.get("new_col_prefix", "lagged_")
        drop_original = self.config.get("drop_original", True)
        numeric_lagged_cols: List[str] = self.config.get("numeric_lagged_cols", [])

        # --- Validation ---
        if not lag_cols or not group_cols or not sort_cols:
            msg = "Missing required config: 'lag_columns', 'group_columns', 'sort_column'"
            logger.error(msg)
            raise ValueError(msg)

        required_df_cols = set(lag_cols + group_cols + sort_cols)
        missing_cols = required_df_cols - set(df.columns)
        if missing_cols:
            msg = f"DataFrame is missing required columns: {missing_cols}"
            logger.error(msg)
            raise KeyError(msg)
        # --- End Validation ---

        logger.info(
            f"Generating {shift_period}-period lagged features for {lag_cols} "
            f"grouped by {group_cols}, sorted by {sort_cols}."
        )

        # Create a copy to avoid SettingWithCopyWarning
        df = df.copy()

        # Sort the DataFrame by group and sort columns (using assignment instead of inplace)
        df = df.sort_values(by=group_cols + sort_cols, kind='mergesort')

        # Generate lagged columns directly in the DataFrame
        for col in lag_cols:
            new_col_name = f"{new_col_prefix}{col}"
            # Assign shifted values directly
            shifted_values = df.groupby(group_cols, observed=True, sort=False)[col].shift(shift_period)
            df[new_col_name] = shifted_values.fillna(fill_value)

            # Convert to numeric if specified
            if col in numeric_lagged_cols:
                df[new_col_name] = pd.to_numeric(df[new_col_name], errors='coerce').fillna(fill_value)
                logger.debug(f"Ensured column '{new_col_name}' is numeric.")

        # Drop original columns if specified
        if drop_original:
            cols_to_drop = [col for col in lag_cols if col in df.columns]
            if cols_to_drop:
                df = df.drop(columns=cols_to_drop)
                logger.debug(f"Dropped original columns: {cols_to_drop}")

        logger.info(f"Generated lagged columns: {[f'{new_col_prefix}{col}' for col in lag_cols]}")
        return df

    def get_description(self) -> str:
        """Get description including key config parameters."""
        desc = (
            f"{self.name}: "
            f"lag_cols={self.config.get('lag_columns')}, "
            f"group_cols={self.config.get('group_columns')}, "
            f"sort_col={self.config.get('sort_column')}, "
            f"shift={self.config.get('shift_period', 1)}"
        )
        return desc


class ZScoreClipper(PipelineStep):
    """Clip dataframe values above a certain Z-Score to remove outliers.

    Configurable Options:
        - columns (List[str]): List of columns to process (default: all numeric columns)
        - z_threshold (float): Maximum Z-Score above which values should be clipped (default=3)
        - clipped_value (Optional[float]): Replace outliers with this value. If None, uses the
          maximum column value below the z_threshold
    """
    step_name = "z_score_clipper"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process the dataframe by clipping values above the specified Z-Score.

        Args:
            df: Input DataFrame

        Returns:
            DataFrame with clipped values
        """
        columns = self.config.get("columns")
        z_threshold = float(self.config.get("z_threshold", 3.0))
        clipped_value = self.config.get("clipped_value")

        if columns is None:
            # If no columns specified, use all numeric columns
            columns = df.select_dtypes(include=np.number).columns.tolist()
            logger.info(f"No columns specified in config. Using all numeric columns: {columns}")

        for col in columns:
            if col not in df.columns:
                logger.warning(f"Column '{col}' not found in DataFrame. Skipping.")
                continue

            if not pd.api.types.is_numeric_dtype(df[col]):
                logger.warning(f"Column '{col}' is not numeric. Skipping.")
                continue

            # Calculate Z-scores
            z_scores = (df[col] - df[col].mean()) / df[col].std()

            # Determine clipping value
            if clipped_value is None:
                current_clipped_value = df.loc[z_scores < z_threshold, col].max()
            else:
                current_clipped_value = clipped_value

            # Clip values
            outlier_mask = z_scores > z_threshold
            if outlier_mask.any():
                logger.debug(f"Clipping {outlier_mask.sum()} outliers in column '{col}'")
                df.loc[outlier_mask, col] = current_clipped_value

        return df


