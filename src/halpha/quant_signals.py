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
            "row_count": len(rows),
        },
        evidence=[
            f"return_std_pct is {_round(volatility_pct)}% over the selected OHLCV window.",
            f"average_abs_return_pct is {_round(average_abs_return_pct)}% over the selected OHLCV window.",
        ],
        uncertainty=["Volatility describes price variation only and does not provide directional evidence."],
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
            "row_count": len(rows),
        },
        evidence=[
            f"latest_volume is {_round(volume_ratio)} times the previous-window average volume."
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
    configured = [str(signal) for signal in quant.get("signals", [])]
    return [signal for signal in configured if signal in INITIAL_STRATEGIES]


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("open_time")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    return frame


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
