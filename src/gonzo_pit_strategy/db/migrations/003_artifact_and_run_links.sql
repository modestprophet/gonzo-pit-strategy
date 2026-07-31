-- +goose Up
-- ADR 0002: artifacts are self-describing on disk; the DB mirrors the manifest
-- for reporting. model_metadata records where the artifact lives, and
-- training_runs no longer requires a model row up front (metadata is written
-- once, at train end).
ALTER TABLE f1db.model_metadata ADD COLUMN artifact_path VARCHAR(255);
ALTER TABLE f1db.training_runs ALTER COLUMN model_id DROP NOT NULL;

-- +goose Down
ALTER TABLE f1db.training_runs ALTER COLUMN model_id SET NOT NULL;
ALTER TABLE f1db.model_metadata DROP COLUMN artifact_path;
