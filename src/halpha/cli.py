from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import ConfigError, load_config
from .pipeline import run_pipeline
from .storage import display_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="halpha")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Start an M0 report run.")
    run_parser.add_argument("--config", required=True, help="Path to a Halpha YAML config file.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(args.config)

    parser.error(f"unknown command: {args.command}")
    return 1


def _run(config_arg: str) -> int:
    config_path = Path(config_arg)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print("Halpha run failed.")
        print("stage: config")
        print(f"reason: {exc}")
        return 2

    result = run_pipeline(config, config_path=config_path)
    manifest = display_path(result.run.manifest_path)

    if result.succeeded:
        report_artifact = result.run.manifest.get("artifacts", {}).get("report", "report/report.md")
        report = display_path(result.run.run_dir / report_artifact)
        print("Halpha run succeeded.")
        print(f"run_id: {result.run.run_id}")
        print(f"report: {report}")
        print(f"manifest: {manifest}")
        return 0

    print("Halpha run failed.")
    print(f"stage: {result.failed_stage}")
    print(f"reason: {result.reason}")
    print(f"manifest: {manifest}")
    return result.exit_code
