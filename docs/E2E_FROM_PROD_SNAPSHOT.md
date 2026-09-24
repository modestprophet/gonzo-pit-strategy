# End-to-end run against a production snapshot

The README documents the **greenfield** path: create a database, migrate from
zero, load the Jolpica CSVs. A production snapshot is the opposite situation — an
already-populated database at an unknown migration version — and two steps of the
greenfield path are actively wrong against it. This is the protocol for that case.

Every command below was exercised against the dev container's scratch Postgres
except where marked *unverified*. Gates 2–5 were last re-run green on
2026-07-31 against PostgreSQL 17.10 (Debian, glibc).

## Why not just follow the README

| README step | Against a snapshot |
|---|---|
| `--steps init` | Harmless but pointless; the database already exists |
| `--steps migrate` | **Required** — and the step where the risk lives (see Gate 1) |
| `--steps load` | **Do not run.** The tables are already populated and the Load is a bare `COPY` with no `ON CONFLICT`; it will fail on primary keys. Since 2026-08-03 the whole Load runs in one transaction, so such a failure rolls back rather than leaving partially duplicated tables — but a snapshot still has nothing to gain from running it |
| `dbt build` | Fine, but it drops and recreates everything in `f1db_ml_prep` — derived data only, never `f1db.*` |

So the snapshot protocol is `migrate` → `dbt build` → `train`, never `load`.

## Gate −1 — environment parity

**Do this once per dev environment, before anything else.** The dataset
fingerprint is collation-dependent, so a dev server that sorts differently from
prod produces a different fingerprint from identical data — which makes every
comparison in Gate 3 and Gate 4 meaningless.

```bash
psql -d "$DEV_POSTGRES_URL" -Atc "select version()"
psql -d "$DEV_POSTGRES_URL" -Atc \
  "select datcollate, datctype from pg_database where datname=current_database()"
```

Major version, **libc**, and `datcollate`/`datctype` must all match prod. As of
2026-07-31 both sides are PostgreSQL 17.10 on Debian/glibc with `en_US.UTF-8`
(dev `17.10-1.pgdg13+1`, prod `17.10-0+deb13u1`).

The libc is the part that bites, and `select version()` is where you see it —
`x86_64-pc-linux-gnu` is glibc, `x86_64-pc-linux-musl` is Alpine. A musl server
passes a naive "PG 17, en_US.UTF-8" check and still sorts differently:

```sql
select x from unnest(ARRAY['nivelles','nürburgring','österreichring','zeltweg']) x
 order by x collate "en_US.utf8";   -- glibc: … nürburgring, österreichring, zeltweg
select x from unnest(ARRAY['nivelles','nürburgring','österreichring','zeltweg']) x
 order by x collate "C";            -- byte order: … zeltweg, österreichring
```

`prep_ohe_circuit.sql:8` builds its one-hot columns from a compile-time
`run_query(... ORDER BY circuit_name)`, so this sort order is baked into the
**column order** of `prep_training_dataset`. Running the identical build on
Alpine/musl once shifted 123 of 408 columns and changed the fingerprint from
`d38a9603…` to `e3a0d93a…` with zero dtype or row-count differences.

Inference is unaffected either way — the ADR-0002 manifest pins `feature_names`
and `predict` reorders to match — so this corrupts *comparisons*, not models.

## Gate 0 — record prod's state before you touch anything

Run this **against prod, read-only**, and keep the output. Without it you cannot
tell afterwards whether a schema difference came from the snapshot or from your
run.

```bash
psql -h <prod-host> -U <user> -d f1db \
  -c "select version_id, is_applied, tstamp from f1db.goose_db_version order by version_id" \
  -c "select is_nullable from information_schema.columns
      where table_schema='f1db' and table_name='training_runs' and column_name='model_id'" \
  -c "select count(*) from information_schema.columns
      where table_schema='f1db' and table_name='model_metadata' and column_name='artifact_path'" \
  -c "select count(*) from f1db.training_runs" \
  -c "select count(*) from f1db.model_metadata" \
  -c "select dataset_version_id, version, record_count, feature_count
      from f1db.dataset_versions order by dataset_version_id" \
  -c "select count(*) from f1db_ml_prep.prep_training_dataset" \
  -c "select version()"
```

Capture the last three. `dataset_versions.version` is the **dataset fingerprint
truncated to 16 chars** — that truncation is why prod's stored value is short
while `fingerprint_dataset()` returns a full 64-char sha256; compare only the
first 16. Prod currently reads `d38a960303b77afb`.

> **Do not treat that value as a baseline.** As of 2026-07-31 the fingerprint is
> not reproducible across independently-built databases, by construction — see
> the `feat_lagged` limitation below. Record prod's value to detect *change over
> time on prod itself*; do not expect a fresh build to match it.

**The number that matters is the highest `version_id`.** Two different files once
claimed version 3, and goose tracks applied migrations by version *number*, not
filename. If prod recorded version 3 from the deleted
`003_model_metadata_artifact_path.sql`, it will skip the kept
`003_artifact_and_run_links.sql` — reporting *"successfully migrated"* while
`training_runs.model_id` stays `NOT NULL`. Training then fails on its first write,
because `GonzoExperimentCallback.on_train_begin` inserts a run with `model_id`
NULL (ADR 0002 §3 — metadata is written once, at train end).

Migration `005_reassert_artifact_and_run_links.sql` repairs this idempotently and
is a no-op where 003 applied correctly, so **you do not need to know which
version 3 prod saw** — but record it anyway, because it tells you whether to
expect `005` to do real work.

## Gate 1 — snapshot and restore

The dev container ships `pg_dump` 17.x, and prod is PostgreSQL 17.10 — so the
client is current and this step is unblocked. The rule still applies if either
side moves: a client cannot dump a *newer* server, so confirm prod's major
version (`select version()`) before assuming your `pg_dump` can read it.

```bash
# Against prod: schema + data for the raw tables and the metadata tables.
pg_dump -h <prod-host> -U <user> -d f1db --schema=f1db --no-owner --no-privileges \
        -Fc -f f1db-snapshot.dump

# Into the scratch server (creates the role/database first if needed).
createdb -h <scratch-host> -U <superuser> f1db
pg_restore -h <scratch-host> -U <superuser> -d f1db --no-owner --no-privileges f1db-snapshot.dump
```

`--schema=f1db` deliberately omits the dbt output schemas (`f1db_staging`,
`f1db_intermediate`, `f1db_features`, `f1db_ml_prep`) — `dbt build` regenerates
those from the raw tables, so dumping them wastes time and hides drift. Include
them only if you specifically want to diff prod's derived tables against a fresh
build.

The restored database needs the app role and its grants. The relevant part of
`db/init_db.sql`, minus the `CREATE DATABASE`:

```sql
CREATE USER gonzo_user WITH ENCRYPTED PASSWORD '<pw>';
GRANT USAGE, ALL PRIVILEGES ON SCHEMA f1db TO gonzo_user;
GRANT CONNECT, CREATE ON DATABASE f1db TO gonzo_user;   -- CREATE is required: dbt makes its own schemas
GRANT ALL ON ALL TABLES IN SCHEMA f1db TO gonzo_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA f1db TO gonzo_user;
```

Omitting `CREATE ON DATABASE` fails later as `permission denied for database f1db`
at the first `dbt build`.

**Check:** row counts match Gate 0, and `\dt f1db.*` shows the 18 Jolpica tables
plus `training_runs`, `training_metrics`, `model_metadata`, `dataset_versions`.

## Gate 2 — migrate

```bash
uv run gonzo-load --db-host <scratch-host> --db-name f1db \
  --db-admin-username <superuser> --db-admin-password <pw> \
  --steps migrate
```

**Check, and do not skip this — the failure here is silent:**

```bash
psql -h <scratch-host> -U <superuser> -d f1db \
  -c "select version_id from f1db.goose_db_version order by version_id" \
  -c "select is_nullable from information_schema.columns
      where table_schema='f1db' and table_name='training_runs' and column_name='model_id'"
```

`model_id` must be `YES`. If it is `NO`, migration `005` did not run — stop and
investigate rather than continuing to training.

Migration `004` drops `f1db.application_logs` and three unused columns. On a
snapshot that is the point; against real prod, be certain you want it. It uses
`IF EXISTS` throughout, so it is safe to re-run.

**On rolling back:** `003`'s Down restores `NOT NULL` on `training_runs.model_id`
and will fail if any run row has a NULL `model_id` — which is every run that
started but never completed. Delete or backfill those rows first. This is a real
property of the Down path, not a snapshot artifact.

## Gate 3 — rebuild the dataset

dbt authenticates separately from `AppConfig`, through `dbt/profiles.yml`:

```bash
cd dbt
export F1DB_HOST=<scratch-host> F1DB_USER=gonzo_user F1DB_PASSWORD=<pw>
export DBT_PROFILES_DIR=$PWD
dbt deps && dbt build
```

Note `dbt/profiles.yml` hardcodes `port: 5432` and `dbname: f1db`; only host,
user and password are parameterized. A scratch server on another port needs the
profile edited.

**Check:** `PASS=36 WARN=1 ERROR=0`. The one warning is expected — it is the
`feat_dnf_handled` uniqueness test reporting `WARN 83`, documented below. Any
`ERROR`, or a warning count other than 1, is not expected. And:

```sql
select count(*) from f1db_ml_prep.prep_training_dataset;
```

Compare that to prod's own `prep_training_dataset` count from Gate 0. A
materially different number means the raw snapshot and prod's derived tables
disagree — worth understanding before you train. Prod's count is **25,873**.

Then the stronger check — the fingerprint, which catches column-order and value
drift that a row count cannot:

```bash
.venv-isolated/bin/python - <<'PY'
import pandas as pd
from gonzo_pit_strategy.config.config import DatabaseConfig
from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.training.data import fingerprint_dataset
Q = "SELECT * FROM f1db_ml_prep.prep_training_dataset"
eng = ConnectionPool(DatabaseConfig(host="<scratch-host>", name="f1db",
                                    user="gonzo_user", password="<pw>")).engine
df = pd.read_sql(Q, eng)
print(df.shape, fingerprint_dataset(df, Q)[:16])
PY
```

Expect `(25873, 408)`. **Expect the fingerprint to differ from prod's**, and read
a mismatch as follows:

| Symptom | Means |
|---|---|
| Different column *order*, same shape and dtypes | Collation — you skipped Gate −1 |
| Same shape and order, only `prev_race_*_scaled` columns differ | The known `feat_lagged` non-determinism. Expected; not a defect in your run |
| Same shape and order, *other* columns differ | A real data difference — worth investigating |
| Different shape | The snapshot's raw tables differ from prod's; go back to Gate 1 |

### The fingerprint is not currently reproducible

`feat_lagged.sql` lags over `PARTITION BY season_year, driver_id ORDER BY
round_number`, and that key is **not unique**: 83 groups / 172 rows in seasons
1950–1964 have a driver entered twice or three times in one round (shared
drives). SQL does not define which tied row `LAG()` returns, so it follows
physical row order — and two independently-built databases order rows
differently.

Because `prep_scaled` standardises with `AVG/STDDEV_POP OVER()`, those 172
ambiguous rows move the mean and stddev and therefore perturb **all 25,873
rows** of `prev_race_points_scaled`, `prev_race_team_wins_scaled` and
`prev_race_race_time_ms_scaled`. Everything else in the dataset is bit-identical.

Measured 2026-07-31 — prod vs a clean greenfield build from
`data/jolpica-f1-csv-2026-01`:

| | value |
|---|---|
| shape | `(25873, 408)` both |
| column order md5 | `fe8845a48a675bd1a4f26b005b9bd2d8` both |
| column type digest | `b98a8e23e43f43fea7b77d579721e91d` both |
| raw table counts | identical |
| columns with differing values | **3**, all `prev_race_*_scaled` |
| fingerprint | prod `d38a960303b77afb` · greenfield `6820cbcc8e821914` |

This was accepted rather than fixed (2026-07-31): the affected seasons all
predate 1965, and the project is filtering to **seasons ≥ 2008**, which removes
every tied group and makes the fingerprint reproducible for free. A
warn-severity `dbt_utils.unique_combination_of_columns` test on
`feat_dnf_handled` tracks it — `dbt build` reports `WARN 83` today, and when
that goes to `PASS` the fingerprint becomes a usable baseline and this section
can be deleted.

Until then, use the **per-column diff** rather than the fingerprint to compare
two databases. `fingerprint_dataset` collapses 408 columns to one value and
cannot tell you which one moved:

```python
{c: int(pd.util.hash_pandas_object(df[c], index=False).sum()) for c in df.columns}
```

## Gate 4 — train

```bash
export DB__HOST=<scratch-host> DB__PORT=5432 DB__NAME=f1db \
       DB__USER=gonzo_user DB__PASSWORD=<pw>
uv run gonzo-train --config config/experiments/training_config_default.json
```

Double underscore is load-bearing: `DB_HOST` matches no field and is silently
discarded. Environment variables take precedence over `.env`, so exporting these
is how you point a run at the scratch database without editing your `.env`.

> **`.env` currently points at prod.** This is the first gate that *writes*, and
> a typo in the `DB__` exports falls back to `.env` — i.e. to prod — rather than
> failing. Confirm before you train, the same way Gate 5 does:
>
> ```bash
> .venv-isolated/bin/python -c \
>   "from gonzo_pit_strategy.config.config import AppConfig; print(AppConfig().db.host)"
> ```

Lower `epochs` for a first pass — you are testing the pipeline, not the model.
Copy the config and override rather than editing the tracked default:

```bash
python -c "import json;c=json.load(open('config/experiments/training_config_default.json'));\
c['epochs']=5;json.dump(c,open('/tmp/e2e_smoke.json','w'),indent=2)"
```

**Check** — the artifact and the reporting mirror must agree:

```sql
select run_id, model_id, dataset_version_id, status, epochs_completed
from f1db.training_runs order by run_id desc limit 5;
select model_id, version, artifact_path from f1db.model_metadata order by model_id desc limit 5;
select dataset_version_id, version, record_count, feature_count from f1db.dataset_versions;
```

One new `training_runs` row, `status = COMPLETED`, and **both** `model_id` and
`dataset_version_id` non-null. `models/artifacts/<version>/` must contain exactly
`model.keras` and `manifest.json`.

`dataset_versions` is content-addressed, so repeated runs over unchanged data
reuse one row — several runs sharing a `dataset_version_id` is correct, not a bug.

Also confirm the log order at train end reads *"Restoring model weights…"*
**before** *"Saved artifact to…"*. Reversed means the artifact holds the final
epoch's weights while the reported metrics describe the best epoch (ADR 0002,
amendment 2026-07-30). `tests/test_runner.py` guards this, but it costs nothing
to eyeball on a real run.

## Gate 5 — round-trip inference

The point of ADR 0002: the artifact rehydrates with zero database calls. This
predicts on a raw slice of the dataset, which is what catches encoding skew.

```python
import pandas as pd
from gonzo_pit_strategy.config.config import AppConfig
from gonzo_pit_strategy.db.connection_pool import ConnectionPool
from gonzo_pit_strategy.inference.predictor import load_predictor

cfg = AppConfig()
assert cfg.db.host == "<scratch-host>", cfg.db.host   # cheap guard against hitting prod
df = pd.read_sql("SELECT * FROM f1db_ml_prep.prep_training_dataset LIMIT 20",
                 ConnectionPool(cfg.db).engine)

p = load_predictor("<model_version>", cfg.paths)
print(p.predict(df).ravel()[:5])
print(df[p.manifest.target_column].values[:5])
```

`prep_training_dataset` legitimately contains `object`-dtype columns (Postgres
returns those for all-NULL numerics), so this path exercises `prepare_features`.
`ValueError: Invalid dtype: object` here means training and inference have
diverged again.

## If you want to run against real prod rather than a snapshot

Three things change, and none are in the code:

1. `dbt build` **drops and recreates** every table in the four dbt schemas. Only
   derived data, but prod consumers reading those tables will see them vanish
   mid-build.
2. Training writes real rows to `training_runs`, `training_metrics`,
   `model_metadata` and `dataset_versions`.
3. Migration `004` is destructive by design.

The Vault path is *unverified* here — it self-disables without `VAULT__ADDR`,
`VAULT__ROLE_ID` and `VAULT__SECRET_ID`, and a fetch *failure* logs a warning and
falls through to the field default rather than aborting. Against prod, confirm the
resolved credentials before trusting a run: `AppConfig().db.host` and `.user`
should be prod's, and a silent fallback to `localhost` / `local_dev_password`
means Vault did not resolve.
