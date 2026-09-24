# ADR 0002: Self-Describing Artifacts; Database as Reporting Mirror

## Status

Accepted 2026-07-29. Lifecycle revisions landed through 2026-07-31.
Publication guarantees added 2026-09-24. See *History* for the reasons behind
these decisions.

## Context

The Artifact concept had no owning module. The artifact path was re-derived by
string-joining in five call sites; `ModelRepository.load_model` guessed among
three file formats; `ModelPredictor` unpacked a return value that didn't exist
(crashing on any real call); and `feature_names` — the model's input-ordering
contract — was computed at training time and discarded, making correct
inference rehydration impossible. Model metadata was written twice per run
(placeholder at train begin, update at train end), with the metadata dict
duplicated across `callbacks.py` and `model_repository.py`.

## Decision

1. **Artifacts are self-describing.** An artifact directory contains
   `model.keras` plus an Artifact Manifest (`manifest.json`) carrying
   `feature_names` in training order, target column, training config, framework
   version, the Dataset Fingerprint, and — so that "the Artifact is the model
   these metrics describe" is checkable from the directory alone —
   `test_metrics`, `dataset_name`, and `epochs_completed`. Inference rehydrates
   from disk alone: zero database calls.

2. **One owner per concern.** `training/artifact.py` (`ArtifactStore`,
   `ArtifactManifest`) owns artifact layout, save, and load; no other module
   joins artifact paths or touches artifact files. `artifacts_root` is the sole
   output location — there is no separate checkpoint directory and no second
   writer of model files.

   `ArtifactStore.save` publishes the model and Artifact Manifest together.
   It rejects every occupied version with `FileExistsError`, including empty
   directories, symlinks, and repeated identical saves. Serialization happens
   in a private `.gonzo-stage-*` directory beneath the Artifact root. Linux
   `renameat2` with `RENAME_NOREPLACE` publishes that directory in one operation.
   Unsupported publication fails rather than falling back to an ordinary rename.

   These guarantees cover concurrent writers and readers, ordinary exceptions,
   and abrupt process termination on local Linux filesystems. Power-loss
   durability and concurrent deletion are outside the contract. Catchable
   failures clean up staging. A killed process can leave hidden staging, which
   loaders reject even through symlink aliases. Automatic stale-staging cleanup
   is intentionally absent because it could remove an active writer's files.

   Versions are single directory names, and `.gonzo-stage-` is reserved for
   unpublished work. New Experiments use the model type followed by a full UUIDv4
   in hexadecimal form. Existing timestamp-named Artifacts keep their layout and
   remain loadable without native publication support or a database connection.

3. **The database is a reporting mirror, and the Run Ledger owns it.** One
   module owns everything the database records about a Training Run: the run
   row, per-epoch Training Metrics, the Model Metadata mirror, and the
   DatasetVersion link. The `RunLedger` interface lives in `training/ledger.py`
   in training's own vocabulary; `db/run_ledger.py` holds the Postgres adapter
   and `tests/fakes.py` the in-memory one. The dependency runs one way — `db`
   imports `training`, never the reverse. Callers never see a SQLAlchemy
   `Session`.

   The interface is a **context manager**, so a Training Run always reaches a
   terminal status:

   ```python
   with ledger.run(config) as run:
       model.fit(..., callbacks=[EpochMetricsCallback(run)])
       run.complete(manifest, artifact_dir, provenance, epochs_completed=n)
   ```

   Leaving the block without completing marks the run `FAILED`. The Model
   Metadata row is written once, at train end — no placeholder rows;
   `TrainingRun.model_id` stays nullable until then. `TrainingRun` status
   provides live-run visibility.

4. **The Experiment lifecycle is sequential code, not callbacks.**
   `Experiment.run` executes fit → evaluate → build manifest → save Artifact →
   mirror to database as ordinary statements. `training/callbacks.py` keeps
   only what genuinely needs an epoch boundary: `EpochMetricsCallback` and
   `ConsoleMetricsCallback`. Evaluation uses `return_dict=True` (positional
   zipping against `model.metrics_names` labels the metric `compile_metrics`
   under Keras 3 — tolerable in a log line, not in a permanent record).

5. **Paths come from AppConfig** (`PathsConfig`), injected per ADR 0001 — never
   derived from `os.getcwd()`.

6. **The manifest pins columns; `prepare_features` pins encoding.**
   `feature_names` fixes *which* columns a model expects and in what order, but
   not how their values are encoded. Both training and inference call one shared
   `prepare_features` in `training/data.py`.

   Rule of thumb: any transformation applied between the RawDataset and
   `model.fit` must live in `prepare_features` so inference gets it too.
   Transformations belonging to the *dataset* rather than the model — scaling
   parameters, feature derivation — stay in dbt (see ADR 0003).

7. **DatasetVersion is identified by a content fingerprint** (sha256 over
   schema, row count, content digest, and query text) computed at fetch time,
   upserted at train end and linked from `TrainingRun.dataset_version_id`.
   `TrainingDataSource` carries its own `dataset_name`; name, fingerprint,
   record count, and feature count travel together as a `DatasetProvenance`
   value from the source through `LoadedData` into both the Artifact Manifest
   and the Run Ledger — so the artifact and the mirror cannot describe
   different data.

## Consequences

### Positive

- Inference works offline from the artifact directory; copying the directory
  copies everything needed to serve the model.
- The feature-ordering contract is explicit and enforced (`df[feature_names]`
  fails loudly on missing columns).
- Save/load round-trips are testable in a temp dir without a database or GPU.
  Tests construct a real `Experiment` with a temp-dir store and an in-memory
  ledger and patch nothing.
- Reproducibility is queryable: every run records which data it trained on.
- A crashed Sweep iteration cannot leave a run row stuck at `RUNNING`.

### Negative

- Manifest and DB mirror can drift if the DB write fails after the artifact
  save; the artifact remains authoritative.
- Artifacts saved before this ADR lack manifests and cannot be rehydrated by
  the new loader.
- `RunLedger` has two adapters that can diverge, and they had already diverged.
  `tests/test_run_ledger_contract.py` now runs one suite against both; on first
  execution (2026-08-03) six of its assertions failed against the in-memory
  adapter and none against Postgres. The fake did not split `val_`-prefixed
  metrics, did not record `test_metrics` as TEST-split rows, wrote an entry for
  an empty `logs` dict, and modelled no DatasetVersion at all — so a green suite
  could assert things that were false in production.

  The fake was corrected to match; `split_metric` moved into
  `training/ledger.py` so the prefix rule has one implementation beside the
  docstring that specifies it, rather than a copy per adapter. The Postgres
  params skip cleanly when no database is reachable, so the core suite still
  needs neither a database nor a GPU.
- `ModelRepository`'s four read methods (`get_model_metadata`,
  `get_model_metadata_by_version`, `list_models`, `delete_model_record`) were
  removed rather than ported — they had no callers and no tests. They should
  come back shaped by a real caller.

## History

The corrections below explain how failures shaped the current decisions.

### Publication protects earlier Artifacts, 2026-09-24

The sequential Experiment lifecycle made each save describe its evaluated model,
but did not protect that Artifact from a later save. Second-resolution versions
could collide, and saving reused the final directory. A later Experiment could
replace the model before the database rejected its duplicate Model Metadata.
An interrupted overwrite could also pair a new model with an old manifest.

Publication now has one owner in ArtifactStore. Callers still call
`store.save(model, manifest)` and receive the final directory. Each writer owns
separate staging, and the kernel rejects an occupied destination at publication
time. A preliminary existence check alone is insufficient because ordinary
rename can replace an empty directory created after that check.

We chose native no-replacement rename over a shared lock file. A lock would
require every writer to follow the same protocol and preserve the same lock
inode. The native operation enforces no-replacement without that shared state.
The tradeoff is a small Linux-specific binding and a filesystem capability
requirement. Public interfaces and the two-file Artifact layout do not change.

`tests/test_artifact.py` covers occupied destinations, interrupted writes,
unsupported publication, staging isolation, and historical loading.
`tests/test_artifact_publication.py` coordinates spawned writers and kills them
before and after publication. `tests/test_runner.py` reloads every successful
Sweep Artifact after the Sweep finishes and checks its own recorded metrics.

Death after publication can leave a complete Artifact without a completed Run
Ledger entry. The Artifact remains authoritative. A retry with the same version
fails rather than replacing it. SIGKILL cannot execute Run Ledger cleanup, so
this filesystem guarantee does not guarantee a terminal Training Run after
process death.

### The manifest pinned columns but not encoding (2026-07-29)

`load_training_data` coerced `object` columns (Postgres returns those for
all-NULL numerics) and cast the dbt one-hot columns from `bool` to `int`;
`ModelPredictor.predict` did neither. Predicting on a raw slice of
`prep_training_dataset` — the exact table the model was trained on — failed with
`ValueError: Invalid dtype: object`. That is live train/serve skew, and it
produced Decision 6.

The bool-to-int step no longer keys off column-name prefixes
(`circuit_`/`team_`/`driver_`); it converts every boolean column, so adding a
one-hot family in dbt needs no corresponding Python change.

### The Artifact was not the model the metrics described (2026-07-30)

Removing `ModelCheckpoint` leaned the "the Artifact is the best checkpoint"
argument entirely on `EarlyStopping(restore_best_weights=True)`. That argument
had a hole: `EarlyStopping` and `GonzoExperimentCallback` both acted in
`on_train_end`, Keras invokes callbacks **in list order**, and
`GonzoExperimentCallback` was first. The Artifact was written with the *final*
epoch's weights; the best weights were restored afterwards, into the in-memory
model that `model.evaluate` then measured. **The recorded test metrics described
a model that was never saved.** While `ModelCheckpoint` existed, its
`save_best_only` file masked this. The run observed at 2026-07-30 02:40 saved
the artifact and only then logged *"Restoring model weights from the end of the
best epoch."*

The first fix ordered the callback list and asserted the ordering in a test.
Note what that test deliberately did *not* do: a test that trains and checks
whether the reloaded artifact reproduces `test_loss` only detects the bug when
the best epoch differs from the last one — on a fixture whose `val_loss`
improves monotonically the restore is a no-op and the assertion passes
vacuously. That version was written first and confirmed to pass against the
known-buggy ordering.

### The ordering constraint moved out of the callback list (2026-07-31)

The ordering fix above is **superseded in mechanism, preserved in intent**, and
produced Decision 4.

The problem was the shape, not the order. Expressing a once-per-run lifecycle as
`on_train_end` handlers made a load-bearing ordering constraint invisible at the
call site: nothing at the point of appending a callback shows that it must
follow `EarlyStopping`, so the constraint could only be defended by a comment,
an ADR, and a test asserting list indices. As sequential statements, the
ordering *is* the code. `GonzoExperimentCallback` was deleted.

This also made the invariant directly testable. `tests/test_runner.py` reloads
the saved Artifact and requires it to reproduce the reported `test_loss`
exactly. Unlike the loss comparison rejected above, this cannot pass vacuously —
the artifact either is or is not the evaluated model. It was confirmed to fail
against a deliberately mutated runner that saves weights other than the
evaluated ones.

### The Run Ledger took ownership of the database record (2026-07-31)

Decision 3 originally said the database is a reporting mirror but named no
owner, so the writes spread out: `ModelRepository` held only `record_model`,
while the `TrainingRun` insert and update, the per-epoch `TrainingMetric`
writes, and the `DatasetVersion` upsert were hand-rolled `session.query(...)`
chains inside `GonzoExperimentCallback`.

The effective seam was therefore a SQLAlchemy `Session`, and testing training at
all required simulating one — `tests/test_runner.py` carried a
`_FakeSession`/`_FakeQuery` pair implementing `filter_by`, `distinct`, `first`,
`one`, and `count`, coupled to the exact query shapes in the callback. Moving
the seam to `RunLedger` deleted all of that, and closed the mutual import that
existed while `ModelRepository` imported `ArtifactManifest`.

The context-manager shape was chosen because the run previously opened in
`on_train_begin` and closed in `on_train_end`: anything that raised between them
left the row `RUNNING` forever — worst inside a Sweep, which catches
per-experiment exceptions and continues, silently accumulating stuck rows.

Two smaller consequences: `epochs_completed` now comes from the training history
rather than a `COUNT(DISTINCT epoch)` over `training_metrics`, and test metrics
are written as `TrainingMetric` rows with `split_type='TEST'`, a value the schema
already allowed but nothing used.

### Violations closed along the way

A duplicate `artifact.py` at the package root was deleted. The `ModelCheckpoint`
callback in `training/runner.py` — a second writer of model files, in breach of
Decision 2 — was removed; `PathsConfig.checkpoints_dir` went with it.
`cli/train.py` no longer derives paths from `os.getcwd()`.
