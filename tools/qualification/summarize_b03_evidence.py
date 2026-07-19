"""Aggregate B03 execution-boundary evidence without copying stable design semantics."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.qualification.real_write_boundary import (
    assess_closed_real_write_boundary,
)


EXPECTED_BOUNDARY_CHECKS = {
    "authoritative_fact_advances_original_action",
    "cancel_is_a_distinct_persisted_action_for_original_identity",
    "closure_atomically_completes_plan_and_releases_allocation",
    "database_b03_boundary_objects_present",
    "database_rejects_action_identity_mutation",
    "executor_cannot_update_append_only_fact",
    "executor_fact_privilege_is_insert_only",
    "exit_uses_explicit_quantity_reduce_only_execution_action",
    "fill_atomically_freezes_r_and_creates_explicit_protection",
    "plan_cap_action_atomic_and_replay_stable",
    "protection_working_precedes_take_profit_responsibilities",
    "qualification_records_rolled_back",
    "submitting_crash_is_query_only_unknown",
    "two_take_profits_use_same_execution_action_flow",
}
EXPECTED_PRODUCT_DEMO_CHECKS = {
    "continuity_pause_precedes_node_start",
    "demo_ack_returns_to_original_uuid",
    "manual_resume_uses_stable_command",
    "product_cancel_and_closure_complete",
    "product_plan_cap_action_precedes_venue_call",
    "product_runtime_reconciliation_precedes_ready",
    "qualification_records_cleaned_after_terminal",
    "secrets_absent_from_runtime_logs",
}
SHARED_EXECUTION_SOURCES = (
    "src/halpha/venue_integration/models.py",
    "src/halpha/venue_integration/transitions.py",
    "src/halpha/venue_integration/repository.py",
    "src/halpha/venue_integration/service.py",
    "src/halpha/venue_integration/gateway.py",
    "src/halpha/venue_integration/nautilus_client.py",
    "src/halpha/venue_integration/nautilus_events.py",
    "src/halpha/executor/coordinator.py",
    "src/halpha/executor/runtime.py",
    "migrations/versions/20260717_0004_b03_execution_boundaries.py",
    "migrations/versions/20260717_0005_b03_client_order_identity.py",
)


class B03SummaryError(RuntimeError):
    """Sanitized B03 evidence aggregation failure."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


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
        raise B03SummaryError(f"B03_EVIDENCE_JSON_INVALID file={path.name}") from None
    if not isinstance(value, dict):
        raise B03SummaryError(f"B03_EVIDENCE_JSON_ROOT_INVALID file={path.name}")
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


def _checked_artifact(
    path: Path,
    *,
    root: Path,
    expected_checks: set[str],
    venue_write_performed: bool,
) -> dict[str, Any]:
    report = _json(path)
    checks = report.get("checks")
    exact_checks = (
        isinstance(checks, dict)
        and set(checks) == expected_checks
        and all(value is True for value in checks.values())
    )
    qualified = (
        report.get("status") == "QUALIFIED"
        and report.get("environment_kind") == "DEMO"
        and report.get("authority_class") == "DEMO_VALIDATION"
        and report.get("venue_write_performed") is venue_write_performed
        and exact_checks
    )
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_file(path),
        "reported_evidence_digest": report.get("evidence_digest"),
        "check_count": len(checks) if isinstance(checks, dict) else None,
        "status": "QUALIFIED" if qualified else "REJECTED",
    }


def _pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None:
        raise B03SummaryError("B03_PYTEST_JUNIT_SUITE_MISSING")
    values = {
        key: int(suite.attrib.get(key, "-1"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    return {
        **values,
        "report_sha256": _sha256_file(path),
        "status": (
            "QUALIFIED"
            if values == {"tests": 151, "failures": 0, "errors": 0, "skipped": 0}
            else "REJECTED"
        ),
    }


def _source_equivalence(root: Path) -> dict[str, Any]:
    files = [root / relative for relative in SHARED_EXECUTION_SOURCES]
    manifest = {
        relative: _sha256_file(root / relative)
        for relative in SHARED_EXECUTION_SOURCES
    }
    combined_sources = "\n".join(path.read_text(encoding="utf-8") for path in files)
    forbidden_types = (
        "DemoExecutionAction",
        "LiveExecutionAction",
        "DemoExecutionRepository",
        "LiveExecutionRepository",
        "SimulatedExecutionAction",
    )
    checks = {
        "one_execution_action_model": combined_sources.count("class ExecutionAction(") == 1,
        "one_execution_repository": (
            combined_sources.count("class PostgreSQLExecutionActionRepository:") == 1
        ),
        "one_nautilus_execution_client": (
            combined_sources.count("class NautilusVenueExecutionClient:") == 1
        ),
        "no_environment_specific_execution_types": not any(
            forbidden in combined_sources for forbidden in forbidden_types
        ),
        "one_shared_source_manifest_for_demo_and_live": True,
    }
    manifest_digest = sha256(_canonical(manifest)).hexdigest()
    return {
        "shared_source_manifest": manifest,
        "shared_source_manifest_digest": manifest_digest,
        "environment_bindings": {
            "DEMO": {
                "shared_source_manifest_digest": manifest_digest,
                "profile": "BINANCE_DEMO",
                "authority_class": "DEMO_VALIDATION",
            },
            "LIVE": {
                "shared_source_manifest_digest": manifest_digest,
                "profiles": ["BINANCE_LIVE_READ_ONLY", "BINANCE_LIVE_WRITE"],
                "authority_class": "LIVE_REAL_CAPITAL",
                "runtime_real_write_gate_required": "OPEN",
            },
        },
        "allowed_environment_variations": [
            "environment identity",
            "execution profile",
            "credential reference",
            "venue endpoint",
            "authority and capital allocation",
            "runtime real-write gate",
        ],
        "checks": checks,
        "status": "QUALIFIED" if all(checks.values()) else "REJECTED",
    }


def summarize(root: Path) -> dict[str, Any]:
    qualification = root / "build/qualification"
    boundary_path = qualification / "b03-execution-boundary.json"
    product_demo_path = qualification / "b03-product-demo-roundtrip.json"
    artifacts = {
        "execution_boundary": _checked_artifact(
            boundary_path,
            root=root,
            expected_checks=EXPECTED_BOUNDARY_CHECKS,
            venue_write_performed=False,
        ),
        "product_demo_roundtrip": _checked_artifact(
            product_demo_path,
            root=root,
            expected_checks=EXPECTED_PRODUCT_DEMO_CHECKS,
            venue_write_performed=True,
        ),
    }
    product_demo = _json(product_demo_path)
    product_demo_safety = {
        "profile": product_demo.get("profile"),
        "proxy_supplied": product_demo.get("proxy_supplied"),
        "proxy_value_persisted": product_demo.get("proxy_value_persisted"),
        "raw_credential_found": product_demo.get("secret_scan", {}).get(
            "raw_credential_found"
        ),
    }
    product_demo_safety["status"] = (
        "QUALIFIED"
        if product_demo_safety["profile"] == "BINANCE_DEMO"
        and product_demo_safety["proxy_value_persisted"] is False
        and product_demo_safety["raw_credential_found"] is False
        else "REJECTED"
    )

    b00 = _json(qualification / "b00-qualification-latest.json")
    b00_dependency = {
        "required_output_count": b00.get("required_output_count"),
        "account_configuration_blocks_b00": b00.get(
            "account_configuration_evaluation", {}
        ).get("blocks_b00"),
        "account_setting_mutation": b00.get(
            "account_configuration_evaluation", {}
        ).get("account_setting_mutation"),
    }
    required_outputs = b00.get("required_outputs")
    all_b00_outputs_qualified = (
        isinstance(required_outputs, dict)
        and len(required_outputs) == 14
        and all(item.get("status") == "QUALIFIED" for item in required_outputs.values())
    )
    b00_dependency["status"] = (
        "QUALIFIED"
        if b00_dependency["required_output_count"] == 14
        and all_b00_outputs_qualified
        and b00_dependency["account_configuration_blocks_b00"] is False
        and b00_dependency["account_setting_mutation"] is False
        else "REJECTED"
    )

    plan = yaml.safe_load(
        (root / "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml").read_text(
            encoding="utf-8"
        )
    )
    real_write_boundary = assess_closed_real_write_boundary(plan)

    record_families_source = (
        root / "src/halpha/database/record_families.py"
    ).read_text(encoding="utf-8")
    record_family_boundary = {
        "expected_count": 16,
        "execution_action_owner": "EXE",
        "venue_fact_owner": "DAT",
        "status": (
            "QUALIFIED"
            if '"execution_action": "EXE"' in record_families_source
            and '"venue_fact": "DAT"' in record_families_source
            and "P0_PRODUCT_RECORD_FAMILY_COUNT_MUST_BE_16" in record_families_source
            else "REJECTED"
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
        "construction_governance": _command(
            (sys.executable, "governance/validate_construction_plan.py"),
            cwd=root,
        ),
        "critical_invariant_trace": _command(
            (sys.executable, "tools/qualification/verify_critical_invariant_trace.py"),
            cwd=root,
        ),
        "git_diff_check": _command(("git", "diff", "--check"), cwd=root),
    }

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
    tests = {"pytest": _pytest_summary(qualification / "b03-pytest.xml")}
    source_equivalence = _source_equivalence(root)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_revision": revision,
        "source_clean": not bool(status_lines),
        "dirty_entry_count": len(status_lines),
        "workflow_run_id": None,
        "workflow_conclusion": "NOT_RUN_UNCOMMITTED" if status_lines else "NOT_RUN_LOCAL",
        "superseded_by": None,
        "artifacts": artifacts,
        "tests": tests,
        "source_equivalence": source_equivalence,
        "product_demo_safety": product_demo_safety,
        "b00_dependency": b00_dependency,
        "record_family_boundary": record_family_boundary,
        "mechanical_gates": mechanical_gates,
        "real_write_boundary": real_write_boundary,
        "build_manifest_expectation": {
            "completeness": "COMPLETE",
            "build_eligible": not bool(status_lines),
            "reason": (
                "CURRENT_SOURCE_CLEAN" if not status_lines else "CURRENT_WORKTREE_UNCOMMITTED"
            ),
        },
        "scope": "B03_BINANCE_DEMO_PRODUCT_EXECUTION_ONLY_LIVE_REAL_WRITE_CLOSED",
    }
    qualified = (
        all(item["status"] == "QUALIFIED" for item in artifacts.values())
        and all(item["status"] == "QUALIFIED" for item in tests.values())
        and source_equivalence["status"] == "QUALIFIED"
        and product_demo_safety["status"] == "QUALIFIED"
        and b00_dependency["status"] == "QUALIFIED"
        and record_family_boundary["status"] == "QUALIFIED"
        and all(code == 0 for code in mechanical_gates.values())
        and real_write_boundary["status"] == "QUALIFIED"
    )
    evidence["status"] = "QUALIFIED" if qualified else "REJECTED"
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise B03SummaryError("B03_SUMMARY_OUTPUT_OUTSIDE_REPOSITORY")
    evidence = summarize(root)
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
