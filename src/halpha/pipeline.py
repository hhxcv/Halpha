from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from halpha.runtime.exception_diagnostics import bounded_exception_diagnostic
from halpha.runtime.logging_utils import redact_private_text
from halpha.runtime.pipeline_contracts import (
    PipelineError,
    RunContext,
    RunResult,
    StageHandler,
)
from halpha.pipeline_stage_handlers import default_stage_handlers
from halpha.pipeline_stages import (
    DECISION_INTELLIGENCE_STAGES,
    STAGE_ORDER,
    stages_after as _stages_after,
    validate_optional_stage as _validate_optional_stage,
    validate_stage as _validate_stage,
)
from halpha.storage import artifact_base, config_base, display_path, ensure_directory, write_json


LOGGER = logging.getLogger(__name__)


def run_pipeline(
    config: dict[str, Any],
    *,
    config_path: Path,
    stage_handlers: dict[str, StageHandler] | None = None,
    now: datetime | None = None,
    until_stage: str | None = None,
    skip_codex: bool = False,
) -> RunResult:
    _validate_optional_stage(until_stage, option_name="--until")
    clock = _clock(now)
    run = _create_run_context(config, config_path=config_path, now=clock())
    _record_validation_mode(run, until_stage=until_stage, skip_codex=skip_codex)
    _write_manifest(run)
    LOGGER.info(
        "Pipeline run started.",
        extra={
            "event": "pipeline.run.start",
            "run_id": run.run_id,
            "until_stage": until_stage,
            "skip_codex": skip_codex,
        },
    )

    handlers = default_stage_handlers(stage_handlers)

    for stage in STAGE_ORDER:
        stage_record: dict[str, Any] = {
            "name": stage,
            "status": "running",
            "started_at": _utc_timestamp(clock()),
            "finished_at": None,
            "artifacts": [],
        }
        run.manifest["stages"].append(stage_record)
        _set_codex_status(run, stage=stage, status="running")
        _write_manifest(run)

        if skip_codex and stage == "run_codex_report":
            _skip_stage(
                run,
                stage_record,
                stage=stage,
                reason="--no-codex requested",
                finished_at=_utc_timestamp(clock()),
            )
        else:
            failure = _run_stage_handler(
                config,
                run,
                handlers[stage],
                stage=stage,
                stage_record=stage_record,
                clock=clock,
            )
            if failure:
                return failure

        _write_manifest(run)
        if stage == until_stage:
            _record_not_run_stages(
                run,
                _stages_after(stage),
                reason=f"--until {stage} requested",
            )
            break

    run.manifest["status"] = "succeeded"
    run.manifest["finished_at"] = _utc_timestamp(clock())
    _write_manifest(run)
    _record_terminal_local_data_state(config, run, clock=clock)
    LOGGER.info(
        "Pipeline run succeeded.",
        extra={"event": "pipeline.run.succeeded", "run_id": run.run_id},
    )
    return RunResult(True, run, 0, None, None)


def run_pipeline_stage(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_dir: Path,
    stage: str,
    stage_handlers: dict[str, StageHandler] | None = None,
    now: datetime | None = None,
) -> RunResult:
    _validate_stage(stage, option_name="stage")
    clock = _clock(now)
    run = _load_run_context(config, config_path=config_path, run_dir=run_dir)
    LOGGER.info(
        "Pipeline single stage started.",
        extra={"event": "pipeline.single_stage.start", "run_id": run.run_id, "stage": stage},
    )
    run.manifest["status"] = "running"
    run.manifest["single_stage_validation"] = {
        "stage": stage,
        "requested_at": _utc_timestamp(clock()),
    }
    _write_manifest(run)

    stage_record: dict[str, Any] = {
        "name": stage,
        "status": "running",
        "started_at": _utc_timestamp(clock()),
        "finished_at": None,
        "artifacts": [],
        "mode": "single_stage",
    }
    run.manifest["stages"].append(stage_record)
    _set_codex_status(run, stage=stage, status="running")
    _write_manifest(run)

    handlers = default_stage_handlers(stage_handlers)
    failure = _run_stage_handler(
        config,
        run,
        handlers[stage],
        stage=stage,
        stage_record=stage_record,
        clock=clock,
    )
    if failure:
        return failure

    run.manifest["status"] = "succeeded"
    run.manifest["finished_at"] = _utc_timestamp(clock())
    _write_manifest(run)
    _record_terminal_local_data_state(config, run, clock=clock)
    LOGGER.info(
        "Pipeline single stage succeeded.",
        extra={"event": "pipeline.single_stage.succeeded", "run_id": run.run_id, "stage": stage},
    )
    return RunResult(True, run, 0, None, None)


def _create_run_context(config: dict[str, Any], *, config_path: Path, now: datetime | None) -> RunContext:
    output_dir = Path(config["run"]["output_dir"])
    if not output_dir.is_absolute():
        output_dir = artifact_base(config_path) / output_dir

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
        config_path=config_path,
        manifest=manifest,
    )


def _load_run_context(config: dict[str, Any], *, config_path: Path, run_dir: Path) -> RunContext:
    manifest_path = run_dir / "run_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            "run_manifest.json was not found in the requested run directory.",
            stage="stage",
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"run_manifest.json is not valid JSON: {exc.msg}.",
            stage="stage",
            exit_code=3,
        ) from exc
    if not isinstance(manifest, dict):
        raise PipelineError(
            "run_manifest.json must be a JSON object.",
            stage="stage",
            exit_code=3,
        )

    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        ensure_directory(directory)
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("run_id", run_dir.name)
    manifest.setdefault("config_path", _path_for_manifest(config_path))
    manifest.setdefault("sources", _source_summary(config))
    manifest.setdefault("artifacts", {})
    manifest.setdefault("counts", {})
    manifest.setdefault("stage_order", list(STAGE_ORDER))
    manifest.setdefault("stages", [])
    manifest.setdefault("codex", _codex_summary(config))
    manifest.setdefault("errors", [])

    return RunContext(
        run_id=str(manifest.get("run_id") or run_dir.name),
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=manifest_path,
        config_path=config_path,
        manifest=manifest,
    )


def _run_stage_handler(
    config: dict[str, Any],
    run: RunContext,
    handler: StageHandler,
    *,
    stage: str,
    stage_record: dict[str, Any],
    clock: Callable[[], datetime],
) -> RunResult | None:
    LOGGER.debug(
        "Pipeline stage started.",
        extra={"event": "pipeline.stage.start", "run_id": run.run_id, "stage": stage},
    )
    try:
        artifacts = handler(config, run)
    except PipelineError as exc:
        finished_at = _utc_timestamp(clock())
        failed_stage = exc.stage or stage
        reason = redact_private_text(str(exc), config_path=run.config_path, config=config)
        error = _error_summary(
            failed_stage,
            reason,
            details=exc.error_details,
            diagnostic=(
                bounded_exception_diagnostic(exc, context={"pipeline_exit_code": exc.exit_code})
                if exc.error_details
                else None
            ),
        )
        stage_record["status"] = "failed"
        stage_record["finished_at"] = finished_at
        stage_record["artifacts"] = exc.artifacts
        stage_record["error"] = error
        _set_codex_status(run, stage=stage, status="failed")
        _record_stage_failure_context(config, run, stage=stage, error=error)
        _finish_manifest(config, run, status="failed", error=error, finished_at=finished_at, clock=clock)
        LOGGER.error(
            "Pipeline stage failed.",
            extra={
                "event": "pipeline.stage.failed",
                "run_id": run.run_id,
                "stage": failed_stage,
                "exit_code": exc.exit_code,
                "reason": reason,
            },
        )
        return RunResult(False, run, exc.exit_code, failed_stage, reason)
    except Exception as exc:
        finished_at = _utc_timestamp(clock())
        exception_message = redact_private_text(str(exc), config_path=run.config_path, config=config)
        reason = f"stage {stage} failed: {exception_message}"
        error = _error_summary(stage, reason, diagnostic=bounded_exception_diagnostic(exc))
        stage_record["status"] = "failed"
        stage_record["finished_at"] = finished_at
        stage_record["error"] = error
        _set_codex_status(run, stage=stage, status="failed")
        _record_stage_failure_context(config, run, stage=stage, error=error)
        _finish_manifest(config, run, status="failed", error=error, finished_at=finished_at, clock=clock)
        LOGGER.error(
            "Pipeline stage failed.",
            extra={
                "event": "pipeline.stage.failed",
                "run_id": run.run_id,
                "stage": stage,
                "exit_code": 1,
                "reason": reason,
            },
        )
        return RunResult(False, run, 1, stage, reason)

    finished_at = _utc_timestamp(clock())
    stage_record["status"] = "succeeded"
    stage_record["finished_at"] = finished_at
    stage_record["artifacts"] = artifacts or []
    _set_codex_status(run, stage=stage, status="succeeded")
    LOGGER.debug(
        "Pipeline stage succeeded.",
        extra={
            "event": "pipeline.stage.succeeded",
            "run_id": run.run_id,
            "stage": stage,
            "artifact_count": len(stage_record["artifacts"]),
        },
    )
    return None


def _skip_stage(
    run: RunContext,
    stage_record: dict[str, Any],
    *,
    stage: str,
    reason: str,
    finished_at: str,
) -> None:
    stage_record["status"] = "skipped"
    stage_record["finished_at"] = finished_at
    stage_record["artifacts"] = []
    stage_record["reason"] = reason
    if stage == "run_codex_report":
        run.manifest["codex"]["status"] = "skipped"
        run.manifest["codex"]["exit_code"] = None
        run.manifest["codex"]["skip_reason"] = reason
    LOGGER.info(
        "Pipeline stage skipped.",
        extra={"event": "pipeline.stage.skipped", "run_id": run.run_id, "stage": stage, "reason": reason},
    )


def _record_stage_failure_context(
    config: dict[str, Any],
    run: RunContext,
    *,
    stage: str,
    error: dict[str, Any],
) -> None:
    failed_stage = str(error.get("stage") or stage)
    if stage not in DECISION_INTELLIGENCE_STAGES and failed_stage not in DECISION_INTELLIGENCE_STAGES:
        return
    from halpha.decision.decision_intelligence import record_decision_intelligence_failure

    message = str(error.get("message") or f"stage {failed_stage} failed")
    record_decision_intelligence_failure(config, run, stage=failed_stage, message=message)


def _record_not_run_stages(run: RunContext, stages: list[str], *, reason: str) -> None:
    for stage in stages:
        record: dict[str, Any] = {
            "name": stage,
            "status": "not_run",
            "started_at": None,
            "finished_at": None,
            "artifacts": [],
            "reason": reason,
        }
        run.manifest["stages"].append(record)
        if stage == "run_codex_report":
            run.manifest["codex"]["status"] = "not_run"
            run.manifest["codex"]["exit_code"] = None
            run.manifest["codex"]["skip_reason"] = reason
    if stages:
        LOGGER.info(
            "Pipeline stages marked not run.",
            extra={
                "event": "pipeline.stages.not_run",
                "run_id": run.run_id,
                "stage_count": len(stages),
                "first_stage": stages[0],
                "last_stage": stages[-1],
                "reason": reason,
            },
        )


def _record_validation_mode(run: RunContext, *, until_stage: str | None, skip_codex: bool) -> None:
    if until_stage is None and not skip_codex:
        return
    run.manifest["validation"] = {
        "mode": "run",
        "until_stage": until_stage,
        "skip_codex": skip_codex,
    }


def _finish_manifest(
    config: dict[str, Any],
    run: RunContext,
    *,
    status: str,
    error: dict[str, Any],
    finished_at: str,
    clock: Callable[[], datetime],
) -> None:
    run.manifest["status"] = status
    run.manifest["finished_at"] = finished_at
    run.manifest["errors"].append(error)
    _write_manifest(run)
    _record_terminal_local_data_state(config, run, clock=clock)


def _record_terminal_local_data_state(
    config: dict[str, Any],
    run: RunContext,
    *,
    clock: Callable[[], datetime],
) -> None:
    _record_run_index(run, clock=clock)
    _record_outcome_history(config, run, clock=clock)
    _record_research_data_catalog(config, run, clock=clock)
    _record_run_index(run, clock=clock)
    _write_manifest(run)


def _record_run_index(run: RunContext, *, clock: Callable[[], datetime]) -> None:
    from halpha.data.run_index import RUN_INDEX_ARTIFACT, write_run_index

    run.manifest.setdefault("artifacts", {})["run_index"] = RUN_INDEX_ARTIFACT
    try:
        summary = write_run_index(run, now=clock())
    except Exception as exc:
        summary = {
            "schema_version": 1,
            "status": "failed",
            "artifact": RUN_INDEX_ARTIFACT,
            "error": str(exc),
        }
    run.manifest["run_index"] = summary
    run.manifest.setdefault("counts", {})["run_index_errors"] = 1 if summary["status"] == "failed" else 0


def _record_outcome_history(
    config: dict[str, Any],
    run: RunContext,
    *,
    clock: Callable[[], datetime],
) -> None:
    from halpha.outcome.outcome_history import OUTCOME_HISTORY_STATE_ARTIFACT, write_outcome_history

    try:
        write_outcome_history(config, run, now=clock())
    except Exception as exc:
        run.manifest["outcome_history"] = {
            "status": "failed",
            "artifact": OUTCOME_HISTORY_STATE_ARTIFACT,
            "error": str(exc),
        }
        run.manifest.setdefault("counts", {})["outcome_history_errors"] = 1


def _record_research_data_catalog(
    config: dict[str, Any],
    run: RunContext,
    *,
    clock: Callable[[], datetime],
) -> None:
    from halpha.data.research_data_catalog import write_research_data_catalog

    try:
        write_research_data_catalog(config, run, now=clock())
    except Exception as exc:
        run.manifest["research_data_catalog"] = {
            "status": "failed",
            "artifact": "data/research/metadata/research_data_catalog.json",
            "error": str(exc),
        }


def _error_summary(
    stage: str,
    reason: str,
    *,
    details: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"stage": stage, "message": reason}
    if details:
        error.update(details)
    if diagnostic:
        error["diagnostic"] = diagnostic
    return error


def _set_codex_status(run: RunContext, *, stage: str, status: str) -> None:
    if stage == "run_codex_report":
        if run.manifest["codex"].get("status") == "disabled" and status == "succeeded":
            return
        run.manifest["codex"]["status"] = status


def _write_manifest(run: RunContext) -> None:
    write_json(run.manifest_path, run.manifest)


def _clock(now: datetime | None) -> Callable[[], datetime]:
    if now is not None:
        return lambda: now
    return lambda: datetime.now(timezone.utc)


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
    derivatives = market.get("derivatives") if isinstance(market, dict) else {}
    macro_calendar = config.get("macro_calendar", {})
    onchain_flow = config.get("onchain_flow", {})
    derivatives_summary = {}
    if isinstance(derivatives, dict):
        derivatives_summary = {
            "enabled": derivatives.get("enabled"),
            "source": derivatives.get("source"),
            "symbols": list(derivatives.get("symbols", [])),
            "data_classes": list(derivatives.get("data_classes", [])),
            "periods": list(derivatives.get("periods", [])),
        }
    macro_calendar_summary = {}
    if isinstance(macro_calendar, dict):
        macro_calendar_summary = {
            "enabled": macro_calendar.get("enabled"),
            "source": macro_calendar.get("source"),
            "data_classes": list(macro_calendar.get("data_classes", [])),
            "regions": list(macro_calendar.get("regions", [])),
        }
    onchain_flow_summary = {}
    if isinstance(onchain_flow, dict):
        onchain_flow_summary = {
            "enabled": onchain_flow.get("enabled"),
            "source": onchain_flow.get("source"),
            "data_classes": list(onchain_flow.get("data_classes", [])),
            "assets": list(onchain_flow.get("assets", [])),
            "chains": list(onchain_flow.get("chains", [])),
        }

    return {
        "market": {
            "enabled": market.get("enabled"),
            "source": market.get("source"),
            "symbols": list(market.get("symbols", [])),
            "derivatives": derivatives_summary,
        },
        "macro_calendar": macro_calendar_summary,
        "onchain_flow": onchain_flow_summary,
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
    return display_path(path, base=config_base(path))

