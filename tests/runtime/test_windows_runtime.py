from __future__ import annotations

from uuid import uuid4

import pytest
import win32con
import win32event

from halpha.windows_runtime import (
    WindowsRuntimeError,
    acquire_executor_mutex,
    create_stop_event,
    current_process_sid,
    event_grants,
    mutex_grants,
    require_process_identity,
    signal_stop_event,
)


BUILTIN_USERS_SID = "S-1-5-32-545"


def _name(kind: str) -> str:
    return rf"Global\Halpha.Test.{kind}.{uuid4().hex}"


def test_current_process_identity_is_exact() -> None:
    sid = current_process_sid()
    assert sid.startswith("S-1-")
    require_process_identity(sid)
    with pytest.raises(WindowsRuntimeError, match="WINDOWS_PROCESS_IDENTITY_MISMATCH"):
        require_process_identity(BUILTIN_USERS_SID)


def test_rejects_duplicate_or_invalid_grant_identities() -> None:
    with pytest.raises(
        WindowsRuntimeError,
        match="WINDOWS_EVENT_IDENTITIES_MUST_BE_DISTINCT",
    ):
        event_grants("S-1-5-18", BUILTIN_USERS_SID)
    with pytest.raises(
        WindowsRuntimeError,
        match="WINDOWS_MUTEX_IDENTITIES_MUST_BE_DISTINCT",
    ):
        mutex_grants("S-1-5-18")


def test_maintenance_event_grant_can_signal_wait_and_verify_acl() -> None:
    grants = event_grants(current_process_sid(), BUILTIN_USERS_SID)
    assert grants[BUILTIN_USERS_SID] == (
        win32event.EVENT_MODIFY_STATE | win32con.SYNCHRONIZE | win32con.READ_CONTROL
    )


def test_stop_event_has_protected_acl_and_rejects_duplicate_creator() -> None:
    task_sid = current_process_sid()
    name = _name("Stop")
    with create_stop_event(
        name=name,
        task_sid=task_sid,
        maintenance_sid=BUILTIN_USERS_SID,
    ) as event:
        assert event.wait(0) == win32con.WAIT_TIMEOUT
        event.signal()
        assert event.wait(0) == win32con.WAIT_OBJECT_0
        with pytest.raises(
            WindowsRuntimeError,
            match="WINDOWS_STOP_EVENT_ALREADY_EXISTS",
        ):
            create_stop_event(
                name=name,
                task_sid=task_sid,
                maintenance_sid=BUILTIN_USERS_SID,
            )


def test_executor_mutex_rejects_second_instance() -> None:
    task_sid = current_process_sid()
    name = _name("Mutex")
    with acquire_executor_mutex(name=name, task_sid=task_sid):
        with pytest.raises(
            WindowsRuntimeError,
            match="WINDOWS_EXECUTOR_MUTEX_ALREADY_HELD",
        ):
            acquire_executor_mutex(name=name, task_sid=task_sid)
    with acquire_executor_mutex(name=name, task_sid=task_sid):
        pass


def test_stop_signal_fails_closed_for_wrong_maintenance_identity() -> None:
    task_sid = current_process_sid()
    with create_stop_event(
        name=_name("StopIdentity"),
        task_sid=task_sid,
        maintenance_sid=BUILTIN_USERS_SID,
    ):
        with pytest.raises(
            WindowsRuntimeError,
            match="WINDOWS_PROCESS_IDENTITY_MISMATCH",
        ):
            signal_stop_event(
                name=_name("NeverOpened"),
                task_sid=task_sid,
                maintenance_sid=BUILTIN_USERS_SID,
            )
