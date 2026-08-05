from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest

from halpha.configuration import (
    WinVaultReference,
    app_settings,
    executor_settings,
    known_live_credential_references,
    load_settings,
)
from halpha.winvault import (
    app_peer_secret_references,
    executor_forbidden_secret_references,
    executor_secret_references,
)
from halpha.windows_deployment import (
    SHARED_BACKUP_USER,
    windows_deployment,
)
from tools.provisioning import provision_task_vaults as vaults
from tools.provisioning.provision_task_vaults import (
    TaskVaultProvisioningError,
    _app_values,
    _backup_values,
    _delete_password_if_present,
    _executor_values,
    _unload_task_identity_profile,
    _write_backend_values,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "provisioning" / "provision_task_vaults.py"
DEMO_CONFIG = ROOT / "config" / "halpha.example.toml"
LIVE_READ_ONLY_CONFIG = ROOT / "config" / "halpha.live-copy-read-only.example.toml"
LIVE_WRITE_CONFIG = ROOT / "config" / "halpha.live-copy-write.example.toml"


class _MemorySource:
    def __init__(self, values: dict[tuple[str, str], str]) -> None:
        self.values = values

    def get_password(self, service: str, account: str) -> str | None:
        return self.values.get((service, account))


class _MemoryBackend(_MemorySource):
    def __init__(self) -> None:
        super().__init__({})
        self.writes: list[tuple[str, str]] = []
        self.deletions: list[tuple[str, str]] = []

    def set_password(self, service: str, account: str, password: str) -> None:
        self.writes.append((service, account))
        self.values[(service, account)] = password

    def delete_password(self, service: str, account: str) -> None:
        self.deletions.append((service, account))
        self.values.pop((service, account), None)


class _MissingDeleteMustNotBeCalled(_MemoryBackend):
    def delete_password(self, service: str, account: str) -> None:
        raise AssertionError("delete_password must not be called for a missing reference")


def test_profile_unload_accepts_only_already_invalid_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vaults.win32profile,
        "UnloadUserProfile",
        lambda _token, _profile: (_ for _ in ()).throw(
            vaults.pywintypes.error(6, "UnloadUserProfile", "invalid handle")
        ),
    )

    _unload_task_identity_profile(
        object(),
        object(),
        username="HalphaBackup",
    )


def test_profile_unload_sanitizes_and_rejects_other_cleanup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        vaults.win32profile,
        "UnloadUserProfile",
        lambda _token, _profile: (_ for _ in ()).throw(
            vaults.pywintypes.error(5, "UnloadUserProfile", "access denied")
        ),
    )

    with pytest.raises(
        TaskVaultProvisioningError,
        match=(
            "TASK_IDENTITY_PROFILE_UNLOAD_FAILED "
            "user=HalphaBackup code=5"
        ),
    ):
        _unload_task_identity_profile(
            object(),
            object(),
            username="HalphaBackup",
        )


def test_role_reference_sets_are_disjoint() -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    references = (
        settings.app.database_credential_reference,
        *(
            target.backup_credential_reference
            for _name, target in settings.maintenance.named_targets()
        ),
        settings.executor.database_credential_reference,
        settings.executor.binance_api_key_reference,
        settings.executor.binance_api_secret_reference,
    )
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )
    app_refs = {reference for reference, _ in _app_values(settings, source)}
    backup_refs = {reference for reference, _ in _backup_values(settings, source)}
    executor_refs = {reference for reference, _ in _executor_values(settings, source)}
    assert not app_refs & executor_refs
    assert not app_refs & backup_refs
    assert not backup_refs & executor_refs
    assert settings.app.csrf_signing_reference in app_refs
    assert settings.executor.binance_api_secret_reference in executor_refs
    assert backup_refs == {
        target.backup_credential_reference
        for _name, target in settings.maintenance.named_targets()
    }
    assert all(
        target.migration_credential_reference
        not in (app_refs | backup_refs | executor_refs)
        for _name, target in settings.maintenance.named_targets()
    )


def test_app_values_include_database_and_fresh_csrf_references() -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    references = (settings.app.database_credential_reference,)
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )
    app_refs = {reference for reference, _ in _app_values(settings, source)}
    assert app_refs == {
        settings.app.database_credential_reference,
        settings.app.csrf_signing_reference,
    }
    assert all(
        target.backup_credential_reference not in app_refs
        and target.migration_credential_reference not in app_refs
        for _name, target in settings.maintenance.named_targets()
    )


def test_live_read_only_executor_values_include_account_observation_references() -> None:
    settings = load_settings(LIVE_READ_ONLY_CONFIG)
    proxy_reference = settings.executor.runtime_proxy_reference
    assert proxy_reference is not None
    key_reference = settings.executor.binance_api_key_reference
    secret_reference = settings.executor.binance_api_secret_reference
    assert key_reference is not None
    assert secret_reference is not None
    references = (
        settings.executor.database_credential_reference,
        key_reference,
        secret_reference,
        proxy_reference,
    )
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )

    executor_refs = tuple(
        reference for reference, _ in _executor_values(settings, source)
    )

    assert executor_refs == references


def _provision_executor_in_memory(settings, target: _MemoryBackend) -> int:
    role_settings = executor_settings(settings)
    references = executor_secret_references(role_settings)
    source = _MemorySource(
        {
            (reference.service, reference.account): "not-a-real-secret"
            for reference in references
        }
    )
    return _write_backend_values(
        backend=target,
        username=windows_deployment(
            settings.release.venue_account_type.value
        ).executor_user,
        values=_executor_values(settings, source),
        forbidden=executor_forbidden_secret_references(role_settings),
    )


@pytest.mark.parametrize(
    ("first_config", "second_config"),
    (
        (DEMO_CONFIG, LIVE_WRITE_CONFIG),
        (LIVE_WRITE_CONFIG, DEMO_CONFIG),
        (DEMO_CONFIG, LIVE_READ_ONLY_CONFIG),
        (LIVE_READ_ONLY_CONFIG, DEMO_CONFIG),
    ),
)
def test_reusing_one_executor_vault_across_profiles_is_rejected_before_write(
    first_config: Path,
    second_config: Path,
) -> None:
    target = _MemoryBackend()
    first = load_settings(first_config)
    second = load_settings(second_config)

    first_count = _provision_executor_in_memory(first, target)
    before_values = dict(target.values)
    before_writes = tuple(target.writes)

    with pytest.raises(
        TaskVaultProvisioningError,
        match="TASK_WINVAULT_FORBIDDEN_REFERENCE_VISIBLE",
    ):
        _provision_executor_in_memory(second, target)

    assert first_count == len(executor_secret_references(executor_settings(first)))
    assert target.values == before_values
    assert tuple(target.writes) == before_writes
    assert target.deletions == []


def test_demo_and_live_executor_vaults_can_be_provisioned_in_parallel() -> None:
    demo = load_settings(DEMO_CONFIG)
    live = load_settings(LIVE_WRITE_CONFIG)
    demo_target = _MemoryBackend()
    live_target = _MemoryBackend()

    demo_count = _provision_executor_in_memory(demo, demo_target)
    live_count = _provision_executor_in_memory(live, live_target)

    assert windows_deployment(demo.release.venue_account_type.value).executor_user != (
        windows_deployment(live.release.venue_account_type.value).executor_user
    )
    assert demo_count == len(executor_secret_references(executor_settings(demo)))
    assert live_count == len(executor_secret_references(executor_settings(live)))
    assert set(demo_target.values).isdisjoint(live_target.values)


def test_reusing_one_app_vault_across_environments_is_rejected_before_write() -> None:
    demo = load_settings(DEMO_CONFIG)
    live = load_settings(LIVE_READ_ONLY_CONFIG)
    target = _MemoryBackend()
    demo_source = _MemorySource(
        {
            (
                demo.app.database_credential_reference.service,
                demo.app.database_credential_reference.account,
            ): "demo-database-secret"
        }
    )
    live_source = _MemorySource(
        {
            (
                live.app.database_credential_reference.service,
                live.app.database_credential_reference.account,
            ): "live-database-secret"
        }
    )
    _write_backend_values(
        backend=target,
        username=windows_deployment(demo.release.venue_account_type.value).app_user,
        values=_app_values(demo, demo_source),
        forbidden=app_peer_secret_references(app_settings(demo)),
    )
    before_values = dict(target.values)
    before_writes = tuple(target.writes)

    with pytest.raises(
        TaskVaultProvisioningError,
        match="TASK_WINVAULT_FORBIDDEN_REFERENCE_VISIBLE",
    ):
        _write_backend_values(
            backend=target,
            username=windows_deployment(live.release.venue_account_type.value).app_user,
            values=_app_values(live, live_source),
            forbidden=app_peer_secret_references(app_settings(live)),
        )

    assert target.values == before_values
    assert tuple(target.writes) == before_writes


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
        settings.app.smtp_credential_reference,
    )
    source = _MemorySource(
        {(reference.service, reference.account): "not-a-real-secret" for reference in references}
    )

    app_refs = {reference for reference, _ in _app_values(settings, source)}

    assert settings.app.smtp_credential_reference in app_refs


def test_provisioner_projects_three_task_vaults_without_cross_role_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    source_references = (
        settings.app.database_credential_reference,
        *(
            target.backup_credential_reference
            for _name, target in settings.maintenance.named_targets()
        ),
        settings.executor.database_credential_reference,
        settings.executor.binance_api_key_reference,
        settings.executor.binance_api_secret_reference,
    )
    source = _MemorySource(
        {
            (reference.service, reference.account): "not-a-real-secret"
            for reference in source_references
        }
    )
    writes: list[dict[str, object]] = []

    monkeypatch.setattr(vaults, "_require_task_identity_binding", lambda _settings: None)
    monkeypatch.setattr(vaults.keyring, "get_keyring", lambda: source)
    monkeypatch.setattr(vaults, "require_win_vault_backend", lambda backend: backend)
    monkeypatch.setattr(
        vaults,
        "_task_password",
        lambda backend, username: f"{username}-test-password",
    )

    def record_write(**kwargs: object) -> int:
        material = tuple(kwargs["values"])  # type: ignore[arg-type]
        forbidden = set(kwargs["forbidden"])  # type: ignore[arg-type]
        assert not {reference for reference, _ in material} & forbidden
        writes.append({**kwargs, "values": material})
        return len(material)

    monkeypatch.setattr(vaults, "_write_as_task_identity", record_write)

    report = vaults.provision_task_vaults(settings)

    assert [write["username"] for write in writes] == [
        windows_deployment(settings.release.venue_account_type.value).app_user,
        windows_deployment(settings.release.venue_account_type.value).executor_user,
        SHARED_BACKUP_USER,
    ]
    projected = [
        {reference for reference, _ in write["values"]}  # type: ignore[union-attr]
        for write in writes
    ]
    assert projected[0] == {
        settings.app.database_credential_reference,
        settings.app.csrf_signing_reference,
    }
    assert projected[1] == {
        settings.executor.database_credential_reference,
        settings.executor.binance_api_key_reference,
        settings.executor.binance_api_secret_reference,
    }
    assert projected[2] == {
        target.backup_credential_reference
        for _name, target in settings.maintenance.named_targets()
    }
    assert not projected[0] & projected[1]
    assert not projected[0] & projected[2]
    assert not projected[1] & projected[2]
    assert set(
        executor_forbidden_secret_references(executor_settings(settings))
    ) <= set(writes[1]["forbidden"])  # type: ignore[arg-type]
    peer_app_references = app_peer_secret_references(
        app_settings(settings)
    )
    assert set(peer_app_references) <= set(
        writes[0]["forbidden"]  # type: ignore[arg-type]
    )
    assert set(peer_app_references) <= set(
        writes[1]["forbidden"]  # type: ignore[arg-type]
    )
    assert report["backup_reference_count"] == 3
    assert report["shared_backup_provisioned"] is True


def test_live_profile_provisions_only_live_product_task_vaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_READ_ONLY_CONFIG)
    deployment = windows_deployment(settings.release.venue_account_type.value)
    source_references = (
        settings.app.database_credential_reference,
        settings.executor.database_credential_reference,
        settings.executor.binance_api_key_reference,
        settings.executor.binance_api_secret_reference,
        settings.executor.runtime_proxy_reference,
    )
    source = _MemorySource(
        {
            (reference.service, reference.account): "not-a-real-secret"
            for reference in source_references
            if reference is not None
        }
    )
    writes: list[dict[str, object]] = []

    monkeypatch.setattr(vaults, "_require_task_identity_binding", lambda _settings: None)
    monkeypatch.setattr(vaults.keyring, "get_keyring", lambda: source)
    monkeypatch.setattr(vaults, "require_win_vault_backend", lambda backend: backend)
    monkeypatch.setattr(
        vaults,
        "_task_password",
        lambda backend, username: f"{username}-test-password",
    )

    def record_write(**kwargs: object) -> int:
        material = tuple(kwargs["values"])  # type: ignore[arg-type]
        writes.append({**kwargs, "values": material})
        return len(material)

    monkeypatch.setattr(vaults, "_write_as_task_identity", record_write)
    stop_checks: list[str] = []
    monkeypatch.setattr(
        vaults,
        "_require_live_task_reprojection_stopped",
        lambda **_kwargs: stop_checks.append("checked"),
    )
    monkeypatch.setattr(
        vaults,
        "acquire_executor_maintenance_mutex",
        lambda **_kwargs: nullcontext(),
    )

    report = vaults.provision_task_vaults(
        settings,
        repository_root=ROOT,
        config_path=LIVE_READ_ONLY_CONFIG,
        task_service=object(),
    )

    assert [write["username"] for write in writes] == [
        deployment.app_user,
        deployment.executor_user,
    ]
    assert SHARED_BACKUP_USER not in {
        write["username"] for write in writes
    }
    assert report["backup_reference_count"] == 0
    assert report["shared_backup_provisioned"] is False
    assert stop_checks == ["checked", "checked"]
    assert all(
        set(write["delete_to_allowlist"])  # type: ignore[arg-type]
        == set(known_live_credential_references())
        for write in writes
    )


def test_delete_password_helper_is_missing_safe_and_verifies_real_deletion() -> None:
    reference = WinVaultReference(
        service="Halpha/PostgreSQL/BINANCE_LIVE_COPY/App",
        account="scram_password",
    )
    missing = _MissingDeleteMustNotBeCalled()
    assert (
        _delete_password_if_present(
            missing,
            reference,
            username="HalphaAppCopy",
        )
        is False
    )

    present = _MemoryBackend()
    present.values[(reference.service, reference.account)] = "not-a-real-secret"
    assert (
        _delete_password_if_present(
            present,
            reference,
            username="HalphaAppCopy",
        )
        is True
    )
    assert present.deletions == [(reference.service, reference.account)]
    assert present.get_password(reference.service, reference.account) is None


def test_live_read_only_convergence_deletes_write_credentials_to_exact_allowlists() -> None:
    settings = load_settings(LIVE_READ_ONLY_CONFIG)
    universe = known_live_credential_references()
    universe_values = {
        (reference.service, reference.account): "not-a-real-secret"
        for reference in universe
    }

    app_target = _MemoryBackend()
    app_target.values.update(universe_values)
    app_material = (
        (settings.app.database_credential_reference, "reader-password"),
        (settings.app.csrf_signing_reference, "csrf-secret"),
        (settings.app.smtp_credential_reference, "smtp-password"),
    )
    app_allowed = {reference for reference, _value in app_material}
    _write_backend_values(
        backend=app_target,
        username="HalphaAppCopy",
        values=app_material,
        forbidden=(
            reference for reference in universe if reference not in app_allowed
        ),
        delete_to_allowlist=universe,
    )

    assert set(app_target.values) == {
        (reference.service, reference.account) for reference in app_allowed
    }
    assert (
        "Halpha/PostgreSQL/BINANCE_LIVE_COPY/App",
        "scram_password",
    ) in app_target.deletions

    executor_target = _MemoryBackend()
    executor_target.values.update(universe_values)
    proxy = settings.executor.runtime_proxy_reference
    assert proxy is not None
    executor_material = ((proxy, "proxy-secret"),)
    _write_backend_values(
        backend=executor_target,
        username="HalphaExecCopy",
        values=executor_material,
        forbidden=(reference for reference in universe if reference != proxy),
        delete_to_allowlist=universe,
    )

    assert set(executor_target.values) == {(proxy.service, proxy.account)}
    for forbidden_identity in (
        ("Halpha/PostgreSQL/BINANCE_LIVE_COPY/Executor", "scram_password"),
        ("Halpha/Binance/BINANCE_LIVE_COPY", "api_key"),
        ("Halpha/Binance/BINANCE_LIVE_COPY", "api_secret"),
    ):
        assert forbidden_identity in executor_target.deletions


def test_live_vault_reprojection_mutex_conflict_precedes_source_vault_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_READ_ONLY_CONFIG)
    accesses: list[str] = []
    monkeypatch.setattr(
        vaults,
        "acquire_executor_maintenance_mutex",
        lambda **_kwargs: (_ for _ in ()).throw(
            vaults.WindowsRuntimeError(
                "LIVE_TASK_WINVAULT_REPROJECTION_EXECUTOR_MUST_BE_STOPPED"
            )
        ),
    )
    monkeypatch.setattr(
        vaults.keyring,
        "get_keyring",
        lambda: accesses.append("source-vault"),
    )

    with pytest.raises(
        TaskVaultProvisioningError,
        match="LIVE_TASK_WINVAULT_REPROJECTION_EXECUTOR_MUST_BE_STOPPED",
    ):
        vaults.provision_task_vaults(
            settings,
            repository_root=ROOT,
            config_path=LIVE_READ_ONLY_CONFIG,
            task_service=object(),
        )

    assert accesses == []


def test_live_vault_reprojection_holds_mutex_across_both_inventory_checks_and_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_WRITE_CONFIG)
    events: list[str] = []

    class _Guard:
        def __enter__(self):
            events.append("entered")
            return self

        def __exit__(self, *_args):
            events.append("exited")

    monkeypatch.setattr(
        vaults,
        "acquire_executor_maintenance_mutex",
        lambda **_kwargs: _Guard(),
    )
    monkeypatch.setattr(
        vaults,
        "_require_live_task_reprojection_stopped",
        lambda **_kwargs: events.append("inventory"),
    )
    monkeypatch.setattr(
        vaults,
        "_require_task_identity_binding",
        lambda _settings: events.append("identity"),
    )

    def project(_settings):
        assert events == ["entered", "inventory", "identity", "inventory"]
        events.append("projected")
        return {"status": "TASK_WINVAULTS_PROVISIONED"}

    monkeypatch.setattr(vaults, "_provision_task_vaults_under_guard", project)

    report = vaults.provision_task_vaults(
        settings,
        repository_root=ROOT,
        config_path=LIVE_WRITE_CONFIG,
        task_service=object(),
    )

    assert report["status"] == "TASK_WINVAULTS_PROVISIONED"
    assert events == [
        "entered",
        "inventory",
        "identity",
        "inventory",
        "projected",
        "exited",
    ]


def test_live_vault_reprojection_requires_inventory_coordinates() -> None:
    settings = load_settings(LIVE_READ_ONLY_CONFIG)

    with pytest.raises(
        TaskVaultProvisioningError,
        match="LIVE_TASK_WINVAULT_REPROJECTION_INVENTORY_REQUIRED",
    ):
        vaults.provision_task_vaults(settings)


def test_identity_mismatch_rejects_before_source_vault_access_or_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(DEMO_CONFIG)
    deployment = windows_deployment(settings.release.venue_account_type.value)
    calls: list[str] = []

    monkeypatch.setattr(
        vaults,
        "_account_sid",
        lambda username: (
            "S-1-5-21-9-9-9-9999"
            if username == deployment.executor_user
            else {
                deployment.app_user: settings.windows.app_task_sid,
                SHARED_BACKUP_USER: settings.windows.backup_task_sid,
            }[username]
        ),
    )
    monkeypatch.setattr(
        vaults,
        "_current_user_sid",
        lambda: settings.windows.maintenance_sid,
    )
    monkeypatch.setattr(
        vaults.keyring,
        "get_keyring",
        lambda: calls.append("source-vault-read"),
    )
    monkeypatch.setattr(
        vaults,
        "_write_as_task_identity",
        lambda **_kwargs: calls.append("task-vault-write"),
    )

    with pytest.raises(
        TaskVaultProvisioningError,
        match="WINDOWS_IDENTITY_CONFIG_MISMATCH roles=executor",
    ):
        vaults.provision_task_vaults(settings)

    assert calls == []


def test_task_vault_provisioner_has_no_external_secret_transport() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "subprocess" not in source
    assert "pgpassword" not in source
    assert "secret_transport\": \"in_process_impersonation_only" in source
    assert "getpass" not in source
    assert "owner_password" not in source
