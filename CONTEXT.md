# Gonzo Pit Strategy - Domain Context

This document captures the ubiquitous language of the project. Use these terms exactly as defined in discussions, variable names, and architecture.

## ML and Training Concepts
- **Experiment**: A single execution of a model training process. It encapsulates the full lifecycle: building the architecture, running the training loop, logging metrics to the database, and saving the final Artifact.
- **Sweep** / **Grid Search**: A formal module that executes a collection of Experiments sequentially or in parallel to explore a hyperparameter space, emitting interim results.
- **Model Metadata**: Information about a trained model (hyperparameters, metrics, path to physical artifacts) stored *exclusively* in the relational database. Used for reporting and inference rehydration.
- **Artifact**: The physical files produced by training (e.g., `.keras` weights).
- **RawDataset**: The untransformed, raw data fetched from a source (e.g. database, CSV) before any ML-specific feature engineering, NaN filling, or dataset splitting occurs.
- **TrainingDataSource**: The interface boundary that provides a `RawDataset` to the training pipeline, decoupling data extraction from data transformation.

## Configuration
- **Environment**: The deployment context of the application (e.g., `development`, `testing`, `production`). Determines behavior like logging verbosity and Vault paths.
- **AppConfig**: The single, unified, strongly-typed configuration tree for the entire application, hydrated via Environment Variables and Vault secrets.
- **Vault Settings Source**: An adapter that transparently bridges HashiCorp Vault secrets into the AppConfig tree during application startup.
