-- +goose Up
-- Re-assert migration 003 idempotently.
--
-- Two different files once claimed version 3: the ADR-0002 migration
-- (003_artifact_and_run_links.sql, kept) and an earlier
-- 003_model_metadata_artifact_path.sql (deleted) that only added
-- model_metadata.artifact_path. goose tracks applied migrations by *version
-- number*, not filename, so any database that recorded version 3 from the
-- deleted file will silently skip the kept one — reporting "successfully
-- migrated" while training_runs.model_id stays NOT NULL. Training then fails on
-- its first write, because GonzoExperimentCallback.on_train_begin inserts a run
-- with model_id NULL (ADR 0002 §3: metadata is written once, at train end).
--
-- Both statements are no-ops where 003 applied correctly, so this is safe to run
-- against any database regardless of which version 3 it saw.
ALTER TABLE f1db.model_metadata ADD COLUMN IF NOT EXISTS artifact_path VARCHAR(255);
ALTER TABLE f1db.training_runs ALTER COLUMN model_id DROP NOT NULL;

-- +goose Down
-- Deliberately not reversed. Restoring NOT NULL on training_runs.model_id would
-- break training, and 003's own Down already covers the rollback path for any
-- database that applied it. Dropping artifact_path here could also destroy a
-- column this migration did not create.
SELECT 1;
