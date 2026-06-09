from __future__ import annotations

import json
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "run_codex_report"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"


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


def _table_summary(summary: str | None, *, data_quality: dict[str, Any]) -> str:
    value = _text(summary)
    if value:
        return value
    row_count = data_quality.get("row_count")
    minimum_rows = data_quality.get("minimum_required_rows")
    if isinstance(row_count, int) and isinstance(minimum_rows, int):
        return f"rows {row_count}/{minimum_rows}"
    return ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
