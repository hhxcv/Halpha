from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from halpha.codex.report_postprocess import (
    inject_derivatives_market_section,
    inject_macro_calendar_section,
    inject_onchain_flow_section,
    inject_quant_strategy_table,
    inject_strategy_effectiveness_table,
)
from halpha.runtime.pipeline_contracts import PipelineError, RunContext


STAGE_NAME = "run_codex_report"
CODEX_PROMPT_ARTIFACT = "codex_context/prompt.md"
REPORT_ARTIFACT = "report/report.md"
STDERR_SUMMARY_LIMIT = 1000


def run_codex_report(config: dict[str, Any], run: RunContext) -> list[str]:
    codex = config.get("codex", {})
    if not codex.get("enabled"):
        run.manifest["codex"]["status"] = "disabled"
        return []

    prompt = _read_prompt(run)
    command = _command_for_subprocess(codex)
    timeout = codex["timeout_seconds"]

    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            cwd=run.run_dir,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_summary = _stderr_summary(exc.stderr)
        _record_codex_failure(run, exit_code=None, stderr_summary=stderr_summary)
        raise PipelineError(
            f"Codex command timed out after {timeout} seconds.",
            stage=STAGE_NAME,
            exit_code=124,
            error_details=_error_details(exit_code=None, stderr_summary=stderr_summary),
        ) from exc
    except FileNotFoundError as exc:
        _record_codex_failure(run, exit_code=None, stderr_summary=None)
        raise PipelineError(
            f"Codex command was not found: {codex['command']}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except OSError as exc:
        _record_codex_failure(run, exit_code=None, stderr_summary=None)
        raise PipelineError(
            f"Codex command could not be started: {exc}.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    stderr_summary = _stderr_summary(completed.stderr)
    run.manifest["codex"]["exit_code"] = completed.returncode
    if stderr_summary:
        run.manifest["codex"]["stderr_summary"] = stderr_summary

    if completed.returncode != 0:
        raise PipelineError(
            f"Codex command failed with exit code {completed.returncode}.",
            stage=STAGE_NAME,
            exit_code=completed.returncode,
            error_details=_error_details(
                exit_code=completed.returncode,
                stderr_summary=stderr_summary,
            ),
        )

    report_error = _report_validation_error(completed.stdout)
    if report_error:
        raise PipelineError(
            report_error,
            stage=STAGE_NAME,
            exit_code=1,
            error_details=_error_details(exit_code=completed.returncode, stderr_summary=stderr_summary),
        )

    report = inject_derivatives_market_section(completed.stdout, run)
    report = inject_macro_calendar_section(report, run)
    report = inject_onchain_flow_section(report, run)
    report = inject_quant_strategy_table(report, run)
    report = inject_strategy_effectiveness_table(report, run)
    report_path = run.report_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    run.manifest["artifacts"]["report"] = REPORT_ARTIFACT
    return [REPORT_ARTIFACT]


def _read_prompt(run: RunContext) -> str:
    path = run.codex_context_dir / "prompt.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{CODEX_PROMPT_ARTIFACT} was not found; build_codex_context must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc


def _command_for_subprocess(codex: dict[str, Any]) -> list[str]:
    executable = codex["command"]
    resolved = shutil.which(executable) or executable
    return [resolved, *codex["args"]]


def _record_codex_failure(
    run: RunContext,
    *,
    exit_code: int | None,
    stderr_summary: str | None,
) -> None:
    run.manifest["codex"]["exit_code"] = exit_code
    if stderr_summary:
        run.manifest["codex"]["stderr_summary"] = stderr_summary


def _error_details(*, exit_code: int | None, stderr_summary: str | None) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if exit_code is not None:
        details["exit_code"] = exit_code
    if stderr_summary:
        details["stderr_summary"] = stderr_summary
    return details


def _stderr_summary(value: str | bytes | None) -> str | None:
    text = _to_text(value)
    if not text:
        return None

    lines = [" ".join(line.strip().split()) for line in text.splitlines() if line.strip()]
    summary = _redact_secrets("\n".join(lines))
    if not summary:
        return None
    if len(summary) > STDERR_SUMMARY_LIMIT:
        return f"{summary[: STDERR_SUMMARY_LIMIT - 3].rstrip()}..."
    return summary


def _report_validation_error(report: str) -> str | None:
    if not report.strip():
        return "Codex stdout was empty; report/report.md was not written."
    if not report.lstrip().startswith("#"):
        return "Codex stdout did not start with a Markdown heading; report/report.md was not written."
    if "风险" not in report:
        return "Codex stdout did not include a risk section; report/report.md was not written."
    return None


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _redact_secrets(text: str) -> str:
    replacements = [
        (r"sk-[A-Za-z0-9_-]+", "sk-[REDACTED]"),
        (r"gh[pousr]_[A-Za-z0-9_]+", "gh[REDACTED]"),
        (r"github_pat_[A-Za-z0-9_]+", "github_pat_[REDACTED]"),
        (r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]"),
        (r"(?i)((?:api[_-]?key|token|password)=)[^\s]+", r"\1[REDACTED]"),
    ]
    redacted = text
    for pattern, replacement in replacements:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted
