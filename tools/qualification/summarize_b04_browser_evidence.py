"""Aggregate B04 browser evidence without copying stable product semantics."""

from __future__ import annotations

import argparse
import base64
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse


EXACT_NODE = r"D:\Environment\node-v24.18.0-win-x64\node.exe"
EXPECTED_PLAYWRIGHT_VERSION = "1.61.1"
EXPECTED_TEST_MATRIX = {
    (
        "chromium-desktop",
        "B04 exposes unknown, protection gap, max loss, exit, takeover, closure and review without collapsing responsibility",
    ): "passed",
    (
        "chromium-desktop",
        "B04 rejects a stale control submission instead of applying a newer activation version",
    ): "passed",
    (
        "chromium-narrow",
        "B04 exposes unknown, protection gap, max loss, exit, takeover, closure and review without collapsing responsibility",
    ): "passed",
    (
        "chromium-narrow",
        "B04 rejects a stale control submission instead of applying a newer activation version",
    ): "skipped",
}
EXPECTED_CLI_SCREENSHOTS = {
    "output/playwright/b04-activation-gap-cli-1440x1000.png": (1440, 1000),
    "output/playwright/b04-operations-cli-1440x1000.png": (1440, 1000),
    "output/playwright/b04-operations-exit-preview-cli-1440x1000.png": (1440, 1000),
    "output/playwright/b04-operations-exit-preview-cli-390x844.png": (390, 844),
}


class B04BrowserSummaryError(RuntimeError):
    """Sanitized B04 browser evidence aggregation failure."""


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
        raise B04BrowserSummaryError(
            f"B04_BROWSER_JSON_INVALID file={path.name}"
        ) from None
    if not isinstance(value, dict):
        raise B04BrowserSummaryError(
            f"B04_BROWSER_JSON_ROOT_INVALID file={path.name}"
        )
    return value


def _attachment_bytes(attachment: dict[str, Any]) -> bytes:
    body = attachment.get("body")
    if not isinstance(body, str):
        raise B04BrowserSummaryError("B04_BROWSER_ATTACHMENT_BODY_MISSING")
    try:
        return base64.b64decode(body, validate=True)
    except Exception:
        raise B04BrowserSummaryError("B04_BROWSER_ATTACHMENT_BODY_INVALID") from None


def _attachment_json(attachment: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(_attachment_bytes(attachment).decode("utf-8"))
    except Exception:
        raise B04BrowserSummaryError("B04_BROWSER_ATTACHMENT_JSON_INVALID") from None
    if not isinstance(value, dict):
        raise B04BrowserSummaryError("B04_BROWSER_ATTACHMENT_JSON_ROOT_INVALID")
    return value


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise B04BrowserSummaryError("B04_BROWSER_SCREENSHOT_NOT_PNG")
    return struct.unpack(">II", data[16:24])


def _tests(suites: Iterable[dict[str, Any]]) -> Iterable[tuple[str, dict[str, Any]]]:
    for suite in suites:
        for spec in suite.get("specs", []):
            title = str(spec.get("title", ""))
            for test in spec.get("tests", []):
                yield title, test
        yield from _tests(suite.get("suites", []))


def _playwright_summary(
    report_path: Path,
    *,
    root: Path,
    screenshot_directory: Path,
) -> dict[str, Any]:
    report = _json(report_path)
    config = report.get("config", {})
    argv = config.get("argv", [])
    stats = report.get("stats", {})
    matrix: dict[tuple[str, str], str] = {}
    axe_attachment_count = 0
    axe_violation_count = 0
    layout_attachment_count = 0
    layout_failures = 0
    screenshot_attachments: list[dict[str, Any]] = []
    routes: set[str] = set()
    result_error_count = 0

    screenshot_directory.mkdir(parents=True, exist_ok=True)
    for title, test in _tests(report.get("suites", [])):
        project = str(test.get("projectName", ""))
        results = test.get("results", [])
        if len(results) != 1:
            raise B04BrowserSummaryError("B04_BROWSER_RESULT_CARDINALITY_INVALID")
        result = results[0]
        status = str(result.get("status", ""))
        matrix[(project, title)] = status
        result_error_count += len(result.get("errors", []))
        for attachment in result.get("attachments", []):
            name = str(attachment.get("name", ""))
            if name.endswith("-axe.json"):
                axe_attachment_count += 1
                value = _attachment_json(attachment)
                axe_violation_count += len(value.get("violations", []))
                url = value.get("url")
                if isinstance(url, str):
                    routes.add(urlparse(url).path)
            elif name == "b04-operations-layout.json":
                layout_attachment_count += 1
                value = _attachment_json(attachment)
                if (
                    value.get("scrollWidth") != value.get("clientWidth")
                    or value.get("offenders") != []
                ):
                    layout_failures += 1
            elif name == "b04-gap-unknown-max-loss.png":
                data = _attachment_bytes(attachment)
                width, height = _png_dimensions(data)
                target = screenshot_directory / f"{project}-{name}"
                target.write_bytes(data)
                screenshot_attachments.append(
                    {
                        "path": target.relative_to(root).as_posix(),
                        "sha256": sha256(data).hexdigest(),
                        "width": width,
                        "height": height,
                    }
                )

    qualified = (
        isinstance(argv, list)
        and bool(argv)
        and argv[0] == EXACT_NODE
        and config.get("version") == EXPECTED_PLAYWRIGHT_VERSION
        and stats.get("expected") == 3
        and stats.get("skipped") == 1
        and stats.get("unexpected") == 0
        and stats.get("flaky") == 0
        and matrix == EXPECTED_TEST_MATRIX
        and result_error_count == 0
        and axe_attachment_count == 9
        and axe_violation_count == 0
        and layout_attachment_count == 2
        and layout_failures == 0
        and len(screenshot_attachments) == 2
    )
    return {
        "path": report_path.relative_to(root).as_posix(),
        "sha256": _sha256_file(report_path),
        "node_executable": argv[0] if isinstance(argv, list) and argv else None,
        "playwright_version": config.get("version"),
        "stats": stats,
        "test_matrix": [
            {"project": project, "title": title, "status": status}
            for (project, title), status in sorted(matrix.items())
        ],
        "result_error_count": result_error_count,
        "axe_attachment_count": axe_attachment_count,
        "axe_violation_count": axe_violation_count,
        "layout_attachment_count": layout_attachment_count,
        "layout_failures": layout_failures,
        "routes": sorted(routes),
        "screenshot_attachments": screenshot_attachments,
        "status": "QUALIFIED" if qualified else "REJECTED",
    }


def _cli_review_summary(path: Path, *, root: Path) -> dict[str, Any]:
    review = _json(path)
    screenshots = review.get("screenshots")
    screenshot_results: list[dict[str, Any]] = []
    if not isinstance(screenshots, list) or not all(
        isinstance(item, dict) for item in screenshots
    ):
        raise B04BrowserSummaryError("B04_BROWSER_CLI_SCREENSHOTS_INVALID")
    screenshot_paths = {str(item.get("path")) for item in screenshots}
    for relative, expected_dimensions in EXPECTED_CLI_SCREENSHOTS.items():
        screenshot = root / relative
        data = screenshot.read_bytes()
        dimensions = _png_dimensions(data)
        screenshot_results.append(
            {
                "path": relative,
                "sha256": sha256(data).hexdigest(),
                "width": dimensions[0],
                "height": dimensions[1],
                "status": (
                    "QUALIFIED"
                    if dimensions == expected_dimensions
                    else "REJECTED"
                ),
            }
        )

    signals = review.get("runtime_signals", {})
    layout = review.get("narrow_layout", {})
    advisories = review.get("verbose_advisories", [])
    qualified = (
        review.get("review_status") == "REVIEWED"
        and review.get("base_url") == "http://127.0.0.1:8875"
        and review.get("profile") == "B04_BROWSER_FIXTURE"
        and review.get("browser") == "chrome-headless"
        and review.get("real_write_gate") == "CLOSED"
        and review.get("product_pids_unchanged") is True
        and review.get("fixture_rows_cleaned") is True
        and review.get("critical_visual_findings") == []
        and review.get("high_visual_findings") == []
        and signals
        == {
            "console_errors": 0,
            "console_warnings": 0,
            "failed_requests": 0,
            "page_errors": 0,
        }
        and layout
        == {
            "client_width": 390,
            "scroll_width": 390,
            "viewport_height": 844,
        }
        and screenshot_paths == set(EXPECTED_CLI_SCREENSHOTS)
        and all(item["status"] == "QUALIFIED" for item in screenshot_results)
        and isinstance(advisories, list)
        and all(
            isinstance(item, dict)
            and item.get("disposition") == "ACCEPTED_NON_BLOCKING"
            for item in advisories
        )
    )
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_file(path),
        "observed_at": review.get("observed_at"),
        "routes": review.get("routes"),
        "states": review.get("states"),
        "runtime_signals": signals,
        "narrow_layout": layout,
        "verbose_advisories": advisories,
        "screenshots": screenshot_results,
        "status": "QUALIFIED" if qualified else "REJECTED",
    }


def summarize(
    root: Path,
    *,
    report_path: Path,
    cli_review_path: Path,
    screenshot_directory: Path,
) -> dict[str, Any]:
    playwright = _playwright_summary(
        report_path,
        root=root,
        screenshot_directory=screenshot_directory,
    )
    cli_review = _cli_review_summary(cli_review_path, root=root)
    current_revision = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    sources = {
        relative: _sha256_file(root / relative)
        for relative in (
            "tools/qualification/run_b04_browser_fixture.py",
            "frontend/playwright.config.ts",
            "frontend/e2e/b04-workbench.spec.ts",
        )
    }
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_revision": current_revision,
        "workflow_run_id": None,
        "workflow_conclusion": "NOT_RUN_UNCOMMITTED",
        "superseded_by": None,
        "playwright": playwright,
        "cli_review": cli_review,
        "source_sha256": sources,
        "scope": "B04_DETERMINISTIC_BROWSER_FIXTURE_NO_VENUE_NETWORK_OR_LIVE_WRITE",
    }
    evidence["status"] = (
        "QUALIFIED"
        if playwright["status"] == "QUALIFIED"
        and cli_review["status"] == "QUALIFIED"
        else "REJECTED"
    )
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cli-review", type=Path, required=True)
    parser.add_argument("--screenshot-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    paths = {
        "report": args.report.resolve(),
        "cli_review": args.cli_review.resolve(),
        "screenshot_directory": args.screenshot_directory.resolve(),
        "output": args.output.resolve(),
    }
    if any(not path.is_relative_to(root) for path in paths.values()):
        raise B04BrowserSummaryError("B04_BROWSER_OUTPUT_OUTSIDE_REPOSITORY")
    evidence = summarize(
        root,
        report_path=paths["report"],
        cli_review_path=paths["cli_review"],
        screenshot_directory=paths["screenshot_directory"],
    )
    output = paths["output"]
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
