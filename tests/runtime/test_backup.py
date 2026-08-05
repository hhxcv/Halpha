from __future__ import annotations

from pathlib import Path

import pytest
import win32security

from halpha import backup as backup_module
from halpha.backup import (
    BACKUP_MANIFEST_KEYS,
    BackupError,
    _apply_retention,
    _assert_restore_manifest,
    _escape_pgpass,
    _protected_security_attributes,
    _repository_path,
    _sha256_file,
)
from halpha.configuration import load_settings
from halpha.windows_filesystem import role_write_grants
from halpha.windows_runtime import BUILTIN_ADMINISTRATORS_SID, SYSTEM_SID


ROOT = Path(__file__).resolve().parents[2]


def test_pgpass_escaping_handles_separator_and_backslash() -> None:
    assert _escape_pgpass(r"a:b\c") == r"a\:b\\c"


def test_repository_paths_cannot_escape_root(tmp_path: Path) -> None:
    assert _repository_path(tmp_path, "backups/postgresql") == (
        tmp_path / "backups" / "postgresql"
    ).resolve()
    with pytest.raises(BackupError, match="OUTSIDE_REPOSITORY"):
        _repository_path(tmp_path, "../outside")


def test_retention_keeps_latest_fourteen_archives_and_manifests(tmp_path: Path) -> None:
    for day in range(16):
        archive = tmp_path / f"halpha_demo-202607{day + 1:02d}T000000Z.dump"
        archive.write_bytes(b"backup")
        archive.with_suffix(".json").write_text("{}", encoding="utf-8")
    removed = _apply_retention(tmp_path, 14)
    assert removed == [
        "halpha_demo-20260702T000000Z.dump",
        "halpha_demo-20260701T000000Z.dump",
    ]
    assert len(list(tmp_path.glob("*.dump"))) == 14
    assert len(list(tmp_path.glob("*.json"))) == 14


def test_backup_source_has_no_password_argument_or_environment_transport() -> None:
    source = (Path(__file__).resolve().parents[2] / "src" / "halpha" / "backup.py").read_text(
        encoding="utf-8"
    )
    assert "PGPASSWORD" not in source
    assert "--password" not in source
    assert "--no-privileges" not in source
    assert "FILE_FLAG_DELETE_ON_CLOSE" in source


def test_restore_manifest_binds_the_exact_environment_archive(
    tmp_path: Path,
) -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    target = settings.maintenance.demo
    archive = tmp_path / "halpha_demo-20260725T010203Z.dump"
    archive.write_bytes(b"custom-archive")
    manifest = {
        "schema_version": 2,
        "observed_at": "2026-07-25T01:02:03Z",
        "database": "halpha_demo",
        "environment_kind": "DEMO",
        "venue_account_type": "USDM_DEMO",
        "archive": archive.name,
        "archive_size": archive.stat().st_size,
        "archive_sha256": _sha256_file(archive),
        "format": "POSTGRESQL_CUSTOM",
        "tool_version": backup_module.POSTGRESQL_VERSION,
        "credential_transport": "DELETE_ON_CLOSE_PGPASSFILE",
    }

    assert set(manifest) == BACKUP_MANIFEST_KEYS
    _assert_restore_manifest(archive, manifest, target=target)

    with pytest.raises(BackupError, match="RESTORE_MANIFEST_INVALID"):
        _assert_restore_manifest(
            archive,
            {**manifest, "environment_kind": "LIVE"},
            target=target,
        )


def test_pgpass_file_acl_keeps_maintenance_and_backup_boundary() -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    attributes = _protected_security_attributes(
        settings.windows.backup_task_sid,
        settings.windows.maintenance_sid,
    )
    descriptor = attributes.SECURITY_DESCRIPTOR
    dacl = descriptor.GetSecurityDescriptorDacl()
    actual = {
        str(win32security.ConvertSidToStringSid(ace[2])): int(ace[1])
        for ace in (dacl.GetAce(index) for index in range(dacl.GetAceCount()))
    }

    assert actual == dict(
        role_write_grants(
            maintenance_sid=settings.windows.maintenance_sid,
            role_sid=settings.windows.backup_task_sid,
        )
    )


def test_restore_pgpass_file_acl_deduplicates_maintenance_identity() -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    attributes = _protected_security_attributes(
        settings.windows.maintenance_sid,
        settings.windows.maintenance_sid,
    )
    descriptor = attributes.SECURITY_DESCRIPTOR
    dacl = descriptor.GetSecurityDescriptorDacl()
    actual = {
        str(win32security.ConvertSidToStringSid(ace[2])): int(ace[1])
        for ace in (dacl.GetAce(index) for index in range(dacl.GetAceCount()))
    }

    assert actual == {
        SYSTEM_SID: backup_module.win32file.FILE_ALL_ACCESS,
        BUILTIN_ADMINISTRATORS_SID: backup_module.win32file.FILE_ALL_ACCESS,
        settings.windows.maintenance_sid: backup_module.win32file.FILE_ALL_ACCESS,
    }


def test_backup_requires_backup_identity_before_vault_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    observed: list[str] = []

    def stop_after_identity_check(sid: str) -> None:
        observed.append(sid)
        raise RuntimeError("identity-boundary-stop")

    monkeypatch.setattr(
        backup_module,
        "require_process_identity",
        stop_after_identity_check,
    )
    monkeypatch.setattr(
        backup_module.keyring,
        "get_keyring",
        lambda: pytest.fail("vault access must follow identity validation"),
    )

    with pytest.raises(RuntimeError, match="identity-boundary-stop"):
        backup_module.backup_environment(
            tmp_path,
            settings,
            environment="demo",
        )

    assert observed == [settings.windows.backup_task_sid]
    assert settings.windows.backup_task_sid != settings.windows.app_task_sid


def test_restore_requires_maintenance_identity_before_archive_or_vault_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(ROOT / "config" / "halpha.example.toml")
    observed: list[str] = []

    def stop_after_identity_check(sid: str) -> None:
        observed.append(sid)
        raise RuntimeError("identity-boundary-stop")

    monkeypatch.setattr(
        backup_module,
        "require_process_identity",
        stop_after_identity_check,
    )
    monkeypatch.setattr(
        backup_module.keyring,
        "get_keyring",
        lambda: pytest.fail("vault access must follow identity validation"),
    )

    with pytest.raises(RuntimeError, match="identity-boundary-stop"):
        backup_module.restore_archive(
            tmp_path,
            settings,
            environment="live_copy",
            archive=tmp_path / "missing.dump",
            target_database="halpha_restore_test",
        )

    assert observed == [settings.windows.maintenance_sid]
    assert settings.windows.maintenance_sid != settings.windows.backup_task_sid
