"""Exact Windows named-object boundaries for the two-process runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pywintypes
import win32api
import win32con
import win32event
import win32security
import winerror


SYSTEM_SID = "S-1-5-18"
BUILTIN_ADMINISTRATORS_SID = "S-1-5-32-544"
MUTEX_ALL_ACCESS = 0x001F0001


class WindowsRuntimeError(RuntimeError):
    """Sanitized fail-closed Windows lifecycle error."""


def current_process_sid() -> str:
    process = win32api.GetCurrentProcess()
    token = win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return str(win32security.ConvertSidToStringSid(sid))
    finally:
        token.Close()


def require_process_identity(expected_sid: str) -> None:
    actual = current_process_sid()
    if actual != expected_sid:
        raise WindowsRuntimeError(
            f"WINDOWS_PROCESS_IDENTITY_MISMATCH expected={expected_sid} actual={actual}"
        )


def _sid(value: str) -> Any:
    try:
        sid = win32security.ConvertStringSidToSid(value)
    except Exception:
        raise WindowsRuntimeError(f"WINDOWS_SID_RESOLUTION_FAILED sid={value}") from None
    if not sid.IsValid():
        raise WindowsRuntimeError(f"WINDOWS_SID_INVALID sid={value}")
    return sid


def _security_attributes(
    *,
    owner_sid: str,
    grants: dict[str, int],
) -> pywintypes.SECURITY_ATTRIBUTES:
    if len(grants) != len(set(grants)) or owner_sid not in grants:
        raise WindowsRuntimeError("WINDOWS_NAMED_OBJECT_GRANT_SET_INVALID")
    dacl = win32security.ACL()
    for sid_text, mask in grants.items():
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            0,
            mask,
            _sid(sid_text),
        )
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorOwner(_sid(owner_sid), False)
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED,
        win32security.SE_DACL_PROTECTED,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.bInheritHandle = False
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes


def event_grants(task_sid: str, maintenance_sid: str) -> dict[str, int]:
    identities = (SYSTEM_SID, BUILTIN_ADMINISTRATORS_SID, task_sid, maintenance_sid)
    if len(set(identities)) != len(identities):
        raise WindowsRuntimeError("WINDOWS_EVENT_IDENTITIES_MUST_BE_DISTINCT")
    return {
        SYSTEM_SID: win32event.EVENT_ALL_ACCESS,
        BUILTIN_ADMINISTRATORS_SID: win32event.EVENT_ALL_ACCESS,
        task_sid: win32event.EVENT_ALL_ACCESS,
        maintenance_sid: (
            win32event.EVENT_MODIFY_STATE
            | win32con.SYNCHRONIZE
            | win32con.READ_CONTROL
        ),
    }


def mutex_grants(task_sid: str) -> dict[str, int]:
    identities = (SYSTEM_SID, BUILTIN_ADMINISTRATORS_SID, task_sid)
    if len(set(identities)) != len(identities):
        raise WindowsRuntimeError("WINDOWS_MUTEX_IDENTITIES_MUST_BE_DISTINCT")
    return {
        SYSTEM_SID: MUTEX_ALL_ACCESS,
        BUILTIN_ADMINISTRATORS_SID: MUTEX_ALL_ACCESS,
        task_sid: MUTEX_ALL_ACCESS,
    }


def assert_kernel_object_security(
    handle: Any,
    *,
    owner_sid: str,
    grants: dict[str, int],
) -> None:
    try:
        descriptor = win32security.GetSecurityInfo(
            handle,
            win32security.SE_KERNEL_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION,
        )
        actual_owner = win32security.ConvertSidToStringSid(
            descriptor.GetSecurityDescriptorOwner()
        )
        dacl = descriptor.GetSecurityDescriptorDacl()
        control, _revision = descriptor.GetSecurityDescriptorControl()
    except Exception as exc:
        raise WindowsRuntimeError(
            f"WINDOWS_NAMED_OBJECT_SECURITY_READ_FAILED type={type(exc).__name__}"
        ) from None
    if actual_owner != owner_sid:
        raise WindowsRuntimeError("WINDOWS_NAMED_OBJECT_OWNER_MISMATCH")
    if not control & win32security.SE_DACL_PROTECTED:
        raise WindowsRuntimeError("WINDOWS_NAMED_OBJECT_DACL_NOT_PROTECTED")
    if dacl is None or dacl.GetAceCount() != len(grants):
        raise WindowsRuntimeError("WINDOWS_NAMED_OBJECT_DACL_COUNT_MISMATCH")
    actual: dict[str, int] = {}
    for index in range(dacl.GetAceCount()):
        ace = dacl.GetAce(index)
        ace_type = ace[0][0]
        if ace_type != win32security.ACCESS_ALLOWED_ACE_TYPE:
            raise WindowsRuntimeError("WINDOWS_NAMED_OBJECT_DACL_ACE_TYPE_MISMATCH")
        actual[str(win32security.ConvertSidToStringSid(ace[2]))] = int(ace[1])
    if actual != grants:
        raise WindowsRuntimeError("WINDOWS_NAMED_OBJECT_DACL_GRANTS_MISMATCH")


@dataclass
class NamedStopEvent:
    handle: Any

    def wait(self, timeout_ms: int = win32event.INFINITE) -> int:
        return int(win32event.WaitForSingleObject(self.handle, timeout_ms))

    def signal(self) -> None:
        win32event.SetEvent(self.handle)

    def close(self) -> None:
        self.handle.Close()

    def __enter__(self) -> "NamedStopEvent":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def create_stop_event(
    *,
    name: str,
    task_sid: str,
    maintenance_sid: str,
) -> NamedStopEvent:
    require_process_identity(task_sid)
    grants = event_grants(task_sid, maintenance_sid)
    attributes = _security_attributes(owner_sid=task_sid, grants=grants)
    try:
        handle = win32event.CreateEvent(attributes, True, False, name)
        already_exists = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
    except Exception as exc:
        raise WindowsRuntimeError(
            f"WINDOWS_STOP_EVENT_CREATE_FAILED type={type(exc).__name__}"
        ) from None
    if already_exists:
        handle.Close()
        raise WindowsRuntimeError("WINDOWS_STOP_EVENT_ALREADY_EXISTS")
    try:
        assert_kernel_object_security(handle, owner_sid=task_sid, grants=grants)
        if win32event.WaitForSingleObject(handle, 0) != win32con.WAIT_TIMEOUT:
            raise WindowsRuntimeError("WINDOWS_STOP_EVENT_NOT_INITIAL_FALSE")
    except Exception:
        handle.Close()
        raise
    return NamedStopEvent(handle)


@dataclass
class ExecutorWriteMutex:
    handle: Any
    owned: bool = True

    def close(self) -> None:
        if self.owned:
            win32event.ReleaseMutex(self.handle)
            self.owned = False
        self.handle.Close()

    def __enter__(self) -> "ExecutorWriteMutex":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def acquire_executor_mutex(*, name: str, task_sid: str) -> ExecutorWriteMutex:
    require_process_identity(task_sid)
    grants = mutex_grants(task_sid)
    attributes = _security_attributes(owner_sid=task_sid, grants=grants)
    try:
        handle = win32event.CreateMutex(attributes, True, name)
        already_exists = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
    except Exception as exc:
        raise WindowsRuntimeError(
            f"WINDOWS_EXECUTOR_MUTEX_CREATE_FAILED type={type(exc).__name__}"
        ) from None
    if already_exists:
        handle.Close()
        raise WindowsRuntimeError("WINDOWS_EXECUTOR_MUTEX_ALREADY_HELD")
    try:
        assert_kernel_object_security(handle, owner_sid=task_sid, grants=grants)
    except Exception:
        win32event.ReleaseMutex(handle)
        handle.Close()
        raise
    return ExecutorWriteMutex(handle)


def signal_stop_event(
    *,
    name: str,
    task_sid: str,
    maintenance_sid: str,
) -> None:
    require_process_identity(maintenance_sid)
    grants = event_grants(task_sid, maintenance_sid)
    try:
        handle = win32event.OpenEvent(
            win32event.EVENT_MODIFY_STATE
            | win32con.SYNCHRONIZE
            | win32con.READ_CONTROL,
            False,
            name,
        )
    except pywintypes.error as exc:
        if exc.winerror == winerror.ERROR_FILE_NOT_FOUND:
            raise WindowsRuntimeError("WINDOWS_STOP_EVENT_NOT_RUNNING") from None
        raise WindowsRuntimeError(
            f"WINDOWS_STOP_EVENT_OPEN_FAILED code={exc.winerror}"
        ) from None
    try:
        assert_kernel_object_security(handle, owner_sid=task_sid, grants=grants)
        win32event.SetEvent(handle)
    finally:
        handle.Close()
