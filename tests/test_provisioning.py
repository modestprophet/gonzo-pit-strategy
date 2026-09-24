"""Tests for Provisioning.

Split the way the module is: the values (Load Plan, rendered SQL, goose argv,
step parsing) are asserted directly, and the three phases run against a real
Postgres, skipping when none is reachable — the same arrangement as
`test_run_ledger_contract.py`, and for the same reason. The interesting
failures here are ones only a real server has an opinion about: whether the
grants let the App Role write, whether a bad row aborts the transaction.

Nothing in this file mocks a subprocess. `goose` and `psql` have exactly one
implementation each, so a fake would only be able to confirm that we built the
argv we built.
"""

import os
import uuid

import pytest

from gonzo_pit_strategy.db.provisioning import (
    ALL_STEPS,
    LOAD_PLAN,
    DatabaseTarget,
    LoadReport,
    Provisioner,
    ProvisioningError,
    Role,
    Step,
    copy_statement,
    goose_command,
    goose_connection_string,
    parse_steps,
    quote_identifier,
    quote_literal,
    render_init_sql,
    resolve_load_plan,
)

TARGET = DatabaseTarget(host="db.example", port=6543, name="f1db", schema="f1db")
ADMIN = Role("postgres", "admin-pw")
APP = Role("gonzo_user", "app-pw")


# ---------------------------------------------------------------------------
# The Load Plan
# ---------------------------------------------------------------------------


def test_load_plan_is_in_foreign_key_order():
    """Not alphabetical, and not incidentally so.

    Each table here references one above it — `round_entries` needs `rounds`,
    `laps` need `session_entries`. Sorting this list would break the Load.
    """
    tables = [table for _, table in LOAD_PLAN]

    for parent, child in [
        ("seasons", "rounds"),
        ("circuits", "rounds"),
        ("rounds", "sessions"),
        ("rounds", "round_entries"),
        ("drivers", "team_drivers"),
        ("teams", "team_drivers"),
        ("round_entries", "session_entries"),
        ("session_entries", "laps"),
        ("session_entries", "pitstops"),
    ]:
        assert tables.index(parent) < tables.index(child), (
            f"{parent} must load before {child}"
        )


def test_load_plan_has_no_duplicate_targets():
    files = [f for f, _ in LOAD_PLAN]
    tables = [t for _, t in LOAD_PLAN]
    assert len(set(files)) == len(files)
    assert len(set(tables)) == len(tables)


def test_resolve_load_plan_requires_every_file(tmp_path):
    """A missing file fails the Load rather than being skipped: dbt's lineage
    needs all of them, so a partial load builds cleanly and is silently wrong."""
    for filename, _ in LOAD_PLAN[:-1]:
        (tmp_path / filename).write_text("header\n")

    with pytest.raises(ProvisioningError, match="Required file not found"):
        resolve_load_plan(tmp_path)


def test_resolve_load_plan_returns_plan_order(tmp_path):
    for filename, _ in LOAD_PLAN:
        (tmp_path / filename).write_text("header\n")

    resolved = resolve_load_plan(tmp_path)

    assert [table for _, table in resolved] == [table for _, table in LOAD_PLAN]


# ---------------------------------------------------------------------------
# Rendering and quoting
# ---------------------------------------------------------------------------


def test_quote_literal_escapes_apostrophes():
    """A password is interpolated into `CREATE USER ... PASSWORD <literal>`;
    an apostrophe in one used to produce a syntax error at best."""
    assert quote_literal("o'brien") == "'o''brien'"


def test_quote_identifier_escapes_double_quotes():
    assert quote_identifier('we"ird') == '"we""ird"'


def test_render_init_sql_quotes_a_hostile_password():
    template = "CREATE USER {{APP_USERNAME}} PASSWORD {{APP_PASSWORD_LITERAL}};"
    app = Role("gonzo_user", "pw'; DROP DATABASE f1db; --")

    rendered = render_init_sql(template, TARGET, app)

    assert rendered == (
        "CREATE USER \"gonzo_user\" "
        "PASSWORD 'pw''; DROP DATABASE f1db; --';"
    )


def test_render_init_sql_distinguishes_identifier_from_literal():
    """The App Role name appears as both, and they quote differently."""
    template = "{{APP_USERNAME}} {{APP_USERNAME_LITERAL}}"

    assert render_init_sql(template, TARGET, APP) == "\"gonzo_user\" 'gonzo_user'"


def test_render_init_sql_rejects_placeholders_it_does_not_know():
    """The template growing a placeholder the renderer has never heard of must
    fail here rather than reaching the server as literal `{{...}}`."""
    with pytest.raises(ProvisioningError, match="APP_EMAIL"):
        render_init_sql("{{DB_NAME}} and {{APP_EMAIL}}", TARGET, APP)


def test_real_template_renders_completely():
    """The shipped template and the renderer must not drift apart."""
    from gonzo_pit_strategy.db.provisioning import INIT_SQL_PATH

    rendered = render_init_sql(INIT_SQL_PATH.read_text(), TARGET, APP)

    assert "{{" not in rendered
    assert '"f1db"' in rendered
    assert "'app-pw'" in rendered


# ---------------------------------------------------------------------------
# goose
# ---------------------------------------------------------------------------


def test_goose_command_qualifies_the_version_table(tmp_path):
    """goose defaults to `goose_db_version` in the search path, which is not
    where this project's migration state lives."""
    command = goose_command(TARGET, ADMIN, migrations_dir=tmp_path)

    assert command[:3] == ["goose", "-table", "f1db.goose_db_version"]
    assert command[-1] == "up"


def test_goose_connection_string_encodes_credentials():
    role = Role("user@host", "p@ss:word/x")

    url = goose_connection_string(TARGET, role)

    assert url.startswith("postgres://user%40host:p%40ss%3Aword%2Fx@db.example:6543/")
    assert url.endswith("/f1db?sslmode=disable")


def test_copy_statement_quotes_schema_and_table():
    assert copy_statement(TARGET, "laps") == (
        'COPY "f1db"."laps" FROM STDIN '
        "WITH (FORMAT CSV, HEADER, DELIMITER ',', NULL '')"
    )


# ---------------------------------------------------------------------------
# Step parsing and ordering
# ---------------------------------------------------------------------------


def test_parse_steps_all():
    assert parse_steps("all") == list(ALL_STEPS)


def test_parse_steps_returns_execution_order_not_argument_order():
    """`load,init` requests both phases; it does not request loading first."""
    assert parse_steps("load,init") == [Step.INIT, Step.LOAD]


def test_parse_steps_rejects_unknown():
    with pytest.raises(ProvisioningError, match="Unknown step"):
        parse_steps("init,migrant")


def test_provision_requires_a_data_dir_for_load():
    provisioner = Provisioner(TARGET, admin=ADMIN, app=APP)

    with pytest.raises(ProvisioningError, match="requires a data directory"):
        provisioner.provision([Step.LOAD])


def test_provision_stops_at_the_first_failing_phase(tmp_path, monkeypatch):
    """A failed Init must not be followed by a Migrate against nothing."""
    provisioner = Provisioner(TARGET, admin=ADMIN, app=APP)
    calls = []

    def failing_init():
        calls.append("init")
        raise ProvisioningError("boom")

    monkeypatch.setattr(provisioner, "initialize", failing_init)
    monkeypatch.setattr(provisioner, "migrate", lambda: calls.append("migrate"))

    with pytest.raises(ProvisioningError, match="boom"):
        provisioner.provision([Step.INIT, Step.MIGRATE])

    assert calls == ["init"]


def test_role_repr_redacts_the_password():
    assert "hunter2" not in repr(Role("gonzo_user", "hunter2"))


def test_load_report_totals():
    assert LoadReport(rows={"laps": 3, "drivers": 4}).total == 7


# ---------------------------------------------------------------------------
# The phases, against a real Postgres
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def provisioned(tmp_path_factory):
    """Provision a throwaway database, yielding (provisioner, data_dir).

    Skips rather than fails when no server is reachable, so the core suite still
    needs neither a database nor a GPU. What is being tested here is exactly
    what a fake could not tell us: that the rendered SQL parses, that the grants
    let the App Role write, and that goose accepts the argv.
    """
    from sqlalchemy.engine import make_url

    url = os.environ.get("DEV_POSTGRES_URL")
    if not url:
        pytest.skip("DEV_POSTGRES_URL not set")

    pytest.importorskip("psycopg2")
    parsed = make_url(url)

    suffix = uuid.uuid4().hex[:10]
    target = DatabaseTarget(
        host=parsed.host,
        port=parsed.port or 5432,
        name=f"gonzo_prov_{suffix}",
        schema="f1db",
    )
    admin = Role(parsed.username, parsed.password)
    # An apostrophe and a double quote in the credentials, so every real run
    # exercises the quoting rather than leaving it to the unit tests alone.
    app = Role(f"gonzo_app_{suffix}", "pw'\"x")

    provisioner = Provisioner(target, admin=admin, app=app)

    try:
        provisioner.initialize()
    except ProvisioningError as exc:
        pytest.skip(f"scratch Postgres unusable: {exc}")

    data_dir = tmp_path_factory.mktemp("jolpica")
    # `COPY ... HEADER` skips the first line and matches columns by position,
    # so a header-only file is a valid zero-row load for any table. That gives
    # the real COPY path, the real FK order, and the real transaction without
    # depending on the 665k-row Jolpica extract being present.
    for filename, _ in LOAD_PLAN:
        (data_dir / filename).write_text("header\n")

    yield provisioner, data_dir

    _drop_database(url, target.name, app.username)


def _drop_database(admin_url: str, name: str, role: str) -> None:
    import psycopg2
    from sqlalchemy.engine import make_url

    parsed = make_url(admin_url)
    connection = psycopg2.connect(
        host=parsed.host,
        port=parsed.port or 5432,
        dbname=parsed.database,
        user=parsed.username,
        password=parsed.password,
    )
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS {quote_identifier(name)}')
            cursor.execute(f'DROP ROLE IF EXISTS {quote_identifier(role)}')
    finally:
        connection.close()


def test_initialize_creates_schema_and_app_role(provisioned):
    """The App Role must be able to connect and use the schema it was granted.

    A missing `GRANT CREATE ON DATABASE` is what once blocked dbt, and no
    amount of asserting on argv would have caught it.
    """
    provisioner, _ = provisioned

    connection = provisioner._connect_as_app()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (provisioner.target.schema,),
            )
            assert cursor.fetchone() is not None
            cursor.execute(
                "SELECT has_database_privilege(%s, %s, 'CREATE')",
                (provisioner.app.username, provisioner.target.name),
            )
            assert cursor.fetchone()[0] is True, "dbt needs CREATE on the database"
    finally:
        connection.close()


def test_initialize_is_idempotent(provisioned):
    """Re-running Init against an existing database must still apply grants
    rather than aborting on `CREATE DATABASE`."""
    provisioner, _ = provisioned

    provisioner.initialize()


def test_migrate_then_load_reports_rows_per_table(provisioned):
    provisioner, data_dir = provisioned

    provisioner.migrate()
    report = provisioner.load(data_dir)

    assert set(report.rows) == {table for _, table in LOAD_PLAN}
    assert report.total == 0, "header-only fixtures carry no data rows"


def test_provision_executes_reversed_duplicate_selection_once(provisioned):
    provisioner, data_dir = provisioned

    report = provisioner.provision(
        iter([Step.LOAD, Step.MIGRATE, Step.INIT, Step.LOAD, Step.INIT]),
        data_dir=data_dir,
    )

    assert report.steps_completed == [Step.INIT, Step.MIGRATE, Step.LOAD]
    assert report.load is not None
    assert set(report.load.rows) == {table for _, table in LOAD_PLAN}
    assert report.load.total == 0


def test_migrate_is_idempotent(provisioned):
    provisioner, _ = provisioned

    provisioner.migrate()


def test_a_bad_row_aborts_the_whole_load(provisioned, tmp_path):
    """The failure the previous implementation could not see.

    `psql` exits 0 on a failed `\\copy` unless `ON_ERROR_STOP=1` is set, so a
    broken load was reported as a success. In-process the copy raises, and the
    single transaction means the tables loaded before it roll back too.
    """
    provisioner, _ = provisioned
    provisioner.migrate()

    for filename, _ in LOAD_PLAN:
        (tmp_path / filename).write_text("header\n")
    # `seasons` loads early and takes an integer year; a row of prose does not
    # parse, so the copy fails part way through the plan.
    (tmp_path / "formula_one_season.csv").write_text(
        "header\nnot,an,integer,row\n"
    )

    with pytest.raises(ProvisioningError, match="Failed to load"):
        provisioner.load(tmp_path)

    connection = provisioner._connect_as_app()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) FROM {quote_identifier(provisioner.target.schema)}"
                '."seasons"'
            )
            assert cursor.fetchone()[0] == 0, "a failed Load leaves nothing behind"
    finally:
        connection.close()
