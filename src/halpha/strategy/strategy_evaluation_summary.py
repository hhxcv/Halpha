from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.market.market_data_views import MARKET_DATA_VIEWS_ARTIFACT, load_market_data_view_records
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.quant.registry import get_strategy_definition
from halpha.quant.strategy_evaluation import (
    HIGH_COST_DRAG_PCT_THRESHOLD,
    evaluate_single_window_backtest,
    evaluate_walk_forward_backtest,
)
from halpha.quant.strategy_records import STRATEGY_VERSION, warning
from halpha.strategy.strategy_evaluation_material import (
    STRATEGY_EVALUATION_MATERIAL_ARTIFACT,
    render_strategy_evaluation_material,
)
from halpha.strategy.strategy_evaluation_history import (
    STRATEGY_EVALUATION_HISTORY_ARTIFACT,
    register_report_strategy_evaluations,
)
from halpha.storage import resolve_runtime_path, write_json


STAGE_NAME = "evaluate_strategy_evaluation"
STRATEGY_EVALUATION_ARTIFACT = "analysis/strategy_evaluation_summary.json"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
SCHEMA_VERSION = 1
HIGH_PARAMETER_TRIAL_COUNT_THRESHOLD = 8
OVERFITTING_SHORT_SAMPLE_ROWS = 120
OVERFITTING_LOW_TRADE_COUNT_THRESHOLD = 3
PARAMETER_RETURN_RANGE_THRESHOLD_PCT = 10.0


def build_strategy_evaluation_summary(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    quant = config.get("quant")
    if not isinstance(quant, dict) or quant.get("enabled") is not True:
        _record_zero_counts(run)
        return []

    strategy_runs_artifact = _read_quant_strategy_runs(run)
    views_artifact = _read_market_data_views(run)
    views_by_id = {
        view.get("view_id"): view for view in views_artifact.get("views", []) if isinstance(view, dict)
    }
    storage_dir = _storage_dir(config, run.config_path)
    created_at = _created_at(strategy_runs_artifact, now)
    records = [
        _evaluation_record(
            config,
            strategy_run,
            views_by_id=views_by_id,
            storage_dir=storage_dir,
            created_at=created_at,
        )
        for strategy_run in strategy_runs_artifact["runs"]
    ]
    warnings = _artifact_warnings(records)
    errors = [record["error"] for record in records if isinstance(record.get("error"), dict)]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "strategy_evaluation_summary",
        "created_at": created_at,
        "source_artifacts": [QUANT_STRATEGY_RUNS_ARTIFACT, MARKET_DATA_VIEWS_ARTIFACT],
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }
    write_json(run.analysis_dir / "strategy_evaluation_summary.json", artifact)
    (run.analysis_dir / "strategy_evaluation_material.md").write_text(
        render_strategy_evaluation_material(artifact),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["strategy_evaluation_summary"] = STRATEGY_EVALUATION_ARTIFACT
    run.manifest["artifacts"]["strategy_evaluation_material"] = STRATEGY_EVALUATION_MATERIAL_ARTIFACT
    run.manifest["artifacts"]["strategy_evaluation_history"] = STRATEGY_EVALUATION_HISTORY_ARTIFACT
    run.manifest["counts"]["strategy_evaluation_material_records"] = len(records)
    run.manifest["counts"]["strategy_evaluation_history_records_upserted"] = register_report_strategy_evaluations(
        run,
        artifact,
        now=created_at,
    )
    _record_manifest_counts(run, records)
    _record_manifest_summary(run, records, warnings=warnings, errors=errors)
    return [STRATEGY_EVALUATION_ARTIFACT, STRATEGY_EVALUATION_MATERIAL_ARTIFACT]


def _evaluation_record(
    config: dict[str, Any],
    strategy_run: dict[str, Any],
    *,
    views_by_id: dict[Any, dict[str, Any]],
    storage_dir: Path,
    created_at: str,
) -> dict[str, Any]:
    status = str(strategy_run.get("status") or "failed")
    if status != "succeeded":
        return _upstream_unavailable_record(strategy_run, status=status, created_at=created_at)

    view = views_by_id.get(strategy_run.get("input_view_id"))
    if view is None:
        return _failed_record(
            strategy_run,
            created_at=created_at,
            error_type="MissingInputView",
            message=f"input view was not found: {strategy_run.get('input_view_id')}",
        )

    name = str(strategy_run.get("strategy_name"))
    definition = get_strategy_definition(name)
    if definition is None:
        return _failed_record(
            strategy_run,
            created_at=created_at,
            error_type="UnsupportedStrategy",
            message=f"{name} is not implemented.",
        )

    try:
        rows = load_market_data_view_records(view, storage_dir=storage_dir)
        strategy = _strategy_input(config, strategy_run)
        signals = definition.signal_records(strategy, view, rows)
        single_window = evaluate_single_window_backtest(
            strategy=strategy,
            market_identity={
                "source": strategy_run.get("source"),
                "symbol": strategy_run.get("symbol"),
                "timeframe": strategy_run.get("timeframe"),
            },
            ohlcv_rows=rows,
            signal_records=signals,
            cost_assumptions=_cost_assumptions(strategy),
        )
        walk_forward = evaluate_walk_forward_backtest(
            strategy=strategy,
            market_identity={
                "source": strategy_run.get("source"),
                "symbol": strategy_run.get("symbol"),
                "timeframe": strategy_run.get("timeframe"),
            },
            ohlcv_rows=rows,
            signal_records=signals,
            cost_assumptions=_cost_assumptions(strategy),
        )
    except Exception as exc:
        return _failed_record(
            strategy_run,
            created_at=created_at,
            error_type=type(exc).__name__,
            message=str(exc),
        )

    record_status = str(single_window.get("status") or "failed")
    parameter_stability = _parameter_stability(strategy_run)
    overfitting_risk = _overfitting_risk(
        strategy_run,
        single_window,
        walk_forward,
        parameter_stability,
    )
    return _base_record(
        strategy_run,
        status=record_status,
        created_at=created_at,
        single_window=single_window,
        walk_forward=walk_forward,
        parameter_stability=parameter_stability,
        overfitting_risk=overfitting_risk,
        assessment=_assessment(single_window, walk_forward, parameter_stability, overfitting_risk),
        warnings=_record_warnings(single_window, walk_forward, parameter_stability, overfitting_risk),
        error=_record_error(single_window),
    )


def _upstream_unavailable_record(
    strategy_run: dict[str, Any],
    *,
    status: str,
    created_at: str,
) -> dict[str, Any]:
    if status == "insufficient_data":
        record_status = "insufficient_data"
        message = "Strategy evaluation is unavailable because the upstream strategy run has insufficient data."
        code = "upstream_strategy_insufficient_data"
    else:
        record_status = "skipped"
        message = f"Strategy evaluation skipped because upstream strategy run status is {status}."
        code = "upstream_strategy_not_succeeded"
    item = warning(code, message, source="strategy_evaluation")
    return _base_record(
        strategy_run,
        status=record_status,
        created_at=created_at,
        single_window={
            "status": record_status,
            "reason": message,
            "strategy_run_status": status,
        },
        walk_forward=_skipped_walk_forward(message),
        parameter_stability=_parameter_stability(strategy_run),
        overfitting_risk=_unknown_overfitting_risk(),
        assessment=_empty_assessment(message),
        warnings=[item],
        error=None if status == "insufficient_data" else strategy_run.get("error"),
    )


def _failed_record(
    strategy_run: dict[str, Any],
    *,
    created_at: str,
    error_type: str,
    message: str,
) -> dict[str, Any]:
    return _base_record(
        strategy_run,
        status="failed",
        created_at=created_at,
        single_window={
            "status": "failed",
            "errors": [
                {
                    "error_type": error_type,
                    "message": message,
                    "stage": STAGE_NAME,
                }
            ],
        },
        walk_forward=_skipped_walk_forward("Strategy evaluation failed before walk-forward evidence was available."),
        parameter_stability=_parameter_stability(strategy_run),
        overfitting_risk=_unknown_overfitting_risk(),
        assessment=_empty_assessment("Strategy evaluation failed before metrics were available."),
        warnings=[],
        error={
            "error_type": error_type,
            "message": message,
            "stage": STAGE_NAME,
        },
    )


def _base_record(
    strategy_run: dict[str, Any],
    *,
    status: str,
    created_at: str,
    single_window: dict[str, Any],
    walk_forward: dict[str, Any],
    parameter_stability: dict[str, Any],
    overfitting_risk: dict[str, Any],
    assessment: dict[str, Any],
    warnings: list[dict[str, Any]],
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    latest = strategy_run.get("latest_candle_time") or "missing"
    name = strategy_run.get("strategy_name")
    source = strategy_run.get("source")
    symbol = strategy_run.get("symbol")
    timeframe = strategy_run.get("timeframe")
    return {
        "evaluation_id": f"strategy_evaluation:{name}:{source}:{symbol}:{timeframe}:{latest}",
        "status": status,
        "strategy_run_id": strategy_run.get("strategy_run_id"),
        "strategy_name": name,
        "strategy_version": strategy_run.get("strategy_version", STRATEGY_VERSION),
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "input_view_id": strategy_run.get("input_view_id"),
        "input_window_start": strategy_run.get("input_window_start"),
        "input_window_end": strategy_run.get("input_window_end"),
        "latest_candle_time": strategy_run.get("latest_candle_time"),
        "params": strategy_run.get("params") if isinstance(strategy_run.get("params"), dict) else {},
        "single_window": single_window,
        "walk_forward": walk_forward,
        "parameter_stability": parameter_stability,
        "overfitting_risk": overfitting_risk,
        "assessment": assessment,
        "warnings": warnings,
        "error": error,
        "source_artifacts": [QUANT_STRATEGY_RUNS_ARTIFACT, MARKET_DATA_VIEWS_ARTIFACT],
        "created_at": created_at,
    }


def _strategy_input(config: dict[str, Any], strategy_run: dict[str, Any]) -> dict[str, Any]:
    name = str(strategy_run.get("strategy_name"))
    configured = _configured_strategy(config, name)
    return {
        "name": name,
        "params": strategy_run.get("params") if isinstance(strategy_run.get("params"), dict) else {},
        "backtest": configured.get("backtest") if isinstance(configured.get("backtest"), dict) else {},
    }


def _configured_strategy(config: dict[str, Any], name: str) -> dict[str, Any]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    strategies = quant.get("strategies") if isinstance(quant.get("strategies"), list) else []
    for strategy in strategies:
        if isinstance(strategy, dict) and strategy.get("name") == name and strategy.get("enabled", True) is not False:
            return strategy
    return {"name": name}


def _cost_assumptions(strategy: dict[str, Any]) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    return {
        "fees_bps": backtest.get("fees_bps", 0.0),
        "slippage_bps": backtest.get("slippage_bps", 0.0),
    }


def _assessment(
    single_window: dict[str, Any],
    walk_forward: dict[str, Any],
    parameter_stability: dict[str, Any],
    overfitting_risk: dict[str, Any],
) -> dict[str, Any]:
    status = single_window.get("status")
    if status != "succeeded":
        return _empty_assessment("Strategy evaluation has not produced enough evidence for reliability judgment.")

    metrics = single_window.get("strategy_metrics") if isinstance(single_window.get("strategy_metrics"), dict) else {}
    relative = single_window.get("relative_metrics") if isinstance(single_window.get("relative_metrics"), dict) else {}
    trade = single_window.get("trade_summary") if isinstance(single_window.get("trade_summary"), dict) else {}
    sample = single_window.get("sample") if isinstance(single_window.get("sample"), dict) else {}
    trade_count = int(trade.get("trade_count") or 0)
    rows = int(sample.get("rows") or 0)
    reliability = "medium" if trade_count >= 3 and rows >= 60 else "low"
    sample_quality = "sufficient" if rows >= 100 else "limited"
    walk_summary = (
        walk_forward.get("summary")
        if isinstance(walk_forward.get("summary"), dict)
        else {}
    )
    walk_status = str(walk_forward.get("status") or "unknown")
    if walk_status != "succeeded":
        reliability = "low"
    summary = (
        "Single-window strategy evaluation completed with "
        f"net_return_pct {metrics.get('net_return_pct')} and "
        f"max_drawdown_pct {metrics.get('max_drawdown_pct')}; "
        f"walk_forward_status is {walk_status} with "
        f"{walk_summary.get('succeeded_windows')} successful windows; "
        f"parameter_performance_stability_status is "
        f"{_parameter_performance_status(parameter_stability)}."
    )
    return {
        "reliability": reliability,
        "sample_quality": sample_quality,
        "cost_sensitivity": _cost_sensitivity(metrics),
        "overfitting_risk": overfitting_risk.get("status", "unknown"),
        "summary": summary,
        "evidence": [
            f"sample rows: {rows}.",
            f"trade_count: {trade_count}.",
            f"exposure_pct: {trade.get('exposure_pct')}.",
            f"cost_drag_pct: {metrics.get('cost_drag_pct')}.",
            f"excess_return_vs_buy_and_hold_pct: {relative.get('excess_return_vs_buy_and_hold_pct')}.",
            f"walk_forward_status: {walk_status}.",
            f"walk_forward_succeeded_windows: {walk_summary.get('succeeded_windows')}.",
            f"walk_forward_mean_net_return_pct: {walk_summary.get('mean_net_return_pct')}.",
            (
                "walk_forward_positive_net_return_window_pct: "
                f"{walk_summary.get('positive_net_return_window_pct')}."
            ),
            f"parameter_stability_status: {parameter_stability.get('status')}.",
            f"parameter_signal_state_stability_status: {_parameter_signal_state_status(parameter_stability)}.",
            f"parameter_performance_stability_status: {_parameter_performance_status(parameter_stability)}.",
            f"parameter_tested_combinations: {parameter_stability.get('tested_combinations')}.",
            f"overfitting_risk_status: {overfitting_risk.get('status')}.",
        ],
        "uncertainty": [
            "Single-window backtest is historical research material, not a forecast.",
            "Walk-forward evidence is bounded and uses fixed strategy params, not optimization.",
            "Parameter diagnostics are bounded sensitivity context, not parameter recommendations.",
        ],
    }


def _cost_sensitivity(metrics: dict[str, Any]) -> str:
    cost_drag_pct = metrics.get("cost_drag_pct")
    if isinstance(cost_drag_pct, bool) or not isinstance(cost_drag_pct, (int, float)):
        return "unknown"
    if cost_drag_pct >= HIGH_COST_DRAG_PCT_THRESHOLD:
        return "high"
    if cost_drag_pct > 0:
        return "medium"
    return "low"


def _parameter_stability(strategy_run: dict[str, Any]) -> dict[str, Any]:
    diagnostic = strategy_run.get("parameter_diagnostic")
    if not isinstance(diagnostic, dict) or diagnostic.get("enabled") is not True:
        return {
            "enabled": False,
            "status": "disabled",
        }

    combinations = [
        item for item in diagnostic.get("combinations", []) if isinstance(item, dict)
    ] if isinstance(diagnostic.get("combinations"), list) else []
    base_direction = _base_direction(strategy_run)
    regions = [_parameter_region(item, base_direction=base_direction) for item in combinations]
    region_counts = _region_counts(regions)
    signal_state_stability = _mapping(diagnostic.get("signal_state_stability"))
    if not signal_state_stability:
        signal_state_stability = {
            "status": diagnostic.get("stability", "unknown"),
            "reason_codes": [],
            "direction_counts": _mapping(diagnostic.get("summary_metrics")).get("direction_counts", {}),
            "latest_regime_counts": _mapping(diagnostic.get("summary_metrics")).get("latest_regime_counts", {}),
        }
    performance_stability = _mapping(diagnostic.get("performance_stability"))
    if not performance_stability:
        performance_stability = {
            "status": "insufficient_evidence",
            "reason_codes": ["performance_stability_unavailable"],
            "reasons": [],
            "metric_ranges": {},
        }
    status = _parameter_stability_status(diagnostic, region_counts, performance_stability)
    warnings = _unique_warnings(
        [
            *_warning_items(diagnostic.get("warnings")),
            *_parameter_stability_warnings(
                status,
                region_counts,
                signal_state_stability=signal_state_stability,
                performance_stability=performance_stability,
            ),
        ]
    )
    assumptions = diagnostic.get("assumptions") if isinstance(diagnostic.get("assumptions"), dict) else {}
    return {
        "enabled": True,
        "status": status,
        "diagnostic_status": diagnostic.get("status"),
        "selection_policy": assumptions.get("selection_policy"),
        "execution_model_id": assumptions.get("execution_model_id"),
        "position_timing": assumptions.get("position_timing"),
        "lookahead_policy": assumptions.get("lookahead_policy"),
        "tested_combinations": int(diagnostic.get("tested_combinations") or 0),
        "valid_combinations": int(diagnostic.get("valid_combinations") or 0),
        "invalid_combinations": int(diagnostic.get("invalid_combinations") or 0),
        "stability": diagnostic.get("stability"),
        "signal_state_status": signal_state_stability.get("status"),
        "performance_status": performance_stability.get("status"),
        "signal_state_stability": signal_state_stability,
        "performance_stability": performance_stability,
        "region_counts": region_counts,
        "regions": regions,
        "summary_metrics": diagnostic.get("summary_metrics")
        if isinstance(diagnostic.get("summary_metrics"), dict)
        else {},
        "evidence": [
            f"diagnostic_status: {diagnostic.get('status')}.",
            f"tested_combinations: {int(diagnostic.get('tested_combinations') or 0)}.",
            f"valid_combinations: {int(diagnostic.get('valid_combinations') or 0)}.",
            f"invalid_combinations: {int(diagnostic.get('invalid_combinations') or 0)}.",
            f"signal_state_stability_status: {signal_state_stability.get('status')}.",
            f"performance_stability_status: {performance_stability.get('status')}.",
            (
                "parameter_regions: "
                f"stable={region_counts['stable']}, fragile={region_counts['fragile']}, "
                f"inconsistent={region_counts['inconsistent']}, "
                f"insufficient_data={region_counts['insufficient_data']}."
            ),
        ],
        "notes": [item for item in diagnostic.get("notes", []) if isinstance(item, str)]
        if isinstance(diagnostic.get("notes"), list)
        else [],
        "warnings": warnings,
    }


def _parameter_region(combination: dict[str, Any], *, base_direction: str | None) -> dict[str, Any]:
    metrics = combination.get("metrics") if isinstance(combination.get("metrics"), dict) else {}
    status = str(combination.get("status") or "unknown")
    direction = metrics.get("direction") if isinstance(metrics.get("direction"), str) else "unknown"
    confidence = metrics.get("confidence") if isinstance(metrics.get("confidence"), str) else "unknown"
    trade_count = _number_or_none(metrics.get("backtest_trade_count"))
    evidence = []
    if status != "succeeded":
        region_status = "insufficient_data"
        error = combination.get("error") if isinstance(combination.get("error"), dict) else {}
        evidence.append(str(error.get("message") or f"combination status is {status}."))
    elif base_direction and direction != "unknown" and direction != base_direction:
        region_status = "inconsistent"
        evidence.append(f"direction {direction} differs from base direction {base_direction}.")
    elif confidence in {"low", "unknown"}:
        region_status = "fragile"
        evidence.append("combination has low confidence.")
    else:
        region_status = "stable"
        evidence.append("combination preserved base direction with usable evidence.")
    return {
        "combination_index": combination.get("combination_index"),
        "status": region_status,
        "diagnostic_status": status,
        "params": combination.get("params") if isinstance(combination.get("params"), dict) else {},
        "direction": direction,
        "confidence": confidence,
        "backtest_trade_count": trade_count,
        "backtest_total_return_pct": _number_or_none(metrics.get("backtest_total_return_pct")),
        "evidence": evidence,
    }


def _region_counts(regions: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "stable": 0,
        "fragile": 0,
        "inconsistent": 0,
        "insufficient_data": 0,
    }
    for region in regions:
        status = region.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _parameter_stability_status(
    diagnostic: dict[str, Any],
    region_counts: dict[str, int],
    performance_stability: dict[str, Any],
) -> str:
    diagnostic_status = diagnostic.get("status")
    if diagnostic_status in {"skipped", "no_valid_combinations"}:
        return "insufficient_data"
    performance_status = performance_stability.get("status")
    if performance_status == "stable":
        return "stable"
    if performance_status in {"partially_stable", "sensitive"}:
        return "fragile"
    if performance_status in {"insufficient_evidence", "no_valid_combinations"}:
        return "insufficient_data"
    if region_counts["inconsistent"] > 0:
        return "inconsistent"
    if region_counts["fragile"] > 0 or region_counts["insufficient_data"] > 0:
        return "fragile"
    if region_counts["stable"] > 0:
        return "stable"
    return "insufficient_data"


def _parameter_stability_warnings(
    status: str,
    region_counts: dict[str, int],
    *,
    signal_state_stability: dict[str, Any],
    performance_stability: dict[str, Any],
) -> list[dict[str, Any]]:
    items = []
    signal_state_status = signal_state_stability.get("status")
    performance_status = performance_stability.get("status")
    if signal_state_status == "sensitive":
        items.append(
            warning(
                "parameter_signal_state_stability_sensitive",
                "Parameter diagnostics produced divergent signal-state labels.",
                source="strategy_evaluation",
            )
        )
    elif signal_state_status == "partially_stable_with_invalid_combinations":
        items.append(
            warning(
                "parameter_signal_state_stability_partial",
                "Parameter signal-state stability is limited by invalid combinations.",
                source="strategy_evaluation",
            )
        )
    if performance_status == "sensitive":
        items.append(
            warning(
                "parameter_performance_stability_sensitive",
                "Parameter diagnostics produced materially divergent performance metrics.",
                source="strategy_evaluation",
            )
        )
    elif performance_status == "partially_stable":
        items.append(
            warning(
                "parameter_performance_stability_partial",
                "Parameter performance stability is limited by invalid combinations.",
                source="strategy_evaluation",
            )
        )
    elif performance_status in {"insufficient_evidence", "no_valid_combinations"}:
        items.append(
            warning(
                "parameter_performance_stability_insufficient",
                "Parameter diagnostics lack enough performance evidence for stability.",
                source="strategy_evaluation",
            )
        )
    if status == "stable":
        return items
    if status == "inconsistent":
        items.append(
            warning(
                "parameter_stability_inconsistent",
                "Parameter diagnostics produced inconsistent regions across configured combinations.",
                source="strategy_evaluation",
            )
        )
        return items
    if status == "fragile":
        items.append(
            warning(
                "parameter_stability_fragile",
                (
                    "Parameter diagnostics include fragile performance evidence or unavailable regions "
                    f"({region_counts['fragile']} fragile, "
                    f"{region_counts['insufficient_data']} insufficient-data)."
                ),
                source="strategy_evaluation",
            )
        )
        return items
    items.append(
        warning(
            "parameter_stability_insufficient_data",
            "Parameter diagnostics did not produce enough valid performance evidence.",
            source="strategy_evaluation",
        )
    )
    return items


def _overfitting_risk(
    strategy_run: dict[str, Any],
    single_window: dict[str, Any],
    walk_forward: dict[str, Any],
    parameter_stability: dict[str, Any],
) -> dict[str, Any]:
    warnings = []
    evidence = []
    tested = _int_value(parameter_stability.get("tested_combinations"))
    if tested >= HIGH_PARAMETER_TRIAL_COUNT_THRESHOLD:
        warnings.append(
            warning(
                "overfitting_high_trial_count",
                f"Parameter diagnostics tested {tested} combinations; selection risk should stay explicit.",
                source="strategy_evaluation",
            )
        )
    sample = single_window.get("sample") if isinstance(single_window.get("sample"), dict) else {}
    rows = _int_value(sample.get("rows"))
    if 0 < rows < OVERFITTING_SHORT_SAMPLE_ROWS:
        warnings.append(
            warning(
                "overfitting_short_sample",
                f"Evaluation sample has {rows} rows, which is short for parameter stability claims.",
                source="strategy_evaluation",
            )
        )
    stability_status = str(parameter_stability.get("status") or "unknown")
    signal_state_status = _parameter_signal_state_status(parameter_stability)
    performance_status = _parameter_performance_status(parameter_stability)
    if performance_status in {"partially_stable", "sensitive"} or stability_status in {"fragile", "inconsistent"}:
        warnings.append(
            warning(
                "overfitting_unstable_parameter_ranking",
                f"Parameter performance stability status is {performance_status}; do not infer a best parameter set.",
                source="strategy_evaluation",
            )
        )
    if performance_status in {"insufficient_evidence", "no_valid_combinations"} or stability_status == "insufficient_data":
        warnings.append(
            warning(
                "overfitting_parameter_evidence_insufficient",
                "Parameter diagnostics are insufficient for overfitting-risk judgment.",
                source="strategy_evaluation",
            )
        )
    metrics = single_window.get("strategy_metrics") if isinstance(single_window.get("strategy_metrics"), dict) else {}
    cost_drag_pct = _number_or_none(metrics.get("cost_drag_pct"))
    if cost_drag_pct is not None and cost_drag_pct >= HIGH_COST_DRAG_PCT_THRESHOLD:
        warnings.append(
            warning(
                "overfitting_cost_sensitivity",
                f"Cost drag is {cost_drag_pct} percentage points, so gross historical results may overstate quality.",
                source="strategy_evaluation",
            )
        )
    trade = single_window.get("trade_summary") if isinstance(single_window.get("trade_summary"), dict) else {}
    trade_count = _int_value(trade.get("trade_count"))
    if trade_count < OVERFITTING_LOW_TRADE_COUNT_THRESHOLD:
        warnings.append(
            warning(
                "overfitting_low_trade_count",
                f"Trade count is {trade_count}, which is too low for robust parameter conclusions.",
                source="strategy_evaluation",
            )
        )
    walk_summary = walk_forward.get("summary") if isinstance(walk_forward.get("summary"), dict) else {}
    if walk_summary.get("result_stability") == "unstable":
        warnings.append(
            warning(
                "overfitting_walk_forward_instability",
                "Walk-forward results are unstable across sequential windows.",
                source="strategy_evaluation",
            )
        )
    return_range = _parameter_return_range(parameter_stability)
    if return_range is not None and return_range >= PARAMETER_RETURN_RANGE_THRESHOLD_PCT:
        warnings.append(
            warning(
                "overfitting_unstable_parameter_ranking",
                f"Parameter diagnostic return range is {return_range} percentage points.",
                source="strategy_evaluation",
            )
        )
    evidence.extend(
        [
            f"tested_combinations: {tested}.",
            f"sample rows: {rows}.",
            f"trade_count: {trade_count}.",
            f"cost_drag_pct: {cost_drag_pct}.",
            f"parameter_stability_status: {stability_status}.",
            f"parameter_signal_state_stability_status: {signal_state_status}.",
            f"parameter_performance_stability_status: {performance_status}.",
            f"walk_forward_result_stability: {walk_summary.get('result_stability')}.",
        ]
    )
    unique_warnings = _unique_warnings(warnings)
    return {
        "status": _overfitting_status(unique_warnings, stability_status, parameter_stability),
        "warnings": unique_warnings,
        "evidence": evidence,
        "selection_policy": "diagnostic_only_no_best_parameter_selection",
    }


def _unknown_overfitting_risk() -> dict[str, Any]:
    return {
        "status": "unknown",
        "warnings": [],
        "evidence": [],
        "selection_policy": "diagnostic_only_no_best_parameter_selection",
    }


def _overfitting_status(
    warnings: list[dict[str, Any]],
    stability_status: str,
    parameter_stability: dict[str, Any],
) -> str:
    if not warnings and parameter_stability.get("enabled") is not True:
        return "unknown"
    performance_status = _parameter_performance_status(parameter_stability)
    if performance_status == "sensitive" or stability_status == "inconsistent" or len(warnings) >= 2:
        return "elevated"
    if warnings:
        return "medium"
    return "low"


def _parameter_return_range(parameter_stability: dict[str, Any]) -> float | None:
    performance = _mapping(parameter_stability.get("performance_stability"))
    metric_ranges = _mapping(performance.get("metric_ranges"))
    return_range = _mapping(metric_ranges.get("backtest_total_return_pct"))
    value = _number_or_none(return_range.get("range"))
    if value is not None:
        return value
    summary = parameter_stability.get("summary_metrics")
    if not isinstance(summary, dict):
        return None
    minimum = _number_or_none(summary.get("backtest_total_return_pct_min"))
    maximum = _number_or_none(summary.get("backtest_total_return_pct_max"))
    if minimum is None or maximum is None:
        return None
    return round(maximum - minimum, 6)


def _base_direction(strategy_run: dict[str, Any]) -> str | None:
    assessment = strategy_run.get("assessment") if isinstance(strategy_run.get("assessment"), dict) else {}
    direction = assessment.get("direction")
    if isinstance(direction, str) and direction.strip() and direction != "unknown":
        return direction
    return None


def _parameter_signal_state_status(parameter_stability: dict[str, Any]) -> str:
    signal_state = _mapping(parameter_stability.get("signal_state_stability"))
    return str(signal_state.get("status") or parameter_stability.get("signal_state_status") or "unknown")


def _parameter_performance_status(parameter_stability: dict[str, Any]) -> str:
    performance = _mapping(parameter_stability.get("performance_stability"))
    return str(performance.get("status") or parameter_stability.get("performance_status") or "unknown")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int_value(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _empty_assessment(summary: str) -> dict[str, Any]:
    return {
        "reliability": "unknown",
        "sample_quality": "unknown",
        "cost_sensitivity": "unknown",
        "overfitting_risk": "unknown",
        "summary": summary,
        "evidence": [],
        "uncertainty": ["No strategy evaluation conclusion is available."],
    }


def _skipped_walk_forward(reason: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "skipped",
        "reason": reason,
        "summary": {},
        "windows": [],
        "warnings": [
            warning(
                "walk_forward_skipped",
                reason,
                source="strategy_evaluation",
            )
        ],
        "errors": [],
    }


def _record_warnings(
    single_window: dict[str, Any],
    walk_forward: dict[str, Any],
    parameter_stability: dict[str, Any],
    overfitting_risk: dict[str, Any],
) -> list[dict[str, Any]]:
    return _unique_warnings(
        [
            *_warning_items(single_window.get("warnings")),
            *_warning_items(walk_forward.get("warnings")),
            *_warning_items(parameter_stability.get("warnings")),
            *_warning_items(overfitting_risk.get("warnings")),
        ]
    )


def _warning_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _unique_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in warnings:
        key = (item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _record_error(single_window: dict[str, Any]) -> dict[str, Any] | None:
    if single_window.get("status") != "failed":
        return None
    errors = single_window.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        return errors[0]
    return {
        "error_type": "StrategyEvaluationFailed",
        "message": "Strategy evaluation failed without a detailed error.",
        "stage": STAGE_NAME,
    }


def _artifact_warnings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for record in records:
        for item in record.get("warnings", []):
            if not isinstance(item, dict):
                continue
            key = (item.get("code"), item.get("message"), item.get("source"))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
    return result


def _read_quant_strategy_runs(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "quant_strategy_runs.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} was not found; evaluate_quant_strategies must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict) or not isinstance(artifact.get("runs"), list):
        raise PipelineError(
            f"{QUANT_STRATEGY_RUNS_ARTIFACT} must contain a runs list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


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


def _storage_dir(config: dict[str, Any], config_path: Path) -> Path:
    ohlcv = config.get("market", {}).get("ohlcv", {})
    storage_dir = Path(str(ohlcv["storage_dir"]))
    return resolve_runtime_path(storage_dir, config_path=config_path)


def _record_zero_counts(run: RunContext) -> None:
    run.manifest["counts"]["strategy_evaluation_records"] = 0
    run.manifest["counts"]["strategy_evaluation_succeeded"] = 0
    run.manifest["counts"]["strategy_evaluation_failed"] = 0
    run.manifest["counts"]["strategy_evaluation_insufficient_data"] = 0
    run.manifest["counts"]["strategy_evaluation_skipped"] = 0
    run.manifest["counts"]["strategy_evaluation_walk_forward_records"] = 0
    run.manifest["counts"]["strategy_evaluation_parameter_stability_records"] = 0
    run.manifest["counts"]["strategy_evaluation_material_records"] = 0
    run.manifest["strategy_evaluation"] = {
        "enabled": False,
        "records": 0,
        "warnings": [],
        "errors": [],
    }


def _record_manifest_counts(run: RunContext, records: list[dict[str, Any]]) -> None:
    run.manifest["counts"]["strategy_evaluation_records"] = len(records)
    for status in ("succeeded", "failed", "insufficient_data", "skipped"):
        run.manifest["counts"][f"strategy_evaluation_{status}"] = sum(
            1 for record in records if record.get("status") == status
        )
    run.manifest["counts"]["strategy_evaluation_walk_forward_records"] = sum(
        len(_walk_forward_windows(record)) for record in records
    )
    run.manifest["counts"]["strategy_evaluation_parameter_stability_records"] = sum(
        1
        for record in records
        if isinstance(record.get("parameter_stability"), dict)
        and record["parameter_stability"].get("enabled") is True
    )


def _record_manifest_summary(
    run: RunContext,
    records: list[dict[str, Any]],
    *,
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    run.manifest["strategy_evaluation"] = {
        "enabled": True,
        "records": len(records),
        "succeeded": sum(1 for record in records if record.get("status") == "succeeded"),
        "failed": sum(1 for record in records if record.get("status") == "failed"),
        "insufficient_data": sum(1 for record in records if record.get("status") == "insufficient_data"),
        "skipped": sum(1 for record in records if record.get("status") == "skipped"),
        "coverage": {
            "quant_strategy_runs": len(records),
            "evaluation_records": len(records),
            "records_with_single_window": sum(1 for record in records if isinstance(record.get("single_window"), dict)),
            "walk_forward_windows": sum(len(_walk_forward_windows(record)) for record in records),
            "records_with_walk_forward": sum(
                1
                for record in records
                if isinstance(record.get("walk_forward"), dict)
                and record["walk_forward"].get("status") == "succeeded"
            ),
            "records_with_parameter_stability": sum(
                1
                for record in records
                if isinstance(record.get("parameter_stability"), dict)
                and record["parameter_stability"].get("enabled") is True
            ),
        },
        "source_artifacts": [QUANT_STRATEGY_RUNS_ARTIFACT, MARKET_DATA_VIEWS_ARTIFACT],
        "warnings": [_warning_summary(item) for item in warnings],
        "errors": errors,
    }


def _warning_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": item.get("code"),
        "message": item.get("message"),
        "source": item.get("source"),
    }


def _walk_forward_windows(record: dict[str, Any]) -> list[Any]:
    walk_forward = record.get("walk_forward")
    if not isinstance(walk_forward, dict):
        return []
    windows = walk_forward.get("windows")
    return windows if isinstance(windows, list) else []


def _created_at(strategy_artifact: dict[str, Any], now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc(now)
    created_at = strategy_artifact.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        return _format_utc(created_at)
    return _format_utc(None)


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
