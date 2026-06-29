from __future__ import annotations

import math
from typing import Any

from ..multi_leg_evaluation import evaluate_multi_leg_backtest
from ..strategy_records import data_quality, parameter_diagnostic, strategy_run_record, warning
from ..strategy_specs import require_strategy_spec


NAME = "cross_sectional_momentum"
SPEC = require_strategy_spec(NAME)
DEFAULT_PARAMS = dict(SPEC.default_params)
CALCULATION_BACKEND = "python.cross_sectional_close_return_rank"
POSITION_POLICY = "research_multi_leg_target_exposure"
LONG_SIDE_GROSS_EXPOSURE = 0.5
SHORT_SIDE_GROSS_EXPOSURE = 0.5


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
        "cross_sectional_strategy_requires_universe_input",
        "cross_sectional_momentum requires an explicit multi-instrument OHLCV universe.",
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
            "minimum_instrument_count": params["min_instrument_count"],
            "exposure_assumptions": _exposure_assumptions(params),
        },
        signals={
            "status": "requires_multi_instrument_input",
            "position_policy": POSITION_POLICY,
        },
        backtest_diagnostic={
            "enabled": False,
            "status": "requires_multi_instrument_input",
        },
        parameter_diagnostic=parameter_diagnostic(),
        assessment={
            "direction": "unknown",
            "strength": "unknown",
            "confidence": "low",
            "summary": "Cross-sectional strategy assessment requires an explicit aligned instrument universe.",
            "evidence": [],
            "uncertainty": [
                "Single-symbol strategy runs do not provide the aligned universe needed for cross-sectional ranking.",
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
        "cross_sectional_strategy_requires_universe_input",
        "cross_sectional_momentum signal records require explicit OHLCV legs.",
        source="strategy",
    )
    return _signal_record_set(
        params=params,
        legs=[],
        status="insufficient_data",
        records=[],
        ranking_summary={},
        warnings=[item],
    )


def universe_signal_records(strategy: dict[str, Any], legs: list[dict[str, Any]]) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    universe, leg_warnings = _universe_legs(legs)
    aligned = _aligned_universe_rows(universe) if len(universe) >= 2 else None
    records = _flat_records(params=params, legs=universe, aligned=aligned) if aligned else []
    universe_warnings = _universe_warnings(params, universe, aligned)
    if universe_warnings:
        return _signal_record_set(
            params=params,
            legs=universe,
            status="insufficient_data",
            records=records,
            ranking_summary=_ranking_summary(records),
            warnings=[*leg_warnings, *universe_warnings],
            alignment=aligned,
        )

    if aligned is None:
        return _signal_record_set(
            params=params,
            legs=universe,
            status="insufficient_data",
            records=[],
            ranking_summary={},
            warnings=[
                *leg_warnings,
                warning(
                    "insufficient_aligned_universe_rows",
                    (
                        "cross_sectional_momentum has 0 aligned rows; "
                        f"requires at least {_minimum_rows(params)} rows."
                    ),
                    source="data_quality",
                ),
            ],
            alignment=None,
        )
    records = _records_from_aligned_universe(params=params, legs=universe, aligned=aligned)
    warnings = [*leg_warnings, *_alignment_warnings(aligned), *_tie_warnings(records)]
    if not any(record["gross_exposure"] > 0 for record in records):
        warnings.append(
            warning(
                "no_cross_sectional_exposure",
                "cross_sectional_momentum target exposure stayed flat throughout the aligned window.",
                source="strategy",
            )
        )
    return _signal_record_set(
        params=params,
        legs=universe,
        status="succeeded",
        records=records,
        ranking_summary=_ranking_summary(records),
        warnings=warnings,
        alignment=aligned,
    )


def evaluate_universe_backtest(
    strategy: dict[str, Any],
    legs: list[dict[str, Any]],
    *,
    cost_assumptions: dict[str, Any] | None = None,
    execution_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    signals = universe_signal_records(strategy, legs)
    universe, _ = _universe_legs(legs)
    evaluation = evaluate_multi_leg_backtest(
        strategy={"name": NAME, "params": params},
        legs=universe,
        signal_records=signals,
        cost_assumptions=cost_assumptions,
        execution_model=execution_model,
    )
    status = str(evaluation.get("status") or signals.get("status") or "failed")
    return {
        "schema_version": 1,
        "artifact_type": "cross_sectional_strategy_backtest",
        "status": status,
        "strategy_name": NAME,
        "strategy_family": SPEC.family,
        "output_position_policy": POSITION_POLICY,
        "params": params,
        "exposure_assumptions": _exposure_assumptions(params),
        "ranking_summary": signals.get("ranking_summary", {}),
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
    long_count = _positive_int(params["long_count"], "long_count")
    short_count = _positive_int(params["short_count"], "short_count")
    min_instrument_count = _positive_int(params["min_instrument_count"], "min_instrument_count")
    if min_instrument_count < long_count + short_count:
        raise ValueError("min_instrument_count must be at least long_count + short_count.")
    return {
        "lookback_window": lookback_window,
        "long_count": long_count,
        "short_count": short_count,
        "min_instrument_count": min_instrument_count,
    }


def _minimum_rows(params: dict[str, Any]) -> int:
    return int(params["lookback_window"]) + 1


def _universe_legs(legs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(legs, list):
        return [], [
            warning("invalid_universe_legs", "cross_sectional_momentum legs must be a list.", source="strategy"),
        ]
    normalized = []
    warnings = []
    seen = set()
    for raw in legs:
        if not isinstance(raw, dict):
            warnings.append(warning("invalid_universe_leg", "Universe skipped a non-object leg.", source="strategy"))
            continue
        identity = raw.get("market_identity") if isinstance(raw.get("market_identity"), dict) else raw
        source = str(identity.get("source") or "unknown")
        symbol = str(identity.get("symbol") or "unknown")
        timeframe = str(identity.get("timeframe") or "unknown")
        key = (source, symbol, timeframe)
        if key in seen:
            warnings.append(
                warning(
                    "duplicate_universe_instrument",
                    f"Duplicate universe instrument {source}:{symbol}:{timeframe} was skipped.",
                    source="strategy",
                )
            )
            continue
        seen.add(key)
        rows = _sorted_rows(raw.get("ohlcv_rows") if isinstance(raw.get("ohlcv_rows"), list) else [])
        normalized.append(
            {
                "leg_id": f"rank_leg:{source}:{symbol}:{timeframe}",
                "source": source,
                "symbol": symbol,
                "timeframe": timeframe,
                "price_basis": str(raw.get("price_basis") or "close"),
                "rows": rows,
                "rows_by_time": {_open_time(row): row for row in rows},
                "market_identity": {
                    "source": source,
                    "symbol": symbol,
                    "timeframe": timeframe,
                },
                "ohlcv_rows": rows,
            }
        )
    normalized.sort(key=lambda leg: (leg["source"], leg["symbol"], leg["timeframe"]))
    return normalized, warnings


def _aligned_universe_rows(legs: list[dict[str, Any]]) -> dict[str, Any]:
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
    timeframes = sorted({leg["timeframe"] for leg in legs})
    return {
        "status": "aligned" if times and len(timeframes) == 1 and not any(item["omitted_rows"] for item in omitted_rows) else "degraded",
        "time_policy": "inner_join_open_time",
        "row_count": len(times),
        "times": times,
        "omitted_rows": omitted_rows,
        "timeframes": timeframes,
    }


def _universe_warnings(
    params: dict[str, Any],
    legs: list[dict[str, Any]],
    aligned: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if len(legs) < int(params["min_instrument_count"]):
        return [
            warning(
                "insufficient_universe_instruments",
                (
                    f"cross_sectional_momentum has {len(legs)} instruments; "
                    f"requires at least {params['min_instrument_count']}."
                ),
                source="data_quality",
            )
        ]
    if len(legs) < int(params["long_count"]) + int(params["short_count"]):
        return [
            warning(
                "insufficient_rank_slots",
                "cross_sectional_momentum needs enough instruments for configured long and short rank slots.",
                source="data_quality",
            )
        ]
    if aligned is None or len(aligned["times"]) < _minimum_rows(params):
        row_count = 0 if aligned is None else len(aligned["times"])
        return [
            warning(
                "insufficient_aligned_universe_rows",
                (
                    f"cross_sectional_momentum has {row_count} aligned rows; "
                    f"requires at least {_minimum_rows(params)} rows."
                ),
                source="data_quality",
            )
        ]
    if len(aligned.get("timeframes", [])) > 1:
        return [
            warning(
                "mismatched_universe_timeframes",
                "cross_sectional_momentum requires one shared timeframe and does not resample mixed-frequency legs.",
                source="data_quality",
            )
        ]
    return []


def _records_from_aligned_universe(
    *,
    params: dict[str, Any],
    legs: list[dict[str, Any]],
    aligned: dict[str, Any],
) -> list[dict[str, Any]]:
    times = aligned["times"]
    records = []
    previous_active = set()
    for index, time in enumerate(times):
        rank_inputs = _rank_inputs(legs, times, index, lookback_window=int(params["lookback_window"]))
        exposures = _target_exposures(rank_inputs, params=params) if rank_inputs else {}
        active = {leg_id for leg_id, exposure in exposures.items() if exposure != 0.0}
        records.append(_signal_record(time, legs, rank_inputs, exposures, previous_active))
        previous_active = active
    return records


def _flat_records(
    *,
    params: dict[str, Any],
    legs: list[dict[str, Any]],
    aligned: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not aligned:
        return []
    records = []
    previous_active: set[str] = set()
    for time in aligned["times"]:
        records.append(_signal_record(time, legs, [], {}, previous_active))
        previous_active = set()
    return records


def _rank_inputs(
    legs: list[dict[str, Any]],
    times: list[str],
    index: int,
    *,
    lookback_window: int,
) -> list[dict[str, Any]]:
    if index < lookback_window:
        return []
    start_time = times[index - lookback_window]
    end_time = times[index]
    inputs = []
    for leg in legs:
        start_close = _positive_close(leg["rows_by_time"][start_time])
        end_close = _positive_close(leg["rows_by_time"][end_time])
        momentum_return = end_close / start_close - 1
        inputs.append(
            {
                "leg_id": leg["leg_id"],
                "source": leg["source"],
                "symbol": leg["symbol"],
                "timeframe": leg["timeframe"],
                "lookback_start_time": start_time,
                "lookback_end_time": end_time,
                "momentum_return_pct": _pct(momentum_return),
                "tie_breaker": f"{leg['source']}:{leg['symbol']}:{leg['timeframe']}",
            }
        )
    ranked = sorted(
        inputs,
        key=lambda item: (-float(item["momentum_return_pct"]), item["source"], item["symbol"], item["timeframe"]),
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    return ranked


def _target_exposures(rank_inputs: list[dict[str, Any]], *, params: dict[str, Any]) -> dict[str, float]:
    long_count = int(params["long_count"])
    short_count = int(params["short_count"])
    exposures = {item["leg_id"]: 0.0 for item in rank_inputs}
    long_exposure = _round(LONG_SIDE_GROSS_EXPOSURE / long_count)
    short_exposure = _round(SHORT_SIDE_GROSS_EXPOSURE / short_count)
    for item in rank_inputs[:long_count]:
        exposures[item["leg_id"]] = long_exposure
    for item in rank_inputs[-short_count:]:
        exposures[item["leg_id"]] = -short_exposure
    return exposures


def _signal_record(
    time: str,
    legs: list[dict[str, Any]],
    rank_inputs: list[dict[str, Any]],
    exposures: dict[str, float],
    previous_active: set[str],
) -> dict[str, Any]:
    active = {leg_id for leg_id, exposure in exposures.items() if exposure != 0.0}
    leg_records = [_signal_leg(leg, exposures.get(leg["leg_id"], 0.0)) for leg in legs]
    gross_exposure = sum(abs(float(item["target_exposure"])) for item in leg_records)
    net_exposure = sum(float(item["target_exposure"]) for item in leg_records)
    return {
        "schema_version": 1,
        "record_type": "multi_leg_signal",
        "signal_time": time,
        "open_time": time,
        "strategy_name": NAME,
        "strategy_version": 1,
        "position_policy": POSITION_POLICY,
        "signal": {
            "active": bool(active),
            "position_state": "long_short" if active else "flat",
        },
        "indicator_context": {
            "calculation_backend": CALCULATION_BACKEND,
            "ranking_feature": "close_to_close_momentum_return",
            "rank_inputs_available": bool(rank_inputs),
            "ranked_instrument_count": len(rank_inputs),
            "lookahead_policy": "closed_bar_no_lookahead",
            "signal_timing": "signal_at_bar_close",
            "position_timing": "next_bar",
        },
        "rank_inputs": rank_inputs,
        "legs": leg_records,
        "gross_exposure": _round(gross_exposure),
        "net_exposure": _round(net_exposure),
        "entry": bool(active - previous_active),
        "exit": bool(previous_active - active),
        "warnings": [],
    }


def _signal_leg(leg: dict[str, Any], target_exposure: float) -> dict[str, Any]:
    return {
        "leg_id": leg["leg_id"],
        "instrument_identity": dict(leg["market_identity"]),
        "target_exposure": _round(target_exposure),
        "price_basis": "close",
    }


def _signal_record_set(
    *,
    params: dict[str, Any],
    legs: list[dict[str, Any]],
    status: str,
    records: list[dict[str, Any]],
    ranking_summary: dict[str, Any],
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
        "exposure_assumptions": _exposure_assumptions(params),
        "alignment": _public_alignment(alignment),
        "legs": [_public_leg(leg) for leg in legs],
        "records": records,
        "latest_record": records[-1] if records else None,
        "record_count": len(records),
        "active_count": sum(1 for record in records if record["signal"]["active"]),
        "flat_count": sum(1 for record in records if not record["signal"]["active"]),
        "entry_count": sum(1 for record in records if record["entry"]),
        "exit_count": sum(1 for record in records if record["exit"]),
        "ranking_summary": ranking_summary,
        "warnings": _unique_warnings(warnings),
    }


def _exposure_assumptions(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "equal_gross_long_short_rank_buckets",
        "gross_exposure_cap": 1.0,
        "long_side_gross_exposure": LONG_SIDE_GROSS_EXPOSURE,
        "short_side_gross_exposure": SHORT_SIDE_GROSS_EXPOSURE,
        "long_count": int(params["long_count"]),
        "short_count": int(params["short_count"]),
        "position_unit": "research_leg_exposure",
        "account_allocation": "not_modeled",
        "leverage": "not_modeled",
    }


def _ranking_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_records = [record for record in records if record["rank_inputs"]]
    latest = ranked_records[-1] if ranked_records else None
    latest_ranks = latest["rank_inputs"] if latest else []
    return {
        "calculation_backend": CALCULATION_BACKEND,
        "ranking_feature": "close_to_close_momentum_return",
        "ranked_record_count": len(ranked_records),
        "latest_long_symbols": [
            leg["instrument_identity"]["symbol"]
            for leg in latest["legs"]
            if latest and float(leg["target_exposure"]) > 0
        ]
        if latest
        else [],
        "latest_short_symbols": [
            leg["instrument_identity"]["symbol"]
            for leg in latest["legs"]
            if latest and float(leg["target_exposure"]) < 0
        ]
        if latest
        else [],
        "latest_rank_inputs": latest_ranks,
    }


def _alignment_warnings(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    omitted = sum(int(item["omitted_rows"]) for item in alignment.get("omitted_rows", []))
    if not omitted:
        return []
    return [
        warning(
            "universe_alignment_degraded",
            f"Cross-sectional alignment omitted {omitted} rows that were not common to every instrument.",
            source="data_quality",
        )
    ]


def _tie_warnings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for record in records:
        scores = [item["momentum_return_pct"] for item in record["rank_inputs"]]
        if len(scores) != len(set(scores)):
            return [
                warning(
                    "cross_sectional_ties_resolved_deterministically",
                    "Equal momentum ranks were resolved by source, symbol, and timeframe ordering.",
                    source="strategy",
                )
            ]
    return []


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
        raise ValueError("close must be a positive number for cross-sectional strategy evaluation.")
    return close


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def _pct(value: float) -> float:
    return _round(value * 100)


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
