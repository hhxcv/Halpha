"""Serve the exact B01 build with a non-production browser-test login."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import keyring
from pydantic import SecretStr
from pwdlib import PasswordHash
import uvicorn

from halpha.app.projection import PostgreSQLWorkbenchProjection
from halpha.app.secrets import AppSecrets
from halpha.app.web import create_app
from halpha.configuration import load_settings
from halpha.winvault import require_win_vault_backend


# Public test fixture data, never a product credential or deployment default.
BROWSER_FIXTURE_PASSWORD = "B01-browser-fixture-only"


def main() -> int:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    reference = settings.app.database_credential_reference
    database_password = backend.get_password(reference.service, reference.account)
    if not database_password:
        raise RuntimeError("B01_BROWSER_FIXTURE_DATABASE_CREDENTIAL_MISSING")
    app = create_app(
        settings,
        AppSecrets(
            database_password=SecretStr(database_password),
            owner_password_hash=SecretStr(
                PasswordHash.recommended().hash(BROWSER_FIXTURE_PASSWORD)
            ),
            session_signing_secret=SecretStr("b01-browser-fixture-session-signing-only"),
            csrf_signing_secret=SecretStr("b01-browser-fixture-csrf-signing-only"),
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
