"""Aggregate requirement-specific B02 qualification evidence without design copies."""

from __future__ import annotations

import argparse
import base64
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, Sequence
import xml.etree.ElementTree as ET

import yaml


EXACT_NODE = r"D:\Environment\node-v24.18.0-win-x64\node.exe"

EXPECTED_DATABASE_CHECKS = {
    "api_open_scope_conflict_maps_to_stable_code",
    "concurrent_cross_version_allocations_are_serialized",
    "deadline_is_idempotent_and_missed_window_never_backfills_entry",
    "different_instrument_with_remaining_allocation_accepted",
    "draft_fix_activation_committed_atomically",
    "failed_atomic_attempts_left_no_partial_records",
    "five_control_commands_persisted",
    "idempotency_key_content_conflict_rejected",
    "idempotent_command_returns_original_receipt",
    "loss_revision_below_threshold_persists_without_exit",
    "max_loss_atomically_latches_stop_and_full_exit",
    "multi_instrument_allocation_overrun_rejected",
    "no_b02_venue_or_execution_write",
    "operations_projection_is_environment_scoped_and_authoritative",
    "paused_activation_drops_racing_proposal_before_cap_or_write",
    "plan_event_conflicts_and_deadline_replays_add_no_duplicates",
    "plan_event_same_source_different_digest_conflicts",
    "plan_event_same_source_replays_original",
    "proposal_is_normalized_cap_checked_and_persisted_atomically",
    "resume_did_not_clear_later_exit_or_takeover",
    "same_instrument_attribution_ambiguity_rejected",
    "secondary_loss_does_not_change_primary_allocation",
    "user_resume_requires_future_authoritative_exe_evidence",
    "writer_continuity_loss_paused_all_open_activations",
}

EXPECTED_PARITY_CHECKS = {
    "adapter_b02_has_no_venue_write_calls",
    "backtest_engine_disposed",
    "backtest_loaded_production_adapter",
    "live_loaded_production_adapter",
    "live_node_lifecycle_closed",
    "one_proposal_per_runtime",
    "pure_logic_has_no_framework_or_venue_write_calls",
    "same_activation_strategy_id",
    "same_normalized_input_same_exact_proposal",
    "same_production_adapter_class",
    "same_production_logic_class",
    "same_proposal_maps_to_same_proposed_action",
}


class B02SummaryError(RuntimeError):
    """Sanitized B02 evidence aggregation failure."""


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raise B02SummaryError(f"B02_EVIDENCE_JSON_INVALID file={path.name}") from None
    if not isinstance(value, dict):
        raise B02SummaryError(f"B02_EVIDENCE_JSON_ROOT_INVALID file={path.name}")
    return value


def _command(command: Sequence[str], *, cwd: Path) -> int:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode


def _artifact(path: Path, *, root: Path, checks: set[str] | None = None) -> dict[str, Any]:
    report = _json(path)
    check_values = report.get("checks")
    exact_checks = True
    if checks is not None:
        exact_checks = (
            isinstance(check_values, dict)
            and set(check_values) == checks
            and all(value is True for value in check_values.values())
        )
    qualified = report.get("status") == "QUALIFIED" and exact_checks
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_file(path),
        "reported_evidence_digest": report.get("evidence_digest"),
        "check_count": len(check_values) if isinstance(check_values, dict) else None,
        "status": "QUALIFIED" if qualified else "REJECTED",
    }


def _pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None:
        raise B02SummaryError("B02_PYTEST_JUNIT_SUITE_MISSING")
    values = {
        key: int(suite.attrib.get(key, "-1"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    return {
        **values,
        "report_sha256": _sha256_file(path),
        "status": (
            "QUALIFIED"
            if values == {"tests": 124, "failures": 0, "errors": 0, "skipped": 0}
            else "REJECTED"
        ),
    }


def _vitest_summary(path: Path) -> dict[str, Any]:
    report = _json(path)
    values = {
        key: int(report.get(key, -1))
        for key in ("numTotalTests", "numPassedTests", "numFailedTests")
    }
    return {
        **values,
        "report_sha256": _sha256_file(path),
        "status": (
            "QUALIFIED"
            if report.get("success") is True
            and values == {
                "numTotalTests": 3,
                "numPassedTests": 3,
                "numFailedTests": 0,
            }
            else "REJECTED"
        ),
    }


def _playwright_tests(suites: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for suite in suites:
        for spec in suite.get("specs", []):
            yield from spec.get("tests", [])
        yield from _playwright_tests(suite.get("suites", []))


def _attachment_json(attachment: dict[str, Any]) -> dict[str, Any]:
    body = attachment.get("body")
    if not isinstance(body, str):
        raise B02SummaryError("B02_PLAYWRIGHT_ATTACHMENT_BODY_MISSING")
    try:
        value = json.loads(base64.b64decode(body).decode("utf-8"))
    except Exception:
        raise B02SummaryError("B02_PLAYWRIGHT_ATTACHMENT_INVALID") from None
    if not isinstance(value, dict):
        raise B02SummaryError("B02_PLAYWRIGHT_ATTACHMENT_ROOT_INVALID")
    return value


def _playwright_summary(path: Path) -> dict[str, Any]:
    report = _json(path)
    stats = report.get("stats", {})
    argv = report.get("config", {}).get("argv", [])
    tests = list(_playwright_tests(report.get("suites", [])))
    result_statuses: list[str] = []
    axe_attachment_count = 0
    axe_violation_count = 0
    screenshot_count = 0
    layout_attachment_count = 0
    layout_failures = 0
    for test in tests:
        for result in test.get("results", []):
            result_statuses.append(str(result.get("status")))
            for attachment in result.get("attachments", []):
                name = str(attachment.get("name", ""))
                if name.endswith("-axe.json"):
                    axe_attachment_count += 1
                    axe_violation_count += len(_attachment_json(attachment).get("violations", []))
                elif name in {"new-plan.png", "operations-after-exit.png"}:
                    screenshot_count += 1
                elif name == "operations-layout.json":
                    layout_attachment_count += 1
                    layout = _attachment_json(attachment)
                    if (
                        layout.get("scrollWidth") != layout.get("clientWidth")
                        or layout.get("offenders") != []
                    ):
                        layout_failures += 1
    qualified = (
        argv
        and argv[0] == EXACT_NODE
        and stats.get("expected") == 2
        and stats.get("unexpected") == 0
        and result_statuses == ["passed", "passed"]
        and axe_attachment_count == 12
        and axe_violation_count == 0
        and screenshot_count == 4
        and layout_attachment_count == 2
        and layout_failures == 0
    )
    return {
        "report_sha256": _sha256_file(path),
        "node_executable": argv[0] if argv else None,
        "expected": int(stats.get("expected", -1)),
        "unexpected": int(stats.get("unexpected", -1)),
        "result_statuses": result_statuses,
        "axe_attachment_count": axe_attachment_count,
        "axe_violation_count": axe_violation_count,
        "screenshot_count": screenshot_count,
        "layout_attachment_count": layout_attachment_count,
        "layout_failures": layout_failures,
        "status": "QUALIFIED" if qualified else "REJECTED",
    }


def _frontend_artifacts(root: Path) -> dict[str, Any]:
    dist = root / "frontend" / "dist"
    files = sorted(path for path in dist.rglob("*") if path.is_file())
    generated_schema = _json(root / "frontend/src/generated/oneShotStrategySchema.json")
    registry = _json(root / "src/halpha/planning/strategy_registry.json")
    definitions = registry.get("strategies", [])
    one_shot = next(
        (
            item for item in definitions
            if item.get("strategy_id") == "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
        ),
        None,
    )
    validator_path = root / "frontend/src/generated/oneShotStrategyValidator.cjs"
    validator_source = validator_path.read_text(encoding="utf-8")
    schema_matches = isinstance(one_shot, dict) and generated_schema == one_shot.get("parameter_schema")
    validator_is_static = "new Function" not in validator_source and "eval(" not in validator_source
    return {
        "dist_files": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256_file(path),
            }
            for path in files
        ],
        "generated_schema_sha256": _sha256_file(
            root / "frontend/src/generated/oneShotStrategySchema.json"
        ),
        "precompiled_validator_sha256": _sha256_file(validator_path),
        "schema_matches_registry": schema_matches,
        "validator_is_static": validator_is_static,
        "status": (
            "QUALIFIED"
            if files and schema_matches and validator_is_static
            else "REJECTED"
        ),
    }


def summarize(root: Path) -> dict[str, Any]:
    qualification = root / "build/qualification"
    artifacts = {
        "database_boundary": _artifact(
            qualification / "b02-database-boundary.json",
            root=root,
            checks=EXPECTED_DATABASE_CHECKS,
        ),
        "strategy_adapter_parity": _artifact(
            qualification / "b02-strategy-adapter-parity.json",
            root=root,
            checks=EXPECTED_PARITY_CHECKS,
        ),
        "critical_invariant_trace": _artifact(
            qualification / "b02-critical-invariant-trace.json",
            root=root,
        ),
        "license_inventory": _artifact(
            qualification / "b02-license-inventory.json",
            root=root,
        ),
    }
    critical = _json(qualification / "b02-critical-invariant-trace.json")
    license_inventory = _json(qualification / "b02-license-inventory.json")
    if critical.get("record_count") != 6:
        artifacts["critical_invariant_trace"]["status"] = "REJECTED"
    ledger = license_inventory.get("direct_dependency_ledger", {})
    if ledger.get("missing") != [] or ledger.get("unexpected") != []:
        artifacts["license_inventory"]["status"] = "REJECTED"

    tests = {
        "pytest": _pytest_summary(qualification / "b02-pytest.xml"),
        "vitest": _vitest_summary(
            qualification / "browser/b02-vitest-report.json"
        ),
        "playwright": _playwright_summary(
            qualification / "browser/b02-playwright-report.json"
        ),
    }
    mechanical_gates = {
        "documentation": _command(
            (
                sys.executable,
                ".agents/skills/write-halpha-docs/scripts/validate_halpha_docs.py",
                "docs",
            ),
            cwd=root,
        ),
        "accepted_integrity": _command(
            (
                sys.executable,
                ".agents/skills/write-halpha-docs/scripts/validate_halpha_docs.py",
                "--accepted-integrity",
            ),
            cwd=root,
        ),
        "construction_governance": _command(
            (sys.executable, "governance/validate_construction_plan.py"),
            cwd=root,
        ),
        "git_diff_check": _command(("git", "diff", "--check"), cwd=root),
    }
    plan = yaml.safe_load(
        (root / "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml").read_text(
            encoding="utf-8"
        )
    )
    current_state = plan["current_state"]
    real_write_boundary = {
        "live_write_build_capability": current_state["live_write_build_capability"],
        "b05_package_eligibility": current_state["b05_package_eligibility"],
        "runtime_real_write_gate": current_state["runtime_real_write_gate"],
    }
    real_write_boundary["status"] = (
        "QUALIFIED"
        if real_write_boundary
        == {
            "live_write_build_capability": "NOT_QUALIFIED",
            "b05_package_eligibility": "NOT_AUTHORIZED",
            "runtime_real_write_gate": "CLOSED",
        }
        else "REJECTED"
    )

    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    status_lines = subprocess.run(
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    frontend = _frontend_artifacts(root)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_revision": revision,
        "source_clean": not bool(status_lines),
        "dirty_entry_count": len(status_lines),
        "workflow_run_id": None,
        "workflow_conclusion": "NOT_RUN_UNCOMMITTED",
        "superseded_by": None,
        "artifacts": artifacts,
        "tests": tests,
        "frontend": frontend,
        "mechanical_gates": mechanical_gates,
        "real_write_boundary": real_write_boundary,
        "build_manifest_expectation": {
            "completeness": "COMPLETE",
            "build_eligible": False,
            "reason": "CURRENT_WORKTREE_UNCOMMITTED",
        },
        "scope": "B02_IMPLEMENTATION_ONLY_NO_EXECUTION_ACTION_VENUE_FACT_OR_VENUE_WRITE",
    }
    qualified = (
        all(item["status"] == "QUALIFIED" for item in artifacts.values())
        and all(item["status"] == "QUALIFIED" for item in tests.values())
        and frontend["status"] == "QUALIFIED"
        and all(code == 0 for code in mechanical_gates.values())
        and real_write_boundary["status"] == "QUALIFIED"
        and not evidence["source_clean"]
    )
    evidence["status"] = "QUALIFIED" if qualified else "REJECTED"
    canonical = json.dumps(
        evidence,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    evidence["evidence_digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    evidence = summarize(root)
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise B02SummaryError("B02_SUMMARY_OUTPUT_OUTSIDE_REPOSITORY")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
