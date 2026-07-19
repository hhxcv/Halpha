#!/usr/bin/env python3
"""Validate small, repository-wide safety invariants in the Halpha L4 plan.

The validator deliberately does not encode one change's workflow, package order,
component versions, parameters, time gates, or evidence model. Product semantics
remain in the current design documents; this check only guards schema identity and a
few fail-closed runtime facts.
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
DEFAULT_PLAN = (
    REPOSITORY_ROOT / "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml"
)
RUNTIME_STATES = {"CLOSED", "OPEN"}


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


class PlanLoadError(RuntimeError):
    """Raised when the L4 file cannot be loaded as a YAML mapping."""


def _normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace("-", "_").replace(" ", "_")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _runtime_views(plan: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    views: list[tuple[str, Mapping[str, Any]]] = []
    current_facts = _mapping(plan.get("current_facts"))
    if isinstance(current_facts.get("runtime"), Mapping):
        views.append(("current_facts.runtime", _mapping(current_facts.get("runtime"))))
    if isinstance(plan.get("live_safety"), Mapping):
        views.append(("live_safety", _mapping(plan.get("live_safety"))))
    return views


def _runtime_state(view: Mapping[str, Any]) -> str:
    return _normalize(view.get("real_write_state"))


def _credentials_loaded(view: Mapping[str, Any]) -> bool:
    return view.get("live_credentials_loaded") is True


def _validate_runtime(
    plan: Mapping[str, Any],
    *,
    violations: list[Violation],
) -> None:
    states: list[tuple[str, str, Mapping[str, Any]]] = []
    for path, view in _runtime_views(plan):
        state = _runtime_state(view)
        if not state:
            continue
        states.append((path, state, view))
        if state not in RUNTIME_STATES:
            violations.append(
                Violation(
                    "GOV-RUNTIME-001",
                    path,
                    f"real-write state must be one of {sorted(RUNTIME_STATES)}",
                )
            )
        if state == "CLOSED" and _credentials_loaded(view):
            violations.append(
                Violation(
                    "GOV-RUNTIME-003",
                    path,
                    "live credentials cannot be loaded while real write is closed",
                )
            )
        if state == "CLOSED" and view.get("live_execution_actions_created") is True:
            violations.append(
                Violation(
                    "GOV-RUNTIME-005",
                    f"{path}.live_execution_actions_created",
                    "live execution actions cannot be recorded while real write is closed",
                )
            )
        if state == "CLOSED" and view.get("venue_live_writes_observed") is True:
            violations.append(
                Violation(
                    "GOV-RUNTIME-006",
                    f"{path}.venue_live_writes_observed",
                    "venue live writes cannot be recorded while real write is closed",
                )
            )

    declared = {state for _, state, _ in states if state in RUNTIME_STATES}
    if len(declared) > 1:
        violations.append(
            Violation(
                "GOV-RUNTIME-004",
                "runtime state",
                "all declared real-write state projections must agree",
            )
        )

    if "OPEN" not in declared:
        return

    live_safety = _mapping(plan.get("live_safety"))
    product_build = _mapping(plan.get("product_build"))
    prerequisites = {
        "product build identity": product_build.get("current_product_build_id"),
        "current activation identity": live_safety.get("current_activation_id"),
    }
    for label, value in prerequisites.items():
        if not isinstance(value, str) or not value.strip():
            violations.append(
                Violation(
                    "GOV-RUNTIME-OPEN-001",
                    label,
                    "must be bound before real write can be open",
                )
            )

    for field in ("database_current", "unique_writer_confirmed", "facts_current"):
        if live_safety.get(field) is not True:
            violations.append(
                Violation(
                    "GOV-RUNTIME-OPEN-002",
                    f"live_safety.{field}",
                    "must be true before real write can be open",
                )
            )


def validate_plan(plan: Mapping[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    expected = {
        "schema_version": 3,
        "document_id": "HALPHA-PLAN-001",
        "level": "L4",
    }
    for field, value in expected.items():
        if plan.get(field) != value:
            violations.append(
                Violation(
                    "GOV-SCHEMA-001",
                    field,
                    f"must be {value!r}",
                )
            )

    _validate_runtime(plan, violations=violations)
    return violations


def load_plan(path: Path) -> Mapping[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PlanLoadError(f"cannot load {path}: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise PlanLoadError(f"{path} must contain a YAML mapping")
    return loaded


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT_PLAN)
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
        print(f"Current plan safety: {len(violations)} violation(s).", file=sys.stderr)
        return 1
    print("Current plan safety: 0 violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
