from __future__ import annotations

import pytest

from halpha.configuration import (
    WinVaultReference,
    app_settings,
    backup_settings,
    executor_settings,
    load_settings,
    maintenance_settings,
)
from halpha.winvault import (
    SecretResolutionError,
    app_secret_resolver,
    backup_secret_resolver,
    executor_secret_resolver,
    maintenance_secret_resolver,
    require_win_vault_backend,
)


class FakeWinVaultKeyring:
    __module__ = "keyring.backends.Windows"
    __qualname__ = "WinVaultKeyring"

    def __init__(self, values: dict[tuple[str, str], str] | None = None) -> None:
        self.values = values or {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))


def _settings():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    return load_settings(root / "config" / "halpha.example.toml")


def _live_read_only_settings():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    return load_settings(root / "config" / "halpha.live-copy-read-only.example.toml")


def _live_write_settings():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    return load_settings(root / "config" / "halpha.live-copy-write.example.toml")


def test_rejects_non_windows_vault_backend() -> None:
    with pytest.raises(SecretResolutionError, match="WINVAULT_BACKEND_REQUIRED"):
        require_win_vault_backend(object())


def test_executor_can_resolve_only_executor_reference() -> None:
    settings = _settings()
    reference = settings.executor.binance_api_key_reference
    secret = "do-not-render"
    backend = FakeWinVaultKeyring({(reference.service, reference.account): secret})
    resolver = executor_secret_resolver(backend, executor_settings(settings))
    material = resolver.resolve(reference)
    assert str(material) == "**********"
    assert repr(material) == "SecretStr('**********')"
    assert material.get_secret_value() == secret

    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.app.csrf_signing_reference)


def test_executor_can_resolve_configured_runtime_proxy_reference() -> None:
    settings = _settings()
    executor = settings.executor.model_dump(mode="json")
    executor["runtime_proxy_reference"] = {
        "service": "Halpha/Network/BINANCE_DEMO",
        "account": "runtime_proxy",
    }
    from halpha.configuration import load_settings
    from pathlib import Path

    configured = load_settings(
        Path(__file__).resolve().parents[2] / "config" / "halpha.example.toml",
        constructor_values={"executor": executor},
    )
    reference = configured.executor.runtime_proxy_reference
    assert reference is not None
    resolver = executor_secret_resolver(
        FakeWinVaultKeyring({(reference.service, reference.account): "loopback-proxy"}),
        executor_settings(configured),
    )
    assert resolver.resolve(reference).get_secret_value() == "loopback-proxy"


def test_live_read_only_executor_resolver_includes_account_observation_credentials() -> None:
    settings = _live_read_only_settings()
    references = (
        settings.executor.database_credential_reference,
        settings.executor.binance_api_key_reference,
        settings.executor.binance_api_secret_reference,
        settings.executor.runtime_proxy_reference,
    )
    assert all(reference is not None for reference in references)
    backend = FakeWinVaultKeyring(
        {
            (reference.service, reference.account): "not-a-real-secret"
            for reference in references
            if reference is not None
        }
    )
    resolver = executor_secret_resolver(
        backend, executor_settings(settings)
    )
    for reference in references:
        assert reference is not None
        assert resolver.resolve(reference).get_secret_value() == "not-a-real-secret"

    peer_binance_reference = WinVaultReference(
        service="Halpha/Binance/BINANCE_LIVE_PERSONAL",
        account="api_key",
    )
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(peer_binance_reference)
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.app.database_credential_reference)


def test_live_public_forward_executor_resolver_omits_private_credentials() -> None:
    configured = _live_read_only_settings()
    executor = configured.executor.model_dump(mode="json")
    executor["binance_api_key_reference"] = None
    executor["binance_api_secret_reference"] = None
    from pathlib import Path

    from halpha.configuration import load_settings

    settings = load_settings(
        Path(__file__).resolve().parents[2]
        / "config"
        / "halpha.live-copy-read-only.example.toml",
        constructor_values={"executor": executor},
    )
    resolver = executor_secret_resolver(
        FakeWinVaultKeyring(), executor_settings(settings)
    )
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.executor.database_credential_reference)


@pytest.mark.parametrize(
    ("settings_loader", "peer_namespace"),
    (
        (_settings, "BINANCE_LIVE"),
        (_live_write_settings, "BINANCE_DEMO"),
    ),
)
def test_executor_resolver_rejects_peer_environment_product_references(
    settings_loader,
    peer_namespace: str,
) -> None:
    settings = settings_loader()
    peer_references = (
        WinVaultReference(
            service=f"Halpha/PostgreSQL/{peer_namespace}/Executor",
            account="scram_password",
        ),
        WinVaultReference(
            service=f"Halpha/Binance/{peer_namespace}",
            account="api_key",
        ),
    )
    backend = FakeWinVaultKeyring(
        {
            (reference.service, reference.account): "peer-secret"
            for reference in peer_references
        }
    )
    resolver = executor_secret_resolver(backend, executor_settings(settings))

    for reference in peer_references:
        with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
            resolver.resolve(reference)


def test_executor_resolver_rejects_profile_mismatched_configured_reference() -> None:
    settings = _settings()
    role_settings = executor_settings(settings)
    mismatched_executor = role_settings.executor.model_copy(
        update={
            "database_credential_reference": WinVaultReference(
                service="Halpha/PostgreSQL/BINANCE_LIVE/Executor",
                account="scram_password",
            )
        }
    )
    mismatched_settings = role_settings.model_copy(
        update={"executor": mismatched_executor}
    )

    with pytest.raises(
        SecretResolutionError,
        match="EXECUTOR_SECRET_REFERENCE_PROFILE_MISMATCH",
    ):
        executor_secret_resolver(FakeWinVaultKeyring(), mismatched_settings)


def test_app_cannot_resolve_binance_reference() -> None:
    settings = _settings()
    resolver = app_secret_resolver(FakeWinVaultKeyring(), app_settings(settings))
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.executor.binance_api_secret_reference)


def test_missing_secret_and_backend_exception_are_sanitized() -> None:
    settings = _settings()
    reference = settings.executor.database_credential_reference
    resolver = executor_secret_resolver(FakeWinVaultKeyring(), executor_settings(settings))
    with pytest.raises(SecretResolutionError, match="MISSING_OR_EMPTY"):
        resolver.resolve(reference)

    leaked = "must-not-appear"

    class BrokenWinVaultKeyring(FakeWinVaultKeyring):
        __module__ = "keyring.backends.Windows"
        __qualname__ = "WinVaultKeyring"

        def get_password(self, service: str, username: str) -> str | None:
            raise RuntimeError(leaked)

    broken = executor_secret_resolver(BrokenWinVaultKeyring(), executor_settings(settings))
    with pytest.raises(SecretResolutionError) as captured:
        broken.resolve(reference)
    assert "WINVAULT_READ_FAILED" in str(captured.value)
    assert leaked not in str(captured.value)


def test_unlisted_reference_is_rejected_before_backend_access() -> None:
    settings = _settings()
    resolver = executor_secret_resolver(FakeWinVaultKeyring(), executor_settings(settings))
    unknown = WinVaultReference(service="Halpha/Unknown", account="unknown")
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(unknown)


def test_maintenance_resolver_is_limited_to_migration_references() -> None:
    settings = _settings()
    reference = settings.maintenance.demo.migration_credential_reference
    backend = FakeWinVaultKeyring(
        {(reference.service, reference.account): "migration-secret"}
    )
    resolver = maintenance_secret_resolver(backend, maintenance_settings(settings))
    assert resolver.resolve(reference).get_secret_value() == "migration-secret"
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.maintenance.demo.backup_credential_reference)
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.app.csrf_signing_reference)


def test_backup_resolver_is_limited_to_backup_references() -> None:
    settings = _settings()
    reference = settings.maintenance.live_copy.backup_credential_reference
    backend = FakeWinVaultKeyring(
        {(reference.service, reference.account): "backup-secret"}
    )
    resolver = backup_secret_resolver(backend, backup_settings(settings))
    assert resolver.resolve(reference).get_secret_value() == "backup-secret"
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.maintenance.live_copy.migration_credential_reference)
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.app.database_credential_reference)
