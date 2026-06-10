from __future__ import annotations

import json
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "run_codex_report"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
STRATEGY_EFFECTIVENESS_GATES_ARTIFACT = "analysis/strategy_effectiveness_gates.json"


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
