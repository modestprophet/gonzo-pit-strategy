-- +goose Up
ALTER TABLE f1db.training_runs DROP COLUMN environment_id;

-- +goose Down
ALTER TABLE f1db.training_runs ADD COLUMN environment_id VARCHAR(100);
