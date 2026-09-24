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
- **PostgreSQL 17** — dev and prod both run 17.10 on Debian/glibc. The Dataset
  Fingerprint is collation-dependent, so major version *and* libc must match
  between any two databases you intend to compare; see Gate −1 in
  [`docs/E2E_FROM_PROD_SNAPSHOT.md`](docs/E2E_FROM_PROD_SNAPSHOT.md)
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
| `init` | Creates the database, the schema, and the App Role via `db/init_db.sql` |
| `migrate` | Applies goose migrations from `db/migrations/` |
| `load` | `COPY` of the 18 Jolpica CSVs into `f1db.*`, in one transaction |

Phases always run in that order — `--steps load,init` requests both, it does not
request loading first — and stop at the first failure. The ordering rule, the
Load Plan, and the failure rules live in `db/provisioning.py`; `cli/load.py` is
argparse and printing.

Credentials are command-line arguments rather than config here: this runs before
the application has a database to connect to. The two roles are not
interchangeable — `init` needs both, `migrate` needs the admin role, `load` needs
the app role — so a run missing a credential a requested phase needs fails before
creating anything.

The load prints rows written per table, so the verification that means something
is the command's own output:

```
--- Rows loaded ---
laps                           664,773
session_entries                 48,248
round_entries                   27,261
total                          814,211
```

A correct load puts ~665k rows in `laps`, ~48k in `session_entries` and ~27k in
`round_entries`. (`base_teams` and `penalties` load zero rows — their Jolpica
CSVs are header-only.) All-zero counts with a success message was a real failure
mode: `psql` exits 0 on a failed `\copy` unless `ON_ERROR_STOP=1` is set, so
every load error was reported as a success. The load now runs `COPY` in-process,
where a failure raises rather than returning an exit code, and the whole plan
runs in one transaction — so a failed load leaves the database as it was rather
than partially populated.

Common failures: *database already exists* is handled and skipped; *permission
denied* means the admin role lacks `CREATEDB`; *goose not found* means the Go
tool isn't on `PATH`.

### Testing against a scratch database

The whole pipeline runs against any empty Postgres matching the version and
libc above — useful for verifying migrations without touching a real database:

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
`f1db_ml_prep`, creating those schemas on first run — the first three as views,
so every intermediate layer stays directly queryable for inspection — which is why `init_db.sql`
grants the app role `CREATE ON DATABASE`, not just rights on the `f1db` schema.
`permission denied for database f1db` means that grant is missing.

Lineage runs staging → intermediate → features → ml_prep, ending at
`f1db_ml_prep.prep_training_dataset`. **dbt owns dataset-level feature
engineering**: DNF handling, time conversion, lagging, season progress, one-hot
encoding, and scaling are SQL models (`dbt/models/features/`,
`dbt/models/ml_prep/`), not Python. Add or change features there.

The dividing line is not SQL-vs-Python but *does inference have to reproduce
this?* — transformations the predictor must repeat live in `prepare_features`;
transformations that define the dataset live here. See ADR 0003.

## 5. Train

```bash
# Write a template config to config/experiments/ (needs no database)
uv run gonzo-train --generate-default

# Train
uv run gonzo-train --config config/experiments/training_config_default.json
```

What happens: the dataset is fetched and content-fingerprinted, split
train/val/test, and the model is built from config and trained. Then, as
sequential steps in `Experiment.run` — not as callbacks — the model is
evaluated, the Artifact is written to `models/artifacts/<version>/`, and
`model_metadata`, `dataset_versions`, and `training_runs` are updated once
through the Run Ledger as a reporting mirror (ADR 0002). Per-epoch metrics
stream to `training_metrics` and TensorBoard.

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

## Design decisions

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-declarative-configuration-and-secrets.md) | Declarative configuration and secrets injection — one `AppConfig` tree, no global singletons |
| [0002](docs/adr/0002-self-describing-artifacts.md) | Self-describing artifacts; the database is a reporting mirror owned by the Run Ledger |
| [0003](docs/adr/0003-feature-engineering-belongs-to-dbt.md) | Feature engineering belongs to dbt; the seam is inference, not language |
