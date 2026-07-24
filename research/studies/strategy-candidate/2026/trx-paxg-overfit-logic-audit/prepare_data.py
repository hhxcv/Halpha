"""Fetch checksum-verified BTC/ETH spot data for the TRX/PAXG audit."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


STUDY_DIR = Path(__file__).resolve().parent
BASE_PATH = (
    STUDY_DIR.parent.parent.parent
    / "legacy"
    / "2026"
    / "mature-alt-spot-top2-momentum"
    / "study.py"
)
SYMBOLS = ("BTCUSDT", "ETHUSDT")


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_spot_audit_data", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("SPOT_DATA_BASE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.SYMBOLS = SYMBOLS
    return module


BASE = _load_base()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--start-month", default="2020-01")
    parser.add_argument("--end-month", default="2026-06")
    args = parser.parse_args()
    BASE.command_fetch(args)


if __name__ == "__main__":
    main()
