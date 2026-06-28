from __future__ import annotations

import math
from statistics import mean
from typing import Any

from .strategy_records import MULTI_LEG_EXECUTION_MODEL, warning


MULTI_LEG_EVALUATION_SOURCE = "multi_leg_strategy_evaluation"
DEFAULT_COST_ASSUMPTIONS = {
    "fees_bps": 0.0,
    "slippage_bps": 0.0,
}


def evaluate_multi_leg_backtest(
    *,
    strategy: dict[str, Any],
    legs: list[dict[str, Any]],
    signal_records: dict[str, Any] | list[dict[str, Any]],
    cost_assumptions: dict[str, Any] | None = None,
    execution_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    costs = _cost_assumptions(cost_assumptions)
    model = _execution_model(execution_model)
    try:
        leg_inputs, leg_warnings = _leg_inputs(legs)
        if len(leg_inputs) < 2:
            return _insufficient_record(
                strategy,
                leg_inputs,
                costs,
                model,
                "insufficient_legs",
                "Multi-leg evaluation requires at least two valid legs.",
                extra_warnings=leg_warnings,
            )
        timeframe_warnings = _timeframe_warnings(leg_inputs)
        if timeframe_warnings:
            return _insufficient_record(
                strategy,
                leg_inputs,
                costs,
                model,
                "mismatched_leg_timeframes",
                "Multi-leg evaluation requires all legs to share one timeframe.",
                extra_warnings=[*leg_warnings, *timeframe_warnings],
            )

        aligned = _aligned_rows(leg_inputs)
        if len(aligned["times"]) < 2:
            return _insufficient_record(
                strategy,
                leg_inputs,
                costs,
                model,
                "insufficient_aligned_rows",
                "Multi-leg evaluation requires at least two common open_time rows across all legs.",
                alignment=aligned,
                extra_warnings=leg_warnings,
            )

        signals = _signal_map(signal_records, [leg["leg_id"] for leg in leg_inputs])
        missing_signals = [time for time in aligned["times"] if time not in signals]
        if missing_signals:
            return _insufficient_record(
                strategy,
                leg_inputs,
                costs,
                model,
                "missing_multi_leg_signals",
                "Multi-leg signal records must cover every aligned open_time.",
                alignment=aligned,
                extra_warnings=[
                    *leg_warnings,
                    warning(
                        "missing_multi_leg_signals",
                        f"Missing multi-leg signals for {len(missing_signals)} aligned rows.",
                        source=MULTI_LEG_EVALUATION_SOURCE,
                    ),
                ],
            )

        result = _evaluate_periods(leg_inputs, aligned["times"], signals, costs)
        drawdown_curve, drawdown_summary = _drawdowns(result["equity_curve"])
        metrics = _metrics(result, drawdown_summary)
        warnings = [
            warning(
                "historical_research_only",
                "Multi-leg backtest evaluation is historical research material, not a forecast.",
                source=MULTI_LEG_EVALUATION_SOURCE,
            ),
            *leg_warnings,
            *_alignment_warnings(aligned),
        ]
        if metrics["average_gross_exposure"] == 0:
            warnings.append(
                warning(
                    "no_multi_leg_exposure",
                    "Multi-leg target exposure stayed flat at zero throughout the evaluation window.",
                    source=MULTI_LEG_EVALUATION_SOURCE,
                )
            )
        return _base_record(
            strategy,
            leg_inputs,
            costs,
            model,
            status="succeeded",
            sample=_sample(aligned["times"]),
            alignment=aligned,
            strategy_metrics=metrics,
            leg_summaries=_leg_summaries(leg_inputs, result),
            equity_curve=result["equity_curve"],
            drawdown_curve=drawdown_curve,
            drawdown_summary=drawdown_summary,
            warnings=warnings,
            errors=[],
        )
    except Exception as exc:  # noqa: BLE001 - evaluator returns bounded failure artifacts.
        return _base_record(
            strategy,
            [],
            costs,
            model,
            status="failed",
            sample={"start": None, "end": None, "rows": 0},
            alignment={"status": "failed", "times": [], "omitted_rows": []},
            strategy_metrics={},
            leg_summaries=[],
            equity_curve=[],
            drawdown_curve=[],
            drawdown_summary={},
            warnings=[
                warning(
                    "historical_research_only",
                    "Multi-leg backtest evaluation is historical research material, not a forecast.",
                    source=MULTI_LEG_EVALUATION_SOURCE,
                )
            ],
            errors=[
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "stage": "multi_leg_strategy_evaluation",
                }
            ],
        )


def _evaluate_periods(
    leg_inputs: list[dict[str, Any]],
    times: list[str],
    signals: dict[str, dict[str, float]],
    costs: dict[str, float],
) -> dict[str, Any]:
    cost_rate = (costs["fees_bps"] + costs["slippage_bps"]) / 10000
    gross_equity = 1.0
    net_equity = 1.0
    equity_curve = [
        {
            "open_time": times[0],
            "gross_equity": 1.0,
            "net_equity": 1.0,
            "period_gross_return_pct": None,
            "period_net_return_pct": None,
            "cost_pct": 0.0,
            "turnover": 0.0,
            "gross_exposure": 0.0,
            "net_exposure": 0.0,
            "legs": [],
        }
    ]
    period_net_returns = []
    cost_returns = []
    turnovers = []
    gross_exposures = []
    net_exposures = []
    leg_stats = {
        leg["leg_id"]: {
            "gross_returns": [],
            "cost_returns": [],
            "turnovers": [],
            "abs_exposures": [],
            "net_exposures": [],
        }
        for leg in leg_inputs
    }
    for index in range(1, len(times)):
        previous_time = times[index - 1]
        current_time = times[index]
        previous_positions = signals[times[index - 2]] if index >= 2 else {}
        positions = signals[previous_time]
        period_legs = []
        period_gross_return = 0.0
        period_cost_return = 0.0
        period_turnover = 0.0
        for leg in leg_inputs:
            leg_id = leg["leg_id"]
            position = positions[leg_id]
            previous_position = previous_positions.get(leg_id, 0.0)
            close_return = _close_return(leg["rows_by_time"][previous_time], leg["rows_by_time"][current_time])
            leg_gross_return = position * close_return
            leg_turnover = abs(position - previous_position)
            leg_cost_return = leg_turnover * cost_rate
            period_gross_return += leg_gross_return
            period_cost_return += leg_cost_return
            period_turnover += leg_turnover
            stats = leg_stats[leg_id]
            stats["gross_returns"].append(leg_gross_return)
            stats["cost_returns"].append(leg_cost_return)
            stats["turnovers"].append(leg_turnover)
            stats["abs_exposures"].append(abs(position))
            stats["net_exposures"].append(position)
            period_legs.append(
                {
                    "leg_id": leg_id,
                    "source": leg["source"],
                    "symbol": leg["symbol"],
                    "timeframe": leg["timeframe"],
                    "position": _round(position),
                    "close_return_pct": _pct(close_return),
                    "gross_contribution_pct": _pct(leg_gross_return),
                    "cost_pct": _pct(leg_cost_return),
                    "turnover": _round(leg_turnover),
                }
            )
        period_net_return = period_gross_return - period_cost_return
        gross_equity *= 1 + period_gross_return
        net_equity *= 1 + period_net_return
        gross_exposure = sum(abs(value) for value in positions.values())
        net_exposure = sum(positions.values())
        period_net_returns.append(period_net_return)
        cost_returns.append(period_cost_return)
        turnovers.append(period_turnover)
        gross_exposures.append(gross_exposure)
        net_exposures.append(net_exposure)
        equity_curve.append(
            {
                "open_time": current_time,
                "gross_equity": _round(gross_equity),
                "net_equity": _round(net_equity),
                "period_gross_return_pct": _pct(period_gross_return),
                "period_net_return_pct": _pct(period_net_return),
                "cost_pct": _pct(period_cost_return),
                "turnover": _round(period_turnover),
                "gross_exposure": _round(gross_exposure),
                "net_exposure": _round(net_exposure),
                "legs": period_legs,
            }
        )
    return {
        "gross_equity": gross_equity,
        "net_equity": net_equity,
        "period_net_returns": period_net_returns,
        "cost_returns": cost_returns,
        "turnovers": turnovers,
        "gross_exposures": gross_exposures,
        "net_exposures": net_exposures,
        "leg_stats": leg_stats,
        "equity_curve": equity_curve,
    }


def _leg_inputs(legs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = []
    warnings = []
    seen = set()
    for position, raw in enumerate(legs):
        if not isinstance(raw, dict):
            warnings.append(warning("invalid_leg", "Multi-leg input skipped a non-object leg.", source=MULTI_LEG_EVALUATION_SOURCE))
            continue
        leg_id = str(raw.get("leg_id") or f"leg_{position + 1}")
        if leg_id in seen:
            warnings.append(warning("duplicate_leg_id", f"Duplicate leg_id {leg_id} was skipped.", source=MULTI_LEG_EVALUATION_SOURCE))
            continue
        seen.add(leg_id)
        identity = raw.get("market_identity") if isinstance(raw.get("market_identity"), dict) else raw
        rows = _sorted_rows(raw.get("ohlcv_rows") if isinstance(raw.get("ohlcv_rows"), list) else [])
        rows_by_time = {_open_time(row): row for row in rows}
        normalized.append(
            {
                "leg_id": leg_id,
                "source": str(identity.get("source") or "unknown"),
                "symbol": str(identity.get("symbol") or "unknown"),
                "timeframe": str(identity.get("timeframe") or "unknown"),
                "price_basis": str(raw.get("price_basis") or "close"),
                "rows": rows,
                "rows_by_time": rows_by_time,
            }
        )
    return normalized, warnings


def _timeframe_warnings(legs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timeframes = {leg["timeframe"] for leg in legs}
    if len(timeframes) <= 1:
        return []
    return [
        warning(
            "mismatched_leg_timeframes",
            f"Multi-leg evaluation received mismatched timeframes: {', '.join(sorted(timeframes))}.",
            source=MULTI_LEG_EVALUATION_SOURCE,
        )
    ]


def _aligned_rows(legs: list[dict[str, Any]]) -> dict[str, Any]:
    row_sets = [set(leg["rows_by_time"]) for leg in legs]
    common = set.intersection(*row_sets) if row_sets else set()
    times = sorted(common)
    omitted_rows = [
        {
            "leg_id": leg["leg_id"],
            "input_rows": len(leg["rows"]),
            "aligned_rows": len(times),
            "omitted_rows": len(set(leg["rows_by_time"]) - common),
        }
        for leg in legs
    ]
    return {
        "status": "aligned" if times and not any(item["omitted_rows"] for item in omitted_rows) else "degraded",
        "time_policy": "inner_join_open_time",
        "times": times,
        "row_count": len(times),
        "omitted_rows": omitted_rows,
    }


def _signal_map(signal_records: dict[str, Any] | list[dict[str, Any]], leg_ids: list[str]) -> dict[str, dict[str, float]]:
    if isinstance(signal_records, dict) and signal_records.get("status") not in {None, "succeeded"}:
        return {}
    records = signal_records.get("records") if isinstance(signal_records, dict) else signal_records
    if not isinstance(records, list):
        return {}
    by_time = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        signal_time = str(record.get("signal_time") or record.get("open_time") or "")
        if not signal_time:
            continue
        legs = record.get("legs") if isinstance(record.get("legs"), list) else []
        exposures = {}
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            leg_id = str(leg.get("leg_id") or "")
            if leg_id in leg_ids:
                exposures[leg_id] = _target_exposure(leg.get("target_exposure", leg.get("weight", 0.0)))
        if set(exposures) == set(leg_ids):
            by_time[signal_time] = exposures
    return by_time


def _metrics(result: dict[str, Any], drawdown_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "gross_return_pct": _pct(float(result["gross_equity"]) - 1),
        "net_return_pct": _pct(float(result["net_equity"]) - 1),
        "total_cost_pct": _pct(sum(result["cost_returns"])),
        "cost_drag_pct": _round(_pct(float(result["gross_equity"]) - 1) - _pct(float(result["net_equity"]) - 1)),
        "max_drawdown_pct": drawdown_summary.get("max_drawdown_pct"),
        "final_equity": _round(float(result["net_equity"])),
        "turnover": _round(sum(result["turnovers"])),
        "average_gross_exposure": _round(mean(result["gross_exposures"])) if result["gross_exposures"] else 0.0,
        "average_net_exposure": _round(mean(result["net_exposures"])) if result["net_exposures"] else 0.0,
    }


def _leg_summaries(legs: list[dict[str, Any]], result: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for leg in legs:
        stats = result["leg_stats"][leg["leg_id"]]
        summaries.append(
            {
                "leg_id": leg["leg_id"],
                "source": leg["source"],
                "symbol": leg["symbol"],
                "timeframe": leg["timeframe"],
                "price_basis": leg["price_basis"],
                "gross_contribution_pct": _pct(sum(stats["gross_returns"])),
                "cost_pct": _pct(sum(stats["cost_returns"])),
                "turnover": _round(sum(stats["turnovers"])),
                "average_abs_exposure": _round(mean(stats["abs_exposures"])) if stats["abs_exposures"] else 0.0,
                "average_net_exposure": _round(mean(stats["net_exposures"])) if stats["net_exposures"] else 0.0,
            }
        )
    return summaries


def _insufficient_record(
    strategy: dict[str, Any],
    legs: list[dict[str, Any]],
    costs: dict[str, float],
    model: dict[str, str],
    code: str,
    message: str,
    *,
    alignment: dict[str, Any] | None = None,
    extra_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _base_record(
        strategy,
        legs,
        costs,
        model,
        status="insufficient_data",
        sample=_sample(alignment.get("times", []) if isinstance(alignment, dict) else []),
        alignment=alignment or {"status": "not_aligned", "times": [], "omitted_rows": []},
        strategy_metrics={},
        leg_summaries=[],
        equity_curve=[],
        drawdown_curve=[],
        drawdown_summary={},
        warnings=[
            warning(code, message, source=MULTI_LEG_EVALUATION_SOURCE),
            *(extra_warnings or []),
            warning(
                "historical_research_only",
                "Multi-leg backtest evaluation is historical research material, not a forecast.",
                source=MULTI_LEG_EVALUATION_SOURCE,
            ),
        ],
        errors=[],
    )


def _base_record(
    strategy: dict[str, Any],
    legs: list[dict[str, Any]],
    costs: dict[str, float],
    model: dict[str, str],
    *,
    status: str,
    sample: dict[str, Any],
    alignment: dict[str, Any],
    strategy_metrics: dict[str, Any],
    leg_summaries: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    drawdown_curve: list[dict[str, Any]],
    drawdown_summary: dict[str, Any],
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    name = str(strategy.get("name") or "unknown")
    latest = sample.get("end") or "missing"
    return {
        "multi_leg_evaluation_id": f"multi_leg_backtest:{name}:{latest}",
        "record_type": "multi_leg_backtest",
        "status": status,
        "strategy_name": name,
        "params": strategy.get("params") if isinstance(strategy.get("params"), dict) else {},
        "sample": sample,
        "execution_model": model,
        "cost_assumptions": costs,
        "legs": [_public_leg(leg) for leg in legs],
        "alignment": _public_alignment(alignment),
        "strategy_metrics": strategy_metrics,
        "leg_summaries": leg_summaries,
        "drawdown_summary": drawdown_summary,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "warnings": warnings,
        "errors": errors,
    }


def _public_leg(leg: dict[str, Any]) -> dict[str, Any]:
    return {
        "leg_id": leg["leg_id"],
        "source": leg["source"],
        "symbol": leg["symbol"],
        "timeframe": leg["timeframe"],
        "price_basis": leg["price_basis"],
        "row_count": len(leg["rows"]),
    }


def _public_alignment(alignment: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in alignment.items()
        if key != "times"
    }


def _alignment_warnings(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    omitted = sum(int(item.get("omitted_rows") or 0) for item in alignment.get("omitted_rows", []))
    if omitted <= 0:
        return []
    return [
        warning(
            "multi_leg_alignment_degraded",
            f"Multi-leg alignment omitted {omitted} rows that were not common to every leg.",
            source=MULTI_LEG_EVALUATION_SOURCE,
        )
    ]


def _sample(times: list[str]) -> dict[str, Any]:
    if not times:
        return {"start": None, "end": None, "rows": 0}
    return {"start": times[0], "end": times[-1], "rows": len(times)}


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
        records.append({"open_time": point["open_time"], "net_drawdown_pct": _pct(drawdown)})
    return records, {
        "max_drawdown_pct": _pct(max_drawdown),
        "max_drawdown_start": max_start,
        "max_drawdown_end": max_end,
    }


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
    model = dict(MULTI_LEG_EXECUTION_MODEL)
    if isinstance(raw, dict):
        model.update({str(key): str(value) for key, value in raw.items()})
    return model


def _sorted_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return sorted([row for row in rows if isinstance(row, dict)], key=lambda item: _open_time(item))


def _open_time(row: dict[str, Any]) -> str:
    value = row.get("open_time")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("OHLCV row open_time must be an ISO 8601 UTC string.")
    return value.strip()


def _close_return(previous: dict[str, Any], current: dict[str, Any]) -> float:
    previous_close = _positive_close(previous)
    current_close = _positive_close(current)
    return current_close / previous_close - 1


def _positive_close(row: dict[str, Any]) -> float:
    close = _finite_number(row.get("close"), "close")
    if close <= 0:
        raise ValueError("close must be a positive number for multi-leg evaluation.")
    return close


def _target_exposure(value: Any) -> float:
    target = _finite_number(value, "target_exposure")
    if target < -1.0 or target > 1.0:
        raise ValueError("multi-leg target_exposure must be between -1.0 and 1.0.")
    return target


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


def _pct(value: float) -> float:
    return _round(value * 100)


def _round(value: float) -> float:
    return round(float(value), 6)
