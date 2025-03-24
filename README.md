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

## Refined Project Structure

```text
├──  .env
├──  .env.example
├──  .github/
│   └──  TODO.md
├──  .gitignore
├──  config/
│   ├──  config.py
│   ├──  inference.json
│   ├──  logging.json
│   ├──  model.json
│   └──  training.json
├──  data/
│   ├──  processed/
│   └──  raw/
│       ├──  circuits_202503231047.tsv
│       ├──  constructorresults_202503231048.tsv
│       ├──  constructors_202503231048.tsv
│       ├──  constructorstandings_202503231048.tsv
│       ├──  drivers_202503231048.tsv
│       ├──  driverstandings_202503231048.tsv
│       ├──  laptimes_202503231048.tsv
│       ├──  pitstops_202503231049.tsv
│       ├──  qualifying_202503231049.tsv
│       ├──  races_202503231049.tsv
│       ├──  results_202503231049.tsv
│       ├──  seasons_202503231050.tsv
│       ├──  sprintresults_202503231050.tsv
│       └──  status_202503231050.tsv
├──  db/
│   ├──  __init__.py
│   ├──  base.py
│   ├──  config.py
│   ├──  connection_pool.py
│   ├──  init_db.sql
│   ├──  migrations/
│   │   ├──  001_schema_and_core_tables.sql
│   │   └──  002_raw_data.sql
│   ├──  models/
│   │   ├──  __init__.py
│   │   ├──  model_metrics.py
│   │   ├──  training_data.py
│   │   └──  trianing_run.py
│   ├──  raw_data_base_ddls.sql
│   └──  repositiries/
│       ├──  __init__.py
│       ├──  base_repository.py
│       ├──  data_repository.py
│       └──  metrics_repository.py
├──  gonzo-pit-strategy/
│   ├──  __init__.py
│   ├──  cli/
│   │   ├──  __init__.py
│   │   ├──  predict.py
│   │   └──  train.py
│   ├──  constants.py
│   ├──  exceptions.py
│   ├──  log/
│   │   ├──  __init__.py
│   │   └──  logger.py
│   ├──  main.py
│   └──  utils/
│       ├──  __init__.py
│       └──  db_utils.py
├──  inference/
│   ├──  __init__.py
│   ├── 󰒍 api/
│   │   ├──  __init__.py
│   │   ├──  endpoints.py
│   │   ├──  models.py
│   │   └──  router.py
│   ├──  main.py
│   ├──  middleware/
│   │   ├──  __init__.py
│   │   └──  logging.py
│   └──  predictor.py
├──  LICENSE
├──  models/
│   ├──  __init__.py
│   ├──  layers/
│   │   ├──  __init__.py
│   │   └──  attention.py
│   ├──  model.py
│   └──  utils/
│       ├──  __init__.py
│       └──  model_io.py
├──  README.md
├──  security/
│   ├──  __init__.py
│   ├──  credentials.py
│   └──  vault.py
└──  training/
    ├──  __init__.py
    ├──  callbacks.py
    ├──  data_loader.py
    ├──  evaluation.py
    ├──  preprocessing.py
    └──  trainer.py