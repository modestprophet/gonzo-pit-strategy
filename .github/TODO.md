### CI/CD stuff
TODO:  Implement CI/CD github actions once ready

```
.github/workflows/
├── ci.yml                      # Testing and validation
└── deploy.yml                  # Deployment to Google Cloud

scripts/
├── setup_db.py                 # Initialize PostgreSQL schema
├── deploy_gcp.sh               # GCP deployment script
└── run_migrations.py           # Run Goose migrations
```