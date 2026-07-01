from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


STRATEGY_EVALUATION_HISTORY_ARTIFACT = "data/research/strategy_evaluations/strategy_evaluation_history.json"
SCHEMA_VERSION = 1
MAX_HISTORY_RECORDS = 500
MAX_VISUALIZATION_POINTS = 120
MAX_VISUALIZATION_MARKERS = 80
MAX_SPARKLINE_POINTS = 160


def strategy_evaluation_history_path(config_path: Path) -> Path:
    return resolve_runtime_path(STRATEGY_EVALUATION_HISTORY_ARTIFACT, config_path=config_path)


def read_strategy_evaluation_history(config_path: Path) -> dict[str, Any]:
    path = strategy_evaluation_history_path(config_path)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_history()
    except (OSError, json.JSONDecodeError):
        return {
            **_empty_history(),
            "status": "failed",
            "errors": [f"{STRATEGY_EVALUATION_HISTORY_ARTIFACT} is not readable."],
        }
    if not isinstance(loaded, dict):
        return {
            **_empty_history(),
            "status": "failed",
            "errors": [f"{STRATEGY_EVALUATION_HISTORY_ARTIFACT} must be a JSON object."],
        }
    records = loaded.get("records") if isinstance(loaded.get("records"), list) else []
    return {
        **loaded,
        "schema_version": loaded.get("schema_version") or SCHEMA_VERSION,
        "artifact_type": "strategy_evaluation_history",
        "records": [record for record in records if isinstance(record, dict)],
        "warnings": _string_list(loaded.get("warnings")),
        "errors": _string_list(loaded.get("errors")),
    }


def register_report_strategy_evaluations(
    run: RunContext,
    evaluation_artifact: dict[str, Any],
    *,
    now: datetime | str | None = None,
) -> int:
    records = [
        _report_record(run, record, evaluation_artifact=evaluation_artifact, now=now)
        for record in _dict_items(evaluation_artifact.get("records"))
    ]
    return _upsert_records(run.config_path, records, now=now)


def register_standalone_strategy_backtest(
    *,
    config_path: Path,
    output_dir: Path,
    manifest: dict[str, Any],
    evaluation: dict[str, Any],
    artifact_path: Path,
    manifest_path: Path,
    now: datetime | str | None = None,
) -> None:
    record = _standalone_record(
        config_path=config_path,
        output_dir=output_dir,
        manifest=manifest,
        evaluation=evaluation,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        now=now,
    )
    _upsert_records(config_path, [record], now=now)


def _upsert_records(config_path: Path, records: list[dict[str, Any]], *, now: datetime | str | None) -> int:
    if not records:
        return 0
    current = read_strategy_evaluation_history(config_path)
    existing = {
        str(record.get("history_id")): record
        for record in current.get("records", [])
        if isinstance(record, dict) and record.get("history_id")
    }
    for record in records:
        existing[str(record["history_id"])] = record
    merged = sorted(
        existing.values(),
        key=lambda record: (
            str(record.get("created_at") or ""),
            str(record.get("history_id") or ""),
        ),
        reverse=True,
    )[:MAX_HISTORY_RECORDS]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "strategy_evaluation_history",
        "updated_at": _format_utc(now),
        "status": "ok",
        "record_count": len(merged),
        "records": merged,
        "warnings": [],
        "errors": [],
        "omitted": {
            "max_records": MAX_HISTORY_RECORDS,
            "older_records": max(0, len(existing) - MAX_HISTORY_RECORDS),
            "full_source_artifacts_embedded": False,
        },
    }
    write_json(strategy_evaluation_history_path(config_path), artifact)
    return len(records)


def _report_record(
    run: RunContext,
    record: dict[str, Any],
    *,
    evaluation_artifact: dict[str, Any],
    now: datetime | str | None,
) -> dict[str, Any]:
    base = runtime_root(run.config_path)
    source_artifacts = [
        display_path(run.analysis_dir / "strategy_evaluation_summary.json", base=base),
        display_path(run.analysis_dir / "quant_strategy_runs.json", base=base),
        display_path(run.raw_dir / "market_data_views.json", base=base),
    ]
    evaluation_id = str(record.get("evaluation_id") or _record_identity(record))
    created_at = str(record.get("created_at") or evaluation_artifact.get("created_at") or _format_utc(now))
    single_window = _dict(record.get("single_window"))
    return {
        "history_id": f"strategy_evaluation_history:report_run:{run.run_id}:{evaluation_id}",
        "record_type": "strategy_evaluation_history_record",
        "created_at": created_at,
        "registered_at": _format_utc(now),
        "execution_source": {
            "type": "report_run",
            "run_id": run.run_id,
            "run_dir": display_path(run.run_dir, base=base),
            "stage": "evaluate_strategy_evaluation",
        },
        "evaluation_id": evaluation_id,
        **_common_record_fields(record),
        "metrics": _metrics_from_evaluation(single_window),
        "visualization": _visualization_from_evaluation(record, single_window),
        "warnings": _message_strings(record.get("warnings")),
        "errors": _record_errors(record),
        "source_artifacts": source_artifacts,
    }


def _standalone_record(
    *,
    config_path: Path,
    output_dir: Path,
    manifest: dict[str, Any],
    evaluation: dict[str, Any],
    artifact_path: Path,
    manifest_path: Path,
    now: datetime | str | None,
) -> dict[str, Any]:
    base = runtime_root(config_path)
    inputs = _dict(manifest.get("inputs"))
    created_at = str(manifest.get("created_at") or _format_utc(now))
    source_artifacts = [
        display_path(manifest_path, base=base),
        display_path(artifact_path, base=base),
    ]
    strategy_name = evaluation.get("strategy_name") or inputs.get("strategy_name")
    source = evaluation.get("source") or inputs.get("source")
    symbol = evaluation.get("symbol") or inputs.get("symbol")
    timeframe = evaluation.get("timeframe") or inputs.get("timeframe")
    return {
        "history_id": f"strategy_evaluation_history:standalone_backtest:{display_path(output_dir, base=base)}",
        "record_type": "strategy_evaluation_history_record",
        "created_at": created_at,
        "registered_at": _format_utc(now),
        "execution_source": {
            "type": "standalone_backtest",
            "output_dir": display_path(output_dir, base=base),
            "command": "backtest",
        },
        "evaluation_id": f"standalone_backtest:{strategy_name}:{source}:{symbol}:{timeframe}:{created_at}",
        "status": evaluation.get("status") or manifest.get("evaluation_status") or "unknown",
        "strategy_name": strategy_name,
        "strategy_version": evaluation.get("strategy_version"),
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "input_window_start": _dict(evaluation.get("sample")).get("start"),
        "input_window_end": _dict(evaluation.get("sample")).get("end"),
        "latest_candle_time": _dict(evaluation.get("sample")).get("end"),
        "params": _dict(inputs.get("params")),
        "metrics": _metrics_from_evaluation(evaluation),
        "visualization": _bounded_visualization(_dict(evaluation.get("visualization"))),
        "warnings": _message_strings(evaluation.get("warnings")),
        "errors": _message_strings(evaluation.get("errors")),
        "source_artifacts": source_artifacts,
    }


def _common_record_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": record.get("status") or "unknown",
        "strategy_name": record.get("strategy_name"),
        "strategy_version": record.get("strategy_version"),
        "source": record.get("source"),
        "symbol": record.get("symbol"),
        "timeframe": record.get("timeframe"),
        "input_window_start": record.get("input_window_start"),
        "input_window_end": record.get("input_window_end"),
        "latest_candle_time": record.get("latest_candle_time"),
        "params": _dict(record.get("params")),
    }


def _metrics_from_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_metrics": _dict(evaluation.get("strategy_metrics")),
        "baseline_metrics": _dict(evaluation.get("baseline_metrics")),
        "relative_metrics": _dict(evaluation.get("relative_metrics")),
        "trade_summary": _dict(evaluation.get("trade_summary")),
        "sample": _dict(evaluation.get("sample")),
        "execution_model": _dict(evaluation.get("execution_model")),
        "cost_assumptions": _dict(evaluation.get("cost_assumptions")),
    }


def _visualization_from_evaluation(record: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    full_curve = _equity_curve_points(evaluation.get("equity_curve"))
    curve = full_curve[-MAX_VISUALIZATION_POINTS:]
    sparkline = _compressed_equity_curve(full_curve, max_points=MAX_SPARKLINE_POINTS)
    full_markers = _markers_from_equity_curve(full_curve, limit=None)
    markers = full_markers[-MAX_VISUALIZATION_MARKERS:]
    if not curve and not markers:
        return {}
    return {
        "schema_version": 1,
        "chart_type": "candlestick_backtest",
        "status": "available" if markers or curve else "partial",
        "strategy_name": record.get("strategy_name"),
        "source": record.get("source"),
        "symbol": record.get("symbol"),
        "timeframe": record.get("timeframe"),
        "bars": [],
        "markers": markers,
        "equity_curve": curve,
        "equity_sparkline": sparkline,
        "limits": {
            "max_markers": MAX_VISUALIZATION_MARKERS,
            "max_equity_points": MAX_VISUALIZATION_POINTS,
            "max_sparkline_equity_points": MAX_SPARKLINE_POINTS,
        },
        "omitted": {
            "bars": 0,
            "equity_points": max(0, len(full_curve) - len(curve)),
            "equity_sparkline_points": max(0, len(full_curve) - len(sparkline)),
            "markers": max(0, len(full_markers) - len(markers)),
        },
        "warnings": [],
    }


def _bounded_visualization(visualization: dict[str, Any]) -> dict[str, Any]:
    if not visualization:
        return {}
    result = dict(visualization)
    result["bars"] = _dict_items(visualization.get("bars"))[-MAX_VISUALIZATION_POINTS:]
    result["markers"] = _dict_items(visualization.get("markers"))[-MAX_VISUALIZATION_MARKERS:]
    result["equity_curve"] = _dict_items(visualization.get("equity_curve"))[-MAX_VISUALIZATION_POINTS:]
    sparkline = _equity_curve_points(visualization.get("equity_sparkline"))
    if not sparkline:
        sparkline = _equity_curve_points(visualization.get("equity_curve"))
    result["equity_sparkline"] = _compressed_equity_curve(sparkline, max_points=MAX_SPARKLINE_POINTS)
    limits = _dict(result.get("limits"))
    limits["max_sparkline_equity_points"] = MAX_SPARKLINE_POINTS
    result["limits"] = limits
    return result


def _bounded_equity_curve(value: Any) -> list[dict[str, Any]]:
    return _equity_curve_points(value)[-MAX_VISUALIZATION_POINTS:]


def _compressed_equity_curve(points: list[dict[str, Any]], *, max_points: int) -> list[dict[str, Any]]:
    clean = [point for point in points if point]
    if len(clean) <= max_points:
        return clean
    if max_points <= 2:
        return [clean[0], clean[-1]][:max_points]
    reserved = set(_reserved_equity_indices(clean))
    budget = max(0, max_points - len(reserved))
    optional = _bucket_extreme_equity_indices(clean, reserved=reserved, budget=budget)
    keep = reserved | set(optional)
    if len(keep) > max_points:
        keep = reserved | set(_evenly_spaced_indices(sorted(keep - reserved), max_points - len(reserved)))
    return [clean[index] for index in sorted(keep)]


def _reserved_equity_indices(points: list[dict[str, Any]]) -> list[int]:
    if not points:
        return []
    reserved = {0, len(points) - 1}
    finite = _indexed_equity_values(points)
    if finite:
        reserved.add(min(finite, key=lambda item: item[1])[0])
        reserved.add(max(finite, key=lambda item: item[1])[0])
        reserved.update(_max_drawdown_equity_indices(finite))
    return sorted(reserved)


def _indexed_equity_values(points: list[dict[str, Any]]) -> list[tuple[int, float]]:
    values: list[tuple[int, float]] = []
    for index, point in enumerate(points):
        value = _equity_numeric_value(point)
        if value is not None:
            values.append((index, value))
    return values


def _equity_numeric_value(point: dict[str, Any]) -> float | None:
    for key in ("net_equity", "equity", "value", "gross_equity"):
        raw_value = point.get(key)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value == value and value not in {float("inf"), float("-inf")}:
            return value
    return None


def _max_drawdown_equity_indices(indexed_values: list[tuple[int, float]]) -> list[int]:
    peak_index: int | None = None
    peak_value: float | None = None
    best_peak_index: int | None = None
    best_trough_index: int | None = None
    worst_drawdown = 0.0
    for index, value in indexed_values:
        if peak_value is None or value > peak_value:
            peak_index = index
            peak_value = value
        if peak_value in {None, 0} or peak_index is None:
            continue
        drawdown = (value / peak_value) - 1
        if drawdown < worst_drawdown:
            worst_drawdown = drawdown
            best_peak_index = peak_index
            best_trough_index = index
    return [index for index in (best_peak_index, best_trough_index) if index is not None]


def _bucket_extreme_equity_indices(
    points: list[dict[str, Any]],
    *,
    reserved: set[int],
    budget: int,
) -> list[int]:
    inner_indices = [index for index in range(1, len(points) - 1) if index not in reserved]
    if budget <= 0 or not inner_indices:
        return []
    if len(inner_indices) <= budget:
        return inner_indices
    if budget < 4:
        return _evenly_spaced_indices(inner_indices, budget)
    bucket_count = max(1, budget // 4)
    bucket_size = max(1, (len(inner_indices) + bucket_count - 1) // bucket_count)
    selected: set[int] = set()
    for offset in range(0, len(inner_indices), bucket_size):
        bucket = inner_indices[offset : offset + bucket_size]
        if not bucket:
            continue
        selected.add(bucket[0])
        selected.add(bucket[-1])
        finite = [(index, _equity_numeric_value(points[index])) for index in bucket]
        finite = [(index, value) for index, value in finite if value is not None]
        if finite:
            selected.add(min(finite, key=lambda item: item[1])[0])
            selected.add(max(finite, key=lambda item: item[1])[0])
    return sorted(selected)


def _evenly_spaced_indices(indices: list[int], count: int) -> list[int]:
    if count <= 0 or not indices:
        return []
    if count >= len(indices):
        return indices
    if count == 1:
        return [indices[len(indices) // 2]]
    last = len(indices) - 1
    selected = {
        indices[round(position * last / (count - 1))]
        for position in range(count)
    }
    return sorted(selected)


def _equity_curve_points(value: Any) -> list[dict[str, Any]]:
    points = []
    for point in _dict_items(value):
        time_value = point.get("open_time") or point.get("timestamp") or point.get("time")
        if not time_value:
            continue
        points.append(
            {
                "time": str(time_value),
                "net_equity": point.get("net_equity", point.get("equity")),
                "gross_equity": point.get("gross_equity"),
                "position": point.get("position"),
                "turnover": point.get("turnover"),
            }
        )
    return points


def _markers_from_equity_curve(curve: list[dict[str, Any]], *, limit: int | None = MAX_VISUALIZATION_MARKERS) -> list[dict[str, Any]]:
    markers = []
    previous_position = 0.0
    for point in curve:
        try:
            position = float(point.get("position") or 0.0)
        except (TypeError, ValueError):
            continue
        marker = None
        if position > 0 and previous_position <= 0:
            marker = {"kind": "entry", "label": "Long", "side": "long"}
        elif position < 0 and previous_position >= 0:
            marker = {"kind": "entry", "label": "Short", "side": "short"}
        elif position == 0 and previous_position != 0:
            marker = {"kind": "exit", "label": "Exit", "side": "flat"}
        elif position != previous_position:
            marker = {"kind": "exposure_change", "label": "Exposure", "side": "mixed"}
        if marker:
            markers.append(
                {
                    "time": point.get("time"),
                    "position": position,
                    "execution_timing": "next_bar",
                    **marker,
                }
            )
        previous_position = position
    if limit is None:
        return markers
    return markers[-limit:]


def _record_identity(record: dict[str, Any]) -> str:
    return ":".join(
        str(record.get(key) or "missing")
        for key in ("strategy_name", "source", "symbol", "timeframe", "latest_candle_time")
    )


def _record_errors(record: dict[str, Any]) -> list[str]:
    error = record.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("error_type")
        return [str(message)] if message else []
    return _message_strings(record.get("errors"))


def _empty_history() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "strategy_evaluation_history",
        "status": "missing",
        "record_count": 0,
        "records": [],
        "warnings": [],
        "errors": [],
    }


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float)) and not isinstance(item, bool)]


def _message_strings(value: Any) -> list[str]:
    messages = []
    for item in _dict_items(value):
        message = item.get("message") or item.get("code")
        if message:
            messages.append(str(message))
    messages.extend(_string_list(value))
    return messages
