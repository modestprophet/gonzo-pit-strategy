# ADR 0001: Declarative Configuration and Secrets Injection

## Status
Accepted

## Context
The application's configuration and secret management had become fragmented and shallow. We had multiple overlapping concepts:
- A legacy configuration singleton (`config.py`).
- Parallel attempts at Pydantic settings (`unified.py`).
- A `Vault Settings Source` adapter split across multiple files.
- An imperative credentials fetcher (`security/credentials.py`) that bypassed the configuration tree entirely, hiding dependencies deep within the application logic.

This fragmentation caused significant friction. Understanding the **Environment** and **AppConfig** required bouncing between several modules. Testing was difficult because global singletons and late-binding secret fetches created hidden state and required extensive mocking.

## Decision
We will enforce a strict, top-down declarative configuration model using Dependency Injection:
1. **Single Source of Truth**: All configuration and secrets are represented strictly within the `AppConfig` Pydantic schema in `config/config.py`.
2. **Early Hydration**: The `Vault Settings Source` is integrated directly into the `AppConfig` hydration process. Secrets are resolved at application startup, not deferred until use.
3. **Environment-Driven Vault Paths**: Rather than hardcoding different Vault mount paths based on the `Environment` (e.g., `prod` vs `dev`), the application reads a `VAULT_MOUNT_POINT` environment variable, which the `Vault Settings Source` prepends to requested secret paths.
4. **No Global Singletons**: We explicitly reject global configuration instances (e.g., `app_config = AppConfig()`) and singletons like `ConnectionPool._instance`. The CLI or web application entry points are responsible for instantiating the configuration and injecting it (or its sub-components, like `DatabaseConfig`) down the stack.
5. **No Imperative Secrets**: The `security/credentials.py` module is deleted. Components that need secrets must declare them in their respective configuration schemas.

## Consequences

### Positive (Locality and Leverage)
- **Locality**: A developer only needs to look at `config/config.py` to see exactly what secrets and variables the application requires to run.
- **Testability (Leverage)**: Tests gain massive leverage. By injecting a dummy `AppConfig`, tests can completely bypass Vault and environment variable concerns without fragile `unittest.mock.patch` calls.
- **Fail Fast**: Missing secrets or malformed configuration will crash the application immediately at startup, rather than halfway through a database transaction or API call.

### Negative
- **Startup Latency**: The application must reach out to Vault during startup, adding slight latency before the first request or command can be handled.
- **Entry Point Overhead**: CLI commands and API endpoints carry the boilerplate of instantiating `AppConfig` and passing it to core components (like the database pool).

## Implementation Notes
- The database connection pool (`db/connection_pool.py`) must be instantiated explicitly by the entry point.
- The `db_session` context manager will rely on a module-level initialization function `init_db(config)` to wire up the pool for SQLAlchemy's global context manager pattern, keeping the initialization explicit while maintaining ergonomic session usage.
