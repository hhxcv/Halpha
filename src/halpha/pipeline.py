from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .storage import ensure_directory, write_json


STAGE_ORDER = (
    "collect_market_data",
    "collect_text_events",
    "build_analysis_materials",
    "build_research_context",
    "build_codex_context",
    "run_codex_report",
)

StageHandler = Callable[[dict[str, Any], "RunContext"], list[str] | None]


class PipelineError(Exception):
    def __init__(self, message: str, *, stage: str | None = None, exit_code: int = 1) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code


class StageNotImplementedError(PipelineError):
    def __init__(self, stage: str) -> None:
        super().__init__(f"stage {stage} is not implemented", stage=stage, exit_code=3)


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_dir: Path
    raw_dir: Path
    analysis_dir: Path
    codex_context_dir: Path
    report_dir: Path
    manifest_path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True)
class RunResult:
    succeeded: bool
    run: RunContext
    exit_code: int
    failed_stage: str | None
    reason: str | None


def run_pipeline(
    config: dict[str, Any],
    *,
    config_path: Path,
    stage_handlers: dict[str, StageHandler] | None = None,
    now: datetime | None = None,
) -> RunResult:
    run = _create_run_context(config, config_path=config_path, now=now)
    _write_manifest(run)

    handlers = {stage: _unimplemented_handler(stage) for stage in STAGE_ORDER}
    if stage_handlers:
        handlers.update(stage_handlers)

    for stage in STAGE_ORDER:
        stage_record: dict[str, Any] = {
            "name": stage,
            "status": "running",
            "started_at": _utc_timestamp(),
            "finished_at": None,
            "artifacts": [],
        }
        run.manifest["stages"].append(stage_record)
        _set_codex_status(run, stage=stage, status="running")
        _write_manifest(run)

        try:
            artifacts = handlers[stage](config, run)
        except PipelineError as exc:
            failed_stage = exc.stage or stage
            reason = str(exc)
            error = _error_summary(failed_stage, reason)
            stage_record["status"] = "failed"
            stage_record["finished_at"] = _utc_timestamp()
            stage_record["error"] = error
            _set_codex_status(run, stage=stage, status="failed")
            _finish_manifest(run, status="failed", error=error)
            return RunResult(False, run, exc.exit_code, failed_stage, reason)
        except Exception as exc:
            reason = f"stage {stage} failed: {exc}"
            error = _error_summary(stage, reason)
            stage_record["status"] = "failed"
            stage_record["finished_at"] = _utc_timestamp()
            stage_record["error"] = error
            _set_codex_status(run, stage=stage, status="failed")
            _finish_manifest(run, status="failed", error=error)
            return RunResult(False, run, 1, stage, reason)

        stage_record["status"] = "succeeded"
        stage_record["finished_at"] = _utc_timestamp()
        stage_record["artifacts"] = artifacts or []
        _set_codex_status(run, stage=stage, status="succeeded")
        _write_manifest(run)

    run.manifest["status"] = "succeeded"
    run.manifest["finished_at"] = _utc_timestamp()
    _write_manifest(run)
    return RunResult(True, run, 0, None, None)


def _create_run_context(config: dict[str, Any], *, config_path: Path, now: datetime | None) -> RunContext:
    output_dir = Path(config["run"]["output_dir"])
    if not output_dir.is_absolute():
        output_dir = config_path.parent / output_dir

    run_id = _run_id(now)
    run_dir = _unique_run_dir(output_dir, run_id)
    run_id = run_dir.name

    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"

    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        ensure_directory(directory)

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "running",
        "started_at": _utc_timestamp(now),
        "finished_at": None,
        "config_path": _path_for_manifest(config_path),
        "sources": _source_summary(config),
        "artifacts": {},
        "counts": {},
        "stage_order": list(STAGE_ORDER),
        "stages": [],
        "codex": _codex_summary(config),
        "errors": [],
    }

    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        manifest=manifest,
    )


def _unimplemented_handler(stage: str) -> StageHandler:
    def handler(config: dict[str, Any], run: RunContext) -> list[str] | None:
        raise StageNotImplementedError(stage)

    return handler


def _finish_manifest(run: RunContext, *, status: str, error: dict[str, str]) -> None:
    run.manifest["status"] = status
    run.manifest["finished_at"] = _utc_timestamp()
    run.manifest["errors"].append(error)
    _write_manifest(run)


def _error_summary(stage: str, reason: str) -> dict[str, str]:
    return {"stage": stage, "message": reason}


def _set_codex_status(run: RunContext, *, stage: str, status: str) -> None:
    if stage == "run_codex_report":
        run.manifest["codex"]["status"] = status


def _write_manifest(run: RunContext) -> None:
    write_json(run.manifest_path, run.manifest)


def _run_id(now: datetime | None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_timestamp(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def _unique_run_dir(output_dir: Path, run_id: str) -> Path:
    ensure_directory(output_dir)
    candidate = output_dir / run_id
    if not candidate.exists():
        candidate.mkdir()
        return candidate

    for index in range(1, 100):
        candidate = output_dir / f"{run_id}-{index:02d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate

    raise PipelineError(f"could not create a unique run directory for run_id {run_id}")


def _source_summary(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market", {})
    text = config.get("text", {})

    return {
        "market": {
            "enabled": market.get("enabled"),
            "source": market.get("source"),
            "symbols": list(market.get("symbols", [])),
        },
        "text": [
            {
                "name": source.get("name"),
                "type": source.get("type"),
                "url": source.get("url"),
            }
            for source in text.get("sources", [])
        ],
    }


def _codex_summary(config: dict[str, Any]) -> dict[str, Any]:
    codex = config.get("codex", {})
    return {
        "enabled": codex.get("enabled"),
        "command": codex.get("command"),
        "status": "not_started",
        "exit_code": None,
    }


def _path_for_manifest(path: Path) -> str:
    return path.as_posix()
