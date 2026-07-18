from __future__ import annotations

import argparse
from pathlib import Path

from halpha.planning.registry import render_strategy_registry


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "src" / "halpha" / "planning" / "strategy_registry.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    rendered = render_strategy_registry()
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("STRATEGY_REGISTRY_DRIFT")
        print("STRATEGY_REGISTRY_VERIFIED")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"STRATEGY_REGISTRY_WRITTEN path={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
