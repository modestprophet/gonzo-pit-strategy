"""Command-line interface for Provisioning a database (`gonzo-load`).

This module builds a `DatabaseTarget` and two `Role`s from arguments, calls
`provision`, and prints the result. Provisioning owns phase selection,
credential requirements, the Load Plan, and failure handling.

Credentials arrive as arguments. LoadSettings resolves only logging.
"""

import argparse
import logging
import sys
from pathlib import Path

from gonzo_pit_strategy.config.config import LoadSettings, setup_logging
from gonzo_pit_strategy.db.provisioning import (
    DatabaseTarget,
    Provisioner,
    ProvisioningError,
    Role,
    parse_steps,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "raw"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gonzo-load",
        description="Provision the F1 database: create it, migrate it, load it",
    )
    parser.add_argument("--db-admin-username", help="Admin Role username")
    parser.add_argument("--db-admin-password", help="Admin Role password")
    parser.add_argument("--app-username", help="App Role username")
    parser.add_argument("--app-password", help="App Role password")
    parser.add_argument("--db-host", default="localhost", help="Database hostname")
    parser.add_argument("--db-port", type=int, default=5432, help="Database port")
    parser.add_argument("--db-name", default="f1db", help="Database name")
    parser.add_argument("--db-schema", default="f1db", help="Schema name")
    parser.add_argument(
        "--data-directory",
        help=f"Path to the Jolpica CSVs [default: {DEFAULT_DATA_DIR}]",
    )
    parser.add_argument(
        "--steps",
        default="all",
        help="Comma-separated phases to run (init,migrate,load) [default: all]",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    setup_logging(LoadSettings().logging)

    provisioner = Provisioner(
        DatabaseTarget(
            host=args.db_host,
            port=args.db_port,
            name=args.db_name,
            schema=args.db_schema,
        ),
        admin=Role(args.db_admin_username or "", args.db_admin_password or ""),
        app=Role(args.app_username or "", args.app_password or ""),
    )

    data_dir = Path(args.data_directory) if args.data_directory else DEFAULT_DATA_DIR

    try:
        steps = parse_steps(args.steps)
        report = provisioner.provision(steps, data_dir=data_dir)
    except ProvisioningError as exc:
        logger.error(str(exc))
        sys.exit(1)

    if report.load is not None:
        print("\n--- Rows loaded ---")
        for table, count in report.load.rows.items():
            print(f"{table:<28} {count:>9,}")
        print(f"{'total':<28} {report.load.total:>9,}")

    logger.info(
        "Provisioning complete: %s",
        ", ".join(step.value for step in report.steps_completed),
    )


if __name__ == "__main__":
    main()
