"""Serve a deterministic B02 `/operations` fixture without venue credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import keyring
from pydantic import SecretStr
from pwdlib import PasswordHash
import uvicorn

from halpha.app.projection import PostgreSQLWorkbenchProjection
from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.configuration import load_settings
from halpha.planning.service import PlanningApplicationService
from halpha.winvault import require_win_vault_backend
from tools.qualification.verify_b02_database_boundary import (
    _cleanup,
    _connect,
    _create_and_activate,
    _insert_limit,
)


BROWSER_FIXTURE_PASSWORD = "B02-browser-fixture-only"
FIXTURE_ENVIRONMENT_ID = "b02-browser-fixture"
FIXTURE_ACCOUNT_ID = "b02-browser-account"


def main() -> int:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    settings = settings.model_copy(
        update={
            "release": settings.release.model_copy(
                update={
                    "environment_id": FIXTURE_ENVIRONMENT_ID,
                    "account_id": FIXTURE_ACCOUNT_ID,
                }
            )
        }
    )
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    reference = settings.app.database_credential_reference
    database_password = backend.get_password(reference.service, reference.account)
    if not database_password:
        raise RuntimeError("B02_BROWSER_FIXTURE_DATABASE_CREDENTIAL_MISSING")

    connection = _connect()
    now = datetime.now(UTC)
    limit_id = str(uuid4())
    try:
        with connection.transaction():
            _cleanup(connection, FIXTURE_ENVIRONMENT_ID)
            _insert_limit(
                connection,
                environment_id=FIXTURE_ENVIRONMENT_ID,
                account_ref=FIXTURE_ACCOUNT_ID,
                limit_id=limit_id,
                now=now,
            )
            _create_and_activate(
                connection,
                environment_id=FIXTURE_ENVIRONMENT_ID,
                account_ref=FIXTURE_ACCOUNT_ID,
                limit_id=limit_id,
                now=now,
                instrument_ref="BTCUSDT-PERP",
                limits=("100", "500", "50"),
            )
            _create_and_activate(
                connection,
                environment_id=FIXTURE_ENVIRONMENT_ID,
                account_ref=FIXTURE_ACCOUNT_ID,
                limit_id=limit_id,
                now=now,
                instrument_ref="ETHUSDT-PERP",
                limits=("80", "400", "40"),
            )
            PlanningApplicationService(
                connection, FIXTURE_ENVIRONMENT_ID
            ).pause_for_writer_continuity_loss(now)

        app = create_app(
            settings,
            AppSecrets(
                database_password=SecretStr(database_password),
                owner_password_hash=SecretStr(
                    PasswordHash.recommended().hash(BROWSER_FIXTURE_PASSWORD)
                ),
                session_signing_secret=SecretStr(
                    "b02-browser-fixture-session-signing-only"
                ),
                csrf_signing_secret=SecretStr("b02-browser-fixture-csrf-signing-only"),
            ),
            repo_root=ROOT,
            projection=PostgreSQLWorkbenchProjection(
                settings.release.database_name,
                SecretStr(database_password),
                settings.release.environment_id,
            ),
            static_dist=ROOT / "frontend" / "dist",
        )
        uvicorn.run(
            app,
            host=settings.app.bind,
            port=settings.app.port,
            workers=1,
            reload=False,
            proxy_headers=False,
            server_header=False,
            log_level="warning",
        )
    finally:
        database_password = None
        try:
            with connection.transaction():
                _cleanup(connection, FIXTURE_ENVIRONMENT_ID)
        finally:
            connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
