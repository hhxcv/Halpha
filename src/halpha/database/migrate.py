"""Run Alembic without putting a database secret in config, argv, or environment."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from alembic import command
from alembic.config import Config
import keyring
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

from halpha.runtime_identity import repository_root, require_repository_runtime
from halpha.winvault import require_win_vault_backend


DATABASES = {
    "halpha_demo": {
        "username": "halpha_demo_migration",
        "service": "Halpha/PostgreSQL/BINANCE_DEMO/Migration",
        "account": "scram_password",
    },
    "halpha_live": {
        "username": "halpha_live_migration",
        "service": "Halpha/PostgreSQL/BINANCE_LIVE/Migration",
        "account": "scram_password",
    },
}


def _alembic_config(root: Path, connection: object) -> Config:
    config = Config(str(root / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m halpha.database.migrate")
    parser.add_argument("database", choices=sorted(DATABASES))
    parser.add_argument("operation", choices=("upgrade", "downgrade", "current"))
    parser.add_argument("target", nargs="?", default="head")
    args = parser.parse_args(argv)

    require_repository_runtime()
    require_win_vault_backend(keyring.get_keyring())
    selected = DATABASES[args.database]
    secret = keyring.get_password(selected["service"], selected["account"])
    if not secret:
        raise RuntimeError("MIGRATION_CREDENTIAL_REFERENCE_MISSING")

    url = URL.create(
        "postgresql+psycopg",
        username=selected["username"],
        password=secret,
        host="127.0.0.1",
        port=5432,
        database=args.database,
    )
    engine = create_engine(url, poolclass=NullPool, echo=False)
    try:
        with engine.connect() as connection:
            config = _alembic_config(repository_root(), connection)
            if args.operation == "upgrade":
                command.upgrade(config, args.target)
            elif args.operation == "downgrade":
                command.downgrade(config, args.target)
            else:
                command.current(config, verbose=True)
    finally:
        secret = None
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
