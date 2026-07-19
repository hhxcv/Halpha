"""Derive the B04 successor-construction decision from scoped evidence claims."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence
from urllib.error import URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from halpha.configuration import load_settings
from halpha.runtime_identity import require_repository_runtime
from halpha.source_identity import (
    capture_product_runtime_source_identity,
    source_sha256_digest,
)


DEFAULT_CONFIG = Path("config/halpha.toml")
DEFAULT_SOAK_EVIDENCE = Path("build/qualification/b04-windows-72h-soak.json")
DEFAULT_JUNIT = Path("build/qualification/b04-construction-continuation-pytest.xml")
DEFAULT_OUTPUT = Path("build/qualification/b04-construction-continuation.json")
EVALUATOR_VERSION = "b04-construction-continuation-finalizer@1"
MINIMUM_PLATFORM_AWAKE_HOURS = 8.0
PRIOR_RULE_IDENTITY = (
    "HALPHA-ENG-001@v1.8.0#ENG-OBS-001-REQ|"
    "HALPHA-ENG-002@v0.9.0#ENG-AUTO-BLD-004-REQ"
)


class ConstructionContinuationError(RuntimeError):
    """Raised when evidence cannot be safely evaluated."""


def _canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _file_digest(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _repository_ref(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ConstructionContinuationError(f"PATH_OUTSIDE_REPOSITORY:{resolved}")
    return resolved.relative_to(root).as_posix()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstructionContinuationError(f"INVALID_JSON:{path}:{exc}") from exc
    if not isinstance(loaded, dict):
        raise ConstructionContinuationError(f"JSON_OBJECT_REQUIRED:{path}")
    return loaded


def _verify_embedded_digest(report: dict[str, Any]) -> str:
    recorded = report.get("evidence_digest")
    if not isinstance(recorded, str):
        raise ConstructionContinuationError("SOAK_EVIDENCE_DIGEST_MISSING")
    recorded_hex = recorded.removeprefix("sha256:")
    if len(recorded_hex) != 64 or any(character not in "0123456789abcdef" for character in recorded_hex):
        raise ConstructionContinuationError("SOAK_EVIDENCE_DIGEST_MISSING")
    digest_basis = dict(report)
    digest_basis.pop("evidence_digest", None)
    calculated_hex = _canonical_digest(digest_basis).removeprefix("sha256:")
    if calculated_hex != recorded_hex:
        raise ConstructionContinuationError("SOAK_EVIDENCE_DIGEST_MISMATCH")
    return f"sha256:{recorded_hex}"


def select_platform_continuity_checkpoint(
    report: dict[str, Any],
    *,
    minimum_awake_hours: float = MINIMUM_PLATFORM_AWAKE_HOURS,
) -> dict[str, Any]:
    """Select the first checkpoint proving same-boot Windows awake time."""

    try:
        started_unbiased = int(report["started_unbiased_100ns"])
        checkpoints = report["checkpoints"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ConstructionContinuationError("PLATFORM_CLOCK_FACTS_MISSING") from exc
    if not isinstance(checkpoints, list):
        raise ConstructionContinuationError("PLATFORM_CHECKPOINTS_INVALID")

    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            continue
        try:
            observed_unbiased = int(checkpoint["unbiased_interrupt_time_100ns"])
            recorded_hours = float(checkpoint["awake_elapsed_hours"])
        except (KeyError, TypeError, ValueError):
            continue
        if observed_unbiased < started_unbiased:
            continue
        calculated_hours = (observed_unbiased - started_unbiased) / 10_000_000 / 3600
        if abs(calculated_hours - recorded_hours) > 1e-6:
            continue
        if calculated_hours < minimum_awake_hours:
            continue
        observed_at = checkpoint.get("observed_at")
        if not isinstance(observed_at, str):
            continue
        return {
            "observed_at": observed_at,
            "awake_elapsed_hours": calculated_hours,
            "started_unbiased_100ns": started_unbiased,
            "observed_unbiased_100ns": observed_unbiased,
            "same_boot_unbiased_clock_monotonic": True,
        }
    raise ConstructionContinuationError("PLATFORM_AWAKE_8H_CHECKPOINT_NOT_FOUND")


def read_junit_summary(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ConstructionContinuationError(f"INVALID_JUNIT:{path}:{exc}") from exc
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    if not suites:
        raise ConstructionContinuationError("JUNIT_TESTSUITE_MISSING")
    leaf_suites = [suite for suite in suites if not suite.findall("./testsuite")]
    selected = leaf_suites or suites

    def total(attribute: str) -> int:
        result = 0
        for suite in selected:
            try:
                result += int(float(suite.attrib.get(attribute, "0")))
            except ValueError as exc:
                raise ConstructionContinuationError(
                    f"JUNIT_ATTRIBUTE_INVALID:{attribute}"
                ) from exc
        return result

    summary = {
        "tests": total("tests"),
        "failures": total("failures"),
        "errors": total("errors"),
        "skipped": total("skipped"),
    }
    if summary["tests"] <= 0:
        raise ConstructionContinuationError("JUNIT_NO_TESTS")
    return summary


def _latest_event(path: Path, event: str) -> dict[str, Any] | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("event") == event:
            return item
    return None


def _operations_status(port: int) -> int:
    try:
        with urlopen(f"http://127.0.0.1:{port}/operations", timeout=5) as response:
            return int(response.status)
    except (OSError, URLError):
        return 0


def _section(path: Path, start: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        raise ConstructionContinuationError(f"RULE_SECTION_NOT_FOUND:{path}")
    return text[start_index:end_index].strip()


def _current_rule_digest(root: Path) -> str:
    l2 = _section(
        root / "docs/L2/HALPHA-ENG-001-ai-development-and-engineering-quality.zh-CN.md",
        "## 5.1 建设继续与长期观察分离【ENG-OBS-001】",
        "## 5.2 ",
    )
    l3 = _section(
        root / "docs/L3/HALPHA-ENG-002-real-trade-core-technology-stack-and-build-boundaries.zh-CN.md",
        "## 5.4 工程观察证据声明、继承与冻结基线【ENG-AUTO-BLD-004-REQ】",
        "# 6. ",
    )
    return _canonical_digest({"l2": l2, "l3": l3})


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def finalize(
    repository_root: Path,
    config_path: Path,
    soak_evidence_path: Path,
    junit_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    root = repository_root.resolve()
    require_repository_runtime(root)
    config_path = config_path.resolve()
    soak_evidence_path = soak_evidence_path.resolve()
    junit_path = junit_path.resolve()
    output_path = output_path.resolve()
    for path in (config_path, soak_evidence_path, junit_path, output_path):
        _repository_ref(root, path)

    soak = _load_json_object(soak_evidence_path)
    raw_evidence_digest = _verify_embedded_digest(soak)
    platform_checkpoint = select_platform_continuity_checkpoint(soak)
    junit = read_junit_summary(junit_path)
    settings = load_settings(config_path)
    source_identity = capture_product_runtime_source_identity(root, config_path=config_path)
    current_source_digest = f"sha256:{source_sha256_digest(source_identity)}"
    log_root = root / settings.maintenance.log_root
    app_starting = _latest_event(log_root / "app.jsonl", "runtime_starting")
    executor_ready = _latest_event(log_root / "executor.jsonl", "runtime_ready")
    operations_status = _operations_status(settings.app.port)

    current_checks = {
        "junit_passed": junit["failures"] == 0 and junit["errors"] == 0,
        "operations_http_200": operations_status == 200,
        "app_runtime_source_matches_current": app_starting is not None
        and app_starting.get("source_sha256_digest") == current_source_digest.removeprefix("sha256:"),
        "executor_runtime_source_matches_current": executor_ready is not None
        and executor_ready.get("source_sha256_digest") == current_source_digest.removeprefix("sha256:"),
        "executor_product_runtime_ready": executor_ready is not None
        and executor_ready.get("product_runtime_started") is True
        and executor_ready.get("startup_reconciliation_completed") is True
        and executor_ready.get("database_continuity_guard_completed") is True,
        "runtime_real_write_gate_closed": executor_ready is not None
        and executor_ready.get("runtime_real_write_gate") == "CLOSED",
        "runtime_proxy_value_not_observed": executor_ready is not None
        and "proxy_url" not in executor_ready,
    }
    status = "QUALIFIED" if all(current_checks.values()) else "REJECTED"
    observed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    report: dict[str, Any] = {
        "schema_version": 1,
        "qualification_scope": "B04_SUCCESSOR_CONSTRUCTION_ONLY",
        "status": status,
        "observed_at": observed_at,
        "decision_semantics": "POINT_IN_TIME_IMPACT_SCOPED_CONSTRUCTION_PERMISSION",
        "evaluator": {
            "version": EVALUATOR_VERSION,
            "code_ref": "tools/qualification/finalize_b04_construction_continuation.py",
        },
        "rule_reevaluation": {
            "prior_rule_identity": PRIOR_RULE_IDENTITY,
            "prior_rule_digest": _canonical_digest({"identity": PRIOR_RULE_IDENTITY}),
            "current_rule_identity": (
                "HALPHA-ENG-001@v1.9.0#ENG-OBS-001-REQ|"
                "HALPHA-ENG-002@v0.10.0#ENG-AUTO-BLD-004-REQ"
            ),
            "current_rule_digest": _current_rule_digest(root),
            "reevaluated_at": observed_at,
            "method": "REEVALUATE_RAW_EVIDENCE",
            "measurement_semantics_changed": False,
        },
        "platform_continuity_claim": {
            "claim": "SAME_BOOT_WINDOWS_AWAKE_PLATFORM_CONTINUITY_AT_LEAST_8H",
            "status": "QUALIFIED",
            **platform_checkpoint,
            "raw_evidence_ref": _repository_ref(root, soak_evidence_path),
            "raw_evidence_digest": raw_evidence_digest,
            "dependency_closure": "WINDOWS_UNBIASED_INTERRUPT_CLOCK_AND_SAME_BOOT_OBSERVATION",
            "direct_consumer": "B04_CONSTRUCTION_CONTINUATION_GATE",
            "does_not_claim": [
                "CURRENT_BUILD_PROCESS_CONTINUITY_8H",
                "CURRENT_BUILD_RELEASE_ELIGIBILITY",
                "REAL_CAPITAL_ELIGIBILITY",
            ],
        },
        "current_build_claim": {
            "claim": "CURRENT_BUILD_IMMEDIATE_TESTS_AND_STARTUP_SMOKE",
            "status": "QUALIFIED" if all(current_checks.values()) else "REJECTED",
            "commit_sha": _git_head(root),
            "product_runtime_source_digest": current_source_digest,
            "junit_ref": _repository_ref(root, junit_path),
            "junit_digest": _file_digest(junit_path),
            "junit": junit,
            "operations_http_status": operations_status,
            "checks": current_checks,
            "dependency_closure": (
                "CURRENT_PRODUCT_RUNTIME_SOURCE_CONFIG_APP_EXECUTOR_STARTUP_AND_TEST_SUITE"
            ),
            "direct_consumer": "B04_CONSTRUCTION_CONTINUATION_GATE",
        },
        "decision": {
            "required": [
                "PLATFORM_CONTINUITY_CLAIM_QUALIFIED",
                "CURRENT_BUILD_CLAIM_QUALIFIED",
                "RUNTIME_REAL_WRITE_GATE_CLOSED",
                "NO_UNISOLATED_CORE_DEFECT_IN_CURRENT_TEST_SCOPE",
            ],
            "permits": ["SEPARATELY_AUTHORIZED_SUCCESSOR_CONSTRUCTION"],
            "does_not_permit": [
                "B04_COMPLETE",
                "BUILD_MANIFEST_RELEASE_ELIGIBLE",
                "B05_REAL_CAPITAL_ACTIVATION",
                "RUNTIME_REAL_WRITE_GATE_OPEN",
            ],
        },
        "limitations": [
            "The inherited eight-hour claim covers Windows same-boot awake platform continuity only.",
            "It does not claim the current build ran continuously for eight hours.",
            "Current-build 72-hour and LIVE_READ_ONLY evidence must use a new exact committed baseline.",
            "Passing this decision does not separately authorize B05 construction.",
        ],
    }
    report["evidence_digest"] = _canonical_digest(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--soak-evidence", type=Path, default=DEFAULT_SOAK_EVIDENCE)
    parser.add_argument("--junit", type=Path, default=DEFAULT_JUNIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = finalize(
        args.repository_root,
        args.config,
        args.soak_evidence,
        args.junit,
        args.output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
