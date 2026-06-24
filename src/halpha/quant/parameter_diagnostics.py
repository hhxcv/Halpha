from __future__ import annotations

from itertools import product
from typing import Any

from .strategy_records import parameter_diagnostic, warning


PARAMETER_DIAGNOSTIC_METRIC_SCOPE = "latest_state_and_canonical_next_bar_backtest_summary"
PARAMETER_DIAGNOSTIC_SELECTION_POLICY = "diagnostic_only_no_best_parameter_selection"
BACKTEST_EXECUTION_FIELDS = (
    "execution_model_id",
    "signal_timing",
    "position_timing",
    "lookahead_policy",
)
PERFORMANCE_STABILITY_MIN_VALID_COMBINATIONS = 2
PERFORMANCE_STABILITY_METRIC_THRESHOLDS = {
    "backtest_total_return_pct": 10.0,
    "backtest_max_drawdown_pct": 10.0,
    "backtest_trade_count": 3.0,
    "backtest_exposure_pct": 25.0,
}


def parameter_diagnostic_config(quant: dict[str, Any]) -> dict[str, Any]:
    diagnostics = quant.get("parameter_diagnostics")
    if not isinstance(diagnostics, dict) or diagnostics.get("enabled") is not True:
        return {
            "enabled": False,
            "max_combinations": 0,
            "grids": {},
        }
    grids = diagnostics.get("grids") if isinstance(diagnostics.get("grids"), dict) else {}
    return {
        "enabled": True,
        "max_combinations": int(diagnostics["max_combinations"]),
        "grids": grids,
    }


def bounded_parameter_diagnostic(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    base_run: dict[str, Any],
    definition: Any,
    config: dict[str, Any],
    engine: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    if config.get("enabled") is not True:
        return parameter_diagnostic()

    strategy_name = str(strategy["name"])
    grid = config.get("grids", {}).get(strategy_name)
    if not isinstance(grid, dict) or not grid:
        return _skipped_diagnostic(
            strategy_name,
            config=config,
            status="skipped",
            notes=[f"No parameter grid is configured for {strategy_name}."],
        )

    if base_run.get("status") != "succeeded":
        return _skipped_diagnostic(
            strategy_name,
            config=config,
            grid=grid,
            status="skipped",
            notes=[f"Parameter diagnostics skipped because base strategy status is {base_run.get('status')}."],
        )

    combinations = _parameter_combinations(grid)
    max_combinations = int(config["max_combinations"])
    if len(combinations) > max_combinations:
        return _skipped_diagnostic(
            strategy_name,
            config=config,
            grid=grid,
            status="skipped",
            notes=["Parameter diagnostics skipped because the grid exceeds max_combinations."],
            warnings=[
                warning(
                    "parameter_grid_over_limit",
                    (
                        f"{strategy_name} parameter grid has {len(combinations)} combinations; "
                        f"max_combinations is {max_combinations}."
                    ),
                    source="parameter_diagnostic",
                )
            ],
        )

    base_params = base_run.get("params") if isinstance(base_run.get("params"), dict) else {}
    results = []
    for index, grid_params in enumerate(combinations, start=1):
        params = {**base_params, **grid_params}
        result = _run_combination(
            strategy,
            view,
            rows,
            definition=definition,
            params=params,
            engine=engine,
            created_at=created_at,
        )
        results.append(
            {
                "combination_index": index,
                "params": params,
                "status": result["status"],
                "metrics": result["metrics"],
                "error": result["error"],
            }
        )

    valid_results = [item for item in results if item["status"] == "succeeded"]
    invalid_results = [item for item in results if item["status"] != "succeeded"]
    summary_metrics = _summary_metrics(valid_results)
    execution_model = _base_backtest_execution_fields(base_run)
    signal_state_stability = _signal_state_stability(valid_results, invalid_results)
    performance_stability = _performance_stability(valid_results, invalid_results)
    warnings = _sensitivity_warnings(
        strategy_name,
        valid_results=valid_results,
        invalid_results=invalid_results,
        base_run=base_run,
        signal_state_stability=signal_state_stability,
        performance_stability=performance_stability,
    )
    notes = _sensitivity_notes(valid_results=valid_results, invalid_results=invalid_results, base_run=base_run)
    return {
        "enabled": True,
        "status": "succeeded" if valid_results else "no_valid_combinations",
        "assumptions": {
            "max_combinations": max_combinations,
            "grid_source": f"quant.parameter_diagnostics.grids.{strategy_name}",
            "metric_scope": PARAMETER_DIAGNOSTIC_METRIC_SCOPE,
            "selection_policy": PARAMETER_DIAGNOSTIC_SELECTION_POLICY,
            "strategy_backtest_enabled": _backtest_enabled(strategy),
            **execution_model,
        },
        "grid": grid,
        "tested_combinations": len(results),
        "valid_combinations": len(valid_results),
        "invalid_combinations": len(invalid_results),
        "stability": signal_state_stability["status"],
        "signal_state_stability": signal_state_stability,
        "performance_stability": performance_stability,
        "summary_metrics": summary_metrics,
        "combinations": results,
        "notes": notes,
        "warnings": warnings,
    }


def _skipped_diagnostic(
    strategy_name: str,
    *,
    config: dict[str, Any],
    status: str,
    grid: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": status,
        "assumptions": {
            "max_combinations": int(config.get("max_combinations", 0)),
            "grid_source": f"quant.parameter_diagnostics.grids.{strategy_name}",
            "metric_scope": PARAMETER_DIAGNOSTIC_METRIC_SCOPE,
            "selection_policy": PARAMETER_DIAGNOSTIC_SELECTION_POLICY,
        },
        "grid": grid or {},
        "tested_combinations": 0,
        "valid_combinations": 0,
        "invalid_combinations": 0,
        "stability": "unknown",
        "signal_state_stability": _unknown_signal_state_stability(),
        "performance_stability": _unknown_performance_stability(),
        "summary_metrics": {},
        "combinations": [],
        "notes": notes or [],
        "warnings": warnings or [],
    }


def _parameter_combinations(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    names = sorted(grid)
    values = [grid[name] for name in names]
    return [dict(zip(names, item, strict=True)) for item in product(*values)]


def _run_combination(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    definition: Any,
    params: dict[str, Any],
    engine: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    diagnostic_strategy = {
        **strategy,
        "params": params,
    }
    try:
        run = definition.run(diagnostic_strategy, view, rows, engine=engine, created_at=created_at)
    except Exception as exc:
        return {
            "status": "failed",
            "metrics": {},
            "error": {
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        }
    return {
        "status": str(run.get("status")),
        "metrics": _combination_metrics(run),
        "error": _combination_error(run),
    }


def _combination_metrics(run: dict[str, Any]) -> dict[str, Any]:
    assessment = run.get("assessment") if isinstance(run.get("assessment"), dict) else {}
    signals = run.get("signals") if isinstance(run.get("signals"), dict) else {}
    backtest = run.get("backtest_diagnostic") if isinstance(run.get("backtest_diagnostic"), dict) else {}
    metrics = {
        "direction": assessment.get("direction", "unknown"),
        "strength": assessment.get("strength", "unknown"),
        "confidence": assessment.get("confidence", "unknown"),
    }
    for key in ("latest_regime", "latest_signal_active", "entry_count", "exit_count"):
        if key in signals:
            metrics[key] = signals[key]
    backtest_metrics = backtest.get("metrics") if isinstance(backtest.get("metrics"), dict) else {}
    for key in ("total_return_pct", "max_drawdown_pct", "trade_count", "exposure_pct"):
        if key in backtest_metrics:
            metrics[f"backtest_{key}"] = backtest_metrics[key]
    backtest_assumptions = backtest.get("assumptions") if isinstance(backtest.get("assumptions"), dict) else {}
    for key in BACKTEST_EXECUTION_FIELDS:
        if key in backtest_metrics:
            metrics[f"backtest_{key}"] = backtest_metrics[key]
        elif key in backtest_assumptions:
            metrics[f"backtest_{key}"] = backtest_assumptions[key]
    if "status" in backtest:
        metrics["backtest_diagnostic_status"] = backtest["status"]
    return metrics


def _combination_error(run: dict[str, Any]) -> dict[str, Any] | None:
    if run.get("status") == "succeeded":
        return None
    error = run.get("error") if isinstance(run.get("error"), dict) else {}
    if isinstance(error.get("message"), str):
        return {
            "error_type": error.get("error_type", "StrategyRunUnavailable"),
            "message": error["message"],
        }
    data_quality = run.get("data_quality") if isinstance(run.get("data_quality"), dict) else {}
    if run.get("status") == "insufficient_data":
        return {
            "error_type": "InsufficientData",
            "message": (
                f"Combination requires {data_quality.get('minimum_required_rows')} rows; "
                f"input has {data_quality.get('row_count')} rows."
            ),
        }
    return {
        "error_type": "StrategyRunUnavailable",
        "message": f"Combination status is {run.get('status')}.",
    }


def _summary_metrics(valid_results: list[dict[str, Any]]) -> dict[str, Any]:
    direction_counts = _value_counts(valid_results, "direction")
    regime_counts = _value_counts(valid_results, "latest_regime")
    summary: dict[str, Any] = {
        "direction_counts": direction_counts,
        "latest_regime_counts": regime_counts,
    }
    for key in (
        "entry_count",
        "exit_count",
        "backtest_total_return_pct",
        "backtest_max_drawdown_pct",
        "backtest_trade_count",
        "backtest_exposure_pct",
    ):
        values = [
            item["metrics"][key]
            for item in valid_results
            if isinstance(item.get("metrics"), dict) and isinstance(item["metrics"].get(key), (int, float))
        ]
        if values:
            summary[f"{key}_min"] = _round(min(values))
            summary[f"{key}_max"] = _round(max(values))
    return summary


def _value_counts(valid_results: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in valid_results:
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        value = metrics.get(key)
        if isinstance(value, str) and value.strip():
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _sensitivity_warnings(
    strategy_name: str,
    *,
    valid_results: list[dict[str, Any]],
    invalid_results: list[dict[str, Any]],
    base_run: dict[str, Any],
    signal_state_stability: dict[str, Any],
    performance_stability: dict[str, Any],
) -> list[dict[str, Any]]:
    items = []
    direction_counts = _value_counts(valid_results, "direction")
    if len(direction_counts) > 1:
        items.append(
            warning(
                "parameter_direction_sensitivity",
                f"{strategy_name} parameter grid produced multiple assessment directions.",
                source="parameter_diagnostic",
            )
        )
    regime_counts = _value_counts(valid_results, "latest_regime")
    if len(regime_counts) > 1:
        items.append(
            warning(
                "parameter_regime_sensitivity",
                f"{strategy_name} parameter grid produced multiple latest regimes.",
                source="parameter_diagnostic",
            )
        )
    if invalid_results:
        items.append(
            warning(
                "parameter_invalid_combinations",
                f"{strategy_name} parameter grid has {len(invalid_results)} invalid or unavailable combinations.",
                source="parameter_diagnostic",
            )
        )
    base_direction = _base_direction(base_run)
    if base_direction and direction_counts and base_direction not in direction_counts:
        items.append(
            warning(
                "base_direction_not_reproduced",
                f"{strategy_name} base direction was not reproduced by valid diagnostic combinations.",
                source="parameter_diagnostic",
            )
        )
    performance_status = performance_stability.get("status")
    if performance_status == "sensitive":
        items.append(
            warning(
                "parameter_performance_sensitivity",
                f"{strategy_name} parameter grid produced materially divergent backtest performance metrics.",
                source="parameter_diagnostic",
            )
        )
    elif performance_status == "partially_stable":
        items.append(
            warning(
                "parameter_performance_partial_evidence",
                f"{strategy_name} parameter grid has invalid combinations that limit performance stability evidence.",
                source="parameter_diagnostic",
            )
        )
    elif performance_status in {"insufficient_evidence", "no_valid_combinations"}:
        items.append(
            warning(
                "parameter_performance_insufficient_evidence",
                f"{strategy_name} parameter grid lacks enough valid backtest metrics for performance stability.",
                source="parameter_diagnostic",
            )
        )
    if signal_state_stability.get("status") == "sensitive":
        items.append(
            warning(
                "parameter_signal_state_sensitivity",
                f"{strategy_name} parameter grid produced divergent signal-state labels.",
                source="parameter_diagnostic",
            )
        )
    return items


def _sensitivity_notes(
    *,
    valid_results: list[dict[str, Any]],
    invalid_results: list[dict[str, Any]],
    base_run: dict[str, Any],
) -> list[str]:
    notes = [
        "Parameter diagnostics compare configured nearby values and do not choose trading parameters.",
        "Results are bounded sensitivity context, not optimization output or return forecasts.",
    ]
    direction_counts = _value_counts(valid_results, "direction")
    base_direction = _base_direction(base_run)
    if not valid_results:
        notes.append("No valid parameter combinations were available for sensitivity comparison.")
    elif len(direction_counts) == 1 and (not base_direction or base_direction in direction_counts):
        notes.append("Valid parameter combinations preserved the base assessment direction.")
    else:
        notes.append("Valid parameter combinations did not preserve one stable assessment direction.")
    if invalid_results:
        notes.append("Some parameter combinations were invalid or unavailable for the current input window.")
    return notes


def _signal_state_stability(
    valid_results: list[dict[str, Any]],
    invalid_results: list[dict[str, Any]],
) -> dict[str, Any]:
    direction_counts = _value_counts(valid_results, "direction")
    regime_counts = _value_counts(valid_results, "latest_regime")
    reason_codes = []
    if not valid_results:
        status = "no_valid_combinations"
        reason_codes.append("no_valid_combinations")
    elif len(direction_counts) <= 1 and len(regime_counts) <= 1 and not invalid_results:
        status = "stable"
        reason_codes.append("direction_and_regime_agree")
    elif len(direction_counts) <= 1 and len(regime_counts) <= 1 and invalid_results:
        status = "partially_stable_with_invalid_combinations"
        reason_codes.extend(["direction_and_regime_agree", "invalid_combinations_present"])
    else:
        status = "sensitive"
        if len(direction_counts) > 1:
            reason_codes.append("direction_sensitivity")
        if len(regime_counts) > 1:
            reason_codes.append("latest_regime_sensitivity")
        if invalid_results:
            reason_codes.append("invalid_combinations_present")
    return {
        "status": status,
        "reason_codes": reason_codes,
        "direction_counts": direction_counts,
        "latest_regime_counts": regime_counts,
        "valid_combinations": len(valid_results),
        "invalid_combinations": len(invalid_results),
    }


def _performance_stability(
    valid_results: list[dict[str, Any]],
    invalid_results: list[dict[str, Any]],
) -> dict[str, Any]:
    metric_ranges = _performance_metric_ranges(valid_results)
    reasons: list[dict[str, Any]] = []
    if not valid_results:
        reasons.append(_stability_reason("no_valid_combinations", "No valid parameter combinations were available."))
        status = "no_valid_combinations"
    elif len(valid_results) < PERFORMANCE_STABILITY_MIN_VALID_COMBINATIONS:
        reasons.append(
            _stability_reason(
                "too_few_valid_combinations",
                "Performance stability requires at least two valid combinations.",
                value=len(valid_results),
                threshold=PERFORMANCE_STABILITY_MIN_VALID_COMBINATIONS,
            )
        )
        status = "insufficient_evidence"
    else:
        missing_metric_reasons = [
            _stability_reason(
                "missing_backtest_metric",
                f"{metric} is missing from at least one valid combination.",
                metric=metric,
                value=details["observed_count"],
                threshold=details["valid_combination_count"],
            )
            for metric, details in metric_ranges.items()
            if details["missing_count"] > 0
        ]
        if missing_metric_reasons:
            reasons.extend(missing_metric_reasons)
            status = "insufficient_evidence"
        else:
            range_reasons = [
                _stability_reason(
                    "metric_range_exceeds_threshold",
                    f"{metric} range exceeds the performance stability threshold.",
                    metric=metric,
                    value=details["range"],
                    threshold=details["threshold"],
                )
                for metric, details in metric_ranges.items()
                if details["range"] is not None and details["range"] > details["threshold"]
            ]
            if range_reasons:
                reasons.extend(range_reasons)
                status = "sensitive"
            elif invalid_results:
                reasons.append(
                    _stability_reason(
                        "invalid_combinations_present",
                        "Invalid combinations limit performance stability evidence.",
                        value=len(invalid_results),
                    )
                )
                status = "partially_stable"
            else:
                reasons.append(
                    _stability_reason(
                        "metric_ranges_within_thresholds",
                        "All bounded performance metric ranges are within configured thresholds.",
                    )
                )
                status = "stable"
    return {
        "status": status,
        "reason_codes": [str(item["code"]) for item in reasons],
        "reasons": reasons,
        "metric_ranges": metric_ranges,
        "valid_combinations": len(valid_results),
        "invalid_combinations": len(invalid_results),
        "min_valid_combinations": PERFORMANCE_STABILITY_MIN_VALID_COMBINATIONS,
    }


def _performance_metric_ranges(valid_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ranges = {}
    for metric, threshold in PERFORMANCE_STABILITY_METRIC_THRESHOLDS.items():
        values = [
            item["metrics"][metric]
            for item in valid_results
            if isinstance(item.get("metrics"), dict)
            and isinstance(item["metrics"].get(metric), (int, float))
            and not isinstance(item["metrics"].get(metric), bool)
        ]
        details: dict[str, Any] = {
            "observed_count": len(values),
            "valid_combination_count": len(valid_results),
            "missing_count": len(valid_results) - len(values),
            "threshold": threshold,
        }
        if values:
            minimum = _round(min(values))
            maximum = _round(max(values))
            details.update(
                {
                    "min": minimum,
                    "max": maximum,
                    "range": _round(maximum - minimum),
                }
            )
        else:
            details.update({"min": None, "max": None, "range": None})
        ranges[metric] = details
    return ranges


def _stability_reason(
    code: str,
    message: str,
    *,
    metric: str | None = None,
    value: Any = None,
    threshold: Any = None,
) -> dict[str, Any]:
    result = {
        "code": code,
        "message": message,
    }
    if metric is not None:
        result["metric"] = metric
    if value is not None:
        result["value"] = value
    if threshold is not None:
        result["threshold"] = threshold
    return result


def _unknown_signal_state_stability() -> dict[str, Any]:
    return {
        "status": "unknown",
        "reason_codes": ["diagnostic_unavailable"],
        "direction_counts": {},
        "latest_regime_counts": {},
        "valid_combinations": 0,
        "invalid_combinations": 0,
    }


def _unknown_performance_stability() -> dict[str, Any]:
    return {
        "status": "insufficient_evidence",
        "reason_codes": ["diagnostic_unavailable"],
        "reasons": [
            _stability_reason("diagnostic_unavailable", "Parameter diagnostics did not run.")
        ],
        "metric_ranges": {},
        "valid_combinations": 0,
        "invalid_combinations": 0,
        "min_valid_combinations": PERFORMANCE_STABILITY_MIN_VALID_COMBINATIONS,
    }


def _base_direction(base_run: dict[str, Any]) -> str | None:
    assessment = base_run.get("assessment") if isinstance(base_run.get("assessment"), dict) else {}
    direction = assessment.get("direction")
    if isinstance(direction, str) and direction.strip():
        return direction
    return None


def _backtest_enabled(strategy: dict[str, Any]) -> bool:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    return backtest.get("enabled") is True


def _base_backtest_execution_fields(base_run: dict[str, Any]) -> dict[str, Any]:
    backtest = (
        base_run.get("backtest_diagnostic")
        if isinstance(base_run.get("backtest_diagnostic"), dict)
        else {}
    )
    assumptions = backtest.get("assumptions") if isinstance(backtest.get("assumptions"), dict) else {}
    metrics = backtest.get("metrics") if isinstance(backtest.get("metrics"), dict) else {}
    result = {}
    for key in BACKTEST_EXECUTION_FIELDS:
        if key in metrics:
            result[key] = metrics[key]
        elif key in assumptions:
            result[key] = assumptions[key]
    return result


def _round(value: float) -> float:
    return round(float(value), 6)
