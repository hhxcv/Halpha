"""Summarize B04 exit evidence without weakening external or time gates."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.build_manifest import DEFAULT_ARTIFACT_SPECS, SCHEMA_VERSION  # noqa: E402
from halpha.source_identity import (  # noqa: E402
    SourceIdentityError,
    source_sha256_digest,
)
from tools.qualification.real_write_boundary import (  # noqa: E402
    assess_closed_real_write_boundary,
)


DEFAULT_OUTPUT = ROOT / "build/qualification/b04-summary.json"
JSON_ARTIFACTS = {
    "b03_summary": "build/qualification/b03-summary.json",
    "historical_data": "build/qualification/b04-historical-data.json",
    "historical_catalog": "build/qualification/b04-historical-catalog.json",
    "historical_backtest": "build/qualification/b04-historical-backtest.json",
    "product_demo_cycle": "build/qualification/b04-product-demo-cycle.json",
    "notification_boundary": "build/qualification/b04-notification-boundary.json",
    "outcome_boundary": "build/qualification/b04-outcome-boundary.json",
    "empty_database_restore": "build/qualification/b04-empty-restore.json",
    "windows_fault_drills": "build/qualification/b04-windows-fault-drills.json",
    "browser_workbench": "build/qualification/b04-browser.json",
    "implemented_complexity_budget": "build/qualification/b04-complexity-budget.json",
    "critical_invariant_trace": "build/qualification/b04-critical-invariant-trace.json",
    "windows_72h_soak": "build/qualification/b04-windows-72h-soak.json",
    "actual_smtp_delivery": "build/qualification/b04-smtp-delivery.json",
    "live_read_only_observation": "build/qualification/b04-live-read-only.json",
}
EXTERNAL_EXIT_EVIDENCE = {
    "actual_smtp_delivery": "ACTUAL_SMTP_DELIVERY",
    "live_read_only_observation": "BINANCE_LIVE_READ_ONLY_7_TO_14_DAY_OBSERVATION",
    "windows_72h_soak": "WINDOWS_72H_MINIMUM_DURATION",
}
EXPECTED_EXTERNAL_STAGES = {
    "actual_smtp_delivery": "B04_ACTUAL_SMTP_DELIVERY",
    "live_read_only_observation": "B04_BINANCE_LIVE_READ_ONLY_OBSERVATION",
    "windows_72h_soak": "B04_WINDOWS_72H_SOAK",
}
REQUIRED_SOURCE_SHA256_ARTIFACTS = {
    "actual_smtp_delivery",
    "browser_workbench",
    "critical_invariant_trace",
    "empty_database_restore",
    "historical_backtest",
    "implemented_complexity_budget",
    "live_read_only_observation",
    "notification_boundary",
    "outcome_boundary",
    "product_demo_cycle",
    "windows_72h_soak",
    "windows_fault_drills",
}
REQUIRED_B04_MANIFEST_BINDINGS = {
    "b04_historical_data",
    "b04_historical_catalog",
    "b04_historical_backtest",
    "b04_product_demo_cycle",
    "b04_notification_boundary",
    "b04_outcome_boundary",
    "b04_empty_database_restore",
    "b04_windows_fault_drills",
    "b04_browser_workbench",
    "b04_implemented_complexity_budget",
    "b04_critical_invariant_trace",
    "b04_pytest_junit",
    "b04_playwright_report",
    "b04_windows_72h_soak",
    "b04_actual_smtp_delivery",
    "b04_live_read_only_observation",
    "b04_summary",
}


class B04SummaryError(RuntimeError):
    """Sanitized B04 summary failure."""


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


def _source_sha256_evidence(root: Path, value: object) -> dict[str, Any]:
    if value is None:
        return {"status": "NOT_DECLARED", "drift": []}
    if not isinstance(value, dict) or not value:
        return {
            "status": "REJECTED",
            "drift": [{"path": None, "reason": "SOURCE_SHA256_MAP_INVALID"}],
        }

    drift: list[dict[str, Any]] = []
    for relative, expected in sorted(value.items(), key=lambda item: str(item[0])):
        if not isinstance(relative, str) or not relative or not isinstance(expected, str):
            drift.append(
                {
                    "path": relative if isinstance(relative, str) else None,
                    "reason": "SOURCE_SHA256_ENTRY_INVALID",
                }
            )
            continue
        source = (root / relative).resolve()
        if not source.is_relative_to(root):
            drift.append({"path": relative, "reason": "SOURCE_PATH_OUTSIDE_REPOSITORY"})
            continue
        if not source.is_file():
            drift.append({"path": relative, "reason": "SOURCE_FILE_MISSING"})
            continue
        actual = _sha256_file(source)
        if actual != expected:
            drift.append(
                {
                    "path": relative,
                    "reason": "SOURCE_SHA256_MISMATCH",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return {"status": "QUALIFIED" if not drift else "REJECTED", "drift": drift}


def _json_artifact(
    root: Path,
    relative: str,
    *,
    require_source_sha256: bool = False,
) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        return {
            "path": relative,
            "status": "MISSING",
            "stage": None,
            "observed_at": None,
            "evidence_digest": None,
            "sha256": None,
            "checks_all_true": False,
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "path": relative,
            "status": "REJECTED",
            "stage": None,
            "observed_at": None,
            "evidence_digest": None,
            "sha256": _sha256_file(path),
            "checks_all_true": False,
            "error": "INVALID_JSON",
        }
    if not isinstance(value, dict):
        raise B04SummaryError(f"B04_ARTIFACT_ROOT_INVALID file={path.name}")
    checks = value.get("checks")
    checks_all_true = (
        isinstance(checks, dict) and bool(checks) and all(item is True for item in checks.values())
    )
    source_sha256 = _source_sha256_evidence(root, value.get("source_sha256"))
    result = {
        "path": relative,
        "status": value.get("status"),
        "stage": value.get("stage") or value.get("scope"),
        "observed_at": value.get("observed_at"),
        "evidence_digest": value.get("evidence_digest"),
        "sha256": _sha256_file(path),
        "checks_all_true": checks_all_true,
        "source_sha256_status": source_sha256["status"],
        "source_sha256_drift": source_sha256["drift"],
    }
    if result["status"] == "QUALIFIED":
        if source_sha256["status"] == "REJECTED":
            result["status"] = "REJECTED"
            result["error"] = "SOURCE_SHA256_DRIFT"
        elif require_source_sha256 and source_sha256["status"] != "QUALIFIED":
            result["status"] = "REJECTED"
            result["error"] = "SOURCE_SHA256_REQUIRED"
    return result


def _pytest_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"path": path.as_posix(), "status": "MISSING"}
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ET.ParseError):
        return {"path": path.as_posix(), "status": "REJECTED", "error": "INVALID_XML"}
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    return {
        "path": path.as_posix(),
        "sha256": _sha256_file(path),
        **counts,
        "status": (
            "QUALIFIED"
            if counts["tests"] > 0 and counts["failures"] == 0 and counts["errors"] == 0
            else "REJECTED"
        ),
    }


def classify_summary(
    artifacts: Mapping[str, Mapping[str, Any]],
    *,
    pytest_status: str,
    gates_qualified: bool,
) -> str:
    statuses = {str(item.get("status")) for item in artifacts.values()}
    if "REJECTED" in statuses or pytest_status == "REJECTED" or not gates_qualified:
        return "REJECTED"
    if statuses == {"QUALIFIED"} and pytest_status == "QUALIFIED":
        return "QUALIFIED"
    return "IN_PROGRESS"


def is_current_b04_package(status: object) -> bool:
    return str(status).strip().upper() in {
        "IN_PROGRESS",
        "IN_PROGRESS_CONSTRUCTION_GATE_AND_LONG_OBSERVATION",
        "COMPLETED",
    }


def windows_soak_contract_error(value: Mapping[str, Any]) -> str | None:
    if value.get("schema_version") != 3:
        return "WINDOWS_SOAK_SCHEMA_V3_REQUIRED"
    checks = value.get("checks")
    if not isinstance(checks, dict):
        return "WINDOWS_SOAK_CHECKS_INVALID"
    for required_check in (
        "app_runtime_source_identity_matches_current",
        "configuration_identity_unchanged",
        "continuous_process_identity_unchanged",
        "executor_runtime_source_identity_matches_current",
        "source_identity_unchanged",
    ):
        if checks.get(required_check) is not True:
            return f"WINDOWS_SOAK_REQUIRED_CHECK_FAILED:{required_check}"
    source = value.get("source_sha256")
    frozen_source_digest = value.get("source_sha256_digest")
    current_source_digest = value.get("current_source_sha256_digest")
    if not isinstance(source, dict) or not isinstance(frozen_source_digest, str):
        return "WINDOWS_SOAK_SOURCE_IDENTITY_INVALID"
    try:
        actual_source_digest = source_sha256_digest(source)
    except SourceIdentityError:
        return "WINDOWS_SOAK_SOURCE_IDENTITY_INVALID"
    if frozen_source_digest != actual_source_digest:
        return "WINDOWS_SOAK_SOURCE_DIGEST_MISMATCH"
    if current_source_digest != frozen_source_digest:
        return "WINDOWS_SOAK_CURRENT_SOURCE_DIGEST_MISMATCH"
    if checks.get("minimum_72_hours_observed") is not True:
        return "WINDOWS_72_AWAKE_HOURS_NOT_MET"
    if checks.get("no_sleep_or_hibernate_over_60_seconds") is not True:
        return "WINDOWS_SLEEP_OR_HIBERNATION_LIMIT_EXCEEDED"
    try:
        started = int(value["started_unbiased_100ns"])
        observed = int(value["observed_unbiased_100ns"])
        elapsed_hours = float(value["elapsed_hours"])
        wall_hours = float(value["wall_elapsed_hours"])
        sleep_seconds = float(value["sleep_or_hibernate_seconds"])
    except (KeyError, TypeError, ValueError):
        return "WINDOWS_SOAK_CLOCK_FIELDS_INVALID"
    if observed < started:
        return "WINDOWS_SOAK_UNBIASED_CLOCK_REGRESSION"
    derived_awake_hours = (observed - started) / 10_000_000 / 3600
    if abs(derived_awake_hours - elapsed_hours) > 0.001:
        return "WINDOWS_SOAK_AWAKE_DURATION_DRIFT"
    if elapsed_hours < 72.0:
        return "WINDOWS_72_AWAKE_HOURS_NOT_MET"
    if wall_hours + 0.001 < elapsed_hours:
        return "WINDOWS_SOAK_WALL_DURATION_INVALID"
    derived_sleep_seconds = max(0.0, (wall_hours - elapsed_hours) * 3600)
    if abs(derived_sleep_seconds - sleep_seconds) > 1.0:
        return "WINDOWS_SOAK_SLEEP_DURATION_DRIFT"
    if sleep_seconds > 60.0:
        return "WINDOWS_SLEEP_OR_HIBERNATION_LIMIT_EXCEEDED"
    return None


def summarize(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    artifacts = {
        name: _json_artifact(
            root,
            relative,
            require_source_sha256=name in REQUIRED_SOURCE_SHA256_ARTIFACTS,
        )
        for name, relative in JSON_ARTIFACTS.items()
    }
    pytest = _pytest_summary(root / "build/qualification/b04-pytest.xml")
    plan = yaml.safe_load(
        (root / "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml").read_text(
            encoding="utf-8"
        )
    )
    current_state = plan["current_state"]
    package = plan["construction_packages"]["B04"]
    real_write_boundary = assess_closed_real_write_boundary(current_state)
    plan_gates = {
        "d00_aligned": plan["design_formalization_gate"]["status"] == "ALIGNED",
        "b00_qualified": plan["dependency_qualification_gate"]["status"] == "QUALIFIED",
        "b01_to_b03_completed": all(
            plan["construction_packages"][name]["status"] == "COMPLETED"
            for name in ("B01", "B02", "B03")
        ),
        "b04_is_current_package": is_current_b04_package(package.get("status")),
        "live_write_build_capability_fail_closed": (
            real_write_boundary["live_write_build_capability"]
            == "NOT_QUALIFIED"
        ),
        "b05_real_capital_blocked": (
            real_write_boundary["b05_real_capital_eligibility"] == "BLOCKED"
        ),
        "runtime_real_write_gate_closed": (
            real_write_boundary["runtime_real_write_gate"] == "CLOSED"
        ),
    }
    for name, expected_stage in EXPECTED_EXTERNAL_STAGES.items():
        artifact = artifacts[name]
        if artifact["status"] == "QUALIFIED" and (
            artifact["stage"] != expected_stage or not artifact["checks_all_true"]
        ):
            artifact["status"] = "REJECTED"
            artifact["error"] = "EXTERNAL_EVIDENCE_CONTRACT_INVALID"
    soak = artifacts["windows_72h_soak"]
    if soak["status"] == "QUALIFIED":
        raw_soak = json.loads((root / JSON_ARTIFACTS["windows_72h_soak"]).read_text(encoding="utf-8"))
        contract_error = windows_soak_contract_error(raw_soak)
        if contract_error is not None:
            soak["status"] = "REJECTED"
            soak["error"] = contract_error

    manifest_names = {spec.name for spec in DEFAULT_ARTIFACT_SPECS}
    manifest_contract = {
        "schema_version": SCHEMA_VERSION,
        "required_b04_bindings": sorted(REQUIRED_B04_MANIFEST_BINDINGS),
        "missing_b04_bindings": sorted(REQUIRED_B04_MANIFEST_BINDINGS - manifest_names),
    }
    plan_binding_value = {
        "accepted_design_set": plan["accepted_design_set"],
        "scope": package["scope"],
        "exit_evidence": package["exit_evidence"],
    }
    gates_qualified = all(plan_gates.values()) and not manifest_contract[
        "missing_b04_bindings"
    ]
    status = classify_summary(
        artifacts,
        pytest_status=str(pytest.get("status")),
        gates_qualified=gates_qualified,
    )
    unmet = sorted(
        evidence_name
        for artifact_name, evidence_name in EXTERNAL_EXIT_EVIDENCE.items()
        if artifacts[artifact_name]["status"] != "QUALIFIED"
    )
    unmet.extend(
        sorted(
            f"LOCAL_ARTIFACT:{name}"
            for name, artifact in artifacts.items()
            if name not in EXTERNAL_EXIT_EVIDENCE and artifact["status"] != "QUALIFIED"
        )
    )
    if pytest.get("status") != "QUALIFIED":
        unmet.append("LOCAL_TESTS:B04_PYTEST")
    if not gates_qualified:
        unmet.append("LOCAL_GATES:B04_PLAN_OR_MANIFEST_CONTRACT")

    revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "stage": "B04_EXIT_EVIDENCE_SUMMARY",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_revision": revision,
        "workflow_run_id": None,
        "workflow_conclusion": "NOT_RUN_UNCOMMITTED",
        "superseded_by": None,
        "artifacts": artifacts,
        "tests": {"pytest": pytest},
        "plan_gates": plan_gates,
        "manifest_contract": manifest_contract,
        "plan_binding": {
            "document_id": plan["document_id"],
            "status": plan["status"],
            "accepted_at": plan["accepted_at"].isoformat(),
            "p0_b04_contract_sha256": sha256(_canonical(plan_binding_value)).hexdigest(),
        },
        "unmet_exit_evidence": sorted(set(unmet)),
        "status": status,
        "scope": "B04_AGGREGATION_ONLY_NO_DATABASE_OR_VENUE_CONNECTION",
        "source_sha256": {
            "src/halpha/build_manifest.py": _sha256_file(root / "src/halpha/build_manifest.py"),
            "tools/qualification/summarize_b04_evidence.py": _sha256_file(
                root / "tools/qualification/summarize_b04_evidence.py"
            ),
        },
        "errors": [] if status != "REJECTED" else sorted(set(unmet)),
    }
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise B04SummaryError("B04_SUMMARY_OUTPUT_OUTSIDE_REPOSITORY")
    evidence = summarize(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(output)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] in {"IN_PROGRESS", "QUALIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
