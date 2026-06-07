from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd

from .market_data_views import MARKET_DATA_VIEWS_ARTIFACT, load_market_data_view_records
from .pipeline import PipelineError, RunContext
from .storage import write_json


STAGE_NAME = "evaluate_quant_strategies"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
SCHEMA_VERSION = 1
STRATEGY_VERSION = 1
DEFAULT_TSMOM_PARAMS = {
    "return_window": 20,
    "volatility_window": 20,
    "target_volatility": 0.2,
}


def evaluate_quant_strategies(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    quant = config.get("quant")
    if not _strategy_config_enabled(quant):
        _record_zero_counts(run)
        return []

    views_artifact = _read_market_data_views(run)
    storage_dir = _storage_dir(config, run.config_path)
    created_at = _format_utc(now)
    enabled, disabled = _configured_strategies(quant)
    engine = _engine_metadata()
    runs = []

    for view in views_artifact.get("views", []):
        rows = load_market_data_view_records(view, storage_dir=storage_dir)
        for strategy in enabled:
            runs.append(_run_strategy(strategy, view, rows, engine=engine, created_at=created_at))

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "quant_strategy_runs",
        "created_at": created_at,
        "engine": {
            **engine,
            "objects_exposed": False,
        },
        "source_artifacts": [MARKET_DATA_VIEWS_ARTIFACT],
        "runs": runs,
    }
    write_json(run.analysis_dir / "quant_strategy_runs.json", artifact)
    run.manifest["artifacts"]["quant_strategy_runs"] = QUANT_STRATEGY_RUNS_ARTIFACT
    _record_manifest_counts(run, runs)
    _record_manifest_summary(run, engine=engine, enabled=enabled, disabled=disabled, runs=runs)
    return [QUANT_STRATEGY_RUNS_ARTIFACT]


def _strategy_config_enabled(quant: Any) -> bool:
    return isinstance(quant, dict) and quant.get("enabled") is True and isinstance(quant.get("strategies"), list)


def _configured_strategies(quant: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    enabled = []
    disabled = []
    for strategy in quant.get("strategies", []):
        name = str(strategy["name"])
        if strategy.get("enabled", True) is False:
            disabled.append(name)
            continue
        enabled.append(strategy)
    return enabled, disabled


def _run_strategy(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    engine: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    name = str(strategy["name"])
    try:
        if name == "tsmom_vol_scaled":
            return _run_tsmom_vol_scaled(strategy, view, rows, engine=engine, created_at=created_at)
        return _failed_run(
            strategy,
            view,
            engine=engine,
            created_at=created_at,
            error_type="UnsupportedStrategy",
            message=f"{name} is not implemented.",
        )
    except Exception as exc:
        return _failed_run(
            strategy,
            view,
            engine=engine,
            created_at=created_at,
            error_type=type(exc).__name__,
            message=str(exc),
        )


def _run_tsmom_vol_scaled(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    engine: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    params = _tsmom_params(strategy.get("params"))
    minimum_rows = max(params["return_window"], params["volatility_window"]) + 1
    if _input_is_insufficient(view, rows, minimum_rows=minimum_rows):
        return _insufficient_run(
            strategy,
            view,
            rows,
            params=params,
            engine=engine,
            created_at=created_at,
            minimum_rows=minimum_rows,
        )

    frame = _frame(rows)
    close = frame["close"]
    returns = close.pct_change()
    return_window = int(params["return_window"])
    volatility_window = int(params["volatility_window"])
    target_volatility = float(params["target_volatility"])
    latest_close = float(close.iloc[-1])
    baseline_close = float(close.iloc[-return_window - 1])
    return_window_pct = _pct_change(latest_close, baseline_close)
    latest_return_pct = _pct_change(float(close.iloc[-1]), float(close.iloc[-2]))
    realized_volatility = _annualized_volatility(
        returns.tail(volatility_window),
        timeframe=str(view.get("timeframe")),
    )
    realized_volatility_pct = realized_volatility * 100
    exposure = _volatility_scaled_exposure(target_volatility, realized_volatility)
    signal_series = close.pct_change(return_window) > 0
    entry_count = _transition_count(signal_series, from_value=False, to_value=True)
    exit_count = _transition_count(signal_series, from_value=True, to_value=False)
    latest_signal = bool(signal_series.iloc[-1])
    previous_signal = bool(signal_series.iloc[-2])
    latest_entry = latest_signal and not previous_signal
    latest_exit = previous_signal and not latest_signal
    direction = _direction(return_window_pct)
    strength = _strength(abs(return_window_pct))
    warnings = _strategy_warnings(realized_volatility, target_volatility)
    confidence = _confidence(len(rows), minimum_rows=minimum_rows, warnings=warnings)
    latest_regime = _latest_regime(
        return_window_pct=return_window_pct,
        exposure=exposure,
        target_volatility=target_volatility,
        realized_volatility=realized_volatility,
    )

    indicators = {
        "latest_close": _round(latest_close),
        "baseline_close": _round(baseline_close),
        "return_window_pct": _round(return_window_pct),
        "latest_return_pct": _round(latest_return_pct),
        "realized_volatility_pct": _round(realized_volatility_pct),
        "target_volatility_pct": _round(target_volatility * 100),
        "volatility_scaled_exposure": _round(exposure),
        "row_count": len(rows),
    }
    signals = {
        "latest_regime": latest_regime,
        "entry_count": entry_count,
        "exit_count": exit_count,
        "latest_entry": latest_entry,
        "latest_exit": latest_exit,
        "latest_signal_active": latest_signal,
    }
    return _strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="succeeded",
        params=params,
        data_quality=_data_quality(view, rows, minimum_rows=minimum_rows, sufficient=True),
        indicators=indicators,
        signals=signals,
        backtest_diagnostic=_backtest_diagnostic(strategy, view, rows, status="skipped"),
        parameter_diagnostic=_parameter_diagnostic(),
        assessment={
            "direction": direction,
            "strength": strength,
            "confidence": confidence,
            "summary": _assessment_summary(direction, latest_regime, warnings),
            "evidence": [
                f"return_window_pct is {_round(return_window_pct)}% over the configured return window.",
                f"realized_volatility_pct is {_round(realized_volatility_pct)}% against target_volatility_pct {_round(target_volatility * 100)}%.",
                f"volatility_scaled_exposure is {_round(exposure)}.",
            ],
            "uncertainty": [
                "Strategy uses OHLCV close prices only and excludes text events.",
                "Volatility scaling is a bounded research assumption, not position sizing advice.",
            ],
        },
        warnings=warnings,
        error=None,
    )


def _strategy_run_record(
    *,
    strategy: dict[str, Any],
    view: dict[str, Any],
    engine: dict[str, str],
    created_at: str,
    status: str,
    params: dict[str, Any],
    data_quality: dict[str, Any],
    indicators: dict[str, Any],
    signals: dict[str, Any],
    backtest_diagnostic: dict[str, Any],
    parameter_diagnostic: dict[str, Any],
    assessment: dict[str, Any],
    warnings: list[dict[str, Any]],
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    name = str(strategy["name"])
    latest = view.get("latest_candle_time") or "missing"
    return {
        "strategy_run_id": f"quant_strategy_run:{name}:{view.get('source')}:{view.get('symbol')}:{view.get('timeframe')}:{latest}",
        "status": status,
        "strategy_name": name,
        "strategy_version": STRATEGY_VERSION,
        "engine": engine,
        "source": view.get("source"),
        "symbol": view.get("symbol"),
        "timeframe": view.get("timeframe"),
        "input_view_id": view.get("view_id"),
        "input_window_start": view.get("input_window_start"),
        "input_window_end": view.get("input_window_end"),
        "latest_candle_time": view.get("latest_candle_time"),
        "params": params,
        "data_quality": data_quality,
        "indicators": indicators,
        "signals": signals,
        "backtest_diagnostic": backtest_diagnostic,
        "parameter_diagnostic": parameter_diagnostic,
        "assessment": assessment,
        "warnings": warnings,
        "error": error,
        "source_artifacts": [MARKET_DATA_VIEWS_ARTIFACT],
        "created_at": created_at,
    }


def _insufficient_run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    engine: dict[str, str],
    created_at: str,
    minimum_rows: int,
) -> dict[str, Any]:
    warning = _warning(
        "insufficient_ohlcv_rows",
        (
            f"{view.get('source')} {view.get('symbol')} {view.get('timeframe')} has "
            f"{len(rows)} OHLCV rows; tsmom_vol_scaled requires at least {minimum_rows} rows."
        ),
        source="data_quality",
    )
    return _strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="insufficient_data",
        params=params,
        data_quality=_data_quality(view, rows, minimum_rows=minimum_rows, sufficient=False, warnings=[warning]),
        indicators={},
        signals={},
        backtest_diagnostic=_backtest_diagnostic(strategy, view, rows, status="skipped"),
        parameter_diagnostic=_parameter_diagnostic(),
        assessment={
            "direction": "unknown",
            "strength": "unknown",
            "confidence": "low",
            "summary": "Strategy result is unavailable because input data is insufficient.",
            "evidence": [f"input view has {len(rows)} OHLCV rows."],
            "uncertainty": ["Insufficient data prevents strategy assessment."],
        },
        warnings=[warning],
        error=None,
    )


def _failed_run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    *,
    engine: dict[str, str],
    created_at: str,
    error_type: str,
    message: str,
) -> dict[str, Any]:
    params = _tsmom_params(strategy.get("params")) if strategy.get("name") == "tsmom_vol_scaled" else {}
    return _strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="failed",
        params=params,
        data_quality=_data_quality(view, [], minimum_rows=0, sufficient=False),
        indicators={},
        signals={},
        backtest_diagnostic=_backtest_diagnostic(strategy, view, [], status="skipped"),
        parameter_diagnostic=_parameter_diagnostic(),
        assessment={
            "direction": "unknown",
            "strength": "unknown",
            "confidence": "low",
            "summary": "Strategy run failed before assessment.",
            "evidence": [],
            "uncertainty": ["No strategy conclusion is available because execution failed."],
        },
        warnings=[],
        error={
            "error_type": error_type,
            "message": message,
            "stage": STAGE_NAME,
        },
    )


def _tsmom_params(raw: Any) -> dict[str, Any]:
    params = dict(DEFAULT_TSMOM_PARAMS)
    if isinstance(raw, dict):
        params.update(raw)
    return_window = _positive_int(params["return_window"], "return_window")
    volatility_window = _positive_int(params["volatility_window"], "volatility_window")
    target_volatility = _positive_number(params["target_volatility"], "target_volatility")
    return {
        "return_window": return_window,
        "volatility_window": volatility_window,
        "target_volatility": target_volatility,
    }


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _positive_number(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0:
        raise ValueError(f"{name} must be a positive number.")
    return float(value)


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


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("open_time")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    return frame


def _input_is_insufficient(view: dict[str, Any], rows: list[dict[str, Any]], *, minimum_rows: int) -> bool:
    return bool(view.get("insufficient_data")) or len(rows) < minimum_rows


def _data_quality(
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    minimum_rows: int,
    sufficient: bool,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "requested_lookback": view.get("requested_lookback"),
        "minimum_required_rows": minimum_rows,
        "sufficient_data": sufficient,
        "missing_row_policy": "do_not_fabricate",
        "warnings": warnings or [],
    }


def _backtest_diagnostic(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    status: str,
) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    enabled = bool(backtest.get("enabled", False))
    if not enabled:
        return {
            "enabled": False,
            "status": "disabled",
        }
    return {
        "enabled": True,
        "status": status,
        "assumptions": {
            "fees_bps": backtest.get("fees_bps"),
            "slippage_bps": backtest.get("slippage_bps"),
            "mode": backtest.get("mode", "long_flat"),
            "price_source": "close",
            "execution_timing": "research_close_to_close",
        },
        "window": {
            "start": view.get("input_window_start"),
            "end": view.get("input_window_end"),
            "rows": len(rows),
        },
        "metrics": {},
        "warnings": [
            "Bounded backtest diagnostics are intentionally deferred to a later M2 task.",
            "Historical diagnostics are research material, not return forecasts.",
        ],
    }


def _parameter_diagnostic() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "disabled",
    }


def _engine_metadata() -> dict[str, str]:
    try:
        version = metadata.version("vectorbt")
    except metadata.PackageNotFoundError:
        version = "unknown"
    return {
        "name": "vectorbt",
        "version": version,
    }


def _annualized_volatility(returns: pd.Series, *, timeframe: str) -> float:
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    periods = 365 * 24 if timeframe == "1h" else 365
    return float(clean.std(ddof=0)) * math.sqrt(periods)


def _volatility_scaled_exposure(target_volatility: float, realized_volatility: float) -> float:
    if realized_volatility <= 0:
        return 1.0
    return max(0.0, min(1.0, target_volatility / realized_volatility))


def _transition_count(series: pd.Series, *, from_value: bool, to_value: bool) -> int:
    clean = series.fillna(False).astype(bool)
    previous = clean.shift(1, fill_value=False)
    return int(((previous == from_value) & (clean == to_value)).sum())


def _strategy_warnings(realized_volatility: float, target_volatility: float) -> list[dict[str, Any]]:
    if target_volatility > 0 and realized_volatility > target_volatility * 1.5:
        return [
            _warning(
                "high_realized_volatility",
                "Realized volatility is elevated relative to the target volatility assumption.",
                source="strategy",
            )
        ]
    return []


def _warning(code: str, message: str, *, source: str) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "source": source,
    }


def _direction(return_window_pct: float) -> str:
    if return_window_pct > 0:
        return "bullish"
    if return_window_pct < 0:
        return "bearish"
    return "neutral"


def _strength(value: float) -> str:
    if value >= 10:
        return "high"
    if value >= 3:
        return "medium"
    return "low"


def _confidence(row_count: int, *, minimum_rows: int, warnings: list[dict[str, Any]]) -> str:
    if warnings:
        return "medium"
    if row_count >= max(minimum_rows * 2, 60):
        return "high"
    return "medium"


def _latest_regime(
    *,
    return_window_pct: float,
    exposure: float,
    target_volatility: float,
    realized_volatility: float,
) -> str:
    if return_window_pct < 0:
        return "risk_off_negative_momentum"
    if return_window_pct == 0:
        return "neutral"
    if target_volatility > 0 and realized_volatility > target_volatility * 1.5:
        return "risk_limited_momentum"
    if exposure < 0.5:
        return "risk_limited_momentum"
    return "risk_on_momentum"


def _assessment_summary(direction: str, latest_regime: str, warnings: list[dict[str, Any]]) -> str:
    if direction == "bullish" and warnings:
        return "Positive time-series momentum is present, but volatility keeps confidence bounded."
    if direction == "bullish":
        return f"Positive time-series momentum is present with latest regime {latest_regime}."
    if direction == "bearish":
        return f"Negative time-series momentum is present with latest regime {latest_regime}."
    return "Time-series momentum is neutral over the configured return window."


def _storage_dir(config: dict[str, Any], config_path: Path) -> Path:
    ohlcv = config.get("market", {}).get("ohlcv", {})
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


def _record_zero_counts(run: RunContext) -> None:
    run.manifest["counts"]["quant_strategy_runs"] = 0
    run.manifest["counts"]["quant_strategy_runs_succeeded"] = 0
    run.manifest["counts"]["quant_strategy_runs_failed"] = 0
    run.manifest["counts"]["quant_strategy_runs_insufficient_data"] = 0
    run.manifest["counts"]["quant_strategy_runs_skipped"] = 0
    run.manifest["counts"]["quant_strategy_runs_disabled"] = 0


def _record_manifest_counts(run: RunContext, runs: list[dict[str, Any]]) -> None:
    run.manifest["counts"]["quant_strategy_runs"] = len(runs)
    for status in ("succeeded", "failed", "insufficient_data", "skipped", "disabled"):
        run.manifest["counts"][f"quant_strategy_runs_{status}"] = sum(
            1 for item in runs if item.get("status") == status
        )


def _record_manifest_summary(
    run: RunContext,
    *,
    engine: dict[str, str],
    enabled: list[dict[str, Any]],
    disabled: list[str],
    runs: list[dict[str, Any]],
) -> None:
    run.manifest["quant_strategies"] = {
        "engine": engine,
        "enabled": [str(strategy["name"]) for strategy in enabled],
        "disabled": disabled,
        "failures": [
            {
                "strategy_name": item.get("strategy_name"),
                "source": item.get("source"),
                "symbol": item.get("symbol"),
                "timeframe": item.get("timeframe"),
                "input_view_id": item.get("input_view_id"),
                "message": (item.get("error") or {}).get("message"),
            }
            for item in runs
            if item.get("status") == "failed"
        ],
        "insufficient_data": [
            {
                "strategy_name": item.get("strategy_name"),
                "source": item.get("source"),
                "symbol": item.get("symbol"),
                "timeframe": item.get("timeframe"),
                "input_view_id": item.get("input_view_id"),
                "row_count": item.get("data_quality", {}).get("row_count"),
                "minimum_required_rows": item.get("data_quality", {}).get("minimum_required_rows"),
            }
            for item in runs
            if item.get("status") == "insufficient_data"
        ],
    }


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


def _round(value: float) -> float:
    return round(float(value), 6)
