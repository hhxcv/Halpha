"""Shared CLI mechanics without shared process capabilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from halpha.configuration import ConfigurationError, load_settings
from halpha.process_contract import ProcessRole, preflight
from halpha.runtime_identity import RuntimeIdentityError


def run_preflight_entrypoint(role: ProcessRole, argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=role.value)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate the selected runtime and process boundary without starting product services",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="explicit path to the non-secret TOML runtime configuration",
    )
    args = parser.parse_args(argv)
    if not args.preflight_only:
        parser.error("B01 skeleton currently supports only --preflight-only")

    try:
        settings = load_settings(args.config)
        report = preflight(role, settings)
    except (ConfigurationError, RuntimeIdentityError) as exc:
        print(json.dumps({"status": "PREFLIGHT_REJECTED", "reason": str(exc)}, sort_keys=True))
        return 2

    print(json.dumps(report, sort_keys=True))
    return 0
