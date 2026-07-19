"""Summarize non-normative B01 qualification artifacts without copying design."""

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


EXACT_NODE = r"D:\Environment\node-v24.18.0-win-x64\node.exe"


class B01SummaryError(RuntimeError):
    """Sanitized B01 evidence aggregation failure."""


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
        raise B01SummaryError(f"B01_EVIDENCE_JSON_INVALID file={path.name}") from None
    if not isinstance(value, dict):
        raise B01SummaryError(f"B01_EVIDENCE_JSON_ROOT_INVALID file={path.name}")
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


def _playwright_tests(suites: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for suite in suites:
        for spec in suite.get("specs", []):
            yield from spec.get("tests", [])
        yield from _playwright_tests(suite.get("suites", []))


def _playwright_summary(path: Path) -> dict[str, Any]:
    report = _json(path)
    stats = report.get("stats", {})
    argv = report.get("config", {}).get("argv", [])
    tests = list(_playwright_tests(report.get("suites", [])))
    axe_attachment_count = 0
    axe_violation_count = 0
    result_statuses: list[str] = []
    for test in tests:
        for result in test.get("results", []):
            result_statuses.append(str(result.get("status")))
            for attachment in result.get("attachments", []):
                if not str(attachment.get("name", "")).endswith("-axe.json"):
                    continue
                axe_attachment_count += 1
                body = attachment.get("body")
                if not isinstance(body, str):
                    raise B01SummaryError("B01_PLAYWRIGHT_AXE_BODY_MISSING")
                payload = json.loads(base64.b64decode(body).decode("utf-8"))
                axe_violation_count += len(payload.get("violations", []))
    return {
        "report_sha256": _sha256_file(path),
        "node_executable": argv[0] if argv else None,
        "expected": int(stats.get("expected", -1)),
        "unexpected": int(stats.get("unexpected", -1)),
        "result_statuses": result_statuses,
        "axe_attachment_count": axe_attachment_count,
        "axe_violation_count": axe_violation_count,
        "status": (
            "QUALIFIED"
            if argv and argv[0] == EXACT_NODE
            and stats.get("expected") == 2
            and stats.get("unexpected") == 0
            and result_statuses == ["passed", "passed"]
            and axe_attachment_count == 6
            and axe_violation_count == 0
            else "REJECTED"
        ),
    }


def _pytest_summary(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    if suite is None:
        raise B01SummaryError("B01_PYTEST_JUNIT_SUITE_MISSING")
    values = {
        key: int(suite.attrib.get(key, "-1"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    return {
        **values,
        "report_sha256": _sha256_file(path),
        "status": (
            "QUALIFIED"
            if values == {"tests": 87, "failures": 0, "errors": 0, "skipped": 0}
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


def summarize(root: Path) -> dict[str, Any]:
    qualification = root / "build" / "qualification"
    artifact_paths = {
        "clean_venv": qualification / "b01-clean-venv.json",
        "database_boundary": qualification / "b01-database-boundary.json",
        "windows_runtime": qualification / "b01-windows-runtime.json",
        "backup_boundary": qualification / "b01-backup-boundary.json",
        "license_inventory": qualification / "b01-license-inventory.json",
    }
    artifacts: dict[str, Any] = {}
    for name, path in artifact_paths.items():
        report = _json(path)
        artifacts[name] = {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256_file(path),
            "reported_evidence_digest": report.get("evidence_digest"),
            "status": report.get("status"),
        }
    pytest_report = _pytest_summary(qualification / "b01-pytest.xml")
    vitest_report = _vitest_summary(
        qualification / "browser" / "vitest-report.json"
    )
    playwright_report = _playwright_summary(
        qualification / "browser" / "playwright-report.json"
    )
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
        "tests": {
            "pytest": pytest_report,
            "vitest": vitest_report,
            "playwright": playwright_report,
        },
        "mechanical_gates": mechanical_gates,
        "build_manifest_expectation": {
            "completeness": "COMPLETE",
            "build_eligible": False,
            "reason": "CURRENT_WORKTREE_UNCOMMITTED",
        },
        "scope": "B01_IMPLEMENTATION_ONLY_NOT_REAL_WRITE_AUTHORIZATION",
    }
    qualified = (
        all(item["status"] == "QUALIFIED" for item in artifacts.values())
        and all(item["status"] == "QUALIFIED" for item in evidence["tests"].values())
        and all(code == 0 for code in mechanical_gates.values())
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
        raise B01SummaryError("B01_SUMMARY_OUTPUT_OUTSIDE_REPOSITORY")
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
