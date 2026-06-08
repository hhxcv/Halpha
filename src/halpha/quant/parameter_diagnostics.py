from __future__ import annotations

from itertools import product
from typing import Any

from .strategy_records import parameter_diagnostic, warning


PARAMETER_DIAGNOSTIC_METRIC_SCOPE = "latest_state_and_bounded_backtest_summary"
PARAMETER_DIAGNOSTIC_SELECTION_POLICY = "diagnostic_only_no_best_parameter_selection"


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
    warnings = _sensitivity_warnings(
        strategy_name,
        valid_results=valid_results,
        invalid_results=invalid_results,
        base_run=base_run,
    )
    notes = _sensitivity_notes(valid_results=valid_results, invalid_results=invalid_results, base_run=base_run)
    stability = _stability_state(valid_results, invalid_results)
    return {
        "enabled": True,
        "status": "succeeded" if valid_results else "no_valid_combinations",
        "assumptions": {
            "max_combinations": max_combinations,
            "grid_source": f"quant.parameter_diagnostics.grids.{strategy_name}",
            "metric_scope": PARAMETER_DIAGNOSTIC_METRIC_SCOPE,
            "selection_policy": PARAMETER_DIAGNOSTIC_SELECTION_POLICY,
            "strategy_backtest_enabled": _backtest_enabled(strategy),
        },
        "grid": grid,
        "tested_combinations": len(results),
        "valid_combinations": len(valid_results),
        "invalid_combinations": len(invalid_results),
        "stability": stability,
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
    for key in ("entry_count", "exit_count", "backtest_total_return_pct", "backtest_max_drawdown_pct"):
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


def _stability_state(valid_results: list[dict[str, Any]], invalid_results: list[dict[str, Any]]) -> str:
    if not valid_results:
        return "no_valid_combinations"
    direction_counts = _value_counts(valid_results, "direction")
    regime_counts = _value_counts(valid_results, "latest_regime")
    if len(direction_counts) <= 1 and len(regime_counts) <= 1 and not invalid_results:
        return "stable"
    if len(direction_counts) <= 1 and invalid_results:
        return "partially_stable_with_invalid_combinations"
    return "sensitive"


def _base_direction(base_run: dict[str, Any]) -> str | None:
    assessment = base_run.get("assessment") if isinstance(base_run.get("assessment"), dict) else {}
    direction = assessment.get("direction")
    if isinstance(direction, str) and direction.strip():
        return direction
    return None


def _backtest_enabled(strategy: dict[str, Any]) -> bool:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    return backtest.get("enabled") is True


def _round(value: float) -> float:
    return round(float(value), 6)
