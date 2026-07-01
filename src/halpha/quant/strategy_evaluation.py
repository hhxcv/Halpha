from __future__ import annotations

import math
from statistics import mean, median, pstdev
from typing import Any

from halpha.market.instrument_identity import InstrumentIdentityError, derive_instrument_identity

from .signal_records import validate_single_leg_target_exposure
from .strategy_records import CANONICAL_EXECUTION_MODEL, SIGNED_EXECUTION_MODEL, SUPPORTED_BACKTEST_MODES, warning


DEFAULT_EXECUTION_MODEL = dict(CANONICAL_EXECUTION_MODEL)
DEFAULT_SIGNED_EXECUTION_MODEL = dict(SIGNED_EXECUTION_MODEL)
DEFAULT_COST_ASSUMPTIONS = {
    "fees_bps": 0.0,
    "slippage_bps": 0.0,
}
STRATEGY_EVALUATION_SOURCE = "strategy_evaluation"
HISTORICAL_RESEARCH_WARNING = "Backtest evaluation is historical research material, not a forecast."
MIN_SAMPLE_ROWS_FOR_RELIABILITY = 60
LOW_TRADE_COUNT_THRESHOLD = 3
HIGH_TURNOVER_THRESHOLD = 10.0
HIGH_COST_DRAG_PCT_THRESHOLD = 1.0
CONTRACT_HIGH_ABS_EXPOSURE_PCT_THRESHOLD = 80.0
CONTRACT_HIGH_PERIOD_MOVE_PCT_THRESHOLD = 15.0
CONTRACT_MARKET_TYPES = {"perpetual", "swap", "futures"}
CONTRACT_TYPES = {"linear_perpetual", "inverse_perpetual", "linear_futures", "inverse_futures"}
DEFAULT_WALK_FORWARD_POLICY = {
    "calibration_rows": 60,
    "window_rows": 60,
    "min_window_rows": 20,
    "min_windows": 3,
}


def evaluate_single_window_backtest(
    *,
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    ohlcv_rows: list[dict[str, Any]],
    signal_records: dict[str, Any] | list[dict[str, Any]],
    cost_assumptions: dict[str, Any] | None = None,
    execution_model: dict[str, Any] | None = None,
    funding_costs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    costs = _cost_assumptions(None)
    model = _execution_model(execution_model)
    funding = None
    rows = _sorted_rows(ohlcv_rows)
    sample = _sample(rows)

    try:
        costs = _cost_assumptions(cost_assumptions)
        records = _signal_record_list(signal_records)
        signed_exposure = _uses_signed_target_exposure(signal_records, records)
        contract_exposure = _contract_identity(market_identity) is not None
        funding = _funding_cost_input(funding_costs, signed=signed_exposure or contract_exposure)
        model = _execution_model(execution_model, signed=signed_exposure)
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
        targets = _aligned_target_exposures(
            rows,
            records,
            mode=_backtest_mode(strategy),
            signed=signed_exposure,
        )
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

        result = _evaluate_periods(rows, closes, targets, costs, funding_by_period=_funding_by_period(funding))
        drawdown_curve, drawdown_summary = _drawdowns(result["equity_curve"])
        strategy_metrics = _strategy_metrics(
            result["gross_equity"],
            result["net_equity"],
            result["period_net_returns"],
            result["cost_returns"],
            funding_drag_returns=result.get("funding_drag_returns"),
            max_drawdown_pct=float(drawdown_summary["max_drawdown_pct"]),
            timeframe=str(market_identity.get("timeframe")),
        )
        trade_summary = _trade_summary(
            result["period_positions"],
            result["period_net_returns"],
            result["turnovers"],
            signed=signed_exposure,
        )
        baseline_metrics = _baseline_metrics(rows, closes, costs, timeframe=str(market_identity.get("timeframe")))
        futures_diagnostics = _futures_diagnostics(
            market_identity=market_identity,
            rows=rows,
            closes=closes,
            result=result,
            strategy_metrics=strategy_metrics,
            trade_summary=trade_summary,
            funding=funding,
        )
        warnings = _unique_warnings(
            [
                *_research_warnings(sample, strategy_metrics, trade_summary),
                *_funding_warnings(funding),
                *_diagnostic_warnings(futures_diagnostics),
            ]
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
            funding_costs=funding,
            futures_diagnostics=futures_diagnostics,
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


def evaluate_walk_forward_backtest(
    *,
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    ohlcv_rows: list[dict[str, Any]],
    signal_records: dict[str, Any] | list[dict[str, Any]],
    cost_assumptions: dict[str, Any] | None = None,
    execution_model: dict[str, Any] | None = None,
    funding_costs: dict[str, Any] | None = None,
    window_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    costs = _cost_assumptions(None)
    model = _execution_model(execution_model)
    funding = None
    rows = _sorted_rows(ohlcv_rows)
    sample = _sample(rows)
    policy = _walk_forward_policy(window_policy)

    try:
        costs = _cost_assumptions(cost_assumptions)
        records = _signal_record_list(signal_records)
        signed_exposure = _uses_signed_target_exposure(signal_records, records)
        contract_exposure = _contract_identity(market_identity) is not None
        funding = _funding_cost_input(funding_costs, signed=signed_exposure or contract_exposure)
        model = _execution_model(execution_model, signed=signed_exposure)
        if len(rows) < 2:
            return _walk_forward_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                policy,
                status="insufficient_data",
                windows=[],
                summary=_walk_forward_summary([], policy),
                warnings=[
                    warning(
                        "insufficient_ohlcv_rows",
                        "Walk-forward evaluation requires at least two OHLCV rows.",
                        source=STRATEGY_EVALUATION_SOURCE,
                    )
                ],
                errors=[],
            )
        if _upstream_signal_status(signal_records) not in {None, "succeeded"}:
            return _walk_forward_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                policy,
                status="insufficient_data",
                windows=[],
                summary=_walk_forward_summary([], policy),
                warnings=[
                    warning(
                        "upstream_signal_records_unavailable",
                        "Strategy signal records are not available for walk-forward evaluation.",
                        source=STRATEGY_EVALUATION_SOURCE,
                    )
                ],
                errors=[],
            )
        if len(records) < len(rows):
            return _walk_forward_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                policy,
                status="insufficient_data",
                windows=[],
                summary=_walk_forward_summary([], policy),
                warnings=[
                    warning(
                        "insufficient_signal_records",
                        "Walk-forward evaluation requires one signal record for each OHLCV row.",
                        source=STRATEGY_EVALUATION_SOURCE,
                    )
                ],
                errors=[],
            )

        records_by_time = _aligned_signal_record_map(rows, records)
        if records_by_time is None:
            return _walk_forward_record(
                strategy,
                market_identity,
                sample,
                costs,
                model,
                policy,
                status="insufficient_data",
                windows=[],
                summary=_walk_forward_summary([], policy),
                warnings=[
                    warning(
                        "missing_signal_records",
                        "Signal records must cover every OHLCV row by open_time.",
                        source=STRATEGY_EVALUATION_SOURCE,
                    )
                ],
                errors=[],
            )

        windows = [
            _walk_forward_window_record(
                strategy=strategy,
                market_identity=market_identity,
                rows=rows,
                records_by_time=records_by_time,
                window=window_item,
                costs=costs,
                model=model,
                funding_costs=_window_funding_costs(funding, rows[window_item["start_index"] : window_item["end_index"]]),
            )
            for window_item in _walk_forward_windows(rows, policy)
        ]
        summary = _walk_forward_summary(windows, policy)
        warnings = _walk_forward_warnings(sample, policy, windows, summary)
        status = "succeeded" if summary["succeeded_windows"] >= policy["min_windows"] else "insufficient_data"
        errors = [
            error
            for item in windows
            for error in item.get("errors", [])
            if isinstance(error, dict)
        ]
        return _walk_forward_record(
            strategy,
            market_identity,
            sample,
            costs,
            model,
            policy,
            status=status,
            windows=windows,
            summary=summary,
            warnings=warnings,
            errors=errors,
        )
    except Exception as exc:  # noqa: BLE001 - evaluator returns bounded failed records.
        return _walk_forward_record(
            strategy,
            market_identity,
            sample,
            costs,
            model,
            policy,
            status="failed",
            windows=[],
            summary=_walk_forward_summary([], policy),
            warnings=[
                warning(
                    "historical_research_only",
                    HISTORICAL_RESEARCH_WARNING,
                    source=STRATEGY_EVALUATION_SOURCE,
                )
            ],
            errors=[
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "stage": "strategy_evaluation.walk_forward",
                }
            ],
        )


def _evaluate_periods(
    rows: list[dict[str, Any]],
    closes: list[float],
    targets: list[float],
    costs: dict[str, float],
    *,
    funding_by_period: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cost_rate = (costs["fees_bps"] + costs["slippage_bps"]) / 10000
    funding_enabled = funding_by_period is not None
    gross_equity = 1.0
    net_equity = 1.0
    initial_point = {
        "open_time": _open_time(rows[0]),
        "gross_equity": 1.0,
        "net_equity": 1.0,
        "position": 0.0,
        "turnover": 0.0,
        "period_gross_return_pct": None,
        "period_net_return_pct": None,
        "cost_pct": 0.0,
    }
    if funding_enabled:
        initial_point.update(
            {
                "funding_rate": 0.0,
                "funding_return_pct": 0.0,
                "funding_drag_pct": 0.0,
                "matched_funding_count": 0,
            }
        )
    equity_curve = [initial_point]
    period_gross_returns = []
    period_net_returns = []
    period_positions = []
    turnovers = []
    cost_returns = []
    funding_drag_returns = []
    funding_record_count = 0
    for index in range(1, len(rows)):
        close_return = (closes[index] / closes[index - 1]) - 1
        position = targets[index - 1]
        previous_position = targets[index - 2] if index >= 2 else 0.0
        turnover = abs(position - previous_position)
        cost_return = turnover * cost_rate
        period_funding = _period_funding(funding_by_period, period_end=_open_time(rows[index]))
        funding_rate = float(period_funding.get("funding_rate") or 0.0)
        funding_return = -position * funding_rate
        funding_drag_return = position * funding_rate
        gross_return = position * close_return
        net_return = gross_return + funding_return - cost_return
        gross_equity *= 1 + gross_return
        net_equity *= 1 + net_return
        period_gross_returns.append(gross_return)
        period_net_returns.append(net_return)
        period_positions.append(position)
        turnovers.append(turnover)
        cost_returns.append(cost_return)
        if funding_enabled:
            funding_drag_returns.append(funding_drag_return)
            funding_record_count += int(period_funding.get("matched_record_count") or 0)
        point = {
            "open_time": _open_time(rows[index]),
            "gross_equity": _round(gross_equity),
            "net_equity": _round(net_equity),
            "position": _round(position),
            "turnover": _round(turnover),
            "period_gross_return_pct": _pct(gross_return),
            "period_net_return_pct": _pct(net_return),
            "cost_pct": _pct(cost_return),
        }
        if funding_enabled:
            point.update(
                {
                    "funding_rate": _round(funding_rate),
                    "funding_return_pct": _pct(funding_return),
                    "funding_drag_pct": _pct(funding_drag_return),
                    "matched_funding_count": int(period_funding.get("matched_record_count") or 0),
                }
            )
        equity_curve.append(point)
    result = {
        "gross_equity": gross_equity,
        "net_equity": net_equity,
        "equity_curve": equity_curve,
        "period_gross_returns": period_gross_returns,
        "period_net_returns": period_net_returns,
        "period_positions": period_positions,
        "turnovers": turnovers,
        "cost_returns": cost_returns,
    }
    if funding_enabled:
        result["funding_drag_returns"] = funding_drag_returns
        result["funding_record_count"] = funding_record_count
    return result


def _strategy_metrics(
    gross_equity: float,
    net_equity: float,
    period_net_returns: list[float],
    cost_returns: list[float],
    *,
    funding_drag_returns: list[float] | None = None,
    max_drawdown_pct: float,
    timeframe: str,
) -> dict[str, Any]:
    gross_return_pct = _pct(gross_equity - 1)
    net_return_pct = _pct(net_equity - 1)
    metrics = {
        "gross_return_pct": gross_return_pct,
        "net_return_pct": net_return_pct,
        "total_cost_pct": _pct(sum(cost_returns)),
        "cost_drag_pct": _round(gross_return_pct - net_return_pct),
        "max_drawdown_pct": max_drawdown_pct,
        "volatility_pct": _annualized_volatility_pct(period_net_returns, timeframe=timeframe),
        "sharpe": _sharpe(period_net_returns, timeframe=timeframe),
        "sortino": _sortino(period_net_returns, timeframe=timeframe),
        "final_equity": _round(net_equity),
    }
    if funding_drag_returns is not None:
        metrics["funding_drag_pct"] = _pct(sum(funding_drag_returns))
    return metrics


def _research_warnings(
    sample: dict[str, Any],
    strategy_metrics: dict[str, Any],
    trade_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings = [
        warning(
            "historical_research_only",
            HISTORICAL_RESEARCH_WARNING,
            source=STRATEGY_EVALUATION_SOURCE,
        )
    ]
    rows = int(sample.get("rows") or 0)
    trade_count = int(trade_summary.get("trade_count") or 0)
    turnover = float(trade_summary.get("turnover") or 0.0)
    cost_drag_pct = float(strategy_metrics.get("cost_drag_pct") or 0.0)
    if rows < MIN_SAMPLE_ROWS_FOR_RELIABILITY:
        warnings.append(
            warning(
                "insufficient_sample_length",
                (
                    f"Evaluation sample has {rows} rows, below the "
                    f"{MIN_SAMPLE_ROWS_FOR_RELIABILITY}-row research reliability threshold."
                ),
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    if trade_count == 0:
        warnings.append(
            warning(
                "no_strategy_exposure",
                "Strategy target exposure stayed flat at zero throughout the evaluation window.",
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    if trade_count < LOW_TRADE_COUNT_THRESHOLD:
        warnings.append(
            warning(
                "low_trade_count",
                (
                    f"Trade count is {trade_count}, below the "
                    f"{LOW_TRADE_COUNT_THRESHOLD}-trade research reliability threshold."
                ),
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    if turnover >= HIGH_TURNOVER_THRESHOLD:
        warnings.append(
            warning(
                "high_turnover",
                (
                    f"Turnover is {turnover}; cost and execution assumptions may dominate net results."
                ),
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    if cost_drag_pct >= HIGH_COST_DRAG_PCT_THRESHOLD:
        warnings.append(
            warning(
                "high_cost_drag",
                (
                    f"Cost drag is {cost_drag_pct} percentage points; compare gross and net returns "
                    "before interpreting strategy quality."
                ),
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    return warnings


def _futures_diagnostics(
    *,
    market_identity: dict[str, Any],
    rows: list[dict[str, Any]],
    closes: list[float],
    result: dict[str, Any],
    strategy_metrics: dict[str, Any],
    trade_summary: dict[str, Any],
    funding: dict[str, Any] | None,
) -> dict[str, Any] | None:
    identity = _contract_identity(market_identity)
    if identity is None:
        return None

    positions = _float_list(result.get("period_positions"))
    gross_returns = _float_list(result.get("period_gross_returns"))
    turnovers = _float_list(result.get("turnovers"))
    cost_returns = _float_list(result.get("cost_returns"))
    period_count = len(positions)
    warnings = [
        *_dict_list(identity.get("warnings")),
        *_futures_funding_warnings(funding),
    ]

    exposure = _futures_exposure_summary(positions)
    risk_warnings = _contract_risk_warnings(
        exposure=exposure,
        closes=closes,
    )
    warnings.extend(risk_warnings)

    return {
        "artifact_type": "futures_strategy_diagnostics",
        "schema_version": 1,
        "status": "degraded" if warnings else "succeeded",
        "instrument_identity": {
            "source": identity.get("source"),
            "symbol": identity.get("symbol"),
            "timeframe": identity.get("timeframe"),
            "market_type": identity.get("market_type"),
            "contract_type": identity.get("contract_type"),
            "base_asset": identity.get("base_asset"),
            "quote_asset": identity.get("quote_asset"),
            "settlement_asset": identity.get("settlement_asset"),
            "identity_status": identity.get("identity_status"),
        },
        "method": {
            "basis": "account_independent_contract_research_diagnostics",
            "contribution_basis": "additive_period_gross_return_percentage_points",
            "liquidation_model": "not_modeled",
            "margin_model": "not_modeled",
            "account_balance_model": "not_modeled",
        },
        "period_count": period_count,
        "contribution": _futures_contribution_summary(positions, gross_returns),
        "exposure": exposure,
        "turnover": {
            "total_turnover": _round(sum(turnovers)),
            "average_turnover": _round(mean(turnovers)) if turnovers else 0.0,
        },
        "costs": {
            "total_cost_pct": strategy_metrics.get("total_cost_pct"),
            "cost_drag_pct": strategy_metrics.get("cost_drag_pct"),
            "additive_cost_pct": _pct(sum(cost_returns)),
        },
        "funding": _futures_funding_summary(strategy_metrics, funding),
        "trade_summary": {
            "trade_count": trade_summary.get("trade_count"),
            "long_trade_count": trade_summary.get("long_trade_count"),
            "short_trade_count": trade_summary.get("short_trade_count"),
            "side_flip_count": trade_summary.get("side_flip_count"),
        },
        "risk_warnings": risk_warnings,
        "warnings": warnings,
    }


def _contract_identity(market_identity: dict[str, Any]) -> dict[str, Any] | None:
    nested = market_identity.get("instrument_identity")
    if isinstance(nested, dict):
        return nested if _is_contract_identity(nested) else None
    if _has_explicit_identity_fields(market_identity):
        return market_identity if _is_contract_identity(market_identity) else None
    source = market_identity.get("source")
    symbol = market_identity.get("symbol")
    timeframe = market_identity.get("timeframe")
    if not all(isinstance(value, str) and value.strip() for value in (source, symbol, timeframe)):
        return None
    try:
        identity = derive_instrument_identity(source=source, symbol=symbol, timeframe=timeframe)
    except InstrumentIdentityError:
        return None
    return identity if _is_contract_identity(identity) else None


def _has_explicit_identity_fields(value: dict[str, Any]) -> bool:
    return any(key in value for key in ("market_type", "contract_type", "settlement_asset"))


def _is_contract_identity(identity: dict[str, Any]) -> bool:
    market_type = str(identity.get("market_type") or "").strip().lower()
    contract_type = str(identity.get("contract_type") or "").strip().lower()
    return market_type in CONTRACT_MARKET_TYPES or contract_type in CONTRACT_TYPES


def _futures_contribution_summary(
    positions: list[float],
    gross_returns: list[float],
) -> dict[str, Any]:
    long_return = 0.0
    short_return = 0.0
    flat_return = 0.0
    for position, period_return in zip(positions, gross_returns, strict=False):
        if position > 0:
            long_return += period_return
        elif position < 0:
            short_return += period_return
        else:
            flat_return += period_return
    return {
        "long_gross_contribution_pct": _pct(long_return),
        "short_gross_contribution_pct": _pct(short_return),
        "flat_gross_contribution_pct": _pct(flat_return),
        "total_gross_contribution_pct": _pct(long_return + short_return + flat_return),
    }


def _futures_exposure_summary(positions: list[float]) -> dict[str, Any]:
    if not positions:
        return {
            "long_time_pct": 0.0,
            "short_time_pct": 0.0,
            "flat_time_pct": 0.0,
            "average_gross_exposure_pct": 0.0,
            "average_net_exposure_pct": 0.0,
            "average_abs_exposure_pct": 0.0,
            "max_abs_exposure_pct": 0.0,
        }
    count = len(positions)
    average_abs = sum(abs(position) for position in positions) / count
    return {
        "long_time_pct": _pct(sum(1 for position in positions if position > 0) / count),
        "short_time_pct": _pct(sum(1 for position in positions if position < 0) / count),
        "flat_time_pct": _pct(sum(1 for position in positions if position == 0) / count),
        "average_gross_exposure_pct": _pct(average_abs),
        "average_net_exposure_pct": _pct(sum(positions) / count),
        "average_abs_exposure_pct": _pct(average_abs),
        "max_abs_exposure_pct": _pct(max(abs(position) for position in positions)),
    }


def _futures_funding_summary(
    strategy_metrics: dict[str, Any],
    funding: dict[str, Any] | None,
) -> dict[str, Any]:
    if funding is None:
        return {
            "status": "unavailable",
            "availability": "not_provided",
        }
    summary = {
        "status": str(funding.get("status") or "unknown"),
        "period_count": funding.get("period_count"),
        "matched_record_count": funding.get("matched_record_count"),
        "missing_period_count": funding.get("missing_period_count"),
    }
    if "funding_drag_pct" in strategy_metrics:
        summary["funding_drag_pct"] = strategy_metrics["funding_drag_pct"]
    return summary


def _futures_funding_warnings(funding: dict[str, Any] | None) -> list[dict[str, Any]]:
    if funding is None:
        return [
            warning(
                "funding_costs_not_provided_for_contract",
                "Contract evaluation did not receive funding cost inputs; funding drag is unavailable.",
                source=STRATEGY_EVALUATION_SOURCE,
            )
        ]
    return _funding_warnings(funding)


def _contract_risk_warnings(
    *,
    exposure: dict[str, Any],
    closes: list[float],
) -> list[dict[str, Any]]:
    average_abs_exposure_pct = float(exposure.get("average_abs_exposure_pct") or 0.0)
    max_period_move_pct = _max_period_abs_return_pct(closes)
    if (
        average_abs_exposure_pct >= CONTRACT_HIGH_ABS_EXPOSURE_PCT_THRESHOLD
        and max_period_move_pct >= CONTRACT_HIGH_PERIOD_MOVE_PCT_THRESHOLD
    ):
        return [
            warning(
                "contract_volatility_exposure_risk",
                (
                    "Contract evaluation combines high average absolute exposure "
                    f"({average_abs_exposure_pct}%) with a large observed period move "
                    f"({max_period_move_pct}%). This is a qualitative research warning; "
                    "exchange margin schedules and liquidation engines are not modeled."
                ),
                source=STRATEGY_EVALUATION_SOURCE,
            )
        ]
    return []


def _max_period_abs_return_pct(closes: list[float]) -> float:
    values = [
        abs((closes[index] / closes[index - 1]) - 1)
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]
    return _pct(max(values)) if values else 0.0


def _diagnostic_warnings(diagnostics: dict[str, Any] | None) -> list[dict[str, Any]]:
    if diagnostics is None:
        return []
    return _dict_list(diagnostics.get("warnings"))


def _unique_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in warnings:
        key = (item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _walk_forward_window_record(
    *,
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    rows: list[dict[str, Any]],
    records_by_time: dict[str, dict[str, Any]],
    window: dict[str, int],
    costs: dict[str, float],
    model: dict[str, str],
    funding_costs: dict[str, Any] | None,
) -> dict[str, Any]:
    start = window["start_index"]
    end = window["end_index"]
    window_rows = rows[start:end]
    window_signals = [records_by_time[_open_time(row)] for row in window_rows]
    single_window = evaluate_single_window_backtest(
        strategy=strategy,
        market_identity=market_identity,
        ohlcv_rows=window_rows,
        signal_records=window_signals,
        cost_assumptions=costs,
        execution_model=model,
        funding_costs=funding_costs,
    )
    return {
        "window_index": window["window_index"],
        "status": single_window.get("status"),
        "calibration_window": _sample(rows[:start]),
        "evaluation_window": _sample(window_rows),
        "single_window_evaluation_id": single_window.get("evaluation_id"),
        "strategy_metrics": _mapping(single_window.get("strategy_metrics")),
        "baseline_metrics": _mapping(single_window.get("baseline_metrics")),
        "relative_metrics": _mapping(single_window.get("relative_metrics")),
        "trade_summary": _mapping(single_window.get("trade_summary")),
        "warnings": _dict_list(single_window.get("warnings")),
        "errors": _dict_list(single_window.get("errors")),
    }


def _walk_forward_summary(windows: list[dict[str, Any]], policy: dict[str, int]) -> dict[str, Any]:
    succeeded = [item for item in windows if item.get("status") == "succeeded"]
    net_returns = _window_metric_values(succeeded, "strategy_metrics", "net_return_pct")
    excess_returns = _window_metric_values(
        succeeded,
        "relative_metrics",
        "excess_return_vs_buy_and_hold_pct",
    )
    drawdowns = _window_metric_values(succeeded, "strategy_metrics", "max_drawdown_pct")
    turnovers = _window_metric_values(succeeded, "trade_summary", "turnover")
    cost_drags = _window_metric_values(succeeded, "strategy_metrics", "cost_drag_pct")
    return {
        "window_count": len(windows),
        "succeeded_windows": len(succeeded),
        "failed_windows": sum(1 for item in windows if item.get("status") == "failed"),
        "insufficient_data_windows": sum(
            1 for item in windows if item.get("status") == "insufficient_data"
        ),
        "mean_net_return_pct": _mean_value(net_returns),
        "median_net_return_pct": _median_value(net_returns),
        "positive_net_return_window_pct": _positive_window_pct(net_returns),
        "mean_excess_return_vs_buy_and_hold_pct": _mean_value(excess_returns),
        "positive_excess_return_window_pct": _positive_window_pct(excess_returns),
        "worst_max_drawdown_pct": min(drawdowns) if drawdowns else None,
        "mean_turnover": _mean_value(turnovers),
        "mean_cost_drag_pct": _mean_value(cost_drags),
        "net_return_range_pct": _range_value(net_returns),
        "result_stability": _result_stability(net_returns, min_windows=policy["min_windows"]),
    }


def _walk_forward_warnings(
    sample: dict[str, Any],
    policy: dict[str, int],
    windows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings = [
        warning(
            "historical_research_only",
            HISTORICAL_RESEARCH_WARNING,
            source=STRATEGY_EVALUATION_SOURCE,
        )
    ]
    if summary["succeeded_windows"] < policy["min_windows"]:
        warnings.append(
            warning(
                "too_few_walk_forward_windows",
                (
                    f"Walk-forward produced {summary['succeeded_windows']} successful windows, "
                    f"below the {policy['min_windows']}-window reliability threshold."
                ),
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    if sample["rows"] < policy["calibration_rows"] + policy["min_windows"] * policy["min_window_rows"]:
        warnings.append(
            warning(
                "insufficient_walk_forward_history",
                (
                    f"Walk-forward sample has {sample['rows']} rows, below the minimum history "
                    "needed for calibration context and reliable evaluation windows."
                ),
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    if any(
        int(_mapping(item.get("evaluation_window")).get("rows") or 0) < policy["window_rows"]
        for item in windows
        if item.get("status") == "succeeded"
    ):
        warnings.append(
            warning(
                "short_walk_forward_samples",
                "One or more walk-forward evaluation windows are shorter than the target window size.",
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    if summary.get("result_stability") == "unstable":
        warnings.append(
            warning(
                "unstable_walk_forward_results",
                "Walk-forward net returns are unstable across sequential evaluation windows.",
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    positive_window_pct = summary.get("positive_net_return_window_pct")
    if isinstance(positive_window_pct, (int, float)) and 0 < positive_window_pct < 100:
        warnings.append(
            warning(
                "regime_dependent_walk_forward_outcomes",
                "Walk-forward outcomes alternate between positive and negative windows.",
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    return warnings


def _walk_forward_record(
    strategy: dict[str, Any],
    market_identity: dict[str, Any],
    sample: dict[str, Any],
    costs: dict[str, float],
    model: dict[str, str],
    policy: dict[str, int],
    *,
    status: str,
    windows: list[dict[str, Any]],
    summary: dict[str, Any],
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    name = str(strategy.get("name"))
    source = market_identity.get("source")
    symbol = market_identity.get("symbol")
    timeframe = market_identity.get("timeframe")
    latest = sample.get("end") or "missing"
    return {
        "walk_forward_id": f"walk_forward_backtest:{name}:{source}:{symbol}:{timeframe}:{latest}",
        "enabled": True,
        "status": status,
        "method": {
            "name": "bounded_chronological_walk_forward_fixed_params",
            "params_optimized_per_window": False,
            "state_carryover_between_windows": False,
            "window_overlap": False,
        },
        "sample": sample,
        "execution_model": model,
        "cost_assumptions": costs,
        "window_policy": policy,
        "summary": summary,
        "windows": windows,
        "warnings": warnings,
        "errors": errors,
    }


def _walk_forward_policy(raw: dict[str, Any] | None) -> dict[str, int]:
    values = dict(DEFAULT_WALK_FORWARD_POLICY)
    if isinstance(raw, dict):
        values.update(raw)
    calibration_rows = _non_negative_int(values.get("calibration_rows"), "calibration_rows")
    window_rows = _positive_int(values.get("window_rows"), "window_rows")
    min_window_rows = _positive_int(values.get("min_window_rows"), "min_window_rows")
    min_windows = _positive_int(values.get("min_windows"), "min_windows")
    if min_window_rows > window_rows:
        raise ValueError("min_window_rows must be less than or equal to window_rows.")
    return {
        "calibration_rows": calibration_rows,
        "window_rows": window_rows,
        "min_window_rows": min_window_rows,
        "min_windows": min_windows,
    }


def _walk_forward_windows(rows: list[dict[str, Any]], policy: dict[str, int]) -> list[dict[str, int]]:
    windows = []
    start = policy["calibration_rows"]
    index = 1
    while start < len(rows):
        end = min(start + policy["window_rows"], len(rows))
        if end - start < policy["min_window_rows"]:
            break
        windows.append(
            {
                "window_index": index,
                "start_index": start,
                "end_index": end,
            }
        )
        index += 1
        start = end
    return windows


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
    *,
    signed: bool,
) -> dict[str, Any]:
    if signed:
        return _signed_trade_summary(period_positions, period_net_returns, turnovers)

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


def _signed_trade_summary(
    period_positions: list[float],
    period_net_returns: list[float],
    turnovers: list[float],
) -> dict[str, Any]:
    trade_count = 0
    long_trade_count = 0
    short_trade_count = 0
    long_to_short_count = 0
    short_to_long_count = 0
    completed_returns = []
    holding_bars = []
    current_side = "flat"
    current_multiplier: float | None = None
    current_holding_bars = 0

    for position, period_return in zip(period_positions, period_net_returns, strict=True):
        side = _position_side(position)
        if current_side == "flat":
            if side != "flat":
                trade_count += 1
                long_trade_count += 1 if side == "long" else 0
                short_trade_count += 1 if side == "short" else 0
                current_side = side
                current_multiplier = 1.0
                current_holding_bars = 0
        elif side == "flat":
            if current_multiplier is not None:
                current_multiplier *= 1 + period_return
                completed_returns.append(current_multiplier - 1)
                holding_bars.append(current_holding_bars)
            current_side = "flat"
            current_multiplier = None
            current_holding_bars = 0
            continue
        elif side != current_side:
            if current_multiplier is not None:
                completed_returns.append(current_multiplier - 1)
                holding_bars.append(current_holding_bars)
            if current_side == "long" and side == "short":
                long_to_short_count += 1
            elif current_side == "short" and side == "long":
                short_to_long_count += 1
            trade_count += 1
            long_trade_count += 1 if side == "long" else 0
            short_trade_count += 1 if side == "short" else 0
            current_side = side
            current_multiplier = 1.0
            current_holding_bars = 0

        if current_multiplier is not None:
            current_multiplier *= 1 + period_return
            current_holding_bars += 1

    if current_multiplier is not None:
        holding_bars.append(current_holding_bars)

    completed_count = len(completed_returns)
    hit_rate = None
    if completed_count:
        hit_rate = (sum(1 for value in completed_returns if value > 0) / completed_count) * 100
    exposure = 0.0
    long_exposure = 0.0
    short_exposure = 0.0
    average_abs_exposure = 0.0
    if period_positions:
        exposure = (sum(1 for position in period_positions if position != 0) / len(period_positions)) * 100
        long_exposure = (sum(1 for position in period_positions if position > 0) / len(period_positions)) * 100
        short_exposure = (sum(1 for position in period_positions if position < 0) / len(period_positions)) * 100
        average_abs_exposure = (sum(abs(position) for position in period_positions) / len(period_positions)) * 100
    average_holding = mean(holding_bars) if holding_bars else None
    open_trade_count = 1 if current_multiplier is not None else 0
    return {
        "trade_count": trade_count,
        "completed_trade_count": completed_count,
        "open_trade_count": open_trade_count,
        "hit_rate_pct": _round(hit_rate) if hit_rate is not None else None,
        "turnover": _round(sum(turnovers)),
        "exposure_pct": _round(exposure),
        "long_exposure_pct": _round(long_exposure),
        "short_exposure_pct": _round(short_exposure),
        "average_abs_exposure_pct": _round(average_abs_exposure),
        "average_holding_bars": _round(average_holding) if average_holding is not None else None,
        "long_trade_count": long_trade_count,
        "short_trade_count": short_trade_count,
        "long_to_short_count": long_to_short_count,
        "short_to_long_count": short_to_long_count,
        "side_flip_count": long_to_short_count + short_to_long_count,
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
    funding_costs: dict[str, Any] | None = None,
    futures_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(strategy.get("name"))
    source = market_identity.get("source")
    symbol = market_identity.get("symbol")
    timeframe = market_identity.get("timeframe")
    latest = sample.get("end") or "missing"
    record = {
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
    if funding_costs is not None:
        record["funding_costs"] = funding_costs
    if futures_diagnostics is not None:
        record["futures_diagnostics"] = futures_diagnostics
    return record


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


def _aligned_signal_record_map(
    rows: list[dict[str, Any]],
    signal_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]] | None:
    by_time = {_open_time(record): record for record in signal_records}
    for row in rows:
        if _open_time(row) not in by_time:
            return None
    return by_time


def _aligned_target_exposures(
    rows: list[dict[str, Any]],
    signal_records: list[dict[str, Any]],
    *,
    mode: str,
    signed: bool,
) -> list[float] | None:
    by_time = {_open_time(record): _target_exposure(record, signed=signed) for record in signal_records}
    targets = []
    for row in rows:
        key = _open_time(row)
        if key not in by_time:
            return None
        targets.append(by_time[key])
    if mode == "long_only" and not signed:
        targets = _long_only_targets(targets)
    return targets


def _long_only_targets(targets: list[float]) -> list[float]:
    active_target = 0.0
    result = []
    for target in targets:
        active_target = max(active_target, target)
        result.append(active_target)
    return result


def _target_exposure(record: dict[str, Any], *, signed: bool) -> float:
    position = record.get("position") if isinstance(record.get("position"), dict) else {}
    value = position.get("target_exposure")
    if value is None:
        signal = record.get("signal") if isinstance(record.get("signal"), dict) else {}
        value = 1.0 if signal.get("active") is True else 0.0
    if signed:
        return validate_single_leg_target_exposure(value, path="signal record target_exposure")
    target = _finite_number(value, "signal record target_exposure")
    if target < 0 or target > 1:
        raise ValueError("signal record target_exposure must be between 0 and 1.")
    return target


def _uses_signed_target_exposure(
    signal_records: dict[str, Any] | list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> bool:
    if isinstance(signal_records, dict):
        if signal_records.get("position_policy") == "research_signed_target_exposure":
            return True
        version = _int_or_none(signal_records.get("signal_record_version"))
        if version is not None and version >= 2:
            return True
    for record in records:
        position = record.get("position") if isinstance(record.get("position"), dict) else {}
        signal = record.get("signal") if isinstance(record.get("signal"), dict) else {}
        if position.get("unit") == "fractional_signed_exposure":
            return True
        if str(position.get("position_state") or signal.get("position_state") or "") in {
            "long",
            "short",
            "flat",
            "unknown",
        }:
            return True
    return False


def _funding_cost_input(raw: dict[str, Any] | None, *, signed: bool) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("funding_costs must be a funding cost input object.")
    if not signed:
        return {
            **raw,
            "status": "skipped",
            "periods": [],
            "warnings": [
                *_dict_list(raw.get("warnings")),
                warning(
                    "funding_requires_signed_exposure",
                    "Funding costs are applied only to signed exposure evaluations.",
                    source=STRATEGY_EVALUATION_SOURCE,
                ),
            ],
        }
    periods = []
    for item in raw.get("periods") or []:
        if not isinstance(item, dict):
            continue
        period_end = item.get("period_end")
        if not isinstance(period_end, str) or not period_end.strip():
            continue
        periods.append(
            {
                **item,
                "period_end": period_end.strip(),
                "funding_rate": _finite_number(item.get("funding_rate"), "funding_rate"),
                "matched_record_count": _non_negative_int(
                    item.get("matched_record_count", 0),
                    "matched_record_count",
                ),
            }
        )
    status = str(raw.get("status") or ("available" if periods else "unavailable"))
    if status in {"available", "partial"} and not periods:
        status = "unavailable"
    return {
        **raw,
        "status": status,
        "periods": periods,
        "warnings": _dict_list(raw.get("warnings")),
        "errors": _dict_list(raw.get("errors")),
    }


def _funding_by_period(funding: dict[str, Any] | None) -> dict[str, dict[str, Any]] | None:
    if funding is None:
        return None
    if funding.get("status") not in {"available", "partial"}:
        return None
    return {
        str(item["period_end"]): item
        for item in _dict_list(funding.get("periods"))
        if isinstance(item.get("period_end"), str)
    }


def _window_funding_costs(funding: dict[str, Any] | None, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if funding is None:
        return None
    period_ends = {_open_time(row) for row in rows[1:]}
    periods = [
        item
        for item in _dict_list(funding.get("periods"))
        if isinstance(item.get("period_end"), str) and item["period_end"] in period_ends
    ]
    matched_record_count = sum(int(item.get("matched_record_count") or 0) for item in periods)
    missing_period_count = sum(
        max(0, int(item.get("expected_record_count") or 0) - int(item.get("matched_record_count") or 0))
        for item in periods
    )
    expected_record_count = sum(int(item.get("expected_record_count") or 0) for item in periods)
    if not periods:
        status = "unavailable"
    elif matched_record_count > 0 and missing_period_count == 0:
        status = "available"
    elif matched_record_count > 0:
        status = "partial"
    else:
        status = "unavailable"
    return {
        **funding,
        "status": status,
        "period_count": len(periods),
        "expected_record_count": expected_record_count,
        "matched_record_count": matched_record_count,
        "missing_period_count": missing_period_count,
        "periods": periods,
    }


def _period_funding(
    funding_by_period: dict[str, dict[str, Any]] | None,
    *,
    period_end: str,
) -> dict[str, Any]:
    if funding_by_period is None:
        return {}
    return funding_by_period.get(period_end) or {"funding_rate": 0.0, "matched_record_count": 0}


def _funding_warnings(funding: dict[str, Any] | None) -> list[dict[str, Any]]:
    if funding is None:
        return []
    warnings = _dict_list(funding.get("warnings"))
    status = funding.get("status")
    if status in {"unavailable", "partial", "failed", "skipped"} and not warnings:
        warnings.append(
            warning(
                "funding_costs_not_fully_applied",
                f"Funding cost status is {status}.",
                source=STRATEGY_EVALUATION_SOURCE,
            )
        )
    return warnings


def _backtest_mode(strategy: dict[str, Any]) -> str:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    mode = backtest.get("mode", "long_flat")
    if not isinstance(mode, str) or mode not in SUPPORTED_BACKTEST_MODES:
        return "long_flat"
    return mode


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


def _execution_model(raw: dict[str, Any] | None, *, signed: bool = False) -> dict[str, str]:
    model = dict(DEFAULT_SIGNED_EXECUTION_MODEL if signed else DEFAULT_EXECUTION_MODEL)
    if isinstance(raw, dict):
        model.update({str(key): str(value) for key, value in raw.items()})
    if signed and model.get("execution_model_id") == CANONICAL_EXECUTION_MODEL.get("execution_model_id"):
        model["execution_model_id"] = SIGNED_EXECUTION_MODEL["execution_model_id"]
    if signed:
        model.setdefault("direction", "long_short")
        model.setdefault("position_unit", "fractional_signed_exposure")
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


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _position_side(position: float) -> str:
    if position > 0:
        return "long"
    if position < 0:
        return "short"
    return "flat"


def _non_negative_number(value: Any, name: str) -> float:
    number = _finite_number(value, name)
    if number < 0:
        raise ValueError(f"{name} must be a non-negative number.")
    return number


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")
    return value


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


def _window_metric_values(windows: list[dict[str, Any]], section: str, key: str) -> list[float]:
    values = []
    for item in windows:
        section_values = item.get(section)
        if not isinstance(section_values, dict):
            continue
        value = section_values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        values.append(float(value))
    return values


def _mean_value(values: list[float]) -> float | None:
    return _round(mean(values)) if values else None


def _median_value(values: list[float]) -> float | None:
    return _round(median(values)) if values else None


def _positive_window_pct(values: list[float]) -> float | None:
    if not values:
        return None
    return _pct(sum(1 for value in values if value > 0) / len(values))


def _range_value(values: list[float]) -> float | None:
    if not values:
        return None
    return _round(max(values) - min(values))


def _result_stability(values: list[float], *, min_windows: int) -> str:
    if len(values) < min_windows:
        return "insufficient"
    has_positive = any(value > 0 for value in values)
    has_negative = any(value < 0 for value in values)
    if has_positive and has_negative:
        return "unstable"
    if _range_value(values) is not None and float(_range_value(values)) >= 20.0:
        return "unstable"
    return "stable"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _float_list(value: Any) -> list[float]:
    return [float(item) for item in value if isinstance(item, (int, float)) and not isinstance(item, bool)] if isinstance(value, list) else []


def _pct(value: float) -> float:
    return _round(value * 100)


def _round(value: float) -> float:
    return round(float(value), 6)
