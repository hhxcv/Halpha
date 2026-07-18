from __future__ import annotations

import pytest

from halpha.configuration import (
    WinVaultReference,
    app_settings,
    executor_settings,
    load_settings,
    maintenance_settings,
)
from halpha.winvault import (
    SecretResolutionError,
    app_secret_resolver,
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
    return load_settings(root / "config" / "halpha.live-read-only.example.toml")


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
        resolver.resolve(settings.app.session_signing_reference)


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


def test_live_read_only_executor_resolver_omits_binance_credentials() -> None:
    settings = _live_read_only_settings()
    assert settings.executor.binance_api_key_reference is None
    assert settings.executor.binance_api_secret_reference is None
    resolver = executor_secret_resolver(
        FakeWinVaultKeyring(), executor_settings(settings)
    )
    absent_binance_reference = WinVaultReference(
        service="Halpha/Binance/BINANCE_LIVE_READ_ONLY",
        account="api_key",
    )
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(absent_binance_reference)


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


def test_maintenance_resolver_is_limited_to_database_maintenance_references() -> None:
    settings = _settings()
    reference = settings.maintenance.demo.backup_credential_reference
    backend = FakeWinVaultKeyring({(reference.service, reference.account): "backup-secret"})
    resolver = maintenance_secret_resolver(backend, maintenance_settings(settings))
    assert resolver.resolve(reference).get_secret_value() == "backup-secret"
    with pytest.raises(SecretResolutionError, match="OUTSIDE_PROCESS_BOUNDARY"):
        resolver.resolve(settings.app.session_signing_reference)
