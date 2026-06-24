from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from halpha.runtime.pipeline_contracts import PipelineError
from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    STATE_STORE_REF,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_error_diagnostic,
    runtime_state_transaction,
)


MUTATION_LEASE_STAGE = "runtime_mutation_lease"
MUTATION_LEASE_NAME = "runtime-root-mutation"
MUTATION_LEASE_MIGRATION_VERSION = 14
MUTATING_WORKFLOW_KINDS = frozenset({"product_run", "stage_rerun", "monitor_cycle"})
LEASE_OWNER_ID_ENV = "HALPHA_MUTATION_LEASE_OWNER_ID"
LEASE_REQUESTED_BY_ENV = "HALPHA_MUTATION_LEASE_REQUESTED_BY"
LEASE_OWNER_KIND_ENV = "HALPHA_MUTATION_LEASE_OWNER_KIND"
LEASE_BLOCKED_MESSAGE = (
    "another mutating Halpha workflow is already running for this runtime root; retry after it finishes."
)
REQUESTED_BY_VALUES = frozenset({"CLI", "Dashboard", "Monitor", "Schedule"})
_ACTIVE_LEASE = threading.local()


MUTATION_LEASE_MIGRATIONS = (
    StateStoreMigration(
        version=MUTATION_LEASE_MIGRATION_VERSION,
        name="runtime_mutation_lease",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS runtime_mutation_lease (
              lease_name TEXT PRIMARY KEY,
              owner_id TEXT NOT NULL,
              owner_kind TEXT NOT NULL,
              workflow TEXT NOT NULL,
              requested_by TEXT NOT NULL,
              owner_pid INTEGER,
              acquired_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
)


class MutationLeaseBlocked(PipelineError):
    def __init__(self, owner: dict[str, Any]) -> None:
        super().__init__(
            LEASE_BLOCKED_MESSAGE,
            stage=MUTATION_LEASE_STAGE,
            exit_code=4,
            error_details={
                "status": "blocked",
                "stage": MUTATION_LEASE_STAGE,
                "message": LEASE_BLOCKED_MESSAGE,
                "database_ref": STATE_STORE_REF,
                "owner": _owner_diagnostic(owner),
                "private_values_embedded": False,
            },
        )


@dataclass
class MutationLease:
    config_path: Path
    owner_id: str
    owner_kind: str
    workflow: str
    requested_by: str
    owner_pid: int | None
    acquired_at: str
    reentrant: bool = False
    _released: bool = False
    _previous_context: dict[str, str] | None = None

    def __enter__(self) -> MutationLease:
        self._previous_context = _active_context()
        _set_active_context(
            {
                "owner_id": self.owner_id,
                "owner_kind": self.owner_kind,
                "workflow": self.workflow,
                "requested_by": self.requested_by,
            }
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        try:
            self.release()
        finally:
            _set_active_context(self._previous_context)
        return False

    def release(self) -> None:
        if self._released:
            return
        release_mutation_lease(config_path=self.config_path, owner_id=self.owner_id)
        self._released = True

    def subprocess_env(self, env: Mapping[str, str] | None = None) -> dict[str, str]:
        values = dict(env or os.environ)
        values[LEASE_OWNER_ID_ENV] = self.owner_id
        values[LEASE_REQUESTED_BY_ENV] = self.requested_by
        values[LEASE_OWNER_KIND_ENV] = self.owner_kind
        return values


def is_mutating_workflow_kind(kind: str) -> bool:
    return str(kind or "").strip() in MUTATING_WORKFLOW_KINDS


def mutation_lease(
    *,
    config_path: Path,
    owner_kind: str,
    workflow: str,
    requested_by: str = "CLI",
    owner_id: str | None = None,
    owner_pid: int | None = None,
) -> MutationLease:
    return acquire_mutation_lease(
        config_path=config_path,
        owner_kind=owner_kind,
        workflow=workflow,
        requested_by=requested_by,
        owner_id=owner_id,
        owner_pid=owner_pid,
    )


def acquire_mutation_lease(
    *,
    config_path: Path,
    owner_kind: str,
    workflow: str,
    requested_by: str = "CLI",
    owner_id: str | None = None,
    owner_pid: int | None = None,
) -> MutationLease:
    context = _active_context()
    resolved_owner_id = _resolved_owner_id(owner_id, context)
    resolved_owner_kind = _safe_label(owner_kind or context.get("owner_kind") or "workflow")
    resolved_workflow = _safe_label(workflow or context.get("workflow") or "workflow")
    resolved_requested_by = _requested_by(requested_by, context)
    resolved_owner_pid = int(owner_pid if owner_pid is not None else os.getpid())
    acquired_at = _utc_now()
    try:
        with closing(open_runtime_state_connection(config_path=config_path)) as connection:
            apply_runtime_state_migrations(
                connection,
                migrations=RUNTIME_STATE_MIGRATIONS + MUTATION_LEASE_MIGRATIONS,
                now=acquired_at,
            )
            with runtime_state_transaction(connection):
                row = connection.execute(
                    """
                    SELECT owner_id, owner_kind, workflow, requested_by, owner_pid, acquired_at, updated_at
                    FROM runtime_mutation_lease
                    WHERE lease_name = ?
                    """,
                    (MUTATION_LEASE_NAME,),
                ).fetchone()
                if row is not None:
                    owner = _row_to_owner(row)
                    if owner["owner_id"] == resolved_owner_id:
                        _update_lease(
                            connection,
                            owner_id=resolved_owner_id,
                            owner_kind=resolved_owner_kind,
                            workflow=resolved_workflow,
                            requested_by=resolved_requested_by,
                            owner_pid=resolved_owner_pid,
                            updated_at=acquired_at,
                        )
                        return MutationLease(
                            config_path=Path(config_path),
                            owner_id=resolved_owner_id,
                            owner_kind=resolved_owner_kind,
                            workflow=resolved_workflow,
                            requested_by=resolved_requested_by,
                            owner_pid=resolved_owner_pid,
                            acquired_at=str(owner.get("acquired_at") or acquired_at),
                            reentrant=True,
                        )
                    if _owner_alive(owner):
                        raise MutationLeaseBlocked(owner)
                    connection.execute("DELETE FROM runtime_mutation_lease WHERE lease_name = ?", (MUTATION_LEASE_NAME,))
                connection.execute(
                    """
                    INSERT INTO runtime_mutation_lease (
                      lease_name,
                      owner_id,
                      owner_kind,
                      workflow,
                      requested_by,
                      owner_pid,
                      acquired_at,
                      updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        MUTATION_LEASE_NAME,
                        resolved_owner_id,
                        resolved_owner_kind,
                        resolved_workflow,
                        resolved_requested_by,
                        resolved_owner_pid,
                        acquired_at,
                        acquired_at,
                    ),
                )
    except MutationLeaseBlocked:
        raise
    except sqlite3.Error as exc:
        raise PipelineError(
            "runtime mutation lease could not be acquired; inspect local state store and retry.",
            stage=MUTATION_LEASE_STAGE,
            exit_code=4,
            error_details=runtime_state_error_diagnostic(exc, operation="acquire runtime mutation lease"),
        ) from exc
    return MutationLease(
        config_path=Path(config_path),
        owner_id=resolved_owner_id,
        owner_kind=resolved_owner_kind,
        workflow=resolved_workflow,
        requested_by=resolved_requested_by,
        owner_pid=resolved_owner_pid,
        acquired_at=acquired_at,
    )


def release_mutation_lease(*, config_path: Path, owner_id: str) -> None:
    try:
        with closing(open_runtime_state_connection(config_path=config_path)) as connection:
            apply_runtime_state_migrations(
                connection,
                migrations=RUNTIME_STATE_MIGRATIONS + MUTATION_LEASE_MIGRATIONS,
            )
            with runtime_state_transaction(connection):
                connection.execute(
                    "DELETE FROM runtime_mutation_lease WHERE lease_name = ? AND owner_id = ?",
                    (MUTATION_LEASE_NAME, owner_id),
                )
    except sqlite3.Error:
        return


def _update_lease(
    connection: sqlite3.Connection,
    *,
    owner_id: str,
    owner_kind: str,
    workflow: str,
    requested_by: str,
    owner_pid: int,
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE runtime_mutation_lease
        SET owner_kind = ?,
            workflow = ?,
            requested_by = ?,
            owner_pid = ?,
            updated_at = ?
        WHERE lease_name = ? AND owner_id = ?
        """,
        (owner_kind, workflow, requested_by, owner_pid, updated_at, MUTATION_LEASE_NAME, owner_id),
    )


def _owner_alive(owner: dict[str, Any]) -> bool:
    pid = owner.get("owner_pid")
    if not isinstance(pid, int) or pid <= 0:
        return True
    return _pid_is_alive(pid)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_pid_is_alive(pid)
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_pid_is_alive(pid: int) -> bool:
    try:
        import ctypes
    except ImportError:
        return False

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _row_to_owner(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "owner_id": str(row[0] or ""),
        "owner_kind": str(row[1] or "workflow"),
        "workflow": str(row[2] or "workflow"),
        "requested_by": str(row[3] or "CLI"),
        "owner_pid": int(row[4]) if row[4] is not None else None,
        "acquired_at": str(row[5] or ""),
        "updated_at": str(row[6] or ""),
    }


def _owner_diagnostic(owner: dict[str, Any]) -> dict[str, Any]:
    return {
        "owner_kind": _safe_label(str(owner.get("owner_kind") or "workflow")),
        "workflow": _safe_label(str(owner.get("workflow") or "workflow")),
        "requested_by": _requested_by(owner.get("requested_by"), {}),
        "owner_pid": owner.get("owner_pid") if isinstance(owner.get("owner_pid"), int) else None,
        "acquired_at": str(owner.get("acquired_at") or ""),
        "updated_at": str(owner.get("updated_at") or ""),
    }


def _resolved_owner_id(owner_id: str | None, context: dict[str, str]) -> str:
    value = str(owner_id or context.get("owner_id") or os.environ.get(LEASE_OWNER_ID_ENV) or "").strip()
    if value:
        return _safe_label(value, fallback=f"owner-{uuid4().hex}")
    return f"owner-{uuid4().hex}"


def _requested_by(value: Any, context: dict[str, str]) -> str:
    env_value = os.environ.get(LEASE_REQUESTED_BY_ENV)
    candidate = str(value or "").strip()
    if env_value in REQUESTED_BY_VALUES:
        return env_value
    if candidate in REQUESTED_BY_VALUES:
        return candidate
    context_value = context.get("requested_by")
    if context_value in REQUESTED_BY_VALUES:
        return context_value
    return "CLI"


def _safe_label(value: str, *, fallback: str = "workflow") -> str:
    text = str(value or "").strip()
    allowed = []
    for char in text[:120]:
        if char.isalnum() or char in {"-", "_", ".", ":"}:
            allowed.append(char)
    safe = "".join(allowed).strip("._:-")
    return safe or fallback


def _active_context() -> dict[str, str]:
    value = getattr(_ACTIVE_LEASE, "context", None)
    return dict(value) if isinstance(value, dict) else {}


def _set_active_context(value: dict[str, str] | None) -> None:
    if value:
        _ACTIVE_LEASE.context = dict(value)
    elif hasattr(_ACTIVE_LEASE, "context"):
        delattr(_ACTIVE_LEASE, "context")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
