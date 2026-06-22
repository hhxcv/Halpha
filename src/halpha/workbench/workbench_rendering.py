from __future__ import annotations

from html import escape
from typing import Any

from halpha.utils.value_helpers import as_dict as _dict, as_list as _list, strict_int as _int


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


def _section_status_text(summary: dict[str, Any], key: str) -> str:
    section = _dict(summary.get(key))
    return str(section.get("status") or "missing")
