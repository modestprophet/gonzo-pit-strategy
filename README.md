# Gonzo Pit Strategy

F1 pit strategy prediction. `gonzo-load` loads Jolpica CSVs into Postgres,
dbt builds the training dataset, and `gonzo-train` trains a Keras model.
The saved model and manifest support inference without a database.

Open [the architecture explorer](docs/architecture.html) in a browser for the
module graph, execution flows, and dbt lineage. The code defines the behavior
and configuration. This README covers setup and common commands.

## Prerequisites

- Python 3.11 or newer. `.python-version` selects 3.13 for this checkout.
- [uv](https://github.com/astral-sh/uv) for Python dependencies.
- PostgreSQL 17 and `psql` on `PATH` for database initialization.
- [goose](https://github.com/pressly/goose) on `PATH` for migrations.
- Linux with `renameat2` no-replacement support for publishing trained models.

No GPU is required. Vault is optional.

## 1. Install and configure

Run these commands from the repository root. The application reads `.env`
and resolves default output paths relative to the working directory.

```bash
uv sync
cp .env.example .env
```

Edit `.env` for your database. The application uses `DB__HOST`, `DB__PORT`,
`DB__NAME`, `DB__USER`, and `DB__PASSWORD`. The double underscore is required.
Set `DB__NAME=f1db`, since the application default is `gonzo` but the SQL
pipeline uses `f1db`.

dbt reads `F1DB_HOST`, `F1DB_USER`, and `F1DB_PASSWORD` separately. Keep these
consistent with the `DB__*` values and the app credentials passed to
`gonzo-load`. Its profile fixes the database to `f1db` and the port to `5432`.

Settings and defaults live in
[`config/config.py`](src/gonzo_pit_strategy/config/config.py). Constructor
arguments take precedence over environment variables, then `.env`, then Vault,
then defaults. To use Vault, set `VAULT__ADDR`, `VAULT__ROLE_ID`, and
`VAULT__SECRET_ID`, and omit `DB__PASSWORD`. Vault failures log a warning and
fall back to defaults, so do not rely on the development credentials elsewhere.

## 2. Load Jolpica data

Place the CSVs in `data/raw/`, or supply another directory. The required
filenames and load order are in `LOAD_PLAN` in
[`db/provisioning.py`](src/gonzo_pit_strategy/db/provisioning.py).

For an empty database, run the following command with your credentials.
The admin role needs permission to create databases and create or alter roles.

```bash
uv run gonzo-load \
	--db-host localhost --db-port 5432 --db-name f1db \
	--db-admin-username postgres --db-admin-password 'ADMIN_PASSWORD' \
	--app-username gonzo_user --app-password 'APP_PASSWORD' \
	--data-directory data/raw --steps all
```

`--steps all` initializes the database and app role, applies the migrations in
[`db/migrations/`](src/gonzo_pit_strategy/db/migrations/), then copies the 18
CSVs into `f1db.*`. Credentials come from these arguments, not `DB__*`.
The command prints rows loaded per table. Counts depend on the CSV snapshot.
The copy runs in one transaction and rolls back if any table fails.

You can select `--steps init`, `--steps migrate`, or `--steps load` separately.
Selected phases always run in that order and stop at the first failure.
Do not run `load` against an already populated database or a restored snapshot.
It inserts rows without deduplication. Check the existing migration state before
applying migrations to a restored database.

See the [Jolpica schema reference](docs/JOLPICA_F1_DATABASE_SCHEMA.md) for the
raw tables.

## 3. Build the training dataset

Run dbt from the repository root through uv. These commands install the dbt
extra and export the variables in `.env` to dbt.

```bash
uv run --extra dbt --env-file .env dbt deps --project-dir dbt --profiles-dir dbt
uv run --extra dbt --env-file .env dbt build --project-dir dbt --profiles-dir dbt
```

dbt builds views in `f1db_staging`, `f1db_intermediate`, and `f1db_features`,
and tables in `f1db_ml_prep`. The final dataset is
`f1db_ml_prep.prep_training_dataset`. The app role needs `CREATE ON DATABASE`
to create these schemas. The initialization SQL grants it.

Feature engineering lives in [`dbt/models/`](dbt/models/). Training and inference
share the numeric conversions in
[`prepare_features`](src/gonzo_pit_strategy/training/data.py).
Database collation can change generated column order and dataset fingerprints.
Use matching PostgreSQL, libc, and collation settings when comparing databases.

## 4. Train

```bash
uv run gonzo-train --config config/experiments/training_config_default.json
```

Without `--config`, the CLI uses `TrainingConfig` defaults. To regenerate the
example, run `uv run gonzo-train --generate-default`. This overwrites
`config/experiments/training_config_default.json` and needs no database.

Training reads the dbt dataset, splits it into training, validation, and test
sets, then fits and evaluates the model. It writes `model.keras` and
`manifest.json` to `models/artifacts/<version>/` before recording the result
in the database. Epoch metrics go to the database and `logs/tensorboard/`.
Training creates its output directories as needed.

For a hyperparameter sweep, supply a separate grid:

```bash
uv run gonzo-train \
	--config config/experiments/training_config_default.json \
	--grid-search config/experiments/dense_sweep.json
```

See the [training configuration reference](config/README.md) for grid syntax,
validation, and exit codes. The fields and model types are declared in
[`training/config.py`](src/gonzo_pit_strategy/training/config.py).

## 5. Predict

Use the model version printed by training and a DataFrame containing the
engineered feature columns from `prep_training_dataset`:

```python
from gonzo_pit_strategy.config.config import PathsConfig
from gonzo_pit_strategy.inference.predictor import load_predictor

predictor = load_predictor("MODEL_VERSION", PathsConfig())
predictions = predictor.predict(df)
```

The manifest records feature names in training order. The predictor reorders
DataFrame columns and applies `prepare_features`. It does not build features
from raw Jolpica records. Copy the entire artifact directory to use it without
a database, and set `PathsConfig.artifacts_root` if it is outside
`models/artifacts/`.

## Testing

```bash
uv run pytest
```

The core tests need no database or GPU, but the full suite imports
Keras and TensorFlow. `uv sync` installs these dependencies and pytest.

Database integration tests use `DEV_POSTGRES_URL` when available. Point it only
at a disposable Postgres instance. The tests truncate ledger tables and create
and drop databases and roles. Provisioning tests also need `psql`, goose, and
administrative privileges. Tests skip database checks when their prerequisites
are unavailable.
