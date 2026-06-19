from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .pipeline import RunResult, StageSelectionError, run_pipeline
from .storage import write_json


DEFAULT_MONITOR_ENABLED = False
DEFAULT_MONITOR_INTERVAL_SECONDS = 300
DEFAULT_MONITOR_MAX_CYCLES = 1
DEFAULT_MONITOR_COOLDOWN_SECONDS = 3600
DEFAULT_MONITOR_OUTPUT_DIR = "runs/monitor"
DEFAULT_MONITOR_TARGET_STAGE = "build_personalized_risk_material"
DEFAULT_MONITOR_NO_CODEX = True
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


PipelineRunner = Callable[..., RunResult]


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
) -> MonitorCycleResult:
    settings = load_monitor_config(config)
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
        "cycle_mode": "once",
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
        "warnings": [],
        "errors": [],
    }
    write_json(manifest_path, manifest)

    try:
        pipeline_result = pipeline_runner(
            config,
            config_path=config_path,
            until_stage=settings.target_stage,
            skip_codex=settings.no_codex,
        )
    except StageSelectionError as exc:
        reason = str(exc)
        finished_at = datetime.now(timezone.utc)
        manifest.update(
            {
                "status": "failed",
                "finished_at": _utc_timestamp(finished_at),
                "exit_code": 2,
                "errors": [{"stage": "target_stage", "message": reason}],
            }
        )
        write_json(manifest_path, manifest)
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

    finished_at = datetime.now(timezone.utc)
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
            "warnings": _manifest_warnings(pipeline_result.run.manifest),
            "errors": errors,
        }
    )
    write_json(manifest_path, manifest)

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
