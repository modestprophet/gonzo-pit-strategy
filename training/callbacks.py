"""
Custom TensorFlow callbacks for model training.
"""
from typing import Dict, Any, Optional
import tensorflow as tf
from datetime import datetime

from db.models.training_metrics import TrainingMetric
from db.base import db_session


class MetricsLoggingCallback(tf.keras.callbacks.Callback):
    """
    Callback for logging training metrics to the database.

    This callback logs metrics at the end of each epoch to the database,
    preserving the training history for later analysis.
    """

    def __init__(self, run_id: int, split_types: Optional[Dict[str, str]] = None):
        """
        Initialize the metrics logging callback.

        Args:
            run_id: The training run ID to associate metrics with
            split_types: Optional mapping of metric prefixes to split types
                         (e.g., {'val_': 'VALIDATION', '': 'TRAIN'})
        """
        super().__init__()
        self.run_id = run_id
        self.split_types = split_types or {'val_': 'VALIDATION', '': 'TRAIN'}

    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        """
        Log metrics at the end of each epoch.

        Args:
            epoch: Current epoch number
            logs: Dictionary containing metrics
        """
        if not logs:
            return

        metrics = []
        timestamp = datetime.now()

        for metric_name, metric_value in logs.items():
            # Determine split type
            split_type = 'TRAIN'  # Default
            for prefix, split in self.split_types.items():
                if metric_name.startswith(prefix):
                    split_type = split
                    # Remove prefix from metric name if it's a validation metric
                    if prefix and prefix != '':
                        metric_name = metric_name[len(prefix):]
                    break

            metrics.append(
                TrainingMetric(
                    run_id=self.run_id,
                    epoch=epoch,
                    timestamp=timestamp,
                    metric_name=metric_name,
                    metric_value=float(metric_value),
                    split_type=split_type
                )
            )

        # Store all metrics for this epoch in a single transaction
        with db_session() as session:
            session.add_all(metrics)
            session.commit()


class ConsoleMetricsCallback(tf.keras.callbacks.Callback):
    """
    Callback for pretty-printing metrics to the console.
    """

    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        """
        Print metrics at the end of each epoch.

        Args:
            epoch: Current epoch number
            logs: Dictionary containing metrics
        """
        if not logs:
            return

        # Format epoch number
        epoch_str = f"Epoch {epoch + 1}"
        print(f"\n{epoch_str}")
        print("-" * len(epoch_str))

        # Group metrics by split type
        train_metrics = {k: v for k, v in logs.items() if not k.startswith('val_')}
        val_metrics = {k.replace('val_', ''): v for k, v in logs.items() if k.startswith('val_')}

        # Print training metrics
        if train_metrics:
            print("Training:")
            for name, value in train_metrics.items():
                print(f"  {name}: {value:.4f}")

        # Print validation metrics
        if val_metrics:
            print("Validation:")
            for name, value in val_metrics.items():
                print(f"  {name}: {value:.4f}")

        print()  # Add a newline for separation