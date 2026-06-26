from __future__ import annotations

from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from json import JSONDecodeError
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from halpha.config import ConfigError, load_config
from halpha.dashboard.schedule_store import (
    DAILY_REPORT_SCHEDULE_ID,
    DashboardScheduleRepository,
)
from halpha.dashboard.state import write_dashboard_selected_config_state
from halpha.dashboard.settings import dashboard_config_ref
from halpha.data.run_index import apply_run_index_migrations, write_run_index
from halpha.monitor.state_store import MonitorStateRepository
from halpha.runtime.command_job_store import CommandJobRepository, JOB_TRANSIENT_STATUSES
from halpha.runtime.pipeline_contracts import RunContext
from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    STATE_STORE_REF,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_path,
    runtime_state_transaction,
)
from halpha.storage import artifact_base, display_path, safe_local_ref


LEGACY_STATE_MIGRATION_SCHEMA_VERSION = 1
LEGACY_STATE_MIGRATION_VERSION = 13
LEGACY_STATE_BACKUP_ROOT = ".halpha/legacy_state_backups"
LEGACY_JOB_TRANSIENT_TERMINAL_ERROR = "legacy non-terminal command job had no verified live process ownership."
LEGACY_SERVICE_DIAGNOSTIC = "legacy service state is diagnostic only; running state is not restored."


@dataclass(frozen=True)
class LegacySource:
    source_type: str
    ref: str
    path: Path
    status: str
    supported_import_type: str | None = None
    fingerprint: str | None = None
    records: tuple[dict[str, Any], ...] = ()
    conflicts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    cleanup_candidate: bool = False
    cleanup_blocked_reason: str | None = None

    @property
    def exists(self) -> bool:
        return self.status != "missing"

    @property
    def importable_records(self) -> int:
        return sum(1 for record in self.records if record.get("status") == "importable")

    @property
    def diagnostic_records(self) -> int:
        return sum(1 for record in self.records if record.get("status") == "diagnostic")

    def as_payload(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "ref": self.ref,
            "exists": self.exists,
            "status": self.status,
            "supported_import_type": self.supported_import_type,
            "record_count": len(self.records),
            "importable_records": self.importable_records,
            "diagnostic_records": self.diagnostic_records,
            "invalid_records": sum(1 for record in self.records if record.get("status") == "invalid"),
            "fingerprint": self.fingerprint,
            "conflicts": list(self.conflicts),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "cleanup": {
                "candidate": self.cleanup_candidate,
                "deletable": False,
                "requires_separate_confirmation": self.cleanup_candidate,
                "blocked_reason": self.cleanup_blocked_reason,
            },
            "records": [_bounded_record(record) for record in self.records[:20]],
        }


LEGACY_STATE_MIGRATIONS = (
    StateStoreMigration(
        version=LEGACY_STATE_MIGRATION_VERSION,
        name="legacy_state_migrations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS legacy_state_sources (
              source_ref TEXT NOT NULL,
              source_type TEXT NOT NULL,
              fingerprint TEXT NOT NULL,
              status TEXT NOT NULL,
              imported_records INTEGER NOT NULL,
              diagnostic_records INTEGER NOT NULL,
              applied_at TEXT NOT NULL,
              diagnostics_json TEXT NOT NULL,
              PRIMARY KEY (source_ref, fingerprint)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS legacy_state_imports (
              import_key TEXT PRIMARY KEY,
              source_ref TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_record_key TEXT NOT NULL,
              fingerprint TEXT NOT NULL,
              status TEXT NOT NULL,
              imported_at TEXT NOT NULL
            )
            """,
        ),
    ),
)


def legacy_state_migration_dry_run(
    config: dict[str, Any],
    *,
    config_path: Path,
    replace_schedule: bool = False,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    return _legacy_state_migration(
        config,
        config_path=config_path,
        apply=False,
        replace_schedule=replace_schedule,
        now=now,
    )


def apply_legacy_state_migration(
    config: dict[str, Any],
    *,
    config_path: Path,
    replace_schedule: bool = False,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    return _legacy_state_migration(
        config,
        config_path=config_path,
        apply=True,
        replace_schedule=replace_schedule,
        now=now,
    )


def rebuild_run_index_from_manifests(
    config: dict[str, Any],
    *,
    config_path: Path,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    timestamp = _format_utc(now)
    base = artifact_base(config_path)
    manifests = _discover_run_manifests(config, base=base)
    imported = 0
    diagnostics: list[dict[str, Any]] = []
    with closing(open_runtime_state_connection(config_path=config_path)) as connection:
        apply_run_index_migrations(connection, now=timestamp)
        with runtime_state_transaction(connection):
            connection.execute("DELETE FROM runs")
    for manifest_path in manifests:
        manifest, error = _read_json_object(manifest_path)
        if error or not _valid_manifest(manifest):
            diagnostics.append(
                {
                    "status": "invalid",
                    "manifest": _safe_ref(manifest_path, base=base),
                    "error": error or "run_manifest.json is missing run_id.",
                }
            )
            continue
        write_run_index(_run_context_from_manifest(manifest_path, manifest, config_path=config_path), now=timestamp)
        imported += 1
    return {
        "schema_version": LEGACY_STATE_MIGRATION_SCHEMA_VERSION,
        "artifact_type": "run_index_rebuild",
        "status": "succeeded" if not diagnostics else "partial",
        "mode": "rebuild_run_index",
        "run_index": STATE_STORE_REF,
        "counts": {
            "run_manifests": len(manifests),
            "rebuilt_runs": imported,
            "diagnostics": len(diagnostics),
        },
        "diagnostics": diagnostics[:50],
        "warnings": [item["error"] for item in diagnostics[:10]],
        "errors": [],
    }


def apply_legacy_state_migrations(connection: sqlite3.Connection, *, now: datetime | str | None = None) -> None:
    apply_runtime_state_migrations(
        connection,
        migrations=RUNTIME_STATE_MIGRATIONS + LEGACY_STATE_MIGRATIONS,
        now=now,
    )


def _legacy_state_migration(
    config: dict[str, Any],
    *,
    config_path: Path,
    apply: bool,
    replace_schedule: bool,
    now: datetime | str | None,
) -> dict[str, Any]:
    timestamp = _format_utc(now)
    base = artifact_base(config_path)
    existing_schedule = _read_existing_schedule(config_path)
    sources = _scan_legacy_sources(
        config,
        config_path=config_path,
        base=base,
        existing_schedule=existing_schedule,
        replace_schedule=replace_schedule,
    )
    backups = _backup_legacy_sources(sources, base=base, timestamp=timestamp) if apply else []
    apply_results: dict[str, dict[str, Any]] = {}
    if apply:
        for source in sources:
            apply_results[source.ref] = _apply_source(
                source,
                config=config,
                config_path=config_path,
                base=base,
                timestamp=timestamp,
                replace_schedule=replace_schedule,
            )
    source_payloads = []
    for source in sources:
        payload = source.as_payload()
        if source.ref in apply_results:
            payload["apply_result"] = apply_results[source.ref]
        source_payloads.append(payload)

    counts = _migration_counts(sources, apply_results=apply_results, backups=backups)
    errors = [error for source in sources for error in source.errors]
    conflicts = _active_conflicts(sources, apply_results=apply_results)
    status = "succeeded" if apply else "available"
    if errors or conflicts:
        status = "partial"
    if apply and any(result.get("status") == "failed" for result in apply_results.values()):
        status = "failed"
    return {
        "schema_version": LEGACY_STATE_MIGRATION_SCHEMA_VERSION,
        "artifact_type": "legacy_state_migration",
        "status": status,
        "mode": "apply" if apply else "dry_run",
        "runtime_state": STATE_STORE_REF,
        "replace_schedule": replace_schedule,
        "sources": source_payloads,
        "cleanup_plan": _cleanup_plan(sources),
        "backup": {
            "status": "created" if backups else ("not_run" if not apply else "empty"),
            "refs": backups,
        },
        "counts": counts,
        "warnings": [warning for source in sources for warning in source.warnings],
        "errors": errors,
        "conflicts": conflicts,
        "omitted": {
            "absolute_local_paths_embedded": False,
            "legacy_file_contents_embedded": False,
            "private_config_values_embedded": False,
        },
    }


def _scan_legacy_sources(
    config: dict[str, Any],
    *,
    config_path: Path,
    base: Path,
    existing_schedule: dict[str, Any] | None,
    replace_schedule: bool,
) -> list[LegacySource]:
    sources = [
        _scan_legacy_run_index(base),
        *_scan_legacy_command_jobs(base),
        _scan_legacy_schedule(base, existing_schedule=existing_schedule, replace_schedule=replace_schedule),
        _scan_legacy_selected_config(base),
        _scan_legacy_dashboard_service_state(base),
        *_scan_legacy_monitor_cycles(base),
        _scan_legacy_monitor_alert_archive(base),
        _scan_legacy_monitor_cooldowns(base),
        _scan_legacy_monitor_archive_state(base),
        _scan_legacy_monitor_health(config, config_path=config_path, base=base),
    ]
    return sources


def _scan_legacy_run_index(base: Path) -> LegacySource:
    path = base / "data/research/index.sqlite"
    if not path.exists():
        return _missing_source("legacy_run_index", "data/research/index.sqlite")
    try:
        rows = _legacy_run_index_rows(path)
    except sqlite3.Error as exc:
        return _invalid_source("legacy_run_index", path, base=base, error=f"legacy run index could not be read: {type(exc).__name__}.")
    records = []
    warnings = []
    for row in rows:
        manifest_ref = _legacy_manifest_ref(row)
        manifest_path = _resolve_ref(manifest_ref, base=base) if manifest_ref else None
        if manifest_path is None:
            records.append({"status": "invalid", "record_key": str(row.get("run_id") or "unknown"), "reason": "manifest ref is missing or unsafe."})
            continue
        manifest, error = _read_json_object(manifest_path)
        safe_manifest = _safe_ref(manifest_path, base=base)
        if error:
            records.append({"status": "diagnostic", "record_key": str(row.get("run_id") or safe_manifest), "manifest": safe_manifest, "reason": error})
            continue
        if not _valid_manifest(manifest):
            records.append(
                {
                    "status": "diagnostic",
                    "record_key": str(row.get("run_id") or safe_manifest),
                    "manifest": safe_manifest,
                    "reason": "run manifest is missing run_id.",
                }
            )
            continue
        mismatch = _legacy_run_index_mismatches(row, manifest)
        if mismatch:
            warnings.append("legacy run-index metadata differs from manifest; manifest evidence will be imported.")
        records.append(
            {
                "status": "importable",
                "record_key": str(manifest.get("run_id")),
                "manifest": safe_manifest,
                "manifest_overrides": mismatch,
            }
        )
    return LegacySource(
        source_type="legacy_run_index",
        ref="data/research/index.sqlite",
        path=path,
        status="available" if records else "empty",
        supported_import_type="run_index_from_manifests",
        fingerprint=_fingerprint(path),
        records=tuple(records),
        warnings=tuple(_unique_strings(warnings)),
        cleanup_candidate=True,
    )


def _scan_legacy_command_jobs(base: Path) -> list[LegacySource]:
    root = base / ".halpha/dashboard/jobs"
    sources: list[LegacySource] = []
    index_path = root / "index.json"
    if index_path.exists():
        loaded, error = _read_json_object(index_path)
        records = _jobs_from_legacy_index(loaded) if not error else []
        sources.append(
            _json_records_source(
                "legacy_dashboard_job_index",
                index_path,
                base=base,
                supported_import_type="command_jobs",
                records=[_legacy_job_record(job, ref=_safe_ref(index_path, base=base)) for job in records],
                error=error,
                cleanup_candidate=True,
            )
        )
    if root.is_dir():
        for job_path in sorted(root.glob("*/job.json")):
            loaded, error = _read_json_object(job_path)
            records = [_legacy_job_record(loaded, ref=_safe_ref(job_path, base=base))] if loaded else []
            sources.append(
                _json_records_source(
                    "legacy_dashboard_job",
                    job_path,
                    base=base,
                    supported_import_type="command_job",
                    records=records,
                    error=error,
                    cleanup_candidate=True,
                )
            )
    if not sources:
        return [_missing_source("legacy_dashboard_jobs", ".halpha/dashboard/jobs")]
    return sources


def _scan_legacy_schedule(
    base: Path,
    *,
    existing_schedule: dict[str, Any] | None,
    replace_schedule: bool,
) -> LegacySource:
    path = base / ".halpha/dashboard/schedules/daily_report_schedule.json"
    loaded, error = _read_json_object(path)
    if not path.exists():
        return _missing_source("legacy_dashboard_schedule", ".halpha/dashboard/schedules/daily_report_schedule.json")
    if error:
        return _json_records_source(
            "legacy_dashboard_schedule",
            path,
            base=base,
            supported_import_type="daily_report_schedule",
            records=[],
            error=error,
            cleanup_candidate=False,
        )
    record = _legacy_schedule_record(loaded)
    conflicts: tuple[str, ...] = ()
    if existing_schedule and record.get("status") == "importable" and not replace_schedule:
        conflicts = ("unified schedule already exists; use explicit replacement to import legacy schedule.",)
        record = {**record, "status": "conflict"}
    return LegacySource(
        source_type="legacy_dashboard_schedule",
        ref=_safe_ref(path, base=base),
        path=path,
        status="conflict" if conflicts else str(record.get("status") or "available"),
        supported_import_type="daily_report_schedule",
        fingerprint=_fingerprint(path),
        records=(record,),
        conflicts=conflicts,
        cleanup_candidate=not conflicts,
        cleanup_blocked_reason=conflicts[0] if conflicts else None,
    )


def _scan_legacy_selected_config(base: Path) -> LegacySource:
    path = base / ".halpha/dashboard/selected_config.json"
    loaded, error = _read_json_object(path)
    if not path.exists():
        return _missing_source("legacy_dashboard_selected_config", ".halpha/dashboard/selected_config.json")
    records: list[dict[str, Any]] = []
    errors: tuple[str, ...] = (error,) if error else ()
    if loaded:
        raw_path = loaded.get("config_path")
        config_path = _resolve_config_ref(raw_path, base=base)
        if config_path is None:
            records.append({"status": "invalid", "record_key": "selected_config", "reason": "selected config path is missing or unsafe."})
        else:
            try:
                load_config(config_path)
            except ConfigError:
                records.append(
                    {
                        "status": "invalid",
                        "record_key": "selected_config",
                        "config": dashboard_config_ref(config_path),
                        "reason": "selected config could not be loaded.",
                    }
                )
            else:
                records.append(
                    {
                        "status": "importable",
                        "record_key": "selected_config",
                        "config": dashboard_config_ref(config_path),
                        "config_path": str(config_path),
                    }
                )
    return LegacySource(
        source_type="legacy_dashboard_selected_config",
        ref=_safe_ref(path, base=base),
        path=path,
        status="invalid" if errors or any(record.get("status") == "invalid" for record in records) else "available",
        supported_import_type="dashboard_selected_config",
        fingerprint=_fingerprint(path),
        records=tuple(records),
        errors=errors,
        cleanup_candidate=not errors and bool(records) and all(record.get("status") == "importable" for record in records),
        cleanup_blocked_reason="selected config is invalid." if errors or any(record.get("status") == "invalid" for record in records) else None,
    )


def _scan_legacy_dashboard_service_state(base: Path) -> LegacySource:
    path = base / ".halpha/dashboard/service_state.json"
    loaded, error = _read_json_object(path)
    if not path.exists():
        return _missing_source("legacy_dashboard_service_state", ".halpha/dashboard/service_state.json")
    records = []
    if loaded:
        records.append(
            {
                "status": "diagnostic",
                "record_key": "dashboard_service_state",
                "legacy_status": str(loaded.get("status") or "unknown"),
                "reason": LEGACY_SERVICE_DIAGNOSTIC,
            }
        )
    return LegacySource(
        source_type="legacy_dashboard_service_state",
        ref=_safe_ref(path, base=base),
        path=path,
        status="invalid" if error else "diagnostic",
        supported_import_type="diagnostic_only",
        fingerprint=_fingerprint(path),
        records=tuple(records),
        warnings=(LEGACY_SERVICE_DIAGNOSTIC,),
        errors=(error,) if error else (),
        cleanup_candidate=error is None,
        cleanup_blocked_reason=error,
    )


def _scan_legacy_monitor_cycles(base: Path) -> list[LegacySource]:
    cycle_root = base / "runs/monitor/cycles"
    if not cycle_root.is_dir():
        return [_missing_source("legacy_monitor_cycles", "runs/monitor/cycles")]
    sources = []
    for path in sorted(cycle_root.glob("*/monitor_cycle_manifest.json")):
        loaded, error = _read_json_object(path)
        records = [_legacy_monitor_cycle_record(loaded, path, base=base)] if loaded else []
        sources.append(
            _json_records_source(
                "legacy_monitor_cycle",
                path,
                base=base,
                supported_import_type="monitor_cycle",
                records=records,
                error=error,
                cleanup_candidate=False,
                cleanup_blocked_reason="monitor cycle manifests are retained as inspectable run artifacts.",
            )
        )
    return sources or [_missing_source("legacy_monitor_cycles", "runs/monitor/cycles")]


def _scan_legacy_monitor_alert_archive(base: Path) -> LegacySource:
    path = base / "runs/monitor/alert_archive.jsonl"
    if not path.exists():
        return _missing_source("legacy_monitor_alert_archive", "runs/monitor/alert_archive.jsonl")
    records, malformed = _read_alert_jsonl(path)
    warnings = [f"{malformed} malformed alert archive line(s) were skipped."] if malformed else []
    return LegacySource(
        source_type="legacy_monitor_alert_archive",
        ref=_safe_ref(path, base=base),
        path=path,
        status="warning" if malformed else "available",
        supported_import_type="monitor_alert_records",
        fingerprint=_fingerprint(path),
        records=tuple(records),
        warnings=tuple(warnings),
        cleanup_candidate=malformed == 0,
        cleanup_blocked_reason="malformed JSONL lines require review." if malformed else None,
    )


def _scan_legacy_monitor_cooldowns(base: Path) -> LegacySource:
    path = base / "runs/monitor/alert_cooldown_state.json"
    loaded, error = _read_json_object(path)
    if not path.exists():
        return _missing_source("legacy_monitor_cooldowns", "runs/monitor/alert_cooldown_state.json")
    records = _legacy_cooldown_records(loaded) if loaded else []
    return _json_records_source(
        "legacy_monitor_cooldowns",
        path,
        base=base,
        supported_import_type="monitor_cooldowns",
        records=records,
        error=error,
        cleanup_candidate=error is None,
    )


def _scan_legacy_monitor_archive_state(base: Path) -> LegacySource:
    path = base / "runs/monitor/alert_archive_state.json"
    loaded, error = _read_json_object(path)
    if not path.exists():
        return _missing_source("legacy_monitor_archive_state", "runs/monitor/alert_archive_state.json")
    records = [{"status": "diagnostic", "record_key": "alert_archive_state", "counts": loaded.get("counts", {})}] if loaded else []
    return _json_records_source(
        "legacy_monitor_archive_state",
        path,
        base=base,
        supported_import_type="diagnostic_only",
        records=records,
        error=error,
        cleanup_candidate=error is None,
    )


def _scan_legacy_monitor_health(config: dict[str, Any], *, config_path: Path, base: Path) -> LegacySource:
    output_dir = _monitor_output_dir(config)
    path = base / output_dir / "monitor_health_state.json"
    loaded, error = _read_json_object(path)
    if not path.exists():
        return _missing_source("legacy_monitor_health", f"{output_dir}/monitor_health_state.json")
    record = _legacy_monitor_health_record(loaded, output_dir=output_dir) if loaded else {}
    return _json_records_source(
        "legacy_monitor_health",
        path,
        base=base,
        supported_import_type="monitor_service_health_snapshot",
        records=[record] if record else [],
        error=error,
        cleanup_candidate=error is None,
    )


def _apply_source(
    source: LegacySource,
    *,
    config: dict[str, Any],
    config_path: Path,
    base: Path,
    timestamp: str,
    replace_schedule: bool,
) -> dict[str, Any]:
    if not source.exists:
        return {"status": "skipped", "reason": "source missing", "imported_records": 0, "duplicate_records": 0}
    if source.fingerprint and _source_applied(config_path, source):
        return {"status": "already_applied", "imported_records": 0, "duplicate_records": source.importable_records or len(source.records)}
    if source.errors or source.conflicts:
        return {"status": "blocked", "reason": "source has errors or conflicts", "imported_records": 0, "duplicate_records": 0}
    try:
        if source.source_type == "legacy_run_index":
            result = _apply_legacy_run_index(source, config_path=config_path, base=base, timestamp=timestamp)
        elif source.source_type in {"legacy_dashboard_job", "legacy_dashboard_job_index"}:
            result = _apply_legacy_jobs(source, config_path=config_path, timestamp=timestamp)
        elif source.source_type == "legacy_dashboard_schedule":
            result = _apply_legacy_schedule(source, config_path=config_path, replace_schedule=replace_schedule, timestamp=timestamp)
        elif source.source_type == "legacy_dashboard_selected_config":
            result = _apply_legacy_selected_config(source, config_path=config_path, runtime_root=base, timestamp=timestamp)
        elif source.source_type == "legacy_monitor_cycle":
            result = _apply_legacy_monitor_cycles(source, config_path=config_path, timestamp=timestamp)
        elif source.source_type == "legacy_monitor_alert_archive":
            result = _apply_legacy_alert_records(source, config_path=config_path, timestamp=timestamp)
        elif source.source_type == "legacy_monitor_cooldowns":
            result = _apply_legacy_cooldowns(source, config_path=config_path, timestamp=timestamp)
        elif source.source_type == "legacy_monitor_health":
            result = _apply_legacy_monitor_health(source, config_path=config_path, timestamp=timestamp)
        else:
            result = {"status": "diagnostic", "imported_records": 0, "duplicate_records": 0}
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        result = {"status": "failed", "imported_records": 0, "duplicate_records": 0, "error": _safe_error(exc)}
    _record_legacy_source(config_path, source, result=result, timestamp=timestamp)
    return result


def _apply_legacy_run_index(source: LegacySource, *, config_path: Path, base: Path, timestamp: str) -> dict[str, Any]:
    imported = 0
    for record in source.records:
        if record.get("status") != "importable":
            continue
        manifest_path = _resolve_ref(str(record.get("manifest") or ""), base=base)
        if manifest_path is None:
            continue
        manifest, error = _read_json_object(manifest_path)
        if error or not _valid_manifest(manifest):
            continue
        write_run_index(_run_context_from_manifest(manifest_path, manifest, config_path=config_path), now=timestamp)
        imported += 1
        _record_legacy_import(config_path, source, record_key=str(record.get("record_key")), status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": imported, "duplicate_records": source.importable_records - imported}


def _apply_legacy_jobs(source: LegacySource, *, config_path: Path, timestamp: str) -> dict[str, Any]:
    repository = CommandJobRepository(config_path=config_path)
    imported = 0
    for record in source.records:
        if record.get("status") != "importable":
            continue
        job = record.get("job") if isinstance(record.get("job"), dict) else {}
        repository.save_job(job, event_type="legacy_import", message="legacy dashboard job imported.")
        imported += 1
        _record_legacy_import(config_path, source, record_key=str(record.get("record_key")), status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": imported, "duplicate_records": source.importable_records - imported}


def _apply_legacy_schedule(
    source: LegacySource,
    *,
    config_path: Path,
    replace_schedule: bool,
    timestamp: str,
) -> dict[str, Any]:
    record = next((item for item in source.records if item.get("status") == "importable"), None)
    if record is None:
        return {"status": "skipped", "imported_records": 0, "duplicate_records": 0}
    existing = _read_existing_schedule(config_path)
    if existing and not replace_schedule:
        return {"status": "blocked", "imported_records": 0, "duplicate_records": 0, "reason": "unified schedule already exists"}
    repository = DashboardScheduleRepository(config_path=config_path)
    schedule = dict(record.get("schedule") if isinstance(record.get("schedule"), dict) else {})
    schedule["updated_at"] = timestamp
    repository.save_schedule(schedule)
    _record_legacy_import(config_path, source, record_key="daily_report", status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": 1, "duplicate_records": 0}


def _apply_legacy_selected_config(source: LegacySource, *, config_path: Path, runtime_root: Path, timestamp: str) -> dict[str, Any]:
    record = next((item for item in source.records if item.get("status") == "importable"), None)
    if record is None:
        return {"status": "skipped", "imported_records": 0, "duplicate_records": 0}
    selected_config_path = Path(str(record.get("config_path") or ""))
    write_dashboard_selected_config_state(selected_config_path, runtime_root=runtime_root, now=timestamp)
    _record_legacy_import(config_path, source, record_key="selected_config", status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": 1, "duplicate_records": 0}


def _apply_legacy_monitor_cycles(source: LegacySource, *, config_path: Path, timestamp: str) -> dict[str, Any]:
    repository = MonitorStateRepository(config_path=config_path)
    imported = 0
    for record in source.records:
        if record.get("status") != "importable":
            continue
        cycle = record.get("cycle") if isinstance(record.get("cycle"), dict) else {}
        repository.save_cycle(cycle, updated_at=timestamp)
        imported += 1
        _record_legacy_import(config_path, source, record_key=str(record.get("record_key")), status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": imported, "duplicate_records": source.importable_records - imported}


def _apply_legacy_alert_records(source: LegacySource, *, config_path: Path, timestamp: str) -> dict[str, Any]:
    records = [record["alert_record"] for record in source.records if record.get("status") == "importable" and isinstance(record.get("alert_record"), dict)]
    if not records:
        return {"status": "skipped", "imported_records": 0, "duplicate_records": 0}
    monitor_output_dir = str(records[0].get("monitor_output_dir") or "runs/monitor")
    result = MonitorStateRepository(config_path=config_path).import_alert_records(
        records,
        monitor_output_dir=monitor_output_dir,
        updated_at=timestamp,
    )
    for record in source.records:
        if record.get("status") == "importable":
            _record_legacy_import(config_path, source, record_key=str(record.get("record_key")), status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": result["inserted"], "duplicate_records": result["duplicates"]}


def _apply_legacy_cooldowns(source: LegacySource, *, config_path: Path, timestamp: str) -> dict[str, Any]:
    cooldowns = {
        str(record.get("record_key")): record["cooldown_record"]
        for record in source.records
        if record.get("status") == "importable" and isinstance(record.get("cooldown_record"), dict)
    }
    if not cooldowns:
        return {"status": "skipped", "imported_records": 0, "duplicate_records": 0}
    result = MonitorStateRepository(config_path=config_path).import_cooldown_records(
        cooldowns,
        monitor_output_dir="runs/monitor",
        updated_at=timestamp,
    )
    for record in source.records:
        if record.get("status") == "importable":
            _record_legacy_import(config_path, source, record_key=str(record.get("record_key")), status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": result["inserted"], "duplicate_records": result["duplicates"]}


def _apply_legacy_monitor_health(source: LegacySource, *, config_path: Path, timestamp: str) -> dict[str, Any]:
    record = next((item for item in source.records if item.get("status") == "importable"), None)
    if record is None:
        return {"status": "skipped", "imported_records": 0, "duplicate_records": 0}
    health = record.get("health") if isinstance(record.get("health"), dict) else {}
    output_dir = str(record.get("monitor_output_dir") or "runs/monitor")
    MonitorStateRepository(config_path=config_path).save_service_health(health, monitor_output_dir=output_dir, updated_at=timestamp)
    _record_legacy_import(config_path, source, record_key="monitor_health", status="imported", timestamp=timestamp)
    return {"status": "imported", "imported_records": 1, "duplicate_records": 0}


def _source_applied(config_path: Path, source: LegacySource) -> bool:
    if not source.fingerprint:
        return False
    state_path = runtime_state_path(config_path=config_path)
    if not state_path.exists():
        return False
    try:
        with closing(open_runtime_state_connection(config_path=config_path)) as connection:
            apply_legacy_state_migrations(connection)
            row = connection.execute(
                "SELECT status FROM legacy_state_sources WHERE source_ref = ? AND fingerprint = ?",
                (source.ref, source.fingerprint),
            ).fetchone()
            return row is not None and row[0] not in {"blocked", "failed"}
    except sqlite3.Error:
        return False


def _record_legacy_source(config_path: Path, source: LegacySource, *, result: dict[str, Any], timestamp: str) -> None:
    if not source.fingerprint:
        return
    with closing(open_runtime_state_connection(config_path=config_path)) as connection:
        apply_legacy_state_migrations(connection, now=timestamp)
        with runtime_state_transaction(connection):
            connection.execute(
                """
                INSERT OR REPLACE INTO legacy_state_sources (
                  source_ref,
                  source_type,
                  fingerprint,
                  status,
                  imported_records,
                  diagnostic_records,
                  applied_at,
                  diagnostics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.ref,
                    source.source_type,
                    source.fingerprint,
                    str(result.get("status") or "unknown"),
                    _int(result.get("imported_records")),
                    source.diagnostic_records,
                    timestamp,
                    _dumps({"warnings": list(source.warnings), "errors": list(source.errors), "conflicts": list(source.conflicts)}),
                ),
            )


def _record_legacy_import(config_path: Path, source: LegacySource, *, record_key: str, status: str, timestamp: str) -> None:
    if not source.fingerprint:
        return
    import_key = sha256(f"{source.ref}|{source.fingerprint}|{record_key}".encode("utf-8")).hexdigest()
    with closing(open_runtime_state_connection(config_path=config_path)) as connection:
        apply_legacy_state_migrations(connection, now=timestamp)
        with runtime_state_transaction(connection):
            connection.execute(
                """
                INSERT OR REPLACE INTO legacy_state_imports (
                  import_key,
                  source_ref,
                  source_type,
                  source_record_key,
                  fingerprint,
                  status,
                  imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (import_key, source.ref, source.source_type, record_key, source.fingerprint, status, timestamp),
            )


def _backup_legacy_sources(sources: list[LegacySource], *, base: Path, timestamp: str) -> list[str]:
    backup_root = base / LEGACY_STATE_BACKUP_ROOT / timestamp.replace(":", "").replace("-", "")
    refs = []
    for source in sources:
        if source.source_type == "legacy_monitor_cycle":
            continue
        if not source.exists or not source.path.is_file():
            continue
        try:
            relative = source.path.resolve().relative_to(base.resolve())
        except (OSError, ValueError):
            continue
        target = backup_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.path, target)
        refs.append(_safe_ref(target, base=base))
    return sorted(refs)


def _cleanup_plan(sources: list[LegacySource]) -> dict[str, Any]:
    candidates = [
        {
            "ref": source.ref,
            "source_type": source.source_type,
            "deletable": False,
            "requires_separate_confirmation": True,
            "blocked_reason": source.cleanup_blocked_reason,
        }
        for source in sources
        if source.cleanup_candidate
    ]
    return {
        "status": "available" if candidates else "empty",
        "candidates": candidates,
        "counts": {
            "candidates": len(candidates),
            "deletable_now": 0,
            "blocked": sum(1 for candidate in candidates if candidate.get("blocked_reason")),
        },
        "warnings": ["legacy cleanup is a separate explicit action; migration never deletes files."],
        "errors": [],
    }


def _active_conflicts(sources: list[LegacySource], *, apply_results: dict[str, dict[str, Any]]) -> list[str]:
    conflicts: list[str] = []
    for source in sources:
        result = apply_results.get(source.ref)
        if result and result.get("status") == "already_applied":
            continue
        conflicts.extend(source.conflicts)
    return conflicts


def _migration_counts(sources: list[LegacySource], *, apply_results: dict[str, dict[str, Any]], backups: list[str]) -> dict[str, int]:
    conflicts = _active_conflicts(sources, apply_results=apply_results)
    return {
        "discovered_files": sum(1 for source in sources if source.exists),
        "supported_sources": sum(1 for source in sources if source.exists and source.supported_import_type),
        "supported_records": sum(len(source.records) for source in sources),
        "importable_records": sum(source.importable_records for source in sources),
        "imported_records": sum(_int(result.get("imported_records")) for result in apply_results.values()),
        "duplicate_records": sum(_int(result.get("duplicate_records")) for result in apply_results.values()),
        "diagnostic_records": sum(source.diagnostic_records for source in sources),
        "conflicts": len(conflicts),
        "invalid_sources": sum(1 for source in sources if source.status == "invalid"),
        "invalid_records": sum(sum(1 for record in source.records if record.get("status") == "invalid") for source in sources),
        "cleanup_candidates": sum(1 for source in sources if source.cleanup_candidate),
        "backups_created": len(backups),
    }


def _legacy_run_index_rows(path: Path) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        table = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'runs'").fetchone()
        if table is None:
            return []
        rows = connection.execute("SELECT * FROM runs ORDER BY run_id").fetchall()
        return [dict(row) for row in rows]


def _legacy_manifest_ref(row: dict[str, Any]) -> str | None:
    for key in ("manifest_path", "manifest", "run_manifest"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    run_dir = row.get("run_dir")
    if isinstance(run_dir, str) and run_dir:
        return str(Path(run_dir) / "run_manifest.json")
    return None


def _legacy_run_index_mismatches(row: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    mismatches = []
    for key in ("run_id", "status", "started_at", "finished_at"):
        legacy = row.get(key)
        current = manifest.get(key)
        if legacy not in (None, "") and current not in (None, "") and legacy != current:
            mismatches.append(key)
    return mismatches


def _legacy_job_record(job: dict[str, Any], *, ref: str) -> dict[str, Any]:
    job_id = str(job.get("job_id") or job.get("id") or "")
    if not job_id:
        return {"status": "invalid", "record_key": ref, "reason": "legacy command job is missing job_id."}
    status = str(job.get("status") or "unknown")
    errors = _bounded_strings(job.get("errors"), limit=20)
    if status in JOB_TRANSIENT_STATUSES:
        status = "failed"
        errors = _unique_strings([*errors, LEGACY_JOB_TRANSIENT_TERMINAL_ERROR])
    normalized = {
        "schema_version": 1,
        "artifact_type": "command_job",
        "job_id": job_id,
        "kind": str(job.get("kind") or "command"),
        "intent": str(job.get("intent") or "unknown"),
        "requested_by": str(job.get("requested_by") or "Dashboard"),
        "requester": job.get("requester") if isinstance(job.get("requester"), dict) else {"source": "legacy_dashboard_job"},
        "params": job.get("params") if isinstance(job.get("params"), dict) else {},
        "config_ref": _safe_config_ref(job.get("config_ref") or job.get("config_path")),
        "status": status,
        "created_at": str(job.get("created_at") or job.get("updated_at") or _epoch()),
        "updated_at": str(job.get("updated_at") or job.get("finished_at") or job.get("created_at") or _epoch()),
        "started_at": _optional_str(job.get("started_at")),
        "finished_at": _optional_str(job.get("finished_at")) or (str(job.get("updated_at") or _epoch()) if status == "failed" else None),
        "pid": _optional_int(job.get("pid")),
        "exit_code": _optional_int(job.get("exit_code")),
        "cancellable": False,
        "command": job.get("command") if isinstance(job.get("command"), list) else [],
        "job_dir": str(job.get("job_dir") or f".halpha/dashboard/jobs/{job_id}"),
        "logs": job.get("logs") if isinstance(job.get("logs"), dict) else {},
        "result_refs": job.get("result_refs") if isinstance(job.get("result_refs"), dict) else {},
        "source_artifacts": _unique_strings([ref, *_bounded_strings(job.get("source_artifacts"), limit=20)]),
        "warnings": _bounded_strings(job.get("warnings"), limit=20),
        "errors": errors,
    }
    return {"status": "importable", "record_key": job_id, "job": normalized}


def _jobs_from_legacy_index(loaded: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = loaded.get("jobs")
    if isinstance(jobs, list):
        return [job for job in jobs if isinstance(job, dict)]
    if isinstance(loaded.get("items"), list):
        return [job for job in loaded["items"] if isinstance(job, dict)]
    return []


def _legacy_schedule_record(loaded: dict[str, Any]) -> dict[str, Any]:
    settings = loaded.get("settings") if isinstance(loaded.get("settings"), dict) else loaded
    schedule = {
        "schema_version": 1,
        "artifact_type": "dashboard_daily_report_schedule",
        "schedule_id": DAILY_REPORT_SCHEDULE_ID,
        "schedule_kind": "daily_report",
        "enabled": loaded.get("enabled") is True,
        "status": str(loaded.get("status") or "available"),
        "settings": {
            "time_of_day": str(settings.get("time_of_day") or "09:00"),
            "timezone": str(settings.get("timezone") or "Asia/Shanghai"),
            "job_intent": str(settings.get("job_intent") or "run"),
        },
        "next_run_at": _optional_str(loaded.get("next_run_at")),
        "last_run_at": _optional_str(loaded.get("last_run_at")),
        "last_job_id": _optional_str(loaded.get("last_job_id")),
        "revision": _int(loaded.get("revision")),
        "created_at": str(loaded.get("created_at") or loaded.get("updated_at") or _epoch()),
        "updated_at": str(loaded.get("updated_at") or _epoch()),
        "warnings": _bounded_strings(loaded.get("warnings"), limit=20),
        "errors": _bounded_strings(loaded.get("errors"), limit=20),
        "codex_authorization": loaded.get("codex_authorization") if isinstance(loaded.get("codex_authorization"), dict) else {},
    }
    return {"status": "importable", "record_key": DAILY_REPORT_SCHEDULE_ID, "schedule": schedule}


def _legacy_monitor_cycle_record(loaded: dict[str, Any], path: Path, *, base: Path) -> dict[str, Any]:
    cycle_id = str(loaded.get("cycle_id") or path.parent.name)
    if not cycle_id:
        return {"status": "invalid", "record_key": _safe_ref(path, base=base), "reason": "monitor cycle is missing cycle_id."}
    cycle = {
        **loaded,
        "cycle_id": cycle_id,
        "monitor_output_dir": str(loaded.get("monitor_output_dir") or "runs/monitor"),
        "cycle_manifest": _safe_ref(path, base=base),
        "cycle_mode": str(loaded.get("cycle_mode") or "once"),
        "trigger_source": str(loaded.get("trigger_source") or "legacy_import"),
        "status": str(loaded.get("status") or "unknown"),
        "started_at": str(loaded.get("started_at") or loaded.get("created_at") or _epoch()),
        "updated_at": str(loaded.get("updated_at") or loaded.get("finished_at") or loaded.get("started_at") or _epoch()),
        "config_ref": _safe_config_ref(loaded.get("config_ref") or loaded.get("config_path")),
        "target_stage": str(loaded.get("target_stage") or ""),
    }
    return {"status": "importable", "record_key": cycle_id, "cycle": cycle}


def _read_alert_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    malformed = 0
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            loaded = json.loads(line)
        except JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(loaded, dict):
            malformed += 1
            continue
        record_id = str(loaded.get("record_id") or "")
        cycle_id = str(loaded.get("cycle_id") or "")
        if not record_id or not cycle_id:
            records.append({"status": "invalid", "record_key": f"line-{index}", "reason": "alert record is missing record_id or cycle_id."})
            continue
        loaded.setdefault("monitor_output_dir", "runs/monitor")
        records.append({"status": "importable", "record_key": record_id, "alert_record": loaded})
    return records, malformed


def _legacy_cooldown_records(loaded: dict[str, Any]) -> list[dict[str, Any]]:
    source = loaded.get("cooldown_records") if isinstance(loaded.get("cooldown_records"), dict) else loaded
    records = []
    for alert_key, record in sorted(source.items()):
        if not isinstance(record, dict):
            continue
        cooldown_until = record.get("cooldown_until")
        if not isinstance(cooldown_until, str) or not cooldown_until:
            records.append({"status": "invalid", "record_key": str(alert_key), "reason": "cooldown_until is missing."})
            continue
        records.append({"status": "importable", "record_key": str(alert_key), "cooldown_record": {**record, "cooldown_until": cooldown_until}})
    return records


def _legacy_monitor_health_record(loaded: dict[str, Any], *, output_dir: str) -> dict[str, Any]:
    status = str(loaded.get("status") or "unknown")
    if status in {"running", "running_cycle", "waiting", "retry_waiting"}:
        status = "legacy_imported"
    health = {
        "service_instance_id": _optional_str(loaded.get("service_instance_id")),
        "status": status,
        "latest_cycle_id": _optional_str(loaded.get("latest_cycle_id")),
        "latest_run_id": _optional_str(loaded.get("latest_run_id")),
        "latest_run_manifest": _optional_str(loaded.get("latest_run_manifest")),
        "consecutive_failures": _int(loaded.get("consecutive_failures")),
        "last_error": loaded.get("last_error") if isinstance(loaded.get("last_error"), dict) else {},
        "warnings": _unique_strings([LEGACY_SERVICE_DIAGNOSTIC, *_bounded_strings(loaded.get("warnings"), limit=20)]),
        "errors": _bounded_strings(loaded.get("errors"), limit=20),
    }
    return {"status": "importable", "record_key": "monitor_health", "monitor_output_dir": output_dir, "health": health}


def _json_records_source(
    source_type: str,
    path: Path,
    *,
    base: Path,
    supported_import_type: str,
    records: list[dict[str, Any]],
    error: str | None,
    cleanup_candidate: bool,
    cleanup_blocked_reason: str | None = None,
) -> LegacySource:
    status = "invalid" if error else ("available" if records else "empty")
    invalid = any(record.get("status") == "invalid" for record in records)
    if invalid and status == "available":
        status = "warning"
    return LegacySource(
        source_type=source_type,
        ref=_safe_ref(path, base=base),
        path=path,
        status=status,
        supported_import_type=supported_import_type,
        fingerprint=_fingerprint(path) if path.exists() else None,
        records=tuple(records),
        errors=(error,) if error else (),
        cleanup_candidate=cleanup_candidate and not error and not invalid,
        cleanup_blocked_reason=cleanup_blocked_reason or ("invalid records require review." if invalid else None),
    )


def _missing_source(source_type: str, ref: str) -> LegacySource:
    return LegacySource(source_type=source_type, ref=ref, path=Path(ref), status="missing")


def _invalid_source(source_type: str, path: Path, *, base: Path, error: str) -> LegacySource:
    return LegacySource(
        source_type=source_type,
        ref=_safe_ref(path, base=base),
        path=path,
        status="invalid",
        errors=(error,),
        fingerprint=_fingerprint(path) if path.exists() else None,
    )


def _read_existing_schedule(config_path: Path) -> dict[str, Any] | None:
    state_path = runtime_state_path(config_path=config_path)
    if not state_path.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{state_path.resolve().as_posix()}?mode=ro", uri=True)) as connection:
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'dashboard_schedules'"
            ).fetchone()
            if table is None:
                return None
            row = connection.execute("SELECT schedule_id, enabled, time_of_day, timezone, job_intent FROM dashboard_schedules LIMIT 1").fetchone()
            if row is None:
                return None
            return {
                "schedule_id": row[0],
                "enabled": bool(row[1]),
                "settings": {"time_of_day": row[2], "timezone": row[3], "job_intent": row[4]},
            }
    except sqlite3.Error:
        return None


def _run_context_from_manifest(manifest_path: Path, manifest: dict[str, Any], *, config_path: Path) -> RunContext:
    run_dir = manifest_path.parent
    run_id = str(manifest.get("run_id") or run_dir.name)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=run_dir / "raw",
        analysis_dir=run_dir / "analysis",
        codex_context_dir=run_dir / "codex_context",
        report_dir=run_dir / "report",
        manifest_path=manifest_path,
        config_path=config_path,
        manifest={**manifest, "run_id": run_id},
    )


def _discover_run_manifests(config: dict[str, Any], *, base: Path) -> list[Path]:
    run_config = config.get("run") if isinstance(config.get("run"), dict) else {}
    output_dir = str(run_config.get("output_dir") or "runs")
    root = Path(output_dir)
    root = root if root.is_absolute() else base / root
    try:
        root.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return []
    return sorted(root.glob("*/run_manifest.json"))


def _monitor_output_dir(config: dict[str, Any]) -> str:
    monitor = config.get("monitor") if isinstance(config.get("monitor"), dict) else {}
    return str(monitor.get("output_dir") or "runs/monitor")


def _valid_manifest(manifest: dict[str, Any]) -> bool:
    return isinstance(manifest.get("run_id"), str) and bool(manifest.get("run_id"))


def _resolve_ref(ref: str, *, base: Path) -> Path | None:
    if not isinstance(ref, str) or not ref:
        return None
    path = Path(ref)
    target = path if path.is_absolute() else base / path
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return target


def _resolve_config_ref(value: Any, *, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip())
    return path if path.is_absolute() else base / path


def _read_json_object(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except OSError:
        return {}, f"{path.name} could not be read."
    except JSONDecodeError:
        return {}, f"{path.name} is not valid JSON."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _fingerprint(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_ref(path: Path, *, base: Path) -> str:
    return safe_local_ref(path, base=base)


def _safe_config_ref(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    path = Path(value)
    if path.is_absolute() or "://" in value:
        return "<external-config>"
    return display_path(path, external_ref="<external-config>")


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    if "\\" in text or "/" in text or "://" in text:
        return "legacy state import failed; inspect local logs."
    return text[:200]


def _bounded_record(record: dict[str, Any]) -> dict[str, Any]:
    output = {key: value for key, value in record.items() if key not in {"job", "schedule", "cycle", "alert_record", "cooldown_record", "health", "config_path"}}
    if "manifest_overrides" in output and isinstance(output["manifest_overrides"], list):
        output["manifest_overrides"] = output["manifest_overrides"][:10]
    return output


def _dumps(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, sort_keys=True, separators=(",", ":"))


def _bounded_strings(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:200] for item in value if isinstance(item, str) and item][:limit]


def _unique_strings(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    with suppress(TypeError, ValueError):
        return int(value)
    return None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    with suppress(TypeError, ValueError):
        return int(value)
    return 0


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("legacy migration timestamp must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("legacy migration timestamp must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("legacy migration timestamp must be a datetime or ISO 8601 string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _epoch() -> str:
    return "1970-01-01T00:00:00Z"
