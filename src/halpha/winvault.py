"""Role-scoped access to secret material held by Windows Credential Manager."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import SecretStr

from halpha.configuration import (
    AppSettingsView,
    ExecutorSettingsView,
    MaintenanceSettingsView,
    WinVaultReference,
)


EXPECTED_BACKEND = "keyring.backends.Windows.WinVaultKeyring"


class SecretResolutionError(RuntimeError):
    """A sanitized, fail-closed secret resolution error."""


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...


def backend_identity(backend: object) -> str:
    backend_type = type(backend)
    return f"{backend_type.__module__}.{backend_type.__qualname__}"


def require_win_vault_backend(backend: object) -> None:
    actual = backend_identity(backend)
    if actual != EXPECTED_BACKEND:
        raise SecretResolutionError(
            f"WINVAULT_BACKEND_REQUIRED expected={EXPECTED_BACKEND} actual={actual}"
        )


class WinVaultSecretResolver:
    """Resolve only references explicitly assigned to one process role."""

    def __init__(
        self,
        backend: KeyringBackend,
        allowed_references: Iterable[WinVaultReference],
    ) -> None:
        require_win_vault_backend(backend)
        self._backend = backend
        self._allowed = frozenset(allowed_references)

    def resolve(self, reference: WinVaultReference) -> SecretStr:
        if reference not in self._allowed:
            raise SecretResolutionError("SECRET_REFERENCE_OUTSIDE_PROCESS_BOUNDARY")
        try:
            value = self._backend.get_password(reference.service, reference.account)
        except Exception as exc:
            raise SecretResolutionError(
                f"WINVAULT_READ_FAILED type={type(exc).__name__}"
            ) from None
        if not value:
            raise SecretResolutionError("WINVAULT_SECRET_MISSING_OR_EMPTY")
        return SecretStr(value)


def app_secret_resolver(
    backend: KeyringBackend,
    settings: AppSettingsView,
) -> WinVaultSecretResolver:
    app = settings.app
    return WinVaultSecretResolver(
        backend,
        (
            app.database_credential_reference,
            app.csrf_signing_reference,
            app.smtp_credential_reference,
        ),
    )


def executor_secret_resolver(
    backend: KeyringBackend,
    settings: ExecutorSettingsView,
) -> WinVaultSecretResolver:
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
    return WinVaultSecretResolver(backend, references)


def maintenance_secret_resolver(
    backend: KeyringBackend,
    settings: MaintenanceSettingsView,
) -> WinVaultSecretResolver:
    maintenance = settings.maintenance
    return WinVaultSecretResolver(
        backend,
        tuple(
            reference
            for target in (maintenance.demo, maintenance.live)
            for reference in (
                target.backup_credential_reference,
                target.migration_credential_reference,
            )
        ),
    )
