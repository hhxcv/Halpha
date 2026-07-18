"""Verify the minimal critical-invariant trace registry and detect evidence drift."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qualification.source_binding import (  # noqa: E402
    SourceBindingError,
    capture_source_sha256,
)


DEFAULT_REGISTRY = ROOT / "config/critical-invariant-trace.registry.json"
DEFAULT_OUTPUT = ROOT / "build/qualification/b02-critical-invariant-trace.json"
REQUIRED_FIELDS = frozenset(
    {
        "requirement_id",
        "spec_source",
        "delivery_horizon",
        "implementation_paths",
        "forbidden_calls",
        "tests",
        "build_gate",
        "evidence_digest",
        "implementation_status",
        "deviation_status",
    }
)
DELIVERY_HORIZONS = frozenset({"P0_REQUIRED", "LONG_TERM_REQUIRED_P0_DEFERRED"})
IMPLEMENTATION_STATUSES = frozenset(
    {"NOT_STARTED", "PARTIAL", "IMPLEMENTED", "DEFERRED"}
)
DEVIATION_STATUSES = frozenset({"NONE", "OPEN", "ACCEPTED"})
BASELINE_PATTERNS = (
    "pyproject.toml",
    "requirements/*.txt",
    "migrations/versions/*.py",
    "config/halpha.example.toml",
    "tools/qualification/verify_critical_invariant_trace.py",
    "tests/qualification/test_critical_invariant_trace.py",
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_pattern(value: str) -> str:
    pattern = value.split("#", 1)[0]
    path = PurePosixPath(pattern)
    if not pattern or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"UNSAFE_TRACE_PATH:{value}")
    return pattern


def _expand_files(root: Path, patterns: Iterable[str]) -> tuple[Path, ...]:
    files: set[Path] = set()
    for raw_pattern in patterns:
        pattern = _safe_pattern(raw_pattern)
        matches = tuple(root.glob(pattern))
        if not matches:
            raise ValueError(f"TRACE_PATH_NOT_FOUND:{raw_pattern}")
        for match in matches:
            resolved = match.resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                raise ValueError(f"TRACE_PATH_OUTSIDE_REPOSITORY:{raw_pattern}") from None
            if resolved.is_file():
                files.add(resolved)
    return tuple(sorted(files, key=lambda item: item.as_posix()))


def compute_record_digest(
    record: dict[str, Any],
    *,
    root: Path = ROOT,
    baseline_patterns: Iterable[str] = BASELINE_PATTERNS,
) -> str:
    references = (
        list(record.get("spec_source", []))
        + list(record.get("implementation_paths", []))
        + list(record.get("tests", []))
        + list(baseline_patterns)
    )
    files = _expand_files(root, references)
    file_digests = {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    record_basis = {
        key: value for key, value in record.items() if key != "evidence_digest"
    }
    return "sha256:" + sha256(
        _canonical({"record": record_basis, "files": file_digests})
    ).hexdigest()


def validate_registry(
    registry: dict[str, Any],
    *,
    root: Path = ROOT,
    baseline_patterns: Iterable[str] = BASELINE_PATTERNS,
) -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    actual_digests: dict[str, str] = {}
    if set(registry) != {"records"} or not isinstance(registry.get("records"), list):
        return ["REGISTRY_SHAPE_INVALID"], actual_digests
    seen: set[str] = set()
    horizons: set[str] = set()
    for index, raw_record in enumerate(registry["records"]):
        if not isinstance(raw_record, dict):
            errors.append(f"RECORD_NOT_OBJECT:{index}")
            continue
        record = raw_record
        requirement_id = str(record.get("requirement_id", f"index-{index}"))
        if set(record) != REQUIRED_FIELDS:
            errors.append(f"RECORD_FIELDS_INVALID:{requirement_id}")
            continue
        if requirement_id in seen:
            errors.append(f"REQUIREMENT_ID_DUPLICATED:{requirement_id}")
        seen.add(requirement_id)
        horizon = record["delivery_horizon"]
        horizons.add(horizon)
        if horizon not in DELIVERY_HORIZONS:
            errors.append(f"DELIVERY_HORIZON_INVALID:{requirement_id}")
        if record["implementation_status"] not in IMPLEMENTATION_STATUSES:
            errors.append(f"IMPLEMENTATION_STATUS_INVALID:{requirement_id}")
        if record["deviation_status"] not in DEVIATION_STATUSES:
            errors.append(f"DEVIATION_STATUS_INVALID:{requirement_id}")
        for field in (
            "spec_source",
            "implementation_paths",
            "forbidden_calls",
            "tests",
            "build_gate",
        ):
            values = record[field]
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                errors.append(f"RECORD_LIST_INVALID:{requirement_id}:{field}")
        if not record["spec_source"] or not record["forbidden_calls"] or not record["build_gate"]:
            errors.append(f"RECORD_REQUIRED_LIST_EMPTY:{requirement_id}")
        if (
            horizon == "LONG_TERM_REQUIRED_P0_DEFERRED"
            and record["implementation_status"] != "DEFERRED"
        ):
            errors.append(f"DEFERRED_STATUS_MISMATCH:{requirement_id}")
        try:
            actual = compute_record_digest(
                record,
                root=root,
                baseline_patterns=baseline_patterns,
            )
        except (OSError, ValueError) as exc:
            errors.append(f"DIGEST_INPUT_INVALID:{requirement_id}:{exc}")
            continue
        actual_digests[requirement_id] = actual
        if record["evidence_digest"] != actual:
            errors.append(f"EVIDENCE_DRIFT:{requirement_id}")
    if horizons != DELIVERY_HORIZONS:
        errors.append("DELIVERY_HORIZON_COVERAGE_INCOMPLETE")
    return errors, actual_digests


def registry_source_patterns(
    registry: dict[str, Any],
    *,
    registry_path: Path,
) -> tuple[str, ...]:
    patterns = {
        *BASELINE_PATTERNS,
        registry_path.resolve().relative_to(ROOT).as_posix(),
        "tools/qualification/source_binding.py",
        "src/halpha/source_identity.py",
    }
    for record in registry.get("records", []):
        if not isinstance(record, dict):
            continue
        for field in ("spec_source", "implementation_paths", "tests"):
            values = record.get(field, [])
            if isinstance(values, list):
                patterns.update(
                    value.split("#", 1)[0]
                    for value in values
                    if isinstance(value, str) and value
                )
    return tuple(sorted(patterns))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    source_patterns = registry_source_patterns(
        registry,
        registry_path=args.registry,
    )
    source_sha256_at_start = capture_source_sha256(ROOT, source_patterns)
    errors, actual_digests = validate_registry(registry)
    try:
        source_stable = (
            capture_source_sha256(ROOT, source_patterns) == source_sha256_at_start
        )
    except SourceBindingError as exc:
        source_stable = False
        errors.append(f"SOURCE_BINDING_FAILED:{exc}")
    report: dict[str, Any] = {
        "stage": "B02_CRITICAL_INVARIANT_TRACE",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "registry": args.registry.resolve().relative_to(ROOT).as_posix(),
        "record_count": len(registry.get("records", [])),
        "actual_digests": actual_digests,
        "checks": {
            "registry_valid": not errors,
            "source_stable_during_qualification": source_stable,
        },
        "source_sha256": source_sha256_at_start,
        "errors": errors,
        "status": "QUALIFIED" if not errors and source_stable else "REJECTED",
    }
    report["evidence_digest"] = sha256(_canonical(report)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
