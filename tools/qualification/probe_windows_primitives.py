from __future__ import annotations

import json
import os
import sys
import uuid

import pywintypes
import win32api
import win32con
import win32event
import win32security
import winerror


def _current_user_sid():
    process = win32api.GetCurrentProcess()
    token = win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
    try:
        return win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()


def _protected_security_attributes(user_sid):
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAceEx(
        win32security.ACL_REVISION,
        0,
        win32event.EVENT_ALL_ACCESS,
        user_sid,
    )
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorOwner(user_sid, False)
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED,
        win32security.SE_DACL_PROTECTED,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.bInheritHandle = False
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes, descriptor


def main() -> int:
    errors: list[str] = []
    windows_version = sys.getwindowsversion()
    if (windows_version.major, windows_version.minor, windows_version.build) != (10, 0, 19045):
        errors.append("WINDOWS_BUILD_MISMATCH")
    if os.environ.get("PROCESSOR_ARCHITECTURE", "").upper() not in {"AMD64", "ARM64"}:
        errors.append("WINDOWS_ARCHITECTURE_MISMATCH")

    user_sid = _current_user_sid()
    sid_text = win32security.ConvertSidToStringSid(user_sid)
    security_attributes, descriptor = _protected_security_attributes(user_sid)
    control, _revision = descriptor.GetSecurityDescriptorControl()
    dacl = descriptor.GetSecurityDescriptorDacl()
    dacl_present = dacl is not None
    dacl_protected = bool(control & win32security.SE_DACL_PROTECTED)
    dacl_exact = (
        dacl_present
        and dacl is not None
        and dacl.GetAceCount() == 1
        and win32security.ConvertSidToStringSid(dacl.GetAce(0)[2]) == sid_text
    )
    if not dacl_protected:
        errors.append("DACL_NOT_PROTECTED")
    if not dacl_exact:
        errors.append("DACL_NOT_EXACT")

    suffix = uuid.uuid4().hex
    mutex_name = f"Global\\Halpha.B00.Mutex.{suffix}"
    event_name = f"Global\\Halpha.B00.Stop.{suffix}"
    mutex_first = mutex_second = stop_event = opened_event = None
    try:
        mutex_first = win32event.CreateMutex(security_attributes, False, mutex_name)
        first_already_exists = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        mutex_second = win32event.CreateMutex(security_attributes, False, mutex_name)
        second_already_exists = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        mutex_wait = win32event.WaitForSingleObject(mutex_first, 0)
        if mutex_wait == win32con.WAIT_OBJECT_0:
            win32event.ReleaseMutex(mutex_first)
        mutex_qualified = (
            not first_already_exists
            and second_already_exists
            and mutex_wait == win32con.WAIT_OBJECT_0
        )
        if not mutex_qualified:
            errors.append("GLOBAL_MUTEX_SEMANTICS_MISMATCH")

        stop_event = win32event.CreateEvent(security_attributes, True, False, event_name)
        initial_wait = win32event.WaitForSingleObject(stop_event, 0)
        opened_event = win32event.OpenEvent(
            win32event.EVENT_MODIFY_STATE | win32con.SYNCHRONIZE,
            False,
            event_name,
        )
        win32event.SetEvent(opened_event)
        signaled_wait = win32event.WaitForSingleObject(stop_event, 0)
        repeated_wait = win32event.WaitForSingleObject(stop_event, 0)
        win32event.ResetEvent(opened_event)
        reset_wait = win32event.WaitForSingleObject(stop_event, 0)
        event_qualified = (
            initial_wait == win32con.WAIT_TIMEOUT
            and signaled_wait == win32con.WAIT_OBJECT_0
            and repeated_wait == win32con.WAIT_OBJECT_0
            and reset_wait == win32con.WAIT_TIMEOUT
        )
        if not event_qualified:
            errors.append("MANUAL_RESET_EVENT_SEMANTICS_MISMATCH")
    except Exception as exc:  # pragma: no cover - evidence contains type only
        mutex_qualified = False
        event_qualified = False
        errors.append(f"WINDOWS_PRIMITIVE_FAILED:{type(exc).__name__}")
    finally:
        for handle in (opened_event, stop_event, mutex_second, mutex_first):
            if handle is not None:
                handle.Close()

    evidence = {
        "windows": {
            "major": windows_version.major,
            "minor": windows_version.minor,
            "build": windows_version.build,
            "platform": windows_version.platform,
        },
        "current_user_sid": sid_text,
        "protected_dacl": dacl_protected,
        "single_sid_ace": dacl_exact,
        "global_mutex": mutex_qualified,
        "manual_reset_initial_false_event": event_qualified,
        "errors": errors,
        "status": "QUALIFIED" if not errors else "REJECTED",
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
