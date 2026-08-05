"""Provision role-scoped WinVault values while impersonating task identities.

All secret transfer remains in one elevated maintenance process.  Values never
enter command arguments, environment variables, temporary files, XML, or JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
from typing import Any, Iterable, Protocol, Sequence

import keyring
from keyring.backends.Windows import WinVaultKeyring
import pywintypes
import win32com.client
import win32con
import win32profile
import win32security

from halpha.configuration import (
    HalphaSettings,
    WinVaultReference,
    app_settings,
    executor_settings,
    known_live_credential_references,
    load_settings,
)
from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import (
    app_peer_secret_references,
    app_secret_references,
    executor_forbidden_secret_references,
    executor_secret_references,
    require_win_vault_backend,
)
from halpha.windows_deployment import (
    SHARED_BACKUP_USER,
    windows_deployment,
)
from tools.provisioning.provision_windows_tasks import (
    TASK_ACCOUNT_VAULT_SERVICE,
    ProvisioningError,
    _account_sid,
    _current_user_sid,
    _require_live_task_reprojection_stopped,
    _require_configured_identity_sids,
)
from halpha.windows_runtime import (
    WindowsRuntimeError,
    acquire_executor_maintenance_mutex,
)


class TaskVaultProvisioningError(RuntimeError):
    """Sanitized task-vault provisioning failure."""


def _unload_task_identity_profile(
    token: Any,
    profile: Any,
    *,
    username: str,
) -> None:
    try:
        win32profile.UnloadUserProfile(token, profile)
    except pywintypes.error as exc:
        # Credential Manager can race the profile service after the final
        # credential operation. ERROR_INVALID_HANDLE means the exact handle
        # returned by LoadUserProfile is already gone, so there is no remaining
        # handle for this process to unload. Every other cleanup failure remains
        # fail-closed and is reported without exposing credential material.
        if exc.winerror == 6:
            return
        raise TaskVaultProvisioningError(
            f"TASK_IDENTITY_PROFILE_UNLOAD_FAILED user={username} "
            f"code={exc.winerror}"
        ) from None


def _require_task_identity_binding(settings: HalphaSettings) -> None:
    deployment = windows_deployment(settings.release.venue_account_type.value)
    try:
        _require_configured_identity_sids(
            configured={
                "app": settings.windows.app_task_sid,
                "executor": settings.windows.executor_task_sid,
                "backup": settings.windows.backup_task_sid,
                "maintenance": settings.windows.maintenance_sid,
            },
            actual={
                "app": _account_sid(deployment.app_user),
                "executor": _account_sid(deployment.executor_user),
                "backup": _account_sid(SHARED_BACKUP_USER),
                "maintenance": _current_user_sid(),
            },
        )
    except ProvisioningError as exc:
        raise TaskVaultProvisioningError(str(exc)) from None


class _WritableKeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def _delete_password_if_present(
    backend: _WritableKeyringBackend,
    reference: WinVaultReference,
    *,
    username: str,
) -> bool:
    try:
        present = backend.get_password(reference.service, reference.account) is not None
        if not present:
            return False
        backend.delete_password(reference.service, reference.account)
        if backend.get_password(reference.service, reference.account) is not None:
            raise TaskVaultProvisioningError(
                f"TASK_WINVAULT_DELETE_WRITEBACK_MISMATCH user={username}"
            )
    except TaskVaultProvisioningError:
        raise
    except Exception as exc:
        raise TaskVaultProvisioningError(
            f"TASK_WINVAULT_DELETE_FAILED user={username} "
            f"type={type(exc).__name__}"
        ) from None
    return True


def _source_value(backend: WinVaultKeyring, reference: WinVaultReference) -> str:
    value = backend.get_password(reference.service, reference.account)
    if not value:
        raise TaskVaultProvisioningError(
            f"SOURCE_WINVAULT_REFERENCE_MISSING service={reference.service} account={reference.account}"
        )
    return value


def _write_backend_values(
    *,
    backend: _WritableKeyringBackend,
    username: str,
    values: Iterable[tuple[WinVaultReference, str]],
    forbidden: Iterable[WinVaultReference],
    required_existing: Iterable[WinVaultReference] = (),
    delete_to_allowlist: Iterable[WinVaultReference] = (),
) -> int:
    material = tuple(values)
    forbidden_references = tuple(forbidden)
    required_references = tuple(required_existing)
    material_references = {reference for reference, _ in material}
    allowed_references = material_references | set(required_references)
    convergence_references = tuple(dict.fromkeys(delete_to_allowlist))
    convergence_set = set(convergence_references)
    if material_references & set(forbidden_references):
        raise TaskVaultProvisioningError(
            f"TASK_WINVAULT_PROJECTION_CONFLICT user={username}"
        )
    if convergence_references and not allowed_references <= convergence_set:
        raise TaskVaultProvisioningError(
            f"TASK_WINVAULT_ALLOWLIST_OUTSIDE_KNOWN_UNIVERSE user={username}"
        )
    for reference in convergence_references:
        if reference not in allowed_references:
            _delete_password_if_present(
                backend,
                reference,
                username=username,
            )
    for reference in forbidden_references:
        if backend.get_password(reference.service, reference.account) is not None:
            raise TaskVaultProvisioningError(
                f"TASK_WINVAULT_FORBIDDEN_REFERENCE_VISIBLE user={username}"
            )
    for reference in required_references:
        if not backend.get_password(reference.service, reference.account):
            raise TaskVaultProvisioningError(
                f"TASK_WINVAULT_REQUIRED_REFERENCE_MISSING user={username}"
            )
    for reference, value in material:
        backend.set_password(reference.service, reference.account, value)
    for reference, expected in material:
        if backend.get_password(reference.service, reference.account) != expected:
            raise TaskVaultProvisioningError(
                f"TASK_WINVAULT_WRITEBACK_MISMATCH user={username}"
            )
    return len(material)


def _write_as_task_identity(
    *,
    username: str,
    account_password: str,
    values: Iterable[tuple[WinVaultReference, str]],
    forbidden: Iterable[WinVaultReference],
    required_existing: Iterable[WinVaultReference] = (),
    delete_to_allowlist: Iterable[WinVaultReference] = (),
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
            return _write_backend_values(
                backend=backend,
                username=username,
                values=values,
                forbidden=forbidden,
                required_existing=required_existing,
                delete_to_allowlist=delete_to_allowlist,
            )
        finally:
            win32security.RevertToSelf()
    finally:
        try:
            if profile is not None:
                _unload_task_identity_profile(
                    token,
                    profile,
                    username=username,
                )
        finally:
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
    app_secret_values = (
        (
            app.database_credential_reference,
            _source_value(source, app.database_credential_reference),
        ),
        *smtp_values,
    )
    return (
        *app_secret_values,
        (app.csrf_signing_reference, secrets.token_urlsafe(64)),
    )


def _backup_values(
    settings: HalphaSettings,
    source: WinVaultKeyring,
) -> tuple[tuple[WinVaultReference, str], ...]:
    references = tuple(
        target.backup_credential_reference
        for _name, target in settings.maintenance.named_targets()
    )
    return tuple(
        (reference, _source_value(source, reference))
        for reference in references
    )


def _executor_values(
    settings: HalphaSettings,
    source: WinVaultKeyring,
) -> tuple[tuple[WinVaultReference, str], ...]:
    references = executor_secret_references(executor_settings(settings))
    return tuple(
        (reference, _source_value(source, reference))
        for reference in references
    )


def _ordered_references(
    *groups: Iterable[WinVaultReference],
) -> tuple[WinVaultReference, ...]:
    return tuple(dict.fromkeys(reference for group in groups for reference in group))


def _provision_task_vaults_under_guard(
    settings: HalphaSettings,
) -> dict[str, object]:
    deployment = windows_deployment(settings.release.venue_account_type.value)
    source = keyring.get_keyring()
    require_win_vault_backend(source)
    app_password = _task_password(source, deployment.app_user)
    executor_password = _task_password(source, deployment.executor_user)
    backup_password = (
        _task_password(source, SHARED_BACKUP_USER)
        if deployment.owns_shared_backup
        else None
    )
    app_values = _app_values(settings, source)
    executor_values = _executor_values(settings, source)
    maintenance_references = tuple(
        reference
        for _name, target in settings.maintenance.named_targets()
        for reference in (
            target.migration_credential_reference,
            target.backup_credential_reference,
        )
    )
    role_settings = executor_settings(settings)
    app_role_settings = app_settings(settings)
    peer_app_references = app_peer_secret_references(app_role_settings)
    known_executor_references = {
        *executor_secret_references(role_settings),
        *executor_forbidden_secret_references(role_settings),
    }
    known_app_references = {
        *app_secret_references(app_role_settings),
        *peer_app_references,
    }
    live_projection = settings.release.profile in {
        "BINANCE_LIVE_READ_ONLY",
        "BINANCE_LIVE_WRITE",
    }
    known_live_universe = known_live_credential_references()
    live_convergence_universe = known_live_universe if live_projection else ()
    app_allowed = {reference for reference, _value in app_values}
    executor_allowed = {reference for reference, _value in executor_values}
    backup_allowed = {
        target.backup_credential_reference
        for _name, target in settings.maintenance.named_targets()
    }
    app_forbidden = _ordered_references(
        peer_app_references,
        known_executor_references,
        maintenance_references,
        (
            reference
            for reference in known_live_universe
            if reference not in app_allowed
        ),
    )
    executor_forbidden = _ordered_references(
        known_app_references,
        maintenance_references,
        executor_forbidden_secret_references(role_settings),
        (
            reference
            for reference in known_live_universe
            if reference not in executor_allowed
        ),
    )
    backup_forbidden = _ordered_references(
        known_app_references,
        known_executor_references,
        (
            reference
            for reference in known_live_universe
            if reference not in backup_allowed
        ),
        (
            target.migration_credential_reference
            for _name, target in settings.maintenance.named_targets()
        ),
    )
    app_count = _write_as_task_identity(
        username=deployment.app_user,
        account_password=app_password,
        values=app_values,
        forbidden=app_forbidden,
        delete_to_allowlist=live_convergence_universe,
    )
    executor_count = _write_as_task_identity(
        username=deployment.executor_user,
        account_password=executor_password,
        values=executor_values,
        forbidden=executor_forbidden,
        delete_to_allowlist=live_convergence_universe,
    )
    backup_count = 0
    if backup_password is not None:
        backup_count = _write_as_task_identity(
            username=SHARED_BACKUP_USER,
            account_password=backup_password,
            values=_backup_values(settings, source),
            forbidden=backup_forbidden,
        )
    return {
        "status": "TASK_WINVAULTS_PROVISIONED",
        "environment_namespace": deployment.namespace,
        "app_reference_count": app_count,
        "executor_reference_count": executor_count,
        "backup_reference_count": backup_count,
        "shared_backup_provisioned": deployment.owns_shared_backup,
        "cross_role_visibility": "REJECTED",
        "secret_transport": "IN_PROCESS_IMPERSONATION_ONLY",
    }


def provision_task_vaults(
    settings: HalphaSettings,
    *,
    repository_root: Path | None = None,
    config_path: Path | None = None,
    task_service: Any | None = None,
) -> dict[str, object]:
    live_projection = settings.release.profile in {
        "BINANCE_LIVE_READ_ONLY",
        "BINANCE_LIVE_WRITE",
    }
    if not live_projection:
        _require_task_identity_binding(settings)
        return _provision_task_vaults_under_guard(settings)
    if repository_root is None or config_path is None or task_service is None:
        raise TaskVaultProvisioningError(
            "LIVE_TASK_WINVAULT_REPROJECTION_INVENTORY_REQUIRED"
        )
    try:
        with acquire_executor_maintenance_mutex(
            name=settings.executor.mutex_name,
            executor_task_sid=settings.windows.executor_task_sid,
            maintenance_sid=settings.windows.maintenance_sid,
            conflict_code="LIVE_TASK_WINVAULT_REPROJECTION_EXECUTOR_MUST_BE_STOPPED",
        ):
            _require_live_task_reprojection_stopped(
                repository_root=repository_root.resolve(),
                config_path=config_path.resolve(),
                settings=settings,
                task_service=task_service,
            )
            _require_task_identity_binding(settings)
            _require_live_task_reprojection_stopped(
                repository_root=repository_root.resolve(),
                config_path=config_path.resolve(),
                settings=settings,
                task_service=task_service,
            )
            return _provision_task_vaults_under_guard(settings)
    except (ProvisioningError, WindowsRuntimeError) as exc:
        raise TaskVaultProvisioningError(str(exc)) from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provision-task-vaults")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = args.repository_root.resolve()
        require_repository_runtime(root)
        config = args.config.resolve()
        settings = load_settings(config)
        task_service = None
        if settings.release.profile in {
            "BINANCE_LIVE_READ_ONLY",
            "BINANCE_LIVE_WRITE",
        }:
            task_service = win32com.client.Dispatch("Schedule.Service")
            task_service.Connect()
        report = provision_task_vaults(
            settings,
            repository_root=root,
            config_path=config,
            task_service=task_service,
        )
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
