-- +goose Up
-- Drop schema that no live code reads or writes.
--
-- application_logs: never referenced from Python; logging goes to stdout only.
-- model_metadata.repository_link: written nowhere.
-- dataset_versions.data_path / preprocessing_steps: written only by the Python
--   preprocessing pipeline that dbt replaced (see dbt/models/features/*).
DROP TABLE IF EXISTS f1db.application_logs;
ALTER TABLE f1db.model_metadata DROP COLUMN IF EXISTS repository_link;
ALTER TABLE f1db.dataset_versions DROP COLUMN IF EXISTS data_path;
ALTER TABLE f1db.dataset_versions DROP COLUMN IF EXISTS preprocessing_steps;

-- +goose Down
ALTER TABLE f1db.dataset_versions ADD COLUMN preprocessing_steps TEXT[];
ALTER TABLE f1db.dataset_versions ADD COLUMN data_path VARCHAR(255);
ALTER TABLE f1db.model_metadata ADD COLUMN repository_link VARCHAR(255);
CREATE TABLE f1db.application_logs (
    log_id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    level VARCHAR(10) NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    component VARCHAR(100),
    message TEXT NOT NULL,
    stack_trace TEXT,
    user_id INTEGER,
    correlation_id VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_app_logs_timestamp ON f1db.application_logs(timestamp);
CREATE INDEX idx_app_logs_level ON f1db.application_logs(level);
