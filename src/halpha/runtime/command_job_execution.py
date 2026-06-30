from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from halpha.data.data_collection_service import collect_research_data
from halpha.data.data_inspection import DataInspectionError, inspect_local_data
from halpha.market.ohlcv_collection import OHLCVCollectionError, display_collection_artifacts
from halpha.monitor.monitoring import (
    inspect_monitor_health,
    load_monitor_config,
    monitor_config_lines,
    run_monitor_cycle,
)
from halpha.outcome.outcome_inspection import OutcomeInspectionError, inspect_local_outcomes
from halpha.pipeline import run_pipeline, run_pipeline_stage
from halpha.product.product_validation_inspection import inspect_product_validation
from halpha.runtime.command_job_commands import CommandSpec
from halpha.runtime.pipeline_contracts import PipelineError
from halpha.storage import artifact_base, display_path
from halpha.strategy.strategy_optimization import DEFAULT_MAX_COMBINATIONS
from halpha.strategy.workbench_service import (
    run_strategy_backtest_action,
    run_strategy_experiment_action,
    run_strategy_optimization_action,
)
from halpha.text.standalone_text_intelligence import run_standalone_text_intelligence
from halpha.text.text_event_collection import TextEventCollectionError
from halpha.text.text_models import prepare_text_models
from halpha.workbench.workbench import build_workbench_summary, inspect_workbench_summary


@dataclass(frozen=True)
class CommandJobExecutionResult:
    exit_code: int
    stdout: str
    stderr: str = ""


def execute_command_job(
    config: dict[str, Any],
    *,
    config_path: Path,
    spec: CommandSpec,
    params: dict[str, Any],
    run_trigger: dict[str, Any],
) -> CommandJobExecutionResult:
    intent = spec.intent
    try:
        if intent in {"run", "run_no_codex", "run_until"}:
            return _execute_run(config, config_path=config_path, spec=spec, params=params, run_trigger=run_trigger)
        if intent == "stage_rerun":
            return _execute_stage_rerun(config, config_path=config_path, params=params, run_trigger=run_trigger)
        if intent == "validate":
            return _execute_validate(config, config_path=config_path, params=params)
        if intent == "data_inspect":
            return _execute_data_inspect(config, config_path=config_path, params=params)
        if intent == "outcomes_inspect":
            return _execute_outcomes_inspect(config, config_path=config_path, params=params)
        if intent == "workbench_build":
            return _execute_workbench_build(config, config_path=config_path, params=params)
        if intent == "workbench_inspect":
            return _execute_workbench_inspect(config, config_path=config_path)
        if intent == "monitor_inspect":
            return _execute_monitor_inspect(config, config_path=config_path)
        if intent in {"monitor_dry_run", "monitor_once"}:
            return _execute_monitor_run(config, config_path=config_path, dry_run=intent == "monitor_dry_run")
        if intent == "backtest":
            return _execute_backtest(config, config_path=config_path, params=params)
        if intent == "experiment":
            return _execute_experiment(config, config_path=config_path, params=params)
        if intent == "optimize":
            return _execute_optimize(config, config_path=config_path, params=params)
        if intent == "text_models_prepare":
            return _execute_text_models_prepare(config, config_path=config_path, params=params)
        if intent == "text_intel":
            return _execute_text_intel(config, config_path=config_path, params=params)
        if intent == "data_collect":
            return _execute_data_collect(config, config_path=config_path, params=params, run_trigger=run_trigger)
    except ValueError as exc:
        return CommandJobExecutionResult(exit_code=2, stdout="", stderr=f"{exc}\n")
    return CommandJobExecutionResult(exit_code=3, stdout="", stderr=f"unsupported internal job intent: {intent}\n")


def _execute_run(
    config: dict[str, Any],
    *,
    config_path: Path,
    spec: CommandSpec,
    params: dict[str, Any],
    run_trigger: dict[str, Any],
) -> CommandJobExecutionResult:
    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage=str(params.get("stage_name") or "") or None,
        skip_codex=spec.intent == "run_no_codex",
        run_trigger=run_trigger,
    )
    manifest = _display(result.run.manifest_path, config_path=config_path)
    if result.succeeded:
        lines = [
            "Halpha run succeeded.",
            f"run_id: {result.run.run_id}",
            f"manifest: {manifest}",
        ]
        report_artifact = result.run.manifest.get("artifacts", {}).get("report")
        if report_artifact:
            lines.insert(2, f"report: {_display(result.run.run_dir / report_artifact, config_path=config_path)}")
        return _ok(lines)
    return _fail(
        result.exit_code,
        [
            "Halpha run failed.",
            f"stage: {result.failed_stage}",
            f"reason: {result.reason}",
            f"manifest: {manifest}",
        ],
    )


def _execute_stage_rerun(
    config: dict[str, Any],
    *,
    config_path: Path,
    params: dict[str, Any],
    run_trigger: dict[str, Any],
) -> CommandJobExecutionResult:
    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=Path(str(params.get("run_dir") or "")),
        stage=str(params.get("stage_name") or ""),
        run_trigger=run_trigger,
    )
    manifest = _display(result.run.manifest_path, config_path=config_path)
    if result.succeeded:
        return _ok(["Halpha stage succeeded.", f"run_id: {result.run.run_id}", f"manifest: {manifest}"])
    return _fail(
        result.exit_code,
        ["Halpha stage failed.", f"stage: {result.failed_stage}", f"reason: {result.reason}", f"manifest: {manifest}"],
    )


def _execute_validate(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    result = inspect_product_validation(config, config_path=config_path, run_dir=_optional_path(params.get("run_dir")))
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=_lines(result.lines))


def _execute_data_inspect(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    try:
        result = inspect_local_data(config, config_path=config_path, run_dir=_optional_path(params.get("run_dir")))
    except DataInspectionError as exc:
        return _fail(exc.exit_code, ["Halpha data inspection failed.", f"reason: {exc}"])
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=_lines(result.lines))


def _execute_outcomes_inspect(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    try:
        result = inspect_local_outcomes(config, config_path=config_path, run_dir=_optional_path(params.get("run_dir")))
    except OutcomeInspectionError as exc:
        return _fail(exc.exit_code, ["Halpha outcome inspection failed.", f"reason: {exc}"])
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=_lines(result.lines))


def _execute_workbench_build(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    result = build_workbench_summary(config, config_path=config_path, run_dir=_optional_path(params.get("run_dir")))
    lines = [
        "Halpha workbench build succeeded.",
        f"status: {result.summary.get('status') or 'unknown'}",
        f"summary: {_display(result.summary_path, config_path=config_path)}",
        "codex: not_run",
    ]
    return _ok(lines)


def _execute_workbench_inspect(config: dict[str, Any], *, config_path: Path) -> CommandJobExecutionResult:
    result = inspect_workbench_summary(config, config_path=config_path)
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=_lines(result.lines))


def _execute_monitor_inspect(config: dict[str, Any], *, config_path: Path) -> CommandJobExecutionResult:
    result = inspect_monitor_health(config, config_path=config_path)
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=_lines(result.lines))


def _execute_monitor_run(config: dict[str, Any], *, config_path: Path, dry_run: bool) -> CommandJobExecutionResult:
    if dry_run:
        settings = load_monitor_config(config)
        return _ok(["Halpha monitor dry run succeeded.", "cycle_execution: not_run", *monitor_config_lines(settings)])
    try:
        result = run_monitor_cycle(config, config_path=config_path)
    except PipelineError as exc:
        return _fail(exc.exit_code, ["Halpha monitor run failed.", f"stage: {exc.stage or 'monitor'}", f"reason: {exc}"])
    manifest = _display(result.manifest_path, config_path=config_path)
    if result.succeeded:
        lines = [
            "Halpha monitor cycle succeeded.",
            f"cycle_id: {result.cycle_id}",
            f"target_stage: {result.target_stage}",
            f"no_codex: {str(result.no_codex).lower()}",
            f"monitor_manifest: {manifest}",
        ]
        if result.run_id:
            lines.insert(2, f"run_id: {result.run_id}")
        return _ok(lines)
    return _fail(
        result.exit_code,
        [
            "Halpha monitor run failed.",
            "stage: monitor",
            *([f"reason: {result.reason}"] if result.reason else []),
            f"monitor_manifest: {manifest}",
        ],
    )


def _execute_backtest(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    result = run_strategy_backtest_action(
        config,
        config_path=config_path,
        strategy_name=str(params.get("strategy_name") or ""),
        source=str(params.get("source") or "") or None,
        symbol=str(params.get("symbol") or ""),
        timeframe=str(params.get("timeframe") or ""),
        start=str(params.get("start") or "") or None,
        end=str(params.get("end") or "") or None,
        output_dir=_optional_path(params.get("output_dir")),
    )
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=result.stdout)


def _execute_experiment(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    result = run_strategy_experiment_action(
        config,
        config_path=config_path,
        strategy_names=params.get("strategy_names") if isinstance(params.get("strategy_names"), list) else None,
        output_dir=_optional_path(params.get("output_dir")),
    )
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=result.stdout)


def _execute_optimize(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    result = run_strategy_optimization_action(
        config,
        config_path=config_path,
        strategy_name=str(params.get("strategy_name") or ""),
        source=str(params.get("source") or "") or None,
        symbol=str(params.get("symbol") or "") or None,
        timeframe=str(params.get("timeframe") or "") or None,
        grid=params.get("grid") if isinstance(params.get("grid"), dict) else None,
        grid_args=params.get("grid_args") if isinstance(params.get("grid_args"), list) else None,
        max_combinations=_positive_int(params.get("max_combinations"), default=DEFAULT_MAX_COMBINATIONS),
        walk_forward_policy=_walk_forward_policy(params),
        output_dir=_optional_path(params.get("output_dir")),
    )
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=result.stdout)


def _execute_text_models_prepare(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    result = prepare_text_models(config, config_path=config_path, output_dir=_optional_path(params.get("output_dir")))
    lines = [
        "Halpha text model preparation completed." if result.succeeded else "Halpha text model preparation failed.",
        f"status: {result.status}",
        f"manifest: {_display(result.manifest_path, config_path=config_path)}",
    ]
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=_lines(lines))


def _execute_text_intel(config: dict[str, Any], *, config_path: Path, params: dict[str, Any]) -> CommandJobExecutionResult:
    result = run_standalone_text_intelligence(
        config,
        config_path=config_path,
        input_path=_optional_path(params.get("input_path")),
        output_dir=_optional_path(params.get("output_dir")),
    )
    output = _display(result.output_dir, config_path=config_path)
    lines = [
        "Halpha text intelligence succeeded." if result.succeeded else "Halpha text intelligence failed.",
        f"status: {result.status}",
        f"output_dir: {output}",
        "text_event_records: analysis/text_event_records.json",
        "text_event_classification_evidence: analysis/text_event_classification_evidence.json",
        "text_event_topics: analysis/text_event_topics.json",
        "text_event_signals: analysis/text_event_signals.json",
        "event_intelligence_material: analysis/event_intelligence_material.md",
        f"manifest: {_display(result.manifest_path, config_path=config_path)}",
    ]
    if result.reason:
        lines.insert(2, f"reason: {result.reason}")
    return CommandJobExecutionResult(exit_code=result.exit_code, stdout=_lines(lines))


def _execute_data_collect(
    config: dict[str, Any],
    *,
    config_path: Path,
    params: dict[str, Any],
    run_trigger: dict[str, Any],
) -> CommandJobExecutionResult:
    try:
        result = collect_research_data(
            config,
            config_path=config_path,
            data_type=str(params.get("data_type") or ""),
            source=str(params.get("source") or "") or None,
            symbol=str(params.get("symbol") or "") or None,
            timeframe=str(params.get("timeframe") or "") or None,
            requested_start=str(params.get("start") or ""),
            requested_end=str(params.get("end") or ""),
            apply=True,
            max_exact_windows=_positive_int(params.get("max_exact_windows"), default=3),
            merge_gap_threshold_seconds=_non_negative_int(params.get("merge_gap_threshold_seconds"), default=0),
            min_fetch_window_seconds=_non_negative_int(params.get("min_fetch_window_seconds"), default=0),
            run_trigger=run_trigger,
        )
    except (OHLCVCollectionError, TextEventCollectionError, ValueError) as exc:
        exit_code = getattr(exc, "exit_code", 2)
        return _fail(exit_code, ["Halpha data collection failed.", f"reason: {exc}"])
    except PipelineError as exc:
        return _fail(exc.exit_code, ["Halpha data collection failed.", f"reason: {exc}"])
    lines = _data_collection_lines(result, config_path=config_path)
    status = str(result.get("status") or "")
    exit_code = 3 if status in {"failed", "blocked"} else 0
    return CommandJobExecutionResult(exit_code=exit_code, stdout=_lines(lines))


def _data_collection_lines(result: dict[str, Any], *, config_path: Path) -> list[str]:
    title = "Halpha data collection failed." if result.get("status") in {"failed", "blocked"} else "Halpha data collection apply succeeded."
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
    lines = [
        title,
        f"status: {result.get('status')}",
        f"mode: {result.get('mode')}",
        f"data_type: {result.get('data_type')}",
        f"source: {result.get('source')}",
        f"symbol: {result.get('symbol')}",
        f"timeframe: {result.get('timeframe')}",
        f"requested_start: {result.get('requested_start')}",
        f"requested_end: {result.get('requested_end')}",
        f"strategy: {plan.get('strategy')}",
    ]
    for key in ("planned_fetch_windows", "raw_items", "raw_errors", "fetched_records", "window_records", "stored_records", "coverage_records_written", "coverage_state_records"):
        if key in counts:
            lines.append(f"{key}: {counts[key]}")
    for key, value in sorted(display_collection_artifacts(result, config_path=config_path).items()):
        lines.append(f"{key}: {value}")
    for warning in (result.get("warnings") or [])[:10]:
        lines.append(f"warning: {warning}")
    for error in (result.get("errors") or [])[:10]:
        if isinstance(error, dict):
            lines.append(f"error: {error.get('message')}")
    return lines


def _optional_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value)


def _positive_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("positive integer parameter is invalid.")
    return value


def _non_negative_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("non-negative integer parameter is invalid.")
    return value


def _walk_forward_policy(params: dict[str, Any]) -> dict[str, Any] | None:
    policy = {
        key: params[param_name]
        for key, param_name in {
            "train_rows": "walk_forward_train_rows",
            "validation_rows": "walk_forward_validation_rows",
            "step_rows": "walk_forward_step_rows",
            "min_windows": "walk_forward_min_windows",
        }.items()
        if params.get(param_name) is not None
    }
    return policy or None


def _display(path: Path, *, config_path: Path) -> str:
    return display_path(path, base=artifact_base(config_path))


def _ok(lines: list[str]) -> CommandJobExecutionResult:
    return CommandJobExecutionResult(exit_code=0, stdout=_lines(lines))


def _fail(exit_code: int, lines: list[str]) -> CommandJobExecutionResult:
    return CommandJobExecutionResult(exit_code=exit_code, stdout=_lines(lines))


def _lines(lines: list[str]) -> str:
    return "\n".join(str(line) for line in lines if line is not None) + "\n"
