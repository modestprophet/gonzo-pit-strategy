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
