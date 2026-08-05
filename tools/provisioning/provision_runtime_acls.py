"""Provision exact Windows filesystem boundaries for all trading contexts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import pywintypes
import win32com.client

from halpha.configuration import HalphaSettings, load_settings
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_deployment import (
    DEMO_DEPLOYMENT,
    LIVE_COPY_DEPLOYMENT,
    LIVE_PERSONAL_DEPLOYMENT,
    SHARED_BACKUP_TASK,
    SHARED_BACKUP_USER,
)
from halpha.windows_filesystem import (
    DirectoryAclSpec,
    WindowsFilesystemError,
    apply_directory_security,
    assert_directory_security,
    runtime_filesystem_specs,
)
from tools.provisioning.provision_windows_tasks import (
    TASK_FOLDER,
    ProvisioningError,
    _account_sid,
    _current_user_sid,
    _require_configured_identity_sids,
    _require_elevated_administrator,
)


TASK_STATE_RUNNING = 4
_TASK_NOT_FOUND_HRESULTS = frozenset({0x80070002, 0x80070003})


class RuntimeAclProvisioningError(RuntimeError):
    """A sanitized filesystem-boundary provisioning failure."""


def _task_scheduler_object_not_found(exc: pywintypes.com_error) -> bool:
    excepinfo = getattr(exc, "excepinfo", None)
    codes = (
        getattr(exc, "hresult", None),
        (
            excepinfo[5]
            if isinstance(excepinfo, tuple) and len(excepinfo) > 5
            else None
        ),
    )
    return any(
        isinstance(code, int)
        and (code & 0xFFFFFFFF) in _TASK_NOT_FOUND_HRESULTS
        for code in codes
    )


def _identity_bindings(
    demo: HalphaSettings,
    live_copy: HalphaSettings,
    live_personal: HalphaSettings,
) -> tuple[dict[str, str], dict[str, str]]:
    configured = {
        "backup": demo.windows.backup_task_sid,
        "demo_app": demo.windows.app_task_sid,
        "demo_executor": demo.windows.executor_task_sid,
        "live_copy_app": live_copy.windows.app_task_sid,
        "live_copy_executor": live_copy.windows.executor_task_sid,
        "live_personal_app": live_personal.windows.app_task_sid,
        "live_personal_executor": live_personal.windows.executor_task_sid,
        "maintenance": demo.windows.maintenance_sid,
    }
    try:
        actual = {
            "backup": _account_sid(SHARED_BACKUP_USER),
            "demo_app": _account_sid(DEMO_DEPLOYMENT.app_user),
            "demo_executor": _account_sid(DEMO_DEPLOYMENT.executor_user),
            "live_copy_app": _account_sid(LIVE_COPY_DEPLOYMENT.app_user),
            "live_copy_executor": _account_sid(LIVE_COPY_DEPLOYMENT.executor_user),
            "live_personal_app": _account_sid(LIVE_PERSONAL_DEPLOYMENT.app_user),
            "live_personal_executor": _account_sid(
                LIVE_PERSONAL_DEPLOYMENT.executor_user
            ),
            "maintenance": _current_user_sid(),
        }
    except ProvisioningError as exc:
        raise RuntimeAclProvisioningError(str(exc)) from None
    return configured, actual


def _require_identity_bindings(
    demo: HalphaSettings,
    live_copy: HalphaSettings,
    live_personal: HalphaSettings,
) -> None:
    configured, actual = _identity_bindings(demo, live_copy, live_personal)
    contexts = (demo, live_copy, live_personal)
    if len({item.windows.maintenance_sid for item in contexts}) != 1:
        raise RuntimeAclProvisioningError(
            "WINDOWS_FILESYSTEM_MAINTENANCE_IDENTITY_MISMATCH"
        )
    if len({item.windows.backup_task_sid for item in contexts}) != 1:
        raise RuntimeAclProvisioningError(
            "WINDOWS_FILESYSTEM_BACKUP_IDENTITY_MISMATCH"
        )
    try:
        _require_configured_identity_sids(
            configured=configured,
            actual=actual,
        )
    except ProvisioningError as exc:
        raise RuntimeAclProvisioningError(str(exc)) from None


def _require_halpha_tasks_stopped() -> None:
    try:
        service = win32com.client.Dispatch("Schedule.Service")
        service.Connect()
        try:
            folder = service.GetFolder(TASK_FOLDER)
        except pywintypes.com_error as exc:
            if _task_scheduler_object_not_found(exc):
                return
            raise
        running: list[str] = []
        task_names = (
            DEMO_DEPLOYMENT.app_task,
            DEMO_DEPLOYMENT.executor_task,
            LIVE_COPY_DEPLOYMENT.app_task,
            LIVE_COPY_DEPLOYMENT.executor_task,
            LIVE_PERSONAL_DEPLOYMENT.app_task,
            LIVE_PERSONAL_DEPLOYMENT.executor_task,
            SHARED_BACKUP_TASK,
        )
        for task_name in task_names:
            try:
                task = folder.GetTask(task_name)
            except pywintypes.com_error as exc:
                if _task_scheduler_object_not_found(exc):
                    continue
                raise
            instances = tuple(task.GetInstances(1))
            if int(task.State) == TASK_STATE_RUNNING or instances:
                running.append(task_name)
    except RuntimeAclProvisioningError:
        raise
    except Exception as exc:
        raise RuntimeAclProvisioningError(
            "WINDOWS_FILESYSTEM_TASK_DISCOVERY_FAILED "
            f"type={type(exc).__name__}"
        ) from None
    if running:
        raise RuntimeAclProvisioningError(
            "WINDOWS_FILESYSTEM_TASKS_MUST_BE_STOPPED "
            f"tasks={','.join(sorted(running))}"
        )


def _require_runtime_processes_stopped(repository_root: Path) -> None:
    root_key = str(repository_root.resolve()).replace("/", "\\").casefold()
    try:
        service = win32com.client.GetObject(r"winmgmts:root\cimv2")
        rows = service.ExecQuery(
            "SELECT ProcessId,ExecutablePath,CommandLine FROM Win32_Process"
        )
    except Exception as exc:
        raise RuntimeAclProvisioningError(
            "WINDOWS_FILESYSTEM_PROCESS_DISCOVERY_FAILED "
            f"type={type(exc).__name__}"
        ) from None
    running: list[int] = []
    signatures = (
        "-m halpha.app",
        "-m halpha.executor",
        "-m halpha.backup",
        "halpha-app.exe",
        "halpha-executor.exe",
        "halpha-backup.exe",
    )
    for row in rows:
        identity = (
            f"{row.ExecutablePath or ''}\0{row.CommandLine or ''}"
            .replace("/", "\\")
            .casefold()
        )
        if root_key in identity and any(
            signature in identity for signature in signatures
        ):
            running.append(int(row.ProcessId))
    if running:
        raise RuntimeAclProvisioningError(
            "WINDOWS_FILESYSTEM_PROCESSES_MUST_BE_STOPPED "
            f"pids={','.join(str(pid) for pid in sorted(running))}"
        )


def _is_reparse_boundary(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _prepare_paths(
    repository_root: Path,
    specs: tuple[DirectoryAclSpec, ...],
    *,
    create_missing: bool,
) -> None:
    root = repository_root.resolve()
    if _is_reparse_boundary(root):
        raise RuntimeAclProvisioningError(
            "WINDOWS_FILESYSTEM_REPOSITORY_REPARSE_FORBIDDEN"
        )
    for spec in specs:
        resolved = spec.path.resolve()
        if resolved != root and not resolved.is_relative_to(root):
            raise RuntimeAclProvisioningError(
                f"WINDOWS_FILESYSTEM_PATH_OUTSIDE_REPOSITORY boundary={spec.label}"
            )
        cursor = spec.path
        while cursor != root:
            if cursor.exists() and _is_reparse_boundary(cursor):
                raise RuntimeAclProvisioningError(
                    f"WINDOWS_FILESYSTEM_REPARSE_FORBIDDEN boundary={spec.label}"
                )
            cursor = cursor.parent
        if spec.create and create_missing:
            spec.path.mkdir(parents=True, exist_ok=True)
        if not spec.path.is_dir():
            raise RuntimeAclProvisioningError(
                f"WINDOWS_FILESYSTEM_DIRECTORY_MISSING boundary={spec.label}"
            )


def qualify_runtime_acls(
    repository_root: Path,
    demo: HalphaSettings,
    live_copy: HalphaSettings,
    live_personal: HalphaSettings,
) -> dict[str, Any]:
    """Read and validate every exact ACL boundary without changing it."""

    specs = runtime_filesystem_specs(
        repository_root, demo, live_copy, live_personal
    )
    _require_identity_bindings(demo, live_copy, live_personal)
    _prepare_paths(
        repository_root,
        specs,
        create_missing=False,
    )
    for spec in specs:
        assert_directory_security(spec)
    return {
        "status": "WINDOWS_RUNTIME_ACLS_QUALIFIED",
        "boundaries": [
            {
                "label": spec.label,
                "path": str(spec.path),
                "owner_sid": spec.owner_sid,
                "grants": [
                    {"sid": sid, "mask": mask}
                    for sid, mask in spec.grants
                ],
            }
            for spec in specs
        ],
        "runtime_source_access": "READ_EXECUTE_ONLY",
        "role_write_directories": "ISOLATED",
    }


def provision_runtime_acls(
    repository_root: Path,
    demo: HalphaSettings,
    live_copy: HalphaSettings,
    live_personal: HalphaSettings,
) -> dict[str, Any]:
    """Apply the bounded ACL plan and verify the exact postcondition."""

    _require_elevated_administrator()
    specs = runtime_filesystem_specs(
        repository_root, demo, live_copy, live_personal
    )
    _require_identity_bindings(demo, live_copy, live_personal)
    _require_halpha_tasks_stopped()
    _require_runtime_processes_stopped(repository_root)
    _prepare_paths(
        repository_root,
        specs,
        create_missing=True,
    )
    for spec in specs:
        apply_directory_security(spec)
        assert_directory_security(spec)
    return qualify_runtime_acls(repository_root, demo, live_copy, live_personal) | {
        "status": "WINDOWS_RUNTIME_ACLS_PROVISIONED"
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provision-runtime-acls")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--demo-config", type=Path, required=True)
    parser.add_argument("--live-copy-config", type=Path, required=True)
    parser.add_argument("--live-personal-config", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.repository_root.resolve()
        require_repository_runtime(root)
        demo = load_settings(args.demo_config)
        live_copy = load_settings(args.live_copy_config)
        live_personal = load_settings(args.live_personal_config)
        report = (
            qualify_runtime_acls(root, demo, live_copy, live_personal)
            if args.check_only
            else provision_runtime_acls(root, demo, live_copy, live_personal)
        )
    except Exception as exc:
        if isinstance(
            exc,
            (
                RuntimeAclProvisioningError,
                WindowsFilesystemError,
            ),
        ):
            reason = str(exc)
        else:
            reason = (
                "WINDOWS_RUNTIME_ACL_PROVISIONING_FAILED "
                f"type={type(exc).__name__}"
            )
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
