from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import json
from json import JSONDecodeError
from pathlib import Path
import sqlite3
from typing import Any

from .monitoring import (
    ALERT_ARCHIVE_STATE_FILENAME,
    MONITOR_HEALTH_STATE_FILENAME,
    load_monitor_config,
)
from .run_index import RUN_INDEX_ARTIFACT, run_index_path
from .storage import display_path, ensure_directory, write_json


DEFAULT_WORKBENCH_OUTPUT_DIR = "runs/workbench/latest"
WORKBENCH_SUMMARY_FILENAME = "workbench_summary.json"
WORKBENCH_MARKDOWN_FILENAME = "index.md"
WORKBENCH_HTML_FILENAME = "index.html"
WORKBENCH_SUMMARY_ARTIFACT = f"{DEFAULT_WORKBENCH_OUTPUT_DIR}/{WORKBENCH_SUMMARY_FILENAME}"
STRATEGY_LIFECYCLE_STATE_ARTIFACT = "analysis/strategy_lifecycle_state.json"
STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT = "analysis/strategy_lifecycle_material.md"
PRODUCT_CONTRACT_VALIDATION_ARTIFACT = "analysis/product_contract_validation.json"
EXTERNAL_ARTIFACT_REF = "<external-artifact>"


@dataclass(frozen=True)
class WorkbenchSummaryResult:
    summary_path: Path
    summary: dict[str, Any]


@dataclass(frozen=True)
class WorkbenchInspectionResult:
    succeeded: bool
    exit_code: int
    lines: list[str]


@dataclass(frozen=True)
class _RunSelection:
    mode: str
    status: str
    run_dir: Path | None
    run_id: str | None
    source_artifact: str | None
    reason: str | None
    selection_key: str | None = None
    selection_label: str | None = None


def build_workbench_summary(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_dir: Path | None = None,
    now: datetime | None = None,
) -> WorkbenchSummaryResult:
    base = _config_base(config_path)
    output_dir = _workbench_output_dir(config, config_path=config_path)
    ensure_directory(output_dir)
    generated_at = _utc_timestamp(now)
    selection = _select_run(config_path, run_dir=run_dir, base=base)

    warnings: list[str] = []
    errors: list[str] = []
    if selection.reason:
        warnings.append(selection.reason)

    manifest: dict[str, Any] = {}
    manifest_error: str | None = None
    if selection.run_dir is not None:
        manifest, manifest_error = _read_json(selection.run_dir / "run_manifest.json")
        if manifest_error:
            errors.append(f"run_manifest.json could not be inspected: {manifest_error}")

    latest_run = _latest_run_state(selection, manifest, manifest_error, base=base)
    decision_state = _decision_state(selection, manifest)
    alert_state = _alert_state(config, selection, manifest, base=base)
    monitor_state = _monitor_state(config, config_path=config_path, base=base)
    outcome_state = _outcome_state(config_path, selection, manifest, base=base)
    strategy_state = _strategy_state(selection, manifest)
    product_validation_state = _product_validation_state(selection, manifest)
    data_quality_state = _data_quality_state(selection, manifest)
    sections = [
        latest_run,
        decision_state,
        alert_state,
        monitor_state,
        outcome_state,
        strategy_state,
        product_validation_state,
        data_quality_state,
    ]

    for section in sections:
        warnings.extend(str(item) for item in _list(section.get("warnings")))
        errors.extend(str(item) for item in _list(section.get("errors")))

    summary_path = output_dir / WORKBENCH_SUMMARY_FILENAME
    markdown_path = output_dir / WORKBENCH_MARKDOWN_FILENAME
    html_path = output_dir / WORKBENCH_HTML_FILENAME
    summary = {
        "schema_version": 1,
        "artifact_type": "workbench_summary",
        "generated_at": generated_at,
        "status": _overall_status([str(section.get("status") or "missing") for section in sections]),
        "source_selection": {
            "mode": selection.mode,
            "status": selection.status,
            "run_id": selection.run_id,
            "run_dir": _portable_path(selection.run_dir, base=base) if selection.run_dir else None,
            "source_artifact": selection.source_artifact,
            "reason": selection.reason,
            "selection_key": selection.selection_key,
            "selection_label": selection.selection_label,
        },
        "latest_run": latest_run,
        "decision_state": decision_state,
        "alert_state": alert_state,
        "monitor_state": monitor_state,
        "outcome_state": outcome_state,
        "strategy_state": strategy_state,
        "product_validation_state": product_validation_state,
        "data_quality_state": data_quality_state,
        "index_outputs": {
            "status": "available",
            "markdown": _portable_path(markdown_path, base=base),
            "html": _portable_path(html_path, base=base),
        },
        "source_artifacts": _source_artifacts(selection, manifest, base=base),
        "omitted": {
            "raw_record_dumps_embedded": False,
            "full_intermediate_json_embedded": False,
            "full_run_manifest_embedded": False,
            "raw_local_user_state_embedded": False,
        },
        "codex_boundary": {
            "codex_input_by_default": False,
            "llm_generated_workbench_state": False,
        },
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
    }
    write_json(summary_path, summary)
    markdown_path.write_text(render_workbench_markdown(summary), encoding="utf-8")
    html_path.write_text(render_workbench_html(summary), encoding="utf-8")
    return WorkbenchSummaryResult(summary_path=summary_path, summary=summary)


def render_workbench_markdown(summary: dict[str, Any]) -> str:
    latest_fields = _section_fields(summary, "latest_run")
    report = _dict(latest_fields.get("report"))
    lines = [
        "# Halpha Workbench",
        "",
        f"- Status: `{summary.get('status') or 'unknown'}`",
        f"- Generated at: `{summary.get('generated_at') or 'unknown'}`",
        f"- Latest run: `{latest_fields.get('run_id') or 'none'}`",
        f"- Latest run status: `{latest_fields.get('run_status') or 'unknown'}`",
        f"- Report: {_markdown_artifact_link(summary, report.get('artifact'))} ({report.get('status') or 'unknown'})",
        "",
        "## Current State",
        "",
        "| Area | Status | Key Counts |",
        "| --- | --- | --- |",
        _markdown_state_row(
            "Decision and watch",
            summary,
            "decision_state",
            {
                "decision_records": "decisions",
                "watch_trigger_records": "watch triggers",
                "risk_blocked_decision_records": "risk blocked",
            },
        ),
        _markdown_state_row(
            "Alerts",
            summary,
            "alert_state",
            {
                "alert_decision_records": "alert decisions",
                "alert_decision_attention_records": "attention records",
            },
        ),
        _markdown_state_row(
            "Monitor",
            summary,
            "monitor_state",
            {
                "cycle_count": "cycles",
                "failed_cycle_count": "failed cycles",
                "cooldown_records": "cooldowns",
            },
        ),
        _markdown_state_row(
            "Outcomes",
            summary,
            "outcome_state",
            {
                "evaluation_records": "evaluations",
                "evaluated_records": "evaluated",
                "pending_records": "pending",
            },
        ),
        _markdown_state_row(
            "Strategy",
            summary,
            "strategy_state",
            {
                "strategy_gate_effective": "effective",
                "strategy_gate_watchlisted": "watchlisted",
                "strategy_gate_rejected": "rejected",
                "strategy_lifecycle_records": "lifecycle records",
                "strategy_lifecycle_degraded": "degraded lifecycle",
                "strategy_lifecycle_retired": "retired lifecycle",
            },
        ),
        _markdown_state_row(
            "Product validation",
            summary,
            "product_validation_state",
            {
                "checks": "checks",
                "warning": "warnings",
                "degraded": "degraded",
                "failed": "failed checks",
            },
        ),
        _markdown_state_row(
            "Data quality",
            summary,
            "data_quality_state",
            {
                "checks": "checks",
                "warnings": "warnings",
                "failed_checks": "failed checks",
            },
        ),
        "",
        "## Source Artifacts",
        "",
        *_markdown_source_artifacts(summary),
        "",
        "## Warnings",
        "",
        *_markdown_messages(summary.get("warnings")),
        "",
        "## Errors",
        "",
        *_markdown_messages(summary.get("errors")),
        "",
    ]
    return "\n".join(lines)


def render_workbench_html(summary: dict[str, Any]) -> str:
    latest_fields = _section_fields(summary, "latest_run")
    report = _dict(latest_fields.get("report"))
    rows = "\n".join(
        [
            _html_state_row(
                "Decision and watch",
                summary,
                "decision_state",
                {
                    "decision_records": "decisions",
                    "watch_trigger_records": "watch triggers",
                    "risk_blocked_decision_records": "risk blocked",
                },
            ),
            _html_state_row(
                "Alerts",
                summary,
                "alert_state",
                {
                    "alert_decision_records": "alert decisions",
                    "alert_decision_attention_records": "attention records",
                },
            ),
            _html_state_row(
                "Monitor",
                summary,
                "monitor_state",
                {
                    "cycle_count": "cycles",
                    "failed_cycle_count": "failed cycles",
                    "cooldown_records": "cooldowns",
                },
            ),
            _html_state_row(
                "Outcomes",
                summary,
                "outcome_state",
                {
                    "evaluation_records": "evaluations",
                    "evaluated_records": "evaluated",
                    "pending_records": "pending",
                },
            ),
            _html_state_row(
                "Strategy",
                summary,
                "strategy_state",
                {
                    "strategy_gate_effective": "effective",
                    "strategy_gate_watchlisted": "watchlisted",
                    "strategy_gate_rejected": "rejected",
                    "strategy_lifecycle_records": "lifecycle records",
                    "strategy_lifecycle_degraded": "degraded lifecycle",
                    "strategy_lifecycle_retired": "retired lifecycle",
                },
            ),
            _html_state_row(
                "Product validation",
                summary,
                "product_validation_state",
                {
                    "checks": "checks",
                    "warning": "warnings",
                    "degraded": "degraded",
                    "failed": "failed checks",
                },
            ),
            _html_state_row(
                "Data quality",
                summary,
                "data_quality_state",
                {
                    "checks": "checks",
                    "warnings": "warnings",
                    "failed_checks": "failed checks",
                },
            ),
        ]
    )
    sources = "\n".join(_html_source_artifacts(summary))
    warnings = "\n".join(_html_messages(summary.get("warnings")))
    errors = "\n".join(_html_messages(summary.get("errors")))
    report_link = _html_artifact_link(summary, report.get("artifact"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Halpha Workbench</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; line-height: 1.5; color: #1f2933; }}
    h1, h2 {{ color: #102a43; }}
    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f0f4f8; }}
    code {{ background: #f0f4f8; padding: 1px 4px; }}
    .meta {{ color: #52606d; }}
  </style>
</head>
<body>
  <h1>Halpha Workbench</h1>
  <p class="meta">Status: <code>{escape(str(summary.get("status") or "unknown"))}</code></p>
  <p class="meta">Generated at: <code>{escape(str(summary.get("generated_at") or "unknown"))}</code></p>
  <section>
    <h2>Latest Run</h2>
    <ul>
      <li>Run id: <code>{escape(str(latest_fields.get("run_id") or "none"))}</code></li>
      <li>Run status: <code>{escape(str(latest_fields.get("run_status") or "unknown"))}</code></li>
      <li>Report: {report_link} ({escape(str(report.get("status") or "unknown"))})</li>
    </ul>
  </section>
  <section>
    <h2>Current State</h2>
    <table>
      <thead><tr><th>Area</th><th>Status</th><th>Key Counts</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </section>
  <section>
    <h2>Source Artifacts</h2>
{sources}
  </section>
  <section>
    <h2>Warnings</h2>
{warnings}
  </section>
  <section>
    <h2>Errors</h2>
{errors}
  </section>
</body>
</html>
"""


def inspect_workbench_summary(config: dict[str, Any], *, config_path: Path) -> WorkbenchInspectionResult:
    base = _config_base(config_path)
    summary_path = _workbench_output_dir(config, config_path=config_path) / WORKBENCH_SUMMARY_FILENAME
    summary, error = _read_json(summary_path)
    summary_ref = _portable_path(summary_path, base=base)
    if error:
        status = "missing" if "was not found" in error else "failed"
        lines = [
            "Halpha workbench inspection succeeded." if status == "missing" else "Halpha workbench inspection failed.",
            f"status: {status}",
            f"summary: {summary_ref}",
            f"reason: {error}",
        ]
        return WorkbenchInspectionResult(status == "missing", 0 if status == "missing" else 3, lines)

    latest_fields = _dict(_dict(summary.get("latest_run")).get("fields"))
    latest_report = _dict(latest_fields.get("report"))
    decision_fields = _dict(_dict(summary.get("decision_state")).get("fields"))
    alert_fields = _dict(_dict(summary.get("alert_state")).get("fields"))
    monitor_fields = _dict(_dict(summary.get("monitor_state")).get("fields"))
    outcome_fields = _dict(_dict(summary.get("outcome_state")).get("fields"))
    strategy_fields = _dict(_dict(summary.get("strategy_state")).get("fields"))
    product_validation_fields = _dict(_dict(summary.get("product_validation_state")).get("fields"))
    quality_fields = _dict(_dict(summary.get("data_quality_state")).get("fields"))
    lines = [
        "Halpha workbench inspection succeeded.",
        f"status: {summary.get('status') or 'unknown'}",
        f"summary: {summary_ref}",
        f"latest_run_id: {latest_fields.get('run_id') or 'none'}",
        f"latest_run_status: {latest_fields.get('run_status') or 'unknown'}",
        f"latest_run_source: {latest_fields.get('selection_key') or 'none'}",
        f"report: {latest_report.get('artifact') or 'none'}",
        f"report_status: {latest_report.get('status') or 'unknown'}",
        f"decision_state: {_section_status_text(summary, 'decision_state')}",
        f"decision_records: {_int(decision_fields.get('decision_records'))}",
        f"watch_trigger_records: {_int(decision_fields.get('watch_trigger_records'))}",
        f"alert_state: {_section_status_text(summary, 'alert_state')}",
        f"alert_decision_records: {_int(alert_fields.get('alert_decision_records'))}",
        f"monitor_state: {_section_status_text(summary, 'monitor_state')}",
        f"monitor_cycle_count: {_int(monitor_fields.get('cycle_count'))}",
        f"outcome_state: {_section_status_text(summary, 'outcome_state')}",
        f"outcome_evaluation_records: {_int(outcome_fields.get('evaluation_records'))}",
        f"strategy_state: {_section_status_text(summary, 'strategy_state')}",
        f"strategy_gate_effective: {_int(strategy_fields.get('strategy_gate_effective'))}",
        f"strategy_lifecycle_state_status: {strategy_fields.get('strategy_lifecycle_state_status') or 'missing'}",
        f"strategy_lifecycle_records: {_int(strategy_fields.get('strategy_lifecycle_records'))}",
        f"strategy_lifecycle_degraded: {_int(strategy_fields.get('strategy_lifecycle_degraded'))}",
        f"strategy_lifecycle_retired: {_int(strategy_fields.get('strategy_lifecycle_retired'))}",
        f"product_validation_state: {_section_status_text(summary, 'product_validation_state')}",
        f"product_validation_checks: {_int(product_validation_fields.get('checks'))}",
        f"product_validation_warnings: {_int(product_validation_fields.get('warning'))}",
        f"product_validation_degraded: {_int(product_validation_fields.get('degraded'))}",
        f"product_validation_failed: {_int(product_validation_fields.get('failed'))}",
        f"data_quality_state: {_section_status_text(summary, 'data_quality_state')}",
        f"data_quality_warnings: {_int(quality_fields.get('warnings'))}",
        f"warning_count: {len(_list(summary.get('warnings')))}",
        f"error_count: {len(_list(summary.get('errors')))}",
    ]
    return WorkbenchInspectionResult(True, 0, lines)


def _section_fields(summary: dict[str, Any], key: str) -> dict[str, Any]:
    return _dict(_dict(summary.get(key)).get("fields"))


def _markdown_state_row(
    label: str,
    summary: dict[str, Any],
    key: str,
    count_labels: dict[str, str],
) -> str:
    status = _section_status_text(summary, key)
    counts = _count_text(_section_fields(summary, key), count_labels)
    return f"| {_markdown_escape(label)} | `{_markdown_escape(status)}` | {_markdown_escape(counts)} |"


def _html_state_row(
    label: str,
    summary: dict[str, Any],
    key: str,
    count_labels: dict[str, str],
) -> str:
    status = _section_status_text(summary, key)
    counts = _count_text(_section_fields(summary, key), count_labels)
    return (
        "        <tr>"
        f"<td>{escape(label)}</td>"
        f"<td><code>{escape(status)}</code></td>"
        f"<td>{escape(counts)}</td>"
        "</tr>"
    )


def _count_text(fields: dict[str, Any], count_labels: dict[str, str]) -> str:
    parts = [f"{label}: {_int(fields.get(key))}" for key, label in count_labels.items()]
    return ", ".join(parts) if parts else "none"


def _markdown_source_artifacts(summary: dict[str, Any]) -> list[str]:
    source_artifacts = _dict(summary.get("source_artifacts"))
    lines: list[str] = []
    run_manifest = source_artifacts.get("run_manifest")
    if isinstance(run_manifest, str) and run_manifest:
        lines.append(f"- run_manifest: {_markdown_artifact_link(summary, run_manifest)}")
    report = source_artifacts.get("report")
    if isinstance(report, str) and report:
        lines.append(f"- report: {_markdown_artifact_link(summary, report)}")
    for group in ("analysis", "raw", "shared_data", "other"):
        entries = _dict(source_artifacts.get(group))
        for key, ref in sorted(entries.items()):
            if isinstance(ref, str) and ref:
                lines.append(f"- {group}.{_markdown_escape(str(key))}: {_markdown_artifact_link(summary, ref)}")
    return lines or ["- none"]


def _html_source_artifacts(summary: dict[str, Any]) -> list[str]:
    source_artifacts = _dict(summary.get("source_artifacts"))
    items: list[str] = []
    run_manifest = source_artifacts.get("run_manifest")
    if isinstance(run_manifest, str) and run_manifest:
        items.append(f"<li>run_manifest: {_html_artifact_link(summary, run_manifest)}</li>")
    report = source_artifacts.get("report")
    if isinstance(report, str) and report:
        items.append(f"<li>report: {_html_artifact_link(summary, report)}</li>")
    for group in ("analysis", "raw", "shared_data", "other"):
        entries = _dict(source_artifacts.get(group))
        for key, ref in sorted(entries.items()):
            if isinstance(ref, str) and ref:
                label = escape(f"{group}.{key}")
                items.append(f"<li>{label}: {_html_artifact_link(summary, ref)}</li>")
    if not items:
        return ["  <p>none</p>"]
    return ["  <ul>", *[f"    {item}" for item in items], "  </ul>"]


def _markdown_messages(value: Any) -> list[str]:
    messages = [str(item) for item in _list(value) if item]
    return [f"- {_markdown_escape(item)}" for item in messages] if messages else ["- none"]


def _html_messages(value: Any) -> list[str]:
    messages = [str(item) for item in _list(value) if item]
    if not messages:
        return ["  <p>none</p>"]
    return ["  <ul>", *[f"    <li>{escape(item)}</li>" for item in messages], "  </ul>"]


def _markdown_artifact_link(summary: dict[str, Any], ref: Any) -> str:
    if not isinstance(ref, str) or not ref:
        return "`none`"
    target = _index_relative_target(summary, ref)
    return f"[`{_markdown_escape(ref)}`]({_markdown_escape(target)})"


def _html_artifact_link(summary: dict[str, Any], ref: Any) -> str:
    if not isinstance(ref, str) or not ref:
        return "<code>none</code>"
    target = _index_relative_target(summary, ref)
    return f'<a href="{escape(target, quote=True)}"><code>{escape(ref)}</code></a>'


def _index_relative_target(summary: dict[str, Any], ref: str) -> str:
    repo_ref = _repo_relative_artifact_ref(summary, ref)
    if repo_ref.startswith("runs/"):
        return "../../" + repo_ref.removeprefix("runs/")
    return "../../../" + repo_ref


def _repo_relative_artifact_ref(summary: dict[str, Any], ref: str) -> str:
    if ref.startswith(("runs/", "data/")):
        return ref
    if ref.startswith(("analysis/", "raw/", "report/", "codex_context/")):
        run_dir = _dict(summary.get("source_selection")).get("run_dir")
        if isinstance(run_dir, str) and run_dir:
            return f"{run_dir.rstrip('/')}/{ref}"
    return ref


def _markdown_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("]", "\\]")


def _select_run(config_path: Path, *, run_dir: Path | None, base: Path) -> _RunSelection:
    if run_dir is not None:
        resolved = _resolve_path(run_dir, base=base)
        if not resolved.exists():
            return _RunSelection(
                mode="explicit_run",
                status="missing",
                run_dir=None,
                run_id=None,
                source_artifact=None,
                reason="requested run directory was not found.",
            )
        if not resolved.is_dir():
            return _RunSelection(
                mode="explicit_run",
                status="failed",
                run_dir=None,
                run_id=None,
                source_artifact=None,
                reason="requested run path is not a directory.",
            )
        return _RunSelection(
            mode="explicit_run",
            status="available",
            run_dir=resolved,
            run_id=resolved.name,
            source_artifact=None,
            reason=None,
        )

    index_path = run_index_path(config_path)
    if not index_path.exists():
        return _RunSelection(
            mode="latest_run_index",
            status="missing",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason="local run index was not found.",
        )
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            row = _latest_run_row(connection)
    except sqlite3.Error as exc:
        return _RunSelection(
            mode="latest_run_index",
            status="failed",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason=f"{RUN_INDEX_ARTIFACT} is not readable: {exc}",
        )
    if row is None:
        return _RunSelection(
            mode="latest_run_index",
            status="missing",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason="local run index does not contain a latest run.",
        )
    selection_key, selected_run_id, selected_run_dir = row
    path = Path(selected_run_dir)
    if not path.is_absolute():
        path = base / path
    if _project_local_path(path, base=base) is None:
        return _RunSelection(
            mode="latest_run_index",
            status="failed",
            run_dir=None,
            run_id=selected_run_id,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason="local run index points outside the configured project root.",
            selection_key=selection_key,
            selection_label=_latest_selection_label(selection_key),
        )
    return _RunSelection(
        mode="latest_run_index",
        status="available",
        run_dir=path,
        run_id=selected_run_id,
        source_artifact=RUN_INDEX_ARTIFACT,
        reason=None,
        selection_key=selection_key,
        selection_label=_latest_selection_label(selection_key),
    )


def _latest_run_row(connection: sqlite3.Connection) -> tuple[str, str, str] | None:
    for key in ("latest_successful_run", "latest_run"):
        row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
        if not row or not isinstance(row[0], str) or not row[0]:
            continue
        run = connection.execute("SELECT run_id, run_dir FROM runs WHERE run_id = ?", (row[0],)).fetchone()
        if run and isinstance(run[0], str) and isinstance(run[1], str):
            return key, run[0], run[1]
    return None


def _latest_selection_label(selection_key: str) -> str:
    if selection_key == "latest_successful_run":
        return "latest successful run"
    if selection_key == "latest_run":
        return "latest indexed run"
    return selection_key


def _latest_run_state(
    selection: _RunSelection,
    manifest: dict[str, Any],
    manifest_error: str | None,
    *,
    base: Path,
) -> dict[str, Any]:
    if selection.run_dir is None:
        return _section("missing", reason=selection.reason)
    manifest_ref = _portable_path(selection.run_dir / "run_manifest.json", base=base)
    if manifest_error:
        return _section("failed", artifact=manifest_ref, errors=[manifest_error])
    report_ref = _report_artifact_ref(manifest)
    report_status = _file_ref_status(selection.run_dir, report_ref, default_ref="report/report.md")
    return _section(
        "available",
        artifact=manifest_ref,
        fields={
            "run_id": manifest.get("run_id") or selection.run_id,
            "run_status": manifest.get("status") or "unknown",
            "started_at": manifest.get("started_at"),
            "finished_at": manifest.get("finished_at"),
            "codex_status": _dict(manifest.get("codex")).get("status"),
            "report": report_status,
            "selection_key": selection.selection_key,
            "selection_label": selection.selection_label,
        },
    )


def _decision_state(selection: _RunSelection, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _manifest_artifact_refs(
        manifest,
        {
            "risk_assessment": "analysis/risk_assessment.json",
            "decision_recommendations": "analysis/decision_recommendations.json",
            "watch_triggers": "analysis/watch_triggers.json",
        },
    )
    if selection.run_dir is None:
        return _section("missing", source_artifacts=refs, reason="no selected run.")
    artifacts = _artifact_statuses(selection.run_dir, refs)
    counts = _dict(manifest.get("counts"))
    return _section(
        _section_status(artifacts),
        source_artifacts=refs,
        fields={
            "risk_records": _int(counts.get("risk_assessment_records")),
            "high_or_extreme_risk_records": _int(counts.get("risk_assessment_high_or_extreme_records")),
            "blocking_risk_records": _int(counts.get("risk_assessment_blocking_records")),
            "decision_records": _int(counts.get("decision_recommendation_records")),
            "actionable_decision_records": _int(counts.get("decision_recommendation_actionable_records")),
            "risk_blocked_decision_records": _int(counts.get("decision_recommendation_risk_blocked_records")),
            "watch_trigger_records": _int(counts.get("watch_trigger_records")),
        },
        details={"artifacts": artifacts},
        warnings=_artifact_warnings(artifacts),
        errors=_artifact_errors(artifacts),
    )


def _alert_state(config: dict[str, Any], selection: _RunSelection, manifest: dict[str, Any], *, base: Path) -> dict[str, Any]:
    refs = _manifest_artifact_refs(manifest, {"alert_decisions": "analysis/alert_decisions.json"})
    artifacts = _artifact_statuses(selection.run_dir, refs) if selection.run_dir is not None else []
    settings = load_monitor_config(config)
    monitor_dir = _resolve_path(settings.output_dir, base=base)
    archive_state_ref = _portable_path(monitor_dir / ALERT_ARCHIVE_STATE_FILENAME, base=base)
    archive_state, archive_error = _read_json(monitor_dir / ALERT_ARCHIVE_STATE_FILENAME)
    archive_status = _json_status(archive_state, archive_error)
    counts = _dict(manifest.get("counts"))
    fields = {
        "alert_decision_records": _int(counts.get("alert_decision_records")),
        "alert_decision_attention_records": _int(counts.get("alert_decision_attention_records")),
        "archive_state": {
            "status": archive_status,
            "artifact": archive_state_ref,
            "counts": _dict(archive_state.get("counts")),
        },
    }
    status_inputs = [item["status"] for item in artifacts] + [archive_status]
    return _section(
        _overall_status(status_inputs),
        source_artifacts={**refs, "alert_archive_state": archive_state_ref},
        fields=fields,
        details={"artifacts": artifacts},
        warnings=[*_artifact_warnings(artifacts), *([archive_error] if archive_error and archive_status == "missing" else [])],
        errors=[*_artifact_errors(artifacts), *([archive_error] if archive_error and archive_status == "failed" else [])],
    )


def _monitor_state(config: dict[str, Any], *, config_path: Path, base: Path) -> dict[str, Any]:
    settings = load_monitor_config(config)
    monitor_dir = _resolve_path(settings.output_dir, base=base)
    health_ref = _portable_path(monitor_dir / MONITOR_HEALTH_STATE_FILENAME, base=base)
    health, error = _read_json(monitor_dir / MONITOR_HEALTH_STATE_FILENAME)
    status = _json_status(health, error)
    fields = {
        "monitor_output_dir": _portable_path(monitor_dir, base=base),
        "health_state": health_ref,
        "cycle_count": _int(health.get("cycle_count")),
        "failed_cycle_count": _int(health.get("failed_cycle_count")),
        "latest_cycle_id": health.get("latest_cycle_id"),
        "latest_cycle_status": health.get("latest_cycle_status"),
        "latest_run_id": health.get("latest_run_id"),
        "latest_run_manifest": health.get("latest_run_manifest"),
        "alert_archive_status": health.get("alert_archive_status"),
        "alert_counts": _dict(health.get("alert_counts")),
        "cooldown_records": _int(health.get("cooldown_records")),
        "warning_count": _int(health.get("warning_count")),
        "error_count": _int(health.get("error_count")),
    }
    return _section(
        status,
        artifact=health_ref,
        fields=fields,
        warnings=[error] if error and status == "missing" else [],
        errors=[error] if error and status == "failed" else [],
    )


def _outcome_state(
    config_path: Path,
    selection: _RunSelection,
    manifest: dict[str, Any],
    *,
    base: Path,
) -> dict[str, Any]:
    refs = _manifest_artifact_refs(
        manifest,
        {
            "outcome_targets": "analysis/outcome_targets.json",
            "outcome_evaluations": "analysis/outcome_evaluations.json",
        },
    )
    history_state_ref = "data/research/metadata/outcome_history_state.json"
    history_state, history_error = _read_json(base / history_state_ref)
    history_status = _json_status(history_state, history_error)
    artifacts = _artifact_statuses(selection.run_dir, refs) if selection.run_dir is not None else []
    counts = _dict(manifest.get("counts"))
    status_inputs = [item["status"] for item in artifacts] + [history_status]
    return _section(
        _overall_status(status_inputs),
        source_artifacts={**refs, "outcome_history_state": history_state_ref},
        fields={
            "target_records": _int(counts.get("outcome_targets")),
            "evaluation_records": _int(counts.get("outcome_evaluations")),
            "evaluated_records": _int(counts.get("outcome_evaluations_evaluated")),
            "pending_records": _int(counts.get("outcome_evaluations_pending")),
            "insufficient_data_records": _int(counts.get("outcome_evaluations_insufficient_data")),
            "history_records": _int(_dict(history_state.get("totals")).get("records")),
        },
        details={"artifacts": artifacts},
        warnings=[*_artifact_warnings(artifacts), *([history_error] if history_error and history_status == "missing" else [])],
        errors=[*_artifact_errors(artifacts), *([history_error] if history_error and history_status == "failed" else [])],
    )


def _strategy_state(selection: _RunSelection, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _manifest_artifact_refs(
        manifest,
        {
            "strategy_evaluation_summary": "analysis/strategy_evaluation_summary.json",
            "strategy_experiment": "analysis/strategy_experiment.json",
            "strategy_effectiveness_gates": "analysis/strategy_effectiveness_gates.json",
        },
    )
    lifecycle_refs = _manifest_artifact_refs(
        manifest,
        {
            "strategy_lifecycle_state": STRATEGY_LIFECYCLE_STATE_ARTIFACT,
            "strategy_lifecycle_material": STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT,
        },
    )
    if selection.run_dir is None:
        return _section("missing", source_artifacts={**refs, **lifecycle_refs}, reason="no selected run.")
    artifacts = _artifact_statuses(selection.run_dir, refs)
    lifecycle_artifacts = _artifact_statuses(selection.run_dir, lifecycle_refs)
    counts = _dict(manifest.get("counts"))
    has_lifecycle = _has_strategy_lifecycle_artifacts(
        _dict(manifest.get("artifacts")),
        counts,
        _dict(manifest.get("strategy_lifecycle_state")),
        _dict(manifest.get("strategy_lifecycle_material")),
    )
    visible_artifacts = [*artifacts, *lifecycle_artifacts] if has_lifecycle else artifacts
    lifecycle_status_fields = _lifecycle_artifact_status_fields(lifecycle_artifacts)
    return _section(
        _section_status(visible_artifacts),
        source_artifacts={**refs, **lifecycle_refs},
        fields={
            "strategy_evaluation_records": _int(counts.get("strategy_evaluation_records")),
            "strategy_evaluation_succeeded": _int(counts.get("strategy_evaluation_succeeded")),
            "strategy_gate_candidates": _int(counts.get("strategy_gate_candidates")),
            "strategy_gate_effective": _int(counts.get("strategy_gate_effective")),
            "strategy_gate_watchlisted": _int(counts.get("strategy_gate_watchlisted")),
            "strategy_gate_rejected": _int(counts.get("strategy_gate_rejected")),
            "strategy_gate_insufficient_evidence": _int(counts.get("strategy_gate_insufficient_evidence")),
            "strategy_lifecycle_records": _int(counts.get("strategy_lifecycle_records")),
            "strategy_lifecycle_effective": _int(counts.get("strategy_lifecycle_effective")),
            "strategy_lifecycle_active_candidate": _int(counts.get("strategy_lifecycle_active_candidate")),
            "strategy_lifecycle_watchlisted": _int(counts.get("strategy_lifecycle_watchlisted")),
            "strategy_lifecycle_rejected": _int(counts.get("strategy_lifecycle_rejected")),
            "strategy_lifecycle_degraded": _int(counts.get("strategy_lifecycle_degraded")),
            "strategy_lifecycle_retired": _int(counts.get("strategy_lifecycle_retired")),
            "strategy_lifecycle_insufficient_evidence": _int(counts.get("strategy_lifecycle_insufficient_evidence")),
            "strategy_lifecycle_failed": _int(counts.get("strategy_lifecycle_failed")),
            "strategy_lifecycle_policy_records": _int(counts.get("strategy_lifecycle_policy_records")),
            "strategy_lifecycle_warnings": _int(counts.get("strategy_lifecycle_warnings")),
            "strategy_lifecycle_errors": _int(counts.get("strategy_lifecycle_errors")),
            **lifecycle_status_fields,
        },
        details={"artifacts": visible_artifacts},
        warnings=_artifact_warnings(visible_artifacts),
        errors=_artifact_errors(visible_artifacts),
    )


def _data_quality_state(selection: _RunSelection, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _manifest_artifact_refs(manifest, {"data_quality_summary": "analysis/data_quality_summary.json"})
    if selection.run_dir is None:
        return _section("missing", source_artifacts=refs, reason="no selected run.")
    artifacts = _artifact_statuses(selection.run_dir, refs)
    counts = _dict(manifest.get("counts"))
    return _section(
        _section_status(artifacts),
        source_artifacts=refs,
        fields={
            "checks": _int(counts.get("data_quality_checks")),
            "warnings": _int(counts.get("data_quality_warnings")),
            "errors": _int(counts.get("data_quality_errors")),
            "degraded_checks": _int(counts.get("data_quality_degraded_checks")),
            "failed_checks": _int(counts.get("data_quality_failed_checks")),
        },
        details={"artifacts": artifacts},
        warnings=_artifact_warnings(artifacts),
        errors=_artifact_errors(artifacts),
    )


def _product_validation_state(selection: _RunSelection, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _manifest_artifact_refs(
        manifest,
        {"product_contract_validation": PRODUCT_CONTRACT_VALIDATION_ARTIFACT},
    )
    if selection.run_dir is None:
        return _section("missing", source_artifacts=refs, reason="no selected run.")
    artifacts = _artifact_statuses(selection.run_dir, refs)
    validation_ref = refs["product_contract_validation"]
    validation, _ = _read_json(selection.run_dir / validation_ref)
    counts = _dict(validation.get("counts"))
    source_refs = _bounded_source_refs(validation.get("source_artifacts"))
    fields = {
        "validation_status": validation.get("status") or _artifact_source_status(artifacts),
        "checks": _int(counts.get("checks")),
        "ok": _int(counts.get("ok")),
        "warning": _int(counts.get("warning")),
        "degraded": _int(counts.get("degraded")),
        "failed": _int(counts.get("failed")),
        "skipped": _int(counts.get("skipped")),
        "errors": _int(counts.get("errors")),
        "warnings": _int(counts.get("warnings")),
        "source_artifact_refs": source_refs["refs"],
        "source_artifact_refs_omitted": source_refs["omitted"],
    }
    return _section(
        _section_status(artifacts),
        source_artifacts=refs,
        fields=fields,
        details={"artifacts": artifacts},
        warnings=_artifact_warnings(artifacts),
        errors=_artifact_errors(artifacts),
    )


def _manifest_artifact_refs(manifest: dict[str, Any], defaults: dict[str, str]) -> dict[str, str]:
    manifest_refs = _dict(manifest.get("artifacts"))
    refs: dict[str, str] = {}
    for key, default in defaults.items():
        value = manifest_refs.get(key)
        refs[key] = value if isinstance(value, str) and value else default
    return refs


def _has_strategy_lifecycle_artifacts(
    artifacts: dict[str, Any],
    counts: dict[str, Any],
    lifecycle_summary: dict[str, Any],
    material_summary: dict[str, Any],
) -> bool:
    if artifacts.get("strategy_lifecycle_state") or artifacts.get("strategy_lifecycle_material"):
        return True
    if lifecycle_summary or material_summary:
        return True
    return any(str(key).startswith("strategy_lifecycle_") for key in counts)


def _lifecycle_artifact_status_fields(artifacts: list[dict[str, Any]]) -> dict[str, str]:
    statuses = {item.get("name"): item.get("status") for item in artifacts}
    return {
        "strategy_lifecycle_state_status": str(statuses.get("strategy_lifecycle_state") or "missing"),
        "strategy_lifecycle_material_status": str(statuses.get("strategy_lifecycle_material") or "missing"),
    }


def _artifact_source_status(artifacts: list[dict[str, Any]]) -> str:
    if not artifacts:
        return "missing"
    value = artifacts[0].get("source_status") or artifacts[0].get("status")
    return str(value or "unknown")


def _artifact_statuses(run_dir: Path | None, refs: dict[str, str]) -> list[dict[str, Any]]:
    if run_dir is None:
        return [
            {
                "name": key,
                "artifact": ref,
                "status": "missing",
                "reason": "no selected run.",
            }
            for key, ref in refs.items()
        ]
    statuses = []
    for key, ref in sorted(refs.items()):
        if not ref.endswith(".json"):
            path = run_dir / ref
            status = "available" if path.is_file() else "missing"
            item: dict[str, Any] = {
                "name": key,
                "artifact": ref,
                "status": status,
            }
            if status == "missing":
                item["reason"] = f"{path.name} was not found."
            statuses.append(item)
            continue
        artifact, error = _read_json(run_dir / ref)
        status = _json_status(artifact, error)
        item: dict[str, Any] = {
            "name": key,
            "artifact": ref,
            "status": status,
        }
        if artifact:
            item["artifact_type"] = artifact.get("artifact_type")
            item["source_status"] = artifact.get("status")
            item["counts"] = _dict(artifact.get("counts"))
            item["warning_count"] = len(_list(artifact.get("warnings")))
            item["error_count"] = len(_list(artifact.get("errors")))
        if error:
            item["reason"] = error
        statuses.append(item)
    return statuses


def _artifact_warnings(artifacts: list[dict[str, Any]]) -> list[str]:
    return [
        f"{item['artifact']} {item['reason']}"
        for item in artifacts
        if item.get("status") in {"missing", "partial", "stale", "degraded", "skipped"}
        and isinstance(item.get("artifact"), str)
        and isinstance(item.get("reason"), str)
    ]


def _artifact_errors(artifacts: list[dict[str, Any]]) -> list[str]:
    return [
        f"{item['artifact']} {item['reason']}"
        for item in artifacts
        if item.get("status") == "failed"
        and isinstance(item.get("artifact"), str)
        and isinstance(item.get("reason"), str)
    ]


def _source_artifacts(selection: _RunSelection, manifest: dict[str, Any], *, base: Path) -> dict[str, Any]:
    if selection.run_dir is None:
        return {}
    refs = {
        key: value
        for key, value in sorted(_dict(manifest.get("artifacts")).items())
        if isinstance(value, str) and value
    }
    return {
        "run_manifest": _portable_path(selection.run_dir / "run_manifest.json", base=base),
        "report": refs.get("report"),
        "analysis": {key: value for key, value in refs.items() if value.startswith("analysis/")},
        "raw": {key: value for key, value in refs.items() if value.startswith("raw/")},
        "shared_data": {key: value for key, value in refs.items() if value.startswith("data/")},
        "other": {
            key: value
            for key, value in refs.items()
            if not value.startswith(("analysis/", "raw/", "data/")) and key != "report"
        },
    }


def _bounded_source_refs(value: Any, *, limit: int = 12) -> dict[str, Any]:
    refs = [str(item) for item in _list(value) if isinstance(item, str) and item]
    return {
        "refs": refs[:limit],
        "omitted": max(0, len(refs) - limit),
    }


def _report_artifact_ref(manifest: dict[str, Any]) -> str | None:
    artifacts = _dict(manifest.get("artifacts"))
    value = artifacts.get("report")
    return value if isinstance(value, str) and value else None


def _file_ref_status(run_dir: Path, ref: str | None, *, default_ref: str) -> dict[str, Any]:
    artifact_ref = ref or default_ref
    exists = (run_dir / artifact_ref).is_file()
    return {
        "status": "available" if exists else "missing",
        "artifact": artifact_ref,
    }


def _section(
    status: str,
    *,
    artifact: str | None = None,
    source_artifacts: dict[str, str] | None = None,
    reason: str | None = None,
    fields: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "artifact": artifact,
        "source_artifacts": source_artifacts or {},
        "reason": reason,
        "fields": fields or {},
        "details": details or {},
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _section_status(artifacts: list[dict[str, Any]]) -> str:
    if not artifacts:
        return "missing"
    return _overall_status([str(item.get("status") or "missing") for item in artifacts])


def _section_status_text(summary: dict[str, Any], key: str) -> str:
    section = _dict(summary.get(key))
    return str(section.get("status") or "unknown")


def _overall_status(statuses: list[str]) -> str:
    cleaned = [status for status in statuses if status]
    if not cleaned:
        return "missing"
    if "failed" in cleaned:
        return "failed"
    if "degraded" in cleaned:
        return "degraded"
    if "partial" in cleaned:
        return "partial"
    if "missing" in cleaned:
        return "missing" if set(cleaned) == {"missing"} else "partial"
    if "stale" in cleaned:
        return "stale"
    if "skipped" in cleaned:
        return "skipped" if set(cleaned) == {"skipped"} else "partial"
    if "not_applicable" in cleaned:
        return "not_applicable" if set(cleaned) == {"not_applicable"} else "partial"
    return "available"


def _json_status(data: dict[str, Any], error: str | None) -> str:
    if error:
        if "was not found" in error:
            return "missing"
        return "failed"
    source_status = str(data.get("status") or "").lower()
    if source_status in {"failed", "degraded", "partial", "stale", "skipped", "not_applicable"}:
        return source_status
    if source_status in {"warning", "unknown"}:
        return "partial"
    return "available"


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except OSError as exc:
        return {}, f"{path.name} could not be read: {exc}."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _workbench_output_dir(config: dict[str, Any], *, config_path: Path) -> Path:
    _ = config
    path = Path(DEFAULT_WORKBENCH_OUTPUT_DIR)
    if path.is_absolute():
        return path
    return _config_base(config_path) / path


def _resolve_path(path: Path, *, base: Path) -> Path:
    return path if path.is_absolute() else base / path


def _portable_path(path: Path, *, base: Path) -> str:
    try:
        path.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return EXTERNAL_ARTIFACT_REF
    return display_path(path, base=base)


def _project_local_path(path: Path, *, base: Path) -> Path | None:
    try:
        path.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return path


def _config_base(config_path: Path) -> Path:
    parent = config_path.parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _dedupe(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})
