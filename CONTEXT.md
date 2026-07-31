# Gonzo Pit Strategy - Domain Context

This document captures the ubiquitous language of the project. Use these terms exactly as defined in discussions, variable names, and architecture.

## ML and Training Concepts
- **Experiment**: A single execution of a model training process. It encapsulates the full lifecycle: building the architecture, running the training loop, logging metrics to the database, and saving the final Artifact.
- **Sweep** / **Grid Search**: A formal module that executes a collection of Experiments sequentially or in parallel to explore a hyperparameter space, emitting interim results.
- **Model Metadata**: The relational-database *reporting mirror* of a trained model's Artifact Manifest (hyperparameters, metrics, artifact path). Used for reporting and queries only — never for inference rehydration (see ADR 0002).
- **Artifact**: A self-describing directory produced by training: the model file (`model.keras`) plus the Artifact Manifest. The sole source of truth for inference rehydration; no database call is required to load a model.
- **Artifact Manifest**: The `manifest.json` saved inside an Artifact, carrying everything needed to rehydrate the model — most importantly `feature_names` in training order (the model's input contract), plus target column, training config, and the Dataset Fingerprint.
- **Dataset Fingerprint**: A content hash of a RawDataset (schema, row count, content digest, source query) computed at fetch time. Identifies a DatasetVersion so Experiments record exactly which data they trained on.
- **RawDataset**: The untransformed, raw data fetched from a source (e.g. database, CSV) before any ML-specific feature engineering, NaN filling, or dataset splitting occurs.
- **TrainingDataSource**: The interface boundary that provides a `RawDataset` to the training pipeline, decoupling data extraction from data transformation.
- **Feature Preparation**: The value-encoding half of the model's input contract (`prepare_features` in `training/data.py`) — object columns coerced to numeric, booleans to integers, NaN filled. Applied identically at training and inference time; applying it in only one place is train/serve skew. The Artifact Manifest fixes *which* columns and their order, Feature Preparation fixes *how* their values are encoded.

## Configuration
- **Environment**: The deployment context of the application (e.g., `development`, `testing`, `production`). Determines behavior like logging verbosity and Vault paths.
- **AppConfig**: The single, unified, strongly-typed configuration tree for the entire application, hydrated via Environment Variables and Vault secrets.
- **Vault Settings Source**: An adapter that transparently bridges HashiCorp Vault secrets into the AppConfig tree during application startup.
