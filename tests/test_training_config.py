import pytest
from pydantic import ValidationError

from gonzo_pit_strategy.training.config import TrainingConfig


@pytest.mark.parametrize(
    "settings",
    [
        {"epoch": 2},
        {"model": {"type": "dense", "learning_rate": 0.2}},
        {"model": {"type": "bilstm", "hidden_layers": [8]}},
    ],
)
def test_unknown_training_fields_are_rejected(settings):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TrainingConfig.model_validate(settings)


@pytest.mark.parametrize(
    "settings",
    [
        {"epochs": 0},
        {"batch_size": -1},
        {"learning_rate": 0},
        {"learning_rate": float("inf")},
        {"learning_rate": float("nan")},
        {"test_size": 0},
        {"validation_size": 0},
        {"test_size": 0.8, "validation_size": 0.3},
        {"test_size": 0.8, "validation_size": 0.2},
        {"model": {"type": "dense", "hidden_layers": [0]}},
        {"model": {"type": "dense", "dropout_rate": 1}},
        {"model": {"type": "bilstm", "lstm_units": []}},
        {"model": {"type": "bilstm", "lstm_units": [-1]}},
        {"model": {"type": "bilstm", "dense_layers": [-1]}},
        {"model": {"type": "bilstm", "recurrent_dropout": 1}},
    ],
)
def test_invalid_training_values_are_rejected_before_execution(settings):
    with pytest.raises(ValidationError):
        TrainingConfig.model_validate(settings)


def test_optional_dense_layers_and_disabled_early_stopping_remain_valid():
    config = TrainingConfig.model_validate(
        {"model": {"type": "dense", "hidden_layers": []}, "early_stopping_patience": 0}
    )
    assert config.model.type == "dense"
    assert config.model.hidden_layers == []
    assert config.early_stopping_patience == 0


@pytest.mark.parametrize("architecture", ["dense", "bilstm"])
@pytest.mark.parametrize("field", ["activation", "output_activation"])
def test_unknown_activation_names_are_rejected(architecture, field):
    with pytest.raises(ValidationError, match="not_an_activation"):
        TrainingConfig.model_validate(
            {"model": {"type": architecture, field: "not_an_activation"}}
        )


@pytest.mark.parametrize("seed", [-1, 2**32])
def test_invalid_random_seed_is_rejected(seed):
    with pytest.raises(ValidationError, match="random_state"):
        TrainingConfig(random_state=seed)
