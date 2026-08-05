"""Exact Windows filesystem boundaries for the local product identities."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pywintypes
import win32api
import win32con
import win32file
import win32security

from halpha.configuration import (
    HalphaSettings,
    VenueAccountType,
    backup_log_directory,
    runtime_log_directory,
)
from halpha.windows_runtime import BUILTIN_ADMINISTRATORS_SID, SYSTEM_SID


FILE_EXECUTE = 0x0020
FILE_DELETE_CHILD = 0x0040
FILE_READ_ATTRIBUTES = 0x0080
FILE_GENERIC_EXECUTE = (
    win32con.READ_CONTROL
    | win32con.SYNCHRONIZE
    | FILE_EXECUTE
    | FILE_READ_ATTRIBUTES
)
DIRECTORY_READ_EXECUTE = win32file.FILE_GENERIC_READ | FILE_GENERIC_EXECUTE
DIRECTORY_MODIFY = (
    DIRECTORY_READ_EXECUTE
    | win32file.FILE_GENERIC_WRITE
    | win32con.DELETE
    | FILE_DELETE_CHILD
)
DIRECTORY_INHERIT_FLAGS = (
    win32security.OBJECT_INHERIT_ACE
    | win32security.CONTAINER_INHERIT_ACE
)


class WindowsFilesystemError(RuntimeError):
    """A sanitized runtime-filesystem provisioning or qualification failure."""


@dataclass(frozen=True)
class DirectoryAclSpec:
    label: str
    path: Path
    owner_sid: str
    grants: tuple[tuple[str, int], ...]
    create: bool

    def grant_map(self) -> dict[str, int]:
        return dict(self.grants)


def _ordered_grants(values: Iterable[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    material = tuple(values)
    identities = tuple(sid for sid, _mask in material)
    if len(set(identities)) != len(identities):
        raise WindowsFilesystemError("WINDOWS_FILESYSTEM_IDENTITIES_MUST_BE_DISTINCT")
    return material


def _full_control_grants(maintenance_sid: str) -> tuple[tuple[str, int], ...]:
    return (
        (SYSTEM_SID, win32file.FILE_ALL_ACCESS),
        (BUILTIN_ADMINISTRATORS_SID, win32file.FILE_ALL_ACCESS),
        (maintenance_sid, win32file.FILE_ALL_ACCESS),
    )


def _read_only_grants(
    *,
    maintenance_sid: str,
    runtime_sids: Iterable[str],
) -> tuple[tuple[str, int], ...]:
    return _ordered_grants(
        (
            *_full_control_grants(maintenance_sid),
            *((sid, DIRECTORY_READ_EXECUTE) for sid in runtime_sids),
        )
    )


def role_write_grants(
    *,
    maintenance_sid: str,
    role_sid: str,
) -> tuple[tuple[str, int], ...]:
    return _ordered_grants(
        (
            *_full_control_grants(maintenance_sid),
            (role_sid, DIRECTORY_MODIFY),
        )
    )


def runtime_log_acl_spec(
    repository_root: Path,
    settings: HalphaSettings,
    *,
    role: str,
) -> DirectoryAclSpec:
    if role == "app":
        role_sid = settings.windows.app_task_sid
    elif role == "executor":
        role_sid = settings.windows.executor_task_sid
    else:
        raise WindowsFilesystemError("WINDOWS_FILESYSTEM_LOG_ROLE_INVALID")
    return DirectoryAclSpec(
        label=f"{settings.release.environment_id}_{role}_logs",
        path=runtime_log_directory(
            repository_root,
            settings,
            role=role,
        ),
        owner_sid=settings.windows.maintenance_sid,
        grants=role_write_grants(
            maintenance_sid=settings.windows.maintenance_sid,
            role_sid=role_sid,
        ),
        create=True,
    )


def backup_acl_specs(
    repository_root: Path,
    settings: HalphaSettings,
) -> tuple[DirectoryAclSpec, ...]:
    root = repository_root.resolve()
    maintenance_sid = settings.windows.maintenance_sid
    backup_sid = settings.windows.backup_task_sid
    grants = role_write_grants(
        maintenance_sid=maintenance_sid,
        role_sid=backup_sid,
    )
    return (
        DirectoryAclSpec(
            label="backup_logs",
            path=backup_log_directory(root, settings),
            owner_sid=maintenance_sid,
            grants=grants,
            create=True,
        ),
        *(
            DirectoryAclSpec(
                label=f"{name}_backups",
                path=root / settings.maintenance.backup_root / name,
                owner_sid=maintenance_sid,
                grants=grants,
                create=True,
            )
            for name, _target in settings.maintenance.named_targets()
        ),
        DirectoryAclSpec(
            label="backup_temporary",
            path=root / settings.maintenance.temporary_root,
            owner_sid=maintenance_sid,
            grants=grants,
            create=True,
        ),
    )


def _require_compatible_settings(
    demo: HalphaSettings,
    live_copy: HalphaSettings,
    live_personal: HalphaSettings,
) -> None:
    contexts = (demo, live_copy, live_personal)
    expected_account_types = (
        VenueAccountType.USDM_DEMO,
        VenueAccountType.USDM_COPY_LEAD,
        VenueAccountType.USDM_PERSONAL,
    )
    if tuple(item.release.venue_account_type for item in contexts) != expected_account_types:
        raise WindowsFilesystemError("WINDOWS_FILESYSTEM_CONTEXT_SET_REQUIRED")
    if demo.release.profile != "BINANCE_DEMO" or any(
        item.release.profile not in {"BINANCE_LIVE_READ_ONLY", "BINANCE_LIVE_WRITE"}
        for item in (live_copy, live_personal)
    ):
        raise WindowsFilesystemError("WINDOWS_FILESYSTEM_PROFILE_SET_REQUIRED")
    if len({item.windows.maintenance_sid for item in contexts}) != 1 or len(
        {item.windows.backup_task_sid for item in contexts}
    ) != 1:
        raise WindowsFilesystemError(
            "WINDOWS_FILESYSTEM_SHARED_IDENTITY_MISMATCH"
        )
    if any(
        (
            item.maintenance.log_root,
            item.maintenance.backup_root,
            item.maintenance.temporary_root,
        )
        != (
            demo.maintenance.log_root,
            demo.maintenance.backup_root,
            demo.maintenance.temporary_root,
        )
        for item in contexts[1:]
    ):
        raise WindowsFilesystemError("WINDOWS_FILESYSTEM_RUNTIME_PATH_MISMATCH")
    identities = (
        demo.windows.maintenance_sid,
        demo.windows.backup_task_sid,
        *(item.windows.app_task_sid for item in contexts),
        *(item.windows.executor_task_sid for item in contexts),
    )
    if len(set(identities)) != len(identities):
        raise WindowsFilesystemError("WINDOWS_FILESYSTEM_IDENTITY_OVERLAP")


def runtime_filesystem_specs(
    repository_root: Path,
    demo: HalphaSettings,
    live_copy: HalphaSettings,
    live_personal: HalphaSettings,
) -> tuple[DirectoryAclSpec, ...]:
    """Return the complete, bounded filesystem ACL plan for one release root."""

    contexts = (demo, live_copy, live_personal)
    _require_compatible_settings(*contexts)
    root = repository_root.resolve()
    maintenance_sid = demo.windows.maintenance_sid
    backup_sid = demo.windows.backup_task_sid
    runtime_sids = (
        *(item.windows.app_task_sid for item in contexts),
        *(item.windows.executor_task_sid for item in contexts),
        backup_sid,
    )
    read_only = _read_only_grants(
        maintenance_sid=maintenance_sid,
        runtime_sids=runtime_sids,
    )
    static_boundaries = (
        ("repository", root),
        ("venv", root / ".venv"),
        ("source", root / "src"),
        ("configuration", root / "config"),
        ("frontend", root / "frontend"),
        ("migrations", root / "migrations"),
        ("requirements", root / "requirements"),
        ("build", root / "build"),
    )
    log_root = root / demo.maintenance.log_root
    backup_root = root / demo.maintenance.backup_root
    temporary_root = root / demo.maintenance.temporary_root
    protected_containers = (
        ("runtime_log_root", log_root),
        *(
            (
                f"{name}_log_environment",
                log_root / item.release.environment_id,
            )
            for name, item in zip(
                ("demo", "live_copy", "live_personal"),
                contexts,
                strict=True,
            )
        ),
        ("maintenance_log_root", log_root / "maintenance"),
        ("backup_parent", backup_root.parent),
        ("backup_root", backup_root),
        ("temporary_parent", temporary_root.parent),
    )
    return (
        *(
            DirectoryAclSpec(
                label=label,
                path=path,
                owner_sid=maintenance_sid,
                grants=read_only,
                create=False,
            )
            for label, path in static_boundaries
        ),
        *(
            DirectoryAclSpec(
                label=label,
                path=path,
                owner_sid=maintenance_sid,
                grants=read_only,
                create=True,
            )
            for label, path in protected_containers
        ),
        *(
            runtime_log_acl_spec(root, item, role=role)
            for item in contexts
            for role in ("app", "executor")
        ),
        *backup_acl_specs(root, demo),
    )


def _directory_dacl(spec: DirectoryAclSpec) -> win32security.ACL:
    dacl = win32security.ACL()
    for sid_text, mask in spec.grants:
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            DIRECTORY_INHERIT_FLAGS,
            mask,
            win32security.ConvertStringSidToSid(sid_text),
        )
    return dacl


@contextmanager
def _ownership_privileges():
    """Temporarily enable the admin privileges needed to replace stale owners."""

    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY,
    )
    previous = None
    try:
        privileges = [
            (
                win32security.LookupPrivilegeValue(None, name),
                win32con.SE_PRIVILEGE_ENABLED,
            )
            for name in (
                "SeTakeOwnershipPrivilege",
                "SeRestorePrivilege",
            )
        ]
        previous = win32security.AdjustTokenPrivileges(
            token,
            False,
            privileges,
        )
        yield
    finally:
        if previous is not None:
            win32security.AdjustTokenPrivileges(token, False, previous)
        token.Close()


def apply_directory_security(spec: DirectoryAclSpec) -> None:
    """Replace one directory boundary with its exact protected allow-list."""

    try:
        with _ownership_privileges():
            win32security.SetNamedSecurityInfo(
                str(spec.path),
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION,
                win32security.ConvertStringSidToSid(spec.owner_sid),
                None,
                None,
                None,
            )
            win32security.SetNamedSecurityInfo(
                str(spec.path),
                win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION
                | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                _directory_dacl(spec),
                None,
            )
    except pywintypes.error as exc:
        raise WindowsFilesystemError(
            "WINDOWS_FILESYSTEM_SECURITY_WRITE_FAILED "
            f"boundary={spec.label} code={exc.winerror}"
        ) from None


def assert_directory_security(spec: DirectoryAclSpec) -> None:
    """Require one exact owner, protected DACL, grant set, and inheritance shape."""

    try:
        descriptor = win32security.GetNamedSecurityInfo(
            str(spec.path),
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION,
        )
        owner = str(
            win32security.ConvertSidToStringSid(
                descriptor.GetSecurityDescriptorOwner()
            )
        )
        dacl = descriptor.GetSecurityDescriptorDacl()
        control, _revision = descriptor.GetSecurityDescriptorControl()
    except pywintypes.error as exc:
        raise WindowsFilesystemError(
            "WINDOWS_FILESYSTEM_SECURITY_READ_FAILED "
            f"boundary={spec.label} code={exc.winerror}"
        ) from None
    except Exception as exc:
        raise WindowsFilesystemError(
            "WINDOWS_FILESYSTEM_SECURITY_READ_FAILED "
            f"boundary={spec.label} type={type(exc).__name__}"
        ) from None
    if owner != spec.owner_sid:
        raise WindowsFilesystemError(
            f"WINDOWS_FILESYSTEM_OWNER_MISMATCH boundary={spec.label}"
        )
    if not control & win32security.SE_DACL_PROTECTED:
        raise WindowsFilesystemError(
            f"WINDOWS_FILESYSTEM_DACL_NOT_PROTECTED boundary={spec.label}"
        )
    expected = spec.grant_map()
    if dacl is None or dacl.GetAceCount() != len(expected):
        raise WindowsFilesystemError(
            f"WINDOWS_FILESYSTEM_DACL_COUNT_MISMATCH boundary={spec.label}"
        )
    actual: dict[str, int] = {}
    for index in range(dacl.GetAceCount()):
        ace = dacl.GetAce(index)
        if ace[0][0] != win32security.ACCESS_ALLOWED_ACE_TYPE:
            raise WindowsFilesystemError(
                f"WINDOWS_FILESYSTEM_DACL_ACE_TYPE_MISMATCH boundary={spec.label}"
            )
        if int(ace[0][1]) != DIRECTORY_INHERIT_FLAGS:
            raise WindowsFilesystemError(
                f"WINDOWS_FILESYSTEM_DACL_ACE_FLAGS_MISMATCH boundary={spec.label}"
            )
        sid = str(win32security.ConvertSidToStringSid(ace[2]))
        if sid in actual:
            raise WindowsFilesystemError(
                f"WINDOWS_FILESYSTEM_DACL_DUPLICATE_IDENTITY boundary={spec.label}"
            )
        actual[sid] = int(ace[1])
    if actual != expected:
        raise WindowsFilesystemError(
            f"WINDOWS_FILESYSTEM_DACL_GRANTS_MISMATCH boundary={spec.label}"
        )
