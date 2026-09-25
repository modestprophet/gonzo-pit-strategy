import pytest

from conftest import StubDataSource
from fakes import InMemoryRunLedger
from gonzo_pit_strategy.config.config import PathsConfig
from gonzo_pit_strategy.training.artifact import ArtifactStore
from gonzo_pit_strategy.training.config import TrainingConfig
from gonzo_pit_strategy.training.sweep import Sweep, SweepConfig


def test_nested_grid_expands_each_combination_without_rewriting_settings():
    base = TrainingConfig(epochs=2, tags=["comparison"], description="Dense trial")
    sweep = SweepConfig(
        base_config=base,
        parameters={
            "learning_rate": [0.001, 0.0003],
            "model": {"hidden_layers": [[4], [8, 4]]},
        },
    )

    configs = sweep.configurations
    assert sweep.total == 4
    actual = []
    for config in configs:
        assert config.model.type == "dense"
        actual.append((config.learning_rate, config.model.hidden_layers))
    assert actual == [
        (0.001, [4]),
        (0.001, [8, 4]),
        (0.0003, [4]),
        (0.0003, [8, 4]),
    ]
    assert all(c.epochs == 2 for c in configs)
    assert all(c.tags == ["comparison"] for c in configs)
    assert all(c.description == "Dense trial" for c in configs)
    assert base.model.type == "dense"
    assert base.model.hidden_layers == [64, 32]


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({"learning_rate": []}, "learning_rate.*nonempty"),
        ({"model": {"hidden_layers": []}}, "model.hidden_layers.*nonempty"),
        ({"epochs": 2}, "epochs.*list"),
        ({"model": [{"hidden_layers": [4]}]}, "model.*nested grid object"),
        ({"model": {"hidden_layers": {"0": [4]}}}, "model.hidden_layers.*list"),
        ({"epoch": [2]}, "Unknown.*epoch"),
        ({"model": {"learning_rate": [0.2]}}, "Unknown.*model.learning_rate"),
        ({"model": {"lstm_units": [[4]]}}, "Unknown.*model.lstm_units"),
        ({"model_dump": [1]}, "Unknown.*model_dump"),
        ({"model.hidden_layers": [[4]]}, "nested.*dotted"),
        (
            {"model": {"hidden_layers": [[4]]}, "model.dropout_rate": [0.1]},
            "nested.*dotted",
        ),
        ({"model": {"type": ["dense"]}}, "architecture.*base"),
        ({"model": {"type": ["dense", "bilstm"]}}, "architecture.*base"),
    ],
)
def test_invalid_grid_structure_rejects_the_sweep(parameters, message):
    with pytest.raises(ValueError, match=message):
        SweepConfig(base_config=TrainingConfig(), parameters=parameters)


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        (
            {"test_size": [0.8], "validation_size": [0.1, 0.3]},
            "test_size + validation_size must be less than 1",
        ),
        ({"model": {"activation": ["relu", "not_an_activation"]}}, "not_an_activation"),
        ({"random_state": [42, -1]}, "random_state"),
    ],
)
def test_invalid_later_combination_rejects_the_whole_sweep(parameters, message):
    with pytest.raises(ValueError, match="Combination 2.*") as error:
        SweepConfig(base_config=TrainingConfig(), parameters=parameters)

    assert message in str(error.value)


@pytest.mark.parametrize("parameters", [{}, {"model": {}}])
def test_empty_grid_keeps_one_unchanged_base_configuration(parameters):
    base = TrainingConfig(tags=["control"], description="Base case")
    sweep = SweepConfig(base_config=base, parameters=parameters)

    assert sweep.total == 1
    assert sweep.configurations == (base,)


def test_bilstm_grid_uses_the_selected_architectures_fields():
    base = TrainingConfig.model_validate({"model": {"type": "bilstm"}})
    sweep = SweepConfig(
        base_config=base,
        parameters={"model": {"lstm_units": [[4], [8]], "dense_layers": [[]]}},
    )

    assert sweep.total == 2
    for config, units in zip(sweep.configurations, [[4], [8]], strict=True):
        assert config.model.type == "bilstm"
        assert config.model.lstm_units == units
        assert config.model.dense_layers == []


def test_prepared_configurations_do_not_share_mutable_inputs():
    base = TrainingConfig()
    layouts = [[4], [8]]
    sweep = SweepConfig(
        base_config=base, parameters={"model": {"hidden_layers": layouts}}
    )

    base.epochs = 0
    layouts[0].append(16)
    exposed = sweep.configurations
    exposed[0].epochs = 0
    exposed[0].tags.append("changed")
    first, second = sweep.configurations

    assert first.epochs == second.epochs == 100
    assert first.tags == second.tags == ["f1", "pit_strategy"]
    assert first.model.type == "dense"
    assert first.model.hidden_layers == [4]


def test_invalid_mutated_base_cannot_bypass_grid_validation():
    base = TrainingConfig()
    base.epochs = 0

    with pytest.raises(ValueError, match="epochs"):
        SweepConfig(base_config=base, parameters={})


def test_repeated_candidates_remain_separate_experiments():
    sweep = SweepConfig(
        base_config=TrainingConfig(), parameters={"learning_rate": [0.001, 0.001]}
    )

    assert sweep.total == 2
    assert [config.learning_rate for config in sweep.configurations] == [0.001, 0.001]


def test_failed_experiment_does_not_cancel_remaining_combinations(raw_dataset, tmp_path):
    base = TrainingConfig.model_validate(
        {"epochs": 1, "model": {"hidden_layers": [2]}, "exclude_columns": ["race_id"]}
    )
    config = SweepConfig(
        base_config=base,
        parameters={"target_column": ["finish_position", "missing", "finish_position"]},
    )
    store = ArtifactStore(tmp_path / "artifacts")
    ledger = InMemoryRunLedger()
    sweep = Sweep(
        config, StubDataSource(raw_dataset), store, ledger,
        paths=PathsConfig(tensorboard_dir=str(tmp_path / "tb")),
    )

    outcomes = list(sweep.run())

    assert [(outcome.index, outcome.total) for outcome in outcomes] == [(1, 3), (2, 3), (3, 3)]
    assert [(outcome.succeeded, outcome.failed) for outcome in outcomes] == [(1, 0), (1, 1), (2, 1)]
    first, failed, last = outcomes
    assert first.error is last.error is None
    assert isinstance(failed.error, ValueError)
    assert "missing" in str(failed.error)
    assert failed.result is None
    assert failed.config.target_column == "missing"
    assert len(ledger.runs) == 2
    assert all(run.status == "COMPLETED" for run in ledger.runs)
    for outcome in (first, last):
        assert outcome.result is not None
        _, manifest = store.load(outcome.result.model_version)
        assert manifest.training_config == outcome.config.model_dump(mode="json")
