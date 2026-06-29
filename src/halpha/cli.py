from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from halpha.config import ConfigError, load_config
from halpha.data.data_collection_service import collect_research_data
from halpha.dashboard import (
    DEFAULT_DASHBOARD_HOST,
    DEFAULT_DASHBOARD_PORT,
    DashboardError,
    dashboard_service_status,
    dashboard_config_ref,
    load_dashboard_startup_config,
    restart_dashboard_service,
    run_dashboard_service,
    sanitize_dashboard_message,
    start_dashboard_service,
    stop_dashboard_service,
    validate_dashboard_host,
    validate_dashboard_port,
)
from halpha.data.data_export import DataExportError, export_data
from halpha.data.data_inspection import DataInspectionError, inspect_local_data
from halpha.data.run_archive_cleanup import (
    REPORT_ARCHIVE_DELETE_CONFIRMATION,
    RunArchiveCleanupError,
    apply_run_archive_cleanup,
    plan_run_archive_cleanup,
)
from halpha.market.ohlcv_collection import OHLCVCollectionError, display_collection_artifacts
from halpha.runtime.legacy_state_migration import (
    apply_legacy_state_migration,
    legacy_state_migration_dry_run,
    rebuild_run_index_from_manifests,
)
from halpha.runtime.exception_diagnostics import bounded_exception_diagnostic
from halpha.runtime.logging_utils import configure_local_logging, redact_private_text
from halpha.runtime.schedule_service import (
    ScheduleServiceError,
    load_schedule_startup_config,
    restart_schedule_service,
    run_schedule_service,
    schedule_service_error_message,
    schedule_service_status,
    start_schedule_service,
    stop_schedule_service,
)
from halpha.monitor.monitoring import (
    inspect_monitor_health,
    load_monitor_config,
    monitor_config_lines,
    run_monitor_cycle,
    run_monitor_loop,
)
from halpha.runtime.monitor_service import (
    MonitorServiceError,
    load_monitor_startup_config,
    monitor_service_error_message,
    monitor_service_status,
    restart_monitor_service,
    run_monitor_service,
    start_monitor_service,
    stop_monitor_service,
)
from halpha.outcome.outcome_inspection import OutcomeInspectionError, inspect_local_outcomes
from halpha.runtime.pipeline_contracts import PipelineError
from halpha.runtime.run_classification import run_trigger_from_env
from halpha.pipeline_stages import StageSelectionError
from halpha.pipeline import run_pipeline, run_pipeline_stage
from halpha.product.product_validation_inspection import inspect_product_validation
from halpha.text.standalone_text_intelligence import run_standalone_text_intelligence
from halpha.storage import display_path
from halpha.strategy.strategy_optimization import (
    DEFAULT_MAX_COMBINATIONS,
    DEFAULT_OPTIMIZATION_WALK_FORWARD_POLICY,
)
from halpha.strategy.workbench_service import (
    run_strategy_backtest_action,
    run_strategy_experiment_action,
    run_strategy_optimization_action,
)
from halpha.text.text_event_collection import TextEventCollectionError
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
        "dashboard_action",
        nargs="?",
        choices=("start", "status", "stop", "restart", "service"),
        default="start",
        help="Dashboard lifecycle action. Defaults to start.",
    )
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
    dashboard_parser.add_argument(
        "--restart-from-instance-id",
        help=argparse.SUPPRESS,
    )

    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Manage the local Schedule resident service.",
        description="Manage the local Schedule resident service.",
    )
    schedule_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    schedule_parser.add_argument(
        "schedule_action",
        nargs="?",
        choices=("start", "status", "stop", "restart", "service"),
        default="start",
        help="Schedule lifecycle action. Defaults to start.",
    )
    schedule_parser.add_argument(
        "--restart-from-instance-id",
        help=argparse.SUPPRESS,
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

    optimize_parser = subparsers.add_parser("optimize", help="Run a bounded strategy parameter optimization.")
    optimize_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    optimize_parser.add_argument("--strategy", required=True, help="Configured strategy name to optimize.")
    optimize_parser.add_argument(
        "--grid",
        action="append",
        default=[],
        metavar="KEY=VALUE[,VALUE]",
        help="Optimization grid override. May be repeated. Defaults to the strategy spec optimization space.",
    )
    optimize_parser.add_argument(
        "--max-combinations",
        type=_positive_int_arg,
        default=DEFAULT_MAX_COMBINATIONS,
        help=f"Maximum grid combinations to evaluate. Defaults to {DEFAULT_MAX_COMBINATIONS}.",
    )
    optimize_parser.add_argument(
        "--walk-forward-train-rows",
        type=_positive_int_arg,
        help=(
            "Training rows per walk-forward optimization window. "
            f"Defaults to {DEFAULT_OPTIMIZATION_WALK_FORWARD_POLICY['train_rows']}."
        ),
    )
    optimize_parser.add_argument(
        "--walk-forward-validation-rows",
        type=_positive_int_arg,
        help=(
            "Validation rows after each train window. "
            f"Defaults to {DEFAULT_OPTIMIZATION_WALK_FORWARD_POLICY['validation_rows']}."
        ),
    )
    optimize_parser.add_argument(
        "--walk-forward-step-rows",
        type=_positive_int_arg,
        help=(
            "Rows to advance between walk-forward windows. "
            f"Defaults to {DEFAULT_OPTIMIZATION_WALK_FORWARD_POLICY['step_rows']}."
        ),
    )
    optimize_parser.add_argument(
        "--walk-forward-min-windows",
        type=_positive_int_arg,
        help=(
            "Minimum successful validation windows required before walk-forward evidence is sufficient. "
            f"Defaults to {DEFAULT_OPTIMIZATION_WALK_FORWARD_POLICY['min_windows']}."
        ),
    )
    optimize_parser.add_argument("--output-dir", help="Directory for strategy optimization output artifacts.")

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
    collect_parser = data_subparsers.add_parser(
        "collect",
        help="Collect or backfill local research data without running a report.",
        description="Collect or backfill local research data without running a report.",
    )
    collect_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    collect_parser.add_argument(
        "--data-type",
        required=True,
        choices=("ohlcv", "text_event", "macro_calendar", "onchain_flow", "derivatives_market", "market_anomaly"),
        help="Data type to collect.",
    )
    collect_parser.add_argument(
        "--source",
        help="Configured OHLCV or text source to collect. Text defaults to all configured sources.",
    )
    collect_parser.add_argument("--symbol", help="Configured OHLCV symbol to collect.")
    collect_parser.add_argument("--timeframe", help="Configured OHLCV timeframe to collect.")
    collect_parser.add_argument("--start", required=True, help="Inclusive ISO 8601 UTC range start.")
    collect_parser.add_argument("--end", required=True, help="Exclusive ISO 8601 UTC range end.")
    collect_mode = collect_parser.add_mutually_exclusive_group()
    collect_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the collection plan without network fetches or writes. This is the default.",
    )
    collect_mode.add_argument(
        "--apply",
        action="store_true",
        help="Execute planned fetch windows and update local stores.",
    )
    collect_parser.add_argument(
        "--max-exact-windows",
        type=_positive_int_arg,
        default=3,
        help="Maximum exact missing windows before planning a wider full-range fetch.",
    )
    collect_parser.add_argument(
        "--merge-gap-threshold-seconds",
        type=_non_negative_int_arg,
        default=0,
        help="Merge planned fetch windows separated by this many seconds or less.",
    )
    collect_parser.add_argument(
        "--min-fetch-window-seconds",
        type=_non_negative_int_arg,
        default=0,
        help="Widen smaller fetch windows to at least this many seconds when possible.",
    )
    export_parser = data_subparsers.add_parser(
        "export",
        help="Export bounded local research data without bypassing query filters.",
        description="Export bounded local research data without bypassing query filters.",
    )
    export_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    export_parser.add_argument(
        "--data-type",
        required=True,
        choices=("ohlcv", "text_event", "macro_calendar", "onchain_flow", "derivatives_market", "market_anomaly"),
        help="Data type to export.",
    )
    export_parser.add_argument("--source", help="Configured source or source filter to export.")
    export_parser.add_argument("--symbol", help="Configured OHLCV symbol to export.")
    export_parser.add_argument("--timeframe", help="Configured OHLCV timeframe to export.")
    export_parser.add_argument(
        "--identity",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional event-like identity filter. May be repeated.",
    )
    export_parser.add_argument("--start", required=True, help="Inclusive ISO 8601 UTC range start.")
    export_parser.add_argument("--end", required=True, help="Exclusive ISO 8601 UTC range end.")
    export_parser.add_argument("--as-of", help="Optional ISO 8601 UTC no-lookahead boundary.")
    export_parser.add_argument(
        "--format",
        required=True,
        choices=("csv", "json", "parquet"),
        help="Output format. OHLCV supports csv or parquet; event-like data supports json or csv.",
    )
    export_parser.add_argument("--output", required=True, help="Local output path for the bounded export.")
    export_parser.add_argument(
        "--limit",
        type=_positive_int_arg,
        help="Optional positive record limit applied by the query layer.",
    )
    export_parser.add_argument(
        "--sort-order",
        choices=("asc", "desc"),
        default="asc",
        help="Event-like record sort order. Defaults to asc.",
    )
    migrate_state_parser = data_subparsers.add_parser(
        "migrate-state",
        help="Inspect or apply explicit legacy local state migration.",
        description="Inspect or apply explicit legacy local state migration.",
    )
    migrate_state_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    migrate_state_mode = migrate_state_parser.add_mutually_exclusive_group()
    migrate_state_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect legacy state and print a migration plan without changing files.",
    )
    migrate_state_mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply supported legacy state imports and create bounded backups.",
    )
    migrate_state_parser.add_argument(
        "--replace-schedule",
        action="store_true",
        help="Replace an existing unified daily report schedule with the legacy schedule.",
    )
    rebuild_index_parser = data_subparsers.add_parser(
        "rebuild-index",
        help="Rebuild the unified run index from current run manifests.",
        description="Rebuild the unified run index from current run manifests.",
    )
    rebuild_index_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    cleanup_runs_parser = data_subparsers.add_parser(
        "cleanup-runs",
        help="Plan or apply explicit cleanup for local run archives.",
        description="Plan or apply explicit cleanup for local run archives.",
    )
    cleanup_runs_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
    cleanup_mode = cleanup_runs_parser.add_mutually_exclusive_group()
    cleanup_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print a cleanup plan without deleting files. This is the default.",
    )
    cleanup_mode.add_argument(
        "--apply",
        action="store_true",
        help="Delete only the selected approved run archive directories.",
    )
    cleanup_runs_parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        help="Run id to delete in apply mode. May be repeated.",
    )
    cleanup_runs_parser.add_argument(
        "--include-report-runs",
        action="store_true",
        help="Allow explicitly selected report-bearing archives to become deletable with stronger confirmation.",
    )
    cleanup_runs_parser.add_argument(
        "--confirm-report-runs",
        help=f"Required text for report-bearing archive deletion: {REPORT_ARCHIVE_DELETE_CONFIRMATION}",
    )

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
    for monitor_action in ("start", "status", "stop", "restart", "service"):
        monitor_action_parser = monitor_subparsers.add_parser(
            monitor_action,
            help=f"{monitor_action.capitalize()} the local Monitor resident service.",
            description=f"{monitor_action.capitalize()} the local Monitor resident service.",
        )
        monitor_action_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")
        if monitor_action == "service":
            monitor_action_parser.add_argument(
                "--restart-from-instance-id",
                help=argparse.SUPPRESS,
            )
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
    try:
        return _dispatch_command(args, parser)
    except Exception as exc:
        return _handle_unhandled_cli_exception(args, exc)


def _dispatch_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "run":
        return _run(args.config, no_codex=args.no_codex, until_stage=args.until)

    if args.command == "stage":
        return _stage(args.stage_name, args.config, args.run_dir)

    if args.command == "validate":
        return _validate(args.config, run_dir=args.run_dir)

    if args.command == "dashboard":
        return _dashboard(
            args.config,
            action=args.dashboard_action,
            host=args.host,
            port=args.port,
            restart_from_instance_id=args.restart_from_instance_id,
        )

    if args.command == "schedule":
        return _schedule(
            args.config,
            action=args.schedule_action,
            restart_from_instance_id=args.restart_from_instance_id,
        )

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

    if args.command == "optimize":
        return _optimize(
            args.config,
            strategy_name=args.strategy,
            grid_args=args.grid,
            max_combinations=args.max_combinations,
            walk_forward_train_rows=args.walk_forward_train_rows,
            walk_forward_validation_rows=args.walk_forward_validation_rows,
            walk_forward_step_rows=args.walk_forward_step_rows,
            walk_forward_min_windows=args.walk_forward_min_windows,
            output_dir=args.output_dir,
        )

    if args.command == "text-models" and args.text_models_command == "prepare":
        return _text_models_prepare(args.config, output_dir=args.output_dir)

    if args.command == "text-intel":
        return _text_intel(args.config, input_path=args.input, output_dir=args.output_dir)

    if args.command == "data" and args.data_command == "inspect":
        return _data_inspect(args.config, run_dir=args.run_dir)

    if args.command == "data" and args.data_command == "collect":
        return _data_collect(
            args.config,
            data_type=args.data_type,
            source=args.source,
            symbol=args.symbol,
            timeframe=args.timeframe,
            requested_start=args.start,
            requested_end=args.end,
            apply=args.apply,
            max_exact_windows=args.max_exact_windows,
            merge_gap_threshold_seconds=args.merge_gap_threshold_seconds,
            min_fetch_window_seconds=args.min_fetch_window_seconds,
        )

    if args.command == "data" and args.data_command == "export":
        return _data_export(
            args.config,
            data_type=args.data_type,
            source=args.source,
            symbol=args.symbol,
            timeframe=args.timeframe,
            identity_args=args.identity,
            requested_start=args.start,
            requested_end=args.end,
            as_of=args.as_of,
            output_format=args.format,
            output_path=args.output,
            limit=args.limit,
            sort_order=args.sort_order,
        )

    if args.command == "data" and args.data_command == "migrate-state":
        return _data_migrate_state(
            args.config,
            apply=args.apply,
            replace_schedule=args.replace_schedule,
        )

    if args.command == "data" and args.data_command == "rebuild-index":
        return _data_rebuild_index(args.config)

    if args.command == "data" and args.data_command == "cleanup-runs":
        return _data_cleanup_runs(
            args.config,
            apply=args.apply,
            run_ids=args.run_id,
            include_report_archives=args.include_report_runs,
            confirm_report_deletion=args.confirm_report_runs,
        )

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

    if args.command == "monitor" and args.monitor_command in {"start", "status", "stop", "restart", "service"}:
        return _monitor_service(
            args.config,
            action=args.monitor_command,
            restart_from_instance_id=getattr(args, "restart_from_instance_id", None),
        )

    if args.command == "workbench" and args.workbench_command == "build":
        return _workbench_build(args.config, run_dir=args.run_dir)

    if args.command == "workbench" and args.workbench_command == "inspect":
        return _workbench_inspect(args.config)

    parser.error(f"unknown command: {args.command}")
    return 1


def _handle_unhandled_cli_exception(args: argparse.Namespace, exc: Exception) -> int:
    command = str(getattr(args, "command", None) or "unknown")
    config_arg = getattr(args, "config", None)
    config_path = Path(config_arg) if isinstance(config_arg, str) and config_arg else Path(command)
    if not logging.getLogger("halpha").handlers:
        _configure_logging(config_path=config_path)
    reason = redact_private_text(str(exc), config_path=config_path)
    LOGGER.error(
        "Halpha command crashed.",
        extra=_command_log_extra(
            "cli.command.crashed",
            command,
            stage="cli",
            reason=reason,
            exception_type=type(exc).__name__,
            diagnostic=bounded_exception_diagnostic(exc, context={"phase": "cli_dispatch"}),
            exit_code=1,
        ),
    )
    print("Halpha command failed.")
    print("stage: cli")
    print("reason: unhandled exception; inspect local logs.")
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
            run_trigger=run_trigger_from_env(
                default_source="CLI",
                default_intent=_run_command_intent(no_codex=no_codex, until_stage=until_stage),
            ),
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
    except PipelineError as exc:
        LOGGER.warning(
            "Halpha command failed.",
            extra={
                "event": "cli.command.failed",
                "command": "run",
                "stage": exc.stage or "pipeline",
                "exit_code": exc.exit_code,
                "reason": str(exc),
            },
        )
        print("Halpha run failed.")
        print(f"stage: {exc.stage or 'pipeline'}")
        print(f"reason: {exc}")
        return exc.exit_code
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


def _run_command_intent(*, no_codex: bool, until_stage: str | None) -> str:
    if until_stage is not None:
        return "run_until"
    if no_codex:
        return "run_no_codex"
    return "run"


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
            run_trigger=run_trigger_from_env(
                default_source="CLI",
                default_intent="stage_rerun",
                extra={"requested_stage": stage_name},
            ),
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


def _dashboard(
    config_arg: str | None,
    *,
    action: str,
    host: str,
    port: int,
    restart_from_instance_id: str | None = None,
) -> int:
    log_config_path = Path(config_arg) if config_arg else Path("dashboard")
    _configure_logging(config_path=log_config_path)
    LOGGER.info(
        "Halpha command started.",
        extra={"event": "cli.command.start", "command": "dashboard", "dashboard_action": action, "host": host, "port": port},
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
        if action == "service":
            LOGGER.info(
                "Halpha dashboard service foreground starting.",
                extra={"event": "dashboard.service.foreground.start", "host": host, "port": port},
            )
            run_dashboard_service(
                config,
                config_path=config_path,
                host=host,
                port=port,
                restart_from_instance_id=restart_from_instance_id,
            )
            LOGGER.info(
                "Halpha dashboard service foreground stopped.",
                extra={"event": "dashboard.service.foreground.stopped", "host": host, "port": port},
            )
            return 0
        if action == "start":
            print("Halpha dashboard starting.")
            print(f"url: {_dashboard_url(host, port)}")
            if config_path is None:
                print("config: not configured")
                print("settings: open the dashboard Settings view to load a config file.")
            else:
                print(f"config: {dashboard_config_ref(config_path)}")
            result = start_dashboard_service(config_arg, host=host, port=port)
            _print_dashboard_service_result("Halpha dashboard started.", result)
            return 0
        if action == "status":
            result = dashboard_service_status(config_arg, host=host, port=port)
            _print_dashboard_service_result("Halpha dashboard status.", result)
            return 0
        if action == "stop":
            result = stop_dashboard_service(config_arg, host=host, port=port)
            _print_dashboard_service_result("Halpha dashboard stop requested.", result)
            return 0
        if action == "restart":
            result = restart_dashboard_service(config_arg, host=host, port=port)
            _print_dashboard_service_result("Halpha dashboard restarted.", result)
            return 0
        raise DashboardError(f"unsupported dashboard action: {action}.")
    except DashboardError as exc:
        LOGGER.error(
            "Halpha dashboard service failed.",
            extra={"event": "dashboard.service.failed", "dashboard_action": action, "host": host, "port": port, "reason": str(exc)},
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
    return 0


def _print_dashboard_service_result(title: str, result: dict) -> None:
    print(title)
    print(f"status: {result.get('status')}")
    endpoint = result.get("endpoint") if isinstance(result.get("endpoint"), dict) else {}
    host = endpoint.get("host")
    port = endpoint.get("port")
    if isinstance(host, str) and isinstance(port, int):
        print(f"url: {_dashboard_url(host, port)}")
    instance_id = result.get("instance_id")
    if isinstance(instance_id, str) and instance_id:
        print(f"instance_id: {instance_id}")
    pid = result.get("pid")
    if isinstance(pid, int):
        print(f"pid: {pid}")
    health = result.get("health")
    if isinstance(health, str):
        print(f"health: {health}")
    for warning in result.get("warnings") or []:
        print(f"warning: {warning}")


def _schedule(
    config_arg: str,
    *,
    action: str,
    restart_from_instance_id: str | None = None,
) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    LOGGER.info(
        "Halpha command started.",
        extra={"event": "cli.command.start", "command": "schedule", "schedule_action": action},
    )

    startup = None
    if action in {"start", "restart", "service"}:
        try:
            startup = load_schedule_startup_config(config_arg)
        except ConfigError as exc:
            LOGGER.warning(
                "Halpha command failed.",
                extra={"event": "cli.command.failed", "command": "schedule", "stage": "config", "reason": str(exc)},
            )
            print("Halpha schedule failed.")
            print("stage: config")
            print(f"reason: {schedule_service_error_message(str(exc), config_path=config_path)}")
            return 2
        _configure_logging(config_path=startup.config_path, config=startup.config)

    try:
        if action == "service":
            assert startup is not None
            LOGGER.info(
                "Halpha schedule service foreground starting.",
                extra={"event": "schedule.service.foreground.start"},
            )
            run_schedule_service(
                startup.config,
                config_path=startup.config_path,
                restart_from_instance_id=restart_from_instance_id,
            )
            LOGGER.info(
                "Halpha schedule service foreground stopped.",
                extra={"event": "schedule.service.foreground.stopped"},
            )
            return 0
        if action == "start":
            assert startup is not None
            result = start_schedule_service(config_arg)
            _print_schedule_service_result("Halpha schedule started.", result)
            return 0
        if action == "status":
            result = schedule_service_status(config_arg)
            _print_schedule_service_result("Halpha schedule status.", result)
            return 0
        if action == "stop":
            result = stop_schedule_service(config_arg)
            _print_schedule_service_result("Halpha schedule stop requested.", result)
            return 0
        if action == "restart":
            assert startup is not None
            result = restart_schedule_service(config_arg)
            _print_schedule_service_result("Halpha schedule restarted.", result)
            return 0
        raise ScheduleServiceError(f"unsupported schedule action: {action}.")
    except ScheduleServiceError as exc:
        LOGGER.error(
            "Halpha schedule service failed.",
            extra={"event": "schedule.service.failed", "schedule_action": action, "reason": str(exc)},
        )
        print("Halpha schedule failed.")
        print("stage: schedule")
        print(f"reason: {schedule_service_error_message(str(exc), config_path=startup.config_path if startup else config_path)}")
        return exc.exit_code
    except KeyboardInterrupt:
        LOGGER.info("Halpha schedule service stopped.", extra={"event": "schedule.service.stopped"})
        print("Halpha schedule stopped.")
        return 0
    return 0


def _print_schedule_service_result(title: str, result: dict) -> None:
    print(title)
    print(f"status: {result.get('status')}")
    instance_id = result.get("instance_id")
    if isinstance(instance_id, str) and instance_id:
        print(f"instance_id: {instance_id}")
    pid = result.get("pid")
    if isinstance(pid, int):
        print(f"pid: {pid}")
    for warning in result.get("warnings") or []:
        print(f"warning: {warning}")


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
    result = run_strategy_backtest_action(
        config,
        config_path=config_path,
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        output_dir=Path(output_dir) if output_dir else None,
    )
    print(result.stdout, end="")
    if result.succeeded:
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
        reason="; ".join(result.errors) or result.status,
        status=result.status,
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        exit_code=result.exit_code,
    )
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
    result = run_strategy_experiment_action(
        config,
        config_path=config_path,
        strategy_names=strategy_names,
        output_dir=Path(output_dir) if output_dir else None,
    )
    print(result.stdout, end="")
    if result.exit_code == 0:
        _log_command_succeeded("experiment", status=result.status, strategy_count=len(strategy_names or []))
    else:
        _log_command_failed(
            "experiment",
            stage="experiment",
            reason="; ".join(result.errors) or result.status,
            status=result.status,
            strategy_count=len(strategy_names or []),
            exit_code=result.exit_code,
        )
    return result.exit_code


def _optimize(
    config_arg: str,
    *,
    strategy_name: str,
    grid_args: list[str],
    max_combinations: int,
    walk_forward_train_rows: int | None,
    walk_forward_validation_rows: int | None,
    walk_forward_step_rows: int | None,
    walk_forward_min_windows: int | None,
    output_dir: str | None,
) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    _log_command_start(
        "optimize",
        strategy_name=strategy_name,
        grid_overrides=len(grid_args),
        max_combinations=max_combinations,
        output_dir_requested=output_dir is not None,
    )
    walk_forward_policy = {
        key: value
        for key, value in {
            "train_rows": walk_forward_train_rows,
            "validation_rows": walk_forward_validation_rows,
            "step_rows": walk_forward_step_rows,
            "min_windows": walk_forward_min_windows,
        }.items()
        if value is not None
    } or None

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed("optimize", stage="config", reason=str(exc), exit_code=2)
        print("Halpha optimization failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    result = run_strategy_optimization_action(
        config,
        config_path=config_path,
        strategy_name=strategy_name,
        grid_args=grid_args,
        max_combinations=max_combinations,
        walk_forward_policy=walk_forward_policy,
        output_dir=Path(output_dir) if output_dir else None,
    )
    print(result.stdout, end="")
    if result.succeeded:
        _log_command_succeeded("optimize", status=result.status, strategy_name=strategy_name)
    else:
        _log_command_failed(
            "optimize",
            stage="optimization",
            reason="; ".join(result.errors) or result.status,
            status=result.status,
            strategy_name=strategy_name,
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


def _data_collect(
    config_arg: str,
    *,
    data_type: str,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
    requested_start: str,
    requested_end: str,
    apply: bool,
    max_exact_windows: int,
    merge_gap_threshold_seconds: int,
    min_fetch_window_seconds: int,
) -> int:
    config_path = Path(config_arg)
    command = "data collect"
    mode = "apply" if apply else "dry_run"
    _configure_logging(config_path=config_path)
    _log_command_start(command, mode=mode, data_type=data_type, source=source, symbol=symbol, timeframe=timeframe)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed(command, stage="config", reason=str(exc), exit_code=2)
        print("Halpha data collection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    if data_type == "ohlcv" and (not source or not symbol or not timeframe):
        reason = "data collect --data-type ohlcv requires --source, --symbol and --timeframe."
        _log_command_failed(command, stage="data_collect", reason=reason, exit_code=2)
        print("Halpha data collection failed.")
        print("stage: data_collect")
        print(f"reason: {reason}")
        return 2
    if data_type == "text_event" and not source:
        source = "all"

    try:
        result = collect_research_data(
            config,
            config_path=config_path,
            data_type=data_type,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            requested_start=requested_start,
            requested_end=requested_end,
            apply=apply,
            max_exact_windows=max_exact_windows,
            merge_gap_threshold_seconds=merge_gap_threshold_seconds,
            min_fetch_window_seconds=min_fetch_window_seconds,
            run_trigger=run_trigger_from_env(
                default_source="CLI",
                default_intent="data_collect",
            ),
        )
    except (OHLCVCollectionError, TextEventCollectionError) as exc:
        _log_command_failed(command, stage="data_collect", reason=str(exc), exit_code=exc.exit_code)
        print("Halpha data collection failed.")
        print("stage: data_collect")
        print(f"reason: {exc}")
        return exc.exit_code
    except (PipelineError, ValueError) as exc:
        exit_code = exc.exit_code if isinstance(exc, PipelineError) else 2
        _log_command_failed(command, stage="data_collect", reason=str(exc), exit_code=exit_code)
        print("Halpha data collection failed.")
        print("stage: data_collect")
        print(f"reason: {exc}")
        return exit_code

    _print_data_collection_result(result, config_path=config_path)
    exit_code = 3 if result.get("status") in {"failed", "blocked"} else 0
    if exit_code == 0:
        _log_command_succeeded(command, status=str(result.get("status") or "unknown"), mode=mode)
    else:
        _log_command_failed(
            command,
            stage="data_collect",
            reason=str(result.get("status") or "failed"),
            exit_code=exit_code,
            mode=mode,
        )
    return exit_code


def _print_data_collection_result(result: dict, *, config_path: Path) -> None:
    dry_run = result.get("mode") == "dry_run"
    if result.get("status") in {"failed", "blocked"}:
        title = "Halpha data collection failed."
    elif dry_run:
        title = "Halpha data collection dry run succeeded."
    else:
        title = "Halpha data collection apply succeeded."
    plan = result.get("plan") if isinstance(result.get("plan"), dict) else {}
    counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
    print(title)
    print(f"status: {result.get('status')}")
    print(f"mode: {result.get('mode')}")
    print(f"data_type: {result.get('data_type')}")
    print(f"source: {result.get('source')}")
    print(f"symbol: {result.get('symbol')}")
    print(f"timeframe: {result.get('timeframe')}")
    if isinstance(result.get("identity"), dict):
        print(f"identity: {result.get('identity')}")
    print(f"requested_start: {result.get('requested_start')}")
    print(f"requested_end: {result.get('requested_end')}")
    print(f"strategy: {plan.get('strategy')}")
    _print_counts(
        counts,
        keys=(
            "skipped_ranges",
            "gap_ranges",
            "retry_ranges",
            "planned_fetch_windows",
            "raw_items",
            "raw_errors",
            "fetched_records",
            "window_records",
            "stored_records",
            "coverage_records_written",
            "coverage_state_records",
        ),
    )
    for window in (plan.get("planned_fetch_windows") or [])[:10]:
        if isinstance(window, dict):
            print(
                "fetch_window: "
                f"{window.get('range_start')}..{window.get('range_end')} "
                f"reason={window.get('reason')}"
            )
    for fetch in (result.get("fetches") or [])[:10]:
        if isinstance(fetch, dict):
            print(
                "fetch_result: "
                f"{fetch.get('range_start')}..{fetch.get('range_end')} "
                f"status={fetch.get('status')} "
                f"records={fetch.get('window_record_count')} "
                f"stored={fetch.get('stored_count')}"
            )
    for key, value in sorted(display_collection_artifacts(result, config_path=config_path).items()):
        print(f"{key}: {value}")
    for warning in (result.get("warnings") or [])[:10]:
        print(f"warning: {warning}")
    for error in (result.get("errors") or [])[:10]:
        if isinstance(error, dict):
            print(f"error: {error.get('message')}")


def _data_export(
    config_arg: str,
    *,
    data_type: str,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
    identity_args: Sequence[str],
    requested_start: str,
    requested_end: str,
    as_of: str | None,
    output_format: str,
    output_path: str,
    limit: int | None,
    sort_order: str,
) -> int:
    config_path = Path(config_arg)
    command = "data export"
    _configure_logging(config_path=config_path)
    _log_command_start(
        command,
        data_type=data_type,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        format=output_format,
    )

    try:
        identity = _parse_identity_args(identity_args)
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed(command, stage="config", reason=str(exc), exit_code=2)
        print("Halpha data export failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2
    except ValueError as exc:
        _log_command_failed(command, stage="data_export", reason=str(exc), exit_code=2)
        print("Halpha data export failed.")
        print("stage: data_export")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = export_data(
            config,
            config_path=config_path,
            data_type=data_type,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            identity=identity,
            start=requested_start,
            end=requested_end,
            as_of=as_of,
            output_format=output_format,
            output_path=output_path,
            limit=limit,
            sort_order=sort_order,
        )
    except DataExportError as exc:
        _log_command_failed(command, stage="data_export", reason=str(exc), exit_code=exc.exit_code)
        print("Halpha data export failed.")
        print("stage: data_export")
        print(f"reason: {exc}")
        return exc.exit_code

    _print_data_export_result(result)
    _log_command_succeeded(command, status=str(result.get("status") or "unknown"))
    return 0


def _print_data_export_result(result: dict) -> None:
    print("Halpha data export succeeded.")
    print(f"status: {result.get('status')}")
    print(f"data_type: {result.get('data_type')}")
    print(f"format: {result.get('format')}")
    print(f"output: {result.get('output_path')}")
    print(f"metadata: {result.get('metadata_path') or 'embedded'}")
    print(f"record_count: {result.get('record_count')}")
    print(f"matched_record_count: {result.get('matched_record_count')}")
    print(f"truncated: {result.get('truncated')}")
    query_parameters = result.get("query_parameters") if isinstance(result.get("query_parameters"), dict) else {}
    print(f"requested_start: {query_parameters.get('start')}")
    print(f"requested_end: {query_parameters.get('end')}")
    print(f"as_of: {query_parameters.get('as_of')}")
    coverage = result.get("coverage_diagnostics") if isinstance(result.get("coverage_diagnostics"), dict) else {}
    print(f"coverage_status: {coverage.get('status')}")
    print(f"coverage_record_count: {coverage.get('record_count')}")
    for warning in (result.get("warnings") or [])[:10]:
        print(f"warning: {warning}")
    for error in (result.get("errors") or [])[:10]:
        if isinstance(error, dict):
            print(f"error: {error.get('message')}")


def _parse_identity_args(values: Sequence[str]) -> dict[str, str]:
    identity: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--identity must use KEY=VALUE.")
        key, raw = value.split("=", 1)
        key = key.strip()
        raw = raw.strip()
        if not key or raw == "":
            raise ValueError("--identity must use non-empty KEY=VALUE.")
        identity[key] = raw
    return identity


def _data_migrate_state(config_arg: str, *, apply: bool, replace_schedule: bool) -> int:
    config_path = Path(config_arg)
    command = "data migrate-state"
    mode = "apply" if apply else "dry_run"
    _configure_logging(config_path=config_path)
    _log_command_start(command, mode=mode, replace_schedule=replace_schedule)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed(command, stage="config", reason=str(exc), exit_code=2)
        print("Halpha legacy state migration failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        if apply:
            result = apply_legacy_state_migration(
                config,
                config_path=config_path,
                replace_schedule=replace_schedule,
            )
        else:
            result = legacy_state_migration_dry_run(
                config,
                config_path=config_path,
                replace_schedule=replace_schedule,
            )
    except Exception as exc:  # pragma: no cover - CLI boundary
        _log_command_failed(command, stage="legacy_state_migration", reason=type(exc).__name__, exit_code=1)
        print("Halpha legacy state migration failed.")
        print("stage: legacy_state_migration")
        print("reason: legacy state migration failed; inspect local logs.")
        return 1

    title = "Halpha legacy state migration apply succeeded." if apply else "Halpha legacy state migration dry run succeeded."
    _print_legacy_state_migration_result(title, result)
    exit_code = 1 if result.get("status") == "failed" else 0
    if exit_code == 0:
        _log_command_succeeded(command, status=str(result.get("status") or "unknown"), mode=mode)
    else:
        _log_command_failed(
            command,
            stage="legacy_state_migration",
            reason=str(result.get("status") or "failed"),
            exit_code=exit_code,
        )
    return exit_code


def _data_rebuild_index(config_arg: str) -> int:
    config_path = Path(config_arg)
    command = "data rebuild-index"
    _configure_logging(config_path=config_path)
    _log_command_start(command)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed(command, stage="config", reason=str(exc), exit_code=2)
        print("Halpha run index rebuild failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        result = rebuild_run_index_from_manifests(config, config_path=config_path)
    except Exception as exc:  # pragma: no cover - CLI boundary
        _log_command_failed(command, stage="run_index_rebuild", reason=type(exc).__name__, exit_code=1)
        print("Halpha run index rebuild failed.")
        print("stage: run_index_rebuild")
        print("reason: run index rebuild failed; inspect local logs.")
        return 1

    print("Halpha run index rebuild succeeded.")
    print(f"status: {result.get('status')}")
    print(f"run_index: {result.get('run_index')}")
    _print_counts(
        result.get("counts"),
        keys=("run_manifests", "rebuilt_runs", "diagnostics"),
    )
    for warning in (result.get("warnings") or [])[:10]:
        print(f"warning: {warning}")
    _log_command_succeeded(command, status=str(result.get("status") or "unknown"))
    return 0


def _data_cleanup_runs(
    config_arg: str,
    *,
    apply: bool,
    run_ids: list[str],
    include_report_archives: bool,
    confirm_report_deletion: str | None,
) -> int:
    config_path = Path(config_arg)
    command = "data cleanup-runs"
    mode = "apply" if apply else "dry_run"
    _configure_logging(config_path=config_path)
    _log_command_start(command, mode=mode, selected_runs=len(run_ids), include_report_archives=include_report_archives)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _log_command_failed(command, stage="config", reason=str(exc), exit_code=2)
        print("Halpha run archive cleanup failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    _configure_logging(config_path=config_path, config=config)
    try:
        if apply:
            result = apply_run_archive_cleanup(
                config,
                config_path=config_path,
                run_ids=run_ids,
                include_report_archives=include_report_archives,
                confirm_report_deletion=confirm_report_deletion,
            )
        else:
            result = plan_run_archive_cleanup(
                config,
                config_path=config_path,
                include_report_archives=include_report_archives,
                confirm_report_deletion=confirm_report_deletion,
            )
    except RunArchiveCleanupError as exc:
        _log_command_failed(command, stage="run_archive_cleanup", reason=str(exc), exit_code=exc.exit_code)
        print("Halpha run archive cleanup failed.")
        print("stage: run_archive_cleanup")
        print(f"reason: {exc}")
        return exc.exit_code
    except Exception as exc:  # pragma: no cover - CLI boundary
        _log_command_failed(command, stage="run_archive_cleanup", reason=type(exc).__name__, exit_code=1)
        print("Halpha run archive cleanup failed.")
        print("stage: run_archive_cleanup")
        print("reason: run archive cleanup failed; inspect local logs.")
        return 1

    title = "Halpha run archive cleanup apply succeeded." if apply else "Halpha run archive cleanup dry run succeeded."
    _print_run_archive_cleanup_result(title, result)
    exit_code = 1 if result.get("status") in {"blocked", "failed"} else 0
    if exit_code == 0:
        _log_command_succeeded(command, status=str(result.get("status") or "unknown"), mode=mode)
    else:
        _log_command_failed(
            command,
            stage="run_archive_cleanup",
            reason=str(result.get("status") or "failed"),
            exit_code=exit_code,
        )
    return exit_code


def _print_run_archive_cleanup_result(title: str, result: dict) -> None:
    print(title)
    print(f"status: {result.get('status')}")
    print(f"mode: {result.get('mode')}")
    print(f"run_root: {result.get('run_root')}")
    _print_counts(
        result.get("counts"),
        keys=(
            "candidates",
            "safe_to_delete",
            "report_bearing",
            "review_required",
            "diagnostics",
            "deletable",
            "approximate_deletable_size_bytes",
        ),
    )
    if result.get("mode") == "apply":
        for item in (result.get("deleted") or [])[:20]:
            if isinstance(item, dict):
                print(f"deleted: {item.get('run_id')} ref={item.get('run_dir')}")
        for item in (result.get("blocked") or [])[:20]:
            if isinstance(item, dict):
                print(f"blocked: {item.get('run_id')} reason={item.get('reason')}")
        index = result.get("index_rebuild")
        if isinstance(index, dict):
            print(f"run_index_rebuild: {index.get('status')}")
        for warning in (result.get("warnings") or [])[:10]:
            print(f"warning: {warning}")
        for error in (result.get("errors") or [])[:10]:
            print(f"error: {error}")
        return
    latest_refs = result.get("latest_index_refs")
    if isinstance(latest_refs, dict):
        for key, value in sorted(latest_refs.items()):
            if value:
                print(f"latest_index_ref: {key}={value}")
    for item in (result.get("candidates") or [])[:40]:
        if not isinstance(item, dict):
            continue
        trigger = item.get("trigger") if isinstance(item.get("trigger"), dict) else {}
        trigger_text = f"{trigger.get('source', 'unknown')}/{trigger.get('intent', 'unknown')}"
        latest = ",".join(item.get("latest_index_refs") or []) or "none"
        print(
            "candidate: "
            f"{item.get('run_id')} "
            f"category={item.get('category')} "
            f"deletable={str(bool(item.get('deletable'))).lower()} "
            f"run_kind={item.get('run_kind')} "
            f"disposal_class={item.get('disposal_class')} "
            f"trigger={trigger_text} "
            f"report={item.get('report', {}).get('status') if isinstance(item.get('report'), dict) else 'unknown'} "
            f"latest={latest} "
            f"size_bytes={item.get('size_bytes')} "
            f"reason={item.get('deletion_reason')}"
        )
    for item in (result.get("diagnostics") or [])[:40]:
        if isinstance(item, dict):
            print(f"diagnostic: {item.get('run_id', item.get('ref', 'unknown'))} reason={item.get('reason')}")
    for warning in (result.get("warnings") or [])[:10]:
        print(f"warning: {warning}")


def _print_legacy_state_migration_result(title: str, result: dict) -> None:
    print(title)
    print(f"status: {result.get('status')}")
    print(f"mode: {result.get('mode')}")
    print(f"runtime_state: {result.get('runtime_state')}")
    _print_counts(
        result.get("counts"),
        keys=(
            "discovered_files",
            "supported_sources",
            "supported_records",
            "importable_records",
            "imported_records",
            "duplicate_records",
            "diagnostic_records",
            "conflicts",
            "invalid_sources",
            "invalid_records",
            "cleanup_candidates",
            "backups_created",
        ),
    )
    for source in (result.get("sources") or [])[:20]:
        if not isinstance(source, dict) or not source.get("exists"):
            continue
        print(
            "source: "
            f"{source.get('source_type')} "
            f"status={source.get('status')} "
            f"records={source.get('record_count')} "
            f"importable={source.get('importable_records')} "
            f"ref={source.get('ref')}"
        )
    for conflict in (result.get("conflicts") or [])[:10]:
        print(f"conflict: {conflict}")
    for warning in (result.get("warnings") or [])[:10]:
        print(f"warning: {warning}")
    for error in (result.get("errors") or [])[:10]:
        print(f"error: {error}")


def _print_counts(counts: object, *, keys: tuple[str, ...]) -> None:
    if not isinstance(counts, dict):
        return
    for key in keys:
        if key in counts:
            print(f"{key}: {counts[key]}")


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
            try:
                result = run_monitor_loop(
                    config,
                    config_path=config_path,
                    max_cycles=max_cycles,
                    interval_seconds=interval_seconds or settings.interval_seconds,
                )
            except PipelineError as exc:
                LOGGER.warning(
                    "Halpha monitor loop failed.",
                    extra={
                        "event": "monitor.loop.failed",
                        "stage": exc.stage or "monitor",
                        "exit_code": exc.exit_code,
                        "reason": str(exc),
                    },
                )
                print("Halpha monitor run failed.")
                print(f"stage: {exc.stage or 'monitor'}")
                print(f"reason: {exc}")
                return exc.exit_code
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
        try:
            result = run_monitor_cycle(config, config_path=config_path)
        except PipelineError as exc:
            LOGGER.warning(
                "Halpha monitor cycle failed.",
                extra={
                    "event": "monitor.cycle.failed",
                    "stage": exc.stage or "monitor",
                    "exit_code": exc.exit_code,
                    "reason": str(exc),
                },
            )
            print("Halpha monitor run failed.")
            print(f"stage: {exc.stage or 'monitor'}")
            print(f"reason: {exc}")
            return exc.exit_code
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


def _monitor_service(
    config_arg: str,
    *,
    action: str,
    restart_from_instance_id: str | None = None,
) -> int:
    config_path = Path(config_arg)
    _configure_logging(config_path=config_path)
    LOGGER.info(
        "Halpha command started.",
        extra={"event": "cli.command.start", "command": "monitor", "monitor_action": action},
    )

    startup = None
    if action in {"start", "restart", "service"}:
        try:
            startup = load_monitor_startup_config(config_arg)
        except ConfigError as exc:
            LOGGER.warning(
                "Halpha command failed.",
                extra={"event": "cli.command.failed", "command": "monitor", "stage": "config", "reason": str(exc)},
            )
            print("Halpha monitor failed.")
            print("stage: config")
            print(f"reason: {monitor_service_error_message(str(exc), config_path=config_path)}")
            return 2
        _configure_logging(config_path=startup.config_path, config=startup.config)

    try:
        if action == "service":
            assert startup is not None
            LOGGER.info(
                "Halpha monitor service foreground starting.",
                extra={"event": "monitor.service.foreground.start"},
            )
            run_monitor_service(
                startup.config,
                config_path=startup.config_path,
                restart_from_instance_id=restart_from_instance_id,
            )
            LOGGER.info(
                "Halpha monitor service foreground stopped.",
                extra={"event": "monitor.service.foreground.stopped"},
            )
            return 0
        if action == "start":
            assert startup is not None
            result = start_monitor_service(config_arg)
            _print_monitor_service_result("Halpha monitor started.", result)
            return 0
        if action == "status":
            result = monitor_service_status(config_arg)
            _print_monitor_service_result("Halpha monitor status.", result)
            return 0
        if action == "stop":
            result = stop_monitor_service(config_arg)
            _print_monitor_service_result("Halpha monitor stop requested.", result)
            return 0
        if action == "restart":
            assert startup is not None
            result = restart_monitor_service(config_arg)
            _print_monitor_service_result("Halpha monitor restarted.", result)
            return 0
        raise MonitorServiceError(f"unsupported monitor action: {action}.")
    except MonitorServiceError as exc:
        LOGGER.error(
            "Halpha monitor service failed.",
            extra={"event": "monitor.service.failed", "monitor_action": action, "reason": str(exc)},
        )
        print("Halpha monitor failed.")
        print("stage: monitor")
        print(f"reason: {monitor_service_error_message(str(exc), config_path=startup.config_path if startup else config_path)}")
        return exc.exit_code
    except KeyboardInterrupt:
        LOGGER.info("Halpha monitor service stopped.", extra={"event": "monitor.service.stopped"})
        print("Halpha monitor stopped.")
        return 0
    return 0


def _print_monitor_service_result(title: str, result: dict) -> None:
    print(title)
    print(f"status: {result.get('status')}")
    instance_id = result.get("instance_id")
    if isinstance(instance_id, str) and instance_id:
        print(f"instance_id: {instance_id}")
    pid = result.get("pid")
    if isinstance(pid, int):
        print(f"pid: {pid}")
    for warning in result.get("warnings") or []:
        print(f"warning: {warning}")


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


def _non_negative_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed
