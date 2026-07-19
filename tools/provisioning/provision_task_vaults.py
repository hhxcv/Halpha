"""Provision role-scoped WinVault values while impersonating task identities.

All secret transfer remains in one elevated maintenance process.  Values never
enter command arguments, environment variables, temporary files, XML, or JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
from typing import Iterable, Sequence

import keyring
from keyring.backends.Windows import WinVaultKeyring
import pywintypes
import win32con
import win32profile
import win32security

from halpha.configuration import HalphaSettings, WinVaultReference, load_settings
from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import require_win_vault_backend
from tools.provisioning.provision_windows_tasks import (
    APP_USER,
    EXECUTOR_USER,
    TASK_ACCOUNT_VAULT_SERVICE,
)


class TaskVaultProvisioningError(RuntimeError):
    """Sanitized task-vault provisioning failure."""


def _source_value(backend: WinVaultKeyring, reference: WinVaultReference) -> str:
    value = backend.get_password(reference.service, reference.account)
    if not value:
        raise TaskVaultProvisioningError(
            f"SOURCE_WINVAULT_REFERENCE_MISSING service={reference.service} account={reference.account}"
        )
    return value


def _write_as_task_identity(
    *,
    username: str,
    account_password: str,
    values: Iterable[tuple[WinVaultReference, str]],
    forbidden: Iterable[WinVaultReference],
    required_existing: Iterable[WinVaultReference] = (),
) -> int:
    try:
        token = win32security.LogonUser(
            username,
            ".",
            account_password,
            win32con.LOGON32_LOGON_BATCH,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
    except pywintypes.error as exc:
        raise TaskVaultProvisioningError(
            f"TASK_IDENTITY_LOGON_FAILED user={username} code={exc.winerror}"
        ) from None

    profile = None
    try:
        try:
            profile = win32profile.LoadUserProfile(token, {"UserName": username})
        except pywintypes.error as exc:
            raise TaskVaultProvisioningError(
                f"TASK_IDENTITY_PROFILE_LOAD_FAILED user={username} code={exc.winerror}"
            ) from None
        win32security.ImpersonateLoggedOnUser(token)
        try:
            backend = WinVaultKeyring()
            require_win_vault_backend(backend)
            material = tuple(values)
            for reference, value in material:
                backend.set_password(reference.service, reference.account, value)
            for reference, expected in material:
                if backend.get_password(reference.service, reference.account) != expected:
                    raise TaskVaultProvisioningError(
                        f"TASK_WINVAULT_WRITEBACK_MISMATCH user={username}"
                    )
            for reference in forbidden:
                if backend.get_password(reference.service, reference.account) is not None:
                    raise TaskVaultProvisioningError(
                        f"TASK_WINVAULT_FORBIDDEN_REFERENCE_VISIBLE user={username}"
                    )
            for reference in required_existing:
                if not backend.get_password(reference.service, reference.account):
                    raise TaskVaultProvisioningError(
                        f"TASK_WINVAULT_REQUIRED_REFERENCE_MISSING user={username}"
                    )
            return len(material)
        finally:
            win32security.RevertToSelf()
    finally:
        if profile is not None:
            win32profile.UnloadUserProfile(token, profile)
        token.Close()


def _task_password(backend: WinVaultKeyring, username: str) -> str:
    value = backend.get_password(TASK_ACCOUNT_VAULT_SERVICE, username)
    if not value:
        raise TaskVaultProvisioningError(
            f"TASK_ACCOUNT_PASSWORD_REFERENCE_MISSING user={username}"
        )
    return value


def _app_values(
    settings: HalphaSettings,
    source: WinVaultKeyring,
) -> tuple[tuple[WinVaultReference, str], ...]:
    app = settings.app
    maintenance_references = tuple(
        reference
        for target in (settings.maintenance.demo, settings.maintenance.live)
        for reference in (
            target.migration_credential_reference,
            target.backup_credential_reference,
        )
    )
    smtp_values = (
        (
            (
                app.smtp_credential_reference,
                _source_value(source, app.smtp_credential_reference),
            ),
        )
        if settings.email.delivery_enabled
        else ()
    )
    database_values = (
        (
            app.database_credential_reference,
            _source_value(source, app.database_credential_reference),
        ),
        *tuple(
            (reference, _source_value(source, reference))
            for reference in maintenance_references
        ),
        *smtp_values,
    )
    return (
        *database_values,
        (app.csrf_signing_reference, secrets.token_urlsafe(64)),
    )


def _executor_values(
    settings: HalphaSettings,
    source: WinVaultKeyring,
) -> tuple[tuple[WinVaultReference, str], ...]:
    executor = settings.executor
    references = [
        reference
        for reference in (
            executor.database_credential_reference,
            executor.binance_api_key_reference,
            executor.binance_api_secret_reference,
        )
        if reference is not None
    ]
    if executor.runtime_proxy_reference is not None:
        references.append(executor.runtime_proxy_reference)
    return tuple(
        (reference, _source_value(source, reference))
        for reference in references
    )


def provision_task_vaults(
    settings: HalphaSettings,
) -> dict[str, object]:
    source = keyring.get_keyring()
    require_win_vault_backend(source)
    app_password = _task_password(source, APP_USER)
    executor_password = _task_password(source, EXECUTOR_USER)
    app_values = _app_values(settings, source)
    executor_values = _executor_values(settings, source)
    app_forbidden = [
        reference
        for reference in (
            settings.executor.database_credential_reference,
            settings.executor.binance_api_key_reference,
            settings.executor.binance_api_secret_reference,
        )
        if reference is not None
    ]
    if settings.executor.runtime_proxy_reference is not None:
        app_forbidden.append(settings.executor.runtime_proxy_reference)
    executor_forbidden = (
        settings.app.database_credential_reference,
        settings.app.csrf_signing_reference,
        settings.app.smtp_credential_reference,
        settings.maintenance.demo.migration_credential_reference,
        settings.maintenance.demo.backup_credential_reference,
        settings.maintenance.live.migration_credential_reference,
        settings.maintenance.live.backup_credential_reference,
    )
    app_count = _write_as_task_identity(
        username=APP_USER,
        account_password=app_password,
        values=app_values,
        forbidden=tuple(app_forbidden),
    )
    executor_count = _write_as_task_identity(
        username=EXECUTOR_USER,
        account_password=executor_password,
        values=executor_values,
        forbidden=executor_forbidden,
    )
    return {
        "status": "TASK_WINVAULTS_PROVISIONED",
        "app_reference_count": app_count,
        "executor_reference_count": executor_count,
        "cross_role_visibility": "REJECTED",
        "secret_transport": "IN_PROCESS_IMPERSONATION_ONLY",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provision-task-vaults")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = args.repository_root.resolve()
        require_repository_runtime(root)
        settings = load_settings(args.config)
        report = provision_task_vaults(settings)
    except Exception as exc:
        if isinstance(exc, TaskVaultProvisioningError):
            reason = str(exc)
        else:
            reason = f"TASK_WINVAULT_PROVISIONING_FAILED type={type(exc).__name__}"
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
