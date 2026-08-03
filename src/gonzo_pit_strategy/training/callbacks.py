"""Keras callbacks for model training.

Only per-epoch work belongs here. Everything that happens once, at the start or
end of an Experiment — opening the Training Run, saving the Artifact, mirroring
it to the database — is sequential code in `runner.Experiment.run`, because
ordering between callbacks is invisible at the call site and got the Artifact
written from the wrong weights once already (ADR 0002).
"""

from typing import Any, Dict

import keras

from gonzo_pit_strategy.training.ledger import RunRecorder
import logging

logger = logging.getLogger(__name__)


class EpochMetricsCallback(keras.callbacks.Callback):
    """Streams each epoch's metrics to the Run Ledger.

    This is the one part of the lifecycle that must be a callback: nothing
    outside the training loop can see an epoch boundary.
    """

    def __init__(self, run: RunRecorder):
        super().__init__()
        self.run = run

    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        if logs:
            self.run.record_epoch(epoch, logs)


class ConsoleMetricsCallback(keras.callbacks.Callback):
    """Pretty-prints metrics to stdout at each epoch end."""

    def on_epoch_end(self, epoch: int, logs: Dict[str, Any] = None) -> None:
        if not logs:
            return
        epoch_str = f"Epoch {epoch + 1}"
        print(f"\n{epoch_str}")
        print("-" * len(epoch_str))
        train_metrics = {k: v for k, v in logs.items() if not k.startswith("val_")}
        val_metrics = {k.replace("val_", ""): v for k, v in logs.items() if k.startswith("val_")}
        if train_metrics:
            print("Training:")
            for name, value in train_metrics.items():
                print(f"  {name}: {value:.4f}")
        if val_metrics:
            print("Validation:")
            for name, value in val_metrics.items():
                print(f"  {name}: {value:.4f}")
        print()
