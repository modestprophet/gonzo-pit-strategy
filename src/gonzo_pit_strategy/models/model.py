"""
Model architecture definitions for the F1 pit strategy prediction.

This module provides model classes for different architectures that can be used
for predicting pit strategy outcomes. 
"""
import os
import keras
from keras import layers, models, optimizers

from gonzo_pit_strategy.db.repositories.model_repository import ModelRepository
from gonzo_pit_strategy.config.config import config

class ModelBase:
    """Base class for all models."""

    def __init__(self, config_name: str = "model"):
        """Initialize the model with configuration.

        Args:
            config_name: Name of the configuration to use (default: "model")
        """
        self.config = config.get_config(config_name)

        self.model = None
        model_path = self.config.get('model_path', 'models/artifacts')
        self.model_path = str(config.get_path(model_path))
        self.model_name = self.config.get('model_name', 'f1_pit_strategy_model')
        self.input_shape = self.config.get('input_shape', None)
        self.output_shape = self.config.get('output_shape', None)

    def build(self) -> keras.Model:
        """Build the model architecture.

        Returns:
            Compiled Keras model
        """
        raise NotImplementedError("Subclasses must implement build()")

    def save(self, version: str) -> str:
        """Save the model to disk using the model repository.

        Args:
            version: Version string for the model

        Returns:
            Path where model was saved
        """
        if self.model is None:
            raise ValueError("Model must be built before saving")

        # Create model repository
        repo = ModelRepository(self.model_path)

        # Prepare metadata
        metadata = {
            "model_name": self.model_name,
            "version": version,
            "input_shape": self.input_shape,
            "output_shape": self.output_shape,
            "config": self.config
        }

        # Save model using repository
        model_id = repo.save_model(self.model, version, metadata)

        # Return the path where the model was saved
        save_path = os.path.join(self.model_path, version, self.model_name)
        return save_path

    def load(self, version: str) -> keras.Model:
        """Load a saved model using the model repository.

        Args:
            version: Version string for the model

        Returns:
            Loaded Keras model
        """
        # Create model repository
        repo = ModelRepository(self.model_path)

        # Load model using repository
        self.model, metadata = repo.load_model(version, self.model_name)

        # Update model attributes from metadata if available
        if metadata:
            if "input_shape" in metadata:
                self.input_shape = metadata["input_shape"]
            if "output_shape" in metadata:
                self.output_shape = metadata["output_shape"]

        return self.model

    def summary(self) -> None:
        """Print model summary."""
        if self.model is None:
            raise ValueError("Model must be built before getting summary")

        self.model.summary()


class DenseModel(ModelBase):
    """Simple dense neural network model."""

    def build(self) -> keras.Model:
        """Build a simple dense neural network.

        Returns:
            Compiled Keras model
        """
        if self.input_shape is None:
            raise ValueError("Input shape must be specified in config")

        if self.output_shape is None:
            raise ValueError("Output shape must be specified in config")

        # Get hyperparameters from config
        hidden_layers = self.config.get('hidden_layers', [64, 32])
        dropout_rate = self.config.get('dropout_rate', 0.2)
        activation = self.config.get('activation', 'relu')
        output_activation = self.config.get('output_activation', 'linear')
        learning_rate = self.config.get('learning_rate', 0.001)

        # Build model
        inputs = layers.Input(shape=self.input_shape)
        x = inputs

        # Add hidden layers
        for units in hidden_layers:
            x = layers.Dense(units, activation=activation)(x)
            x = layers.Dropout(dropout_rate)(x)

        # Output layer
        outputs = layers.Dense(self.output_shape, activation=output_activation)(x)

        # Create model
        self.model = models.Model(inputs=inputs, outputs=outputs)

        # Compile model
        self.model.compile(
            optimizer=optimizers.Adam(learning_rate=learning_rate),
            loss=self.config.get('loss', 'mse'),
            metrics=self.config.get('metrics', ['mae'])
        )

        return self.model


class BiLSTMModel(ModelBase):
    """Bidirectional LSTM model for sequence data."""

    def build(self) -> keras.Model:
        """Build a bidirectional LSTM model.

        Returns:
            Compiled Keras model
        """
        if self.input_shape is None:
            raise ValueError("Input shape must be specified in config")

        if self.output_shape is None:
            raise ValueError("Output shape must be specified in config")

        # Get hyperparameters from config
        lstm_units = self.config.get('lstm_units', [64, 32])
        dropout_rate = self.config.get('dropout_rate', 0.2)
        recurrent_dropout = self.config.get('recurrent_dropout', 0.2)
        dense_layers = self.config.get('dense_layers', [32])
        activation = self.config.get('activation', 'relu')
        output_activation = self.config.get('output_activation', 'linear')
        learning_rate = self.config.get('learning_rate', 0.001)

        # Build model
        inputs = layers.Input(shape=self.input_shape)
        x = inputs

        # Add LSTM layers
        for i, units in enumerate(lstm_units):
            return_sequences = i < len(lstm_units) - 1
            x = layers.Bidirectional(
                layers.LSTM(
                    units, 
                    return_sequences=return_sequences,
                    dropout=dropout_rate,
                    recurrent_dropout=recurrent_dropout
                )
            )(x)

        # Add dense layers
        for units in dense_layers:
            x = layers.Dense(units, activation=activation)(x)
            x = layers.Dropout(dropout_rate)(x)

        # Output layer
        outputs = layers.Dense(self.output_shape, activation=output_activation)(x)

        # Create model
        self.model = models.Model(inputs=inputs, outputs=outputs)

        # Compile model
        self.model.compile(
            optimizer=optimizers.Adam(learning_rate=learning_rate),
            loss=self.config.get('loss', 'mse'),
            metrics=self.config.get('metrics', ['mae'])
        )

        return self.model


def get_model(model_type: str, config_name: str = "model") -> ModelBase:
    """Factory function to get a model instance.

    Args:
        model_type: Type of model to create ('dense', 'bilstm', etc.)
        config_name: Name of the configuration to use (default: "model")

    Returns:
        Model instance
    """
    model_types = {
        'dense': DenseModel,
        'bilstm': BiLSTMModel,
    }

    if model_type not in model_types:
        raise ValueError(f"Unknown model type: {model_type}. Available types: {list(model_types.keys())}")

    return model_types[model_type](config_name=config_name)
