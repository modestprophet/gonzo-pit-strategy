from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    model_validator,
)


def _validate_activation(name: str) -> str:
    from keras import activations

    activations.get(name)
    return name


ActivationName = Annotated[str, AfterValidator(_validate_activation)]


class DenseModelConfig(BaseModel):
    """Configuration for Dense Neural Network models."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["dense"] = "dense"
    hidden_layers: list[PositiveInt] = Field(
        default=[64, 32], description="Units per hidden layer"
    )
    dropout_rate: float = Field(default=0.2, ge=0.0, lt=1.0)
    activation: ActivationName = "relu"
    output_activation: ActivationName = "linear"


class BiLSTMModelConfig(BaseModel):
    """Configuration for Bidirectional LSTM models."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["bilstm"] = "bilstm"
    lstm_units: list[PositiveInt] = Field(
        default=[64, 32], min_length=1, description="Units per LSTM layer"
    )
    dense_layers: list[PositiveInt] = Field(
        default=[32], description="Units per dense layer after LSTM"
    )
    dropout_rate: float = Field(default=0.2, ge=0.0, lt=1.0)
    recurrent_dropout: float = Field(default=0.2, ge=0.0, lt=1.0)
    activation: ActivationName = "relu"
    output_activation: ActivationName = "linear"


ModelConfig = DenseModelConfig | BiLSTMModelConfig


class TrainingConfig(BaseModel):
    """Master configuration for training runs."""

    model_config = ConfigDict(extra="forbid")

    target_column: str = "finish_position"
    exclude_columns: list[str] = Field(
        default_factory=list, description="Columns to exclude from training"
    )
    test_size: float = Field(default=0.2, gt=0.0, lt=1.0)
    validation_size: float = Field(default=0.1, gt=0.0, lt=1.0)
    random_state: int = Field(default=42, ge=0, le=2**32 - 1)

    model: ModelConfig = Field(default_factory=DenseModelConfig)

    batch_size: PositiveInt = 32
    epochs: PositiveInt = 100
    learning_rate: float = Field(default=0.001, gt=0.0, allow_inf_nan=False)
    early_stopping_patience: int = 10

    tags: list[str] = Field(default_factory=lambda: ["f1", "pit_strategy"])
    description: str | None = None

    @model_validator(mode="after")
    def require_training_split(self) -> Self:
        if self.test_size + self.validation_size >= 1:
            raise ValueError("test_size + validation_size must be less than 1")
        return self
