from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

from ..multi_leg_evaluation import evaluate_multi_leg_backtest
from ..strategy_records import data_quality, parameter_diagnostic, strategy_run_record, warning
from ..strategy_specs import require_strategy_spec


NAME = "pair_zscore_reversion"
SPEC = require_strategy_spec(NAME)
DEFAULT_PARAMS = dict(SPEC.default_params)
CALCULATION_BACKEND = "python.rolling_log_price_spread_zscore"
POSITION_POLICY = "research_multi_leg_target_exposure"
SPREAD_MODE = "log_price_spread"
LEG_A_ID = "spread_leg_a"
LEG_B_ID = "spread_leg_b"


def run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    engine: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    item = warning(
        "pair_strategy_requires_multi_leg_input",
        "pair_zscore_reversion requires two explicit OHLCV legs and cannot run as a single-symbol strategy.",
        source="strategy",
    )
    return strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="insufficient_data",
        params=params,
        data_quality=data_quality(
            view,
            rows,
            minimum_rows=_minimum_rows(params),
            sufficient=False,
            warnings=[item],
        ),
        indicators={
            "calculation_backend": CALCULATION_BACKEND,
            "required_leg_count": 2,
            "hedge_ratio_assumption": _hedge_ratio_assumption(params, []),
        },
        signals={
            "status": "requires_multi_leg_input",
            "position_policy": POSITION_POLICY,
        },
        backtest_diagnostic={
            "enabled": False,
            "status": "requires_multi_leg_input",
        },
        parameter_diagnostic=parameter_diagnostic(),
        assessment={
            "direction": "unknown",
            "strength": "unknown",
            "confidence": "low",
            "summary": "Pair strategy assessment requires two explicit aligned OHLCV legs.",
            "evidence": [],
            "uncertainty": [
                "Single-symbol strategy runs do not provide the pair alignment needed for statistical arbitrage.",
            ],
        },
        warnings=[item],
        error=None,
    )


def failed_params(strategy: dict[str, Any]) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    raw = strategy.get("params")
    if isinstance(raw, dict):
        params.update(raw)
    return params


def signal_records(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    item = warning(
        "pair_strategy_requires_multi_leg_input",
        "pair_zscore_reversion signal records require two explicit OHLCV legs.",
        source="strategy",
    )
    return _signal_record_set(
        strategy,
        params=params,
        legs=[],
        status="insufficient_data",
        records=[],
        spread_indicator_summary={},
        warnings=[item],
    )


def pair_signal_records(strategy: dict[str, Any], legs: list[dict[str, Any]]) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    pair_legs, leg_warnings = _pair_legs(legs)
    if len(pair_legs) != 2:
        return _signal_record_set(
            strategy,
            params=params,
            legs=pair_legs,
            status="insufficient_data",
            records=[],
            spread_indicator_summary={},
            warnings=[
                warning(
                    "insufficient_pair_legs",
                    "pair_zscore_reversion requires exactly two valid OHLCV legs.",
                    source="strategy",
                ),
                *leg_warnings,
            ],
        )

    aligned = _aligned_pair_rows(pair_legs)
    minimum_rows = _minimum_rows(params)
    if len(aligned["times"]) < minimum_rows:
        return _signal_record_set(
            strategy,
            params=params,
            legs=pair_legs,
            status="insufficient_data",
            records=[],
            spread_indicator_summary={},
            warnings=[
                warning(
                    "insufficient_aligned_pair_rows",
                    (
                        f"pair_zscore_reversion has {len(aligned['times'])} aligned rows; "
                        f"requires at least {minimum_rows} rows."
                    ),
                    source="data_quality",
                ),
                *leg_warnings,
                *_alignment_warnings(aligned),
            ],
            alignment=aligned,
        )

    records, summary = _records_from_aligned_pair(strategy, params=params, legs=pair_legs, aligned=aligned)
    warnings = [
        *leg_warnings,
        *_alignment_warnings(aligned),
        *_parameter_warnings(params),
    ]
    if not any(record["gross_exposure"] > 0 for record in records):
        warnings.append(
            warning(
                "no_pair_exposure",
                "pair_zscore_reversion target exposure stayed flat throughout the aligned window.",
                source="strategy",
            )
        )
    return _signal_record_set(
        strategy,
        params=params,
        legs=pair_legs,
        status="succeeded",
        records=records,
        spread_indicator_summary=summary,
        warnings=warnings,
        alignment=aligned,
    )


def evaluate_pair_backtest(
    strategy: dict[str, Any],
    legs: list[dict[str, Any]],
    *,
    cost_assumptions: dict[str, Any] | None = None,
    execution_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    signals = pair_signal_records(strategy, legs)
    pair_legs, _ = _pair_legs(legs)
    evaluation = evaluate_multi_leg_backtest(
        strategy={"name": NAME, "params": params},
        legs=pair_legs,
        signal_records=signals,
        cost_assumptions=cost_assumptions,
        execution_model=execution_model,
    )
    status = str(evaluation.get("status") or signals.get("status") or "failed")
    return {
        "schema_version": 1,
        "artifact_type": "pair_strategy_backtest",
        "status": status,
        "strategy_name": NAME,
        "strategy_family": SPEC.family,
        "output_position_policy": POSITION_POLICY,
        "params": params,
        "hedge_ratio_assumption": _hedge_ratio_assumption(params, pair_legs),
        "spread_indicator_summary": signals.get("spread_indicator_summary", {}),
        "signal_records": signals,
        "multi_leg_evaluation": evaluation,
        "warnings": _unique_warnings([*signals.get("warnings", []), *evaluation.get("warnings", [])]),
        "errors": evaluation.get("errors", []),
    }


def _params(raw: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    if isinstance(raw, dict):
        params.update(raw)
    lookback_window = _positive_int(params["lookback_window"], "lookback_window")
    entry_zscore = _positive_number(params["entry_zscore"], "entry_zscore")
    exit_zscore = _non_negative_number(params["exit_zscore"], "exit_zscore")
    if exit_zscore >= entry_zscore:
        raise ValueError("exit_zscore must be lower than entry_zscore.")
    hedge_ratio = _positive_number(params["hedge_ratio"], "hedge_ratio")
    return {
        "lookback_window": lookback_window,
        "entry_zscore": entry_zscore,
        "exit_zscore": exit_zscore,
        "hedge_ratio": hedge_ratio,
    }


def _minimum_rows(params: dict[str, Any]) -> int:
    return int(params["lookback_window"]) + 1


def _pair_legs(legs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = []
    warnings = []
    if not isinstance(legs, list):
        return [], [
            warning("invalid_pair_legs", "pair_zscore_reversion legs must be a list.", source="strategy"),
        ]
    for position, raw in enumerate(legs[:2]):
        if not isinstance(raw, dict):
            warnings.append(warning("invalid_pair_leg", "Pair strategy skipped a non-object leg.", source="strategy"))
            continue
        identity = raw.get("market_identity") if isinstance(raw.get("market_identity"), dict) else raw
        rows = _sorted_rows(raw.get("ohlcv_rows") if isinstance(raw.get("ohlcv_rows"), list) else [])
        normalized.append(
            {
                "leg_id": LEG_A_ID if position == 0 else LEG_B_ID,
                "source": str(identity.get("source") or "unknown"),
                "symbol": str(identity.get("symbol") or "unknown"),
                "timeframe": str(identity.get("timeframe") or "unknown"),
                "price_basis": str(raw.get("price_basis") or "close"),
                "rows": rows,
                "rows_by_time": {_open_time(row): row for row in rows},
                "market_identity": {
                    "source": str(identity.get("source") or "unknown"),
                    "symbol": str(identity.get("symbol") or "unknown"),
                    "timeframe": str(identity.get("timeframe") or "unknown"),
                },
                "ohlcv_rows": rows,
            }
        )
    if len(legs) > 2:
        warnings.append(
            warning(
                "extra_pair_legs_ignored",
                "pair_zscore_reversion uses the first two provided legs and ignores additional legs.",
                source="strategy",
            )
        )
    return normalized, warnings


def _aligned_pair_rows(legs: list[dict[str, Any]]) -> dict[str, Any]:
    common = set(legs[0]["rows_by_time"]) & set(legs[1]["rows_by_time"])
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
    timeframes = sorted({leg["timeframe"] for leg in legs})
    return {
        "status": "aligned" if times and len(timeframes) == 1 and not any(item["omitted_rows"] for item in omitted_rows) else "degraded",
        "time_policy": "inner_join_open_time",
        "row_count": len(times),
        "times": times,
        "omitted_rows": omitted_rows,
        "timeframes": timeframes,
    }


def _records_from_aligned_pair(
    strategy: dict[str, Any],
    *,
    params: dict[str, Any],
    legs: list[dict[str, Any]],
    aligned: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    times = aligned["times"]
    leg_a, leg_b = legs
    hedge_ratio = float(params["hedge_ratio"])
    spreads = [
        _log_price_spread(
            _positive_close(leg_a["rows_by_time"][time]),
            _positive_close(leg_b["rows_by_time"][time]),
            hedge_ratio=hedge_ratio,
        )
        for time in times
    ]
    contexts = _spread_contexts(spreads, params=params)
    states = _state_series(contexts, params=params)
    leg_a_weight, leg_b_weight = _leg_weights(hedge_ratio)
    records = []
    previous_state = "flat"
    for time, context, state in zip(times, contexts, states, strict=True):
        leg_a_exposure, leg_b_exposure = _target_exposures(
            state,
            leg_a_weight=leg_a_weight,
            leg_b_weight=leg_b_weight,
        )
        transition = _transition(previous_state, state)
        records.append(
            {
                "schema_version": 1,
                "record_type": "multi_leg_signal",
                "signal_time": time,
                "open_time": time,
                "strategy_name": NAME,
                "strategy_version": 1,
                "position_policy": POSITION_POLICY,
                "pair_signal_state": state,
                "signal": {
                    "active": state != "flat",
                    "position_state": state,
                },
                "indicator_context": context,
                "legs": [
                    _signal_leg(leg_a, leg_a_exposure),
                    _signal_leg(leg_b, leg_b_exposure),
                ],
                "gross_exposure": _round(abs(leg_a_exposure) + abs(leg_b_exposure)),
                "net_exposure": _round(leg_a_exposure + leg_b_exposure),
                "entry": transition["entry"],
                "exit": transition["exit"],
                "long_spread_entry": transition["long_spread_entry"],
                "long_spread_exit": transition["long_spread_exit"],
                "short_spread_entry": transition["short_spread_entry"],
                "short_spread_exit": transition["short_spread_exit"],
                "warnings": [],
            }
        )
        previous_state = state
    return records, _spread_summary(contexts, states)


def _spread_contexts(spreads: list[float], *, params: dict[str, Any]) -> list[dict[str, Any]]:
    lookback = int(params["lookback_window"])
    contexts = []
    for index, spread in enumerate(spreads):
        window = spreads[max(0, index - lookback + 1) : index + 1]
        if len(window) < lookback:
            average = None
            stdev = None
            zscore = None
        else:
            average_value = mean(window)
            stdev_value = pstdev(window)
            average = _round(average_value)
            stdev = _round(stdev_value)
            zscore = None if stdev_value <= 0 else _round((spread - average_value) / stdev_value)
        contexts.append(
            {
                "calculation_backend": CALCULATION_BACKEND,
                "spread_mode": SPREAD_MODE,
                "spread": _round(spread),
                "spread_mean": average,
                "spread_std": stdev,
                "spread_zscore": zscore,
                "lookback_window": lookback,
                "entry_zscore": float(params["entry_zscore"]),
                "exit_zscore": float(params["exit_zscore"]),
                "hedge_ratio": float(params["hedge_ratio"]),
                "signal_timing": "signal_at_bar_close",
                "position_timing": "next_bar",
                "lookahead_policy": "closed_bar_no_lookahead",
            }
        )
    return contexts


def _state_series(contexts: list[dict[str, Any]], *, params: dict[str, Any]) -> list[str]:
    entry_zscore = float(params["entry_zscore"])
    exit_zscore = float(params["exit_zscore"])
    state = "flat"
    states = []
    for context in contexts:
        zscore = context["spread_zscore"]
        if zscore is None:
            state = "flat"
        elif zscore <= -entry_zscore:
            state = "long_spread"
        elif zscore >= entry_zscore:
            state = "short_spread"
        elif state == "long_spread" and zscore >= -exit_zscore:
            state = "flat"
        elif state == "short_spread" and zscore <= exit_zscore:
            state = "flat"
        states.append(state)
    return states


def _target_exposures(state: str, *, leg_a_weight: float, leg_b_weight: float) -> tuple[float, float]:
    if state == "long_spread":
        return leg_a_weight, -leg_b_weight
    if state == "short_spread":
        return -leg_a_weight, leg_b_weight
    return 0.0, 0.0


def _leg_weights(hedge_ratio: float) -> tuple[float, float]:
    denominator = 1.0 + abs(hedge_ratio)
    return _round(1.0 / denominator), _round(abs(hedge_ratio) / denominator)


def _signal_leg(leg: dict[str, Any], target_exposure: float) -> dict[str, Any]:
    return {
        "leg_id": leg["leg_id"],
        "instrument_identity": dict(leg["market_identity"]),
        "target_exposure": _round(target_exposure),
        "price_basis": "close",
    }


def _signal_record_set(
    strategy: dict[str, Any],
    *,
    params: dict[str, Any],
    legs: list[dict[str, Any]],
    status: str,
    records: list[dict[str, Any]],
    spread_indicator_summary: dict[str, Any],
    warnings: list[dict[str, Any]],
    alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "multi_leg_signal_records",
        "record_type": "multi_leg_signal_set",
        "status": status,
        "strategy_name": NAME,
        "strategy_version": 1,
        "strategy_family": SPEC.family,
        "position_policy": POSITION_POLICY,
        "params": params,
        "hedge_ratio_assumption": _hedge_ratio_assumption(params, legs),
        "alignment": _public_alignment(alignment),
        "legs": [_public_leg(leg) for leg in legs],
        "records": records,
        "latest_record": records[-1] if records else None,
        "record_count": len(records),
        "long_spread_count": sum(1 for record in records if record["pair_signal_state"] == "long_spread"),
        "short_spread_count": sum(1 for record in records if record["pair_signal_state"] == "short_spread"),
        "flat_count": sum(1 for record in records if record["pair_signal_state"] == "flat"),
        "entry_count": sum(1 for record in records if record["entry"]),
        "exit_count": sum(1 for record in records if record["exit"]),
        "spread_indicator_summary": spread_indicator_summary,
        "warnings": _unique_warnings(warnings),
    }


def _hedge_ratio_assumption(params: dict[str, Any], legs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "mode": "configured_fixed",
        "hedge_ratio": float(params["hedge_ratio"]),
        "spread_mode": SPREAD_MODE,
        "calculation_backend": CALCULATION_BACKEND,
        "leg_a": _public_leg(legs[0]) if len(legs) >= 1 else None,
        "leg_b": _public_leg(legs[1]) if len(legs) >= 2 else None,
        "optimization": "not_performed",
        "cointegration_test": "not_performed",
    }


def _spread_summary(contexts: list[dict[str, Any]], states: list[str]) -> dict[str, Any]:
    zscores = [context["spread_zscore"] for context in contexts if context["spread_zscore"] is not None]
    latest = contexts[-1] if contexts else {}
    return {
        "spread_mode": SPREAD_MODE,
        "latest_spread": latest.get("spread"),
        "latest_spread_zscore": latest.get("spread_zscore"),
        "max_abs_spread_zscore": _round(max(abs(float(value)) for value in zscores)) if zscores else None,
        "long_spread_count": states.count("long_spread"),
        "short_spread_count": states.count("short_spread"),
        "flat_count": states.count("flat"),
    }


def _alignment_warnings(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    omitted = sum(int(item["omitted_rows"]) for item in alignment.get("omitted_rows", []))
    if omitted:
        warnings.append(
            warning(
                "pair_alignment_degraded",
                f"Pair alignment omitted {omitted} rows that were not common to both legs.",
                source="data_quality",
            )
        )
    if len(alignment.get("timeframes", [])) > 1:
        warnings.append(
            warning(
                "mismatched_pair_timeframes",
                "Pair strategy received mismatched leg timeframes; no resampling was performed.",
                source="data_quality",
            )
        )
    return warnings


def _parameter_warnings(params: dict[str, Any]) -> list[dict[str, Any]]:
    if float(params["entry_zscore"]) <= 0.5:
        return [
            warning(
                "low_pair_entry_threshold",
                "entry_zscore is low; pair strategy may react to noise.",
                source="strategy",
            )
        ]
    return []


def _transition(previous_state: str, state: str) -> dict[str, bool]:
    long_entry = state == "long_spread" and previous_state != "long_spread"
    long_exit = previous_state == "long_spread" and state != "long_spread"
    short_entry = state == "short_spread" and previous_state != "short_spread"
    short_exit = previous_state == "short_spread" and state != "short_spread"
    return {
        "entry": long_entry or short_entry,
        "exit": long_exit or short_exit,
        "long_spread_entry": long_entry,
        "long_spread_exit": long_exit,
        "short_spread_entry": short_entry,
        "short_spread_exit": short_exit,
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


def _public_alignment(alignment: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(alignment, dict):
        return {
            "status": "not_aligned",
            "time_policy": "inner_join_open_time",
            "row_count": 0,
            "omitted_rows": [],
        }
    return {key: value for key, value in alignment.items() if key != "times"}


def _sorted_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return sorted([row for row in rows if isinstance(row, dict)], key=lambda item: _open_time(item))


def _open_time(row: dict[str, Any]) -> str:
    value = row.get("open_time")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("OHLCV row open_time must be an ISO 8601 UTC string.")
    return value.strip()


def _positive_close(row: dict[str, Any]) -> float:
    close = _finite_number(row.get("close"), "close")
    if close <= 0:
        raise ValueError("close must be a positive number for pair strategy evaluation.")
    return close


def _log_price_spread(leg_a_close: float, leg_b_close: float, *, hedge_ratio: float) -> float:
    return math.log(leg_a_close) - hedge_ratio * math.log(leg_b_close)


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _positive_number(value: Any, name: str) -> float:
    number = _finite_number(value, name)
    if number <= 0:
        raise ValueError(f"{name} must be a positive number.")
    return number


def _non_negative_number(value: Any, name: str) -> float:
    number = _finite_number(value, name)
    if number < 0:
        raise ValueError(f"{name} must be a non-negative number.")
    return number


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def _unique_warnings(items: list[Any]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _round(value: float) -> float:
    return round(float(value), 6)
