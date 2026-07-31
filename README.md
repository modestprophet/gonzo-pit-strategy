# Gonzo Pit Strategy

F1 pit strategy prediction. Jolpica CSVs land in Postgres, dbt transforms them
into a training dataset, and Keras trains against it — producing a
self-describing artifact that inference can load with no database at all.

```
data/raw/*.csv ──gonzo-load──▶ f1db.* (18 tables) ──dbt build──▶ f1db_ml_prep.prep_training_dataset
                                                                            │
                                                                       gonzo-train
                                                                            │
                                                    models/artifacts/<version>/{model.keras, manifest.json}
                                                                            │
                                                                     ModelPredictor
```

Design decisions live in `docs/adr/`; the project's vocabulary is defined in
`CONTEXT.md`. Read both before changing the config or artifact layers.

## Prerequisites

- **Python 3.11+** (`.python-version` pins 3.13)
- **PostgreSQL 13+**, running and reachable
- **[uv](https://github.com/astral-sh/uv)** for dependency management
- **[goose](https://github.com/pressly/goose)** for migrations —
  `go install github.com/pressly/goose/v3/cmd/goose@latest`
- **HashiCorp Vault** — optional, for injecting the database password

## 1. Install

```bash
uv sync                      # training + inference
uv sync --extra dbt          # add dbt, needed to rebuild the dataset
uv sync --extra notebooks     # add Jupyter
```

## 2. Configure

```bash
cp .env.example .env
```

Environment variables map onto the `AppConfig` tree using `__` as the nesting
delimiter, so `AppConfig.db.host` is set by **`DB__HOST`**. A single underscore
does not work — `DB_HOST` matches no field and is silently discarded.

```ini
APP_ENV=development

DB__HOST=localhost
DB__PORT=5432
DB__NAME=f1db
DB__USER=gonzo_user
DB__PASSWORD=local_dev_password   # omit to source from Vault instead

LOGGING__LEVEL=INFO
```

Every setting is declared in `src/gonzo_pit_strategy/config/config.py` — one
file to read to know what the application needs (ADR 0001). Precedence is
constructor kwargs → environment → `.env` → Vault → field defaults.

**Vault is optional.** Set `VAULT__ADDR`, `VAULT__ROLE_ID`, and `VAULT__SECRET_ID`
to enable it; leave any of them unset and the Vault settings source disables
itself, with values falling back to the variables above. Fields are marked for
Vault via `json_schema_extra={"vault_path": ...}`, resolved beneath
`VAULT__MOUNT_POINT`. Note that a Vault *fetch failure* logs a warning and falls
through to the default rather than aborting — do not rely on the local default
credentials outside development.

dbt reads the database separately through `dbt/profiles.yml`, which is why
`.env.example` also carries `F1DB_*` variables.

## 3. Load raw Jolpica data

Put the Jolpica CSVs in `data/raw/`, then:

```bash
uv run gonzo-load \
  --db-host localhost --db-port 5432 --db-name f1db \
  --db-admin-username postgres --db-admin-password <admin-pw> \
  --app-username gonzo_user --app-password <app-pw> \
  --data-directory data/raw \
  --steps all
```

`--steps all` runs three phases, each also runnable alone as `--steps init`,
`--steps migrate`, or `--steps load`:

| Phase | What it does |
|---|---|
| `init` | Creates the database, the `f1db` schema, and the application role via `db/init_db.sql` |
| `migrate` | Applies goose migrations from `db/migrations/` |
| `load` | `psql \copy` of the 18 Jolpica CSVs into `f1db.*` |

Credentials are command-line arguments rather than config here: this runs before
the application has a database to connect to.

Verify — check row counts, not just that tables exist:

```bash
psql -h localhost -U gonzo_user -d f1db \
  -c "select relname, n_live_tup from pg_stat_user_tables
      where schemaname='f1db' order by n_live_tup desc"
```

A correct load puts ~665k rows in `laps`, ~48k in `session_entries` and ~27k in
`round_entries`. All-zero counts with a success message was a real failure mode:
`psql` exits 0 on a failed `\copy` unless `ON_ERROR_STOP=1` is set, so every load
error was reported as a success. Fixed, but the row-count check is still the
verification that means something.

Common failures: *database already exists* is handled and skipped; *permission
denied* means the admin role lacks `CREATEDB`; *goose not found* means the Go
tool isn't on `PATH`.

### Testing against a scratch database

The whole pipeline runs against any empty Postgres 16 — useful for verifying
migrations without touching a real database:

```bash
uv run gonzo-load --db-host <scratch-host> --db-name f1db \
  --db-admin-username <superuser> --db-admin-password <pw> \
  --app-username gonzo_user --app-password gonzo_pw \
  --data-directory data/raw --steps all
```

Migrations are reversible: `goose ... down` through all of them and back up again
applies cleanly on an empty database, so a scratch database can be reset without
recreating it.

Running against a **snapshot of an existing database** is a different procedure —
`--steps load` must be skipped, and the migration state needs checking first. See
[`docs/E2E_FROM_PROD_SNAPSHOT.md`](docs/E2E_FROM_PROD_SNAPSHOT.md).

## 4. Build the training dataset (dbt)

dbt authenticates separately from `AppConfig`, via `dbt/profiles.yml`:

```bash
cd dbt
export F1DB_HOST=localhost F1DB_USER=gonzo_user F1DB_PASSWORD=<app-pw>
dbt deps
dbt build
```

dbt materializes into `f1db_staging`, `f1db_intermediate`, `f1db_features` and
`f1db_ml_prep`, creating those schemas on first run — which is why `init_db.sql`
grants the app role `CREATE ON DATABASE`, not just rights on the `f1db` schema.
`permission denied for database f1db` means that grant is missing.

Lineage runs staging → intermediate → features → ml_prep, ending at
`f1db_ml_prep.prep_training_dataset`. **dbt owns all feature engineering**: DNF
handling, time conversion, lagging, season progress, one-hot encoding, and
scaling are SQL models (`dbt/models/features/`, `dbt/models/ml_prep/`), not
Python. Add or change features there.

## 5. Train

```bash
# Write a template config to config/experiments/ (needs no database)
uv run gonzo-train --generate-default

# Train
uv run gonzo-train --config config/experiments/training_config_default.json
```

What happens: the dataset is fetched and content-fingerprinted, split
train/val/test, the model is built from config, and on train end the Artifact is
written to `models/artifacts/<version>/` while `model_metadata`,
`dataset_versions`, and `training_runs` are updated once as a reporting mirror
(ADR 0002). Per-epoch metrics stream to `training_metrics` and TensorBoard.

Configs are validated by pydantic, so a typo or an out-of-range value fails
before training starts:

```json
{
  "target_column": "finish_position",
  "exclude_columns": ["race_id"],
  "test_size": 0.2,
  "model": { "type": "dense", "hidden_layers": [128, 64], "dropout_rate": 0.3 },
  "epochs": 50,
  "learning_rate": 0.001
}
```

Switching architecture means changing the `model` object; validation enforces
the parameters that architecture requires.

```json
{
  "model": {
    "type": "bilstm",
    "lstm_units": [64, 32],
    "dense_layers": [32],
    "dropout_rate": 0.2
  }
}
```

### Hyperparameter sweeps

Dot-notation targets nested fields. Combine with `--config` to fix the base.

```json
{ "learning_rate": [0.01, 0.001], "batch_size": [32, 64], "model.dropout_rate": [0.2, 0.5] }
```

```bash
uv run gonzo-train --grid-search config/experiments/sweep_params.json
```

## 6. Predict

An artifact is self-describing, so inference needs no database — copy the
directory and it carries everything required:

```python
from gonzo_pit_strategy.config.config import AppConfig
from gonzo_pit_strategy.inference.predictor import load_predictor

predictor = load_predictor("dense_20260729_120000", AppConfig().paths)
predictions = predictor.predict(df)
```

`manifest.json` holds `feature_names` in training order — the model's input
contract. `predict` reorders columns to match and applies the same encoding
training used, so a raw slice of `prep_training_dataset` works directly.

## Adding a model architecture

1. Add a config class in `training/config.py` with a `Literal` discriminator and
   add it to the `ModelConfig` union:

   ```python
   class TransformerConfig(BaseModel):
       type: Literal["transformer"] = "transformer"
       num_heads: int = 4
       embed_dim: int = 64

   ModelConfig = Union[DenseModelConfig, BiLSTMModelConfig, TransformerConfig]
   ```

2. Add a `_build_transformer` builder in `training/model_factory.py` and
   dispatch to it from `build_model`.
3. Set `"type": "transformer"` in a config and train.

## Testing

```bash
uv run pytest
```

Tests need neither a database nor a GPU. `tests/conftest.py` provides a
`StubDataSource` satisfying the `TrainingDataSource` protocol, and the keras
import is lazy so the config and data tests run without TensorFlow.

## Reusing this as a template

The generic ML spine is:

- `config/` — `AppConfig`, Vault settings source, `setup_logging`
- `db/base.py`, `db/connection_pool.py`, and the four metadata tables
  (`training_runs`, `training_metrics`, `model_metadata`, `dataset_versions`)
- `training/` — `config`, `data`, `runner`, `model_factory`, `callbacks`,
  `artifact`, `sweep`
- `inference/predictor.py`, `cli/train.py`

The F1-specific parts are exactly:

- `dbt/` — the whole transformation layer
- the `prep_training_dataset` query in `DatabaseDataSource` (`training/data.py`)
- the F1 defaults in `training/config.py` (`target_column`, `tags`)
- `utils/db_setup.py` and `db/migrations/002_jolpica_setup.sql` — Jolpica ingest

These are deliberately **not** parameterized. Extracting a cookiecutter means
copying the spine and editing those four places, which is cheaper to reason
about than the indirection that generalizing them would require.
