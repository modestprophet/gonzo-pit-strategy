# gonzo-pit-strategy
Forecasting Formula 1 Grand Prix Pitstops


# Project Structure Specification
## Project Requirements
- **ML Framework**: TensorFlow/Keras (BiLSTM with attention)
- **Database**: PostgreSQL with SQLAlchemy ORM; goose for migrations; repository pattern
- **Infrastructure**: Single-machine training, FastAPI inference, GCP deployment (prod), local linux deployment (dev)
- **Versioning**: Git for code/models, PostgreSQL for data/metrics
- **Scale**: <100MB datasets, single developer
- **Config**: json files in config directory, .env file for APP_ENV (prod|dev) and initial secrets
- **Logging**: stdout and postgres logging available

## Refined Project Structure

```text
├── config
│   ├── config.py
│   ├── database.json
│   ├── inference.json
│   ├── logging.json
│   ├── model.json
│   └── training.json
├── data
│   └── raw
│       ├── circuits_202503231936.tsv
│       ├── constructorresults_202503231937.tsv
│       ├── constructors_202503231937.tsv
│       ├── constructorstandings_202503231937.tsv
│       ├── drivers_202503231937.tsv
│       ├── driverstandings_202503231938.tsv
│       ├── laptimes_202503231938.tsv
│       ├── pitstops_202503231938.tsv
│       ├── qualifying_202503231939.tsv
│       ├── races_202503231939.tsv
│       ├── results_202503231939.tsv
│       ├── seasons_202503231939.tsv
│       ├── sprintresults_202503231939.tsv
│       └── status_202503231939.tsv
├── db
│   ├── base.py
│   ├── config.py
│   ├── connection_pool.py
│   ├── init_db.sql
│   ├── __init__.py
│   ├── migrations
│   │   ├── 001_schema_and_core_tables.sql
│   │   └── 002_raw_data.sql
│   ├── models
│   │   ├── application_logs.py
│   │   ├── dataset_versions.py
│   │   ├── f1_models.py
│   │   ├── __init__.py
│   │   ├── model_metadata.py
│   │   ├── __pycache__
│   │   ├── training_metrics.py
│   │   └── training_runs.py
│   ├── __pycache__
│   ├── raw_data_base_ddls.sql
│   └── repositiries
│       ├── base_repository.py
│       ├── data_repository.py
│       ├── __init__.py
│       ├── metrics_repository.py
│       └── __pycache__
├── gonzo_pit_strategy
│   ├── cli
│   │   ├── __init__.py
│   │   ├── predict.py
│   │   └── train.py
│   ├── constants.py
│   ├── exceptions.py
│   ├── __init__.py
│   ├── log
│   │   ├── db_logger.py
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── __pycache__
│   ├── main.py
│   ├── __pycache__
│   └── utils
│       ├── db_setup.py
│       ├── db_utils.py
│       └── __init__.py
├── inference
│   ├── api
│   │   ├── endpoints.py
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── router.py
│   ├── __init__.py
│   ├── main.py
│   ├── middleware
│   │   ├── __init__.py
│   │   └── logging.py
│   └── predictor.py
├── __init__.py
├── LICENSE
├── models
│   ├── __init__.py
│   ├── layers
│   │   ├── attention.py
│   │   └── __init__.py
│   ├── model.py
│   └── utils
│       ├── __init__.py
│       └── model_io.py
├── notebooks
│   └── race_data_eda.ipynb
├── README.md
├── security
│   ├── credentials.py
│   ├── __init__.py
│   ├── __pycache__
│   └── vault.py
└── training
    ├── callbacks.py
    ├── data_loader.py
    ├── evaluation.py
    ├── preprocessing.py
    └── trainer.py