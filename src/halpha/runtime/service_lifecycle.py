from __future__ import annotations

from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    STATE_STORE_REF,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_path,
    runtime_state_transaction,
)
from halpha.storage import display_path


SERVICE_LIFECYCLE_ARTIFACT = STATE_STORE_REF
SERVICE_LIFECYCLE_SCHEMA_VERSION = 1
SERVICE_LIFECYCLE_MIGRATION_VERSION = 7
SERVICE_EVENT_LIMIT = 50
SERVICE_ROLES = frozenset({"dashboard", "monitor", "schedule"})
RUNNING_STATUSES = {"starting", "running", "stop_requested"}
TERMINAL_STATUSES = {"stopped", "failed", "crashed"}
ServiceRole = Literal["dashboard", "monitor", "schedule"]
_PROCESS_LOCKS_GUARD = Lock()
_PROCESS_LOCKS: set[Path] = set()


class ServiceLifecycleError(Exception):
    pass


@dataclass(frozen=True)
class ServiceLifecycleResult:
    status: str
    role: ServiceRole
    instance_id: str | None = None
    owns_lock: bool = False
    state: dict[str, Any] | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ServiceStopRequest:
    status: str
    role: ServiceRole
    instance_id: str
    requested: bool
    requested_at: str | None = None


class ServiceOwnership:
    def __init__(self, *, role: ServiceRole, instance_id: str, lock: "_RoleLock") -> None:
        self.role = role
        self.instance_id = instance_id
        self._lock = lock

    def release(self) -> None:
        self._lock.release()

    def __enter__(self) -> "ServiceOwnership":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.release()
        return False


SERVICE_LIFECYCLE_MIGRATIONS = (
    StateStoreMigration(
        version=SERVICE_LIFECYCLE_MIGRATION_VERSION,
        name="resident_service_lifecycle",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS resident_services (
              role TEXT PRIMARY KEY,
              instance_id TEXT,
              pid INTEGER,
              config_ref TEXT,
              config_digest TEXT,
              status TEXT NOT NULL,
              started_at TEXT,
              updated_at TEXT NOT NULL,
              heartbeat_at TEXT,
              heartbeat_timeout_seconds INTEGER NOT NULL,
              stop_requested_at TEXT,
              stop_requested_by_instance_id TEXT,
              endpoint_json TEXT NOT NULL,
              exit_code INTEGER,
              terminal_at TEXT,
              last_error_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS resident_service_events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              role TEXT NOT NULL,
              instance_id TEXT,
              event_type TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              details_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_resident_service_events_role ON resident_service_events(role, event_id)",
        ),
    ),
)


def apply_service_lifecycle_migrations(connection: sqlite3.Connection, *, now: datetime | str | None = None) -> None:
    apply_runtime_state_migrations(
        connection,
        migrations=RUNTIME_STATE_MIGRATIONS + SERVICE_LIFECYCLE_MIGRATIONS,
        now=now,
    )


class ServiceLifecycleRepository:
    def __init__(
        self,
        *,
        config_path: Path | None = None,
        runtime_root: Path | None = None,
        heartbeat_timeout_seconds: int = 30,
    ) -> None:
        if heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds must be positive.")
        self.config_path = config_path
        self.runtime_root = runtime_root
        self.database_path = runtime_state_path(runtime_root=runtime_root, config_path=config_path)
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds

    def inspect(self, role: str, *, now: datetime | str | None = None) -> ServiceLifecycleResult:
        role_id = _role(role)
        with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
            apply_service_lifecycle_migrations(connection, now=now)
            state = _service_state(connection, role_id)
        lock_probe = _RoleLock(self._lock_path(role_id))
        lock_free = lock_probe.acquire()
        lock_probe.release()
        return _inspection_result(role_id, state=state, lock_free=lock_free, now=now)

    def attempt_start_ownership(
        self,
        role: str,
        *,
        config_ref: str,
        config_digest: str,
        endpoint: dict[str, Any] | None = None,
        pid: int | None = None,
        now: datetime | str | None = None,
    ) -> tuple[ServiceLifecycleResult, ServiceOwnership | None]:
        role_id = _role(role)
        timestamp = _format_utc(now)
        lock = _RoleLock(self._lock_path(role_id))
        if not lock.acquire():
            with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
                apply_service_lifecycle_migrations(connection, now=timestamp)
                state = _service_state(connection, role_id)
            return _held_lock_result(
                role_id,
                state=state,
                config_digest=config_digest,
                now=timestamp,
            ), None

        try:
            with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
                apply_service_lifecycle_migrations(connection, now=timestamp)
                previous = _service_state(connection, role_id)
            blocking_result = _terminal_start_result(role_id, previous) or _same_process_running_result(
                role_id,
                state=previous,
                config_digest=config_digest,
                now=timestamp,
            )
            if blocking_result is not None:
                lock.release()
                return blocking_result, None

            instance_id = _instance_id(role_id)
            ownership = ServiceOwnership(role=role_id, instance_id=instance_id, lock=lock)
            status = "acquired"
            with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
                apply_service_lifecycle_migrations(connection, now=timestamp)
                with runtime_state_transaction(connection):
                    previous = _service_state(connection, role_id)
                    blocking_result = _terminal_start_result(role_id, previous)
                    if blocking_result is not None:
                        lock.release()
                        return blocking_result, None
                    if previous and previous.get("status") in RUNNING_STATUSES:
                        _record_event(
                            connection,
                            role=role_id,
                            instance_id=str(previous.get("instance_id") or ""),
                            event_type="reconcile_stale",
                            status="crashed",
                            created_at=timestamp,
                            details={"reason": "lock was free while persisted service state was running."},
                        )
                        status = "acquired_after_reconcile"
                    state = _starting_state(
                        role_id,
                        instance_id=instance_id,
                        pid=pid or os.getpid(),
                        config_ref=config_ref,
                        config_digest=config_digest,
                        endpoint=endpoint or {},
                        now=timestamp,
                        heartbeat_timeout_seconds=self.heartbeat_timeout_seconds,
                    )
                    _replace_service_state(connection, state)
                    _record_event(
                        connection,
                        role=role_id,
                        instance_id=instance_id,
                        event_type="ownership_acquired",
                        status="starting",
                        created_at=timestamp,
                        details={"config_digest": config_digest},
                    )
                    _trim_events(connection, role_id)
        except Exception:
            lock.release()
            raise
        return ServiceLifecycleResult(status=status, role=role_id, instance_id=instance_id, owns_lock=True, state=state), ownership

    def attempt_restart_ownership(
        self,
        role: str,
        *,
        previous_instance_id: str,
        config_ref: str,
        config_digest: str,
        endpoint: dict[str, Any] | None = None,
        pid: int | None = None,
        now: datetime | str | None = None,
    ) -> tuple[ServiceLifecycleResult, ServiceOwnership | None]:
        role_id = _role(role)
        timestamp = _format_utc(now)
        lock = _RoleLock(self._lock_path(role_id))
        if not lock.acquire():
            with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
                apply_service_lifecycle_migrations(connection, now=timestamp)
                state = _service_state(connection, role_id)
            return _held_lock_result(
                role_id,
                state=state,
                config_digest=config_digest,
                now=timestamp,
            ), None

        try:
            with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
                apply_service_lifecycle_migrations(connection, now=timestamp)
                previous = _service_state(connection, role_id)
            blocking_result = _restart_blocking_result(
                role_id,
                state=previous,
                previous_instance_id=previous_instance_id,
            )
            if blocking_result is not None:
                lock.release()
                return blocking_result, None

            instance_id = _instance_id(role_id)
            ownership = ServiceOwnership(role=role_id, instance_id=instance_id, lock=lock)
            with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
                apply_service_lifecycle_migrations(connection, now=timestamp)
                with runtime_state_transaction(connection):
                    previous = _service_state(connection, role_id)
                    blocking_result = _restart_blocking_result(
                        role_id,
                        state=previous,
                        previous_instance_id=previous_instance_id,
                    )
                    if blocking_result is not None:
                        lock.release()
                        return blocking_result, None
                    previous_status = str(previous.get("status") or "unknown") if previous else "unknown"
                    state = _starting_state(
                        role_id,
                        instance_id=instance_id,
                        pid=pid or os.getpid(),
                        config_ref=config_ref,
                        config_digest=config_digest,
                        endpoint=endpoint or {},
                        now=timestamp,
                        heartbeat_timeout_seconds=self.heartbeat_timeout_seconds,
                    )
                    _replace_service_state(connection, state)
                    _record_event(
                        connection,
                        role=role_id,
                        instance_id=instance_id,
                        event_type="restart_ownership_acquired",
                        status="starting",
                        created_at=timestamp,
                        details={
                            "config_digest": config_digest,
                            "previous_instance_id": previous_instance_id,
                            "previous_status": previous_status,
                        },
                    )
                    _trim_events(connection, role_id)
        except Exception:
            lock.release()
            raise
        return ServiceLifecycleResult(status="restart_acquired", role=role_id, instance_id=instance_id, owns_lock=True, state=state), ownership

    def register_started(
        self,
        role: str,
        *,
        instance_id: str,
        endpoint: dict[str, Any] | None = None,
        now: datetime | str | None = None,
    ) -> ServiceLifecycleResult:
        role_id = _role(role)
        timestamp = _format_utc(now)
        with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
            apply_service_lifecycle_migrations(connection, now=timestamp)
            with runtime_state_transaction(connection):
                state = _require_matching_state(connection, role_id, instance_id)
                state["status"] = "running"
                state["updated_at"] = timestamp
                state["heartbeat_at"] = timestamp
                if endpoint is not None:
                    state["endpoint"] = _safe_endpoint(endpoint)
                _replace_service_state(connection, state)
                _record_event(connection, role=role_id, instance_id=instance_id, event_type="started", status="running", created_at=timestamp)
                _trim_events(connection, role_id)
        return ServiceLifecycleResult(status="running", role=role_id, instance_id=instance_id, owns_lock=False, state=state)

    def update_heartbeat(
        self,
        role: str,
        *,
        instance_id: str,
        now: datetime | str | None = None,
    ) -> ServiceLifecycleResult:
        role_id = _role(role)
        timestamp = _format_utc(now)
        with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
            apply_service_lifecycle_migrations(connection, now=timestamp)
            with runtime_state_transaction(connection):
                state = _require_matching_state(connection, role_id, instance_id)
                state["heartbeat_at"] = timestamp
                state["updated_at"] = timestamp
                _replace_service_state(connection, state)
        return ServiceLifecycleResult(status="heartbeat_recorded", role=role_id, instance_id=instance_id, state=state)

    def request_graceful_stop(
        self,
        role: str,
        *,
        instance_id: str,
        now: datetime | str | None = None,
    ) -> ServiceLifecycleResult:
        role_id = _role(role)
        timestamp = _format_utc(now)
        with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
            apply_service_lifecycle_migrations(connection, now=timestamp)
            with runtime_state_transaction(connection):
                state = _service_state(connection, role_id)
                if not state:
                    return ServiceLifecycleResult(status="not_found", role=role_id, reason="service state was not found.")
                if state.get("instance_id") != instance_id:
                    return ServiceLifecycleResult(
                        status="instance_mismatch",
                        role=role_id,
                        instance_id=str(state.get("instance_id") or ""),
                        state=state,
                        reason="stop request instance id does not match the current service instance.",
                    )
                state["status"] = "stop_requested"
                state["stop_requested_at"] = timestamp
                state["stop_requested_by_instance_id"] = instance_id
                state["updated_at"] = timestamp
                _replace_service_state(connection, state)
                _record_event(connection, role=role_id, instance_id=instance_id, event_type="stop_requested", status="stop_requested", created_at=timestamp)
                _trim_events(connection, role_id)
        return ServiceLifecycleResult(status="stop_requested", role=role_id, instance_id=instance_id, state=state)

    def observe_stop_request(self, role: str, *, instance_id: str) -> ServiceStopRequest:
        role_id = _role(role)
        with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
            apply_service_lifecycle_migrations(connection)
            state = _service_state(connection, role_id)
        requested = bool(
            state
            and state.get("instance_id") == instance_id
            and state.get("status") == "stop_requested"
            and state.get("stop_requested_by_instance_id") == instance_id
        )
        return ServiceStopRequest(
            status="stop_requested" if requested else "not_requested",
            role=role_id,
            instance_id=instance_id,
            requested=requested,
            requested_at=str(state.get("stop_requested_at")) if requested and state else None,
        )

    def record_terminal_exit(
        self,
        role: str,
        *,
        instance_id: str,
        status: str,
        exit_code: int | None = None,
        error: str | None = None,
        now: datetime | str | None = None,
    ) -> ServiceLifecycleResult:
        role_id = _role(role)
        if status not in TERMINAL_STATUSES:
            raise ValueError("terminal service status must be stopped, failed, or crashed.")
        timestamp = _format_utc(now)
        with closing(open_runtime_state_connection(runtime_root=self.runtime_root, config_path=self.config_path)) as connection:
            apply_service_lifecycle_migrations(connection, now=timestamp)
            with runtime_state_transaction(connection):
                state = _require_matching_state(connection, role_id, instance_id)
                state["status"] = status
                state["exit_code"] = exit_code
                state["terminal_at"] = timestamp
                state["updated_at"] = timestamp
                state["last_error"] = _last_error(error)
                _replace_service_state(connection, state)
                _record_event(
                    connection,
                    role=role_id,
                    instance_id=instance_id,
                    event_type="terminal_exit",
                    status=status,
                    created_at=timestamp,
                    details={"exit_code": exit_code, "has_error": bool(error)},
                )
                _trim_events(connection, role_id)
        return ServiceLifecycleResult(status=status, role=role_id, instance_id=instance_id, state=state)

    def _lock_path(self, role: ServiceRole) -> Path:
        root = self.database_path.parent
        return root / "service_locks" / f"{role}.lock"


class _RoleLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._registry_key = path.resolve()
        self._handle = None
        self.acquired = False

    def acquire(self) -> bool:
        if self.acquired:
            return True
        with _PROCESS_LOCKS_GUARD:
            if self._registry_key in _PROCESS_LOCKS:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b")
            try:
                _ensure_lock_byte(handle)
            except OSError:
                handle.close()
                return False
            try:
                if sys.platform == "win32":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                handle.close()
                return False
            self._handle = handle
            self.acquired = True
            _PROCESS_LOCKS.add(self._registry_key)
            return True

    def release(self) -> None:
        with _PROCESS_LOCKS_GUARD:
            if self._handle is None:
                return
            with suppress(OSError):
                if sys.platform == "win32":
                    import msvcrt

                    self._handle.seek(0)
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            with suppress(OSError):
                self._handle.close()
            _PROCESS_LOCKS.discard(self._registry_key)
            self._handle = None
            self.acquired = False


def _role(role: str) -> ServiceRole:
    value = str(role)
    if value not in SERVICE_ROLES:
        supported = ", ".join(sorted(SERVICE_ROLES))
        raise ValueError(f"service role must be one of: {supported}.")
    return value  # type: ignore[return-value]


def _starting_state(
    role: ServiceRole,
    *,
    instance_id: str,
    pid: int,
    config_ref: str,
    config_digest: str,
    endpoint: dict[str, Any],
    now: str,
    heartbeat_timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "role": role,
        "instance_id": instance_id,
        "pid": int(pid),
        "config_ref": _safe_config_ref(config_ref),
        "config_digest": str(config_digest),
        "status": "starting",
        "started_at": now,
        "updated_at": now,
        "heartbeat_at": now,
        "heartbeat_timeout_seconds": int(heartbeat_timeout_seconds),
        "stop_requested_at": None,
        "stop_requested_by_instance_id": None,
        "endpoint": _safe_endpoint(endpoint),
        "exit_code": None,
        "terminal_at": None,
        "last_error": {},
    }


def _held_lock_result(
    role: ServiceRole,
    *,
    state: dict[str, Any] | None,
    config_digest: str,
    now: datetime | str | None,
) -> ServiceLifecycleResult:
    if not state:
        return ServiceLifecycleResult(status="starting", role=role, reason="service lock is held but lifecycle state is not registered yet.")
    status = str(state.get("status") or "unknown")
    if status in RUNNING_STATUSES:
        if _heartbeat_is_stale(state, now=now):
            return ServiceLifecycleResult(
                status="unresponsive",
                role=role,
                instance_id=_state_instance_id(state),
                state=state,
                reason="service lock is held but heartbeat is stale.",
            )
    if status in {"starting", "stop_requested"}:
        return ServiceLifecycleResult(status=status, role=role, instance_id=_state_instance_id(state), state=state)
    if status == "running":
        if state.get("config_digest") == config_digest:
            return ServiceLifecycleResult(status="existing", role=role, instance_id=_state_instance_id(state), state=state)
        return ServiceLifecycleResult(
            status="conflict",
            role=role,
            instance_id=_state_instance_id(state),
            state=state,
            reason="service is already running with a different config digest.",
        )
    return ServiceLifecycleResult(status="locked", role=role, instance_id=_state_instance_id(state), state=state)


def _terminal_start_result(role: ServiceRole, state: dict[str, Any] | None) -> ServiceLifecycleResult | None:
    if not state:
        return None
    status = str(state.get("status") or "unknown")
    if status not in TERMINAL_STATUSES:
        return None
    return ServiceLifecycleResult(
        status=status,
        role=role,
        instance_id=_state_instance_id(state),
        state=state,
        reason="service is in a terminal state; use explicit restart after confirming the instance id.",
    )


def _restart_blocking_result(
    role: ServiceRole,
    *,
    state: dict[str, Any] | None,
    previous_instance_id: str,
) -> ServiceLifecycleResult | None:
    if not state:
        return ServiceLifecycleResult(status="not_found", role=role, reason="restart requires a confirmed terminal service state.")
    current_instance_id = _state_instance_id(state)
    if current_instance_id != previous_instance_id:
        return ServiceLifecycleResult(
            status="instance_mismatch",
            role=role,
            instance_id=current_instance_id,
            state=state,
            reason="restart instance id does not match the current service state.",
        )
    status = str(state.get("status") or "unknown")
    if status not in TERMINAL_STATUSES:
        return ServiceLifecycleResult(
            status=status,
            role=role,
            instance_id=current_instance_id,
            state=state,
            reason="restart requires a stopped, failed, or crashed terminal state.",
        )
    return None


def _same_process_running_result(
    role: ServiceRole,
    *,
    state: dict[str, Any] | None,
    config_digest: str,
    now: datetime | str | None,
) -> ServiceLifecycleResult | None:
    if not state or not _state_pid_is_current_process(state) or _heartbeat_is_stale(state, now=now):
        return None
    status = str(state.get("status") or "unknown")
    if status in {"starting", "stop_requested"}:
        return ServiceLifecycleResult(status=status, role=role, instance_id=_state_instance_id(state), state=state)
    if status == "running":
        if state.get("config_digest") == config_digest:
            return ServiceLifecycleResult(status="existing", role=role, instance_id=_state_instance_id(state), state=state)
        return ServiceLifecycleResult(
            status="conflict",
            role=role,
            instance_id=_state_instance_id(state),
            state=state,
            reason="service is already running with a different config digest.",
        )
    return None


def _inspection_result(
    role: ServiceRole,
    *,
    state: dict[str, Any] | None,
    lock_free: bool,
    now: datetime | str | None,
) -> ServiceLifecycleResult:
    if not state:
        return ServiceLifecycleResult(status="not_found", role=role, reason="service state was not found.")
    status = str(state.get("status") or "unknown")
    if status in RUNNING_STATUSES and lock_free and _state_pid_is_current_process(state) and not _heartbeat_is_stale(state, now=now):
        return ServiceLifecycleResult(status=status, role=role, instance_id=_state_instance_id(state), state=state)
    if status in RUNNING_STATUSES and lock_free:
        return ServiceLifecycleResult(status="stale", role=role, instance_id=_state_instance_id(state), state=state, reason="service lock is free.")
    if status in RUNNING_STATUSES and not lock_free and _heartbeat_is_stale(state, now=now):
        return ServiceLifecycleResult(status="unresponsive", role=role, instance_id=_state_instance_id(state), state=state)
    if status in RUNNING_STATUSES and not lock_free:
        return ServiceLifecycleResult(status=status, role=role, instance_id=_state_instance_id(state), state=state)
    return ServiceLifecycleResult(status=status, role=role, instance_id=_state_instance_id(state), state=state)


def _replace_service_state(connection: sqlite3.Connection, state: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO resident_services (
          role,
          instance_id,
          pid,
          config_ref,
          config_digest,
          status,
          started_at,
          updated_at,
          heartbeat_at,
          heartbeat_timeout_seconds,
          stop_requested_at,
          stop_requested_by_instance_id,
          endpoint_json,
          exit_code,
          terminal_at,
          last_error_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state["role"],
            state.get("instance_id"),
            state.get("pid"),
            state.get("config_ref"),
            state.get("config_digest"),
            state["status"],
            state.get("started_at"),
            state["updated_at"],
            state.get("heartbeat_at"),
            int(state.get("heartbeat_timeout_seconds") or 0),
            state.get("stop_requested_at"),
            state.get("stop_requested_by_instance_id"),
            _dumps(state.get("endpoint") or {}),
            state.get("exit_code"),
            state.get("terminal_at"),
            _dumps(state.get("last_error") or {}),
        ),
    )


def _service_state(connection: sqlite3.Connection, role: ServiceRole) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
          role,
          instance_id,
          pid,
          config_ref,
          config_digest,
          status,
          started_at,
          updated_at,
          heartbeat_at,
          heartbeat_timeout_seconds,
          stop_requested_at,
          stop_requested_by_instance_id,
          endpoint_json,
          exit_code,
          terminal_at,
          last_error_json
        FROM resident_services
        WHERE role = ?
        """,
        (role,),
    ).fetchone()
    if row is None:
        return None
    return {
        "role": row[0],
        "instance_id": row[1],
        "pid": row[2],
        "config_ref": row[3],
        "config_digest": row[4],
        "status": row[5],
        "started_at": row[6],
        "updated_at": row[7],
        "heartbeat_at": row[8],
        "heartbeat_timeout_seconds": row[9],
        "stop_requested_at": row[10],
        "stop_requested_by_instance_id": row[11],
        "endpoint": _loads(row[12]),
        "exit_code": row[13],
        "terminal_at": row[14],
        "last_error": _loads(row[15]),
    }


def _require_matching_state(connection: sqlite3.Connection, role: ServiceRole, instance_id: str) -> dict[str, Any]:
    state = _service_state(connection, role)
    if not state:
        raise ServiceLifecycleError("service state was not found.")
    if state.get("instance_id") != instance_id:
        raise ServiceLifecycleError("service instance id does not match current lifecycle state.")
    return state


def _record_event(
    connection: sqlite3.Connection,
    *,
    role: ServiceRole,
    instance_id: str | None = None,
    event_type: str,
    status: str,
    created_at: str,
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO resident_service_events (
          role,
          instance_id,
          event_type,
          status,
          created_at,
          details_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (role, instance_id, event_type, status, created_at, _dumps(details or {})),
    )


def _trim_events(connection: sqlite3.Connection, role: ServiceRole) -> None:
    connection.execute(
        """
        DELETE FROM resident_service_events
        WHERE role = ?
          AND event_id NOT IN (
            SELECT event_id
            FROM resident_service_events
            WHERE role = ?
            ORDER BY event_id DESC
            LIMIT ?
          )
        """,
        (role, role, SERVICE_EVENT_LIMIT),
    )


def _heartbeat_is_stale(state: dict[str, Any], *, now: datetime | str | None) -> bool:
    heartbeat = _parse_utc(state.get("heartbeat_at"))
    if heartbeat is None:
        return True
    timeout = int(state.get("heartbeat_timeout_seconds") or 0)
    if timeout <= 0:
        return True
    return (_parse_utc(_format_utc(now)) - heartbeat).total_seconds() > timeout


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    with suppress(ValueError):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc)
    return None


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("service lifecycle timestamp must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("service lifecycle timestamp must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("service lifecycle timestamp must be a datetime or ISO 8601 string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _safe_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    for key in ("host", "port", "health_url"):
        value = endpoint.get(key)
        if key == "port" and isinstance(value, int):
            allowed[key] = value
        elif isinstance(value, str) and value:
            allowed[key] = value[:200]
    return allowed


def _safe_config_ref(value: str) -> str:
    text = str(value).strip()
    if not text:
        return "unknown"
    lowered = text.lower()
    if "://" in lowered or text.startswith("~"):
        return "<local-config>"
    safe_ref = display_path(Path(text), external_ref="<local-config>")
    return safe_ref[:200]


def _last_error(error: str | None) -> dict[str, Any]:
    if not error:
        return {}
    text = str(error).strip()
    lowered = text.lower()
    private_markers = ("\\", "/", "://", "token", "secret", "cookie", "proxy", "password")
    if any(marker in lowered for marker in private_markers):
        return {
            "message": "service error redacted; inspect local logs.",
            "private_values_embedded": False,
        }
    return {"message": text[:500], "private_values_embedded": False}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    with suppress(json.JSONDecodeError):
        loaded = json.loads(value)
        if isinstance(loaded, dict):
            return loaded
    return {}


def _state_instance_id(state: dict[str, Any] | None) -> str | None:
    if not state:
        return None
    value = state.get("instance_id")
    return str(value) if isinstance(value, str) and value else None


def _state_pid_is_current_process(state: dict[str, Any]) -> bool:
    with suppress(TypeError, ValueError):
        return int(state.get("pid")) == os.getpid()
    return False


def _instance_id(role: ServiceRole) -> str:
    return f"{role}-{uuid4().hex}"


def _ensure_lock_byte(handle: Any) -> None:
    handle.seek(0)
    if handle.read(1):
        handle.seek(0)
        return
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    os.fsync(handle.fileno())
    handle.seek(0)
