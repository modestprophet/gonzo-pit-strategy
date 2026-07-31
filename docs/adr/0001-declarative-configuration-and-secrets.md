# ADR 0001: Declarative Configuration and Secrets Injection

## Status
Accepted; amended and fully landed 2026-07-29.

The original decisions stand. The amendment corrects three claims that the code
never actually satisfied and removes an implementation note that contradicted
Decision 4. See *Amendments* at the end.

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
- **Startup Latency**: When Vault is configured, the application reaches out to it during startup, adding slight latency before the first request or command can be handled.
- **Entry Point Overhead**: CLI commands and API endpoints carry the boilerplate of instantiating `AppConfig` and passing it to core components (like the database pool).

## Implementation Notes
- The database connection pool (`db/connection_pool.py`) must be instantiated explicitly by the entry point.
- `db_session(pool)` takes the pool as an explicit argument. There is deliberately no module-level `init_db(config)`: a module global wired once at import is the very pattern Decision 4 rejects, and passing the pool costs one argument at the two call sites that need it.

## Amendments (2026-07-29)

The decisions above were only partly implemented. Three corrections:

1. **Decision 1 was violated by the config module itself.** `VAULT_ADDR`,
   `VAULT_ROLE_ID`, `VAULT_SECRET_ID`, and `VAULT_MOUNT_POINT` were read
   straight from `os.environ`, and `Multipass` read them again in its
   constructor — so Vault's own configuration sat outside the tree it was
   meant to populate. Vault settings are now a `VaultConfig` submodel at
   `AppConfig.vault`, and `Multipass(url, role_id, secret_id)` takes injected
   credentials. Nothing under `config/` or `security/` reads `os.environ`.

2. **`DatabaseConfig` defaulted from `os.environ` at import time**, e.g.
   `host: str = Field(default=os.environ.get("DB_HOST", "localhost"))`. Because
   `AppConfig` sets `env_nested_delimiter="__"`, pydantic populates `db.host`
   from `DB__HOST`; a bare `DB_HOST` matched no field and was dropped by
   `extra="ignore"`. The import-time defaults were therefore the *only* path by
   which `DB_HOST` had any effect, and since nothing calls `load_dotenv` and
   pydantic's dotenv source does not write to `os.environ`, the `DB_*` entries
   in `.env` were silently ignored entirely — the application connected to the
   fallback `localhost:5432/gonzo` regardless of what `.env` said. Defaults are
   now plain literals and the settings sources are the single mechanism. The
   convention is `DB__HOST`, `LOGGING__LEVEL`, `VAULT__ADDR`; `tests/test_config.py`
   pins it, including a test asserting single-underscore names do *not* work.

3. **"Fail Fast" overstated the behaviour.** Vault is optional by design: when
   `addr`/`role_id`/`secret_id` are absent the settings source disables itself,
   and a fetch failure logs a warning and falls through to the field default.
   Malformed *configuration* still fails immediately via pydantic validation,
   but missing *secrets* degrade rather than crash. Treat the local default
   credentials as development-only.

Also completed as originally specified: `security/credentials.py` and
`config/unified.py` (which carried the rejected `app_config = AppConfig()`
global) are deleted, along with the duplicate `config/vault_source.py`.
