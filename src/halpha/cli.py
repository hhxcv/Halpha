from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import ConfigError, load_config
from .data_inspection import DataInspectionError, inspect_local_data
from .monitoring import (
    inspect_monitor_health,
    load_monitor_config,
    monitor_config_lines,
    run_monitor_cycle,
    run_monitor_loop,
)
from .outcome_inspection import OutcomeInspectionError, inspect_local_outcomes
from .pipeline import PipelineError, StageSelectionError, run_pipeline, run_pipeline_stage
from .standalone_backtest import StandaloneBacktestError, run_standalone_strategy_backtest
from .standalone_text_intelligence import run_standalone_text_intelligence
from .storage import display_path
from .strategy_experiment import StrategyExperimentError, run_strategy_experiment
from .text_models import prepare_text_models
from .workbench import build_workbench_summary, inspect_workbench_summary


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

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha run failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    try:
        result = run_pipeline(
            config,
            config_path=config_path,
            until_stage=until_stage,
            skip_codex=no_codex,
        )
    except StageSelectionError as exc:
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
        return 0

    print("Halpha run failed.")
    print(f"stage: {result.failed_stage}")
    print(f"reason: {result.reason}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _stage(stage_name: str, config_arg: str, run_dir_arg: str) -> int:
    config_path = Path(config_arg)
    run_dir = Path(run_dir_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha stage failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    try:
        result = run_pipeline_stage(
            config,
            config_path=config_path,
            run_dir=run_dir,
            stage=stage_name,
        )
    except StageSelectionError as exc:
        print("Halpha stage failed.")
        print("stage: cli")
        print(f"reason: {exc}")
        return 2
    except PipelineError as exc:
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
        return 0

    print("Halpha stage failed.")
    print(f"stage: {result.failed_stage}")
    print(f"reason: {result.reason}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _backtest(
    config_arg: str,
    *,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    output_dir: str | None,
) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha backtest failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

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
        return 0

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

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha experiment failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    try:
        result = run_strategy_experiment(
            config,
            config_path=config_path,
            strategy_names=strategy_names,
            output_dir=Path(output_dir) if output_dir else None,
        )
    except StrategyExperimentError as exc:
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
    return result.exit_code


def _text_models_prepare(config_arg: str, *, output_dir: str | None) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha text model preparation failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

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
        return 0

    print("Halpha text model preparation failed.")
    print(f"status: {result.status}")
    if result.manifest.get("errors"):
        print(f"reason: {result.manifest['errors'][0]}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _text_intel(config_arg: str, *, input_path: str | None, output_dir: str | None) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha text intelligence failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

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
        return 0

    print("Halpha text intelligence failed.")
    print(f"status: {result.status}")
    if result.reason:
        print(f"reason: {result.reason}")
    print(f"output_dir: {output}")
    print(f"manifest: {manifest}")
    return result.exit_code


def _data_inspect(config_arg: str, *, run_dir: str | None) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha data inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    try:
        result = inspect_local_data(
            config,
            config_path=config_path,
            run_dir=Path(run_dir) if run_dir else None,
        )
    except DataInspectionError as exc:
        print("Halpha data inspection failed.")
        print("stage: data_inspect")
        print(f"reason: {exc}")
        return exc.exit_code

    for line in result.lines:
        print(line)
    return 0


def _outcomes_inspect(config_arg: str, *, run_dir: str | None) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha outcome inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    try:
        result = inspect_local_outcomes(
            config,
            config_path=config_path,
            run_dir=Path(run_dir) if run_dir else None,
        )
    except OutcomeInspectionError as exc:
        print("Halpha outcome inspection failed.")
        print("stage: outcomes_inspect")
        print(f"reason: {exc}")
        return exc.exit_code

    for line in result.lines:
        print(line)
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

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha monitor run failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    if not dry_run:
        if interval_seconds is not None and max_cycles is None:
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
            return result.exit_code
        if not once:
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
            return result.exit_code

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
    return 0


def _monitor_inspect(config_arg: str) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha monitor inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    result = inspect_monitor_health(config, config_path=config_path)
    for line in result.lines:
        print(line)
    return result.exit_code


def _workbench_build(config_arg: str, *, run_dir: str | None) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha workbench build failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

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
    print("codex: not_run")
    return 0


def _workbench_inspect(config_arg: str) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha workbench inspection failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    result = inspect_workbench_summary(config, config_path=config_path)
    for line in result.lines:
        print(line)
    return result.exit_code


def _safe_local_display_path(path: Path) -> str:
    try:
        path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path.name
    return display_path(path)


def _positive_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed
