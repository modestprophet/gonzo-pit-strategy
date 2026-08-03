"""
Experiment runner for executing training pipelines.
"""

import os
import time
from keras import callbacks
from dataclasses import dataclass
from typing import Dict, Any, Optional

import keras

from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import load_training_data, TrainingDataSource
from gonzo_pit_strategy.training.model_factory import build_model
from gonzo_pit_strategy.training.callbacks import (
    ConsoleMetricsCallback,
    EpochMetricsCallback,
)
from gonzo_pit_strategy.training.artifact import ArtifactManifest, ArtifactStore
from gonzo_pit_strategy.training.ledger import RunLedger
from gonzo_pit_strategy.config.config import PathsConfig
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    model_version: str
    model_id: Optional[int]
    run_id: Optional[int]
    test_loss: float
    test_metrics: Dict[str, float]
    history: Dict[str, Any]
    artifact_path: str


class Experiment:
    """
    Encapsulates the full lifecycle of a single model training process.
    Provides a deep module interface to run training from a configuration.

    Its two collaborators — the ArtifactStore and the Run Ledger — are injected
    rather than constructed here, so a test drives a real Experiment against a
    temp directory and an in-memory ledger with no patching.
    """

    def __init__(
        self,
        config: TrainingConfig,
        data_source: TrainingDataSource,
        artifact_store: ArtifactStore,
        ledger: RunLedger,
        config_path: Optional[str] = None,
        paths: Optional[PathsConfig] = None,
        environment: str = "local",
    ):
        self.config = config
        self.data_source = data_source
        self.artifact_store = artifact_store
        self.ledger = ledger
        self.config_path = config_path
        self.paths = paths or PathsConfig()
        self.environment = environment

    def run(self) -> ExperimentResult:
        """
        Execute a full training experiment based on the configuration.

        The order below is the contract, and it is why this is straight-line
        code rather than a set of callbacks: train, *then* evaluate, *then*
        write the Artifact from the model those metrics were measured on,
        *then* mirror it to the database. Expressed as `on_train_end`
        callbacks this ordering depended on list position against
        EarlyStopping's weight restore, and silently produced an Artifact that
        the reported metrics did not describe (ADR 0002).

        Returns:
            ExperimentResult object.
        """
        # 1. Load Data
        logger.info("Loading training data...")
        data = load_training_data(self.config, self.data_source)
        X_train, X_val, X_test = data.X_train, data.X_val, data.X_test
        y_train, y_val, y_test = data.y_train, data.y_val, data.y_test

        input_shape = X_train.shape[1:]
        output_shape = 1 if len(y_train.shape) == 1 else y_train.shape[1]

        logger.info(f"Input shape: {input_shape}, Output shape: {output_shape}")

        # 2. Build Model
        logger.info(f"Building {self.config.model.type} model...")
        model = build_model(self.config, input_shape, output_shape)
        model.summary()

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        model_version = f"{self.config.model.type}_{timestamp}"

        with self.ledger.run(self.config, environment=self.environment) as run:
            # 3. Setup Callbacks — per-epoch concerns only.
            cb_list = []

            if self.config.early_stopping_patience > 0:
                cb_list.append(
                    callbacks.EarlyStopping(
                        monitor="val_loss",
                        patience=self.config.early_stopping_patience,
                        restore_best_weights=True,
                        verbose=1,
                    )
                )

            cb_list.append(ConsoleMetricsCallback())

            # Injected paths (ADR 0001) — no os.getcwd() derivation
            log_dir = os.path.join(self.paths.tensorboard_dir, model_version)
            os.makedirs(log_dir, exist_ok=True)
            cb_list.append(
                callbacks.TensorBoard(
                    log_dir=log_dir, histogram_freq=1, write_graph=True, update_freq="epoch"
                )
            )

            cb_list.append(EpochMetricsCallback(run))

            # 4. Train
            logger.info(f"Starting training for {self.config.epochs} epochs...")
            history = model.fit(
                X_train,
                y_train,
                validation_data=(X_val, y_val),
                epochs=self.config.epochs,
                batch_size=self.config.batch_size,
                callbacks=cb_list,
                verbose=1,
            )

            # 5. Evaluate. EarlyStopping has restored the best weights by now
            # (it acts in on_train_end, which model.fit has already run), so
            # these metrics describe the model currently in memory.
            logger.info("Evaluating on test set...")
            # return_dict gives the real metric names. Zipping positionally
            # against `model.metrics_names` labels them 'compile_metrics'
            # under Keras 3, which was tolerable as a log line but not as the
            # manifest's permanent record of what was measured.
            evaluation = model.evaluate(X_test, y_test, verbose=1, return_dict=True)
            test_loss = float(evaluation["loss"])
            test_metrics = {
                name: float(value)
                for name, value in evaluation.items()
                if name != "loss"
            }

            logger.info(f"Test Loss: {test_loss}")
            logger.info(f"Test Metrics: {test_metrics}")

            # 6. Save the Artifact — the very model just evaluated.
            epochs_completed = len(next(iter(history.history.values()), []))
            manifest = ArtifactManifest(
                model_name="f1_pit_strategy_model",
                model_version=model_version,
                architecture=self.config.model.type,
                feature_names=data.feature_names,
                target_column=self.config.target_column,
                training_config=self.config.model_dump(mode="json"),
                framework_version=keras.__version__,
                dataset_name=data.provenance.name,
                dataset_fingerprint=data.provenance.fingerprint,
                epochs_completed=epochs_completed,
                test_metrics={"loss": float(test_loss), **test_metrics},
                created_by="Experiment",
                description=self.config.description or f"{self.config.model.type} model",
                tags=self.config.tags,
            )
            artifact_dir = self.artifact_store.save(model, manifest)

            # 7. Mirror to the database and close the run.
            run.complete(
                manifest,
                artifact_dir,
                data.provenance,
                epochs_completed=epochs_completed,
                config_source_path=self.config_path,
            )

            return ExperimentResult(
                model_version=model_version,
                model_id=run.model_id,
                run_id=run.run_id,
                test_loss=test_loss,
                test_metrics=test_metrics,
                history=history.history,
                artifact_path=str(artifact_dir),
            )
