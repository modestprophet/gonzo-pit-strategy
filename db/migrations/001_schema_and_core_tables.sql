-- +goose Up
-- Application Logs
CREATE TABLE application_logs (
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
CREATE INDEX idx_app_logs_timestamp ON application_logs(timestamp);
CREATE INDEX idx_app_logs_level ON application_logs(level);

-- Dataset Versions
CREATE TABLE dataset_versions (
    dataset_version_id SERIAL PRIMARY KEY,
    dataset_name VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    data_path VARCHAR(255),
    record_count INTEGER,
    feature_count INTEGER,
    preprocessing_steps TEXT[],
    UNIQUE(dataset_name, version)
);

-- Model Metadata
CREATE TABLE model_metadata (
    model_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    architecture TEXT,
    framework_version VARCHAR(50),
    repository_link VARCHAR(255),
    tags TEXT[],
    configuration JSONB,
    config_source_path VARCHAR(255),    -- Optional
    UNIQUE(name, version)
);

-- Training Runs
CREATE TABLE training_runs (
    run_id SERIAL PRIMARY KEY,
    model_id INTEGER NOT NULL REFERENCES model_metadata(model_id) ON DELETE CASCADE,
    dataset_version_id INTEGER REFERENCES dataset_versions(dataset_version_id),
    start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    status VARCHAR(20) CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    epochs_completed INTEGER DEFAULT 0,
    early_stopping BOOLEAN DEFAULT FALSE,
    environment_id VARCHAR(100)
);

-- Training Metrics
CREATE TABLE training_metrics (
    metric_id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES training_runs(run_id) ON DELETE CASCADE,
    epoch INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    split_type VARCHAR(20) CHECK (split_type IN ('TRAIN', 'VALIDATION', 'TEST'))
);

-- +goose Down
DROP TABLE IF EXISTS training_metrics;
DROP TABLE IF EXISTS training_runs;
DROP TABLE IF EXISTS model_metadata;
DROP TABLE IF EXISTS dataset_versions;
DROP TABLE IF EXISTS application_logs;