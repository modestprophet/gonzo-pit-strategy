"""
Hyperparameter sweep execution and configuration.

This module owns the formal Sweep concept, generating permutations
of a base configuration and executing Experiments iteratively.
"""
import copy
import itertools
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    PrivateAttr,
    ValidationError,
    model_validator,
)

from gonzo_pit_strategy.config.config import PathsConfig
from gonzo_pit_strategy.training.artifact import ArtifactStore
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.data import TrainingDataSource
from gonzo_pit_strategy.training.ledger import RunLedger
from gonzo_pit_strategy.training.runner import Experiment, ExperimentResult

logger = logging.getLogger(__name__)


class SweepConfig(BaseModel):
    """A fully validated grid, prepared before execution dependencies are needed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_config: TrainingConfig
    parameters: dict[str, Any]
    sweep_name: str = "Grid Search"
    _configurations: tuple[TrainingConfig, ...] = PrivateAttr(default=())

    @model_validator(mode="after")
    def prepare(self) -> Self:
        base = TrainingConfig.model_validate(self.base_config.model_dump())
        axes = _grid_axes(base, self.parameters)
        configs = []
        combinations = itertools.product(*(choices for _, choices in axes))
        for index, combination in enumerate(combinations, start=1):
            settings = copy.deepcopy(base.model_dump())
            for (path, _), value in zip(axes, combination):
                parent = settings
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = copy.deepcopy(value)
            try:
                configs.append(TrainingConfig.model_validate(settings))
            except ValidationError as exc:
                raise ValueError(f"Combination {index} is invalid: {exc}") from exc
        self._configurations = tuple(configs)
        return self

    @property
    def total(self) -> int:
        return len(self._configurations)

    @property
    def configurations(self) -> tuple[TrainingConfig, ...]:
        return tuple(config.model_copy(deep=True) for config in self._configurations)


@dataclass
class SweepIterationResult:
    config: TrainingConfig
    index: int
    total: int
    failed: int
    result: ExperimentResult | None = None
    error: Exception | None = None

    @property
    def succeeded(self) -> int:
        return self.index - self.failed


def _grid_axes(
    base: BaseModel,
    grid: dict[str, Any],
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], list[Any]]]:
    axes = []
    for name, choices in grid.items():
        path = (*prefix, name)
        location = ".".join(path)
        if "." in name:
            raise ValueError(f"Use nested grid objects instead of dotted key {location!r}")
        if name not in type(base).model_fields:
            raise ValueError(f"Unknown grid field: {location}")
        if path == ("model", "type"):
            raise ValueError("Select the architecture in the base configuration, not the grid")
        field = getattr(base, name)
        if isinstance(field, BaseModel):
            if not isinstance(choices, dict):
                # Pydantic wraps ValueError, but lets TypeError escape validation.
                raise ValueError(f"{location} must be a nested grid object")  # noqa: TRY004
            axes.extend(_grid_axes(field, choices, path))
        else:
            if not isinstance(choices, list) or not choices:
                raise ValueError(f"{location} must be a nonempty list of candidate values")
            axes.append((path, choices))
    return axes


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
        config_path: str | None = None,
        paths: PathsConfig | None = None,
    ):
        self.config = config
        self.data_source = data_source
        self.artifact_store = artifact_store
        self.ledger = ledger
        self.config_path = config_path
        self.paths = paths

    def run(self) -> Iterator[SweepIterationResult]:
        """
        Execute the sweep, yielding results iteratively.
        """
        configs = self.config.configurations
        total = len(configs)

        logger.info(f"Generated {total} configurations for sweep: {self.config.sweep_name}")

        failed = 0
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
            except Exception as e:
                failed += 1
                logger.exception(f"Experiment {iteration_idx} failed")
                yield SweepIterationResult(
                    config=exp_config, index=iteration_idx, total=total,
                    failed=failed, error=e,
                )
            else:
                yield SweepIterationResult(
                    config=exp_config, index=iteration_idx, total=total,
                    failed=failed, result=result,
                )
