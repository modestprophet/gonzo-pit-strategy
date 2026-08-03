# ADR 0003: Feature Engineering Belongs to dbt; the Seam Is Inference, Not Language

## Status

Accepted 2026-08-03.

## Context

The migration to dbt was undertaken to reduce project complexity and to make
data-transformation changes reviewable in version control. Feature engineering
ending up in SQL was a **side effect** of that migration, not a decision anyone
made deliberately — which is why the arrangement has never been recorded, and
why the question of where transformation code belongs has stayed open.

Two pressures reopened it:

1. **Discomfort with SQL as an authoring language.** The transformations that
   need dbt macros — `clean_column_name`, `convert_lap_time_to_seconds`,
   `convert_race_time_to_ms`, `z_score_clip` — are correct and working, but
   Python is the more comfortable medium, and a step-through debugger is a
   valued part of that workflow.
2. **Uncertainty about the engine.** Local PySpark and DuckDB were both
   considered as ways to get Python into the transformation layer.

Underneath both sat an unanswered architectural question: *what actually
separates dbt's territory from Python's?* Without an answer, the split was
being drawn along language lines, which is not a property the system cares
about.

ADR 0002 §6 had already answered it implicitly, for one narrow case:

> any transformation applied between the RawDataset and `model.fit` must live in
> `prepare_features` so inference gets it too.

This ADR generalizes that rule and settles the engine question.

## Decision

1. **The seam is inference, not language.** A transformation belongs to dbt if
   it defines *the dataset*; it belongs to `prepare_features` if *inference must
   reproduce it at request time*. The question to ask of any transformation is
   **"does the predictor have to do this too?"** — not "is this SQL or Python?"

   The invariant this protects is train/serve skew, which has bitten this
   project once already (ADR 0002, *History* 2026-07-29).

2. **dbt owns dataset-level feature engineering.** DNF handling, time
   conversion, lagging, season progress, one-hot encoding, and scaling are dbt
   models. They are materialized, they are covered by the Dataset Fingerprint,
   and inference never repeats them — it receives rows that already have them.

3. **`prepare_features` owns model-level encoding**, and nothing else does.
   Value coercion applied identically at training and inference time. See
   ADR 0002 §6.

4. **Engine is an implementation detail behind the seam.** A PySpark or Python
   transformation that materializes rows into `f1db_ml_prep` would sit on the
   *dataset* side of the seam despite being Python, exactly as dbt SQL does.
   The seam does not move if the engine changes. This is why the engine question
   is separable from — and much smaller than — the ownership question.

## Rejected: migrating the transformation layer to Python

Considered and rejected for now. The reasoning, so it is not re-litigated:

- **Scale doesn't justify it.** The largest table is ~665k rows. Postgres is
  already local compute and handles this comfortably. Spark's parallelism
  addresses a problem this project does not have, at the cost of JVM startup,
  serialization overhead, and a worse debugging experience.
- **The surface is 42 lines.** The entire macro layer is four files totalling
  42 lines of SQL. Migrating an engine to avoid that is a large price for a
  small surface.
- **The debugger gap is smaller than it looks.** What a debugger provides here
  is inspection of intermediate values, and dbt already provides that more
  durably: `staging`, `intermediate`, and `features` are all materialized as
  views, so every layer is directly queryable, persists after the run, and can
  be diffed between runs. `dbt compile` shows macro expansion; `dbt show`
  previews without materializing; a notebook can read any intermediate model
  into pandas for full inspection.
- **It would weaken the project as a showpiece.** A Keras pipeline fed by a
  layered dbt warehouse demonstrates more than the same pipeline doing its
  transformations in pandas.

## Revisit if

- A transformation genuinely requires a Python library with no reasonable SQL
  equivalent — a fitted `sklearn` transformer whose learned parameters must be
  persisted, for example. That is a capability gap, not a preference, and it is
  the trigger this ADR is designed to admit.
- Dataset size grows past what Postgres handles comfortably in a single-node
  build.

At that point the options are, in ascending order of disruption: a pandas step
materializing back into Postgres between dbt stages; DuckDB as the
transformation engine (embedded, in-process, native pandas interop); or a
distributed engine. **Note that `dbt-postgres` does not support Python models** —
they exist on Snowflake, BigQuery, and Databricks — so "just write a dbt Python
model" is not available on the current warehouse. Verify current adapter support
before relying on this.

## Consequences

### Positive

- The dbt/Python question has a criterion that can be applied to a new
  transformation in one step, rather than being re-argued each time.
- The train/serve skew invariant now has an explicit owner and an explicit rule,
  rather than living inside an amendment to a different ADR.
- The engine question is deferred without being lost, with a concrete trigger.

### Negative

- Authoring transformations stays in SQL, which is the less comfortable medium
  for this project's author. Accepted deliberately; the cost is learning a small
  number of SQL patterns rather than migrating an engine.
- dbt macro logic is not unit-tested the way Python transformation code would
  be. dbt tests cover model output, not macro behaviour in isolation.
