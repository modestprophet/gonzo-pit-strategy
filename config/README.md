# Configuration Management

This directory contains configuration files and utilities for the Gonzo Pit Strategy project.

## Configuration Files

The project uses several JSON configuration files:

- `model.json`: Configuration for model architecture and parameters
- `training.json`: Configuration for model training
- `pipeline_race_history.json`: Configuration for the data pipeline
- `database.json`: Configuration for database connections
- `inference.json`: Configuration for model inference
- `logging.json`: Configuration for logging

## Configuration Management System

The project uses a centralized configuration management system implemented in `config.py`. This system provides:

1. **Centralized Configuration Loading**: Load configuration from JSON files using a consistent interface
2. **Environment-based Configuration**: Support for different environments (development, testing, production)
3. **Path Resolution**: Resolve paths relative to the project root

## Usage

### Basic Usage

```python
from config.config import config

# Load configuration
model_config = config.get_config("model")
training_config = config.get_config("training")

# Access configuration values
model_type = model_config.get("model_type", "dense")
epochs = training_config.get("epochs", 100)

# Resolve paths relative to project root
data_path = config.get_path("data/processed")
```

### Environment

The configuration system uses the `APP_ENV` environment variable to determine the current environment. Valid environments are:

- `development` (default)
- `testing`
- `production`

You can access the current environment using:

```python
from config.config import config

env = config.environment
```

### Path Resolution

To resolve paths relative to the project root, use the `get_path` method:

```python
from config.config import config

# Resolve a path relative to the project root
absolute_path = config.get_path("data/processed")
```

This ensures that paths are correctly resolved regardless of the current working directory.

## Configuration File Format

Configuration files are JSON files with a structure specific to each configuration type. For example, a model configuration might look like:

```json
{
  "model_type": "dense",
  "hidden_layers": [64, 32],
  "dropout_rate": 0.2,
  "activation": "relu",
  "output_activation": "linear",
  "learning_rate": 0.001
}
```

## Adding a New Configuration

To add a new configuration file:

1. Create a new JSON file in the `config` directory
2. Add the configuration name and file name to the `CONFIG_FILES` dictionary in `config.py`
3. Use the configuration in your code with `config.get_config("your_config_name")`