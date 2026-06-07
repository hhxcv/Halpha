from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .market_data_views import MARKET_DATA_VIEWS_ARTIFACT, load_market_data_view_records
from .pipeline import PipelineError, RunContext
from .storage import write_json


STAGE_NAME = "evaluate_market_strategy_signals"
MARKET_STRATEGY_SIGNALS_ARTIFACT = "analysis/market_strategy_signals.json"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
SIGNAL_SCHEMA_VERSION = 1
INITIAL_STRATEGIES = ("trend", "momentum", "volatility", "volume_anomaly")
MIN_SIGNAL_ROWS = 2

Evaluator = Callable[[dict[str, Any], list[dict[str, Any]], str], dict[str, Any]]


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

    if _uses_strategy_runs(quant):
        return _build_signals_from_strategy_runs(run, now=now)

    views_artifact = _read_market_data_views(run)
    storage_dir = _storage_dir(config, run.config_path)
    created_at = _format_utc(now)
    signals = []
    for view in views_artifact.get("views", []):
        rows = load_market_data_view_records(view, storage_dir=storage_dir)
        for strategy in _configured_strategies(quant):
            signals.append(_evaluate_strategy(strategy, view, rows, created_at))

    artifact = {
        "schema_version": SIGNAL_SCHEMA_VERSION,
        "artifact_type": "market_strategy_signals",
        "created_at": created_at,
        "source_artifacts": [MARKET_DATA_VIEWS_ARTIFACT],
        "signals": signals,
    }
    write_json(run.analysis_dir / "market_strategy_signals.json", artifact)
    run.manifest["artifacts"]["market_strategy_signals"] = MARKET_STRATEGY_SIGNALS_ARTIFACT
    run.manifest["counts"]["market_strategy_signals"] = len(signals)
    run.manifest["counts"]["market_strategy_signals_insufficient_data"] = sum(
        1 for signal in signals if signal["insufficient_data"]
    )
    return [MARKET_STRATEGY_SIGNALS_ARTIFACT]


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
    uncertainty = [
        *_string_list(assessment.get("uncertainty")),
        *warnings,
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
    keys = (
        "latest_close",
        "return_window_pct",
        "latest_return_pct",
        "realized_volatility_pct",
        "target_volatility_pct",
        "volatility_scaled_exposure",
        "row_count",
    )
    result = {key: indicators[key] for key in keys if key in indicators}
    for key in ("latest_regime", "entry_count", "exit_count", "latest_signal_active"):
        if key in signals:
            result[key] = signals[key]
    if "status" in backtest:
        result["backtest_diagnostic_status"] = backtest["status"]
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


def _read_market_data_views(run: RunContext) -> dict[str, Any]:
    path = run.raw_dir / "market_data_views.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{MARKET_DATA_VIEWS_ARTIFACT} was not found; build_market_data_views must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{MARKET_DATA_VIEWS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict) or not isinstance(artifact.get("views"), list):
        raise PipelineError(
            f"{MARKET_DATA_VIEWS_ARTIFACT} must contain a views list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _evaluate_strategy(
    strategy: str,
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    if strategy not in EVALUATORS:
        return _insufficient_signal(
            strategy,
            view,
            rows,
            created_at,
            uncertainty=f"{strategy} is configured but not implemented in the initial evaluator set.",
        )
    if _input_is_insufficient(view, rows):
        return _insufficient_signal(
            strategy,
            view,
            rows,
            created_at,
            uncertainty=_insufficient_uncertainty(view, rows),
        )
    return EVALUATORS[strategy](view, rows, created_at)


def _trend_signal(view: dict[str, Any], rows: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    frame = _frame(rows)
    latest_close = float(frame["close"].iloc[-1])
    short_window = min(5, max(1, (len(frame) + 1) // 2))
    long_window = min(20, len(frame))
    short_mean = float(frame["close"].tail(short_window).mean())
    long_mean = float(frame["close"].tail(long_window).mean())
    close_vs_long_pct = _pct_change(latest_close, long_mean)
    short_vs_long_pct = _pct_change(short_mean, long_mean)
    direction = _trend_direction(close_vs_long_pct, short_vs_long_pct)
    strength = _strength_from_pct(max(abs(close_vs_long_pct), abs(short_vs_long_pct)))

    evidence = [
        _comparison_evidence("latest_close", latest_close, "moving_average_long", long_mean),
        _comparison_evidence("moving_average_short", short_mean, "moving_average_long", long_mean),
    ]
    return _signal_record(
        strategy="trend",
        view=view,
        created_at=created_at,
        direction=direction,
        strength=strength,
        confidence=_confidence(len(rows)),
        key_values={
            "latest_close": _round(latest_close),
            "moving_average_short": _round(short_mean),
            "moving_average_long": _round(long_mean),
            "close_vs_long_pct": _round(close_vs_long_pct),
            "short_vs_long_pct": _round(short_vs_long_pct),
            "row_count": len(rows),
        },
        evidence=evidence,
        uncertainty=["Trend uses OHLCV close prices only and excludes text events."],
        insufficient_data=False,
    )


def _momentum_signal(view: dict[str, Any], rows: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    frame = _frame(rows)
    first_close = float(frame["close"].iloc[0])
    previous_close = float(frame["close"].iloc[-2])
    latest_close = float(frame["close"].iloc[-1])
    window_return_pct = _pct_change(latest_close, first_close)
    latest_return_pct = _pct_change(latest_close, previous_close)

    return _signal_record(
        strategy="momentum",
        view=view,
        created_at=created_at,
        direction=_direction_from_pct(window_return_pct),
        strength=_strength_from_pct(abs(window_return_pct)),
        confidence=_confidence(len(rows)),
        key_values={
            "first_close": _round(first_close),
            "previous_close": _round(previous_close),
            "latest_close": _round(latest_close),
            "window_return_pct": _round(window_return_pct),
            "latest_return_pct": _round(latest_return_pct),
            "row_count": len(rows),
        },
        evidence=[
            f"window_return_pct is {_round(window_return_pct)}% from input_window_start to input_window_end.",
            f"latest_return_pct is {_round(latest_return_pct)}% for the latest candle interval.",
        ],
        uncertainty=["Momentum uses OHLCV close prices only and excludes text events."],
        insufficient_data=False,
    )


def _volatility_signal(view: dict[str, Any], rows: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    frame = _frame(rows)
    returns_pct = frame["close"].pct_change().dropna() * 100
    volatility_pct = float(returns_pct.std(ddof=0))
    average_abs_return_pct = float(returns_pct.abs().mean())
    range_pct_values = _range_pct_values(frame)
    latest_range_pct = range_pct_values[-1]
    average_range_pct = sum(range_pct_values) / len(range_pct_values)
    max_range_pct = max(range_pct_values)

    return _signal_record(
        strategy="volatility",
        view=view,
        created_at=created_at,
        direction="unknown",
        strength=_volatility_strength(volatility_pct),
        confidence=_confidence(len(rows)),
        key_values={
            "return_std_pct": _round(volatility_pct),
            "average_abs_return_pct": _round(average_abs_return_pct),
            "latest_range_pct": _round(latest_range_pct),
            "average_range_pct": _round(average_range_pct),
            "max_range_pct": _round(max_range_pct),
            "row_count": len(rows),
        },
        evidence=[
            f"return_std_pct is {_round(volatility_pct)}% over the selected OHLCV window.",
            f"average_abs_return_pct is {_round(average_abs_return_pct)}% over the selected OHLCV window.",
            f"latest_range_pct is {_round(latest_range_pct)}% for the latest candle.",
            f"average_range_pct is {_round(average_range_pct)}% over the selected OHLCV window.",
        ],
        uncertainty=[
            "Volatility describes price variation and candle ranges only and does not provide directional evidence."
        ],
        insufficient_data=False,
    )


def _volume_anomaly_signal(
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    frame = _frame(rows)
    latest_volume = float(frame["volume"].iloc[-1])
    previous_average_volume = float(frame["volume"].iloc[:-1].mean())
    volume_ratio = latest_volume / previous_average_volume if previous_average_volume else 0.0
    volume_change_pct = _pct_change(latest_volume, previous_average_volume)

    return _signal_record(
        strategy="volume_anomaly",
        view=view,
        created_at=created_at,
        direction="unknown",
        strength=_volume_strength(volume_ratio),
        confidence=_confidence(len(rows)),
        key_values={
            "latest_volume": _round(latest_volume),
            "previous_average_volume": _round(previous_average_volume),
            "volume_ratio": _round(volume_ratio),
            "volume_change_pct": _round(volume_change_pct),
            "row_count": len(rows),
        },
        evidence=[
            f"latest_volume is {_round(volume_ratio)} times the previous-window average volume.",
            f"volume_change_pct is {_round(volume_change_pct)}% against the previous-window average volume.",
        ],
        uncertainty=["Volume anomaly describes activity level only and does not provide directional evidence."],
        insufficient_data=False,
    )


EVALUATORS: dict[str, Evaluator] = {
    "trend": _trend_signal,
    "momentum": _momentum_signal,
    "volatility": _volatility_signal,
    "volume_anomaly": _volume_anomaly_signal,
}


def _signal_record(
    *,
    strategy: str,
    view: dict[str, Any],
    created_at: str,
    direction: str,
    strength: str,
    confidence: str,
    key_values: dict[str, Any],
    evidence: list[str],
    uncertainty: list[str],
    insufficient_data: bool,
) -> dict[str, Any]:
    latest = view.get("latest_candle_time") or "missing"
    return {
        "strategy_signal_id": (
            f"strategy_signal:{strategy}:{view.get('source')}:{view.get('symbol')}:"
            f"{view.get('timeframe')}:{latest}"
        ),
        "strategy_name": strategy,
        "source": view.get("source"),
        "symbol": view.get("symbol"),
        "timeframe": view.get("timeframe"),
        "input_view_id": view.get("view_id"),
        "input_window_start": view.get("input_window_start"),
        "input_window_end": view.get("input_window_end"),
        "latest_candle_time": view.get("latest_candle_time"),
        "direction": direction,
        "strength": strength,
        "confidence": confidence,
        "key_values": key_values,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "insufficient_data": insufficient_data,
        "source_artifacts": [MARKET_DATA_VIEWS_ARTIFACT],
        "created_at": created_at,
    }


def _insufficient_signal(
    strategy: str,
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    created_at: str,
    *,
    uncertainty: str,
) -> dict[str, Any]:
    row_count = len(rows)
    requested_lookback = view.get("requested_lookback")
    return _signal_record(
        strategy=strategy,
        view=view,
        created_at=created_at,
        direction="unknown",
        strength="unknown",
        confidence="low",
        key_values={
            "row_count": row_count,
            "requested_lookback": requested_lookback,
        },
        evidence=[
            f"input view has {row_count} OHLCV rows for requested_lookback {requested_lookback}."
        ],
        uncertainty=[uncertainty],
        insufficient_data=True,
    )


def _input_is_insufficient(view: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    return bool(view.get("insufficient_data")) or len(rows) < MIN_SIGNAL_ROWS


def _insufficient_uncertainty(view: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    return (
        f"{view.get('source')} {view.get('symbol')} {view.get('timeframe')} has "
        f"{len(rows)} OHLCV rows, below the initial evaluator minimum {MIN_SIGNAL_ROWS} "
        f"or the configured lookback."
    )


def _configured_strategies(quant: dict[str, Any]) -> list[str]:
    return [str(signal) for signal in quant.get("signals", [])]


def _uses_strategy_runs(quant: dict[str, Any]) -> bool:
    return isinstance(quant.get("strategies"), list)


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


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("open_time")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    return frame


def _range_pct_values(frame: pd.DataFrame) -> list[float]:
    values = []
    for row in frame.itertuples(index=False):
        close = float(row.close)
        if close == 0:
            values.append(0.0)
        else:
            values.append(((float(row.high) - float(row.low)) / close) * 100)
    return values


def _storage_dir(config: dict[str, Any], config_path: Path) -> Path:
    ohlcv = config.get("market", {}).get("ohlcv", {})
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


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


def _pct_change(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return ((current - baseline) / baseline) * 100


def _trend_direction(close_vs_long_pct: float, short_vs_long_pct: float) -> str:
    threshold = 0.25
    if close_vs_long_pct > threshold and short_vs_long_pct > threshold:
        return "bullish"
    if close_vs_long_pct < -threshold and short_vs_long_pct < -threshold:
        return "bearish"
    if abs(close_vs_long_pct) <= threshold and abs(short_vs_long_pct) <= threshold:
        return "neutral"
    return "mixed"


def _direction_from_pct(value: float) -> str:
    threshold = 0.5
    if value > threshold:
        return "bullish"
    if value < -threshold:
        return "bearish"
    return "neutral"


def _strength_from_pct(value: float) -> str:
    if value >= 5:
        return "high"
    if value >= 1:
        return "medium"
    return "low"


def _volatility_strength(value: float) -> str:
    if value >= 3:
        return "high"
    if value >= 1:
        return "medium"
    return "low"


def _volume_strength(value: float) -> str:
    if value >= 2:
        return "high"
    if value >= 1.25:
        return "medium"
    return "low"


def _confidence(row_count: int) -> str:
    if row_count >= 20:
        return "high"
    return "medium"


def _comparison_evidence(left_name: str, left: float, right_name: str, right: float) -> str:
    if left > right:
        relation = "above"
    elif left < right:
        relation = "below"
    else:
        relation = "equal to"
    return f"{left_name} is {relation} {right_name}."


def _round(value: float) -> float:
    return round(float(value), 6)
