"""Provisioning: an empty Postgres server to a migrated, loaded `f1db`.

This module owns the three phases behind `gonzo-load` — Init, Migrate, Load —
and lives beside the `migrations/` and `init_db.sql` it drives.

Provisioning produces the raw `f1db.*` tables and stops there. dbt turns those
into the training dataset (ADR 0003); the Experiment trains on that. Nothing
here knows about models.

The split inside is by *kind*, not by adapter:

* **Values** — `render_init_sql`, `goose_command`, `copy_statement`, `LOAD_PLAN`.
  Pure, and asserted directly. There is exactly one way to invoke `goose`, so a
  runner interface here would be a seam with one adapter — a fake invented so a
  test has something to assert against, which is testing past the interface.
* **Effects** — `Provisioner`'s three phases. Tested against a real Postgres by
  `tests/test_provisioning.py`, which skips when none is reachable, exactly as
  the Run Ledger contract suite does.

Credentials are arguments rather than `AppConfig` because this runs *before* the
application has a database to connect to. The two roles are not
interchangeable and which phase needs which is part of the interface: Init
needs both, Migrate needs the Admin Role, Load needs the App Role.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

logger = logging.getLogger(__name__)

MODULE_DIR = Path(__file__).resolve().parent
MIGRATIONS_DIR = MODULE_DIR / "migrations"
INIT_SQL_PATH = MODULE_DIR / "init_db.sql"


class ProvisioningError(RuntimeError):
    """A phase could not complete.

    Phases raise rather than returning a boolean: a `False` return says only
    that something went wrong, leaving every caller to re-decide what it meant,
    and the previous implementation logged each failure once here and again at
    the call site.
    """


# ---------------------------------------------------------------------------
# The Load Plan
# ---------------------------------------------------------------------------

#: Jolpica CSV files and their target tables, in **foreign-key order**.
#:
#: The order is the reason the Load phase works at all — `round_entries`
#: references `rounds`, `laps` reference `session_entries`, and so on — so this
#: is domain knowledge, not configuration, and it is not sorted alphabetically.
#: Every entry is required: dbt's lineage needs all of them, and a partial load
#: builds cleanly while being silently wrong.
LOAD_PLAN: Tuple[Tuple[str, str], ...] = (
    ("formula_one_baseteam.csv", "base_teams"),
    ("formula_one_championshipsystem.csv", "championship_systems"),
    ("formula_one_pointsystem.csv", "point_systems"),
    ("formula_one_season.csv", "seasons"),
    ("formula_one_circuit.csv", "circuits"),
    ("formula_one_driver.csv", "drivers"),
    ("formula_one_team.csv", "teams"),
    ("formula_one_teamdriver.csv", "team_drivers"),
    ("formula_one_round.csv", "rounds"),
    ("formula_one_session.csv", "sessions"),
    ("formula_one_roundentry.csv", "round_entries"),
    ("formula_one_sessionentry.csv", "session_entries"),
    ("formula_one_lap.csv", "laps"),
    ("formula_one_pitstop.csv", "pitstops"),
    ("formula_one_penalty.csv", "penalties"),
    ("formula_one_championshipadjustment.csv", "championship_adjustments"),
    ("formula_one_driverchampionship.csv", "driver_championships"),
    ("formula_one_teamchampionship.csv", "team_championships"),
)


class Step(str, Enum):
    """One phase of Provisioning."""

    INIT = "init"
    MIGRATE = "migrate"
    LOAD = "load"


#: The phases in the only order they can run in.
ALL_STEPS: Tuple[Step, ...] = (Step.INIT, Step.MIGRATE, Step.LOAD)
_REQUIRED_ROLES = {
    Step.INIT: ("admin", "app"),
    Step.MIGRATE: ("admin",),
    Step.LOAD: ("app",),
}


def _normalize_steps(steps: Iterable[Step | str]) -> list[Step]:
    requested: set[Step] = set()
    for value in steps:
        try:
            requested.add(Step(value))
        except ValueError as exc:
            raise ProvisioningError(
                f"Unknown step: {value!r}. "
                f"Valid steps: {', '.join(step.value for step in ALL_STEPS)}"
            ) from exc
    if not requested:
        raise ProvisioningError("No steps requested")
    return [step for step in ALL_STEPS if step in requested]


def parse_steps(raw: str) -> List[Step]:
    """Parse a comma-separated `--steps` value, `all` included.

    Always returns the requested phases in execution order: `load,init` is a
    request for both phases, not a request to load before the schema exists.
    Empty selections and unknown names fail, including unknown names beside `all`.
    """
    names = [part.strip().lower() for part in raw.split(",") if part.strip()]
    requested: list[Step | str] = []
    for name in names:
        requested.extend(ALL_STEPS if name == "all" else [name])
    return _normalize_steps(requested)


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseTarget:
    """Where a Provisioning run points. Carries no credentials."""

    host: str = "localhost"
    port: int = 5432
    name: str = "f1db"
    schema: str = "f1db"


@dataclass(frozen=True)
class Role:
    """One credential set. See Admin Role / App Role in CONTEXT.md."""

    username: str
    password: str

    def __repr__(self) -> str:  # keep the password out of tracebacks and logs
        return f"Role(username={self.username!r}, password=<redacted>)"


@dataclass(frozen=True)
class LoadReport:
    """Rows actually written per table.

    Row counts are the verification that means something: `psql` exits 0 on a
    failed `\\copy` unless `ON_ERROR_STOP=1` is set, so a silent zero-row load
    once reported success. Loading in-process makes that failure raise, and this
    makes the result checkable without a follow-up query.
    """

    rows: Mapping[str, int]

    @property
    def total(self) -> int:
        return sum(self.rows.values())


@dataclass
class ProvisionReport:
    """What a Provisioning run did."""

    steps_completed: List[Step] = field(default_factory=list)
    load: Optional[LoadReport] = None


def quote_identifier(name: str) -> str:
    """Quote a SQL identifier. Table, schema, database, and role names."""
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Quote a SQL string literal.

    Passwords reach `CREATE USER ... ENCRYPTED PASSWORD` as literal text, so
    this is the one place that has to get quoting right; an apostrophe in a
    password previously produced a syntax error at best.
    """
    return "'" + value.replace("'", "''") + "'"


def render_init_sql(template: str, target: DatabaseTarget, app: Role) -> str:
    """Fill `init_db.sql` in for a target and its App Role.

    Names appear in the template both as identifiers and, inside the `pg_roles`
    lookup, as string literals — different quoting, hence separate placeholders.
    """
    substitutions = {
        "{{DB_NAME}}": quote_identifier(target.name),
        "{{DB_SCHEMA}}": quote_identifier(target.schema),
        "{{APP_USERNAME}}": quote_identifier(app.username),
        "{{APP_USERNAME_LITERAL}}": quote_literal(app.username),
        "{{APP_PASSWORD_LITERAL}}": quote_literal(app.password),
    }
    rendered = template
    for placeholder, value in substitutions.items():
        rendered = rendered.replace(placeholder, value)

    # Catches the template growing a placeholder this function does not know
    # about, which would otherwise reach the server as literal `{{...}}`.
    leftover = re.findall(r"\{\{[^}]*\}\}", rendered)
    if leftover:
        raise ProvisioningError(
            f"Unsubstituted placeholders in init SQL: {sorted(set(leftover))}"
        )
    return rendered


def goose_connection_string(target: DatabaseTarget, role: Role) -> str:
    """Connection string for goose. Credentials are URL-encoded."""
    return (
        f"postgres://{quote(role.username, safe='')}:{quote(role.password, safe='')}"
        f"@{target.host}:{target.port}/{target.name}?sslmode=disable"
    )


def goose_command(
    target: DatabaseTarget,
    admin: Role,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    direction: str = "up",
) -> List[str]:
    """The `goose` argv for a target.

    The version table is schema-qualified: goose defaults to `goose_db_version`
    in the search path, which is not where this project's migration state lives.
    """
    return [
        "goose",
        "-table",
        f"{target.schema}.goose_db_version",
        "-dir",
        str(migrations_dir),
        "postgres",
        goose_connection_string(target, admin),
        direction,
    ]


def copy_statement(target: DatabaseTarget, table: str) -> str:
    """The `COPY ... FROM STDIN` statement for one table of the Load Plan."""
    return (
        f"COPY {quote_identifier(target.schema)}.{quote_identifier(table)} "
        "FROM STDIN WITH (FORMAT CSV, HEADER, DELIMITER ',', NULL '')"
    )


def resolve_load_plan(
    data_dir: Path, plan: Sequence[Tuple[str, str]] = LOAD_PLAN
) -> List[Tuple[Path, str]]:
    """Resolve the Load Plan against a directory, in plan order.

    Every file is required. A missing one raises rather than being skipped:
    dbt's lineage needs all of them, so a partial load produces a dataset that
    builds and is silently wrong.
    """
    resolved = []
    for filename, table in plan:
        path = data_dir / filename
        if not path.exists():
            raise ProvisioningError(
                f"Required file not found: {path} (target table {table}). "
                "The Load Plan has no optional entries."
            )
        resolved.append((path, table))
    return resolved


# ---------------------------------------------------------------------------
# Effects
# ---------------------------------------------------------------------------


class Provisioner:
    """Takes a Postgres server from empty to a migrated, loaded database."""

    def __init__(
        self,
        target: DatabaseTarget,
        *,
        admin: Role,
        app: Role,
        migrations_dir: Path = MIGRATIONS_DIR,
        init_sql_path: Path = INIT_SQL_PATH,
    ):
        self.target = target
        self.admin = admin
        self.app = app
        self.migrations_dir = Path(migrations_dir)
        self.init_sql_path = Path(init_sql_path)

    # -- orchestration ----------------------------------------------------

    def provision(
        self, steps: Iterable[Step], *, data_dir: Optional[Path] = None
    ) -> ProvisionReport:
        """Validate selection and credentials, then run each phase once in order.

        File checks stay within each phase. The first failure stops the run.
        """
        steps = _normalize_steps(steps)
        self._require_credentials(steps)
        if Step.LOAD in steps and data_dir is None:
            raise ProvisioningError("The Load phase requires a data directory")

        report = ProvisionReport()
        for step in steps:
            if step is Step.INIT:
                self.initialize()
            elif step is Step.MIGRATE:
                self.migrate()
            elif step is Step.LOAD:
                assert data_dir is not None
                report.load = self.load(data_dir)
            report.steps_completed.append(step)
        return report

    # -- phases -----------------------------------------------------------

    def initialize(self) -> None:
        """Create the database, the schema, and the App Role.

        Re-running this against an existing database is expected and must still
        apply the grants, so `psql` runs *without* `ON_ERROR_STOP`: a
        `CREATE DATABASE` that fails because the database is already there is
        tolerated, and the statements after it still apply.
        """
        self._require_credentials([Step.INIT])
        logger.info("Step 1/3: initializing database %s", self.target.name)

        if not self.init_sql_path.exists():
            raise ProvisioningError(f"SQL init file not found: {self.init_sql_path}")

        sql = render_init_sql(
            self.init_sql_path.read_text(), self.target, self.app
        )
        result = self._run_psql_script(sql, role=self.admin, database="postgres")

        if result.returncode != 0:
            if "already exists" in result.stderr:
                logger.warning(
                    "Database or role already exists; continuing: %s",
                    result.stderr.strip().splitlines()[0],
                )
            else:
                raise ProvisioningError(
                    f"Database initialization failed: {result.stderr.strip()}"
                )

        logger.info("Database initialization successful")

    def migrate(self) -> None:
        """Apply goose migrations using the Admin Role."""
        self._require_credentials([Step.MIGRATE])
        logger.info("Step 2/3: applying migrations from %s", self.migrations_dir)

        if not self.migrations_dir.exists():
            raise ProvisioningError(
                f"Migrations directory not found: {self.migrations_dir}"
            )

        command = goose_command(
            self.target, self.admin, migrations_dir=self.migrations_dir
        )
        try:
            # check=False: the returncode is inspected below so the failure
            # surfaces as ProvisioningError carrying goose's stderr, rather than
            # as a CalledProcessError that says only that a command exited 1.
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
        except FileNotFoundError as exc:
            raise ProvisioningError(
                "goose not found on PATH; install it with "
                "`go install github.com/pressly/goose/v3/cmd/goose@latest`"
            ) from exc

        if result.returncode != 0:
            raise ProvisioningError(f"Migration failed: {result.stderr.strip()}")

        logger.info("Migrations successful")

    def load(self, data_dir: Path) -> LoadReport:
        """Load the Load Plan using the App Role, in one transaction.

        `COPY FROM STDIN` in-process rather than `psql \\copy`: a failed copy
        raises here, where the previous implementation depended on remembering
        `ON_ERROR_STOP=1` to stop `psql` exiting 0 on failure. One transaction
        wraps the whole plan, so a failure part way through leaves the database
        as it was rather than partially loaded.
        """
        self._require_credentials([Step.LOAD])
        logger.info("Step 3/3: loading data from %s", data_dir)

        files = resolve_load_plan(Path(data_dir))
        rows: Dict[str, int] = {}

        connection = self._connect_as_app()
        try:
            with connection.cursor() as cursor:
                for path, table in files:
                    logger.info(
                        "Loading %s into %s.%s...",
                        path.name,
                        self.target.schema,
                        table,
                    )
                    with path.open("r", encoding="utf-8", newline="") as handle:
                        try:
                            cursor.copy_expert(
                                copy_statement(self.target, table), handle
                            )
                        except Exception as exc:
                            raise ProvisioningError(
                                f"Failed to load {path.name} into "
                                f"{self.target.schema}.{table}: {exc}"
                            ) from exc
                    rows[table] = cursor.rowcount
                    logger.info("Loaded %s rows into %s", cursor.rowcount, table)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        report = LoadReport(rows=rows)
        logger.info(
            "Data loading complete: %s rows across %s tables",
            report.total,
            len(report.rows),
        )
        return report

    # -- internals --------------------------------------------------------

    def _require_credentials(self, steps: Iterable[Step]) -> None:
        required = {name for step in steps for name in _REQUIRED_ROLES[step]}
        missing = []
        for name, role in (("admin", self.admin), ("app", self.app)):
            if name not in required:
                continue
            for credential, value in (
                ("username", role.username), ("password", role.password)
            ):
                if not value:
                    missing.append(f"{name.title()} Role {credential}")
        if missing:
            raise ProvisioningError(f"Missing required credentials: {', '.join(missing)}")

    def _connect_as_app(self):
        """Connect as the App Role. Imported here so the pure helpers in this
        module stay importable without psycopg2 present."""
        import psycopg2

        try:
            return psycopg2.connect(
                host=self.target.host,
                port=self.target.port,
                dbname=self.target.name,
                user=self.app.username,
                password=self.app.password,
            )
        except Exception as exc:
            raise ProvisioningError(
                f"Could not connect to {self.target.name} as "
                f"{self.app.username}: {exc}"
            ) from exc

    def _run_psql_script(
        self, sql: str, *, role: Role, database: str
    ) -> subprocess.CompletedProcess:
        """Run a SQL script through `psql`.

        Init keeps `psql` because `init_db.sql` uses the `\\c` meta-command to
        reconnect to the database it just created; that is a client feature, not
        a server one.
        """
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sql", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(sql)
            script_path = Path(tmp.name)

        try:
            command = [
                "psql",
                "-h",
                self.target.host,
                "-p",
                str(self.target.port),
                "-U",
                role.username,
                "-d",
                database,
                "-f",
                str(script_path),
            ]
            env = os.environ.copy()
            env["PGPASSWORD"] = role.password
            try:
                # check=False is load-bearing here: `initialize` tolerates a
                # non-zero exit whose stderr says "already exists", which is how
                # a re-run still applies the grants.
                return subprocess.run(
                    command, env=env, capture_output=True, text=True, check=False
                )
            except FileNotFoundError as exc:
                raise ProvisioningError("psql not found on PATH") from exc
        finally:
            script_path.unlink(missing_ok=True)
