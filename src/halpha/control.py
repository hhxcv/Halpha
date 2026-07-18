"""One-shot maintenance commands for the two scheduled processes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from halpha.configuration import ConfigurationError, load_settings
from halpha.runtime_identity import RuntimeIdentityError, require_repository_runtime
from halpha.windows_runtime import WindowsRuntimeError, signal_stop_event


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="halpha-control")
    subparsers = parser.add_subparsers(dest="command", required=True)
    stop = subparsers.add_parser("stop")
    stop.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require_repository_runtime()
        settings = load_settings(args.config)
        windows = settings.windows
        results: dict[str, str] = {}
        failures = False
        for role, name, sid in (
            ("app", windows.app_stop_event, windows.app_task_sid),
            ("executor", windows.executor_stop_event, windows.executor_task_sid),
        ):
            try:
                signal_stop_event(
                    name=name,
                    task_sid=sid,
                    maintenance_sid=windows.maintenance_sid,
                )
                results[role] = "SIGNALED"
            except WindowsRuntimeError as exc:
                results[role] = str(exc)
                failures = True
    except (ConfigurationError, RuntimeIdentityError, WindowsRuntimeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "PARTIAL" if failures else "STOP_SIGNALED",
                "results": results,
            },
            sort_keys=True,
        )
    )
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
