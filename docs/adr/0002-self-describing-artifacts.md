# ADR 0002: Self-Describing Artifacts; Database as Reporting Mirror

## Status
Accepted; fully landed 2026-07-29.

Two violations were closed at that point: a duplicate `artifact.py` at the
package root was deleted, and the `ModelCheckpoint` callback in
`training/runner.py` — a second writer of model files, in breach of Decision 2 —
was removed. `EarlyStopping(restore_best_weights=True)` already leaves the best
weights in the model at train end, so the Artifact *is* the best checkpoint;
`PathsConfig.checkpoints_dir` went with it, leaving `artifacts_root` as the sole
output location. `cli/train.py` no longer derives paths from `os.getcwd()`
(Decision 4).

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
   `model.keras` plus an Artifact Manifest (`manifest.json`) with
   `feature_names` in training order, target column, training config,
   framework version, and the Dataset Fingerprint. Inference rehydrates from
   disk alone — zero database calls.
2. **One owner.** `training/artifact.py` (`ArtifactStore`, `ArtifactManifest`)
   owns artifact layout, save, and load. No other module joins artifact paths
   or touches artifact files.
3. **The database is a reporting mirror.** `ModelRepository.record_model`
   writes the manifest into `ModelMetadata` (including `artifact_path`) once,
   **at train end**. No placeholder rows; `TrainingRun.model_id` is nullable
   until then. `TrainingRun` status still provides live-run visibility.
4. **Paths come from AppConfig** (`PathsConfig`), injected per ADR 0001 —
   never derived from `os.getcwd()`.
5. **DatasetVersion is identified by a content fingerprint** (sha256 over
   schema, row count, content digest, and query text) computed at fetch time,
   upserted at train end and linked from `TrainingRun.dataset_version_id`.

## Consequences

### Positive
- Inference works offline from the artifact directory; copying the directory
  copies everything needed to serve the model.
- The feature-ordering contract is explicit and enforced (`df[feature_names]`
  fails loudly on missing columns).
- Save/load round-trips are testable in a temp dir without a database or GPU.
- Reproducibility is queryable: every run records which data it trained on.

### Negative
- Manifest and DB mirror can drift if the DB write fails after the artifact
  save; the artifact remains authoritative.
- Artifacts saved before this ADR lack manifests and cannot be rehydrated by
  the new loader.

## Amendment (2026-07-29): the manifest pins columns, not encoding

`feature_names` fixes *which* columns a model expects and in what order, but not
how their values are encoded — and that gap was live train/serve skew.
`load_training_data` coerced `object` columns (Postgres returns those for
all-NULL numerics) and cast the dbt one-hot columns from `bool` to `int`;
`ModelPredictor.predict` did neither. Predicting on a raw slice of
`prep_training_dataset` — the exact table the model was trained on — failed with
`ValueError: Invalid dtype: object`.

Both paths now call one shared `prepare_features` in `training/data.py`. The
bool-to-int step also no longer keys off column-name prefixes
(`circuit_`/`team_`/`driver_`); it converts every boolean column, so adding a
one-hot family in dbt needs no corresponding Python change.

Rule of thumb: any transformation applied between the RawDataset and `model.fit`
must live in `prepare_features` so inference gets it too. Transformations that
belong to the *dataset* rather than the model — scaling parameters, feature
derivation — stay in dbt.

## Amendment (2026-07-30): the Artifact must be the model the metrics describe

Removing `ModelCheckpoint` (see *Status*) leaned the whole "the Artifact is the
best checkpoint" argument on `EarlyStopping(restore_best_weights=True)`. That
argument had a hole: `EarlyStopping` and `GonzoExperimentCallback` both act in
`on_train_end`, Keras invokes callbacks **in list order**, and
`GonzoExperimentCallback` was first. So the Artifact was written with the *final*
epoch's weights and the best weights were restored afterwards — into the
in-memory model that `model.evaluate` then measured. The recorded test metrics
described a model that was never saved. While `ModelCheckpoint` existed its
`save_best_only` file masked this; the run observed at 2026-07-30 02:40 saved the
artifact and only then logged *"Restoring model weights from the end of the best
epoch"*.

**Decision 2 is therefore extended:** the single artifact writer must be the
**last** `on_train_end` callback, so every weight-mutating callback has already
run. `runner.py` now appends `experiment_cb` last, and
`tests/test_runner.py` asserts `EarlyStopping` precedes it.

That test asserts the *ordering*, not a loss comparison. A test that trains and
checks whether the reloaded artifact reproduces `test_loss` only detects the bug
when the best epoch differs from the last one — on a fixture whose `val_loss`
improves monotonically the restore is a no-op and the assertion passes
vacuously. That version was written first and confirmed to pass against the
known-buggy ordering.
