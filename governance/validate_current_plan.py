#!/usr/bin/env python3
"""Validate the small set of fail-safe facts in the Halpha current plan.

Product semantics remain in the current design documents. This check guards only
the plan identity and the directly actionable real-account trading facts.
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
DEFAULT_PLAN = REPOSITORY_ROOT / "docs/L4/HALPHA-PLAN-001-current-plan.yaml"


@dataclass(frozen=True)
class Violation:
    code: str
    path: str
    message: str


class PlanLoadError(RuntimeError):
    """Raised when the L4 file cannot be loaded as a YAML mapping."""


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_real_account_trading(
    plan: Mapping[str, Any], *, violations: list[Violation]
) -> None:
    path = "real_account_trading"
    facts = _mapping(plan.get(path))
    allowed = facts.get("exchange_change_requests_allowed")
    if not isinstance(allowed, bool):
        violations.append(
            Violation(
                "GOV-REAL-001",
                f"{path}.exchange_change_requests_allowed",
                "must be true or false",
            )
        )
        return

    if not allowed:
        forbidden_true = (
            "credentials_loaded",
            "execution_actions_created",
            "exchange_changes_observed",
        )
        for field in forbidden_true:
            if facts.get(field) is True:
                violations.append(
                    Violation(
                        "GOV-REAL-002",
                        f"{path}.{field}",
                        "must be false when exchange-changing requests are not allowed",
                    )
                )
        return

    product_build = _mapping(plan.get("product_build"))
    required_identities = {
        "product_build.current_product_build_id": product_build.get(
            "current_product_build_id"
        ),
        f"{path}.current_activation_id": facts.get("current_activation_id"),
    }
    for field, value in required_identities.items():
        if not isinstance(value, str) or not value.strip():
            violations.append(
                Violation(
                    "GOV-REAL-003",
                    field,
                    "must identify the active build or plan before exchange-changing requests are allowed",
                )
            )

    for field in (
        "credentials_loaded",
        "database_current",
        "unique_executor_confirmed",
        "facts_current",
    ):
        if facts.get(field) is not True:
            violations.append(
                Violation(
                    "GOV-REAL-004",
                    f"{path}.{field}",
                    "must be true before exchange-changing requests are allowed",
                )
            )


def validate_plan(plan: Mapping[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    expected = {
        "document_id": "HALPHA-PLAN-001",
        "level": "L4",
        "language": "zh-CN",
    }
    for field, value in expected.items():
        if plan.get(field) != value:
            violations.append(
                Violation("GOV-PLAN-001", field, f"must be {value!r}")
            )

    _validate_real_account_trading(plan, violations=violations)
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
