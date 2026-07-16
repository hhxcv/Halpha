from __future__ import annotations

import json
import platform
import sys
from pathlib import Path


EXPECTED_VERSION = (3, 13, 14)


def collect_environment() -> tuple[dict[str, object], list[str]]:
    repository_root = Path(__file__).resolve().parents[2]
    expected_prefix = (repository_root / ".venv").resolve()
    actual_prefix = Path(sys.prefix).resolve()
    executable = Path(sys.executable).resolve()

    evidence: dict[str, object] = {
        "python_version": platform.python_version(),
        "architecture": platform.architecture()[0],
        "executable": str(executable),
        "venv_prefix": str(actual_prefix),
        "base_prefix": str(Path(sys.base_prefix).resolve()),
        "expected_venv_prefix": str(expected_prefix),
        "is_venv": sys.prefix != sys.base_prefix,
    }

    errors: list[str] = []
    if sys.version_info[:3] != EXPECTED_VERSION:
        errors.append("PYTHON_VERSION_MISMATCH")
    if platform.architecture()[0] != "64bit":
        errors.append("PYTHON_ARCHITECTURE_MISMATCH")
    if sys.prefix == sys.base_prefix:
        errors.append("VENV_REQUIRED")
    if actual_prefix != expected_prefix:
        errors.append("VENV_LOCATION_MISMATCH")
    if executable.parent != expected_prefix / "Scripts":
        errors.append("VENV_EXECUTABLE_MISMATCH")

    return evidence, errors


def main() -> int:
    evidence, errors = collect_environment()
    evidence["status"] = "QUALIFIED" if not errors else "REJECTED"
    evidence["errors"] = errors
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
