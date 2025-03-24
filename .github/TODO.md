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
# .github/workflows/db-setup.yml
name: Database Setup

on:
  workflow_dispatch:
  
jobs:
  setup-database:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install psycopg2-binary
      - name: Install Goose Migration Tool
        run: |
          wget -O goose.tar.gz https://github.com/pressly/goose/releases/download/v3.5.0/goose_linux_x86_64.tar.gz
          tar -xzf goose.tar.gz
          sudo mv goose /usr/local/bin/
      - name: Set up database
        run: |
          python db_setup.py \
            --db-admin-username ${{ secrets.DB_ADMIN_USERNAME }} \
            --db-admin-password ${{ secrets.DB_ADMIN_PASSWORD }} \
            --app-username ${{ secrets.DB_APP_USERNAME }} \
            --app-password ${{ secrets.DB_APP_PASSWORD }} \
            --db-host localhost \
            --db-port 5432 \
            --db-name f1db
```