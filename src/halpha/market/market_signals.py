from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import write_json


BUILD_MARKET_SIGNALS_STAGE = "build_market_signals"
BUILD_MARKET_SIGNAL_MATERIAL_STAGE = "build_market_signal_material"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
MARKET_SIGNAL_MATERIAL_ARTIFACT = "analysis/market_signal_material.md"
MARKET_DATA_VIEWS_ARTIFACT = "raw/market_data_views.json"
MARKET_SIGNALS_SCHEMA_VERSION = 1
MARKET_SIGNAL_MATERIAL_SCHEMA_VERSION = 1


def build_market_signals(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        run.manifest["counts"]["market_signals"] = 0
        run.manifest["counts"]["market_signals_insufficient_data"] = 0
        return []

    strategy_artifact = _read_json_artifact(
        run.analysis_dir / "quant_strategy_runs.json",
        QUANT_STRATEGY_RUNS_ARTIFACT,
        producer_stage="evaluate_quant_strategies",
        stage=BUILD_MARKET_SIGNALS_STAGE,
    )
    strategy_runs = _strategy_runs_from_artifact(strategy_artifact, stage=BUILD_MARKET_SIGNALS_STAGE)
    created_at = _created_at(strategy_artifact, now)
    signals = [
        _market_signal_from_strategy_run(strategy_run, created_at=created_at)
        for strategy_run in strategy_runs
    ]

    artifact = {
        "schema_version": MARKET_SIGNALS_SCHEMA_VERSION,
        "artifact_type": "market_signals",
        "created_at": created_at,
        "source_artifacts": _market_signal_source_artifacts(strategy_artifact),
        "signals": signals,
    }
    write_json(run.analysis_dir / "market_signals.json", artifact)
    run.manifest["artifacts"]["market_signals"] = MARKET_SIGNALS_ARTIFACT
    run.manifest["counts"]["market_signals"] = len(signals)
    run.manifest["counts"]["market_signals_insufficient_data"] = sum(
        1 for signal in signals if signal["insufficient_data"]
    )
    return [MARKET_SIGNALS_ARTIFACT]


def build_market_signal_material(config: dict[str, Any], run: RunContext) -> list[str]:
    if not _quant_enabled(config):
        run.manifest["counts"]["market_signal_material_records"] = 0
        return []

    market_signals = _read_json_artifact(
        run.analysis_dir / "market_signals.json",
        MARKET_SIGNALS_ARTIFACT,
        producer_stage=BUILD_MARKET_SIGNALS_STAGE,
        stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE,
    )
    _signals_from_artifact(market_signals, stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE)
    strategy_runs = _read_strategy_runs_for_material(run, market_signals)
    output_path = run.analysis_dir / "market_signal_material.md"
    output_path.write_text(
        render_market_signal_material(market_signals, strategy_runs=strategy_runs),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["market_signal_material"] = MARKET_SIGNAL_MATERIAL_ARTIFACT
    run.manifest["counts"]["market_signal_material_records"] = len(market_signals["signals"])
    return [MARKET_SIGNAL_MATERIAL_ARTIFACT]


def render_market_signal_material(
    market_signals: dict[str, Any],
    *,
    strategy_runs: dict[str, Any] | None = None,
) -> str:
    source_artifacts = _unique_ordered(
        [
            MARKET_SIGNALS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
            *_string_list(market_signals.get("source_artifacts")),
            *([QUANT_STRATEGY_RUNS_ARTIFACT] if strategy_runs is not None else []),
            *_string_list(strategy_runs.get("source_artifacts") if strategy_runs else None),
        ]
    )
    signals = market_signals["signals"]
    lines = [
        "---",
        "artifact_type: analysis_market_signal_material",
        f"schema_version: {MARKET_SIGNAL_MATERIAL_SCHEMA_VERSION}",
        "audience: ai",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# market_signal_material",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_source_policy()).rstrip(),
        "```",
        "",
        "## quant_overview",
        "",
        "```yaml",
        _yaml_block(_quant_overview(market_signals, strategy_runs)).rstrip(),
        "```",
        "",
        "## strategy_matrix",
        "",
        "```yaml",
        _yaml_block(_strategy_matrix(signals)).rstrip(),
        "```",
        "",
        "## confluence_and_conflict",
        "",
        "```yaml",
        _yaml_block(_confluence_and_conflict(signals)).rstrip(),
        "```",
        "",
        "## risk_and_uncertainty",
        "",
        "```yaml",
        _yaml_block(_risk_and_uncertainty(signals, strategy_runs)).rstrip(),
        "```",
        "",
        "## report_guidance",
        "",
        "```yaml",
        _yaml_block(_report_guidance()).rstrip(),
        "```",
        "",
    ]

    for signal in signals:
        lines.extend(
            [
                f"## record: {signal['signal_id']}",
                "",
                "```yaml",
                _yaml_block(_material_record(signal)).rstrip(),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def _read_strategy_runs_for_material(run: RunContext, market_signals: dict[str, Any]) -> dict[str, Any] | None:
    if QUANT_STRATEGY_RUNS_ARTIFACT not in _string_list(market_signals.get("source_artifacts")):
        return None
    artifact = _read_json_artifact(
        run.analysis_dir / "quant_strategy_runs.json",
        QUANT_STRATEGY_RUNS_ARTIFACT,
        producer_stage="evaluate_quant_strategies",
        stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE,
    )
    runs = artifact.get("runs")
    if not isinstance(runs, list):
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} must contain a runs list.",
            stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE,
            exit_code=3,
        )
    for index, item in enumerate(runs):
        if not isinstance(item, dict):
            raise PipelineError(
                f"runs[{index}] must be a mapping.",
                stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE,
                exit_code=3,
            )
    return artifact


def _market_signal_from_strategy_run(strategy_run: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    assessment = strategy_run.get("assessment") if isinstance(strategy_run.get("assessment"), dict) else {}
    warnings = _warning_messages(strategy_run.get("warnings"))
    error = strategy_run.get("error") if isinstance(strategy_run.get("error"), dict) else None
    backtest = (
        strategy_run.get("backtest_diagnostic")
        if isinstance(strategy_run.get("backtest_diagnostic"), dict)
        else {}
    )
    parameter = (
        strategy_run.get("parameter_diagnostic")
        if isinstance(strategy_run.get("parameter_diagnostic"), dict)
        else {}
    )
    uncertainty = [
        *_string_list(assessment.get("uncertainty")),
        *warnings,
        *_warning_messages(backtest.get("warnings")),
        *_string_list(parameter.get("notes")),
        *_warning_messages(parameter.get("warnings")),
    ]
    if error and isinstance(error.get("message"), str):
        uncertainty.append(error["message"])
    latest = strategy_run.get("latest_candle_time") or "missing"
    return {
        "signal_id": (
            f"market_signal:{strategy_run.get('strategy_name')}:{strategy_run.get('source')}:"
            f"{strategy_run.get('symbol')}:{strategy_run.get('timeframe')}:{latest}"
        ),
        "strategy_name": strategy_run.get("strategy_name"),
        "source": strategy_run.get("source"),
        "symbol": strategy_run.get("symbol"),
        "timeframe": strategy_run.get("timeframe"),
        "input_window_start": strategy_run.get("input_window_start"),
        "input_window_end": strategy_run.get("input_window_end"),
        "latest_candle_time": strategy_run.get("latest_candle_time"),
        "direction": assessment.get("direction", "unknown"),
        "strength": assessment.get("strength", "unknown"),
        "confidence": assessment.get("confidence", "unknown"),
        "key_values": _strategy_run_key_values(strategy_run),
        "evidence": _string_list(assessment.get("evidence")),
        "uncertainty": uncertainty,
        "insufficient_data": strategy_run.get("status") == "insufficient_data",
        "source_artifacts": _unique_ordered(
            [QUANT_STRATEGY_RUNS_ARTIFACT, *_string_list(strategy_run.get("source_artifacts"))]
        ),
        "created_at": strategy_run.get("created_at") or created_at,
    }


def _strategy_run_key_values(strategy_run: dict[str, Any]) -> dict[str, Any]:
    data_quality = strategy_run.get("data_quality") if isinstance(strategy_run.get("data_quality"), dict) else {}
    indicators = strategy_run.get("indicators") if isinstance(strategy_run.get("indicators"), dict) else {}
    signals = strategy_run.get("signals") if isinstance(strategy_run.get("signals"), dict) else {}
    backtest = (
        strategy_run.get("backtest_diagnostic")
        if isinstance(strategy_run.get("backtest_diagnostic"), dict)
        else {}
    )
    parameter = (
        strategy_run.get("parameter_diagnostic")
        if isinstance(strategy_run.get("parameter_diagnostic"), dict)
        else {}
    )
    keys = (
        "latest_close",
        "return_window_pct",
        "latest_return_pct",
        "realized_volatility_pct",
        "target_volatility_pct",
        "volatility_scaled_exposure",
        "breakout_window_high",
        "breakout_window_low",
        "exit_window_low",
        "atr",
        "atr_pct",
        "range_width_pct",
        "breakout_distance_atr",
        "short_sma",
        "long_sma",
        "trend_spread_pct",
        "bollinger_middle",
        "bollinger_upper",
        "bollinger_lower",
        "bollinger_band_width_pct",
        "bollinger_percent_b",
        "rsi",
        "rsi_oversold_threshold",
        "rsi_overbought_threshold",
        "trend_window_pct",
        "trend_filter_pct",
        "row_count",
    )
    result = {key: indicators[key] for key in keys if key in indicators}
    for key in ("row_count", "requested_lookback", "minimum_required_rows"):
        if key in data_quality and key not in result:
            result[key] = data_quality[key]
    for key in (
        "latest_regime",
        "entry_count",
        "exit_count",
        "latest_signal_active",
        "latest_oversold",
        "latest_overbought",
        "trend_filter_active",
        "strong_trend_direction",
    ):
        if key in signals:
            result[key] = signals[key]
    if "status" in backtest:
        result["backtest_diagnostic_status"] = backtest["status"]
    metrics = backtest.get("metrics") if isinstance(backtest.get("metrics"), dict) else {}
    for key in (
        "total_return_pct",
        "max_drawdown_pct",
        "trade_count",
        "exposure_pct",
        "final_equity",
    ):
        if key in metrics:
            result[f"backtest_{key}"] = metrics[key]
    assumptions = backtest.get("assumptions") if isinstance(backtest.get("assumptions"), dict) else {}
    for key in (
        "execution_model_id",
        "signal_timing",
        "position_timing",
        "lookahead_policy",
    ):
        if key in metrics:
            result[f"backtest_{key}"] = metrics[key]
        elif key in assumptions:
            result[f"backtest_{key}"] = assumptions[key]
    if parameter.get("enabled") is True and "status" in parameter:
        result["parameter_diagnostic_status"] = parameter["status"]
        for key in ("tested_combinations", "valid_combinations", "invalid_combinations", "stability"):
            if key in parameter:
                result[f"parameter_{key}"] = parameter[key]
        signal_state = parameter.get("signal_state_stability")
        if isinstance(signal_state, dict) and "status" in signal_state:
            result["parameter_signal_state_stability"] = signal_state["status"]
        performance = parameter.get("performance_stability")
        if isinstance(performance, dict) and "status" in performance:
            result["parameter_performance_stability"] = performance["status"]
            if isinstance(performance.get("reason_codes"), list):
                result["parameter_performance_stability_reason_codes"] = performance["reason_codes"]
    return result


def _market_signal_source_artifacts(strategy_artifact: dict[str, Any]) -> list[str]:
    return _unique_ordered(
        [
            QUANT_STRATEGY_RUNS_ARTIFACT,
            *_string_list(strategy_artifact.get("source_artifacts")),
        ]
    )


def _material_record(signal: dict[str, Any]) -> dict[str, Any]:
    record = {
        "record_type": "market_signal",
        "signal_id": signal["signal_id"],
        "strategy_name": signal["strategy_name"],
        "source": signal["source"],
        "symbol": signal["symbol"],
        "timeframe": signal["timeframe"],
        "input_window_start": signal["input_window_start"],
        "input_window_end": signal["input_window_end"],
        "latest_candle_time": signal["latest_candle_time"],
        "direction": signal["direction"],
        "strength": signal["strength"],
        "confidence": signal["confidence"],
        "key_values": signal["key_values"],
        "evidence": signal["evidence"],
        "uncertainty": signal["uncertainty"],
        "insufficient_data": signal["insufficient_data"],
        "source_artifacts": signal["source_artifacts"],
    }
    if _has_backtest_diagnostic_summary(signal["key_values"]):
        record["backtest_diagnostic_policy"] = "historical_research_material_only_not_forecast"
    if _has_parameter_diagnostic_summary(signal["key_values"]):
        record["parameter_diagnostic_policy"] = "bounded_sensitivity_context_only_not_optimization"
    return record


def _quant_overview(market_signals: dict[str, Any], strategy_runs: dict[str, Any] | None) -> dict[str, Any]:
    signals = market_signals["signals"]
    return {
        "material_scope": "quant_strategy_signal_summary",
        "normalized_market_signal_artifact": MARKET_SIGNALS_ARTIFACT,
        "quant_strategy_runs_artifact": QUANT_STRATEGY_RUNS_ARTIFACT if strategy_runs is not None else None,
        "signal_count": len(signals),
        "strategy_count": len(_strategy_names(signals)),
        "strategies": _strategy_names(signals),
        "symbols": _sorted_unique(signal.get("symbol") for signal in signals),
        "timeframes": _sorted_unique(signal.get("timeframe") for signal in signals),
        "direction_counts": _count_by(signals, "direction"),
        "confidence_counts": _count_by(signals, "confidence"),
        "insufficient_data_count": sum(1 for signal in signals if signal.get("insufficient_data") is True),
        "strategy_run_status_counts": _strategy_run_status_counts(strategy_runs),
        "raw_ohlcv_history_embedded": False,
        "source_artifacts": _unique_ordered(
            [
                MARKET_SIGNALS_ARTIFACT,
                *_string_list(market_signals.get("source_artifacts")),
                *([QUANT_STRATEGY_RUNS_ARTIFACT] if strategy_runs is not None else []),
            ]
        ),
    }


def _strategy_matrix(signals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "columns": [
            "strategy_name",
            "source",
            "symbol",
            "timeframe",
            "direction",
            "strength",
            "confidence",
            "latest_regime",
            "diagnostics",
            "insufficient_data",
        ],
        "signals": [
            {
                "strategy_name": signal.get("strategy_name"),
                "source": signal.get("source"),
                "symbol": signal.get("symbol"),
                "timeframe": signal.get("timeframe"),
                "direction": signal.get("direction", "unknown"),
                "strength": signal.get("strength", "unknown"),
                "confidence": signal.get("confidence", "unknown"),
                "latest_regime": _key_value(signal, "latest_regime"),
                "diagnostics": _diagnostic_summary(signal),
                "insufficient_data": signal.get("insufficient_data") is True,
                "evidence_count": len(_string_list(signal.get("evidence"))),
                "uncertainty_count": len(_string_list(signal.get("uncertainty"))),
                "source_artifacts": _string_list(signal.get("source_artifacts")),
            }
            for signal in signals
        ],
    }


def _confluence_and_conflict(signals: list[dict[str, Any]]) -> dict[str, Any]:
    groups = []
    for key, items in _group_signals(signals).items():
        concrete_directions = [
            str(item.get("direction"))
            for item in items
            if isinstance(item.get("direction"), str) and item.get("direction") not in {"unknown", "mixed"}
        ]
        direction_counts = _count_by(items, "direction")
        unique_concrete = sorted(set(concrete_directions))
        has_conflict = len(unique_concrete) > 1 or any(item.get("direction") == "mixed" for item in items)
        confluence_direction = unique_concrete[0] if len(unique_concrete) == 1 and len(concrete_directions) > 1 else None
        groups.append(
            {
                "group": key,
                "strategies": _strategy_names(items),
                "signal_count": len(items),
                "direction_counts": direction_counts,
                "confluence_direction": confluence_direction or "none",
                "conflict": has_conflict,
                "insufficient_data": any(item.get("insufficient_data") is True for item in items),
                "low_confidence_count": sum(
                    1 for item in items if item.get("confidence") in {"low", "unknown"}
                ),
                "report_note": _group_report_note(
                    has_conflict=has_conflict,
                    confluence_direction=confluence_direction,
                    insufficient_data=any(item.get("insufficient_data") is True for item in items),
                ),
            }
        )
    return {
        "group_count": len(groups),
        "confluence_group_count": sum(1 for group in groups if group["confluence_direction"] != "none"),
        "conflict_group_count": sum(1 for group in groups if group["conflict"]),
        "groups": groups,
    }


def _risk_and_uncertainty(signals: list[dict[str, Any]], strategy_runs: dict[str, Any] | None) -> dict[str, Any]:
    uncertainty_items = _unique_ordered(
        [
            item
            for signal in signals
            for item in _string_list(signal.get("uncertainty"))
        ]
    )
    groups = _confluence_and_conflict(signals)["groups"]
    return {
        "low_confidence_signals": [
            signal.get("signal_id")
            for signal in signals
            if signal.get("confidence") in {"low", "unknown"}
        ],
        "insufficient_data_signals": [
            signal.get("signal_id")
            for signal in signals
            if signal.get("insufficient_data") is True
        ],
        "conflicting_groups": [group["group"] for group in groups if group["conflict"]],
        "uncertainty_notes": uncertainty_items,
        "diagnostic_policy": {
            "backtest_summaries_are_forecasts": False,
            "parameter_diagnostics_are_optimization": False,
            "strategy_run_status_counts": _strategy_run_status_counts(strategy_runs),
        },
        "raw_ohlcv_history_embedded": False,
    }


def _report_guidance() -> dict[str, Any]:
    return {
        "high_confidence_signals": [
            "Use as quantitative evidence when direction is clear and no same-market conflict is present.",
            "Keep evidence and uncertainty close to the conclusion.",
        ],
        "low_confidence_signals": [
            "Use cautious language and explain why confidence is low.",
            "Avoid upgrading low-confidence signals into firm conclusions.",
        ],
        "conflicting_signals": [
            "Describe disagreement across strategies before giving any synthesis.",
            "Prefer watch points and risk notes when directions diverge.",
        ],
        "insufficient_data_signals": [
            "State that the strategy conclusion is unavailable for the affected market window.",
            "Do not fabricate missing values or substitute raw OHLCV history.",
        ],
        "source_rules": [
            "Reference normalized market signals and quant strategy run artifacts.",
            "Do not calculate new quantitative signals from raw OHLCV history.",
            "Do not present diagnostics as forecasts or financial advice.",
        ],
    }


def _read_json_artifact(path, artifact: str, *, producer_stage: str, stage: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=stage,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact} is not valid JSON: {exc.msg}.",
            stage=stage,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{artifact} must be a JSON object.",
            stage=stage,
            exit_code=3,
        )
    return loaded


def _signals_from_artifact(artifact: dict[str, Any], *, stage: str) -> list[dict[str, Any]]:
    signals = artifact.get("signals")
    if not isinstance(signals, list):
        raise PipelineError(
            "market signal artifacts must contain a signals list.",
            stage=stage,
            exit_code=3,
        )
    for index, signal in enumerate(signals):
        if not isinstance(signal, dict):
            raise PipelineError(
                f"signals[{index}] must be a mapping.",
                stage=stage,
                exit_code=3,
            )
    return signals


def _strategy_runs_from_artifact(artifact: dict[str, Any], *, stage: str) -> list[dict[str, Any]]:
    runs = artifact.get("runs")
    if not isinstance(runs, list):
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} must contain a runs list.",
            stage=stage,
            exit_code=3,
        )
    for index, item in enumerate(runs):
        if not isinstance(item, dict):
            raise PipelineError(
                f"runs[{index}] must be a mapping.",
                stage=stage,
                exit_code=3,
            )
    return runs


def _created_at(strategy_artifact: dict[str, Any], now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc(now)
    created_at = strategy_artifact.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        return _format_utc(created_at)
    return _format_utc(None)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError("created_at must be an ISO 8601 UTC string.", exit_code=3) from exc
        if timestamp.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", exit_code=3)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError("created_at must be a datetime or ISO 8601 UTC string.", exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")


def _source_policy() -> dict[str, Any]:
    return {
        "signal_material_is_financial_advice": False,
        "trading_instructions_allowed": False,
        "raw_ohlcv_history_embedded": False,
        "vectorbt_objects_embedded": False,
        "backtest_diagnostics_are_historical_research_material": True,
        "backtest_diagnostics_are_forecasts": False,
        "parameter_diagnostics_are_optimization": False,
        "fabricate_missing_signals": False,
        "allowed_basis": [
            "normalized_market_signals",
            "bounded_input_window_metadata",
            "bounded_backtest_diagnostic_summaries",
            "bounded_parameter_diagnostic_summaries",
            "key_values",
            "evidence",
            "uncertainty",
        ],
    }


def _quant_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant")
    return isinstance(quant, dict) and quant.get("enabled") is True


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _warning_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    messages = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("message"), str):
            messages.append(item["message"])
        elif isinstance(item, str) and item.strip():
            messages.append(item)
    return messages


def _strategy_names(signals: list[dict[str, Any]]) -> list[str]:
    return _sorted_unique(signal.get("strategy_name") for signal in signals)


def _sorted_unique(values: Any) -> list[str]:
    return sorted({item for item in values if isinstance(item, str) and item.strip()})


def _count_by(signals: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signal in signals:
        value = signal.get(key)
        if not isinstance(value, str) or not value.strip():
            value = "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _strategy_run_status_counts(strategy_runs: dict[str, Any] | None) -> dict[str, int]:
    if strategy_runs is None:
        return {}
    runs = strategy_runs.get("runs")
    if not isinstance(runs, list):
        return {}
    counts: dict[str, int] = {}
    for run in runs:
        status = run.get("status") if isinstance(run, dict) else None
        if not isinstance(status, str) or not status.strip():
            status = "unknown"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _key_value(signal: dict[str, Any], key: str) -> Any:
    key_values = signal.get("key_values")
    if not isinstance(key_values, dict):
        return None
    return key_values.get(key)


def _diagnostic_summary(signal: dict[str, Any]) -> dict[str, Any]:
    key_values = signal.get("key_values")
    if not isinstance(key_values, dict):
        return {}
    result = {}
    for key in (
        "backtest_diagnostic_status",
        "parameter_diagnostic_status",
        "parameter_stability",
        "parameter_signal_state_stability",
        "parameter_performance_stability",
        "parameter_performance_stability_reason_codes",
        "parameter_tested_combinations",
        "parameter_valid_combinations",
        "parameter_invalid_combinations",
    ):
        if key in key_values:
            result[key] = key_values[key]
    return result


def _group_signals(signals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        key = _signal_group_key(signal)
        groups.setdefault(key, []).append(signal)
    return dict(sorted(groups.items()))


def _signal_group_key(signal: dict[str, Any]) -> str:
    return ":".join(
        str(signal.get(key) or "missing")
        for key in ("source", "symbol", "timeframe")
    )


def _group_report_note(
    *,
    has_conflict: bool,
    confluence_direction: str | None,
    insufficient_data: bool,
) -> str:
    if insufficient_data:
        return "At least one strategy lacks sufficient data; keep the report conclusion conditional."
    if has_conflict:
        return "Strategies disagree for this market window; describe the conflict before synthesis."
    if confluence_direction:
        return f"Multiple strategies support {confluence_direction} direction for this market window."
    return "Single-strategy context only; avoid presenting confluence."


def _has_backtest_diagnostic_summary(key_values: dict[str, Any]) -> bool:
    return any(key.startswith("backtest_") for key in key_values)


def _has_parameter_diagnostic_summary(key_values: dict[str, Any]) -> bool:
    return any(key.startswith("parameter_") for key in key_values)


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML market signal material records.",
            stage=BUILD_MARKET_SIGNAL_MATERIAL_STAGE,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
