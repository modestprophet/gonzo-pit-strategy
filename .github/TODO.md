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


```
jobs:
  migrate-db:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Install PostgreSQL Client
        run: sudo apt-get install -y postgresql-client

      - name: Create Database and Schema
        env:
          PGPASSWORD: ${{ secrets.DB_SUPERUSER_PASSWORD }}
        run: |
          psql -h ${{ secrets.DB_HOST }} -U ${{ secrets.DB_SUPERUSER }} -d postgres -f init_db.sql

      - name: Run Goose Migrations
        env:
          PGPASSWORD: ${{ secrets.DBAPPPASS }}
        run: |
          goose -table=f1db.goose_db_version postgres "postgres://${{ secrets.DBAPPUSER }}:${{ secrets.DBAPPPASS }}@${{ secrets.DB_HOST }}:5432/f1db?sslmode=disable" up

```