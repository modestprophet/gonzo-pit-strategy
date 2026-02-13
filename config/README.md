# Configuration Management

This directory contains configuration files and utilities for the Gonzo Pit Strategy project.

## Configuration Files

The project uses the following active configuration files:

- `database.json`: Configuration for database connections
- `logging.json`: Configuration for logging

> **Note**: Training configurations are now generated dynamically or passed via CLI arguments. Generated configs are stored in `config/experiments/`.

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
db_config = config.get_config("database")

# Access configuration values
host = db_config.get("host")

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

## Adding a New Configuration

To add a new configuration file:

1. Create a new JSON file in the `config` directory
2. Add the configuration name and file name to the `CONFIG_FILES` dictionary in `config.py`
3. Use the configuration in your code with `config.get_config("your_config_name")`
