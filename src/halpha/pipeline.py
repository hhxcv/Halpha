from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .storage import ensure_directory, write_json


STAGE_ORDER = (
    "collect_market_data",
    "collect_text_events",
    "sync_ohlcv",
    "build_market_data_views",
    "evaluate_quant_strategies",
    "evaluate_market_strategy_signals",
    "build_market_signals",
    "build_market_signal_material",
    "build_market_regime_assessment",
    "build_risk_assessment",
    "build_decision_recommendations",
    "build_analysis_materials",
    "build_research_context",
    "build_codex_context",
    "run_codex_report",
)

StageHandler = Callable[[dict[str, Any], "RunContext"], list[str] | None]


class PipelineError(Exception):
    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        exit_code: int = 1,
        artifacts: list[str] | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code
        self.artifacts = artifacts or []
        self.error_details = error_details or {}


class StageNotImplementedError(PipelineError):
    def __init__(self, stage: str) -> None:
        super().__init__(f"stage {stage} is not implemented", stage=stage, exit_code=3)


class StageSelectionError(Exception):
    """Raised when a requested validation stage is not known."""


@dataclass(frozen=True)
class RunContext:
    run_id: str
    run_dir: Path
    raw_dir: Path
    analysis_dir: Path
    codex_context_dir: Path
    report_dir: Path
    manifest_path: Path
    config_path: Path
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
    until_stage: str | None = None,
    skip_codex: bool = False,
) -> RunResult:
    _validate_optional_stage(until_stage, option_name="--until")
    clock = _clock(now)
    run = _create_run_context(config, config_path=config_path, now=clock())
    _record_validation_mode(run, until_stage=until_stage, skip_codex=skip_codex)
    _write_manifest(run)

    handlers = _stage_handlers(stage_handlers)

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
                finished_at=_utc_timestamp(clock()),
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

    handlers = _stage_handlers(stage_handlers)
    failure = _run_stage_handler(
        config,
        run,
        handlers[stage],
        stage=stage,
        stage_record=stage_record,
        finished_at=_utc_timestamp(clock()),
    )
    if failure:
        return failure

    run.manifest["status"] = "succeeded"
    run.manifest["finished_at"] = _utc_timestamp(clock())
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


def _stage_handlers(overrides: dict[str, StageHandler] | None = None) -> dict[str, StageHandler]:
    handlers = {stage: _unimplemented_handler(stage) for stage in STAGE_ORDER}
    handlers["collect_market_data"] = _collect_market_data
    handlers["collect_text_events"] = _collect_text_events
    handlers["sync_ohlcv"] = _sync_ohlcv
    handlers["build_market_data_views"] = _build_market_data_views
    handlers["evaluate_quant_strategies"] = _evaluate_quant_strategies
    handlers["evaluate_market_strategy_signals"] = _evaluate_market_strategy_signals
    handlers["build_market_signals"] = _build_market_signals
    handlers["build_market_signal_material"] = _build_market_signal_material
    handlers["build_market_regime_assessment"] = _build_market_regime_assessment
    handlers["build_risk_assessment"] = _build_risk_assessment
    handlers["build_decision_recommendations"] = _build_decision_recommendations
    handlers["build_analysis_materials"] = _build_analysis_materials
    handlers["build_research_context"] = _build_research_context
    handlers["build_codex_context"] = _build_codex_context
    handlers["run_codex_report"] = _run_codex_report
    if overrides:
        handlers.update(overrides)
    return handlers


def _run_stage_handler(
    config: dict[str, Any],
    run: RunContext,
    handler: StageHandler,
    *,
    stage: str,
    stage_record: dict[str, Any],
    finished_at: str,
) -> RunResult | None:
    try:
        artifacts = handler(config, run)
    except PipelineError as exc:
        failed_stage = exc.stage or stage
        reason = str(exc)
        error = _error_summary(failed_stage, reason, details=exc.error_details)
        stage_record["status"] = "failed"
        stage_record["finished_at"] = finished_at
        stage_record["artifacts"] = exc.artifacts
        stage_record["error"] = error
        _set_codex_status(run, stage=stage, status="failed")
        _finish_manifest(run, status="failed", error=error, finished_at=finished_at)
        return RunResult(False, run, exc.exit_code, failed_stage, reason)
    except Exception as exc:
        reason = f"stage {stage} failed: {exc}"
        error = _error_summary(stage, reason)
        stage_record["status"] = "failed"
        stage_record["finished_at"] = finished_at
        stage_record["error"] = error
        _set_codex_status(run, stage=stage, status="failed")
        _finish_manifest(run, status="failed", error=error, finished_at=finished_at)
        return RunResult(False, run, 1, stage, reason)

    stage_record["status"] = "succeeded"
    stage_record["finished_at"] = finished_at
    stage_record["artifacts"] = artifacts or []
    _set_codex_status(run, stage=stage, status="succeeded")
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


def _stages_after(stage: str) -> list[str]:
    index = STAGE_ORDER.index(stage)
    return list(STAGE_ORDER[index + 1 :])


def _validate_optional_stage(stage: str | None, *, option_name: str) -> None:
    if stage is None:
        return
    _validate_stage(stage, option_name=option_name)


def _validate_stage(stage: str, *, option_name: str) -> None:
    if stage not in STAGE_ORDER:
        supported = ", ".join(STAGE_ORDER)
        raise StageSelectionError(f"{option_name} must be one of: {supported}.")


def _record_validation_mode(run: RunContext, *, until_stage: str | None, skip_codex: bool) -> None:
    if until_stage is None and not skip_codex:
        return
    run.manifest["validation"] = {
        "mode": "run",
        "until_stage": until_stage,
        "skip_codex": skip_codex,
    }


def _unimplemented_handler(stage: str) -> StageHandler:
    def handler(config: dict[str, Any], run: RunContext) -> list[str] | None:
        raise StageNotImplementedError(stage)

    return handler


def _collect_market_data(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .collectors.market import collect_market_data

    return collect_market_data(config, run)


def _collect_text_events(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .collectors.text import collect_text_events

    return collect_text_events(config, run)


def _sync_ohlcv(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .ohlcv_sync import sync_ohlcv_history

    return sync_ohlcv_history(config, run)


def _build_market_data_views(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .market_data_views import build_market_data_views

    return build_market_data_views(config, run)


def _evaluate_quant_strategies(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .quant_strategies import evaluate_quant_strategies

    return evaluate_quant_strategies(config, run)


def _evaluate_market_strategy_signals(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .quant_signals import evaluate_market_strategy_signals

    return evaluate_market_strategy_signals(config, run)


def _build_market_signals(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .market_signals import build_market_signals

    return build_market_signals(config, run)


def _build_market_signal_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .market_signals import build_market_signal_material

    return build_market_signal_material(config, run)


def _build_market_regime_assessment(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .decision_intelligence import build_market_regime_assessment

    return build_market_regime_assessment(config, run)


def _build_risk_assessment(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .decision_intelligence import build_risk_assessment

    return build_risk_assessment(config, run)


def _build_decision_recommendations(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .decision_intelligence import build_decision_recommendations

    return build_decision_recommendations(config, run)


def _build_analysis_materials(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .analysis.market_material import build_market_material
    from .analysis.text_material import build_text_material

    artifacts = []
    try:
        artifacts.extend(build_market_material(config, run))
        artifacts.extend(build_text_material(config, run))
    except PipelineError as exc:
        if artifacts and not exc.artifacts:
            exc.artifacts = artifacts
        raise
    return artifacts


def _build_research_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .analysis.research_context import build_research_context

    return build_research_context(config, run)


def _build_codex_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .codex.context_builder import build_codex_context

    return build_codex_context(config, run)


def _run_codex_report(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from .codex.runner import run_codex_report

    return run_codex_report(config, run)


def _finish_manifest(run: RunContext, *, status: str, error: dict[str, Any], finished_at: str) -> None:
    run.manifest["status"] = status
    run.manifest["finished_at"] = finished_at
    run.manifest["errors"].append(error)
    _write_manifest(run)


def _error_summary(stage: str, reason: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"stage": stage, "message": reason}
    if details:
        error.update(details)
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
