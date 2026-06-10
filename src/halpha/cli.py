from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import ConfigError, load_config
from .pipeline import PipelineError, StageSelectionError, run_pipeline, run_pipeline_stage
from .standalone_backtest import StandaloneBacktestError, run_standalone_strategy_backtest
from .storage import display_path


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
