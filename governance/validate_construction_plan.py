"""Validate fail-closed construction gates in the current Halpha L4 plan.

This check deliberately validates only machine-readable current-state consistency.
It does not decide whether an upstream design conflict is semantically resolved and
does not advance any construction or real-write state.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = REPOSITORY_ROOT / "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml"

ALIGNED_STATES = {"ALIGNED", "FULLY_ALIGNED", "ALIGNED_UPSTREAM"}
RESOLVED_CONFLICT_STATES = {
    "ACCEPTED_ALIGNMENT",
    "CLOSED",
    "RESOLVED",
    "SUPERSEDED",
}
NOT_STARTED_PACKAGE_STATES = {"", "BLOCKED", "DEFERRED", "NOT_STARTED", "PLANNED"}
PACKAGE_COMPLETE_STATES = {"COMPLETE", "COMPLETED"}


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


class PlanLoadError(RuntimeError):
    """Raised when the current plan cannot be read as a YAML mapping."""


def _normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _mapping(
    value: object,
    path: str,
    violations: list[Violation],
) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    violations.append(Violation("GOV-SCHEMA-001", path, "must be a mapping"))
    return {}


def _is_blocked(value: object) -> bool:
    return _normalize(value).startswith("BLOCKED")


def _is_started_or_later(value: object) -> bool:
    return _normalize(value) not in NOT_STARTED_PACKAGE_STATES


def _is_complete(value: object) -> bool:
    return _normalize(value) in PACKAGE_COMPLETE_STATES


def _has_unresolved_upstream_conflicts(formalization: Mapping[str, Any]) -> bool:
    record_status = _normalize(formalization.get("status"))
    if record_status.startswith("BLOCKED") or "UNRESOLVED" in record_status:
        return True
    if "RECORDED_UPSTREAM_CONFLICT" in record_status:
        return True

    alignment = _normalize(formalization.get("alignment"))
    if alignment not in ALIGNED_STATES:
        return True

    conflicts = formalization.get("conflicts", [])
    if not isinstance(conflicts, Sequence) or isinstance(conflicts, (str, bytes)):
        return True

    for conflict in conflicts:
        if not isinstance(conflict, Mapping):
            return True
        resolution = _normalize(
            conflict.get("resolution_status", conflict.get("status"))
        )
        if resolution not in RESOLVED_CONFLICT_STATES:
            return True
    return False


def validate_plan(plan: Mapping[str, Any]) -> list[Violation]:
    """Return every construction-governance violation found in *plan*."""

    violations: list[Violation] = []
    current_state = _mapping(plan.get("current_state"), "current_state", violations)
    formalization = _mapping(
        plan.get("formalization_record"), "formalization_record", violations
    )
    d00 = _mapping(
        plan.get("design_formalization_gate"),
        "design_formalization_gate",
        violations,
    )
    b00 = _mapping(
        plan.get("dependency_qualification_gate"),
        "dependency_qualification_gate",
        violations,
    )
    packages = _mapping(
        plan.get("construction_packages"), "construction_packages", violations
    )
    readiness = _mapping(
        plan.get("definition_of_ready_to_start_p0"),
        "definition_of_ready_to_start_p0",
        violations,
    )

    package_records: dict[str, Mapping[str, Any]] = {}
    for package_id in ("B01", "B02", "B03", "B04", "B05"):
        package_records[package_id] = _mapping(
            packages.get(package_id),
            f"construction_packages.{package_id}",
            violations,
        )

    unresolved = _has_unresolved_upstream_conflicts(formalization)
    if unresolved:
        blocked_fields = (
            (
                "formalization_record.status",
                formalization.get("status"),
            ),
            (
                "current_state.design_status",
                current_state.get("design_status"),
            ),
            (
                "design_formalization_gate.status",
                d00.get("status"),
            ),
            (
                "definition_of_ready_to_start_p0.design_status",
                readiness.get("design_status"),
            ),
        )
        for path, value in blocked_fields:
            if not _is_blocked(value):
                violations.append(
                    Violation(
                        "GOV-CONFLICT-001",
                        path,
                        "must be BLOCKED while upstream conflicts remain unresolved",
                    )
                )

        for package_id, record in package_records.items():
            if not _is_blocked(record.get("eligibility")):
                violations.append(
                    Violation(
                        "GOV-CONFLICT-002",
                        f"construction_packages.{package_id}.eligibility",
                        "must be BLOCKED while upstream conflicts remain unresolved; "
                        "only isolated B00 qualification may continue",
                    )
                )

        if _normalize(current_state.get("real_write_status")) != "DISABLED":
            violations.append(
                Violation(
                    "GOV-CONFLICT-003",
                    "current_state.real_write_status",
                    "must be DISABLED while upstream conflicts remain unresolved",
                )
            )

    b01_dependencies = package_records["B01"].get("depends_on")
    if not isinstance(b01_dependencies, Sequence) or isinstance(
        b01_dependencies, (str, bytes)
    ):
        violations.append(
            Violation(
                "GOV-DEPENDENCY-001",
                "construction_packages.B01.depends_on",
                "must be a list containing D00=ALIGNED and B00=QUALIFIED",
            )
        )
        normalized_dependencies: set[str] = set()
    else:
        normalized_dependencies = {_normalize(item) for item in b01_dependencies}

    for required_dependency in ("D00=ALIGNED", "B00=QUALIFIED"):
        if required_dependency not in normalized_dependencies:
            violations.append(
                Violation(
                    "GOV-DEPENDENCY-002",
                    "construction_packages.B01.depends_on",
                    f"missing required dependency {required_dependency}",
                )
            )

    expected_package_dependencies = {
        "B02": "B01",
        "B03": "B02",
        "B04": "B03",
        "B05": "B04",
    }
    for package_id, expected_dependency in expected_package_dependencies.items():
        dependencies = package_records[package_id].get("depends_on")
        if not isinstance(dependencies, Sequence) or isinstance(
            dependencies, (str, bytes)
        ):
            normalized_package_dependencies: set[str] = set()
        else:
            normalized_package_dependencies = {_normalize(item) for item in dependencies}
        if expected_dependency not in normalized_package_dependencies:
            violations.append(
                Violation(
                    "GOV-DEPENDENCY-003",
                    f"construction_packages.{package_id}.depends_on",
                    f"missing required dependency {expected_dependency}",
                )
            )

    b00_status = _normalize(b00.get("status"))
    d00_aligned = _normalize(d00.get("status")) in ALIGNED_STATES
    if not d00_aligned:
        for package_id, record in package_records.items():
            if _is_started_or_later(record.get("status")):
                violations.append(
                    Violation(
                        "GOV-SEQUENCE-002",
                        f"construction_packages.{package_id}.status",
                        "cannot advance until D00 is ALIGNED",
                    )
                )

    if b00_status != "QUALIFIED":
        for package_id, record in package_records.items():
            if _is_started_or_later(record.get("status")):
                violations.append(
                    Violation(
                        "GOV-SEQUENCE-001",
                        f"construction_packages.{package_id}.status",
                        f"cannot advance while B00 is {b00_status or 'UNKNOWN'}",
                    )
                )

    for package_id, record in package_records.items():
        if _is_started_or_later(record.get("status")):
            eligibility = _normalize(record.get("eligibility"))
            if not eligibility or _is_blocked(eligibility):
                violations.append(
                    Violation(
                        "GOV-SEQUENCE-003",
                        f"construction_packages.{package_id}",
                        "cannot advance without explicit non-BLOCKED eligibility",
                    )
                )

    b00_to_b04_complete = (
        not unresolved
        and d00_aligned
        and b00_status == "QUALIFIED"
        and all(
            _is_complete(package_records[package_id].get("status"))
            for package_id in ("B01", "B02", "B03", "B04")
        )
    )
    if (
        not b00_to_b04_complete
        and _normalize(current_state.get("real_write_status")) != "DISABLED"
    ):
        violations.append(
            Violation(
                "GOV-REAL-WRITE-001",
                "current_state.real_write_status",
                "must be DISABLED until B00 is QUALIFIED and B01-B04 are complete",
            )
        )

    return violations


def load_plan(path: Path) -> Mapping[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PlanLoadError(f"cannot read {path}: {exc}") from exc

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PlanLoadError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(loaded, Mapping):
        raise PlanLoadError(f"{path} must contain a YAML mapping")
    return loaded


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "plan",
        nargs="?",
        type=Path,
        default=DEFAULT_PLAN,
        help="current construction plan (defaults to the repository L4 plan)",
    )
    args = parser.parse_args(argv)

    try:
        plan = load_plan(args.plan)
    except PlanLoadError as exc:
        print(f"[ERROR] GOV-LOAD-001 {exc}", file=sys.stderr)
        return 2

    violations = validate_plan(plan)
    for violation in violations:
        print(
            f"[ERROR] {violation.code} {violation.path}: {violation.message}",
            file=sys.stderr,
        )
    if violations:
        print(f"Construction governance: {len(violations)} violation(s).", file=sys.stderr)
        return 1

    print("Construction governance: 0 violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
