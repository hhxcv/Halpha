from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

from .strategy_records import warning


DEFAULT_EXECUTION_MODEL = {
    "price_source": "close",
    "signal_timing": "signal_at_bar_close",
    "position_timing": "next_bar",
    "lookahead_policy": "no_same_bar_execution",
    "execution_timing": "research_close_to_close",
}
DEFAULT_COST_ASSUMPTIONS = {
    "fees_bps": 0.0,
    "slippage_bps": 0.0,
}
STRATEGY_EVALUATION_SOURCE = "strategy_evaluation"
HISTORICAL_RESEARCH_WARNING = "Backtest evaluation is historical research material, not a forecast."


def evaluate_single_window_backtest(
    *,
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    ohlcv_rows: list[dict[str, Any]],
    signal_records: dict[str, Any] | list[dict[str, Any]],
    cost_assumptions: dict[str, Any] | None = None,
    execution_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    costs = _cost_assumptions(None)
    model = _execution_model(execution_model)
    rows = _sorted_rows(ohlcv_rows)
    sample = _sample(rows)

    try:
        costs = _cost_assumptions(cost_assumptions)
        records = _signal_record_list(signal_records)
        if len(rows) < 2:
            return _insufficient_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                "insufficient_ohlcv_rows",
                "Backtest evaluation requires at least two OHLCV rows.",
            )
        if _upstream_signal_status(signal_records) not in {None, "succeeded"}:
            return _insufficient_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                "upstream_signal_records_unavailable",
                "Strategy signal records are not available for evaluation.",
            )
        if len(records) < len(rows):
            return _insufficient_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                "insufficient_signal_records",
                "Backtest evaluation requires one signal record for each OHLCV row.",
            )

        closes = [_positive_close(row) for row in rows]
        targets = _aligned_target_exposures(rows, records)
        if targets is None:
            return _insufficient_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                "missing_signal_records",
                "Signal records must cover every OHLCV row by open_time.",
            )

        result = _evaluate_periods(rows, closes, targets, costs)
        drawdown_curve, drawdown_summary = _drawdowns(result["equity_curve"])
        strategy_metrics = _strategy_metrics(
            result["gross_equity"],
            result["net_equity"],
            result["period_net_returns"],
            result["cost_returns"],
            max_drawdown_pct=float(drawdown_summary["max_drawdown_pct"]),
            timeframe=str(market_identity.get("timeframe")),
        )
        trade_summary = _trade_summary(
            result["period_positions"],
            result["period_net_returns"],
            result["turnovers"],
        )
        baseline_metrics = _baseline_metrics(rows, closes, costs, timeframe=str(market_identity.get("timeframe")))
        warnings = [
            warning(
                "historical_research_only",
                HISTORICAL_RESEARCH_WARNING,
                source=STRATEGY_EVALUATION_SOURCE,
            )
        ]
        if trade_summary["trade_count"] == 0:
            warnings.append(
                warning(
                    "no_strategy_exposure",
                    "Strategy target exposure stayed flat at zero throughout the evaluation window.",
                    source=STRATEGY_EVALUATION_SOURCE,
                )
            )

        return _base_record(
            strategy,
            market_identity,
            sample,
            costs,
            model,
            status="succeeded",
            strategy_metrics=strategy_metrics,
            baseline_metrics=baseline_metrics,
            relative_metrics=_relative_metrics(strategy_metrics, baseline_metrics),
            trade_summary=trade_summary,
            drawdown_summary=drawdown_summary,
            equity_curve=result["equity_curve"],
            drawdown_curve=drawdown_curve,
            warnings=warnings,
            errors=[],
        )
    except Exception as exc:  # noqa: BLE001 - core returns bounded failed records instead of leaking internals.
        return _failed_record(
            strategy,
            market_identity,
            sample,
            costs,
            model,
            error_type=type(exc).__name__,
            message=str(exc),
        )


def _evaluate_periods(
    rows: list[dict[str, Any]],
    closes: list[float],
    targets: list[float],
    costs: dict[str, float],
) -> dict[str, Any]:
    cost_rate = (costs["fees_bps"] + costs["slippage_bps"]) / 10000
    gross_equity = 1.0
    net_equity = 1.0
    equity_curve = [
        {
            "open_time": _open_time(rows[0]),
            "gross_equity": 1.0,
            "net_equity": 1.0,
            "position": 0.0,
            "turnover": 0.0,
            "period_gross_return_pct": None,
            "period_net_return_pct": None,
            "cost_pct": 0.0,
        }
    ]
    period_gross_returns = []
    period_net_returns = []
    period_positions = []
    turnovers = []
    cost_returns = []
    for index in range(1, len(rows)):
        close_return = (closes[index] / closes[index - 1]) - 1
        position = targets[index - 1]
        previous_position = targets[index - 2] if index >= 2 else 0.0
        turnover = abs(position - previous_position)
        cost_return = turnover * cost_rate
        gross_return = position * close_return
        net_return = gross_return - cost_return
        gross_equity *= 1 + gross_return
        net_equity *= 1 + net_return
        period_gross_returns.append(gross_return)
        period_net_returns.append(net_return)
        period_positions.append(position)
        turnovers.append(turnover)
        cost_returns.append(cost_return)
        equity_curve.append(
            {
                "open_time": _open_time(rows[index]),
                "gross_equity": _round(gross_equity),
                "net_equity": _round(net_equity),
                "position": _round(position),
                "turnover": _round(turnover),
                "period_gross_return_pct": _pct(gross_return),
                "period_net_return_pct": _pct(net_return),
                "cost_pct": _pct(cost_return),
            }
        )
    return {
        "gross_equity": gross_equity,
        "net_equity": net_equity,
        "equity_curve": equity_curve,
        "period_gross_returns": period_gross_returns,
        "period_net_returns": period_net_returns,
        "period_positions": period_positions,
        "turnovers": turnovers,
        "cost_returns": cost_returns,
    }


def _strategy_metrics(
    gross_equity: float,
    net_equity: float,
    period_net_returns: list[float],
    cost_returns: list[float],
    *,
    max_drawdown_pct: float,
    timeframe: str,
) -> dict[str, Any]:
    return {
        "gross_return_pct": _pct(gross_equity - 1),
        "net_return_pct": _pct(net_equity - 1),
        "total_cost_pct": _pct(sum(cost_returns)),
        "max_drawdown_pct": max_drawdown_pct,
        "volatility_pct": _annualized_volatility_pct(period_net_returns, timeframe=timeframe),
        "sharpe": _sharpe(period_net_returns, timeframe=timeframe),
        "sortino": _sortino(period_net_returns, timeframe=timeframe),
        "final_equity": _round(net_equity),
    }


def _baseline_metrics(
    rows: list[dict[str, Any]],
    closes: list[float],
    costs: dict[str, float],
    *,
    timeframe: str,
) -> dict[str, Any]:
    cost_rate = (costs["fees_bps"] + costs["slippage_bps"]) / 10000
    period_returns = []
    equity = 1.0
    equity_values = [equity]
    for index in range(1, len(rows)):
        close_return = (closes[index] / closes[index - 1]) - 1
        cost_return = cost_rate if index == 1 else 0.0
        net_return = close_return - cost_return
        period_returns.append(net_return)
        equity *= 1 + net_return
        equity_values.append(equity)
    return {
        "buy_and_hold": {
            "net_return_pct": _pct(equity - 1),
            "max_drawdown_pct": _pct(_max_drawdown_from_equity(equity_values)),
            "volatility_pct": _annualized_volatility_pct(period_returns, timeframe=timeframe),
            "final_equity": _round(equity),
        },
        "cash": {
            "net_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "volatility_pct": 0.0,
            "final_equity": 1.0,
        },
    }


def _relative_metrics(strategy_metrics: dict[str, Any], baseline_metrics: dict[str, Any]) -> dict[str, Any]:
    buy_and_hold = baseline_metrics["buy_and_hold"]
    return {
        "excess_return_vs_buy_and_hold_pct": _round(
            strategy_metrics["net_return_pct"] - buy_and_hold["net_return_pct"]
        ),
        "drawdown_delta_vs_buy_and_hold_pct": _round(
            strategy_metrics["max_drawdown_pct"] - buy_and_hold["max_drawdown_pct"]
        ),
    }


def _trade_summary(
    period_positions: list[float],
    period_net_returns: list[float],
    turnovers: list[float],
) -> dict[str, Any]:
    trade_count = 0
    completed_returns = []
    holding_bars = []
    current_multiplier: float | None = None
    current_holding_bars = 0
    previous_position = 0.0
    for position, period_return in zip(period_positions, period_net_returns, strict=True):
        if position > 0 and previous_position <= 0:
            trade_count += 1
            current_multiplier = 1.0
            current_holding_bars = 0
        if current_multiplier is not None:
            current_multiplier *= 1 + period_return
            if position > 0:
                current_holding_bars += 1
        if position <= 0 and previous_position > 0 and current_multiplier is not None:
            completed_returns.append(current_multiplier - 1)
            holding_bars.append(current_holding_bars)
            current_multiplier = None
            current_holding_bars = 0
        previous_position = position

    open_trade_count = 1 if current_multiplier is not None else 0
    if current_multiplier is not None:
        holding_bars.append(current_holding_bars)

    completed_count = len(completed_returns)
    hit_rate = None
    if completed_count:
        hit_rate = (sum(1 for value in completed_returns if value > 0) / completed_count) * 100
    exposure = 0.0
    if period_positions:
        exposure = (sum(1 for position in period_positions if position > 0) / len(period_positions)) * 100
    average_holding = mean(holding_bars) if holding_bars else None
    return {
        "trade_count": trade_count,
        "completed_trade_count": completed_count,
        "open_trade_count": open_trade_count,
        "hit_rate_pct": _round(hit_rate) if hit_rate is not None else None,
        "turnover": _round(sum(turnovers)),
        "exposure_pct": _round(exposure),
        "average_holding_bars": _round(average_holding) if average_holding is not None else None,
    }


def _drawdowns(equity_curve: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    peak = 0.0
    peak_time = None
    max_drawdown = 0.0
    max_start = None
    max_end = None
    records = []
    for point in equity_curve:
        equity = float(point["net_equity"])
        if equity >= peak:
            peak = equity
            peak_time = point["open_time"]
        drawdown = 0.0 if peak <= 0 else (equity / peak) - 1
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_start = peak_time
            max_end = point["open_time"]
        records.append(
            {
                "open_time": point["open_time"],
                "net_drawdown_pct": _pct(drawdown),
            }
        )
    return records, {
        "max_drawdown_pct": _pct(max_drawdown),
        "max_drawdown_start": max_start,
        "max_drawdown_end": max_end,
    }


def _insufficient_record(
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    sample: dict[str, Any],
    costs: dict[str, float],
    model: dict[str, str],
    code: str,
    message: str,
) -> dict[str, Any]:
    return _base_record(
        strategy,
        market_identity,
        sample,
        costs,
        model,
        status="insufficient_data",
        strategy_metrics={},
        baseline_metrics={},
        relative_metrics={},
        trade_summary={},
        drawdown_summary={},
        equity_curve=[],
        drawdown_curve=[],
        warnings=[
            warning(code, message, source=STRATEGY_EVALUATION_SOURCE),
            warning(
                "historical_research_only",
                HISTORICAL_RESEARCH_WARNING,
                source=STRATEGY_EVALUATION_SOURCE,
            ),
        ],
        errors=[],
    )


def _failed_record(
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    sample: dict[str, Any],
    costs: dict[str, float],
    model: dict[str, str],
    *,
    error_type: str,
    message: str,
) -> dict[str, Any]:
    return _base_record(
        strategy,
        market_identity,
        sample,
        costs,
        model,
        status="failed",
        strategy_metrics={},
        baseline_metrics={},
        relative_metrics={},
        trade_summary={},
        drawdown_summary={},
        equity_curve=[],
        drawdown_curve=[],
        warnings=[
            warning(
                "historical_research_only",
                HISTORICAL_RESEARCH_WARNING,
                source=STRATEGY_EVALUATION_SOURCE,
            )
        ],
        errors=[
            {
                "error_type": error_type,
                "message": message,
                "stage": "strategy_evaluation.single_window",
            }
        ],
    )


def _base_record(
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    sample: dict[str, Any],
    costs: dict[str, float],
    model: dict[str, str],
    *,
    status: str,
    strategy_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
    relative_metrics: dict[str, Any],
    trade_summary: dict[str, Any],
    drawdown_summary: dict[str, Any],
    equity_curve: list[dict[str, Any]],
    drawdown_curve: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    name = str(strategy.get("name"))
    source = market_identity.get("source")
    symbol = market_identity.get("symbol")
    timeframe = market_identity.get("timeframe")
    latest = sample.get("end") or "missing"
    return {
        "evaluation_id": f"single_window_backtest:{name}:{source}:{symbol}:{timeframe}:{latest}",
        "status": status,
        "strategy_name": name,
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "params": strategy.get("params") if isinstance(strategy.get("params"), dict) else {},
        "sample": sample,
        "execution_model": model,
        "cost_assumptions": costs,
        "strategy_metrics": strategy_metrics,
        "baseline_metrics": baseline_metrics,
        "relative_metrics": relative_metrics,
        "trade_summary": trade_summary,
        "drawdown_summary": drawdown_summary,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "warnings": warnings,
        "errors": errors,
    }


def _signal_record_list(signal_records: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(signal_records, dict):
        records = signal_records.get("records")
        return records if isinstance(records, list) else []
    return signal_records


def _upstream_signal_status(signal_records: dict[str, Any] | list[dict[str, Any]]) -> str | None:
    if isinstance(signal_records, dict):
        status = signal_records.get("status")
        return str(status) if status is not None else None
    return None


def _aligned_target_exposures(
    rows: list[dict[str, Any]],
    signal_records: list[dict[str, Any]],
) -> list[float] | None:
    by_time = {_open_time(record): _target_exposure(record) for record in signal_records}
    targets = []
    for row in rows:
        key = _open_time(row)
        if key not in by_time:
            return None
        targets.append(by_time[key])
    return targets


def _target_exposure(record: dict[str, Any]) -> float:
    position = record.get("position") if isinstance(record.get("position"), dict) else {}
    value = position.get("target_exposure")
    if value is None:
        signal = record.get("signal") if isinstance(record.get("signal"), dict) else {}
        value = 1.0 if signal.get("active") is True else 0.0
    target = _finite_number(value, "signal record target_exposure")
    if target < 0 or target > 1:
        raise ValueError("signal record target_exposure must be between 0 and 1.")
    return target


def _cost_assumptions(raw: dict[str, Any] | None) -> dict[str, float]:
    values = dict(DEFAULT_COST_ASSUMPTIONS)
    if isinstance(raw, dict):
        values.update(raw)
    fees_bps = _non_negative_number(values.get("fees_bps"), "fees_bps")
    slippage_bps = _non_negative_number(values.get("slippage_bps"), "slippage_bps")
    return {
        "fees_bps": fees_bps,
        "slippage_bps": slippage_bps,
        "total_one_way_bps": _round(fees_bps + slippage_bps),
    }


def _execution_model(raw: dict[str, Any] | None) -> dict[str, str]:
    model = dict(DEFAULT_EXECUTION_MODEL)
    if isinstance(raw, dict):
        model.update({str(key): str(value) for key, value in raw.items()})
    return model


def _sample(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"start": None, "end": None, "rows": 0}
    return {
        "start": _open_time(rows[0]),
        "end": _open_time(rows[-1]),
        "rows": len(rows),
    }


def _sorted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: str(item.get("open_time") or ""))


def _positive_close(row: dict[str, Any]) -> float:
    close = _finite_number(row.get("close"), "close")
    if close <= 0:
        raise ValueError("close must be a positive number for strategy evaluation.")
    return close


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def _non_negative_number(value: Any, name: str) -> float:
    number = _finite_number(value, name)
    if number < 0:
        raise ValueError(f"{name} must be a non-negative number.")
    return number


def _open_time(row: dict[str, Any]) -> str:
    return str(row.get("open_time"))


def _max_drawdown_from_equity(equity_values: list[float]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for equity in equity_values:
        if equity >= peak:
            peak = equity
        drawdown = 0.0 if peak <= 0 else (equity / peak) - 1
        max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def _annualized_volatility_pct(period_returns: list[float], *, timeframe: str) -> float:
    if len(period_returns) < 2:
        return 0.0
    return _pct(pstdev(period_returns) * math.sqrt(_periods_per_year(timeframe)))


def _sharpe(period_returns: list[float], *, timeframe: str) -> float:
    if len(period_returns) < 2:
        return 0.0
    volatility = pstdev(period_returns)
    if volatility == 0:
        return 0.0
    periods = _periods_per_year(timeframe)
    return _round((mean(period_returns) * periods) / (volatility * math.sqrt(periods)))


def _sortino(period_returns: list[float], *, timeframe: str) -> float:
    if len(period_returns) < 2:
        return 0.0
    downside = [period_return for period_return in period_returns if period_return < 0]
    if not downside:
        return 0.0
    downside_volatility = pstdev(downside)
    if downside_volatility == 0:
        return 0.0
    periods = _periods_per_year(timeframe)
    return _round((mean(period_returns) * periods) / (downside_volatility * math.sqrt(periods)))


def _periods_per_year(timeframe: str) -> int:
    if timeframe == "1h":
        return 365 * 24
    return 365


def _pct(value: float) -> float:
    return _round(value * 100)


def _round(value: float) -> float:
    return round(float(value), 6)
