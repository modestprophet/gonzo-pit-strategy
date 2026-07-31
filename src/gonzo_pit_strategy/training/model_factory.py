"""
Factory for building Keras models based on Pydantic configurations.
"""

import keras
from keras import layers, models, optimizers
from typing import Tuple

from gonzo_pit_strategy.training.config import (
    TrainingConfig,
    DenseModelConfig,
    BiLSTMModelConfig,
)


def build_model(
    config: TrainingConfig, input_shape: Tuple[int, ...], output_shape: int
) -> keras.Model:
    """
    Build and compile a Keras model based on the training configuration.

    Args:
        config: Full TrainingConfig object.
        input_shape: Shape of the input features (e.g. (10,)).
        output_shape: Number of output units (e.g. 1 for regression).

    Returns:
        Compiled Keras model.
    """
    model_conf = config.model

    if model_conf.type == "dense":
        model = _build_dense(model_conf, input_shape, output_shape)
    elif model_conf.type == "bilstm":
        model = _build_bilstm(model_conf, input_shape, output_shape)
    else:
        raise ValueError(f"Unsupported model type: {model_conf.type}")

    # Compile model using training loop params from the main config
    model.compile(
        optimizer=optimizers.Adam(learning_rate=config.learning_rate),
        loss="mse",  # Defaulting to MSE for now, could be in config
        metrics=["mae"],
    )

    return model


def _build_dense(
    conf: DenseModelConfig, input_shape: Tuple[int, ...], output_shape: int
) -> keras.Model:
    inputs = layers.Input(shape=input_shape)
    x = inputs

    for units in conf.hidden_layers:
        x = layers.Dense(units, activation=conf.activation)(x)
        x = layers.Dropout(conf.dropout_rate)(x)

    outputs = layers.Dense(output_shape, activation=conf.output_activation)(x)

    return models.Model(inputs=inputs, outputs=outputs, name="dense_model")


def _build_bilstm(
    conf: BiLSTMModelConfig, input_shape: Tuple[int, ...], output_shape: int
) -> keras.Model:
    # LSTM needs 3D input (batch, time, features). `load_training_data` produces
    # 2D (rows, features), so each row is treated as a length-1 sequence.
    inputs = layers.Input(shape=input_shape)
    x = inputs

    if len(input_shape) == 1:
        x = layers.Reshape((1, input_shape[0]))(x)

    for i, units in enumerate(conf.lstm_units):
        # Intermediate layers pass the whole sequence on; the last one collapses
        # it to a single vector for the dense head.
        is_last_lstm = i == len(conf.lstm_units) - 1

        x = layers.Bidirectional(
            layers.LSTM(
                units,
                return_sequences=not is_last_lstm,
                dropout=conf.dropout_rate,
                recurrent_dropout=conf.recurrent_dropout,
            )
        )(x)

    for units in conf.dense_layers:
        x = layers.Dense(units, activation=conf.activation)(x)
        x = layers.Dropout(conf.dropout_rate)(x)

    outputs = layers.Dense(output_shape, activation=conf.output_activation)(x)

    return models.Model(inputs=inputs, outputs=outputs, name="bilstm_model")
