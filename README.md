# Gonzo Pit Strategy

F1 Pit Strategy Prediction System using Machine Learning.

## Training System Documentation

This project uses a **Configuration-Driven Architecture** for reproducible and scalable model training. All training parameters are defined in strict JSON schemas validated by Pydantic.

### 1. Configuration Basics

The configuration system handles:
- **Data Selection**: Target columns, excluded features, splits.
- **Model Architecture**: Type-safe parameters for Dense, BiLSTM, etc.
- **Training Loop**: Batch size, epochs, learning rate, early stopping.

### 2. Generating & Managing Configs

#### Generate a Default Config
To get started, generate a template configuration file with default settings:

```bash
python3 src/gonzo_pit_strategy/cli/train.py --generate-default
```

This creates `config/experiments/training_config_default.json` in the `config/experiments/` directory.

#### Create a Custom Config
You can modify the generated JSON or create one from scratch.

**Example (Dense Model):**
```json
{
  "target_column": "finish_position",
  "exclude_columns": ["driver_id", "race_id"],
  "test_size": 0.2,
  "model": {
    "type": "dense",
    "hidden_layers": [128, 64],
    "dropout_rate": 0.3
  },
  "epochs": 50,
  "learning_rate": 0.001
}
```

**Example (BiLSTM Model):**
To switch architectures, simply change the `model` object. The validation system ensures you provide the correct parameters for that type.

```json
{
  "target_column": "finish_position",
  "model": {
    "type": "bilstm",
    "lstm_units": [64, 32],
    "dense_layers": [32],
    "dropout_rate": 0.2
  },
  "epochs": 50
}
```

### 3. Running Experiments

#### Train a Single Model
Run an experiment by passing your config file:

```bash
python3 src/gonzo_pit_strategy/cli/train.py --config config/experiments/my_config.json
```

**What happens:**
1.  Data is loaded and preprocessed (auto-scaling, OHE, NaN handling).
2.  The model is built according to the config.
3.  A `TrainingRun` is logged to the database.
4.  Metrics are tracked in real-time.
5.  Artifacts are saved to `models/artifacts/` upon completion.

#### Run a Hyperparameter Sweep (Grid Search)
You can test multiple parameter combinations automatically.

1.  **Create a Sweep Config** (JSON):
    Keys can use dot-notation to target nested fields.
    ```json
    {
      "learning_rate": [0.01, 0.001],
      "batch_size": [32, 64],
      "model.dropout_rate": [0.2, 0.5]
    }
    ```

2.  **Execute the Sweep**:
    ```bash
    python3 src/gonzo_pit_strategy/cli/train.py --grid-search sweep_params.json
    ```
    *Note: You can combine this with `--config base.json` to set common parameters.*

### 4. Extending With New Model Types

To add a new architecture (e.g., `Transformer`), follow these steps:

#### Step 1: Define the Config Schema
Edit `src/gonzo_pit_strategy/training/config.py`:

```python
class TransformerConfig(BaseModel):
    type: Literal["transformer"] = "transformer"
    num_heads: int = 4
    embed_dim: int = 64
    # ... other specific params

# Update the Union
ModelConfig = Union[DenseModelConfig, BiLSTMModelConfig, TransformerConfig]
```

#### Step 2: Implement the Builder
Edit `src/gonzo_pit_strategy/training/model_factory.py`:

```python
def build_model(config: TrainingConfig, ...):
    # ... existing dispatch logic ...
    elif model_conf.type == "transformer":
        return _build_transformer(model_conf, input_shape, output_shape)

def _build_transformer(conf: TransformerConfig, input_shape, output_shape):
    # Implement Keras model construction here
    ...
```

#### Step 3: Use It
Create a config with `"type": "transformer"` and run training!
