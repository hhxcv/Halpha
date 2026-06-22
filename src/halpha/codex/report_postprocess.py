from __future__ import annotations

import json
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext


STAGE_NAME = "run_codex_report"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
STRATEGY_EFFECTIVENESS_GATES_ARTIFACT = "analysis/strategy_effectiveness_gates.json"
DERIVATIVES_MARKET_CONTEXT_ARTIFACT = "analysis/derivatives_market_context.json"
DERIVATIVES_MARKET_MATERIAL_ARTIFACT = "analysis/derivatives_market_material.md"
MACRO_CALENDAR_CONTEXT_ARTIFACT = "analysis/macro_calendar_context.json"
MACRO_CALENDAR_MATERIAL_ARTIFACT = "analysis/macro_calendar_material.md"
ONCHAIN_FLOW_CONTEXT_ARTIFACT = "analysis/onchain_flow_context.json"
ONCHAIN_FLOW_MATERIAL_ARTIFACT = "analysis/onchain_flow_material.md"
MAX_DERIVATIVES_REPORT_ROWS = 8
MAX_MACRO_CALENDAR_REPORT_ROWS = 8
MAX_ONCHAIN_FLOW_REPORT_ROWS = 8


def inject_derivatives_market_section(report: str, run: RunContext) -> str:
    table = _derivatives_market_markdown_table(run)
    if table is None:
        return report
    section = "\n".join(
        [
            "## \u884d\u751f\u54c1\u4e0e\u5e02\u573a\u7ed3\u6784\u8bc1\u636e",
            "",
            (
                "\u4ee5\u4e0b\u5185\u5bb9\u6765\u81ea "
                f"`{DERIVATIVES_MARKET_MATERIAL_ARTIFACT}` "
                "\u548c Halpha \u786e\u5b9a\u6027\u4e0a\u4e0b\u6587\uff1b"
                "\u53ea\u7528\u4e8e\u89e3\u91ca\uff0c\u4e0d\u751f\u6210\u98ce\u9669\u7b49\u7ea7\u3001"
                "\u4ea4\u6613\u6307\u4ee4\u3001\u4ed3\u4f4d\u5efa\u8bae\u6216\u4ef7\u683c\u9884\u6d4b\u3002"
            ),
            "",
            table,
            "",
        ]
    )
    return _insert_report_section(report, section)


def inject_macro_calendar_section(report: str, run: RunContext) -> str:
    table = _macro_calendar_markdown_table(run)
    if table is None:
        return report
    section = "\n".join(
        [
            "## \u5b8f\u89c2\u65e5\u5386\u4e0e\u8c03\u5ea6\u98ce\u9669\u8bc1\u636e",
            "",
            (
                "\u4ee5\u4e0b\u5185\u5bb9\u6765\u81ea "
                f"`{MACRO_CALENDAR_MATERIAL_ARTIFACT}` "
                "\u548c Halpha \u786e\u5b9a\u6027\u5b8f\u89c2\u65e5\u5386\u4e0a\u4e0b\u6587\uff1b"
                "\u8ba1\u5212\u4e2d\u50ac\u5316\u5242\u4ec5\u4ee3\u8868\u65f6\u70b9\u548c\u4e0d\u786e\u5b9a\u6027\uff0c"
                "\u4e0d\u4ee3\u8868\u5df2\u786e\u8ba4\u7684\u5e02\u573a\u5f71\u54cd\u3001"
                "\u98ce\u9669\u7b49\u7ea7\u3001\u4ea4\u6613\u6307\u4ee4\u6216\u4ef7\u683c\u9884\u6d4b\u3002"
            ),
            "",
            table,
            "",
        ]
    )
    return _insert_report_section(report, section)


def inject_onchain_flow_section(report: str, run: RunContext) -> str:
    table = _onchain_flow_markdown_table(run)
    if table is None:
        return report
    section = "\n".join(
        [
            "## \u94fe\u4e0a\u6d41\u4e0e\u6765\u6e90\u53ef\u7528\u6027\u8bc1\u636e",
            "",
            (
                "\u4ee5\u4e0b\u5185\u5bb9\u6765\u81ea "
                f"`{ONCHAIN_FLOW_MATERIAL_ARTIFACT}` "
                "\u548c Halpha \u786e\u5b9a\u6027\u94fe\u4e0a\u6d41\u4e0a\u4e0b\u6587\uff1b"
                "\u53ea\u7528\u4e8e\u89e3\u91ca\u6d41\u52a8\u6027\u3001\u4f7f\u7528\u5ea6\u3001"
                "\u7f51\u7edc\u62e5\u5835\u548c\u6765\u6e90\u4e0d\u786e\u5b9a\u6027\uff0c"
                "\u4e0d\u751f\u6210\u94fe\u4e0a\u8bb0\u5f55\u3001\u5730\u5740\u6807\u7b7e\u3001"
                "\u98ce\u9669\u7b49\u7ea7\u3001\u4ea4\u6613\u6307\u4ee4\u6216\u4ef7\u683c\u9884\u6d4b\u3002"
            ),
            "",
            table,
            "",
        ]
    )
    return _insert_report_section(report, section)


def inject_quant_strategy_table(report: str, run: RunContext) -> str:
    table = _quant_strategy_markdown_table(run)
    if table is None:
        return report
    section = "\n".join(
        [
            "## 量化策略输出表",
            "",
            table,
            "",
        ]
    )
    return _insert_report_section(report, section)


def _macro_calendar_markdown_table(run: RunContext) -> str | None:
    material_path = run.analysis_dir / "macro_calendar_material.md"
    if not material_path.exists():
        return None
    artifact = _read_macro_calendar_context(run)
    records = artifact.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} must contain records as a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    rows = [_macro_calendar_report_row(record) for record in _selected_macro_calendar_records(records)]
    if not rows:
        rows = [
            [
                "\u65e0\u53ef\u7528\u8bb0\u5f55",
                "",
                "",
                "",
                _text(artifact.get("status")),
                "not_evaluated",
                "\u5b8f\u89c2\u65e5\u5386 material \u5b58\u5728\uff0c\u4f46\u672a\u63d0\u4f9b\u53ef\u62a5\u544a\u7684 context record\u3002",
                MACRO_CALENDAR_MATERIAL_ARTIFACT,
            ]
        ]
    header = [
        "\u7c7b\u578b",
        "\u4e8b\u4ef6",
        "\u533a\u57df",
        "\u65f6\u95f4",
        "\u72b6\u6001",
        "\u5b9e\u9645\u5f71\u54cd",
        "\u89e3\u91ca\u53e3\u5f84",
        "\u6765\u6e90",
    ]
    lines = [
        _markdown_row(header),
        _markdown_row(["---"] * len(header)),
    ]
    for row in rows:
        lines.append(_markdown_row(row))
    return "\n".join(lines)


def _derivatives_market_markdown_table(run: RunContext) -> str | None:
    material_path = run.analysis_dir / "derivatives_market_material.md"
    if not material_path.exists():
        return None
    artifact = _read_derivatives_market_context(run)
    records = artifact.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} must contain records as a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    rows = [_derivatives_report_row(record) for record in _selected_derivatives_records(records)]
    if not rows:
        rows = [
            [
                "\u65e0\u53ef\u7528\u8bb0\u5f55",
                "",
                "",
                _text(artifact.get("status")),
                "",
                "\u884d\u751f\u54c1 material \u5b58\u5728\uff0c\u4f46\u672a\u63d0\u4f9b\u53ef\u62a5\u544a\u7684 context record\u3002",
                DERIVATIVES_MARKET_MATERIAL_ARTIFACT,
            ]
        ]
    header = [
        "\u7c7b\u578b",
        "\u6807\u7684",
        "\u5468\u671f",
        "\u72b6\u6001",
        "\u5f3a\u5ea6",
        "\u89e3\u91ca\u53e3\u5f84",
        "\u6765\u6e90",
    ]
    lines = [
        _markdown_row(header),
        _markdown_row(["---"] * len(header)),
    ]
    for row in rows:
        lines.append(_markdown_row(row))
    return "\n".join(lines)


def _onchain_flow_markdown_table(run: RunContext) -> str | None:
    material_path = run.analysis_dir / "onchain_flow_material.md"
    if not material_path.exists():
        return None
    artifact = _read_onchain_flow_context(run)
    records = artifact.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} must contain records as a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    rows = [_onchain_flow_report_row(record) for record in _selected_onchain_flow_records(records)]
    if not rows:
        rows = [
            [
                "\u65e0\u53ef\u7528\u8bb0\u5f55",
                "",
                "",
                _text(artifact.get("status")),
                "",
                "\u94fe\u4e0a\u6d41 material \u5b58\u5728\uff0c\u4f46\u672a\u63d0\u4f9b\u53ef\u62a5\u544a\u7684 context record\u3002",
                ONCHAIN_FLOW_MATERIAL_ARTIFACT,
            ]
        ]
    header = [
        "\u7c7b\u578b",
        "\u6807\u7684/\u94fe",
        "\u65f6\u95f4",
        "\u72b6\u6001",
        "\u5f3a\u5ea6",
        "\u89e3\u91ca\u53e3\u5f84",
        "\u6765\u6e90",
    ]
    lines = [
        _markdown_row(header),
        _markdown_row(["---"] * len(header)),
    ]
    for row in rows:
        lines.append(_markdown_row(row))
    return "\n".join(lines)


def _read_macro_calendar_context(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "macro_calendar_context.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} was not found but macro calendar material exists.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} must be a mapping.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _read_derivatives_market_context(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "derivatives_market_context.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} was not found but derivatives material exists.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} must be a mapping.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _read_onchain_flow_context(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "onchain_flow_context.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} was not found but on-chain flow material exists.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} must be a mapping.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _selected_macro_calendar_records(records: list[Any]) -> list[dict[str, Any]]:
    mappings = [record for record in records if isinstance(record, dict)]
    return sorted(mappings, key=_macro_calendar_record_sort_key)[:MAX_MACRO_CALENDAR_REPORT_ROWS]


def _selected_derivatives_records(records: list[Any]) -> list[dict[str, Any]]:
    mappings = [record for record in records if isinstance(record, dict)]
    return sorted(mappings, key=_derivatives_record_sort_key)[:MAX_DERIVATIVES_REPORT_ROWS]


def _selected_onchain_flow_records(records: list[Any]) -> list[dict[str, Any]]:
    mappings = [record for record in records if isinstance(record, dict)]
    return sorted(mappings, key=_onchain_flow_record_sort_key)[:MAX_ONCHAIN_FLOW_REPORT_ROWS]


def _macro_calendar_record_sort_key(record: dict[str, Any]) -> tuple[int, int, int, float, str, str]:
    severity_order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    status_order = {
        "failed": 0,
        "unavailable": 1,
        "stale": 2,
        "degraded": 3,
        "partial": 4,
        "succeeded": 5,
        "no_event": 6,
    }
    type_order = {
        "scheduled_catalyst": 0,
        "recent_catalyst": 1,
        "source_availability": 2,
        "no_event_window": 3,
    }
    hours = record.get("time_to_event_hours")
    hours_value = abs(float(hours)) if isinstance(hours, int | float) else 999999.0
    severity = _text(record.get("severity")) or "unknown"
    status = _text(record.get("status")) or "unknown"
    context_type = _text(record.get("context_type")) or "unknown"
    return (
        severity_order.get(severity, 2),
        status_order.get(status, 7),
        type_order.get(context_type, 4),
        hours_value,
        _text(record.get("scheduled_at")),
        _text(record.get("context_id")),
    )


def _derivatives_record_sort_key(record: dict[str, Any]) -> tuple[int, int, str, str, str]:
    severity_order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    status_order = {
        "failed": 0,
        "unavailable": 1,
        "stale": 2,
        "degraded": 3,
        "partial": 4,
        "insufficient": 5,
        "succeeded": 6,
    }
    severity = _text(record.get("severity")) or "unknown"
    status = _text(record.get("status")) or "unknown"
    return (
        severity_order.get(severity, 2),
        status_order.get(status, 6),
        _text(record.get("context_type")),
        _text(record.get("symbol")),
        _text(record.get("period")),
    )


def _onchain_flow_record_sort_key(record: dict[str, Any]) -> tuple[int, int, int, str, str, str]:
    severity_order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    status_order = {
        "failed": 0,
        "unavailable": 1,
        "stale": 2,
        "degraded": 3,
        "partial": 4,
        "insufficient": 5,
        "bounded": 6,
        "succeeded": 7,
    }
    type_order = {
        "stablecoin_liquidity": 0,
        "network_congestion": 1,
        "chain_activity": 2,
        "exchange_flow_source_availability": 3,
    }
    severity = _text(record.get("severity")) or "unknown"
    status = _text(record.get("status")) or "unknown"
    context_type = _text(record.get("context_type")) or "unknown"
    return (
        severity_order.get(severity, 2),
        status_order.get(status, 8),
        type_order.get(context_type, 4),
        _text(record.get("asset")),
        _text(record.get("chain")),
        _text(record.get("context_id")),
    )


def _macro_calendar_report_row(record: dict[str, Any]) -> list[str]:
    return [
        _macro_calendar_type_label(record.get("context_type")),
        _text(record.get("event_name")) or "-",
        _text(record.get("region")),
        _text(record.get("scheduled_at")) or "-",
        _macro_calendar_status(record),
        _macro_calendar_realized_impact(record),
        _macro_calendar_interpretation(record),
        _macro_calendar_sources(record),
    ]


def _derivatives_report_row(record: dict[str, Any]) -> list[str]:
    return [
        _derivatives_type_label(record.get("context_type")),
        _text(record.get("symbol")),
        _text(record.get("period")),
        _derivatives_status(record),
        _text(record.get("severity")),
        _derivatives_interpretation(record),
        _derivatives_sources(record),
    ]


def _onchain_flow_report_row(record: dict[str, Any]) -> list[str]:
    target = "/".join(
        part for part in [_text(record.get("asset")), _text(record.get("chain"))] if part
    )
    return [
        _onchain_flow_type_label(record.get("context_type")),
        target,
        _text(record.get("as_of")) or "-",
        _onchain_flow_status(record),
        _text(record.get("severity")),
        _onchain_flow_interpretation(record),
        _onchain_flow_sources(record),
    ]


def _macro_calendar_type_label(value: Any) -> str:
    labels = {
        "scheduled_catalyst": "\u8ba1\u5212\u4e2d\u50ac\u5316\u5242",
        "recent_catalyst": "\u8fd1\u671f\u50ac\u5316\u5242",
        "no_event_window": "\u65e0\u4e8b\u4ef6\u7a97\u53e3",
        "source_availability": "\u6765\u6e90\u53ef\u7528\u6027",
    }
    return labels.get(value, _text(value))


def _derivatives_type_label(value: Any) -> str:
    labels = {
        "funding_pressure": "\u8d44\u91d1\u8d39\u7387\u538b\u529b",
        "open_interest_pressure": "\u672a\u5e73\u4ed3\u91cf\u538b\u529b",
        "premium_basis_state": "\u6ea2\u4ef7\u6216\u57fa\u5dee",
        "liquidity_depth_state": "\u4e70\u5356\u4ef7\u5dee\u4e0e\u6df1\u5ea6",
        "liquidation_availability": "\u5f3a\u5e73\u6765\u6e90\u53ef\u7528\u6027",
    }
    return labels.get(value, _text(value))


def _onchain_flow_type_label(value: Any) -> str:
    labels = {
        "stablecoin_liquidity": "\u7a33\u5b9a\u5e01\u6d41\u52a8\u6027",
        "chain_activity": "\u94fe\u4e0a\u6d3b\u52a8",
        "network_congestion": "\u7f51\u7edc\u62e5\u5835",
        "exchange_flow_source_availability": "\u4ea4\u6613\u6240\u6d41\u6765\u6e90\u53ef\u7528\u6027",
    }
    return labels.get(value, _text(value))


def _macro_calendar_status(record: dict[str, Any]) -> str:
    status = _text(record.get("status")) or "unknown"
    state = _text(record.get("state")) or "unknown"
    return f"{status}/{state}"


def _derivatives_status(record: dict[str, Any]) -> str:
    status = _text(record.get("status")) or "unknown"
    state = _text(record.get("state")) or "unknown"
    return f"{status}/{state}"


def _onchain_flow_status(record: dict[str, Any]) -> str:
    status = _text(record.get("status")) or "unknown"
    state = _text(record.get("state")) or "unknown"
    return f"{status}/{state}"


def _macro_calendar_realized_impact(record: dict[str, Any]) -> str:
    impact = record.get("realized_impact") if isinstance(record.get("realized_impact"), dict) else {}
    status = _text(impact.get("status")) or "not_evaluated"
    if status == "not_evaluated":
        return "not_evaluated; \u672a\u8bc4\u4f30\u5b9e\u9645\u5e02\u573a\u5f71\u54cd"
    return status


def _macro_calendar_interpretation(record: dict[str, Any]) -> str:
    context_type = _text(record.get("context_type")) or "unknown"
    status = _text(record.get("status")) or "unknown"
    state = _text(record.get("state")) or "unknown"
    if status in {"failed", "unavailable", "stale", "degraded", "partial"} or state in {
        "unavailable",
        "stale",
        "degraded",
        "partial",
        "failed",
    }:
        return (
            f"Halpha material \u6807\u8bb0\u4e3a {status}/{state}\uff1b"
            "\u8fd9\u662f\u6765\u6e90\u6216\u65f6\u6548\u4e0d\u786e\u5b9a\u6027\uff0c"
            "\u4e0d\u4ee3\u8868\u4f4e\u98ce\u9669\u3002"
        )
    if context_type == "scheduled_catalyst":
        return (
            "\u8ba1\u5212\u4e2d\u50ac\u5316\u5242\u53ea\u8868\u793a\u65f6\u70b9\u548c\u50ac\u5316\u5242\u98ce\u9669\uff1b"
            "\u4e0d\u7b49\u4e8e\u9884\u6d4b\uff0c\u4e5f\u4e0d\u7b49\u4e8e\u5df2\u786e\u8ba4\u7684\u5e02\u573a\u5f71\u54cd\u3002"
        )
    if context_type == "recent_catalyst":
        return (
            "\u8fd1\u671f\u50ac\u5316\u5242\u662f\u4e8b\u4ef6\u65f6\u70b9\u8bc1\u636e\uff1b"
            "\u4e0d\u786e\u8ba4\u5e02\u573a\u5df2\u53d1\u751f\u54cd\u5e94\u3002"
        )
    if context_type == "no_event_window":
        return (
            "\u65e0\u4e8b\u4ef6\u7a97\u53e3\u4e0d\u8bc1\u660e\u5b8f\u89c2\u98ce\u9669\u4e0d\u5b58\u5728\uff1b"
            "\u4ec5\u8bf4\u660e\u5f53\u524d\u7a97\u53e3\u672a\u8bb0\u5f55\u914d\u7f6e\u4e8b\u4ef6\u3002"
        )
    return (
        "\u4ec5\u6309 Halpha \u5df2\u751f\u6210\u7684\u5b8f\u89c2\u65e5\u5386 context \u89e3\u91ca\uff1b"
        "\u4e0d\u751f\u6210\u98ce\u9669\u7b49\u7ea7\u3001\u4ea4\u6613\u6307\u4ee4\u6216\u9884\u6d4b\u3002"
    )


def _derivatives_interpretation(record: dict[str, Any]) -> str:
    status = _text(record.get("status")) or "unknown"
    state = _text(record.get("state")) or "unknown"
    severity = _text(record.get("severity")) or "unknown"
    if status in {"failed", "unavailable", "stale", "degraded", "partial"} or state in {
        "unavailable",
        "stale",
        "insufficient_evidence",
    }:
        return (
            f"Halpha material \u6807\u8bb0\u4e3a {status}/{state}\uff1b"
            "\u8fd9\u662f\u6765\u6e90\u6216\u8d28\u91cf\u4e0d\u786e\u5b9a\u6027\uff0c"
            "\u4e0d\u4ee3\u8868\u4f4e\u98ce\u9669\u3002"
        )
    if severity in {"high", "medium"}:
        return (
            f"Halpha material \u663e\u793a {state}\uff1b"
            "\u53ea\u53ef\u5728\u4e0b\u6e38 Halpha \u4ea7\u7269\u94fe\u63a5\u65f6\u4f5c\u4e3a"
            "\u4fdd\u5b88\u786e\u8ba4\u6216\u51b2\u7a81\u7ebf\u7d22\u3002"
        )
    if state in {"neutral", "open_interest_level_only"} or severity == "low":
        return (
            f"Halpha material \u663e\u793a {state}\uff1b"
            "\u53ef\u4f5c\u4e3a no-impact \u8bc1\u636e\uff0c"
            "\u4f46\u4e0d\u5f97\u5355\u72ec\u964d\u4f4e\u5176\u4ed6\u98ce\u9669\u3002"
        )
    return (
        "\u4ec5\u6309 Halpha \u5df2\u751f\u6210\u7684\u884d\u751f\u54c1 context \u89e3\u91ca\uff1b"
        "\u4e0d\u751f\u6210\u4ea4\u6613\u6307\u4ee4\u6216\u9884\u6d4b\u3002"
    )


def _onchain_flow_interpretation(record: dict[str, Any]) -> str:
    status = _text(record.get("status")) or "unknown"
    state = _text(record.get("state")) or "unknown"
    context_type = _text(record.get("context_type")) or "unknown"
    severity = _text(record.get("severity")) or "unknown"
    if status in {"failed", "unavailable", "stale", "degraded", "partial", "insufficient"} or state in {
        "unavailable",
        "stale",
        "partial",
        "failed",
        "insufficient_evidence",
    }:
        return (
            f"Halpha material \u6807\u8bb0\u4e3a {status}/{state}\uff1b"
            "\u8fd9\u662f\u6765\u6e90\u3001\u65f6\u6548\u6216\u8bc1\u636e\u4e0d\u8db3\uff0c"
            "\u4e0d\u4ee3\u8868\u4f4e\u98ce\u9669\u3002"
        )
    if context_type == "stablecoin_liquidity":
        return (
            f"Halpha material \u663e\u793a {state}/{severity}\uff1b"
            "\u4ec5\u4f5c\u4e3a\u7a33\u5b9a\u5e01\u6d41\u52a8\u6027\u80cc\u666f\uff0c"
            "\u4e0d\u7b49\u4e8e\u4ef7\u683c\u9884\u6d4b\u3002"
        )
    if context_type == "chain_activity":
        return (
            f"Halpha material \u663e\u793a {state}/{severity}\uff1b"
            "\u4ec5\u4f5c\u4e3a\u4f7f\u7528\u5ea6\u80cc\u666f\uff0c"
            "\u4e0d\u4ea7\u751f\u64cd\u4f5c\u6307\u4ee4\u3002"
        )
    if context_type == "network_congestion":
        return (
            f"Halpha material \u663e\u793a {state}/{severity}\uff1b"
            "\u4ec5\u4f5c\u4e3a\u7ed3\u7b97\u6469\u64e6\u6216\u62e5\u5835\u80cc\u666f\uff0c"
            "\u4e0d\u4ee3\u8868\u5e02\u573a\u65b9\u5411\u3002"
        )
    if context_type == "exchange_flow_source_availability":
        return (
            "\u4ea4\u6613\u6240\u6d41\u6765\u6e90\u53ef\u7528\u6027\u53ea\u63cf\u8ff0\u8986\u76d6\u72b6\u6001\uff1b"
            "\u4e0d\u63a8\u65ad\u4ea4\u6613\u6240\u5145\u63d0\u538b\u529b\u6216\u5730\u5740\u6807\u7b7e\u3002"
        )
    return (
        "\u4ec5\u6309 Halpha \u5df2\u751f\u6210\u7684\u94fe\u4e0a\u6d41 context \u89e3\u91ca\uff1b"
        "\u4e0d\u751f\u6210\u5730\u5740\u6807\u7b7e\u3001\u4ea4\u6613\u6307\u4ee4\u6216\u9884\u6d4b\u3002"
    )


def _macro_calendar_sources(record: dict[str, Any]) -> str:
    artifacts = [
        MACRO_CALENDAR_MATERIAL_ARTIFACT,
        *[
            artifact
            for artifact in record.get("source_artifacts", [])
            if isinstance(artifact, str) and artifact
        ],
    ]
    return "; ".join(_unique(artifacts)[:4])


def _derivatives_sources(record: dict[str, Any]) -> str:
    artifacts = [
        DERIVATIVES_MARKET_MATERIAL_ARTIFACT,
        *[
            artifact
            for artifact in record.get("source_artifacts", [])
            if isinstance(artifact, str) and artifact
        ],
    ]
    return "; ".join(_unique(artifacts)[:4])


def _onchain_flow_sources(record: dict[str, Any]) -> str:
    artifacts = [
        ONCHAIN_FLOW_MATERIAL_ARTIFACT,
        *[
            artifact
            for artifact in record.get("source_artifacts", [])
            if isinstance(artifact, str) and artifact
        ],
    ]
    return "; ".join(_unique(artifacts)[:4])


def inject_strategy_effectiveness_table(report: str, run: RunContext) -> str:
    table = _strategy_effectiveness_markdown_table(run)
    if table is None:
        return report
    section = "\n".join(
        [
            "## \u7b56\u7565\u6709\u6548\u6027\u95e8\u69db\u8868",
            "",
            table,
            "",
        ]
    )
    return _insert_report_section(report, section)


def _quant_strategy_markdown_table(run: RunContext) -> str | None:
    artifact = _read_quant_strategy_runs(run)
    if artifact is None:
        return None
    runs = artifact.get("runs")
    if not isinstance(runs, list) or not runs:
        return None
    rows = [_strategy_run_table_row(item) for item in runs if isinstance(item, dict)]
    if not rows:
        return None
    header = [
        "策略",
        "来源",
        "标的",
        "周期",
        "输入窗口",
        "状态",
        "方向",
        "强度",
        "置信度",
        "结论",
    ]
    lines = [
        _markdown_row(header),
        _markdown_row(["---"] * len(header)),
    ]
    for row in sorted(rows, key=_strategy_table_sort_key):
        lines.append(_markdown_row(row))
    return "\n".join(lines)


def _strategy_effectiveness_markdown_table(run: RunContext) -> str | None:
    artifact = _read_strategy_effectiveness_gates(run)
    if artifact is None:
        return None
    records = artifact.get("records")
    if not isinstance(records, list) or not records:
        return None
    rows = [_strategy_effectiveness_table_row(item) for item in records if isinstance(item, dict)]
    if not rows:
        return None
    header = [
        "\u7b56\u7565",
        "\u72b6\u6001",
        "\u57fa\u51c6\u8986\u76d6",
        "\u51c0\u6536\u76ca",
        "\u76f8\u5bf9\u57fa\u51c6",
        "\u6210\u672c\u62d6\u7d2f",
        "\u6837\u672c",
        "Walk-forward",
        "\u8fc7\u62df\u5408\u98ce\u9669",
        "\u5173\u952e\u539f\u56e0",
    ]
    lines = [
        _markdown_row(header),
        _markdown_row(["---"] * len(header)),
    ]
    for row in sorted(rows, key=lambda item: item[0]):
        lines.append(_markdown_row(row))
    return "\n".join(lines)


def _read_quant_strategy_runs(run: RunContext) -> dict[str, Any] | None:
    path = run.analysis_dir / "quant_strategy_runs.json"
    if not path.exists():
        return None
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} must be a mapping.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _read_strategy_effectiveness_gates(run: RunContext) -> dict[str, Any] | None:
    path = run.analysis_dir / "strategy_effectiveness_gates.json"
    if not path.exists():
        return None
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{STRATEGY_EFFECTIVENESS_GATES_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(
            f"{STRATEGY_EFFECTIVENESS_GATES_ARTIFACT} must be a mapping.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _strategy_run_table_row(item: dict[str, Any]) -> list[str]:
    assessment = item.get("assessment") if isinstance(item.get("assessment"), dict) else {}
    data_quality = item.get("data_quality") if isinstance(item.get("data_quality"), dict) else {}
    error = item.get("error") if isinstance(item.get("error"), dict) else {}
    summary = assessment.get("summary") if isinstance(assessment.get("summary"), str) else None
    if not summary and isinstance(error.get("message"), str):
        summary = error["message"]
    if not summary:
        signals = item.get("signals") if isinstance(item.get("signals"), dict) else {}
        summary = str(signals.get("latest_regime") or "")
    return [
        _text(item.get("strategy_name")),
        _text(item.get("source")),
        _text(item.get("symbol")),
        _text(item.get("timeframe")),
        _input_window(item),
        _status_label(item.get("status")),
        _text(assessment.get("direction")),
        _text(assessment.get("strength")),
        _text(assessment.get("confidence")),
        _table_summary(summary, data_quality=data_quality),
    ]


def _strategy_effectiveness_table_row(item: dict[str, Any]) -> list[str]:
    inputs = item.get("gate_inputs") if isinstance(item.get("gate_inputs"), dict) else {}
    coverage = inputs.get("benchmark_coverage") if isinstance(inputs.get("benchmark_coverage"), dict) else {}
    net = inputs.get("net_performance") if isinstance(inputs.get("net_performance"), dict) else {}
    baseline = (
        inputs.get("baseline_comparison")
        if isinstance(inputs.get("baseline_comparison"), dict)
        else {}
    )
    cost = inputs.get("cost_drag") if isinstance(inputs.get("cost_drag"), dict) else {}
    sample = inputs.get("sample_quality") if isinstance(inputs.get("sample_quality"), dict) else {}
    walk_forward = (
        inputs.get("walk_forward_stability")
        if isinstance(inputs.get("walk_forward_stability"), dict)
        else {}
    )
    overfitting = inputs.get("overfitting_risk") if isinstance(inputs.get("overfitting_risk"), dict) else {}
    return [
        _text(item.get("strategy_name")),
        _gate_status_label(item.get("status")),
        _coverage_summary(coverage),
        _metric_summary(
            net.get("mean_net_return_pct"),
            positive_pct=net.get("positive_net_return_benchmark_pct"),
        ),
        _metric_summary(
            baseline.get("mean_excess_return_vs_buy_and_hold_pct"),
            positive_pct=baseline.get("positive_excess_return_benchmark_pct"),
        ),
        _pct_value(cost.get("max_cost_drag_pct")),
        _sample_summary(sample),
        _walk_forward_summary(walk_forward),
        _text(overfitting.get("status")),
        _reason_summary(item),
    ]


def _strategy_table_sort_key(row: list[str]) -> tuple[str, str, str, str]:
    source = row[1]
    symbol = row[2]
    timeframe = row[3]
    strategy = row[0]
    return (source, symbol, timeframe, strategy)


def _insert_report_section(report: str, section: str) -> str:
    stripped = report.rstrip()
    for heading in ("## 综合判断", "## 风险提示"):
        index = stripped.find(f"\n{heading}")
        if index != -1:
            return f"{stripped[:index].rstrip()}\n\n{section}{stripped[index:]}\n"
    return f"{stripped}\n\n{section}"


def _markdown_row(values: list[str]) -> str:
    return "| " + " | ".join(_escape_markdown_cell(value) for value in values) + " |"


def _escape_markdown_cell(value: str) -> str:
    return " ".join(str(value).replace("|", "\\|").split())


def _input_window(item: dict[str, Any]) -> str:
    start = _text(item.get("input_window_start"))
    end = _text(item.get("input_window_end"))
    if start and end:
        return f"{start} to {end}"
    return end or start


def _status_label(value: Any) -> str:
    labels = {
        "succeeded": "成功",
        "failed": "失败",
        "insufficient_data": "数据不足",
        "skipped": "跳过",
        "disabled": "禁用",
    }
    return labels.get(value, _text(value))


def _gate_status_label(value: Any) -> str:
    labels = {
        "effective": "\u6709\u6548",
        "watchlisted": "\u89c2\u5bdf",
        "rejected": "\u62d2\u7edd",
        "insufficient_evidence": "\u8bc1\u636e\u4e0d\u8db3",
    }
    return labels.get(value, _text(value))


def _table_summary(summary: str | None, *, data_quality: dict[str, Any]) -> str:
    value = _text(summary)
    if value:
        return value
    row_count = data_quality.get("row_count")
    minimum_rows = data_quality.get("minimum_required_rows")
    if isinstance(row_count, int) and isinstance(minimum_rows, int):
        return f"rows {row_count}/{minimum_rows}"
    return ""


def _coverage_summary(value: dict[str, Any]) -> str:
    succeeded = value.get("succeeded")
    records = value.get("benchmark_records")
    rate = value.get("success_rate_pct")
    base = f"{_text(succeeded)}/{_text(records)}" if succeeded is not None or records is not None else ""
    if rate is None:
        return base
    return f"{base} ({_pct_value(rate)})" if base else _pct_value(rate)


def _metric_summary(value: Any, *, positive_pct: Any) -> str:
    metric = _pct_value(value)
    positive = _pct_value(positive_pct)
    if metric and positive:
        return f"{metric}; positive {positive}"
    return metric or positive


def _sample_summary(value: dict[str, Any]) -> str:
    minimum = value.get("min_sample_rows")
    maximum = value.get("max_sample_rows")
    if minimum is None and maximum is None:
        return ""
    if maximum is None:
        return f"min rows {_text(minimum)}"
    return f"rows {_text(minimum)}-{_text(maximum)}"


def _walk_forward_summary(value: dict[str, Any]) -> str:
    stability = _text(value.get("result_stability"))
    windows = value.get("succeeded_windows")
    positive = value.get("min_positive_net_return_window_pct")
    parts = [item for item in (stability, f"windows {_text(windows)}" if windows is not None else "") if item]
    if positive is not None:
        parts.append(f"positive {_pct_value(positive)}")
    return "; ".join(parts)


def _reason_summary(item: dict[str, Any]) -> str:
    reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
    codes = [
        str(reason.get("code"))
        for reason in reasons
        if isinstance(reason, dict)
        and reason.get("severity") in {"block", "downgrade", "reject", "info"}
        and reason.get("code")
    ]
    if not codes:
        codes = [
            str(reason.get("code"))
            for reason in reasons
            if isinstance(reason, dict) and reason.get("code")
        ]
    return ", ".join(codes[:4])


def _pct_value(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    return f"{float(value):.6g}%"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
