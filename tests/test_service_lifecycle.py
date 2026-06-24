from __future__ import annotations

from contextlib import closing
import multiprocessing
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from halpha.runtime.command_job_store import apply_command_job_migrations
from halpha.data.run_index import apply_run_index_migrations
from halpha.runtime.service_lifecycle import (
    SERVICE_ROLES,
    ServiceLifecycleRepository,
    apply_service_lifecycle_migrations,
)
from halpha.runtime.state_store import open_runtime_state_connection


def test_service_lifecycle_rejects_unknown_roles(tmp_path: Path) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)

    assert SERVICE_ROLES == frozenset({"dashboard", "monitor", "schedule"})
    with pytest.raises(ValueError, match="service role must be one of: dashboard, monitor, schedule"):
        repository.inspect("worker")


def test_service_lifecycle_start_reports_existing_and_config_conflict(tmp_path: Path) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "dashboard",
        config_ref="config.yaml",
        config_digest="digest-a",
        endpoint={"host": "127.0.0.1", "port": 8765},
        now="2026-06-05T00:00:00Z",
    )
    assert ownership is not None
    try:
        repository.register_started("dashboard", instance_id=result.instance_id or "", now="2026-06-05T00:00:01Z")

        same, same_ownership = repository.attempt_start_ownership(
            "dashboard",
            config_ref="config.yaml",
            config_digest="digest-a",
            now="2026-06-05T00:00:02Z",
        )
        conflict, conflict_ownership = repository.attempt_start_ownership(
            "dashboard",
            config_ref="other.yaml",
            config_digest="digest-b",
            now="2026-06-05T00:00:03Z",
        )
    finally:
        ownership.release()

    assert result.status == "acquired"
    assert same.status == "existing"
    assert same.instance_id == result.instance_id
    assert same_ownership is None
    assert conflict.status == "conflict"
    assert conflict.instance_id == result.instance_id
    assert conflict_ownership is None


def test_service_lifecycle_inspect_reports_owned_service_state(tmp_path: Path) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "dashboard",
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:00Z",
    )
    assert ownership is not None
    try:
        repository.register_started("dashboard", instance_id=result.instance_id or "", now="2026-06-05T00:00:01Z")
        inspected = repository.inspect("dashboard", now="2026-06-05T00:00:02Z")
    finally:
        ownership.release()

    assert inspected.status == "running"
    assert inspected.instance_id == result.instance_id


def test_service_lifecycle_reconciles_stale_running_state_when_lock_is_free(tmp_path: Path) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path, heartbeat_timeout_seconds=1)
    result, ownership = repository.attempt_start_ownership(
        "monitor",
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:00Z",
    )
    assert ownership is not None
    repository.register_started("monitor", instance_id=result.instance_id or "", now="2026-06-05T00:00:00Z")
    ownership.release()

    next_result, next_ownership = repository.attempt_start_ownership(
        "monitor",
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:10Z",
    )
    assert next_ownership is not None
    next_ownership.release()

    assert next_result.status == "acquired_after_reconcile"
    assert next_result.instance_id != result.instance_id
    with closing(sqlite3.connect(tmp_path / ".halpha" / "state.sqlite")) as connection:
        events = connection.execute(
            "SELECT event_type, status FROM resident_service_events WHERE role = ? ORDER BY event_id",
            ("monitor",),
        ).fetchall()
    assert ("reconcile_stale", "crashed") in events


def test_service_lifecycle_reports_unresponsive_when_lock_is_held_with_stale_heartbeat(tmp_path: Path) -> None:
    process, ready, release = _start_service_process(
        tmp_path,
        role="schedule",
        config_digest="digest-a",
        heartbeat_timeout_seconds=1,
    )
    try:
        state = ready.get(timeout=10)
        repository = ServiceLifecycleRepository(runtime_root=tmp_path, heartbeat_timeout_seconds=1)

        result, ownership = repository.attempt_start_ownership(
            "schedule",
            config_ref="config.yaml",
            config_digest="digest-a",
            now="2026-06-05T00:00:10Z",
        )
    finally:
        release.set()
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    assert state["status"] == "running"
    assert result.status == "unresponsive"
    assert result.instance_id == state["instance_id"]
    assert ownership is None


def test_service_lifecycle_lock_reports_existing_or_conflict_across_processes(tmp_path: Path) -> None:
    process, ready, release = _start_service_process(
        tmp_path,
        role="monitor",
        config_digest="digest-a",
        heartbeat_timeout_seconds=30,
    )
    try:
        state = ready.get(timeout=10)
        repository = ServiceLifecycleRepository(runtime_root=tmp_path, heartbeat_timeout_seconds=30)

        same, same_ownership = repository.attempt_start_ownership(
            "monitor",
            config_ref="config.yaml",
            config_digest="digest-a",
            now="2026-06-05T00:00:02Z",
        )
        conflict, conflict_ownership = repository.attempt_start_ownership(
            "monitor",
            config_ref="other.yaml",
            config_digest="digest-b",
            now="2026-06-05T00:00:03Z",
        )
    finally:
        release.set()
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    assert state["status"] == "running"
    assert same.status == "existing"
    assert same.instance_id == state["instance_id"]
    assert same_ownership is None
    assert conflict.status == "conflict"
    assert conflict.instance_id == state["instance_id"]
    assert conflict_ownership is None


def test_service_lifecycle_stop_request_targets_instance_id_not_pid(tmp_path: Path) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "dashboard",
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:00Z",
    )
    assert ownership is not None
    instance_id = result.instance_id or ""
    try:
        repository.register_started("dashboard", instance_id=instance_id, now="2026-06-05T00:00:01Z")

        mismatch = repository.request_graceful_stop(
            "dashboard",
            instance_id="dashboard-reused-pid",
            now="2026-06-05T00:00:02Z",
        )
        requested = repository.request_graceful_stop(
            "dashboard",
            instance_id=instance_id,
            now="2026-06-05T00:00:03Z",
        )
        observed = repository.observe_stop_request("dashboard", instance_id=instance_id)
        terminal = repository.record_terminal_exit(
            "dashboard",
            instance_id=instance_id,
            status="stopped",
            exit_code=0,
            now="2026-06-05T00:00:04Z",
        )
    finally:
        ownership.release()

    assert mismatch.status == "instance_mismatch"
    assert requested.status == "stop_requested"
    assert observed.requested is True
    assert observed.requested_at == "2026-06-05T00:00:03Z"
    assert terminal.status == "stopped"


def test_service_lifecycle_requires_explicit_restart_after_terminal_state(tmp_path: Path) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "schedule",
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:00Z",
    )
    assert ownership is not None
    instance_id = result.instance_id or ""
    try:
        repository.register_started("schedule", instance_id=instance_id, now="2026-06-05T00:00:01Z")
        terminal = repository.record_terminal_exit(
            "schedule",
            instance_id=instance_id,
            status="stopped",
            exit_code=0,
            now="2026-06-05T00:00:02Z",
        )
    finally:
        ownership.release()

    blocked, blocked_ownership = repository.attempt_start_ownership(
        "schedule",
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:03Z",
    )
    mismatch, mismatch_ownership = repository.attempt_restart_ownership(
        "schedule",
        previous_instance_id="schedule-reused-pid",
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:04Z",
    )
    restarted, restart_ownership = repository.attempt_restart_ownership(
        "schedule",
        previous_instance_id=instance_id,
        config_ref="config.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:05Z",
    )
    assert restart_ownership is not None
    restart_ownership.release()

    assert terminal.status == "stopped"
    assert blocked.status == "stopped"
    assert blocked_ownership is None
    assert blocked.reason == "service is in a terminal state; use explicit restart after confirming the instance id."
    assert mismatch.status == "instance_mismatch"
    assert mismatch_ownership is None
    assert restarted.status == "restart_acquired"
    assert restarted.instance_id != instance_id


def test_service_lifecycle_redacts_private_error_values(tmp_path: Path) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "monitor",
        config_ref=r"C:\\Users\\private\\config.local.yaml",
        config_digest="digest-a",
        now="2026-06-05T00:00:00Z",
    )
    assert ownership is not None
    try:
        terminal = repository.record_terminal_exit(
            "monitor",
            instance_id=result.instance_id or "",
            status="failed",
            exit_code=1,
            error=r"C:\\Users\\private\\token.txt failed",
            now="2026-06-05T00:00:01Z",
        )
    finally:
        ownership.release()

    assert terminal.state is not None
    assert terminal.state["config_ref"] == "<local-config>"
    assert terminal.state["last_error"] == {
        "message": "service error redacted; inspect local logs.",
        "private_values_embedded": False,
    }


def test_service_lifecycle_migration_uses_distinct_runtime_version(tmp_path: Path) -> None:
    with closing(open_runtime_state_connection(runtime_root=tmp_path)) as connection:
        apply_command_job_migrations(connection, now="2026-06-05T00:00:00Z")
        apply_run_index_migrations(connection, now="2026-06-05T00:01:00Z")
        apply_service_lifecycle_migrations(connection, now="2026-06-05T00:02:00Z")
        versions = [
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        ]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'resident_service%'"
            ).fetchall()
        }

    assert versions == [1, 2, 6, 7, 9, 14]
    assert tables == {"resident_services", "resident_service_events"}


def _start_service_process(
    runtime_root: Path,
    *,
    role: str,
    config_digest: str,
    heartbeat_timeout_seconds: int,
) -> tuple[multiprocessing.Process, Any, Any]:
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    release = context.Event()
    process = context.Process(
        target=_service_process_main,
        args=(str(runtime_root), role, config_digest, heartbeat_timeout_seconds, ready, release),
    )
    process.start()
    return process, ready, release


def _service_process_main(
    runtime_root: str,
    role: str,
    config_digest: str,
    heartbeat_timeout_seconds: int,
    ready: Any,
    release: Any,
) -> None:
    repository = ServiceLifecycleRepository(
        runtime_root=Path(runtime_root),
        heartbeat_timeout_seconds=heartbeat_timeout_seconds,
    )
    result, ownership = repository.attempt_start_ownership(
        role,
        config_ref="config.yaml",
        config_digest=config_digest,
        now="2026-06-05T00:00:00Z",
    )
    if ownership is None:
        ready.put({"status": result.status, "instance_id": result.instance_id})
        return
    try:
        repository.register_started(role, instance_id=result.instance_id or "", now="2026-06-05T00:00:00Z")
        ready.put({"status": "running", "instance_id": result.instance_id})
        release.wait(15)
    finally:
        ownership.release()
