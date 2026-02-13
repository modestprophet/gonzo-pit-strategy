from typing import List, Literal, Union, Optional
from pydantic import BaseModel, Field

# --- Model Specific Configs ---


class DenseModelConfig(BaseModel):
    """Configuration for Dense Neural Network models."""

    type: Literal["dense"] = "dense"
    hidden_layers: List[int] = Field(
        default=[64, 32], description="Units per hidden layer"
    )
    dropout_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    activation: str = "relu"
    output_activation: str = "linear"


class BiLSTMModelConfig(BaseModel):
    """Configuration for Bidirectional LSTM models."""

    type: Literal["bilstm"] = "bilstm"
    lstm_units: List[int] = Field(default=[64, 32], description="Units per LSTM layer")
    dense_layers: List[int] = Field(
        default=[32], description="Units per dense layer after LSTM"
    )
    dropout_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    recurrent_dropout: float = Field(default=0.2, ge=0.0, le=1.0)
    activation: str = "relu"
    output_activation: str = "linear"


ModelConfig = Union[DenseModelConfig, BiLSTMModelConfig]

# --- Main Training Config ---


class TrainingConfig(BaseModel):
    """Master configuration for training runs."""

    # Data params
    target_column: str = "finish_position"
    exclude_columns: List[str] = Field(
        default_factory=list, description="Columns to exclude from training"
    )
    test_size: float = Field(default=0.2, ge=0.0, le=1.0)
    validation_size: float = Field(default=0.1, ge=0.0, le=1.0)
    random_state: int = 42

    # Model params (Polymorphic!)
    model: ModelConfig = Field(default_factory=DenseModelConfig)

    # Training Loop params
    batch_size: int = 32
    epochs: int = 100
    learning_rate: float = 0.001
    early_stopping_patience: int = 10

    # Logging
    tags: List[str] = Field(default_factory=lambda: ["f1", "pit_strategy"])
    description: Optional[str] = None
