"""
Hyperparameter sweep execution and configuration.

This module owns the formal Sweep concept, generating permutations
of a base configuration and executing Experiments iteratively.
"""
import copy
import itertools
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional
import logging

from pydantic import BaseModel, Field

from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.runner import Experiment, ExperimentResult
from gonzo_pit_strategy.training.data import TrainingDataSource
from gonzo_pit_strategy.training.artifact import ArtifactStore
from gonzo_pit_strategy.training.ledger import RunLedger
from gonzo_pit_strategy.config.config import PathsConfig

logger = logging.getLogger(__name__)


class SweepConfig(BaseModel):
    """Configuration for a hyperparameter sweep."""
    base_config: TrainingConfig
    parameters: Dict[str, List[Any]] = Field(
        description="Grid of parameters. Keys are dot-separated paths (e.g. 'model.learning_rate')."
    )
    sweep_name: str = "Grid Search"


@dataclass
class SweepIterationResult:
    config: TrainingConfig
    index: int
    total: int
    result: Optional[ExperimentResult] = None
    error: Optional[Exception] = None


def _set_nested_value(d: Dict[str, Any], keys: List[str], value: Any):
    """Recursively set a value in a nested dictionary."""
    if len(keys) == 1:
        d[keys[0]] = value
    else:
        if keys[0] not in d or not isinstance(d[keys[0]], dict):
            d[keys[0]] = {}
        _set_nested_value(d[keys[0]], keys[1:], value)


class Sweep:
    """
    Executes a collection of Experiments to explore a hyperparameter space.
    """

    def __init__(
        self,
        config: SweepConfig,
        data_source: TrainingDataSource,
        artifact_store: ArtifactStore,
        ledger: RunLedger,
        config_path: Optional[str] = None,
        paths: Optional[PathsConfig] = None,
    ):
        self.config = config
        self.data_source = data_source
        self.artifact_store = artifact_store
        self.ledger = ledger
        self.config_path = config_path
        self.paths = paths

    def _generate_configs(self) -> List[TrainingConfig]:
        keys = list(self.config.parameters.keys())
        values_list = list(self.config.parameters.values())

        configs = []
        base_dict = self.config.base_config.model_dump()

        for combination in itertools.product(*values_list):
            current_config_dict = copy.deepcopy(base_dict)
            param_desc = []

            for i, full_key in enumerate(keys):
                value = combination[i]
                key_parts = full_key.split(".")
                _set_nested_value(current_config_dict, key_parts, value)
                param_desc.append(f"{full_key}={value}")

            if "tags" not in current_config_dict:
                current_config_dict["tags"] = []
            if isinstance(current_config_dict["tags"], list) and "grid_search" not in current_config_dict["tags"]:
                current_config_dict["tags"].append("grid_search")

            desc = current_config_dict.get("description") or self.config.sweep_name
            current_config_dict["description"] = f"{desc} | {', '.join(param_desc)}"

            try:
                configs.append(TrainingConfig(**current_config_dict))
            except Exception as e:
                logger.error(f"Failed to create config for combination {combination}: {e}")

        return configs

    def run(self) -> Iterator[SweepIterationResult]:
        """
        Execute the sweep, yielding results iteratively.
        """
        configs = self._generate_configs()
        total = len(configs)

        logger.info(f"Generated {total} configurations for sweep: {self.config.sweep_name}")

        for i, exp_config in enumerate(configs):
            iteration_idx = i + 1
            try:
                experiment = Experiment(
                    config=exp_config,
                    data_source=self.data_source,
                    artifact_store=self.artifact_store,
                    ledger=self.ledger,
                    config_path=self.config_path,
                    paths=self.paths,
                )
                result = experiment.run()
                yield SweepIterationResult(
                    config=exp_config, index=iteration_idx, total=total, result=result
                )
            except Exception as e:
                logger.error(f"Experiment {iteration_idx} failed: {e}", exc_info=True)
                yield SweepIterationResult(
                    config=exp_config, index=iteration_idx, total=total, error=e
                )
