# Gonzo Pit Strategy

F1 Pit Strategy Prediction System using Machine Learning.

## Prerequisites

Before getting started, ensure you have the following installed:
- **Python 3.9+**
- **PostgreSQL 13+** (Running and accessible)
- **[uv](https://github.com/astral-sh/uv)** (for fast Python dependency management)
- **[Goose](https://github.com/pressly/goose)** (for database migrations)
- **HashiCorp Vault** (Optional: used for managing secrets/credentials in production)

---

## Setup Instructions

### 1. Install Dependencies

Clone the repository and install the project dependencies. This project uses `uv` for managing virtual environments and packages.

```bash
# Create a virtual environment and sync dependencies
uv sync

# Alternatively, install the project in editable mode
uv pip install -e .
```

### 2. Environment Configuration

Create a `.env` file in the root directory (you can copy `.env.example` as a starting point).

```bash
cp .env.example .env
```

Ensure the following variables are set for the data pipeline and training scripts:
```ini
APP_ENV=development

# Database Settings
DB_HOST=localhost
DB_PORT=5432
DB_NAME=f1db
DB_USER=your_app_username
DB_PASSWORD=your_app_password

# For dbt specifically:
F1DB_HOST=localhost
F1DB_USER=your_app_username
F1DB_PASSWORD=your_app_password
```
*(Note: If using Vault, database passwords can be omitted here and securely fetched at runtime).*

### 3. Database Initialization & Raw Data Loading

To prepare the database, we use the `gonzo-load` script which handles creating the schema, running `goose` migrations, and loading the raw Jolpica F1 CSV data. 

Ensure your raw F1 CSV files are located in `data/raw/` before running this command.

```bash
uv run gonzo-load \
  --db-host localhost \
  --db-port 5432 \
  --db-name f1db \
  --db-admin-username postgres \
  --db-admin-password your_admin_password \
  --app-username your_app_username \
  --app-password your_app_password \
  --data-directory data/raw \
  --steps all
```
*Note: The `--steps all` argument executes three phases: `init` (creates the database/roles), `migrate` (runs goose schemas), and `load` (copies CSVs).*

### 4. Data Transformation Pipeline (dbt)

Once the raw data is loaded, we use `dbt` to transform it into analytics-ready tables and final ML feature sets.

```bash
cd dbt

# Install dbt dependencies
dbt deps

# Run the transformation pipeline
dbt build
```

This will run all SQL models, generating the intermediate and final `f1db_ml_prep.prep_training_dataset` table, while strictly verifying data constraints and accepted values.

---

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
uv run gonzo-train --generate-default
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
uv run gonzo-train --config config/experiments/my_config.json
```

**What happens:**
1.  Data is loaded directly from the PostgreSQL `f1db_ml_prep` schema.
2.  The model is built according to the config.
3.  A `TrainingRun` and its configuration metadata is logged to the database.
4.  Metrics are tracked in real-time.
5.  Artifacts (model `.h5` / `.keras` weights) are saved to `models/checkpoints/` upon completion.

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
    uv run gonzo-train --grid-search config/experiments/sweep_params.json
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
