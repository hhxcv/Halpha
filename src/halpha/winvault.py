"""Role-scoped access to secret material held by Windows Credential Manager."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from pydantic import SecretStr

from halpha.configuration import (
    AppSettingsView,
    BackupSettingsView,
    ExecutorSettingsView,
    MaintenanceSettingsView,
    WinVaultReference,
)
from halpha.windows_deployment import ALL_WINDOWS_DEPLOYMENTS


EXPECTED_BACKEND = "keyring.backends.Windows.WinVaultKeyring"



def _executor_product_references(
    namespace: str,
) -> tuple[WinVaultReference, ...]:
    return (
        WinVaultReference(
            service=f"Halpha/PostgreSQL/{namespace}/Executor",
            account="scram_password",
        ),
        WinVaultReference(
            service=f"Halpha/Binance/{namespace}",
            account="api_key",
        ),
        WinVaultReference(
            service=f"Halpha/Binance/{namespace}",
            account="api_secret",
        ),
    )


def _app_product_references(namespace: str) -> tuple[WinVaultReference, ...]:
    database_roles = ("App",) if namespace == "BINANCE_DEMO" else ("App", "AppReader")
    return (
        *(
            WinVaultReference(
                service=f"Halpha/PostgreSQL/{namespace}/{role}",
                account="scram_password",
            )
            for role in database_roles
        ),
        WinVaultReference(
            service=f"Halpha/Web/{namespace}",
            account="csrf_signing",
        ),
        WinVaultReference(
            service=f"Halpha/SMTP/{namespace}",
            account="password",
        ),
    )


_EXECUTOR_PRODUCT_REFERENCES_BY_CONTEXT: dict[
    tuple[str, str], tuple[WinVaultReference, ...]
] = {
    ("USDM_DEMO", "BINANCE_DEMO"): _executor_product_references("BINANCE_DEMO"),
    ("USDM_COPY_LEAD", "BINANCE_LIVE_READ_ONLY"): _executor_product_references(
        "BINANCE_LIVE_COPY"
    ),
    ("USDM_COPY_LEAD", "BINANCE_LIVE_WRITE"): _executor_product_references(
        "BINANCE_LIVE_COPY"
    ),
    ("USDM_PERSONAL", "BINANCE_LIVE_READ_ONLY"): _executor_product_references(
        "BINANCE_LIVE_PERSONAL"
    ),
    ("USDM_PERSONAL", "BINANCE_LIVE_WRITE"): _executor_product_references(
        "BINANCE_LIVE_PERSONAL"
    ),
}
_EXECUTOR_PROXY_SERVICE_BY_CONTEXT = {
    ("USDM_DEMO", "BINANCE_DEMO"): "Halpha/Network/BINANCE_DEMO",
    (
        "USDM_COPY_LEAD",
        "BINANCE_LIVE_READ_ONLY",
    ): "Halpha/Network/BINANCE_LIVE_COPY_READ_ONLY",
    (
        "USDM_COPY_LEAD",
        "BINANCE_LIVE_WRITE",
    ): "Halpha/Network/BINANCE_LIVE_COPY",
    (
        "USDM_PERSONAL",
        "BINANCE_LIVE_READ_ONLY",
    ): "Halpha/Network/BINANCE_LIVE_PERSONAL_READ_ONLY",
    (
        "USDM_PERSONAL",
        "BINANCE_LIVE_WRITE",
    ): "Halpha/Network/BINANCE_LIVE_PERSONAL",
}
_KNOWN_EXECUTOR_SECRET_REFERENCES = (
    *tuple(
        reference
        for references in _EXECUTOR_PRODUCT_REFERENCES_BY_CONTEXT.values()
        for reference in references
    ),
    *tuple(
        WinVaultReference(service=service, account=account)
        for service in _EXECUTOR_PROXY_SERVICE_BY_CONTEXT.values()
        for account in ("proxy_url", "runtime_proxy")
    ),
)


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
    return WinVaultSecretResolver(
        backend,
        app_secret_references(settings),
    )


def app_secret_references(
    settings: AppSettingsView,
) -> tuple[WinVaultReference, ...]:
    app = settings.app
    return (
        app.database_credential_reference,
        app.csrf_signing_reference,
        app.smtp_credential_reference,
    )


def app_peer_secret_references(
    settings: AppSettingsView,
) -> tuple[WinVaultReference, ...]:
    """Return every known App-role reference outside this exact projection."""

    allowed = frozenset(app_secret_references(settings))
    known = tuple(
        reference
        for deployment in ALL_WINDOWS_DEPLOYMENTS
        for reference in _app_product_references(deployment.namespace)
    )
    return tuple(reference for reference in known if reference not in allowed)


def executor_secret_resolver(
    backend: KeyringBackend,
    settings: ExecutorSettingsView,
) -> WinVaultSecretResolver:
    return WinVaultSecretResolver(
        backend,
        executor_secret_references(settings),
    )


def executor_secret_references(
    settings: ExecutorSettingsView,
) -> tuple[WinVaultReference, ...]:
    """Return the exact secret projection permitted for this executor profile."""

    executor = settings.executor
    profile = settings.release.profile
    account_type = settings.release.venue_account_type.value
    context = (account_type, profile)
    references: list[WinVaultReference] = []
    key_reference = executor.binance_api_key_reference
    secret_reference = executor.binance_api_secret_reference
    private_product_access = (
        profile != "BINANCE_LIVE_READ_ONLY"
        or key_reference is not None
        or secret_reference is not None
    )
    if private_product_access:
        if key_reference is None or secret_reference is None:
            raise SecretResolutionError(
                "EXECUTOR_PROFILE_SECRET_REFERENCES_INCOMPLETE"
            )
        configured_product_references = (
            executor.database_credential_reference,
            key_reference,
            secret_reference,
        )
        expected_product_references = _EXECUTOR_PRODUCT_REFERENCES_BY_CONTEXT[context]
        if configured_product_references != expected_product_references:
            raise SecretResolutionError(
                "EXECUTOR_SECRET_REFERENCE_PROFILE_MISMATCH"
            )
        references.extend(configured_product_references)
    proxy_reference = executor.runtime_proxy_reference
    if proxy_reference is not None:
        expected_proxy_service = _EXECUTOR_PROXY_SERVICE_BY_CONTEXT[context]
        if (
            proxy_reference.service != expected_proxy_service
            or proxy_reference.account not in {"proxy_url", "runtime_proxy"}
        ):
            raise SecretResolutionError(
                "EXECUTOR_PROXY_REFERENCE_PROFILE_MISMATCH"
            )
        references.append(proxy_reference)
    return tuple(references)


def executor_forbidden_secret_references(
    settings: ExecutorSettingsView,
) -> tuple[WinVaultReference, ...]:
    """Return known executor references outside the current profile projection."""

    allowed = frozenset(executor_secret_references(settings))
    return tuple(
        reference
        for reference in _KNOWN_EXECUTOR_SECRET_REFERENCES
        if reference not in allowed
    )


def maintenance_secret_resolver(
    backend: KeyringBackend,
    settings: MaintenanceSettingsView,
) -> WinVaultSecretResolver:
    maintenance = settings.maintenance
    return WinVaultSecretResolver(
        backend,
        tuple(
            reference
            for _name, target in maintenance.named_targets()
            for reference in (target.migration_credential_reference,)
        ),
    )


def backup_secret_resolver(
    backend: KeyringBackend,
    settings: BackupSettingsView,
) -> WinVaultSecretResolver:
    maintenance = settings.maintenance
    return WinVaultSecretResolver(
        backend,
        tuple(
            target.backup_credential_reference
            for _name, target in maintenance.named_targets()
        ),
    )
