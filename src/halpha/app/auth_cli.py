"""Offline local-owner credential provisioning."""

from __future__ import annotations

import argparse
from getpass import getpass
import json
from pathlib import Path
import secrets
from typing import Protocol, Sequence

import keyring
from pwdlib import PasswordHash

from halpha.configuration import ConfigurationError, app_settings, load_settings
from halpha.runtime_identity import RuntimeIdentityError, require_repository_runtime
from halpha.winvault import require_win_vault_backend


class WritableKeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...


class AuthProvisioningError(RuntimeError):
    """Sanitized offline provisioning failure."""


def _read_new_password() -> str:
    first = getpass("New local owner password: ")
    second = getpass("Repeat local owner password: ")
    if first != second:
        raise AuthProvisioningError("OWNER_PASSWORD_CONFIRMATION_MISMATCH")
    if not first or "\x00" in first or len(first) > 1024:
        raise AuthProvisioningError("OWNER_PASSWORD_INPUT_INVALID")
    return first


def set_owner_password(
    config_path: Path,
    *,
    backend: WritableKeyringBackend,
    password: str,
) -> dict[str, str]:
    require_win_vault_backend(backend)
    if not password or "\x00" in password or len(password) > 1024:
        raise AuthProvisioningError("OWNER_PASSWORD_INPUT_INVALID")
    settings = app_settings(load_settings(config_path))
    app = settings.app
    values = (
        (app.session_signing_reference, secrets.token_urlsafe(64)),
        (app.csrf_signing_reference, secrets.token_urlsafe(64)),
        (app.owner_password_hash_reference, PasswordHash.recommended().hash(password)),
    )
    try:
        for reference, value in values:
            backend.set_password(reference.service, reference.account, value)
        for reference, expected in values:
            if backend.get_password(reference.service, reference.account) != expected:
                raise AuthProvisioningError("WINVAULT_WRITEBACK_MISMATCH")
    except AuthProvisioningError:
        raise
    except Exception as exc:
        raise AuthProvisioningError(
            f"WINVAULT_WRITE_FAILED type={type(exc).__name__}"
        ) from None
    return {
        "status": "OWNER_WEB_SECRETS_PROVISIONED",
        "config": str(config_path.resolve()),
        "backend": "keyring.backends.Windows.WinVaultKeyring",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="halpha-auth")
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_password = subparsers.add_parser("set-password")
    set_password.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        require_repository_runtime()
        password = _read_new_password()
        report = set_owner_password(
            args.config,
            backend=keyring.get_keyring(),
            password=password,
        )
    except (AuthProvisioningError, ConfigurationError, RuntimeIdentityError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
