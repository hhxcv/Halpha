from __future__ import annotations

from pathlib import Path

import pytest
import win32con
import win32file

from halpha.configuration import load_settings
from halpha.windows_filesystem import (
    DIRECTORY_MODIFY,
    DIRECTORY_READ_EXECUTE,
    WindowsFilesystemError,
    runtime_filesystem_specs,
)
from tools.provisioning import provision_runtime_acls as acl_module


ROOT = Path(__file__).resolve().parents[2]
DEMO_CONFIG = ROOT / "config" / "halpha.example.toml"
LIVE_CONFIG = ROOT / "config" / "halpha.live-copy-read-only.example.toml"
PERSONAL_CONFIG = ROOT / "config" / "halpha.live-personal-read-only.example.toml"


def _settings():
    return (
        load_settings(DEMO_CONFIG),
        load_settings(LIVE_CONFIG),
        load_settings(PERSONAL_CONFIG),
    )


def test_runtime_acl_plan_is_read_only_except_exact_role_directories(
    tmp_path: Path,
) -> None:
    demo, live, personal = _settings()
    specs = runtime_filesystem_specs(tmp_path, demo, live, personal)
    by_label = {spec.label: spec for spec in specs}

    read_boundaries = {
        "repository",
        "venv",
        "source",
        "configuration",
        "frontend",
        "migrations",
        "requirements",
        "build",
        "runtime_log_root",
        "demo_log_environment",
        "live_copy_log_environment",
        "live_personal_log_environment",
        "maintenance_log_root",
        "backup_parent",
        "backup_root",
        "temporary_parent",
    }
    runtime_sids = {
        demo.windows.app_task_sid,
        demo.windows.executor_task_sid,
        live.windows.app_task_sid,
        live.windows.executor_task_sid,
        personal.windows.app_task_sid,
        personal.windows.executor_task_sid,
        demo.windows.backup_task_sid,
    }
    for label in read_boundaries:
        grants = by_label[label].grant_map()
        assert {grants[sid] for sid in runtime_sids} == {
            DIRECTORY_READ_EXECUTE
        }
        assert not DIRECTORY_READ_EXECUTE & (
            0x0002
            | 0x0004
            | 0x0010
            | 0x0040
            | 0x0100
            | win32con.DELETE
            | win32con.WRITE_DAC
            | win32con.WRITE_OWNER
        )

    role_directories = {
        "binance-demo-primary_app_logs": demo.windows.app_task_sid,
        "binance-demo-primary_executor_logs": demo.windows.executor_task_sid,
        "binance-live-copy-primary_app_logs": live.windows.app_task_sid,
        "binance-live-copy-primary_executor_logs": live.windows.executor_task_sid,
        "binance-live-personal-primary_app_logs": personal.windows.app_task_sid,
        "binance-live-personal-primary_executor_logs": personal.windows.executor_task_sid,
        "backup_logs": demo.windows.backup_task_sid,
        "demo_backups": demo.windows.backup_task_sid,
        "live_copy_backups": demo.windows.backup_task_sid,
        "live_personal_backups": demo.windows.backup_task_sid,
        "backup_temporary": demo.windows.backup_task_sid,
    }
    for label, owner_role_sid in role_directories.items():
        grants = by_label[label].grant_map()
        assert grants[owner_role_sid] == DIRECTORY_MODIFY
        assert not DIRECTORY_MODIFY & (
            win32con.WRITE_DAC | win32con.WRITE_OWNER
        )
        assert not (runtime_sids - {owner_role_sid}) & set(grants)

    assert by_label["demo_log_environment"].path == (
        tmp_path / "logs" / demo.release.environment_id
    ).resolve()
    assert by_label["live_copy_log_environment"].path == (
        tmp_path / "logs" / live.release.environment_id
    ).resolve()
    assert by_label["live_personal_log_environment"].path == (
        tmp_path / "logs" / personal.release.environment_id
    ).resolve()
    assert by_label["backup_parent"].path == (tmp_path / "backups").resolve()
    assert by_label["backup_root"].path == (
        tmp_path / "backups" / "postgresql"
    ).resolve()
    assert by_label["temporary_parent"].path == (tmp_path / "tmp").resolve()


def test_runtime_acl_plan_keeps_live_observation_inside_executor_logs(
    tmp_path: Path,
) -> None:
    demo, live, personal = _settings()
    by_label = {
        spec.label: spec
        for spec in runtime_filesystem_specs(tmp_path, demo, live, personal)
    }

    live_executor = by_label["binance-live-copy-primary_executor_logs"].path
    assert live_executor == (
        tmp_path
        / "logs"
        / live.release.environment_id
        / "executor"
    ).resolve()
    assert not any(
        spec.path == (tmp_path / "build" / "evidence" / "reports").resolve()
        and spec.create
        for spec in by_label.values()
    )


def test_runtime_acl_plan_rejects_shared_identity_drift(
    tmp_path: Path,
) -> None:
    demo, live, personal = _settings()
    changed_windows = live.windows.model_copy(
        update={"backup_task_sid": "S-1-5-21-0-0-0-9999"}
    )
    changed_live = live.model_copy(update={"windows": changed_windows})

    with pytest.raises(
        WindowsFilesystemError,
        match="WINDOWS_FILESYSTEM_SHARED_IDENTITY_MISMATCH",
    ):
        runtime_filesystem_specs(tmp_path, demo, changed_live, personal)


def test_provisioning_applies_and_rechecks_every_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    demo, live, personal = _settings()
    (tmp_path / ".venv").mkdir()
    specs = runtime_filesystem_specs(tmp_path, demo, live, personal)[:2]
    observed: list[tuple[str, str]] = []

    monkeypatch.setattr(
        acl_module,
        "runtime_filesystem_specs",
        lambda *_args: specs,
    )
    monkeypatch.setattr(
        acl_module,
        "_require_elevated_administrator",
        lambda: observed.append(("preflight", "administrator")),
    )
    monkeypatch.setattr(
        acl_module,
        "_require_identity_bindings",
        lambda *_args: observed.append(("preflight", "identities")),
    )
    monkeypatch.setattr(
        acl_module,
        "_require_halpha_tasks_stopped",
        lambda: observed.append(("preflight", "tasks")),
    )
    monkeypatch.setattr(
        acl_module,
        "_require_runtime_processes_stopped",
        lambda *_args: observed.append(("preflight", "processes")),
    )
    monkeypatch.setattr(
        acl_module,
        "_prepare_paths",
        lambda *_args, **_kwargs: observed.append(("preflight", "paths")),
    )
    monkeypatch.setattr(
        acl_module,
        "apply_directory_security",
        lambda spec: observed.append(("apply", spec.label)),
    )
    monkeypatch.setattr(
        acl_module,
        "assert_directory_security",
        lambda spec: observed.append(("assert", spec.label)),
    )

    report = acl_module.provision_runtime_acls(tmp_path, demo, live, personal)

    assert report["status"] == "WINDOWS_RUNTIME_ACLS_PROVISIONED"
    assert observed[:5] == [
        ("preflight", "administrator"),
        ("preflight", "identities"),
        ("preflight", "tasks"),
        ("preflight", "processes"),
        ("preflight", "paths"),
    ]
    assert [
        item for item in observed if item[0] == "apply"
    ] == [("apply", spec.label) for spec in specs]
    assert [
        item for item in observed if item[0] == "assert"
    ] == [
        *(("assert", spec.label) for spec in specs),
        *(("assert", spec.label) for spec in specs),
    ]


def test_qualification_rejects_a_missing_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    demo, live, personal = _settings()
    missing = runtime_filesystem_specs(tmp_path, demo, live, personal)[2]
    monkeypatch.setattr(
        acl_module,
        "runtime_filesystem_specs",
        lambda *_args: (missing,),
    )
    monkeypatch.setattr(
        acl_module,
        "_require_identity_bindings",
        lambda *_args: None,
    )

    with pytest.raises(
        acl_module.RuntimeAclProvisioningError,
        match="WINDOWS_FILESYSTEM_DIRECTORY_MISSING",
    ):
        acl_module.qualify_runtime_acls(tmp_path, demo, live, personal)


def test_directory_modify_is_not_full_control() -> None:
    assert DIRECTORY_MODIFY != win32file.FILE_ALL_ACCESS
    assert DIRECTORY_MODIFY & win32con.DELETE
    assert not DIRECTORY_MODIFY & (win32con.WRITE_DAC | win32con.WRITE_OWNER)
