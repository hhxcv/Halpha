from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any, Callable

from halpha.pipeline import RunResult, StageSelectionError, run_pipeline
from halpha.storage import write_json


LOGGER = logging.getLogger(__name__)


DEFAULT_MONITOR_ENABLED = False
DEFAULT_MONITOR_INTERVAL_SECONDS = 300
DEFAULT_MONITOR_MAX_CYCLES = 1
DEFAULT_MONITOR_COOLDOWN_SECONDS = 3600
DEFAULT_MONITOR_OUTPUT_DIR = "runs/monitor"
DEFAULT_MONITOR_TARGET_STAGE = "build_personalized_risk_material"
DEFAULT_MONITOR_NO_CODEX = True
ALERT_ARCHIVE_FILENAME = "alert_archive.jsonl"
ALERT_COOLDOWN_STATE_FILENAME = "alert_cooldown_state.json"
ALERT_ARCHIVE_STATE_FILENAME = "alert_archive_state.json"
MONITOR_HEALTH_STATE_FILENAME = "monitor_health_state.json"
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
SUPPORTED_MONITOR_FIELDS = {
    "cooldown_seconds",
    "enabled",
    "interval_seconds",
    "max_cycles",
    "no_codex",
    "output_dir",
    "target_stage",
}


@dataclass(frozen=True)
class MonitorConfig:
    enabled: bool
    interval_seconds: int
    max_cycles: int
    cooldown_seconds: int
    output_dir: Path
    target_stage: str
    no_codex: bool


@dataclass(frozen=True)
class MonitorCycleResult:
    succeeded: bool
    exit_code: int
    cycle_id: str
    status: str
    target_stage: str
    no_codex: bool
    manifest_path: Path
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


def load_monitor_config(config: dict[str, Any]) -> MonitorConfig:
    section = config.get("monitor", {})
    if not isinstance(section, dict):
        raise ValueError("monitor config must be a mapping.")

    return MonitorConfig(
        enabled=section.get("enabled", DEFAULT_MONITOR_ENABLED),
        interval_seconds=section.get("interval_seconds", DEFAULT_MONITOR_INTERVAL_SECONDS),
        max_cycles=section.get("max_cycles", DEFAULT_MONITOR_MAX_CYCLES),
        cooldown_seconds=section.get("cooldown_seconds", DEFAULT_MONITOR_COOLDOWN_SECONDS),
        output_dir=Path(str(section.get("output_dir", DEFAULT_MONITOR_OUTPUT_DIR))),
        target_stage=section.get("target_stage", DEFAULT_MONITOR_TARGET_STAGE),
        no_codex=section.get("no_codex", DEFAULT_MONITOR_NO_CODEX),
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
) -> MonitorCycleResult:
    settings = load_monitor_config(config)
    fixed_time = now is not None
    started_at = _coerce_utc(now or datetime.now(timezone.utc))
    cycle_id = _cycle_id(started_at)
    output_dir = _resolve_output_dir(settings.output_dir, config_path=config_path)
    cycle_dir = _unique_cycle_dir(output_dir / "cycles", cycle_id)
    cycle_id = cycle_dir.name
    manifest_path = cycle_dir / "monitor_cycle_manifest.json"
    base = _config_base(config_path)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "monitor_cycle_manifest",
        "cycle_id": cycle_id,
        "cycle_mode": cycle_mode,
        "loop_id": loop_id,
        "cycle_sequence": cycle_sequence,
        "trigger_source": "cli",
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
        "alert_archive": {
            "status": "not_run",
            "archive": _portable_path(output_dir / ALERT_ARCHIVE_FILENAME, base=base),
            "cooldown_state": _portable_path(output_dir / ALERT_COOLDOWN_STATE_FILENAME, base=base),
            "archive_state": _portable_path(output_dir / ALERT_ARCHIVE_STATE_FILENAME, base=base),
            "counts": _empty_alert_archive_counts(),
            "warnings": [],
            "errors": [],
        },
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
        _write_monitor_health_state(output_dir, config_base=base, timestamp=finished_at)
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
    alert_archive = _archive_alert_decisions(
        pipeline_result,
        cycle_id=cycle_id,
        output_dir=output_dir,
        config_base=base,
        timestamp=finished_at,
        cooldown_seconds=settings.cooldown_seconds,
    )
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
            "alert_archive": alert_archive,
            "warnings": _manifest_warnings(pipeline_result.run.manifest),
            "errors": errors,
        }
    )
    write_json(manifest_path, manifest)
    _write_monitor_health_state(output_dir, config_base=base, timestamp=finished_at)
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
    settings = load_monitor_config(config)
    if max_cycles <= 0:
        raise ValueError("max_cycles must be a positive integer.")
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be a positive integer.")

    output_dir = _resolve_output_dir(settings.output_dir, config_path=config_path)
    base = _config_base(config_path)
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
    health_state_path = _write_monitor_health_state(
        output_dir,
        config_base=base,
        timestamp=finished_at,
        loop_summary={
            "loop_id": loop_id,
            "status": status,
            "max_cycles": max_cycles,
            "completed_cycles": len(cycle_results),
            "stop_reason": stop_reason,
            "started_at": _utc_timestamp(started_at),
            "finished_at": _utc_timestamp(finished_at),
            "latest_cycle_id": cycle_results[-1].cycle_id if cycle_results else None,
        },
    )
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
    base = _config_base(config_path)
    health_state = _monitor_health_state(output_dir, config_base=base)
    lines = [
        "Halpha monitor inspection succeeded.",
        f"monitor_output_dir: {_portable_path(output_dir, base=base)}",
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
    return MonitorInspectionResult(True, 0, lines)


def monitor_config_lines(settings: MonitorConfig) -> list[str]:
    return [
        f"enabled: {str(settings.enabled).lower()}",
        f"interval_seconds: {settings.interval_seconds}",
        f"max_cycles: {settings.max_cycles}",
        f"cooldown_seconds: {settings.cooldown_seconds}",
        f"output_dir: {settings.output_dir.as_posix()}",
        f"target_stage: {settings.target_stage}",
        f"no_codex: {str(settings.no_codex).lower()}",
    ]


def _resolve_output_dir(output_dir: Path, *, config_path: Path) -> Path:
    if output_dir.is_absolute():
        return output_dir
    return _config_base(config_path) / output_dir


def _unique_cycle_dir(parent: Path, cycle_id: str) -> Path:
    candidate = parent / cycle_id
    suffix = 2
    while candidate.exists():
        candidate = parent / f"{cycle_id}-{suffix}"
        suffix += 1
    return candidate


def _cycle_id(now: datetime) -> str:
    return f"cycle-{now.strftime('%Y%m%dT%H%M%S%fZ')}"


def _utc_timestamp(value: datetime) -> str:
    return _coerce_utc(value).isoformat().replace("+00:00", "Z")


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _config_base(config_path: Path) -> Path:
    parent = config_path.parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


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


def _archive_alert_decisions(
    result: RunResult,
    *,
    cycle_id: str,
    output_dir: Path,
    config_base: Path,
    timestamp: datetime,
    cooldown_seconds: int,
) -> dict[str, Any]:
    archive_path = output_dir / ALERT_ARCHIVE_FILENAME
    cooldown_path = output_dir / ALERT_COOLDOWN_STATE_FILENAME
    archive_state_path = output_dir / ALERT_ARCHIVE_STATE_FILENAME
    summary: dict[str, Any] = {
        "status": "skipped",
        "archive": _portable_path(archive_path, base=config_base),
        "cooldown_state": _portable_path(cooldown_path, base=config_base),
        "archive_state": _portable_path(archive_state_path, base=config_base),
        "counts": _empty_alert_archive_counts(),
        "warnings": [],
        "errors": [],
    }

    artifact_ref = _alert_decisions_artifact_ref(result.run.manifest)
    if not artifact_ref:
        summary["warnings"].append("analysis/alert_decisions.json was not produced by the linked run.")
        _write_alert_archive_state(archive_state_path, summary, cycle_id=cycle_id, timestamp=timestamp)
        return summary

    artifact_path = result.run.run_dir / artifact_ref
    artifact, error = _read_alert_decisions_artifact(artifact_path)
    if error:
        summary["status"] = "degraded"
        summary["errors"].append(error)
        _write_alert_archive_state(archive_state_path, summary, cycle_id=cycle_id, timestamp=timestamp)
        return summary

    records = artifact.get("records")
    if not isinstance(records, list):
        summary["status"] = "degraded"
        summary["errors"].append("analysis/alert_decisions.json records must be a list.")
        _write_alert_archive_state(archive_state_path, summary, cycle_id=cycle_id, timestamp=timestamp)
        return summary

    cooldown_state, state_warnings = _load_cooldown_state(cooldown_path)
    summary["warnings"].extend(state_warnings)
    archive_records: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    created_at = _utc_timestamp(timestamp)

    for index, record in enumerate(records):
        archive_record = _alert_archive_record(
            record,
            index=index,
            cycle_id=cycle_id,
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
        summary["counts"][status] = summary["counts"].get(status, 0) + 1
        summary["counts"]["records"] += 1

    if archive_records:
        _append_archive_records(archive_path, archive_records)
        summary["status"] = "succeeded"
    else:
        summary["warnings"].append("analysis/alert_decisions.json contained no alert decision records.")

    _write_cooldown_state(
        cooldown_path,
        cooldown_state,
        cooldown_seconds=cooldown_seconds,
        timestamp=timestamp,
        config_base=config_base,
    )
    _write_alert_archive_state(archive_state_path, summary, cycle_id=cycle_id, timestamp=timestamp)
    return summary


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


def _load_cooldown_state(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, []
    except json.JSONDecodeError:
        return {}, [f"{ALERT_COOLDOWN_STATE_FILENAME} was not valid JSON; starting with empty cooldown state."]
    if not isinstance(data, dict):
        return {}, [f"{ALERT_COOLDOWN_STATE_FILENAME} was not a JSON object; starting with empty cooldown state."]
    records = data.get("records", {})
    if not isinstance(records, dict):
        return {}, [f"{ALERT_COOLDOWN_STATE_FILENAME}.records was not a JSON object; starting with empty cooldown state."]
    return {str(key): value for key, value in records.items() if isinstance(value, dict)}, []


def _append_archive_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")


def _write_cooldown_state(
    path: Path,
    records: dict[str, Any],
    *,
    cooldown_seconds: int,
    timestamp: datetime,
    config_base: Path,
) -> None:
    state = {
        "schema_version": 1,
        "artifact_type": "monitor_alert_cooldown_state",
        "updated_at": _utc_timestamp(timestamp),
        "cooldown_seconds": cooldown_seconds,
        "records": records,
        "record_count": len(records),
        "state_path": _portable_path(path, base=config_base),
    }
    write_json(path, state)


def _write_alert_archive_state(
    path: Path,
    summary: dict[str, Any],
    *,
    cycle_id: str,
    timestamp: datetime,
) -> None:
    state = {
        "schema_version": 1,
        "artifact_type": "monitor_alert_archive_state",
        "updated_at": _utc_timestamp(timestamp),
        "last_cycle_id": cycle_id,
        "status": summary["status"],
        "archive": summary["archive"],
        "cooldown_state": summary["cooldown_state"],
        "counts": summary["counts"],
        "warnings": summary["warnings"],
        "errors": summary["errors"],
    }
    write_json(path, state)


def _write_monitor_health_state(
    output_dir: Path,
    *,
    config_base: Path,
    timestamp: datetime,
    loop_summary: dict[str, Any] | None = None,
) -> Path:
    health_state_path = output_dir / MONITOR_HEALTH_STATE_FILENAME
    state = _monitor_health_state(output_dir, config_base=config_base, latest_loop=loop_summary)
    state["updated_at"] = _utc_timestamp(timestamp)
    write_json(health_state_path, state)
    return health_state_path


def _monitor_health_state(
    output_dir: Path,
    *,
    config_base: Path,
    latest_loop: dict[str, Any] | None = None,
) -> dict[str, Any]:
    health_state_path = output_dir / MONITOR_HEALTH_STATE_FILENAME
    previous_health = _read_json_object(health_state_path)
    cycle_manifests = _read_cycle_manifests(output_dir)
    latest_cycle = cycle_manifests[0] if cycle_manifests else {}
    archive_state = _read_json_object(output_dir / ALERT_ARCHIVE_STATE_FILENAME)
    cooldown_state = _read_json_object(output_dir / ALERT_COOLDOWN_STATE_FILENAME)
    alert_counts = _dict(archive_state.get("counts"))
    if not alert_counts:
        alert_counts = _empty_alert_archive_counts()
    cooldown_records = _dict(cooldown_state.get("records"))
    warning_count = _health_warning_count(cycle_manifests, archive_state)
    error_count = _health_error_count(cycle_manifests, archive_state)

    loop = latest_loop if latest_loop is not None else _dict(previous_health.get("latest_loop"))
    return {
        "schema_version": 1,
        "artifact_type": "monitor_health_state",
        "health_state_path": _portable_path(health_state_path, base=config_base),
        "monitor_output_dir": _portable_path(output_dir, base=config_base),
        "cycle_count": len(cycle_manifests),
        "failed_cycle_count": sum(1 for manifest in cycle_manifests if manifest.get("status") == "failed"),
        "latest_cycle_id": _clean_text(latest_cycle.get("cycle_id"), fallback="none"),
        "latest_cycle_status": _clean_text(latest_cycle.get("status"), fallback="missing"),
        "latest_run_id": _clean_text(latest_cycle.get("run_id"), fallback="none"),
        "latest_run_manifest": _clean_text(latest_cycle.get("run_manifest"), fallback="none"),
        "latest_cycle_manifest": _portable_path(Path(str(latest_cycle.get("_path", ""))), base=config_base)
        if latest_cycle
        else "none",
        "alert_archive_status": _clean_text(archive_state.get("status"), fallback="missing"),
        "alert_counts": {
            "records": int(alert_counts.get("records", 0)),
            "emitted": int(alert_counts.get("emitted", 0)),
            "suppressed_duplicate": int(alert_counts.get("suppressed_duplicate", 0)),
            "suppressed_cooldown": int(alert_counts.get("suppressed_cooldown", 0)),
            "suppressed_no_alert": int(alert_counts.get("suppressed_no_alert", 0)),
            "skipped": int(alert_counts.get("skipped", 0)),
        },
        "cooldown_records": int(cooldown_state.get("record_count", len(cooldown_records))),
        "warning_count": warning_count,
        "error_count": error_count,
        "latest_loop": loop,
    }


def _read_cycle_manifests(output_dir: Path) -> list[dict[str, Any]]:
    cycle_dir = output_dir / "cycles"
    manifests: list[dict[str, Any]] = []
    for path in sorted(cycle_dir.glob("*/monitor_cycle_manifest.json")):
        manifest = _read_json_object(path)
        if not manifest:
            continue
        manifest["_path"] = path
        manifests.append(manifest)
    return sorted(
        manifests,
        key=lambda manifest: str(manifest.get("finished_at") or manifest.get("started_at") or ""),
        reverse=True,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _health_warning_count(cycle_manifests: list[dict[str, Any]], archive_state: dict[str, Any]) -> int:
    count = 0
    for manifest in cycle_manifests:
        warnings = manifest.get("warnings", [])
        if isinstance(warnings, list):
            count += len(warnings)
        archive = _dict(manifest.get("alert_archive"))
        archive_warnings = archive.get("warnings", [])
        if isinstance(archive_warnings, list):
            count += len(archive_warnings)
    state_warnings = archive_state.get("warnings", [])
    if isinstance(state_warnings, list):
        count += len(state_warnings)
    return count


def _health_error_count(cycle_manifests: list[dict[str, Any]], archive_state: dict[str, Any]) -> int:
    count = 0
    for manifest in cycle_manifests:
        errors = manifest.get("errors", [])
        if isinstance(errors, list):
            count += len(errors)
        archive = _dict(manifest.get("alert_archive"))
        archive_errors = archive.get("errors", [])
        if isinstance(archive_errors, list):
            count += len(archive_errors)
    state_errors = archive_state.get("errors", [])
    if isinstance(state_errors, list):
        count += len(state_errors)
    return count


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
