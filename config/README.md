# Configuration Management

This project uses a unified, strongly-typed configuration system powered by `pydantic-settings`.

## Configuration System

The `AppConfig` class in `src/gonzo_pit_strategy/config/config.py` provides:

1. **Unified Tree**: All config is under one tree (`config.db`, `config.training`).
2. **Type Safety**: Pydantic validates all inputs.
3. **Vault Integration**: The `VaultSettingsSource` injects secrets transparently.
4. **Environment Variables**: Overrides are possible via environment variables (e.g., `DB__HOST=localhost`).

## Usage

```python
from gonzo_pit_strategy.config.config import config

# Access configuration values with dot notation
host = config.db.host
epochs = config.training.epochs
```

## Adding a New Configuration

To add a new configuration setting:

1. Add it to the corresponding sub-model (like `DatabaseConfig` or `TrainingConfig`).
2. If adding a new sub-system, create a new `BaseModel` class and add it as a field to `AppConfig`.
3. Use it in your code via `config.new_system.property`.
