from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
from typing import Any, Callable

from halpha.monitor.state_store import (
    MONITOR_STATE_STORE_ARTIFACT,
    MonitorArchivePersistence,
    MonitorStateRepository,
)
from halpha.runtime.mutation_lease import mutation_lease
from halpha.runtime.pipeline_contracts import PipelineError, RunContext, RunResult
from halpha.runtime.state_store import runtime_state_path
from halpha.pipeline_stage_handlers import default_stage_handlers
from halpha.pipeline_stages import StageSelectionError
from halpha.pipeline import run_pipeline
from halpha.storage import artifact_base, write_json


LOGGER = logging.getLogger(__name__)


DEFAULT_MONITOR_ENABLED = False
DEFAULT_MONITOR_INTERVAL_SECONDS = 300
DEFAULT_MONITOR_MAX_CYCLES = 1
DEFAULT_MONITOR_FAILURE_BACKOFF_MAX_SECONDS = 3600
DEFAULT_MONITOR_COOLDOWN_SECONDS = 3600
DEFAULT_MONITOR_OUTPUT_DIR = "runs/monitor"
DEFAULT_MONITOR_TARGET_STAGE = "build_materials"
DEFAULT_MONITOR_NO_CODEX = True
DEFAULT_MONITOR_SLOW_SOURCE_CADENCE_SECONDS = 3600
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
MONITOR_SOURCE_KEYS = ("derivatives", "macro_calendar", "market", "onchain_flow", "text")
SLOW_MONITOR_SOURCE_KEYS = {"macro_calendar", "onchain_flow"}
MONITOR_DIAGNOSTIC_CYCLE_DIR_LIMIT = 20
SOURCE_REFRESH_TASKS = {
    "derivatives": ("collect_derivatives_market_data", "sync_derivatives_market_history"),
    "macro_calendar": ("collect_macro_calendar_data", "sync_macro_calendar_history"),
    "market": ("collect_market_data", "sync_ohlcv"),
    "onchain_flow": ("collect_onchain_flow_data", "sync_onchain_flow_history"),
    "text": ("collect_text_events",),
}
SOURCE_CADENCE_EXCLUDED_TASKS = (
    "build_source_evidence",
    "run_strategy_research",
    "synthesize_intelligence",
    "build_materials",
    "generate_report",
    "finalize_run",
)
SUPPORTED_MONITOR_FIELDS = {
    "cooldown_seconds",
    "enabled",
    "failure_backoff_max_seconds",
    "interval_seconds",
    "max_cycles",
    "no_codex",
    "output_dir",
    "source_cadence_seconds",
    "target_stage",
}


@dataclass(frozen=True)
class MonitorConfig:
    enabled: bool
    interval_seconds: int
    max_cycles: int
    failure_backoff_max_seconds: int
    cooldown_seconds: int
    output_dir: Path
    target_stage: str
    no_codex: bool
    source_cadence_seconds: dict[str, int]


@dataclass(frozen=True)
class MonitorCycleResult:
    succeeded: bool
    exit_code: int
    cycle_id: str
    status: str
    target_stage: str
    no_codex: bool
    manifest_path: Path | None
    run_id: str | None
    run_dir: Path | None
    run_manifest_path: Path | None
    reason: str | None


@dataclass(frozen=True)
class MonitorLoopResult:
    succeeded: bool
    exit_code: int
    loop_id: str
    status: str
    max_cycles: int
    completed_cycles: int
    stop_reason: str
    cycle_results: list[MonitorCycleResult]
    health_state_path: Path
    reason: str | None


@dataclass(frozen=True)
class MonitorInspectionResult:
    succeeded: bool
    exit_code: int
    lines: list[str]


PipelineRunner = Callable[..., RunResult]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class MonitorSourceGroup:
    source_key: str
    enabled: bool
    cadence_seconds: int


@dataclass(frozen=True)
class MonitorSourceRefreshResult:
    succeeded: bool
    exit_code: int
    failed_stage: str | None
    reason: str | None
    revision: str | None
    source_artifacts: dict[str, str]
    counts: dict[str, Any]
    warnings: list[str]


SourceRefresher = Callable[..., MonitorSourceRefreshResult]


def load_monitor_config(config: dict[str, Any]) -> MonitorConfig:
    section = config.get("monitor", {})
    if not isinstance(section, dict):
        raise ValueError("monitor config must be a mapping.")

    return MonitorConfig(
        enabled=section.get("enabled", DEFAULT_MONITOR_ENABLED),
        interval_seconds=section.get("interval_seconds", DEFAULT_MONITOR_INTERVAL_SECONDS),
        max_cycles=section.get("max_cycles", DEFAULT_MONITOR_MAX_CYCLES),
        failure_backoff_max_seconds=section.get(
            "failure_backoff_max_seconds",
            DEFAULT_MONITOR_FAILURE_BACKOFF_MAX_SECONDS,
        ),
        cooldown_seconds=section.get("cooldown_seconds", DEFAULT_MONITOR_COOLDOWN_SECONDS),
        output_dir=Path(str(section.get("output_dir", DEFAULT_MONITOR_OUTPUT_DIR))),
        target_stage=section.get("target_stage", DEFAULT_MONITOR_TARGET_STAGE),
        no_codex=section.get("no_codex", DEFAULT_MONITOR_NO_CODEX),
        source_cadence_seconds=_source_cadence_config(section.get("source_cadence_seconds")),
    )


def run_monitor_cycle(
    config: dict[str, Any],
    *,
    config_path: Path,
    now: datetime | None = None,
    pipeline_runner: PipelineRunner = run_pipeline,
    cycle_mode: str = "once",
    loop_id: str | None = None,
    cycle_sequence: int | None = None,
    cycle_id: str | None = None,
    trigger_source: str = "cli",
) -> MonitorCycleResult:
    with mutation_lease(config_path=config_path, owner_kind="monitor", workflow="monitor_cycle", requested_by="Monitor"):
        return _run_monitor_cycle_unlocked(
            config,
            config_path=config_path,
            now=now,
            pipeline_runner=pipeline_runner,
            cycle_mode=cycle_mode,
            loop_id=loop_id,
            cycle_sequence=cycle_sequence,
            cycle_id=cycle_id,
            trigger_source=trigger_source,
        )


def _run_monitor_cycle_unlocked(
    config: dict[str, Any],
    *,
    config_path: Path,
    now: datetime | None = None,
    pipeline_runner: PipelineRunner = run_pipeline,
    cycle_mode: str = "once",
    loop_id: str | None = None,
    cycle_sequence: int | None = None,
    cycle_id: str | None = None,
    trigger_source: str = "cli",
) -> MonitorCycleResult:
    settings = load_monitor_config(config)
    fixed_time = now is not None
    started_at = _coerce_utc(now or datetime.now(timezone.utc))
    cycle_id = cycle_id or _cycle_id(started_at)
    output_dir = _resolve_output_dir(settings.output_dir, config_path=config_path)
    cycle_dir = _unique_cycle_dir(output_dir / "cycles", cycle_id)
    cycle_id = cycle_dir.name
    manifest_path = cycle_dir / "monitor_cycle_manifest.json"
    base = artifact_base(config_path)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "monitor_cycle_manifest",
        "cycle_id": cycle_id,
        "cycle_mode": cycle_mode,
        "loop_id": loop_id,
        "cycle_sequence": cycle_sequence,
        "trigger_source": trigger_source,
        "status": "running",
        "started_at": _utc_timestamp(started_at),
        "finished_at": None,
        "config_ref": _portable_path(config_path, base=base),
        "monitor_output_dir": _portable_path(output_dir, base=base),
        "target_stage": settings.target_stage,
        "no_codex": settings.no_codex,
        "exit_code": None,
        "run_id": None,
        "run_dir": None,
        "run_manifest": None,
        "product_run": None,
        "source_artifacts": {},
        "alert_archive": _monitor_alert_archive_summary(status="not_run"),
        "warnings": [],
        "errors": [],
    }
    write_json(manifest_path, manifest)
    LOGGER.info(
        "Monitor cycle started.",
        extra={
            "event": "monitor.cycle.start",
            "cycle_id": cycle_id,
            "cycle_mode": cycle_mode,
            "loop_id": loop_id,
            "cycle_sequence": cycle_sequence,
            "target_stage": settings.target_stage,
            "no_codex": settings.no_codex,
        },
    )

    try:
        pipeline_result = pipeline_runner(
            config,
            config_path=config_path,
            until_stage=settings.target_stage,
            skip_codex=settings.no_codex,
            run_trigger={
                "source": "Monitor",
                "intent": "monitor_cycle",
                "monitor_cycle_id": cycle_id,
            },
        )
    except StageSelectionError as exc:
        reason = str(exc)
        finished_at = started_at if fixed_time else datetime.now(timezone.utc)
        manifest.update(
            {
                "status": "failed",
                "finished_at": _utc_timestamp(finished_at),
                "exit_code": 2,
                "errors": [{"stage": "target_stage", "message": reason}],
            }
        )
        write_json(manifest_path, manifest)
        _persist_monitor_cycle(config_path=config_path, manifest=manifest, manifest_path=manifest_path, output_dir=output_dir, base=base)
        LOGGER.error(
            "Monitor cycle failed.",
            extra={
                "event": "monitor.cycle.failed",
                "cycle_id": cycle_id,
                "target_stage": settings.target_stage,
                "exit_code": 2,
                "reason": reason,
            },
        )
        return MonitorCycleResult(
            succeeded=False,
            exit_code=2,
            cycle_id=cycle_id,
            status="failed",
            target_stage=settings.target_stage,
            no_codex=settings.no_codex,
            manifest_path=manifest_path,
            run_id=None,
            run_dir=None,
            run_manifest_path=None,
            reason=reason,
        )

    finished_at = started_at if fixed_time else datetime.now(timezone.utc)
    product_run = _product_run_summary(pipeline_result, base=base)
    errors = _result_errors(pipeline_result)
    status = "succeeded" if pipeline_result.succeeded else "failed"
    manifest.update(
        {
            "status": status,
            "finished_at": _utc_timestamp(finished_at),
            "exit_code": pipeline_result.exit_code,
            "run_id": pipeline_result.run.run_id,
            "run_dir": _portable_path(pipeline_result.run.run_dir, base=base),
            "run_manifest": _portable_path(pipeline_result.run.manifest_path, base=base),
            "product_run": product_run,
            "source_artifacts": _artifact_refs(pipeline_result.run.manifest),
            "alert_archive": _monitor_alert_archive_summary(status="not_run"),
            "warnings": _manifest_warnings(pipeline_result.run.manifest),
            "errors": errors,
        }
    )
    alert_archive = _archive_alert_decisions(
        pipeline_result,
        cycle_manifest=manifest,
        manifest_path=manifest_path,
        output_dir=output_dir,
        config_path=config_path,
        config_base=base,
        timestamp=finished_at,
        cooldown_seconds=settings.cooldown_seconds,
    )
    manifest["alert_archive"] = alert_archive
    write_json(manifest_path, manifest)
    LOGGER.log(
        logging.INFO if pipeline_result.succeeded else logging.WARNING,
        "Monitor cycle finished.",
        extra={
            "event": "monitor.cycle.finished",
            "cycle_id": cycle_id,
            "status": status,
            "run_id": pipeline_result.run.run_id,
            "target_stage": settings.target_stage,
            "no_codex": settings.no_codex,
            "exit_code": pipeline_result.exit_code,
            "reason": pipeline_result.reason,
        },
    )

    return MonitorCycleResult(
        succeeded=pipeline_result.succeeded,
        exit_code=pipeline_result.exit_code,
        cycle_id=cycle_id,
        status=status,
        target_stage=settings.target_stage,
        no_codex=settings.no_codex,
        manifest_path=manifest_path,
        run_id=pipeline_result.run.run_id,
        run_dir=pipeline_result.run.run_dir,
        run_manifest_path=pipeline_result.run.manifest_path,
        reason=pipeline_result.reason,
    )


def run_monitor_source_cycle(
    config: dict[str, Any],
    *,
    config_path: Path,
    now: datetime | None = None,
    pipeline_runner: PipelineRunner = run_pipeline,
    source_refresher: SourceRefresher | None = None,
    cycle_id: str | None = None,
    loop_id: str | None = None,
    cycle_sequence: int | None = None,
    trigger_source: str = "monitor_service",
) -> MonitorCycleResult:
    with mutation_lease(config_path=config_path, owner_kind="monitor", workflow="monitor_cycle", requested_by="Monitor"):
        return _run_monitor_source_cycle_unlocked(
            config,
            config_path=config_path,
            now=now,
            pipeline_runner=pipeline_runner,
            source_refresher=source_refresher,
            cycle_id=cycle_id,
            loop_id=loop_id,
            cycle_sequence=cycle_sequence,
            trigger_source=trigger_source,
        )


def _run_monitor_source_cycle_unlocked(
    config: dict[str, Any],
    *,
    config_path: Path,
    now: datetime | None = None,
    pipeline_runner: PipelineRunner = run_pipeline,
    source_refresher: SourceRefresher | None = None,
    cycle_id: str | None = None,
    loop_id: str | None = None,
    cycle_sequence: int | None = None,
    trigger_source: str = "monitor_service",
) -> MonitorCycleResult:
    settings = load_monitor_config(config)
    fixed_time = now is not None
    started_at = _coerce_utc(now or datetime.now(timezone.utc))
    cycle_id = cycle_id or _cycle_id(started_at)
    output_dir = _resolve_output_dir(settings.output_dir, config_path=config_path)
    manifest_path: Path | None = None
    base = artifact_base(config_path)
    output_ref = _portable_path(output_dir, base=base)
    repository = MonitorStateRepository(config_path=config_path)
    source_groups = _monitor_source_groups(config, settings)
    source_refresher = source_refresher or refresh_monitor_source
    previous_states = {state["source_key"]: state for state in repository.source_states(monitor_output_dir=output_ref)}
    due_groups = [
        group
        for group in source_groups
        if group.enabled and _source_due(previous_states.get(group.source_key, {}), at=started_at)
    ]
    latest_run_id: str | None = None
    latest_run_dir: Path | None = None
    latest_run_manifest_path: Path | None = None
    latest_run_manifest_ref: str | None = None
    latest_product_run: dict[str, Any] | None = None
    source_artifacts: dict[str, Any] = {}
    source_results: list[dict[str, Any]] = []
    states_by_key: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    errors: list[dict[str, str]] = []
    partial_reason: str | None = None

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "monitor_cycle_manifest",
        "cycle_id": cycle_id,
        "cycle_mode": "source_cadence",
        "loop_id": loop_id,
        "cycle_sequence": cycle_sequence,
        "trigger_source": trigger_source,
        "status": "running",
        "started_at": _utc_timestamp(started_at),
        "finished_at": None,
        "config_ref": _portable_path(config_path, base=base),
        "monitor_output_dir": output_ref,
        "target_stage": "refresh_data",
        "no_codex": True,
        "exit_code": None,
        "run_id": None,
        "run_dir": None,
        "run_manifest": None,
        "product_run": None,
        "source_artifacts": {},
        "source_cadence": {
            "source_groups": [_source_group_manifest(group, previous_states.get(group.source_key, {})) for group in source_groups],
            "due_sources": [group.source_key for group in due_groups],
            "changed_sources": [],
            "failed_sources": [],
            "source_results": [],
            "slow_tasks_excluded": list(SOURCE_CADENCE_EXCLUDED_TASKS),
        },
        "alert_archive": _monitor_alert_archive_summary(status="not_run"),
        "warnings": [],
        "errors": [],
    }
    LOGGER.info(
        "Monitor source cycle started.",
        extra={
            "event": "monitor.source_cycle.start",
            "cycle_id": cycle_id,
            "loop_id": loop_id,
            "cycle_sequence": cycle_sequence,
            "due_source_count": len(due_groups),
        },
    )

    for group in source_groups:
        previous = previous_states.get(group.source_key, {})
        if not group.enabled:
            states_by_key[group.source_key] = _disabled_source_state(group, previous)
            continue
        if group not in due_groups:
            states_by_key[group.source_key] = _waiting_source_state(group, previous)
            continue

        source_config = _source_scoped_config(config, group.source_key)
        try:
            refresh_result = source_refresher(
                source_config,
                config_path=config_path,
                group=group,
                started_at=started_at,
            )
        except Exception as exc:  # noqa: BLE001
            failure = _source_exception_result(group, previous, started_at=started_at, settings=settings, exc=exc)
            states_by_key[group.source_key] = failure["state"]
            source_results.append(failure["result"])
            errors.append({"stage": group.source_key, "message": failure["result"]["reason"]})
            partial_reason = "one or more monitor source groups failed"
            continue

        if not refresh_result.succeeded:
            failure = _failed_source_refresh_state(
                group,
                previous,
                result=refresh_result,
                started_at=started_at,
                settings=settings,
            )
            states_by_key[group.source_key] = failure["state"]
            source_results.append(failure["result"])
            errors.append(
                {
                    "stage": refresh_result.failed_stage or group.source_key,
                    "message": str(failure["result"]["reason"] or "source refresh failed"),
                }
            )
            partial_reason = "one or more monitor source groups failed"
            continue

        warnings.extend(f"{group.source_key}: {warning}" for warning in refresh_result.warnings)
        revision = refresh_result.revision or _stable_hash(
            {
                "source_key": group.source_key,
                "counts": refresh_result.counts,
                "source_artifacts": refresh_result.source_artifacts,
            }
        )
        changed = revision != previous.get("latest_published_data_revision")
        status = "changed" if changed else "no_change"
        state = _successful_source_state(
            group,
            previous,
            status=status,
            revision=revision,
            changed_scope=_source_changed_scope(config, group.source_key) if changed else {},
            started_at=started_at,
        )
        states_by_key[group.source_key] = state
        source_artifacts.update({f"{group.source_key}:{key}": value for key, value in refresh_result.source_artifacts.items()})
        source_results.append(
            {
                "source_key": group.source_key,
                "status": status,
                "changed": changed,
                "run_id": None,
                "run_manifest": None,
                "latest_published_data_revision": revision,
                "changed_scope": state["changed_scope"],
                "reason": None,
            }
        )

    if not due_groups:
        status = "no_due_sources"
    elif any(result.get("status") == "failed" for result in source_results):
        status = "partial"
    elif any(result.get("status") == "changed" for result in source_results):
        status = "changed"
    else:
        status = "no_change"

    finished_at = started_at if fixed_time else datetime.now(timezone.utc)
    updated_at = _utc_timestamp(finished_at)
    changed_sources = [str(result["source_key"]) for result in source_results if result.get("status") == "changed"]
    failed_sources = [str(result["source_key"]) for result in source_results if result.get("status") == "failed"]

    if changed_sources:
        try:
            pipeline_result = pipeline_runner(
                config,
                config_path=config_path,
                until_stage=settings.target_stage,
                skip_codex=settings.no_codex,
                run_trigger={
                    "source": "Monitor",
                    "intent": "monitor_reassessment",
                    "monitor_cycle_id": cycle_id,
                    "source_keys": changed_sources,
                },
            )
        except Exception as exc:  # noqa: BLE001
            status = "partial"
            reason = _source_error_message(str(exc) or "monitor reassessment failed")
            errors.append({"stage": settings.target_stage, "message": reason})
            partial_reason = "monitor reassessment failed"
        else:
            latest_run_id = pipeline_result.run.run_id
            latest_run_dir = pipeline_result.run.run_dir
            latest_run_manifest_path = pipeline_result.run.manifest_path
            latest_run_manifest_ref = _portable_path(pipeline_result.run.manifest_path, base=base)
            latest_product_run = _product_run_summary(pipeline_result, base=base)
            source_artifacts.update(_artifact_refs(pipeline_result.run.manifest))
            for source_key in changed_sources:
                states_by_key[source_key]["latest_run_id"] = latest_run_id
                states_by_key[source_key]["latest_run_manifest"] = latest_run_manifest_ref
            for result in source_results:
                if result.get("status") == "changed":
                    result["run_id"] = latest_run_id
                    result["run_manifest"] = latest_run_manifest_ref
            if not pipeline_result.succeeded:
                status = "partial"
                partial_reason = "monitor reassessment failed"
                errors.extend(_result_errors(pipeline_result))

    repository.save_source_states(
        [states_by_key[group.source_key] for group in source_groups],
        monitor_output_dir=output_ref,
        updated_at=updated_at,
    )
    manifest.update(
        {
            "status": status,
            "finished_at": updated_at,
            "exit_code": 0,
            "run_id": latest_run_id,
            "run_dir": _portable_path(latest_run_dir, base=base) if latest_run_dir is not None else None,
            "run_manifest": latest_run_manifest_ref,
            "product_run": latest_product_run,
            "source_artifacts": source_artifacts,
            "warnings": sorted(set(warnings)),
            "errors": errors,
        }
    )
    manifest["source_cadence"].update(
        {
            "changed_sources": changed_sources,
            "failed_sources": failed_sources,
            "source_results": source_results,
        }
    )
    if _source_cycle_needs_manifest(status):
        cycle_dir = _unique_cycle_dir(output_dir / "cycles", cycle_id)
        cycle_id = cycle_dir.name
        manifest["cycle_id"] = cycle_id
        manifest_path = cycle_dir / "monitor_cycle_manifest.json"
        write_json(manifest_path, manifest)
        _prune_monitor_cycle_dirs(output_dir / "cycles")
    _persist_monitor_cycle(config_path=config_path, manifest=manifest, manifest_path=manifest_path, output_dir=output_dir, base=base)
    LOGGER.info(
        "Monitor source cycle finished.",
        extra={
            "event": "monitor.source_cycle.finished",
            "cycle_id": cycle_id,
            "status": status,
            "changed_source_count": len(changed_sources),
            "failed_source_count": len(failed_sources),
        },
    )

    return MonitorCycleResult(
        succeeded=True,
        exit_code=0,
        cycle_id=cycle_id,
        status=status,
        target_stage="refresh_data",
        no_codex=True,
        manifest_path=manifest_path,
        run_id=latest_run_id,
        run_dir=latest_run_dir,
        run_manifest_path=latest_run_manifest_path,
        reason=None if status != "partial" else partial_reason or "one or more monitor source groups failed",
    )


def refresh_monitor_source(
    config: dict[str, Any],
    *,
    config_path: Path,
    group: MonitorSourceGroup,
    started_at: datetime,
) -> MonitorSourceRefreshResult:
    tasks = SOURCE_REFRESH_TASKS.get(group.source_key)
    if not tasks:
        return MonitorSourceRefreshResult(
            succeeded=False,
            exit_code=3,
            failed_stage=group.source_key,
            reason=f"unsupported monitor source group {group.source_key}",
            revision=None,
            source_artifacts={},
            counts={},
            warnings=[],
        )

    with TemporaryDirectory(prefix="halpha-monitor-source-") as temp_dir:
        run_dir = Path(temp_dir)
        raw_dir = run_dir / "raw"
        analysis_dir = run_dir / "analysis"
        codex_context_dir = run_dir / "codex_context"
        report_dir = run_dir / "report"
        for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
            directory.mkdir(parents=True, exist_ok=True)
        run = RunContext(
            run_id=f"monitor-source-{group.source_key}-{started_at.strftime('%Y%m%dT%H%M%SZ')}",
            run_dir=run_dir,
            raw_dir=raw_dir,
            analysis_dir=analysis_dir,
            codex_context_dir=codex_context_dir,
            report_dir=report_dir,
            manifest_path=run_dir / "monitor_source_refresh_manifest.json",
            config_path=config_path,
            manifest={
                "schema_version": 1,
                "run_id": f"monitor-source-{group.source_key}",
                "status": "running",
                "artifacts": {},
                "counts": {},
                "warnings": [],
                "errors": [],
            },
        )
        handlers = default_stage_handlers()
        try:
            for task in tasks:
                handlers[task](config, run)
        except PipelineError as exc:
            return MonitorSourceRefreshResult(
                succeeded=False,
                exit_code=exc.exit_code,
                failed_stage=exc.stage or group.source_key,
                reason=str(exc),
                revision=None,
                source_artifacts=_persistent_source_artifacts(run.manifest),
                counts=dict(run.manifest.get("counts")) if isinstance(run.manifest.get("counts"), dict) else {},
                warnings=_manifest_warnings(run.manifest),
            )

        run.manifest["status"] = "succeeded"
        revision = _source_revision(RunResult(True, run, 0, None, None), source_key=group.source_key)
        return MonitorSourceRefreshResult(
            succeeded=True,
            exit_code=0,
            failed_stage=None,
            reason=None,
            revision=revision,
            source_artifacts=_persistent_source_artifacts(run.manifest),
            counts=dict(run.manifest.get("counts")) if isinstance(run.manifest.get("counts"), dict) else {},
            warnings=_manifest_warnings(run.manifest),
        )


def run_monitor_loop(
    config: dict[str, Any],
    *,
    config_path: Path,
    max_cycles: int,
    interval_seconds: int,
    now: datetime | None = None,
    pipeline_runner: PipelineRunner = run_pipeline,
    sleeper: Sleeper = time.sleep,
) -> MonitorLoopResult:
    with mutation_lease(config_path=config_path, owner_kind="monitor", workflow="monitor_cycle", requested_by="Monitor"):
        return _run_monitor_loop_unlocked(
            config,
            config_path=config_path,
            max_cycles=max_cycles,
            interval_seconds=interval_seconds,
            now=now,
            pipeline_runner=pipeline_runner,
            sleeper=sleeper,
        )


def _run_monitor_loop_unlocked(
    config: dict[str, Any],
    *,
    config_path: Path,
    max_cycles: int,
    interval_seconds: int,
    now: datetime | None = None,
    pipeline_runner: PipelineRunner = run_pipeline,
    sleeper: Sleeper = time.sleep,
) -> MonitorLoopResult:
    settings = load_monitor_config(config)
    if max_cycles <= 0:
        raise ValueError("max_cycles must be a positive integer.")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be a positive integer.")

    output_dir = _resolve_output_dir(settings.output_dir, config_path=config_path)
    base = artifact_base(config_path)
    started_at = _coerce_utc(now or datetime.now(timezone.utc))
    loop_id = f"loop-{started_at.strftime('%Y%m%dT%H%M%S%fZ')}"
    cycle_results: list[MonitorCycleResult] = []
    status = "succeeded"
    stop_reason = "max_cycles_reached"
    reason: str | None = None
    LOGGER.info(
        "Monitor loop started.",
        extra={
            "event": "monitor.loop.start",
            "loop_id": loop_id,
            "max_cycles": max_cycles,
            "interval_seconds": interval_seconds,
        },
    )

    for index in range(max_cycles):
        cycle_now = started_at + timedelta(seconds=interval_seconds * index) if now is not None else None
        result = run_monitor_cycle(
            config,
            config_path=config_path,
            now=cycle_now,
            pipeline_runner=pipeline_runner,
            cycle_mode="loop",
            loop_id=loop_id,
            cycle_sequence=index + 1,
        )
        cycle_results.append(result)
        if not result.succeeded:
            status = "failed"
            stop_reason = "cycle_failed"
            reason = result.reason or "monitor cycle failed"
            break
        if index < max_cycles - 1 and now is None:
            sleeper(interval_seconds)

    finished_at = started_at if now is not None else datetime.now(timezone.utc)
    updated_at = _utc_timestamp(finished_at)
    repository = MonitorStateRepository(config_path=config_path)
    repository.save_loop(
        {
            "loop_id": loop_id,
            "status": status,
            "max_cycles": max_cycles,
            "completed_cycles": len(cycle_results),
            "stop_reason": stop_reason,
            "started_at": _utc_timestamp(started_at),
            "finished_at": updated_at,
            "latest_cycle_id": cycle_results[-1].cycle_id if cycle_results else None,
            "reason": reason,
        },
        monitor_output_dir=_portable_path(output_dir, base=base),
        updated_at=updated_at,
    )
    health_state_path = runtime_state_path(config_path=config_path)
    LOGGER.log(
        logging.INFO if status == "succeeded" else logging.WARNING,
        "Monitor loop finished.",
        extra={
            "event": "monitor.loop.finished",
            "loop_id": loop_id,
            "status": status,
            "max_cycles": max_cycles,
            "completed_cycles": len(cycle_results),
            "stop_reason": stop_reason,
            "reason": reason,
        },
    )
    return MonitorLoopResult(
        succeeded=status == "succeeded",
        exit_code=0 if status == "succeeded" else (cycle_results[-1].exit_code if cycle_results else 3),
        loop_id=loop_id,
        status=status,
        max_cycles=max_cycles,
        completed_cycles=len(cycle_results),
        stop_reason=stop_reason,
        cycle_results=cycle_results,
        health_state_path=health_state_path,
        reason=reason,
    )


def inspect_monitor_health(config: dict[str, Any], *, config_path: Path) -> MonitorInspectionResult:
    settings = load_monitor_config(config)
    output_dir = _resolve_output_dir(settings.output_dir, config_path=config_path)
    base = artifact_base(config_path)
    health_state = MonitorStateRepository(config_path=config_path).health_state(
        monitor_output_dir=_portable_path(output_dir, base=base),
        base=base,
    )
    lines = [
        "Halpha monitor inspection succeeded.",
        f"monitor_output_dir: {_portable_path(output_dir, base=base)}",
        f"service_status: {health_state.get('service', {}).get('status', 'missing')}",
        f"service_instance_id: {health_state.get('service', {}).get('service_instance_id') or 'none'}",
        f"service_current_cycle_id: {health_state.get('service', {}).get('current_cycle_id') or 'none'}",
        f"service_consecutive_failures: {health_state.get('service', {}).get('consecutive_failures', 0)}",
        f"service_next_retry_at: {health_state.get('service', {}).get('next_retry_at') or 'none'}",
        f"latest_cycle_id: {health_state['latest_cycle_id']}",
        f"latest_cycle_status: {health_state['latest_cycle_status']}",
        f"latest_run_id: {health_state['latest_run_id']}",
        f"latest_run_manifest: {health_state['latest_run_manifest']}",
        f"cycle_count: {health_state['cycle_count']}",
        f"failed_cycle_count: {health_state['failed_cycle_count']}",
        f"alert_archive_status: {health_state['alert_archive_status']}",
        f"alert_records: {health_state['alert_counts']['records']}",
        f"alert_emitted: {health_state['alert_counts']['emitted']}",
        f"alert_suppressed_duplicate: {health_state['alert_counts']['suppressed_duplicate']}",
        f"alert_suppressed_cooldown: {health_state['alert_counts']['suppressed_cooldown']}",
        f"alert_suppressed_no_alert: {health_state['alert_counts']['suppressed_no_alert']}",
        f"alert_skipped: {health_state['alert_counts']['skipped']}",
        f"cooldown_records: {health_state['cooldown_records']}",
        f"warning_count: {health_state['warning_count']}",
        f"error_count: {health_state['error_count']}",
        f"health_state: {health_state['health_state_path']}",
    ]
    loop = health_state.get("latest_loop")
    if isinstance(loop, dict) and loop:
        lines.extend(
            [
                f"latest_loop_id: {loop.get('loop_id', 'none')}",
                f"latest_loop_status: {loop.get('status', 'unknown')}",
                f"latest_loop_completed_cycles: {loop.get('completed_cycles', 0)}",
                f"latest_loop_stop_reason: {loop.get('stop_reason', 'unknown')}",
            ]
        )
    source_states = health_state.get("source_states")
    if isinstance(source_states, list) and source_states:
        lines.append(f"source_state_count: {len(source_states)}")
        for state in source_states:
            if not isinstance(state, dict):
                continue
            source_key = _clean_text(state.get("source_key"))
            lines.extend(
                [
                    f"source_{source_key}_enabled: {str(state.get('enabled') is True).lower()}",
                    f"source_{source_key}_status: {state.get('status') or 'unknown'}",
                    f"source_{source_key}_cadence_seconds: {_positive_int(state.get('cadence_seconds'))}",
                    f"source_{source_key}_next_attempt_at: {state.get('next_attempt_at') or 'none'}",
                    f"source_{source_key}_consecutive_failures: {_positive_int(state.get('consecutive_failures'))}",
                    f"source_{source_key}_latest_revision: {state.get('latest_published_data_revision') or 'none'}",
                    f"source_{source_key}_latest_run_manifest: {state.get('latest_run_manifest') or 'none'}",
                ]
            )
    return MonitorInspectionResult(True, 0, lines)


def monitor_config_lines(settings: MonitorConfig) -> list[str]:
    return [
        f"enabled: {str(settings.enabled).lower()}",
        f"interval_seconds: {settings.interval_seconds}",
        f"max_cycles: {settings.max_cycles}",
        f"failure_backoff_max_seconds: {settings.failure_backoff_max_seconds}",
        f"cooldown_seconds: {settings.cooldown_seconds}",
        f"output_dir: {settings.output_dir.as_posix()}",
        f"target_stage: {settings.target_stage}",
        f"no_codex: {str(settings.no_codex).lower()}",
        f"source_cadence_seconds: {_format_source_cadences(settings)}",
    ]


def _source_cadence_config(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int(item)
        for key, item in value.items()
        if isinstance(key, str) and key in MONITOR_SOURCE_KEYS and isinstance(item, int) and not isinstance(item, bool) and item > 0
    }


def _format_source_cadences(settings: MonitorConfig) -> str:
    groups = _monitor_source_groups({}, settings)
    return ", ".join(f"{group.source_key}={group.cadence_seconds}" for group in groups)


def _monitor_source_groups(config: dict[str, Any], settings: MonitorConfig) -> list[MonitorSourceGroup]:
    return [
        MonitorSourceGroup(
            source_key=source_key,
            enabled=_source_enabled(config, source_key),
            cadence_seconds=_source_cadence_seconds(settings, source_key),
        )
        for source_key in MONITOR_SOURCE_KEYS
    ]


def _source_cadence_seconds(settings: MonitorConfig, source_key: str) -> int:
    if source_key in settings.source_cadence_seconds:
        return settings.source_cadence_seconds[source_key]
    if source_key in SLOW_MONITOR_SOURCE_KEYS:
        return max(settings.interval_seconds, DEFAULT_MONITOR_SLOW_SOURCE_CADENCE_SECONDS)
    return settings.interval_seconds


def _source_enabled(config: dict[str, Any], source_key: str) -> bool:
    market = _dict(config.get("market"))
    if source_key == "derivatives":
        derivatives = _dict(market.get("derivatives"))
        return derivatives.get("enabled") is True
    if source_key == "market":
        return market.get("enabled") is True
    if source_key == "macro_calendar":
        return _dict(config.get("macro_calendar")).get("enabled") is True
    if source_key == "onchain_flow":
        return _dict(config.get("onchain_flow")).get("enabled") is True
    if source_key == "text":
        return _dict(config.get("text")).get("enabled") is True
    return False


def _source_due(state: dict[str, Any], *, at: datetime) -> bool:
    next_attempt = _parse_utc_timestamp(state.get("next_attempt_at"))
    return next_attempt is None or at >= next_attempt


def _source_group_manifest(group: MonitorSourceGroup, previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_key": group.source_key,
        "enabled": group.enabled,
        "cadence_seconds": group.cadence_seconds,
        "status": previous.get("status") if isinstance(previous.get("status"), str) else None,
        "next_attempt_at": previous.get("next_attempt_at") if isinstance(previous.get("next_attempt_at"), str) else None,
        "latest_published_data_revision": previous.get("latest_published_data_revision")
        if isinstance(previous.get("latest_published_data_revision"), str)
        else None,
    }


def _source_scoped_config(config: dict[str, Any], source_key: str) -> dict[str, Any]:
    scoped = deepcopy(config if isinstance(config, dict) else {})
    monitor = _dict(scoped.get("monitor"))
    if monitor is not scoped.get("monitor"):
        scoped["monitor"] = monitor
    monitor["target_stage"] = "refresh_data"
    monitor["no_codex"] = True

    market = _dict(scoped.get("market"))
    if market is not scoped.get("market"):
        scoped["market"] = market
    derivatives = _dict(market.get("derivatives"))
    if derivatives is not market.get("derivatives"):
        market["derivatives"] = derivatives

    if source_key != "market":
        market["enabled"] = False
    if source_key != "derivatives":
        derivatives["enabled"] = False

    macro_calendar = _dict(scoped.get("macro_calendar"))
    if macro_calendar or source_key == "macro_calendar":
        scoped["macro_calendar"] = macro_calendar
        macro_calendar["enabled"] = source_key == "macro_calendar"

    onchain_flow = _dict(scoped.get("onchain_flow"))
    if onchain_flow or source_key == "onchain_flow":
        scoped["onchain_flow"] = onchain_flow
        onchain_flow["enabled"] = source_key == "onchain_flow"

    text = _dict(scoped.get("text"))
    if text is not scoped.get("text"):
        scoped["text"] = text
    text["enabled"] = source_key == "text"

    codex = _dict(scoped.get("codex"))
    if codex is not scoped.get("codex"):
        scoped["codex"] = codex
    codex["enabled"] = False
    return scoped


def _waiting_source_state(group: MonitorSourceGroup, previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_key": group.source_key,
        "enabled": True,
        "cadence_seconds": group.cadence_seconds,
        "status": str(previous.get("status") or "waiting"),
        "last_attempt_at": previous.get("last_attempt_at") if isinstance(previous.get("last_attempt_at"), str) else None,
        "last_success_at": previous.get("last_success_at") if isinstance(previous.get("last_success_at"), str) else None,
        "next_attempt_at": previous.get("next_attempt_at") if isinstance(previous.get("next_attempt_at"), str) else None,
        "consecutive_failures": _positive_int(previous.get("consecutive_failures")),
        "backoff_seconds": _positive_int(previous.get("backoff_seconds")),
        "last_error": _dict(previous.get("last_error")),
        "latest_published_data_revision": previous.get("latest_published_data_revision")
        if isinstance(previous.get("latest_published_data_revision"), str)
        else None,
        "changed_scope": _dict(previous.get("changed_scope")),
        "latest_run_id": previous.get("latest_run_id") if isinstance(previous.get("latest_run_id"), str) else None,
        "latest_run_manifest": previous.get("latest_run_manifest") if isinstance(previous.get("latest_run_manifest"), str) else None,
    }


def _disabled_source_state(group: MonitorSourceGroup, previous: dict[str, Any]) -> dict[str, Any]:
    state = _waiting_source_state(group, previous)
    state.update(
        {
            "enabled": False,
            "status": "disabled",
            "next_attempt_at": None,
            "consecutive_failures": 0,
            "backoff_seconds": 0,
            "last_error": {},
        }
    )
    return state


def _successful_source_state(
    group: MonitorSourceGroup,
    previous: dict[str, Any],
    *,
    status: str,
    revision: str,
    changed_scope: dict[str, Any],
    started_at: datetime,
) -> dict[str, Any]:
    return {
        "source_key": group.source_key,
        "enabled": True,
        "cadence_seconds": group.cadence_seconds,
        "status": status,
        "last_attempt_at": _utc_timestamp(started_at),
        "last_success_at": _utc_timestamp(started_at),
        "next_attempt_at": _utc_timestamp(started_at + timedelta(seconds=group.cadence_seconds)),
        "consecutive_failures": 0,
        "backoff_seconds": 0,
        "last_error": {},
        "latest_published_data_revision": revision,
        "changed_scope": changed_scope,
        "latest_run_id": previous.get("latest_run_id") if isinstance(previous.get("latest_run_id"), str) else None,
        "latest_run_manifest": previous.get("latest_run_manifest") if isinstance(previous.get("latest_run_manifest"), str) else None,
    }


def _failed_source_refresh_state(
    group: MonitorSourceGroup,
    previous: dict[str, Any],
    *,
    result: MonitorSourceRefreshResult,
    started_at: datetime,
    settings: MonitorConfig,
) -> dict[str, Any]:
    consecutive_failures = _positive_int(previous.get("consecutive_failures")) + 1
    backoff_seconds = _source_backoff_seconds(group.cadence_seconds, settings.failure_backoff_max_seconds, consecutive_failures)
    reason = _source_error_message(result.reason or "source refresh failed")
    state = {
        "source_key": group.source_key,
        "enabled": True,
        "cadence_seconds": group.cadence_seconds,
        "status": "failed",
        "last_attempt_at": _utc_timestamp(started_at),
        "last_success_at": previous.get("last_success_at") if isinstance(previous.get("last_success_at"), str) else None,
        "next_attempt_at": _utc_timestamp(started_at + timedelta(seconds=backoff_seconds)),
        "consecutive_failures": consecutive_failures,
        "backoff_seconds": backoff_seconds,
        "last_error": {
            "stage": result.failed_stage or "refresh_data",
            "message": reason,
            "private_values_embedded": False,
        },
        "latest_published_data_revision": previous.get("latest_published_data_revision")
        if isinstance(previous.get("latest_published_data_revision"), str)
        else None,
        "changed_scope": {},
        "latest_run_id": previous.get("latest_run_id") if isinstance(previous.get("latest_run_id"), str) else None,
        "latest_run_manifest": previous.get("latest_run_manifest") if isinstance(previous.get("latest_run_manifest"), str) else None,
    }
    return {
        "state": state,
        "result": {
            "source_key": group.source_key,
            "status": "failed",
            "changed": False,
            "run_id": None,
            "run_manifest": None,
            "latest_published_data_revision": state["latest_published_data_revision"],
            "changed_scope": {},
            "reason": reason,
        },
    }


def _source_exception_result(
    group: MonitorSourceGroup,
    previous: dict[str, Any],
    *,
    started_at: datetime,
    settings: MonitorConfig,
    exc: Exception,
) -> dict[str, Any]:
    consecutive_failures = _positive_int(previous.get("consecutive_failures")) + 1
    backoff_seconds = _source_backoff_seconds(group.cadence_seconds, settings.failure_backoff_max_seconds, consecutive_failures)
    reason = _source_error_message(str(exc) or "source refresh failed")
    state = {
        "source_key": group.source_key,
        "enabled": True,
        "cadence_seconds": group.cadence_seconds,
        "status": "failed",
        "last_attempt_at": _utc_timestamp(started_at),
        "last_success_at": previous.get("last_success_at") if isinstance(previous.get("last_success_at"), str) else None,
        "next_attempt_at": _utc_timestamp(started_at + timedelta(seconds=backoff_seconds)),
        "consecutive_failures": consecutive_failures,
        "backoff_seconds": backoff_seconds,
        "last_error": {
            "stage": "refresh_data",
            "message": reason,
            "private_values_embedded": False,
        },
        "latest_published_data_revision": previous.get("latest_published_data_revision")
        if isinstance(previous.get("latest_published_data_revision"), str)
        else None,
        "changed_scope": {},
        "latest_run_id": previous.get("latest_run_id") if isinstance(previous.get("latest_run_id"), str) else None,
        "latest_run_manifest": previous.get("latest_run_manifest") if isinstance(previous.get("latest_run_manifest"), str) else None,
    }
    return {
        "state": state,
        "result": {
            "source_key": group.source_key,
            "status": "failed",
            "changed": False,
            "run_id": None,
            "run_manifest": None,
            "latest_published_data_revision": state["latest_published_data_revision"],
            "changed_scope": {},
            "reason": reason,
        },
    }


def _source_backoff_seconds(cadence_seconds: int, max_seconds: int, consecutive_failures: int) -> int:
    exponent = max(0, consecutive_failures - 1)
    return max(1, min(max_seconds, cadence_seconds * (2**exponent)))


def _source_revision(result: RunResult, *, source_key: str) -> str:
    manifest = result.run.manifest
    explicit = manifest.get("monitor_source_revision")
    if isinstance(explicit, str) and explicit:
        return explicit
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    artifact_refs = sorted(set(_artifact_ref_values(artifacts)))
    payload = {
        "source_key": source_key,
        "artifacts": artifacts,
        "counts": manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {},
        "artifact_digests": {
            ref: _artifact_file_digest(result.run.run_dir, ref)
            for ref in artifact_refs
        },
    }
    return _stable_hash(payload)


def _artifact_ref_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        refs: list[str] = []
        for item in value:
            refs.extend(_artifact_ref_values(item))
        return refs
    if isinstance(value, dict):
        refs: list[str] = []
        for item in value.values():
            refs.extend(_artifact_ref_values(item))
        return refs
    return []


def _artifact_file_digest(run_dir: Path, ref: str) -> str:
    path = Path(ref)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        return "outside-run"
    artifact_path = run_dir / path
    if not artifact_path.is_file():
        return "missing"
    digest = hashlib.sha256()
    with artifact_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_changed_scope(config: dict[str, Any], source_key: str) -> dict[str, Any]:
    market = _dict(config.get("market"))
    if source_key == "market":
        ohlcv = _dict(market.get("ohlcv"))
        return {
            "symbols": _string_list(market.get("symbols")),
            "timeframes": _string_list(ohlcv.get("timeframes")),
        }
    if source_key == "derivatives":
        derivatives = _dict(market.get("derivatives"))
        return {
            "symbols": _string_list(derivatives.get("symbols")),
            "data_classes": _string_list(derivatives.get("data_classes")),
            "periods": _string_list(derivatives.get("periods")),
        }
    if source_key == "text":
        raw_sources = _dict(config.get("text")).get("sources")
        sources = raw_sources if isinstance(raw_sources, list) else []
        return {
            "sources": sorted(
                str(source.get("name")).strip()
                for source in sources
                if isinstance(source, dict) and isinstance(source.get("name"), str) and str(source.get("name")).strip()
            )
        }
    if source_key == "macro_calendar":
        macro_calendar = _dict(config.get("macro_calendar"))
        return {
            "regions": _string_list(macro_calendar.get("regions")),
            "data_classes": _string_list(macro_calendar.get("data_classes")),
        }
    if source_key == "onchain_flow":
        onchain_flow = _dict(config.get("onchain_flow"))
        return {
            "assets": _string_list(onchain_flow.get("assets")),
            "chains": _string_list(onchain_flow.get("chains")),
            "data_classes": _string_list(onchain_flow.get("data_classes")),
        }
    return {}


def _source_error_message(message: str) -> str:
    text = str(message or "source refresh failed").strip()
    if not text:
        return "source refresh failed"
    lowered = text.lower()
    private_markers = ("\\", "/", "://", "token", "secret", "cookie", "proxy", "password")
    if any(marker in lowered for marker in private_markers):
        return "monitor source refresh error redacted; inspect local logs."
    return text[:500]


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _resolve_output_dir(output_dir: Path, *, config_path: Path) -> Path:
    if output_dir.is_absolute():
        return output_dir
    return artifact_base(config_path) / output_dir


def _unique_cycle_dir(parent: Path, cycle_id: str) -> Path:
    candidate = parent / cycle_id
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{cycle_id}-{suffix}"
        suffix += 1
    return candidate


def _source_cycle_needs_manifest(status: str) -> bool:
    return status not in {"no_due_sources", "no_change"}


def _prune_monitor_cycle_dirs(cycles_dir: Path) -> None:
    limit = max(0, int(MONITOR_DIAGNOSTIC_CYCLE_DIR_LIMIT))
    if not cycles_dir.exists():
        return
    cycle_dirs = sorted((path for path in cycles_dir.iterdir() if path.is_dir()), key=_cycle_dir_sort_key)
    stale = cycle_dirs[:-limit] if limit else cycle_dirs
    try:
        resolved_root = cycles_dir.resolve()
    except OSError:
        return
    for path in stale:
        try:
            path.resolve().relative_to(resolved_root)
        except (OSError, ValueError):
            continue
        shutil.rmtree(path, ignore_errors=True)


def _cycle_dir_sort_key(path: Path) -> tuple[int, str]:
    try:
        return path.stat().st_mtime_ns, path.name
    except OSError:
        return 0, path.name


def _cycle_id(now: datetime) -> str:
    return f"cycle-{now.strftime('%Y%m%dT%H%M%S%fZ')}"


def _utc_timestamp(value: datetime) -> str:
    return _coerce_utc(value).isoformat().replace("+00:00", "Z")


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _portable_path(path: Path, *, base: Path) -> str:
    resolved_base = base.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_base).as_posix()
    except ValueError:
        return path.name


def _product_run_summary(result: RunResult, *, base: Path) -> dict[str, Any]:
    return {
        "run_id": result.run.run_id,
        "status": result.run.manifest.get("status"),
        "exit_code": result.exit_code,
        "failed_stage": result.failed_stage,
        "reason": result.reason,
        "run_dir": _portable_path(result.run.run_dir, base=base),
        "run_manifest": _portable_path(result.run.manifest_path, base=base),
    }


def _artifact_refs(manifest: dict[str, Any]) -> dict[str, str]:
    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return {}
    return {str(key): str(value) for key, value in sorted(artifacts.items()) if isinstance(value, str)}


def _persistent_source_artifacts(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        key: value
        for key, value in _artifact_refs(manifest).items()
        if not value.startswith(("raw/", "analysis/", "codex_context/", "report/"))
    }


def _manifest_warnings(manifest: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    manifest_warnings = manifest.get("warnings", [])
    if isinstance(manifest_warnings, list):
        warnings.extend(str(warning) for warning in manifest_warnings if warning)
    stages = manifest.get("stages", [])
    if isinstance(stages, list):
        for stage in stages:
            if not isinstance(stage, dict):
                continue
            stage_warnings = stage.get("warnings", [])
            if isinstance(stage_warnings, list):
                warnings.extend(str(warning) for warning in stage_warnings if warning)
    return sorted(set(warnings))


def _result_errors(result: RunResult) -> list[dict[str, str]]:
    if result.succeeded:
        return []
    return [
        {
            "stage": result.failed_stage or "pipeline",
            "message": result.reason or "pipeline failed without a reason",
        }
    ]


def _monitor_alert_archive_summary(*, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "state_store": MONITOR_STATE_STORE_ARTIFACT,
        "archive": MONITOR_STATE_STORE_ARTIFACT,
        "cooldown_state": MONITOR_STATE_STORE_ARTIFACT,
        "archive_state": MONITOR_STATE_STORE_ARTIFACT,
        "counts": _empty_alert_archive_counts(),
        "warnings": [],
        "errors": [],
    }


def _persist_monitor_cycle(
    *,
    config_path: Path,
    manifest: dict[str, Any],
    manifest_path: Path | None,
    output_dir: Path,
    base: Path,
) -> None:
    updated_at = _clean_text(manifest.get("finished_at"), fallback=_utc_timestamp(datetime.now(timezone.utc)))
    MonitorStateRepository(config_path=config_path).save_cycle(
        _monitor_cycle_state_record(manifest, manifest_path=manifest_path, output_dir=output_dir, base=base),
        updated_at=updated_at,
    )


def _persist_monitor_archive(
    *,
    config_path: Path,
    cycle_manifest: dict[str, Any],
    manifest_path: Path,
    output_dir: Path,
    base: Path,
    timestamp: datetime,
    summary: dict[str, Any],
    archive_records: list[dict[str, Any]],
    build_archive: Callable[[dict[str, dict[str, Any]]], MonitorArchivePersistence] | None = None,
) -> dict[str, Any]:
    def default_builder(cooldown_state: dict[str, dict[str, Any]]) -> MonitorArchivePersistence:
        return MonitorArchivePersistence(
            summary=summary,
            records=archive_records,
            cooldown_records=cooldown_state,
        )

    return MonitorStateRepository(config_path=config_path).persist_cycle_with_archive_builder(
        _monitor_cycle_state_record(cycle_manifest, manifest_path=manifest_path, output_dir=output_dir, base=base),
        build_archive=build_archive or default_builder,
        updated_at=_utc_timestamp(timestamp),
    )


def _monitor_cycle_state_record(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None,
    output_dir: Path,
    base: Path,
) -> dict[str, Any]:
    cycle_manifest_ref = _portable_path(manifest_path, base=base) if manifest_path is not None else MONITOR_STATE_STORE_ARTIFACT
    return {
        "cycle_id": _clean_text(manifest.get("cycle_id")),
        "monitor_output_dir": _portable_path(output_dir, base=base),
        "cycle_manifest": cycle_manifest_ref,
        "cycle_mode": _clean_text(manifest.get("cycle_mode")),
        "loop_id": manifest.get("loop_id") if isinstance(manifest.get("loop_id"), str) else None,
        "cycle_sequence": manifest.get("cycle_sequence"),
        "trigger_source": _clean_text(manifest.get("trigger_source")),
        "status": _clean_text(manifest.get("status")),
        "started_at": _clean_text(manifest.get("started_at")),
        "finished_at": manifest.get("finished_at") if isinstance(manifest.get("finished_at"), str) else None,
        "config_ref": _clean_text(manifest.get("config_ref")),
        "target_stage": _clean_text(manifest.get("target_stage")),
        "no_codex": manifest.get("no_codex") is True,
        "exit_code": manifest.get("exit_code"),
        "run_id": manifest.get("run_id") if isinstance(manifest.get("run_id"), str) else None,
        "run_dir": manifest.get("run_dir") if isinstance(manifest.get("run_dir"), str) else None,
        "run_manifest": manifest.get("run_manifest") if isinstance(manifest.get("run_manifest"), str) else None,
        "product_run": manifest.get("product_run") if isinstance(manifest.get("product_run"), dict) else {},
        "source_artifacts": manifest.get("source_artifacts") if isinstance(manifest.get("source_artifacts"), dict) else {},
        "alert_archive": manifest.get("alert_archive") if isinstance(manifest.get("alert_archive"), dict) else {},
        "warnings": manifest.get("warnings") if isinstance(manifest.get("warnings"), list) else [],
        "errors": [
            str(error.get("message") or error)
            if isinstance(error, dict)
            else str(error)
            for error in manifest.get("errors", [])
            if error
        ]
        if isinstance(manifest.get("errors"), list)
        else [],
    }


def _archive_alert_decisions(
    result: RunResult,
    *,
    cycle_manifest: dict[str, Any],
    manifest_path: Path,
    output_dir: Path,
    config_path: Path,
    config_base: Path,
    timestamp: datetime,
    cooldown_seconds: int,
) -> dict[str, Any]:
    summary: dict[str, Any] = _monitor_alert_archive_summary(status="skipped")

    artifact_ref = _alert_decisions_artifact_ref(result.run.manifest)
    if not artifact_ref:
        summary["warnings"].append("analysis/alert_decisions.json was not produced by the linked run.")
        return _persist_monitor_archive(
            config_path=config_path,
            cycle_manifest=cycle_manifest,
            manifest_path=manifest_path,
            output_dir=output_dir,
            base=config_base,
            timestamp=timestamp,
            summary=summary,
            archive_records=[],
        )

    artifact_path = result.run.run_dir / artifact_ref
    artifact, error = _read_alert_decisions_artifact(artifact_path)
    if error:
        summary["status"] = "degraded"
        summary["errors"].append(error)
        return _persist_monitor_archive(
            config_path=config_path,
            cycle_manifest=cycle_manifest,
            manifest_path=manifest_path,
            output_dir=output_dir,
            base=config_base,
            timestamp=timestamp,
            summary=summary,
            archive_records=[],
        )

    records = artifact.get("records")
    if not isinstance(records, list):
        summary["status"] = "degraded"
        summary["errors"].append("analysis/alert_decisions.json records must be a list.")
        return _persist_monitor_archive(
            config_path=config_path,
            cycle_manifest=cycle_manifest,
            manifest_path=manifest_path,
            output_dir=output_dir,
            base=config_base,
            timestamp=timestamp,
            summary=summary,
            archive_records=[],
        )

    def build_archive(cooldown_state: dict[str, dict[str, Any]]) -> MonitorArchivePersistence:
        archive_summary = _monitor_alert_archive_summary(status="skipped")
        archive_records: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        created_at = _utc_timestamp(timestamp)

        for index, record in enumerate(records):
            archive_record = _alert_archive_record(
                record,
                index=index,
                cycle_id=str(cycle_manifest.get("cycle_id") or ""),
                created_at=created_at,
                timestamp=timestamp,
                cooldown_seconds=cooldown_seconds,
                cooldown_state=cooldown_state,
                seen_keys=seen_keys,
                run=result.run,
                config_base=config_base,
            )
            archive_records.append(archive_record)
            status = str(archive_record["status"])
            archive_summary["counts"][status] = archive_summary["counts"].get(status, 0) + 1
            archive_summary["counts"]["records"] += 1

        if archive_records:
            archive_summary["status"] = "succeeded"
        else:
            archive_summary["warnings"].append("analysis/alert_decisions.json contained no alert decision records.")

        return MonitorArchivePersistence(
            summary=archive_summary,
            records=archive_records,
            cooldown_records=cooldown_state,
        )

    return _persist_monitor_archive(
        config_path=config_path,
        cycle_manifest=cycle_manifest,
        manifest_path=manifest_path,
        output_dir=output_dir,
        base=config_base,
        timestamp=timestamp,
        summary=summary,
        archive_records=[],
        build_archive=build_archive,
    )


def _alert_decisions_artifact_ref(manifest: dict[str, Any]) -> str | None:
    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return None
    value = artifacts.get("alert_decisions")
    if not isinstance(value, str) or not value:
        return None
    return value


def _read_alert_decisions_artifact(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{ALERT_DECISIONS_ARTIFACT} was referenced but not found."
    except json.JSONDecodeError as exc:
        return {}, f"{ALERT_DECISIONS_ARTIFACT} is not valid JSON: {exc.msg}."
    if not isinstance(data, dict):
        return {}, f"{ALERT_DECISIONS_ARTIFACT} must be a JSON object."
    return data, None


def _alert_archive_record(
    record: Any,
    *,
    index: int,
    cycle_id: str,
    created_at: str,
    timestamp: datetime,
    cooldown_seconds: int,
    cooldown_state: dict[str, Any],
    seen_keys: set[str],
    run: Any,
    config_base: Path,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        return _skipped_alert_record(
            index=index,
            cycle_id=cycle_id,
            created_at=created_at,
            run=run,
            config_base=config_base,
            reason="alert_decision_record_not_mapping",
        )

    decision_id = _clean_text(record.get("alert_decision_id"))
    priority = _clean_text(record.get("priority"), fallback="unknown")
    attention_decision = _clean_text(record.get("attention_decision"), fallback="unknown")
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    symbol = _clean_text(scope.get("symbol"), fallback="unknown")
    timeframe = _clean_text(scope.get("timeframe"), fallback="unknown")
    source_artifacts = _string_list(record.get("source_artifacts"))
    insufficient_reasons = _insufficient_alert_reasons(
        decision_id=decision_id,
        priority=priority,
        attention_decision=attention_decision,
        symbol=symbol,
        timeframe=timeframe,
    )
    alert_key = _alert_key(record, fallback_index=index)
    status = "emitted"
    suppression_reasons: list[str] = []
    cooldown_until: str | None = None

    if insufficient_reasons:
        status = "skipped"
        suppression_reasons = insufficient_reasons
    elif priority == "no_alert" or attention_decision == "no_alert":
        status = "suppressed_no_alert"
        suppression_reasons = ["priority_no_alert"]
    elif alert_key in seen_keys:
        status = "suppressed_duplicate"
        suppression_reasons = ["duplicate_alert_key_in_cycle"]
    else:
        seen_keys.add(alert_key)
        cooldown_record = _dict(cooldown_state.get(alert_key))
        existing_cooldown_until = _parse_utc_timestamp(cooldown_record.get("cooldown_until"))
        if existing_cooldown_until and timestamp < existing_cooldown_until:
            status = "suppressed_cooldown"
            suppression_reasons = ["cooldown_active"]
            cooldown_until = _utc_timestamp(existing_cooldown_until)
        else:
            cooldown_until_dt = timestamp + timedelta(seconds=cooldown_seconds)
            cooldown_until = _utc_timestamp(cooldown_until_dt)
            cooldown_state[alert_key] = {
                "alert_key": alert_key,
                "cooldown_until": cooldown_until,
                "last_emitted_at": created_at,
                "last_record_id": _record_id(cycle_id=cycle_id, index=index, alert_key=alert_key),
                "decision_id": decision_id,
                "priority": priority,
                "attention_decision": attention_decision,
                "source_artifacts": source_artifacts,
            }

    return {
        "schema_version": 1,
        "artifact_type": "monitor_alert_archive_record",
        "record_id": _record_id(cycle_id=cycle_id, index=index, alert_key=alert_key),
        "cycle_id": cycle_id,
        "created_at": created_at,
        "status": status,
        "alert_key": alert_key,
        "decision_id": decision_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "priority": priority,
        "attention_decision": attention_decision,
        "requires_user_attention": record.get("requires_user_attention") is True,
        "suppression_reasons": suppression_reasons,
        "cooldown_until": cooldown_until,
        "source_artifacts": source_artifacts,
        "personalized_context": _personalized_context(record),
        "source_run": {
            "run_id": run.run_id,
            "run_manifest": _portable_path(run.manifest_path, base=config_base),
        },
    }


def _skipped_alert_record(
    *,
    index: int,
    cycle_id: str,
    created_at: str,
    run: Any,
    config_base: Path,
    reason: str,
) -> dict[str, Any]:
    alert_key = f"alert:skipped:{_stable_hash({'cycle_id': cycle_id, 'index': index, 'reason': reason})}"
    return {
        "schema_version": 1,
        "artifact_type": "monitor_alert_archive_record",
        "record_id": _record_id(cycle_id=cycle_id, index=index, alert_key=alert_key),
        "cycle_id": cycle_id,
        "created_at": created_at,
        "status": "skipped",
        "alert_key": alert_key,
        "decision_id": "unknown",
        "symbol": "unknown",
        "timeframe": "unknown",
        "priority": "unknown",
        "attention_decision": "unknown",
        "requires_user_attention": False,
        "suppression_reasons": [reason],
        "cooldown_until": None,
        "source_artifacts": [],
        "personalized_context": {"present": False},
        "source_run": {
            "run_id": run.run_id,
            "run_manifest": _portable_path(run.manifest_path, base=config_base),
        },
    }


def _insufficient_alert_reasons(
    *,
    decision_id: str,
    priority: str,
    attention_decision: str,
    symbol: str,
    timeframe: str,
) -> list[str]:
    reasons: list[str] = []
    if decision_id == "unknown":
        reasons.append("missing_alert_decision_id")
    if priority == "unknown":
        reasons.append("missing_priority")
    if attention_decision == "unknown":
        reasons.append("missing_attention_decision")
    if symbol == "unknown":
        reasons.append("missing_symbol")
    if timeframe == "unknown":
        reasons.append("missing_timeframe")
    return reasons


def _alert_key(record: dict[str, Any], *, fallback_index: int) -> str:
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    symbol = _clean_text(scope.get("symbol"), fallback="unknown")
    timeframe = _clean_text(scope.get("timeframe"), fallback="unknown")
    priority = _clean_text(record.get("priority"), fallback="unknown")
    payload = {
        "alert_decision_id": _clean_text(record.get("alert_decision_id")),
        "attention_decision": _clean_text(record.get("attention_decision"), fallback="unknown"),
        "priority": priority,
        "scope": {
            "assessment_id": _clean_text(scope.get("assessment_id"), fallback=f"index:{fallback_index}"),
            "event_signal_ids": _string_list(scope.get("event_signal_ids")),
            "symbol": symbol,
            "timeframe": timeframe,
            "topic_ids": _string_list(scope.get("topic_ids")),
        },
        "source_artifacts": _string_list(record.get("source_artifacts")),
        "status": _clean_text(record.get("status"), fallback="unknown"),
    }
    return f"alert:{symbol}:{timeframe}:{priority}:{_stable_hash(payload)}"


def _record_id(*, cycle_id: str, index: int, alert_key: str) -> str:
    return f"monitor_alert:{cycle_id}:{index:04d}:{_stable_hash(alert_key)}"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _empty_alert_archive_counts() -> dict[str, int]:
    return {
        "records": 0,
        "emitted": 0,
        "suppressed_duplicate": 0,
        "suppressed_cooldown": 0,
        "suppressed_no_alert": 0,
        "skipped": 0,
    }


def _personalized_context(record: dict[str, Any]) -> dict[str, Any]:
    constraint_id = _clean_text(record.get("personalized_constraint_id"))
    state = _clean_text(record.get("personalized_state"))
    action = _clean_text(record.get("personalized_action"))
    if constraint_id == "unknown" and state == "unknown" and action == "unknown":
        return {"present": False}
    return {
        "present": True,
        "constraint_id": constraint_id,
        "state": state,
        "action": action,
    }


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _coerce_utc(parsed)


def _clean_text(value: Any, *, fallback: str = "unknown") -> str:
    if not isinstance(value, str) or not value.strip():
        return fallback
    return value.strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item.strip() for item in value if isinstance(item, str) and item.strip()})


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
