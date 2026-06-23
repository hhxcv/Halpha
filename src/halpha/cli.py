from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from halpha.config import ConfigError, load_config
from halpha.dashboard import (
    DEFAULT_DASHBOARD_HOST,
    DEFAULT_DASHBOARD_PORT,
    DashboardError,
    dashboard_config_ref,
    load_dashboard_startup_config,
    run_dashboard_service,
    sanitize_dashboard_message,
    validate_dashboard_host,
    validate_dashboard_port,
)
from halpha.data.data_inspection import DataInspectionError, inspect_local_data
from halpha.runtime.logging_utils import configure_local_logging
from halpha.monitor.monitoring import (
    inspect_monitor_health,
    load_monitor_config,
    monitor_config_lines,
    run_monitor_cycle,
    run_monitor_loop,
)
from halpha.outcome.outcome_inspection import OutcomeInspectionError, inspect_local_outcomes
from halpha.runtime.pipeline_contracts import PipelineError
from halpha.pipeline_stages import StageSelectionError
from halpha.pipeline import run_pipeline, run_pipeline_stage
from halpha.product.product_validation_inspection import inspect_product_validation
from halpha.strategy.standalone_backtest import StandaloneBacktestError, run_standalone_strategy_backtest
from halpha.text.standalone_text_intelligence import run_standalone_text_intelligence
from halpha.storage import display_path
from halpha.strategy.strategy_experiment import StrategyExperimentError, run_strategy_experiment
from halpha.text.text_models import prepare_text_models
from halpha.workbench.workbench import build_workbench_summary, inspect_workbench_summary


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="halpha")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Start a Halpha report run.")
    run_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    run_parser.add_argument(
        "--no-codex",
        action="store_true",
        help="Run pre-Codex stages and skip Codex report execution.",
    )
    run_parser.add_argument(
        "--until",
        help="Stop after the named pipeline stage and mark later stages as not run.",
    )

    stage_parser = subparsers.add_parser("stage", help="Run one pipeline stage against an existing run directory.")
    stage_parser.add_argument("stage_name", help="Pipeline stage name to run.")
    stage_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    stage_parser.add_argument("--run-dir", required=True, help="Existing Halpha run directory.")

    validate_parser = subparsers.add_parser("validate", help="Inspect product contract health without running stages.")
    validate_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    validate_parser.add_argument("--run-dir", help="Optional run directory to validate.")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Run the local web dashboard.",
        description="Run the local web dashboard.",
    )
    dashboard_parser.add_argument("--config", help="Optional path to a Halpha YAML config file.")
    dashboard_parser.add_argument(
        "--host",
        default=DEFAULT_DASHBOARD_HOST,
        help=f"Local dashboard host. Defaults to {DEFAULT_DASHBOARD_HOST}.",
    )
    dashboard_parser.add_argument(
        "--port",
        type=_positive_int_arg,
        default=DEFAULT_DASHBOARD_PORT,
        help=f"Local dashboard port. Defaults to {DEFAULT_DASHBOARD_PORT}.",
    )

    backtest_parser = subparsers.add_parser("backtest", help="Run one standalone strategy backtest.")
    backtest_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    backtest_parser.add_argument("--strategy", required=True, help="Configured strategy name to evaluate.")
    backtest_parser.add_argument("--symbol", required=True, help="Configured market symbol to evaluate.")
    backtest_parser.add_argument("--timeframe", required=True, help="Configured OHLCV timeframe to evaluate.")
    backtest_parser.add_argument("--output-dir", help="Directory for standalone backtest output artifacts.")

    experiment_parser = subparsers.add_parser("experiment", help="Run standalone strategy experiments.")
    experiment_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    experiment_parser.add_argument(
        "--strategy",
        action="append",
        help="Configured strategy name to include. May be repeated. Defaults to all enabled strategies.",
    )
    experiment_parser.add_argument("--output-dir", help="Directory for strategy experiment output artifacts.")

    text_models_parser = subparsers.add_parser("text-models", help="Manage local text intelligence models.")
    text_models_subparsers = text_models_parser.add_subparsers(dest="text_models_command", required=True)
    prepare_parser = text_models_subparsers.add_parser(
        "prepare",
        help="Explicitly prepare configured text intelligence models.",
    )
    prepare_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    prepare_parser.add_argument("--output-dir", help="Directory for model preparation metadata and cache.")

    text_intel_parser = subparsers.add_parser("text-intel", help="Run standalone text intelligence processing.")
    text_intel_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    text_intel_parser.add_argument("--input", help="Existing raw text events JSON artifact to process.")
    text_intel_parser.add_argument("--output-dir", help="Directory for standalone text intelligence output.")

    data_parser = subparsers.add_parser("data", help="Inspect local research data state.")
    data_subparsers = data_parser.add_subparsers(dest="data_command", required=True)
    inspect_parser = data_subparsers.add_parser(
        "inspect",
        help="Inspect local stores and data-quality state.",
        description="Inspect local stores and data-quality state.",
    )
    inspect_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    inspect_parser.add_argument("--run-dir", help="Optional run directory for data-quality inspection.")

    outcomes_parser = subparsers.add_parser("outcomes", help="Inspect local outcome tracking state.")
    outcomes_subparsers = outcomes_parser.add_subparsers(dest="outcomes_command", required=True)
    outcomes_inspect_parser = outcomes_subparsers.add_parser(
        "inspect",
        help="Inspect outcome targets, evaluations, material, and history state.",
        description="Inspect outcome targets, evaluations, material, and history state.",
    )
    outcomes_inspect_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    outcomes_inspect_parser.add_argument("--run-dir", help="Optional run directory for outcome artifact inspection.")

    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Manage local monitoring runs.",
        description="Manage local monitoring runs.",
    )
    monitor_subparsers = monitor_parser.add_subparsers(dest="monitor_command", required=True)
    monitor_run_parser = monitor_subparsers.add_parser(
        "run",
        help="Run or validate local monitor cycles without hidden background execution.",
        description="Run or validate local monitor cycles without hidden background execution.",
    )
    monitor_run_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    monitor_run_mode = monitor_run_parser.add_mutually_exclusive_group()
    monitor_run_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate monitor configuration and print effective settings without running a cycle.",
    )
    monitor_run_mode.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one bounded monitor cycle.",
    )
    monitor_run_mode.add_argument(
        "--max-cycles",
        type=_positive_int_arg,
        help="Run a finite local monitor loop for the given positive cycle count.",
    )
    monitor_run_parser.add_argument(
        "--interval-seconds",
        type=_positive_int_arg,
        help="Override the positive interval between finite-loop cycles.",
    )
    monitor_inspect_parser = monitor_subparsers.add_parser(
        "inspect",
        help="Inspect local monitor state.",
        description="Inspect local monitor state.",
    )
    monitor_inspect_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")

    workbench_parser = subparsers.add_parser(
        "workbench",
        help="Build or inspect local workbench delivery artifacts.",
        description="Build or inspect local workbench delivery artifacts.",
    )
    workbench_subparsers = workbench_parser.add_subparsers(dest="workbench_command", required=True)
    workbench_build_parser = workbench_subparsers.add_parser(
        "build",
        help="Build a local workbench summary from existing artifacts.",
        description="Build a local workbench summary from existing artifacts.",
    )
    workbench_build_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    workbench_build_parser.add_argument("--run-dir", help="Optional run directory to summarize.")
    workbench_inspect_parser = workbench_subparsers.add_parser(
        "inspect",
        help="Inspect the latest local workbench summary.",
        description="Inspect the latest local workbench summary.",
    )
    workbench_inspect_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(args.config, no_codex=args.no_codex, until_stage=args.until)

    if args.command == "stage":
        return _stage(args.stage_name, args.config, args.run_dir)

    if args.command == "validate":
        return _validate(args.config, run_dir=args.run_dir)

    if args.command == "dashboard":
        return _dashboard(args.config, host=args.host, port=args.port)

    if args.command == "backtest":
        return _backtest(
            args.config,
            strategy_name=args.strategy,
            symbol=args.symbol,
            timeframe=args.timeframe,
            output_dir=args.output_dir,
        )

    if args.command == "experiment":
        return _experiment(
            args.config,
            strategy_names=args.strategy,
            output_dir=args.output_dir,
        )

    if args.command == "text-models" and args.text_models_command == "prepare":
        return _text_models_prepare(args.config, output_dir=args.output_dir)

    if args.command == "text-intel":
        return _text_intel(args.config, input_path=args.input, output_dir=args.output_dir)

    if args.command == "data" and args.data_command == "inspect":
        return _data_inspect(args.config, run_dir=args.run_dir)

    if args.command == "outcomes" and args.outcomes_command == "inspect":
        return _outcomes_inspect(args.config, run_dir=args.run_dir)

    if args.command == "monitor" and args.monitor_command == "run":
        return _monitor_run(
            args.config,
            dry_run=args.dry_run,
            once=args.once,
            max_cycles=args.max_cycles,
            interval_seconds=args.interval_seconds,
        )

    if args.command == "monitor" and args.monitor_command == "inspect":
        return _monitor_inspect(args.config)

    if args.command == "workbench" and args.workbench_command == "build":
        return _workbench_build(args.config, run_dir=args.run_dir)

    if args.command == "workbench" and args.workbench_command == "inspect":
        return _workbench_inspect(args.config)

    parser.error(f"unknown command: {args.command}")
    return 1


def _run(config_arg: str, *, no_codex: bool = False, until_stage: str | None = None) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    LOGGER.info(
        "Halpha command started.",
        extra={"event": "cli.command.start", "command": "run", "no_codex": no_codex, "until_stage": until_stage},
    )

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        LOGGER.warning(
            "Halpha command failed.",
            extra={"event": "cli.command.failed", "command": "run", "stage": "config", "reason": str(exc)},
        )
        print("Halpha run failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = run_pipeline(
            config,
            config_path=config_path,
            until_stage=until_stage,
            skip_codex=no_codex,
        )
    except StageSelectionError as exc:
        LOGGER.warning(
            "Halpha command failed.",
            extra={"event": "cli.command.failed", "command": "run", "stage": "cli", "reason": str(exc)},
        )
        print("Halpha run failed.")
        print("stage: cli")
        print(f"reason: {exc}")
        return 2
    manifest = display_path(result.run.manifest_path)

    if result.succeeded:
        report_artifact = result.run.manifest.get("artifacts", {}).get("report")
        print("Halpha run succeeded.")
        print(f"run_id: {result.run.run_id}")
        if report_artifact:
            report = display_path(result.run.run_dir / report_artifact)
            print(f"report: {report}")
        if result.run.manifest.get("codex", {}).get("status") == "skipped":
            print("codex: skipped")
        print(f"manifest: {manifest}")
        LOGGER.info(
            "Halpha command succeeded.",
            extra={"event": "cli.command.succeeded", "command": "run", "run_id": result.run.run_id},
        )
        return 0

    LOGGER.warning(
        "Halpha command failed.",
        extra={
            "event": "cli.command.failed",
            "command": "run",
            "stage": result.failed_stage,
            "run_id": result.run.run_id,
            "exit_code": result.exit_code,
            "reason": result.reason,
        },
    )
    print("Halpha run failed.")
    print(f"stage: {result.failed_stage}")
    print(f"reason: {result.reason}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _stage(stage_name: str, config_arg: str, run_dir_arg: str) -> int:
    config_path = Path(config_arg)
    run_dir = Path(run_dir_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("stage", stage_name=stage_name)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("stage", stage="config", reason=str(exc), stage_name=stage_name, exit_code=2)
        print("Halpha stage failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = run_pipeline_stage(
            config,
            config_path=config_path,
            run_dir=run_dir,
            stage=stage_name,
        )
    except StageSelectionError as exc:
        _log_command_failed("stage", stage="cli", reason=str(exc), stage_name=stage_name, exit_code=2)
        print("Halpha stage failed.")
        print("stage: cli")
        print(f"reason: {exc}")
        return 2
    except PipelineError as exc:
        _log_command_failed(
            "stage",
            stage=exc.stage or stage_name,
            reason=str(exc),
            stage_name=stage_name,
            exit_code=exc.exit_code,
        )
        print("Halpha stage failed.")
        print(f"stage: {exc.stage or stage_name}")
        print(f"reason: {exc}")
        return exc.exit_code

    manifest = display_path(result.run.manifest_path)
    if result.succeeded:
        print("Halpha stage succeeded.")
        print(f"run_id: {result.run.run_id}")
        print(f"stage: {stage_name}")
        print(f"manifest: {manifest}")
        _log_command_succeeded("stage", stage_name=stage_name, run_id=result.run.run_id)
        return 0

    _log_command_failed(
        "stage",
        stage=result.failed_stage or stage_name,
        reason=result.reason or "stage failed",
        stage_name=stage_name,
        run_id=result.run.run_id,
        exit_code=result.exit_code,
    )
    print("Halpha stage failed.")
    print(f"stage: {result.failed_stage}")
    print(f"reason: {result.reason}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _validate(config_arg: str, *, run_dir: str | None) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("validate", explicit_run=run_dir is not None)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("validate", stage="config", reason=str(exc), exit_code=2)
        print("Halpha product validation failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    result = inspect_product_validation(
        config,
        config_path=config_path,
        run_dir=Path(run_dir) if run_dir else None,
    )
    for line in result.lines:
        print(line)
    if result.exit_code == 0:
        _log_command_succeeded("validate", status=result.status, explicit_run=run_dir is not None)
    else:
        _log_command_failed(
            "validate",
            stage="product_validation",
            reason=result.status,
            status=result.status,
            explicit_run=run_dir is not None,
            exit_code=result.exit_code,
        )
    return result.exit_code


def _dashboard(config_arg: str | None, *, host: str, port: int) -> int:
    log_config_path = Path(config_arg) if config_arg else Path("dashboard")
    _configure_logging(config_path=log_config_path)
    LOGGER.info(
        "Halpha command started.",
        extra={"event": "cli.command.start", "command": "dashboard", "host": host, "port": port},
    )

    try:
        startup = load_dashboard_startup_config(config_arg)
    except ConfigError as exc:
        LOGGER.warning(
            "Halpha command failed.",
            extra={"event": "cli.command.failed", "command": "dashboard", "stage": "config", "reason": str(exc)},
        )
        print("Halpha dashboard failed.")
        print("stage: config")
        print(f"reason: {sanitize_dashboard_message(str(exc), config_path=log_config_path)}")
        return 2

    config = startup.config
    config_path = startup.config_path
    _configure_logging(config_path=config_path or log_config_path, config=config)
    try:
        validate_dashboard_host(host)
        validate_dashboard_port(port)
        print("Halpha dashboard starting.")
        print(f"url: {_dashboard_url(host, port)}")
        if config_path is None:
            print("config: not configured")
            print("settings: open the dashboard Settings view to load a config file.")
        else:
            print(f"config: {dashboard_config_ref(config_path)}")
        LOGGER.info(
            "Halpha dashboard service starting.",
            extra={"event": "dashboard.service.start", "host": host, "port": port},
        )
        run_dashboard_service(config, config_path=config_path, host=host, port=port)
    except DashboardError as exc:
        LOGGER.error(
            "Halpha dashboard service failed.",
            extra={"event": "dashboard.service.failed", "host": host, "port": port, "reason": str(exc)},
        )
        print("Halpha dashboard failed.")
        print("stage: dashboard")
        print(f"reason: {sanitize_dashboard_message(str(exc), config_path=config_path or log_config_path)}")
        return exc.exit_code
    except KeyboardInterrupt:
        LOGGER.info(
            "Halpha dashboard service stopped.",
            extra={"event": "dashboard.service.stopped", "host": host, "port": port},
        )
        print("Halpha dashboard stopped.")
        return 0
    LOGGER.info(
        "Halpha dashboard service stopped.",
        extra={"event": "dashboard.service.stopped", "host": host, "port": port},
    )
    return 0


def _backtest(
    config_arg: str,
    *,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    output_dir: str | None,
) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start(
        "backtest",
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        output_dir_requested=output_dir is not None,
    )

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("backtest", stage="config", reason=str(exc), exit_code=2)
        print("Halpha backtest failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = run_standalone_strategy_backtest(
            config,
            config_path=config_path,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            output_dir=Path(output_dir) if output_dir else None,
        )
    except StandaloneBacktestError as exc:
        _log_command_failed("backtest", stage="backtest", reason=str(exc), exit_code=exc.exit_code)
        print("Halpha backtest failed.")
        print("stage: backtest")
        print(f"reason: {exc}")
        return exc.exit_code

    artifact = display_path(result.artifact_path)
    manifest = display_path(result.manifest_path)
    if result.succeeded:
        print("Halpha backtest succeeded.")
        print(f"status: {result.status}")
        print(f"strategy_backtest: {artifact}")
        print(f"manifest: {manifest}")
        _log_command_succeeded(
            "backtest",
            status=result.status,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
        )
        return 0

    _log_command_failed(
        "backtest",
        stage="backtest",
        reason=result.reason or result.status,
        status=result.status,
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        exit_code=result.exit_code,
    )
    print("Halpha backtest failed.")
    print(f"status: {result.status}")
    print(f"reason: {result.reason}")
    print(f"strategy_backtest: {artifact}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _experiment(
    config_arg: str,
    *,
    strategy_names: list[str] | None,
    output_dir: str | None,
) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start(
        "experiment",
        strategy_count=len(strategy_names or []),
        output_dir_requested=output_dir is not None,
    )

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("experiment", stage="config", reason=str(exc), exit_code=2)
        print("Halpha experiment failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = run_strategy_experiment(
            config,
            config_path=config_path,
            strategy_names=strategy_names,
            output_dir=Path(output_dir) if output_dir else None,
        )
    except StrategyExperimentError as exc:
        _log_command_failed("experiment", stage="experiment", reason=str(exc), exit_code=exc.exit_code)
        print("Halpha experiment failed.")
        print("stage: experiment")
        print(f"reason: {exc}")
        return exc.exit_code

    artifact = display_path(result.artifact_path)
    benchmark_suite = display_path(result.benchmark_suite_path)
    gates = display_path(result.gates_path)
    manifest = display_path(result.manifest_path)
    print("Halpha experiment succeeded.")
    print(f"status: {result.status}")
    print(f"strategy_experiment: {artifact}")
    print(f"strategy_benchmark_suite: {benchmark_suite}")
    print(f"strategy_effectiveness_gates: {gates}")
    print(f"manifest: {manifest}")
    if result.exit_code == 0:
        _log_command_succeeded("experiment", status=result.status, strategy_count=len(strategy_names or []))
    else:
        _log_command_failed(
            "experiment",
            stage="experiment",
            reason=result.status,
            status=result.status,
            strategy_count=len(strategy_names or []),
            exit_code=result.exit_code,
        )
    return result.exit_code


def _text_models_prepare(config_arg: str, *, output_dir: str | None) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("text-models prepare", output_dir_requested=output_dir is not None)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("text-models prepare", stage="config", reason=str(exc), exit_code=2)
        print("Halpha text model preparation failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    result = prepare_text_models(
        config,
        config_path=config_path,
        output_dir=Path(output_dir) if output_dir else None,
    )

    manifest = _safe_local_display_path(result.manifest_path)
    if result.succeeded:
        print("Halpha text model preparation completed.")
        print(f"status: {result.status}")
        print(f"manifest: {manifest}")
        _log_command_succeeded("text-models prepare", status=result.status)
        return 0

    _log_command_failed(
        "text-models prepare",
        stage="text_models",
        reason=(
            str(result.manifest.get("errors", [result.status])[0])
            if result.manifest.get("errors")
            else result.status
        ),
        status=result.status,
        exit_code=result.exit_code,
    )
    print("Halpha text model preparation failed.")
    print(f"status: {result.status}")
    if result.manifest.get("errors"):
        print(f"reason: {result.manifest['errors'][0]}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _text_intel(config_arg: str, *, input_path: str | None, output_dir: str | None) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start(
        "text-intel",
        input_path_provided=input_path is not None,
        output_dir_requested=output_dir is not None,
    )

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("text-intel", stage="config", reason=str(exc), exit_code=2)
        print("Halpha text intelligence failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    result = run_standalone_text_intelligence(
        config,
        config_path=config_path,
        input_path=Path(input_path) if input_path else None,
        output_dir=Path(output_dir) if output_dir else None,
    )

    manifest = _safe_local_display_path(result.manifest_path)
    output = _safe_local_display_path(result.output_dir)
    if result.succeeded:
        print("Halpha text intelligence succeeded.")
        print(f"status: {result.status}")
        print(f"output_dir: {output}")
        print("text_event_records: analysis/text_event_records.json")
        print("text_event_classification_evidence: analysis/text_event_classification_evidence.json")
        print("text_event_topics: analysis/text_event_topics.json")
        print("text_event_signals: analysis/text_event_signals.json")
        print("event_intelligence_material: analysis/event_intelligence_material.md")
        print(f"manifest: {manifest}")
        _log_command_succeeded("text-intel", status=result.status)
        return 0

    _log_command_failed(
        "text-intel",
        stage="text_intelligence",
        reason=result.reason or result.status,
        status=result.status,
        exit_code=result.exit_code,
    )
    print("Halpha text intelligence failed.")
    print(f"status: {result.status}")
    if result.reason:
        print(f"reason: {result.reason}")
    print(f"output_dir: {output}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _data_inspect(config_arg: str, *, run_dir: str | None) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("data inspect", explicit_run=run_dir is not None)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("data inspect", stage="config", reason=str(exc), exit_code=2)
        print("Halpha data inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = inspect_local_data(
            config,
            config_path=config_path,
            run_dir=Path(run_dir) if run_dir else None,
        )
    except DataInspectionError as exc:
        _log_command_failed("data inspect", stage="data_inspect", reason=str(exc), exit_code=exc.exit_code)
        print("Halpha data inspection failed.")
        print("stage: data_inspect")
        print(f"reason: {exc}")
        return exc.exit_code

    for line in result.lines:
        print(line)
    _log_command_succeeded("data inspect", status=result.status, explicit_run=run_dir is not None)
    return 0


def _outcomes_inspect(config_arg: str, *, run_dir: str | None) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("outcomes inspect", explicit_run=run_dir is not None)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("outcomes inspect", stage="config", reason=str(exc), exit_code=2)
        print("Halpha outcome inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = inspect_local_outcomes(
            config,
            config_path=config_path,
            run_dir=Path(run_dir) if run_dir else None,
        )
    except OutcomeInspectionError as exc:
        _log_command_failed(
            "outcomes inspect",
            stage="outcomes_inspect",
            reason=str(exc),
            exit_code=exc.exit_code,
        )
        print("Halpha outcome inspection failed.")
        print("stage: outcomes_inspect")
        print(f"reason: {exc}")
        return exc.exit_code

    for line in result.lines:
        print(line)
    _log_command_succeeded("outcomes inspect", status=result.status, explicit_run=run_dir is not None)
    return 0


def _monitor_run(
    config_arg: str,
    *,
    dry_run: bool,
    once: bool,
    max_cycles: int | None,
    interval_seconds: int | None,
) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    LOGGER.info(
        "Halpha command started.",
        extra={
            "event": "cli.command.start",
            "command": "monitor run",
            "dry_run": dry_run,
            "once": once,
            "max_cycles": max_cycles,
            "interval_seconds": interval_seconds,
        },
    )

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        LOGGER.warning(
            "Halpha command failed.",
            extra={"event": "cli.command.failed", "command": "monitor run", "stage": "config", "reason": str(exc)},
        )
        print("Halpha monitor run failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    if not dry_run:
        if interval_seconds is not None and max_cycles is None:
            LOGGER.warning(
                "Halpha command failed.",
                extra={
                    "event": "cli.command.failed",
                    "command": "monitor run",
                    "stage": "monitor",
                    "reason": "--interval-seconds requires --max-cycles.",
                },
            )
            print("Halpha monitor run failed.")
            print("stage: monitor")
            print("reason: --interval-seconds requires --max-cycles.")
            return 3
        if max_cycles is not None:
            settings = load_monitor_config(config)
            result = run_monitor_loop(
                config,
                config_path=config_path,
                max_cycles=max_cycles,
                interval_seconds=interval_seconds or settings.interval_seconds,
            )
            health = _safe_local_display_path(result.health_state_path)
            if result.succeeded:
                print("Halpha monitor loop succeeded.")
            else:
                print("Halpha monitor loop failed.")
            print(f"loop_id: {result.loop_id}")
            print(f"status: {result.status}")
            print(f"completed_cycles: {result.completed_cycles}")
            print(f"max_cycles: {result.max_cycles}")
            print(f"stop_reason: {result.stop_reason}")
            if result.cycle_results:
                print(f"latest_cycle_id: {result.cycle_results[-1].cycle_id}")
            if result.reason:
                print(f"reason: {result.reason}")
            print(f"health_state: {health}")
            LOGGER.log(
                logging.INFO if result.succeeded else logging.WARNING,
                "Halpha monitor loop finished.",
                extra={
                    "event": "monitor.loop.finished",
                    "loop_id": result.loop_id,
                    "status": result.status,
                    "completed_cycles": result.completed_cycles,
                    "max_cycles": result.max_cycles,
                    "stop_reason": result.stop_reason,
                    "exit_code": result.exit_code,
                    "reason": result.reason,
                },
            )
            return result.exit_code
        if not once:
            LOGGER.warning(
                "Halpha command failed.",
                extra={
                    "event": "cli.command.failed",
                    "command": "monitor run",
                    "stage": "monitor",
                    "reason": "choose --dry-run, --once, or --max-cycles.",
                },
            )
            print("Halpha monitor run failed.")
            print("stage: monitor")
            print("reason: choose --dry-run, --once, or --max-cycles.")
            return 3
        result = run_monitor_cycle(config, config_path=config_path)
        manifest = _safe_local_display_path(result.manifest_path)
        if result.succeeded:
            print("Halpha monitor cycle succeeded.")
            print(f"cycle_id: {result.cycle_id}")
            if result.run_id:
                print(f"run_id: {result.run_id}")
            print(f"target_stage: {result.target_stage}")
            print(f"no_codex: {str(result.no_codex).lower()}")
            print(f"monitor_manifest: {manifest}")
            LOGGER.info(
                "Halpha monitor cycle finished.",
                extra={
                    "event": "monitor.cycle.finished",
                    "cycle_id": result.cycle_id,
                    "status": result.status,
                    "run_id": result.run_id,
                    "target_stage": result.target_stage,
                    "no_codex": result.no_codex,
                    "exit_code": result.exit_code,
                },
            )
            return result.exit_code

        LOGGER.warning(
            "Halpha monitor cycle failed.",
            extra={
                "event": "monitor.cycle.finished",
                "cycle_id": result.cycle_id,
                "status": result.status,
                "target_stage": result.target_stage,
                "no_codex": result.no_codex,
                "exit_code": result.exit_code,
                "reason": result.reason,
            },
        )
        print("Halpha monitor run failed.")
        print("stage: monitor")
        if result.reason:
            print(f"reason: {result.reason}")
        print(f"target_stage: {result.target_stage}")
        print(f"no_codex: {str(result.no_codex).lower()}")
        print(f"monitor_manifest: {manifest}")
        return result.exit_code

    settings = load_monitor_config(config)
    print("Halpha monitor dry run succeeded.")
    print("cycle_execution: not_run")
    for line in monitor_config_lines(settings):
        print(line)
    LOGGER.info(
        "Halpha monitor dry run finished.",
        extra={"event": "monitor.dry_run.finished", "status": "succeeded"},
    )
    return 0


def _monitor_inspect(config_arg: str) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("monitor inspect")

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("monitor inspect", stage="config", reason=str(exc), exit_code=2)
        print("Halpha monitor inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    result = inspect_monitor_health(config, config_path=config_path)
    for line in result.lines:
        print(line)
    if result.exit_code == 0:
        _log_command_succeeded("monitor inspect")
    else:
        _log_command_failed(
            "monitor inspect",
            stage="monitor_inspect",
            reason="monitor inspection failed",
            exit_code=result.exit_code,
        )
    return result.exit_code


def _workbench_build(config_arg: str, *, run_dir: str | None) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("workbench build", explicit_run=run_dir is not None)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("workbench build", stage="config", reason=str(exc), exit_code=2)
        print("Halpha workbench build failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    result = build_workbench_summary(
        config,
        config_path=config_path,
        run_dir=Path(run_dir) if run_dir else None,
    )
    print("Halpha workbench build succeeded.")
    print(f"status: {result.summary.get('status') or 'unknown'}")
    print(f"summary: {_safe_local_display_path(result.summary_path)}")
    index_outputs = result.summary.get("index_outputs")
    if isinstance(index_outputs, dict):
        if index_outputs.get("markdown"):
            print(f"index_markdown: {index_outputs['markdown']}")
        if index_outputs.get("html"):
            print(f"index_html: {index_outputs['html']}")
    latest_run = result.summary.get("latest_run")
    if isinstance(latest_run, dict):
        fields = latest_run.get("fields")
        if isinstance(fields, dict) and fields.get("run_id"):
            print(f"latest_run_id: {fields['run_id']}")
        if isinstance(fields, dict) and fields.get("selection_key"):
            print(f"latest_run_source: {fields['selection_key']}")
    print("codex: not_run")
    _log_command_succeeded(
        "workbench build",
        status=str(result.summary.get("status") or "unknown"),
        explicit_run=run_dir is not None,
    )
    return 0


def _workbench_inspect(config_arg: str) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start("workbench inspect")

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("workbench inspect", stage="config", reason=str(exc), exit_code=2)
        print("Halpha workbench inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    result = inspect_workbench_summary(config, config_path=config_path)
    for line in result.lines:
        print(line)
    if result.exit_code == 0:
        _log_command_succeeded("workbench inspect")
    else:
        _log_command_failed(
            "workbench inspect",
            stage="workbench_inspect",
            reason="workbench inspection failed",
            exit_code=result.exit_code,
        )
    return result.exit_code


def _safe_local_display_path(path: Path) -> str:
    try:
        path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path.name
    return display_path(path)


def _dashboard_url(host: str, port: int) -> str:
    display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{display_host}:{port}"


def _log_command_start(command: str, **fields) -> None:
    LOGGER.info(
        "Halpha command started.",
        extra=_command_log_extra("cli.command.start", command, **fields),
    )


def _log_command_succeeded(command: str, **fields) -> None:
    LOGGER.info(
        "Halpha command succeeded.",
        extra=_command_log_extra("cli.command.succeeded", command, **fields),
    )


def _log_command_failed(
    command: str,
    *,
    stage: str,
    reason: str,
    exit_code: int | None = None,
    **fields,
) -> None:
    LOGGER.warning(
        "Halpha command failed.",
        extra=_command_log_extra(
            "cli.command.failed",
            command,
            stage=stage,
            reason=reason,
            exit_code=exit_code,
            **fields,
        ),
    )


def _command_log_extra(event: str, command: str, **fields) -> dict:
    extra = {"event": event, "command": command}
    for key, value in fields.items():
        if value is not None:
            extra[key] = value
    return extra


def _configure_logging(config_path: Path, *, config: dict | None = None) -> None:
    try:
        configure_local_logging(config_path=config_path, config=config)
    except OSError:
        return


def _positive_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed
