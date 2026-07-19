from __future__ import annotations

from pathlib import Path

from halpha.configuration import load_settings
from tools.provisioning.provision_task_vaults import (
    _app_values,
    _executor_values,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "provisioning" / "provision_task_vaults.py"


class _MemorySource:
    def __init__(self, values: dict[tuple[str, str], str]) -> None:
        self.values = values

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))


def test_role_reference_sets_are_disjoint() -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    references = (
        settings.app.database_credential_reference,
        settings.maintenance.demo.migration_credential_reference,
        settings.maintenance.demo.backup_credential_reference,
        settings.maintenance.live.migration_credential_reference,
        settings.maintenance.live.backup_credential_reference,
        settings.executor.database_credential_reference,
        settings.executor.binance_api_key_reference,
        settings.executor.binance_api_secret_reference,
    )
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )
    app_refs = {reference for reference, _ in _app_values(settings, source)}
    executor_refs = {reference for reference, _ in _executor_values(settings, source)}
    assert not app_refs & executor_refs
    assert settings.app.csrf_signing_reference in app_refs
    assert settings.executor.binance_api_secret_reference in executor_refs


def test_app_values_include_database_and_fresh_csrf_references() -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    references = (
        settings.app.database_credential_reference,
        settings.maintenance.demo.migration_credential_reference,
        settings.maintenance.demo.backup_credential_reference,
        settings.maintenance.live.migration_credential_reference,
        settings.maintenance.live.backup_credential_reference,
    )
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )
    app_refs = {reference for reference, _ in _app_values(settings, source)}
    assert app_refs == {*references, settings.app.csrf_signing_reference}


def test_live_read_only_executor_values_omit_absent_binance_references() -> None:
    settings = load_settings(ROOT / "config" / "halpha.live-read-only.example.toml")
    proxy_reference = settings.executor.runtime_proxy_reference
    assert proxy_reference is not None
    references = (
        settings.executor.database_credential_reference,
        proxy_reference,
    )
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )

    executor_refs = tuple(
        reference for reference, _ in _executor_values(settings, source)
    )

    assert executor_refs == references
    assert settings.executor.binance_api_key_reference is None
    assert settings.executor.binance_api_secret_reference is None


def test_enabled_smtp_credential_is_projected_only_to_app_task_vault() -> None:
    base = load_settings(ROOT / "config" / "halpha.example.toml")
    email = base.email.model_dump(mode="json")
    email.update(
        {
            "delivery_enabled": True,
            "smtp_host": "smtp.example.invalid",
            "smtp_username": "owner@example.invalid",
            "sender": "owner@example.invalid",
            "owner_recipient": "owner@example.invalid",
        }
    )
    settings = load_settings(
        ROOT / "config" / "halpha.example.toml",
        constructor_values={"email": email},
    )
    references = (
        settings.app.database_credential_reference,
        settings.maintenance.demo.migration_credential_reference,
        settings.maintenance.demo.backup_credential_reference,
        settings.maintenance.live.migration_credential_reference,
        settings.maintenance.live.backup_credential_reference,
        settings.app.smtp_credential_reference,
    )
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )

    app_refs = {reference for reference, _ in _app_values(settings, source)}

    assert settings.app.smtp_credential_reference in app_refs


def test_task_vault_provisioner_has_no_external_secret_transport() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "subprocess" not in source
    assert "pgpassword" not in source
    assert "secret_transport\": \"in_process_impersonation_only" in source
    assert "getpass" not in source
    assert "owner_password" not in source
