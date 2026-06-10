from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .market_data_views import MARKET_DATA_VIEWS_ARTIFACT
from .pipeline import PipelineError, RunContext
from .storage import write_json


STAGE_NAME = "evaluate_market_strategy_signals"
MARKET_STRATEGY_SIGNALS_ARTIFACT = "analysis/market_strategy_signals.json"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
SIGNAL_SCHEMA_VERSION = 1


def evaluate_market_strategy_signals(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    quant = config.get("quant")
    if not isinstance(quant, dict) or quant.get("enabled") is not True:
        run.manifest["counts"]["market_strategy_signals"] = 0
        run.manifest["counts"]["market_strategy_signals_insufficient_data"] = 0
        return []

    return _build_signals_from_strategy_runs(run, now=now)


def _build_signals_from_strategy_runs(
    run: RunContext,
    *,
    now: datetime | str | None,
) -> list[str]:
    strategy_runs_artifact = _read_quant_strategy_runs(run)
    created_at = _created_at(strategy_runs_artifact, now)
    signals = [_strategy_run_signal(strategy_run, created_at) for strategy_run in strategy_runs_artifact["runs"]]
    artifact = {
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "artifact_type": "market_strategy_signals",
        "created_at": created_at,
        "source_artifacts": [QUANT_STRATEGY_RUNS_ARTIFACT, MARKET_DATA_VIEWS_ARTIFACT],
        "signals": signals,
    }
    write_json(run.analysis_dir / "market_strategy_signals.json", artifact)
    run.manifest["artifacts"]["market_strategy_signals"] = MARKET_STRATEGY_SIGNALS_ARTIFACT
    run.manifest["counts"]["market_strategy_signals"] = len(signals)
    run.manifest["counts"]["market_strategy_signals_insufficient_data"] = sum(
        1 for signal in signals if signal["insufficient_data"]
    )
    return [MARKET_STRATEGY_SIGNALS_ARTIFACT]


def _read_quant_strategy_runs(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "quant_strategy_runs.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} was not found; evaluate_quant_strategies must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict) or not isinstance(artifact.get("runs"), list):
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} must contain a runs list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    for index, strategy_run in enumerate(artifact["runs"]):
        if not isinstance(strategy_run, dict):
            raise PipelineError(
                f"runs[{index}] must be a mapping.",
                stage=STAGE_NAME,
                exit_code=3,
            )
    return artifact


def _strategy_run_signal(strategy_run: dict[str, Any], created_at: str) -> dict[str, Any]:
    assessment = strategy_run.get("assessment") if isinstance(strategy_run.get("assessment"), dict) else {}
    source_artifacts = _unique_ordered(
        [QUANT_STRATEGY_RUNS_ARTIFACT, *_string_list(strategy_run.get("source_artifacts"))]
    )
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
        "strategy_signal_id": (
            f"strategy_signal:{strategy_run.get('strategy_name')}:{strategy_run.get('source')}:"
            f"{strategy_run.get('symbol')}:{strategy_run.get('timeframe')}:{latest}"
        ),
        "strategy_name": strategy_run.get("strategy_name"),
        "source": strategy_run.get("source"),
        "symbol": strategy_run.get("symbol"),
        "timeframe": strategy_run.get("timeframe"),
        "input_view_id": strategy_run.get("input_view_id"),
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
        "source_artifacts": source_artifacts,
        "created_at": strategy_run.get("created_at") or created_at,
    }


def _strategy_run_key_values(strategy_run: dict[str, Any]) -> dict[str, Any]:
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
    if parameter.get("enabled") is True and "status" in parameter:
        result["parameter_diagnostic_status"] = parameter["status"]
        for key in ("tested_combinations", "valid_combinations", "invalid_combinations", "stability"):
            if key in parameter:
                result[f"parameter_{key}"] = parameter[key]
    return result


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


def _created_at(strategy_artifact: dict[str, Any], now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc(now)
    created_at = strategy_artifact.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        return _format_utc(created_at)
    return _format_utc(None)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError("created_at must be an ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3) from exc
        if timestamp.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError("created_at must be a datetime or ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")
