from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from .quant.registry import get_strategy_definition
from .quant.strategy_evaluation import evaluate_single_window_backtest
from .storage import display_path, ensure_directory, write_json


STRATEGY_BACKTEST_ARTIFACT = "strategy_backtest.json"
STANDALONE_MANIFEST_ARTIFACT = "manifest.json"
MAX_BACKTEST_VISUALIZATION_BARS = 120
MAX_BACKTEST_VISUALIZATION_MARKERS = 80


class StandaloneBacktestError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class StandaloneBacktestResult:
    succeeded: bool
    exit_code: int
    status: str
    reason: str | None
    output_dir: Path
    artifact_path: Path
    manifest_path: Path


def run_standalone_strategy_backtest(
    config: dict[str, Any],
    *,
    config_path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> StandaloneBacktestResult:
    clock_value = _utc_now(now)
    strategy = _configured_strategy(config, strategy_name)
    market = _market_config(config)
    ohlcv = _ohlcv_config(market)
    source = str(market["source"])
    _require_configured_symbol(market, symbol)
    _require_configured_timeframe(ohlcv, timeframe)

    storage_dir = _storage_dir(ohlcv, config_path)
    rows = _history_rows(
        storage_dir=storage_dir,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
    )
    if not rows:
        raise StandaloneBacktestError(
            f"no OHLCV history found for source={source}, symbol={symbol}, timeframe={timeframe}.",
            exit_code=3,
        )

    lookback = int(ohlcv["lookback"][timeframe])
    window = rows[-lookback:]
    view = _view_record(
        storage_dir=storage_dir,
        config_path=config_path,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        lookback=lookback,
        rows=window,
    )
    definition = get_strategy_definition(strategy_name)
    if definition is None:
        raise StandaloneBacktestError(f"strategy is not supported: {strategy_name}", exit_code=2)

    try:
        signals = definition.signal_records(strategy, view, window)
        evaluation = evaluate_single_window_backtest(
            strategy=strategy,
            market_identity={
                "source": source,
                "symbol": symbol,
                "timeframe": timeframe,
            },
            ohlcv_rows=window,
            signal_records=signals,
            cost_assumptions=_cost_assumptions(strategy),
        )
    except Exception as exc:
        raise StandaloneBacktestError(f"strategy backtest failed: {exc}", exit_code=3) from exc

    evaluation = {
        **evaluation,
        "visualization": _visualization_record(
            rows=window,
            evaluation=evaluation,
            strategy_name=strategy_name,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
        ),
    }
    target_dir = _unique_output_dir(
        _base_output_dir(config, config_path=config_path, output_dir=output_dir),
        _backtest_id(clock_value, strategy_name, source, symbol, timeframe),
    )
    artifact_path = target_dir / STRATEGY_BACKTEST_ARTIFACT
    manifest_path = target_dir / STANDALONE_MANIFEST_ARTIFACT
    write_json(artifact_path, evaluation)
    manifest = _manifest(
        config_path=config_path,
        created_at=_format_utc(clock_value),
        strategy=strategy,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        storage_dir=storage_dir,
        view=view,
        evaluation=evaluation,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
    )
    write_json(manifest_path, manifest)

    status = str(evaluation.get("status") or "failed")
    succeeded = status == "succeeded"
    reason = None if succeeded else _failure_reason(evaluation)
    return StandaloneBacktestResult(
        succeeded=succeeded,
        exit_code=0 if succeeded else 3,
        status=status,
        reason=reason,
        output_dir=target_dir,
        artifact_path=artifact_path,
        manifest_path=manifest_path,
    )


def _configured_strategy(config: dict[str, Any], strategy_name: str) -> dict[str, Any]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    if quant.get("enabled") is not True:
        raise StandaloneBacktestError("quant.enabled must be true for standalone backtest.", exit_code=2)
    strategies = quant.get("strategies")
    if not isinstance(strategies, list):
        raise StandaloneBacktestError("quant.strategies must be configured for standalone backtest.", exit_code=2)
    matches = [
        strategy
        for strategy in strategies
        if isinstance(strategy, dict)
        and strategy.get("name") == strategy_name
        and strategy.get("enabled", True) is not False
    ]
    if not matches:
        raise StandaloneBacktestError(
            f"strategy is not configured and enabled: {strategy_name}",
            exit_code=2,
        )
    return matches[0]


def _market_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict) or market.get("enabled") is not True:
        raise StandaloneBacktestError("market.enabled must be true for standalone backtest.", exit_code=2)
    return market


def _ohlcv_config(market: dict[str, Any]) -> dict[str, Any]:
    ohlcv = market.get("ohlcv")
    if not isinstance(ohlcv, dict):
        raise StandaloneBacktestError("market.ohlcv must be configured for standalone backtest.", exit_code=2)
    return ohlcv


def _require_configured_symbol(market: dict[str, Any], symbol: str) -> None:
    symbols = [str(value) for value in market.get("symbols", [])]
    if symbol not in symbols:
        raise StandaloneBacktestError(f"symbol is not configured: {symbol}", exit_code=2)


def _require_configured_timeframe(ohlcv: dict[str, Any], timeframe: str) -> None:
    timeframes = [str(value) for value in ohlcv.get("timeframes", [])]
    if timeframe not in timeframes:
        raise StandaloneBacktestError(f"timeframe is not configured: {timeframe}", exit_code=2)
    lookback = ohlcv.get("lookback")
    if not isinstance(lookback, dict) or timeframe not in lookback:
        raise StandaloneBacktestError(f"lookback is not configured for timeframe: {timeframe}", exit_code=2)


def _history_rows(
    *,
    storage_dir: Path,
    source: str,
    symbol: str,
    timeframe: str,
) -> list[dict[str, Any]]:
    store = OHLCVParquetStore(storage_dir)
    try:
        return store.read_records(source=source, symbol=symbol, timeframe=timeframe)
    except OHLCVStoreError as exc:
        raise StandaloneBacktestError(str(exc), exit_code=3) from exc


def _view_record(
    *,
    storage_dir: Path,
    config_path: Path,
    source: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    row_count = len(rows)
    latest = rows[-1]["open_time"] if rows else None
    return {
        "view_id": f"ohlcv_view:{source}:{symbol}:{timeframe}:{latest or 'missing'}",
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_lookback": lookback,
        "input_window_start": rows[0]["open_time"] if rows else None,
        "input_window_end": latest,
        "latest_candle_time": latest,
        "row_count": row_count,
        "storage_ref": display_path(
            storage_dir / f"source={source}" / f"symbol={symbol}" / f"timeframe={timeframe}",
            base=config_path.parent,
        ),
        "included_columns": ["open_time", "open", "high", "low", "close", "volume"],
        "insufficient_data": row_count < lookback,
        "warnings": []
        if row_count >= lookback
        else [
            (
                f"{source} {symbol} {timeframe} has {row_count} OHLCV rows, "
                f"below configured lookback {lookback}."
            )
        ],
    }


def _cost_assumptions(strategy: dict[str, Any]) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    return {
        "fees_bps": backtest.get("fees_bps", 0.0),
        "slippage_bps": backtest.get("slippage_bps", 0.0),
    }


def _visualization_record(
    *,
    rows: list[dict[str, Any]],
    evaluation: dict[str, Any],
    strategy_name: str,
    source: str,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    bars = [_visualization_bar(row) for row in rows]
    bars = [bar for bar in bars if bar is not None]
    visible_bars = bars[-MAX_BACKTEST_VISUALIZATION_BARS:]
    visible_times = {str(bar["time"]) for bar in visible_bars}
    full_equity_curve = _visualization_equity_curve(evaluation)
    equity_curve = [point for point in full_equity_curve if str(point["time"]) in visible_times]
    markers = [
        marker
        for marker in _visualization_markers(full_equity_curve, bars)
        if str(marker["time"]) in visible_times
    ]
    warnings = []
    if len(bars) < 2:
        warnings.append("Backtest visualization requires at least two OHLCV bars.")
    if not equity_curve:
        warnings.append("Backtest visualization has no equity curve points.")
    return {
        "schema_version": 1,
        "chart_type": "candlestick_backtest",
        "status": "available" if len(visible_bars) >= 2 and equity_curve else "partial",
        "strategy_name": strategy_name,
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": visible_bars,
        "markers": markers[:MAX_BACKTEST_VISUALIZATION_MARKERS],
        "equity_curve": equity_curve,
        "limits": {
            "max_bars": MAX_BACKTEST_VISUALIZATION_BARS,
            "max_markers": MAX_BACKTEST_VISUALIZATION_MARKERS,
        },
        "omitted": {
            "bars": max(0, len(bars) - len(visible_bars)),
            "markers": max(0, len(markers) - MAX_BACKTEST_VISUALIZATION_MARKERS),
        },
        "warnings": warnings,
    }


def _visualization_bar(row: dict[str, Any]) -> dict[str, Any] | None:
    time_value = row.get("open_time")
    if time_value is None or str(time_value) == "":
        return None
    try:
        return {
            "time": str(time_value),
            "open": _round_float(row.get("open")),
            "high": _round_float(row.get("high")),
            "low": _round_float(row.get("low")),
            "close": _round_float(row.get("close")),
            "volume": _optional_round_float(row.get("volume")),
        }
    except (TypeError, ValueError):
        return None


def _visualization_equity_curve(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    curve = evaluation.get("equity_curve")
    if not isinstance(curve, list):
        return []
    visible = []
    for point in curve:
        if not isinstance(point, dict):
            continue
        time_value = point.get("open_time") or point.get("timestamp")
        if time_value is None or str(time_value) == "":
            continue
        net_equity = point.get("net_equity", point.get("equity"))
        try:
            visible.append(
                {
                    "time": str(time_value),
                    "net_equity": _round_float(net_equity),
                    "gross_equity": _optional_round_float(point.get("gross_equity")),
                    "position": _optional_round_float(point.get("position")),
                    "turnover": _optional_round_float(point.get("turnover")),
                }
            )
        except (TypeError, ValueError):
            continue
    return visible


def _visualization_markers(
    equity_curve: list[dict[str, Any]],
    bars: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bars_by_time = {str(bar["time"]): bar for bar in bars}
    markers = []
    previous_position = 0.0
    for point in equity_curve:
        position = point.get("position")
        if position is None:
            continue
        position_value = float(position)
        time_value = str(point["time"])
        bar = bars_by_time.get(time_value)
        price = bar.get("close") if bar else None
        if position_value > 0 and previous_position <= 0:
            markers.append(
                {
                    "time": time_value,
                    "kind": "entry",
                    "label": "Long",
                    "position": _round_float(position_value),
                    "price": price,
                }
            )
        elif position_value <= 0 and previous_position > 0:
            markers.append(
                {
                    "time": time_value,
                    "kind": "exit",
                    "label": "Flat",
                    "position": _round_float(position_value),
                    "price": price,
                }
            )
        elif position_value > 0 and previous_position > 0 and abs(position_value - previous_position) > 1e-9:
            markers.append(
                {
                    "time": time_value,
                    "kind": "exposure_change",
                    "label": "Exposure",
                    "position": _round_float(position_value),
                    "price": price,
                }
            )
        previous_position = position_value
    return markers


def _round_float(value: Any) -> float:
    return round(float(value), 8)


def _optional_round_float(value: Any) -> float | None:
    if value is None:
        return None
    return _round_float(value)


def _manifest(
    *,
    config_path: Path,
    created_at: str,
    strategy: dict[str, Any],
    source: str,
    symbol: str,
    timeframe: str,
    storage_dir: Path,
    view: dict[str, Any],
    evaluation: dict[str, Any],
    artifact_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "standalone_strategy_backtest_manifest",
        "created_at": created_at,
        "status": "succeeded" if evaluation.get("status") == "succeeded" else "failed",
        "evaluation_status": evaluation.get("status"),
        "config_path": display_path(config_path, base=config_path.parent),
        "inputs": {
            "strategy_name": strategy.get("name"),
            "source": source,
            "symbol": symbol,
            "timeframe": timeframe,
            "params": strategy.get("params") if isinstance(strategy.get("params"), dict) else {},
            "storage_dir": display_path(storage_dir, base=config_path.parent),
            "input_view_id": view.get("view_id"),
        },
        "artifacts": {
            "strategy_backtest": display_path(artifact_path, base=manifest_path.parent),
            "manifest": display_path(manifest_path, base=manifest_path.parent),
        },
        "warnings": evaluation.get("warnings", []),
        "errors": evaluation.get("errors", []),
    }


def _failure_reason(evaluation: dict[str, Any]) -> str:
    errors = evaluation.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict) and first.get("message"):
            return str(first["message"])
    warnings = evaluation.get("warnings")
    if isinstance(warnings, list) and warnings:
        first = warnings[0]
        if isinstance(first, dict) and first.get("message"):
            return str(first["message"])
    return f"strategy evaluation status is {evaluation.get('status')}"


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


def _base_output_dir(config: dict[str, Any], *, config_path: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    root = Path(str(run.get("output_dir") or "runs"))
    if not root.is_absolute():
        root = config_path.parent / root
    return root / "strategy_backtests"


def _unique_output_dir(output_dir: Path, backtest_id: str) -> Path:
    ensure_directory(output_dir)
    candidate = output_dir / backtest_id
    if not candidate.exists():
        candidate.mkdir()
        return candidate
    for index in range(1, 100):
        candidate = output_dir / f"{backtest_id}-{index:02d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise StandaloneBacktestError(f"could not create a unique output directory for {backtest_id}.")


def _backtest_id(now: datetime, strategy_name: str, source: str, symbol: str, timeframe: str) -> str:
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "_".join(
        [
            timestamp,
            _slug(strategy_name),
            _slug(source),
            _slug(symbol),
            _slug(timeframe),
        ]
    )


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "value"


def _utc_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise StandaloneBacktestError("now must include a UTC offset.", exit_code=2)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
