"""
Factory for building Keras models based on Pydantic configurations.
"""

import keras
from keras import layers, models, optimizers
from typing import Tuple, Union

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
    # LSTM requires 3D input (batch, time, features).
    # If input is 2D, we might need to reshape or assume it's already 3D.
    # For now, assuming the input handling logic ensures correct shape
    # OR we add a Reshape layer if we know the time steps.
    # But usually, if we use LSTM, our data loader should provide (batch, time, feats).
    # Since the current data loader produces 2D data (rows, features),
    # feeding it to LSTM directly without Reshape won't work unless we treat it as 1 timestep.

    inputs = layers.Input(shape=input_shape)
    x = inputs

    # If input is 1D (features only), expand dims to (1, features) for LSTM
    # This treats each sample as a sequence of length 1.
    if len(input_shape) == 1:
        x = layers.Reshape((1, input_shape[0]))(x)

    for i, units in enumerate(conf.lstm_units):
        return_sequences = (i < len(conf.lstm_units) - 1) or (
            len(conf.dense_layers) > 0
        )
        # If we have dense layers after, we might want return_sequences=False on the last LSTM
        # unless we want to process the sequence in Dense layers (which is rare for this use case).
        # Typically: LSTM -> ... -> LSTM (last) -> Dense
        # If last LSTM, return_sequences=False (default is False in Keras if not specified, but we need to control it)

        # Actually, let's follow the logic:
        # If it's NOT the last LSTM layer, return_sequences=True.
        # If it IS the last LSTM layer, return_sequences=False.
        is_last_lstm = i == len(conf.lstm_units) - 1

        # However, the config logic in original model.py was:
        # return_sequences = i < len(lstm_units) - 1
        # This implies the last LSTM layer returns only the last output (2D).

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
