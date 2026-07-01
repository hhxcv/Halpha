from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any


SCHEMA_VERSION = 1
STRATEGY_EFFECTIVENESS_GATES_ARTIFACT = "strategy_effectiveness_gates.json"
GATE_SOURCE = "strategy_effectiveness_gates"
GATE_STATUSES = ("effective", "watchlisted", "rejected", "insufficient_evidence")

DEFAULT_GATE_THRESHOLDS = {
    "min_succeeded_benchmarks": 2,
    "min_benchmark_success_rate_pct": 60.0,
    "min_mean_net_return_pct": 0.0,
    "min_mean_excess_return_vs_buy_and_hold_pct": 0.0,
    "min_positive_net_return_benchmark_pct": 50.0,
    "min_positive_excess_return_benchmark_pct": 50.0,
    "max_abs_drawdown_pct": 35.0,
    "max_cost_drag_pct": 1.0,
    "max_turnover": 10.0,
    "max_abs_funding_drag_pct": 1.0,
    "max_average_gross_exposure_pct": 150.0,
    "min_total_trade_count": 3,
    "min_min_sample_rows": 60,
    "min_walk_forward_succeeded_windows": 3,
    "min_walk_forward_positive_net_return_window_pct": 50.0,
    "require_walk_forward_stable": True,
    "require_parameter_stability": False,
    "elevated_overfitting_blocks_effective": True,
}


def build_strategy_effectiveness_gates(
    experiment_artifact: dict[str, Any],
    config: dict[str, Any],
    *,
    created_at: datetime | str | None = None,
    source_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    timestamp = _created_at(experiment_artifact, created_at)
    thresholds = effectiveness_gate_thresholds(config)
    candidates = _dict_list(experiment_artifact.get("candidates"))
    gate_source_artifacts = source_artifacts or ["strategy_experiment.json"]
    records = [
        _gate_record(
            candidate,
            thresholds=thresholds,
            source_artifacts=gate_source_artifacts,
        )
        for candidate in candidates
    ]
    warnings = _artifact_warnings(records)
    errors = [
        error
        for record in records
        for error in _dict_list(record.get("errors"))
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "strategy_effectiveness_gates",
        "created_at": timestamp,
        "policy": {
            "gate_statuses": list(GATE_STATUSES),
            "thresholds": thresholds,
            "single_window_profit_alone_can_be_effective": False,
            "llm_generated_gate_outcomes": False,
            "automatic_parameter_optimization": False,
            "historical_research_material": True,
        },
        "source_artifacts": gate_source_artifacts,
        "coverage": _coverage(records),
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }


def effectiveness_gate_thresholds(config: dict[str, Any]) -> dict[str, Any]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    configured = (
        quant.get("effectiveness_gates")
        if isinstance(quant.get("effectiveness_gates"), dict)
        else {}
    )
    thresholds = dict(DEFAULT_GATE_THRESHOLDS)
    thresholds.update({key: configured[key] for key in thresholds if key in configured})
    return {
        "min_succeeded_benchmarks": _positive_int(
            thresholds["min_succeeded_benchmarks"],
            "min_succeeded_benchmarks",
        ),
        "min_benchmark_success_rate_pct": _non_negative_number(
            thresholds["min_benchmark_success_rate_pct"],
            "min_benchmark_success_rate_pct",
        ),
        "min_mean_net_return_pct": _non_negative_number(
            thresholds["min_mean_net_return_pct"],
            "min_mean_net_return_pct",
        ),
        "min_mean_excess_return_vs_buy_and_hold_pct": _non_negative_number(
            thresholds["min_mean_excess_return_vs_buy_and_hold_pct"],
            "min_mean_excess_return_vs_buy_and_hold_pct",
        ),
        "min_positive_net_return_benchmark_pct": _non_negative_number(
            thresholds["min_positive_net_return_benchmark_pct"],
            "min_positive_net_return_benchmark_pct",
        ),
        "min_positive_excess_return_benchmark_pct": _non_negative_number(
            thresholds["min_positive_excess_return_benchmark_pct"],
            "min_positive_excess_return_benchmark_pct",
        ),
        "max_abs_drawdown_pct": _non_negative_number(
            thresholds["max_abs_drawdown_pct"],
            "max_abs_drawdown_pct",
        ),
        "max_cost_drag_pct": _non_negative_number(
            thresholds["max_cost_drag_pct"],
            "max_cost_drag_pct",
        ),
        "max_turnover": _non_negative_number(
            thresholds["max_turnover"],
            "max_turnover",
        ),
        "max_abs_funding_drag_pct": _non_negative_number(
            thresholds["max_abs_funding_drag_pct"],
            "max_abs_funding_drag_pct",
        ),
        "max_average_gross_exposure_pct": _non_negative_number(
            thresholds["max_average_gross_exposure_pct"],
            "max_average_gross_exposure_pct",
        ),
        "min_total_trade_count": _positive_int(
            thresholds["min_total_trade_count"],
            "min_total_trade_count",
        ),
        "min_min_sample_rows": _positive_int(
            thresholds["min_min_sample_rows"],
            "min_min_sample_rows",
        ),
        "min_walk_forward_succeeded_windows": _positive_int(
            thresholds["min_walk_forward_succeeded_windows"],
            "min_walk_forward_succeeded_windows",
        ),
        "min_walk_forward_positive_net_return_window_pct": _non_negative_number(
            thresholds["min_walk_forward_positive_net_return_window_pct"],
            "min_walk_forward_positive_net_return_window_pct",
        ),
        "require_walk_forward_stable": _bool_value(
            thresholds["require_walk_forward_stable"],
            "require_walk_forward_stable",
        ),
        "require_parameter_stability": _bool_value(
            thresholds["require_parameter_stability"],
            "require_parameter_stability",
        ),
        "elevated_overfitting_blocks_effective": _bool_value(
            thresholds["elevated_overfitting_blocks_effective"],
            "elevated_overfitting_blocks_effective",
        ),
    }


def _gate_record(
    candidate: dict[str, Any],
    *,
    thresholds: dict[str, Any],
    source_artifacts: list[str],
) -> dict[str, Any]:
    inputs = _gate_inputs(candidate, thresholds=thresholds)
    reasons = _gate_reasons(inputs, thresholds=thresholds)
    status = _gate_status(reasons)
    warnings = [
        _warning(str(reason["code"]), str(reason["message"]))
        for reason in reasons
        if reason.get("severity") in {"block", "downgrade", "reject"}
    ]
    errors = [
        error
        for evaluation in _dict_list(candidate.get("evaluations"))
        for error in _dict_list(evaluation.get("errors"))
    ]
    return {
        "gate_id": f"strategy_effectiveness_gate:{candidate.get('strategy_name')}",
        "strategy_name": candidate.get("strategy_name"),
        "params": candidate.get("params") if isinstance(candidate.get("params"), dict) else {},
        "status": status,
        "gate_inputs": inputs,
        "reasons": reasons,
        "warnings": _unique_items(warnings),
        "errors": errors,
        "source_artifacts": source_artifacts,
    }


def _gate_inputs(candidate: dict[str, Any], *, thresholds: dict[str, Any]) -> dict[str, Any]:
    evaluations = _dict_list(candidate.get("evaluations"))
    succeeded = [item for item in evaluations if item.get("status") == "succeeded"]
    net_returns = _metric_values(succeeded, "strategy", "net_return_pct")
    excess_returns = _metric_values(succeeded, "relative", "excess_return_vs_buy_and_hold_pct")
    cost_drags = _metric_values(succeeded, "strategy", "cost_drag_pct")
    drawdowns = _metric_values(succeeded, "strategy", "max_drawdown_pct")
    trade_counts = _metric_values(succeeded, "trade", "trade_count")
    sample_rows = _sample_rows(succeeded)
    benchmark_records = len(evaluations)
    benchmark_succeeded = len(succeeded)
    benchmark_success_rate = _pct(benchmark_succeeded / benchmark_records) if benchmark_records else None
    advanced = _advanced_gate_inputs(candidate, evaluations=succeeded)
    inputs = {
        "candidate_status": candidate.get("status"),
        "benchmark_coverage": {
            "benchmark_records": benchmark_records,
            "succeeded": benchmark_succeeded,
            "insufficient_data": sum(1 for item in evaluations if item.get("status") == "insufficient_data"),
            "failed": sum(1 for item in evaluations if item.get("status") == "failed"),
            "skipped": sum(1 for item in evaluations if item.get("status") == "skipped"),
            "success_rate_pct": benchmark_success_rate,
        },
        "net_performance": {
            "mean_net_return_pct": _rounded_mean(net_returns),
            "positive_net_return_benchmark_pct": _positive_pct(net_returns),
        },
        "baseline_comparison": {
            "mean_excess_return_vs_buy_and_hold_pct": _rounded_mean(excess_returns),
            "positive_excess_return_benchmark_pct": _positive_pct(excess_returns),
        },
        "cost_drag": {
            "mean_cost_drag_pct": _rounded_mean(cost_drags),
            "max_cost_drag_pct": max(cost_drags) if cost_drags else None,
        },
        "drawdown": {
            "worst_abs_drawdown_pct": max(abs(item) for item in drawdowns) if drawdowns else None,
        },
        "trade_count": {
            "total_trade_count": int(sum(trade_counts)) if trade_counts else 0,
            "min_trade_count": int(min(trade_counts)) if trade_counts else 0,
        },
        "sample_quality": {
            "min_sample_rows": min(sample_rows) if sample_rows else 0,
            "max_sample_rows": max(sample_rows) if sample_rows else 0,
        },
        "walk_forward_stability": _walk_forward_inputs(succeeded),
        "parameter_stability": _parameter_stability(candidate),
        "position_model": advanced["position_model"],
        "futures_risk": advanced["futures_risk"],
        "multi_leg_quality": advanced["multi_leg_quality"],
        "feature_availability": advanced["feature_availability"],
        "optimization_robustness": advanced["optimization_robustness"],
    }
    inputs["overfitting_risk"] = _overfitting_risk(inputs, candidate, thresholds=thresholds)
    return inputs


def _gate_reasons(inputs: dict[str, Any], *, thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    coverage = _mapping(inputs.get("benchmark_coverage"))
    benchmark_succeeded = int(coverage.get("succeeded") or 0)
    success_rate = _number_or_none(coverage.get("success_rate_pct"))
    if benchmark_succeeded < thresholds["min_succeeded_benchmarks"]:
        _add_reason(
            reasons,
            "insufficient_benchmark_coverage",
            "block",
            "Candidate does not have enough succeeded benchmark evaluations.",
            benchmark_succeeded,
            thresholds["min_succeeded_benchmarks"],
        )
    else:
        _add_reason(
            reasons,
            "benchmark_coverage_met",
            "pass",
            "Candidate has enough succeeded benchmark evaluations.",
            benchmark_succeeded,
            thresholds["min_succeeded_benchmarks"],
        )
    if success_rate is None or success_rate < thresholds["min_benchmark_success_rate_pct"]:
        _add_reason(
            reasons,
            "low_benchmark_success_rate",
            "block",
            "Candidate benchmark success rate is below the gate threshold.",
            success_rate,
            thresholds["min_benchmark_success_rate_pct"],
        )

    sample = _mapping(inputs.get("sample_quality"))
    min_sample_rows = int(sample.get("min_sample_rows") or 0)
    if min_sample_rows < thresholds["min_min_sample_rows"]:
        _add_reason(
            reasons,
            "insufficient_sample_quality",
            "block",
            "Candidate has at least one succeeded benchmark with too few sample rows.",
            min_sample_rows,
            thresholds["min_min_sample_rows"],
        )

    trade = _mapping(inputs.get("trade_count"))
    total_trade_count = int(trade.get("total_trade_count") or 0)
    if total_trade_count < thresholds["min_total_trade_count"]:
        _add_reason(
            reasons,
            "low_trade_count",
            "block",
            "Candidate trade count is too low for effectiveness evidence.",
            total_trade_count,
            thresholds["min_total_trade_count"],
        )

    performance = _mapping(inputs.get("net_performance"))
    mean_net = _number_or_none(performance.get("mean_net_return_pct"))
    if mean_net is None or mean_net < thresholds["min_mean_net_return_pct"]:
        _add_reason(
            reasons,
            "weak_net_performance",
            "reject",
            "Candidate mean net return is below the gate threshold.",
            mean_net,
            thresholds["min_mean_net_return_pct"],
        )

    baseline = _mapping(inputs.get("baseline_comparison"))
    mean_excess = _number_or_none(baseline.get("mean_excess_return_vs_buy_and_hold_pct"))
    if mean_excess is None or mean_excess < thresholds["min_mean_excess_return_vs_buy_and_hold_pct"]:
        _add_reason(
            reasons,
            "weak_baseline_comparison",
            "reject",
            "Candidate mean excess return versus buy and hold is below the gate threshold.",
            mean_excess,
            thresholds["min_mean_excess_return_vs_buy_and_hold_pct"],
        )

    positive_net = _number_or_none(performance.get("positive_net_return_benchmark_pct"))
    if positive_net is None or positive_net < thresholds["min_positive_net_return_benchmark_pct"]:
        _add_reason(
            reasons,
            "low_positive_net_return_coverage",
            "downgrade",
            "Candidate positive net-return benchmark coverage is below the gate threshold.",
            positive_net,
            thresholds["min_positive_net_return_benchmark_pct"],
        )

    positive_excess = _number_or_none(baseline.get("positive_excess_return_benchmark_pct"))
    if positive_excess is None or positive_excess < thresholds["min_positive_excess_return_benchmark_pct"]:
        _add_reason(
            reasons,
            "low_positive_excess_return_coverage",
            "downgrade",
            "Candidate positive excess-return benchmark coverage is below the gate threshold.",
            positive_excess,
            thresholds["min_positive_excess_return_benchmark_pct"],
        )

    drawdown = _mapping(inputs.get("drawdown"))
    worst_abs_drawdown = _number_or_none(drawdown.get("worst_abs_drawdown_pct"))
    if worst_abs_drawdown is None or worst_abs_drawdown > thresholds["max_abs_drawdown_pct"]:
        _add_reason(
            reasons,
            "excessive_drawdown",
            "reject",
            "Candidate drawdown exceeds the gate threshold.",
            worst_abs_drawdown,
            thresholds["max_abs_drawdown_pct"],
        )

    cost = _mapping(inputs.get("cost_drag"))
    max_cost_drag = _number_or_none(cost.get("max_cost_drag_pct"))
    if max_cost_drag is not None and max_cost_drag > thresholds["max_cost_drag_pct"]:
        _add_reason(
            reasons,
            "excessive_cost_drag",
            "downgrade",
            "Candidate cost drag is high enough to block effective status.",
            max_cost_drag,
            thresholds["max_cost_drag_pct"],
        )

    walk_forward = _mapping(inputs.get("walk_forward_stability"))
    wf_windows = int(walk_forward.get("succeeded_windows") or 0)
    if wf_windows < thresholds["min_walk_forward_succeeded_windows"]:
        _add_reason(
            reasons,
            "insufficient_walk_forward_evidence",
            "block",
            "Candidate lacks enough succeeded walk-forward windows.",
            wf_windows,
            thresholds["min_walk_forward_succeeded_windows"],
        )
    wf_stability = str(walk_forward.get("result_stability") or "unknown")
    if thresholds["require_walk_forward_stable"] and wf_stability != "stable":
        _add_reason(
            reasons,
            "unstable_walk_forward",
            "downgrade",
            "Candidate walk-forward evidence is not stable.",
            wf_stability,
            "stable",
        )
    wf_positive = _number_or_none(walk_forward.get("min_positive_net_return_window_pct"))
    if wf_positive is None or wf_positive < thresholds["min_walk_forward_positive_net_return_window_pct"]:
        _add_reason(
            reasons,
            "weak_walk_forward_positive_coverage",
            "downgrade",
            "Candidate walk-forward positive-return coverage is below the gate threshold.",
            wf_positive,
            thresholds["min_walk_forward_positive_net_return_window_pct"],
        )

    parameter = _mapping(inputs.get("parameter_stability"))
    parameter_status = str(parameter.get("status") or "unknown")
    if thresholds["require_parameter_stability"] and parameter_status != "stable":
        severity = "block" if parameter_status in {"disabled", "unavailable", "insufficient_data"} else "downgrade"
        _add_reason(
            reasons,
            "parameter_stability_not_stable",
            severity,
            "Candidate parameter performance-stability evidence is not stable.",
            parameter_status,
            "stable",
        )
    elif parameter_status in {"fragile", "inconsistent"}:
        _add_reason(
            reasons,
            "parameter_stability_not_stable",
            "downgrade",
            "Candidate parameter performance-stability evidence is not stable.",
            parameter_status,
            "stable",
        )
    elif parameter_status in {"disabled", "unavailable"}:
        _add_reason(
            reasons,
            "parameter_stability_unavailable",
            "info",
            "Parameter-stability evidence is unavailable and is not required by current thresholds.",
            parameter_status,
            "stable",
        )

    overfitting = _mapping(inputs.get("overfitting_risk"))
    overfitting_status = str(overfitting.get("status") or "unknown")
    if (
        thresholds["elevated_overfitting_blocks_effective"]
        and overfitting_status in {"medium", "elevated"}
    ):
        _add_reason(
            reasons,
            "elevated_overfitting_risk",
            "downgrade",
            "Candidate overfitting risk is high enough to block effective status.",
            overfitting_status,
            "low",
        )

    _add_advanced_reasons(reasons, inputs, thresholds=thresholds)
    return reasons


def _add_advanced_reasons(
    reasons: list[dict[str, Any]],
    inputs: dict[str, Any],
    *,
    thresholds: dict[str, Any],
) -> None:
    futures = _mapping(inputs.get("futures_risk"))
    if int(futures.get("records_with_futures_diagnostics") or 0):
        funding_statuses = _mapping(futures.get("funding_status_counts"))
        missing_funding_statuses = {
            "degraded",
            "failed",
            "insufficient_data",
            "not_provided",
            "partial",
            "stale",
            "unavailable",
        }
        if any(int(funding_statuses.get(status) or 0) for status in missing_funding_statuses):
            _add_reason(
                reasons,
                "missing_funding_evidence",
                "downgrade",
                "Futures evaluation has missing or degraded funding evidence.",
                funding_statuses,
                "available",
            )
        max_funding_drag = _number_or_none(futures.get("max_abs_funding_drag_pct"))
        if max_funding_drag is not None and max_funding_drag > thresholds["max_abs_funding_drag_pct"]:
            _add_reason(
                reasons,
                "excessive_funding_drag",
                "downgrade",
                "Futures funding drag is high enough to block effective status.",
                max_funding_drag,
                thresholds["max_abs_funding_drag_pct"],
            )
        max_gross_exposure = _number_or_none(futures.get("max_average_gross_exposure_pct"))
        if max_gross_exposure is not None and max_gross_exposure > thresholds["max_average_gross_exposure_pct"]:
            _add_reason(
                reasons,
                "excessive_gross_exposure",
                "downgrade",
                "Futures average gross exposure exceeds the gate threshold.",
                max_gross_exposure,
                thresholds["max_average_gross_exposure_pct"],
            )
        max_turnover = _number_or_none(futures.get("max_turnover"))
        if max_turnover is not None and max_turnover > thresholds["max_turnover"]:
            _add_reason(
                reasons,
                "high_advanced_turnover",
                "downgrade",
                "Advanced strategy turnover exceeds the gate threshold.",
                max_turnover,
                thresholds["max_turnover"],
            )
        short_time = _number_or_none(futures.get("max_short_time_pct"))
        short_contribution = _number_or_none(futures.get("min_short_gross_contribution_pct"))
        if short_time is not None and short_time > 0 and short_contribution is not None and short_contribution < 0:
            _add_reason(
                reasons,
                "weak_short_side_contribution",
                "downgrade",
                "Short-side exposure contributed negative gross return in futures diagnostics.",
                short_contribution,
                0.0,
            )

    multi_leg = _mapping(inputs.get("multi_leg_quality"))
    if int(multi_leg.get("records_with_multi_leg_evaluation") or 0):
        alignment_statuses = _mapping(multi_leg.get("alignment_status_counts"))
        failed_alignment = any(
            int(alignment_statuses.get(status) or 0)
            for status in ("failed", "insufficient_data", "not_aligned")
        )
        degraded_alignment = any(
            int(alignment_statuses.get(status) or 0)
            for status in ("degraded", "partial")
        )
        if failed_alignment:
            _add_reason(
                reasons,
                "misaligned_multi_leg_evidence",
                "block",
                "Multi-leg evaluation does not have enough aligned leg evidence.",
                alignment_statuses,
                "aligned",
            )
        elif degraded_alignment or int(multi_leg.get("max_alignment_omitted_rows") or 0) > 0:
            _add_reason(
                reasons,
                "degraded_multi_leg_alignment",
                "downgrade",
                "Multi-leg evaluation omitted rows during leg alignment.",
                multi_leg.get("max_alignment_omitted_rows"),
                0,
            )
        max_multi_leg_turnover = _number_or_none(multi_leg.get("max_turnover"))
        if max_multi_leg_turnover is not None and max_multi_leg_turnover > thresholds["max_turnover"]:
            _add_reason(
                reasons,
                "high_advanced_turnover",
                "downgrade",
                "Advanced strategy turnover exceeds the gate threshold.",
                max_multi_leg_turnover,
                thresholds["max_turnover"],
            )
        max_multi_leg_gross = _number_or_none(multi_leg.get("max_average_gross_exposure_pct"))
        if max_multi_leg_gross is not None and max_multi_leg_gross > thresholds["max_average_gross_exposure_pct"]:
            _add_reason(
                reasons,
                "excessive_gross_exposure",
                "downgrade",
                "Multi-leg average gross exposure exceeds the gate threshold.",
                max_multi_leg_gross,
                thresholds["max_average_gross_exposure_pct"],
            )

    feature = _mapping(inputs.get("feature_availability"))
    if int(feature.get("records_with_feature_availability") or 0):
        status_counts = _mapping(feature.get("status_counts"))
        insufficient_statuses = {"failed", "insufficient_data", "unavailable"}
        degraded_statuses = {"degraded", "partial", "skipped", "stale"}
        if any(int(status_counts.get(status) or 0) for status in insufficient_statuses):
            _add_reason(
                reasons,
                "event_feature_insufficient_evidence",
                "block",
                "Event or feature input evidence is unavailable or insufficient.",
                status_counts,
                "succeeded",
            )
        elif any(int(status_counts.get(status) or 0) for status in degraded_statuses):
            _add_reason(
                reasons,
                "event_feature_coverage_gap",
                "downgrade",
                "Event or feature input evidence is partial, stale, or degraded.",
                status_counts,
                "succeeded",
            )

    optimization = _mapping(inputs.get("optimization_robustness"))
    optimization_status = str(optimization.get("status") or "not_available")
    if optimization_status in {"failed", "insufficient_data"}:
        _add_reason(
            reasons,
            "optimization_robustness_insufficient",
            "block",
            "Optimization robustness evidence is unavailable or failed.",
            optimization_status,
            "robust",
        )
    elif optimization_status in {"fragile", "overfit_risk"}:
        _add_reason(
            reasons,
            "optimization_robustness_not_robust",
            "downgrade",
            "Optimization walk-forward robustness is not robust.",
            optimization_status,
            "robust",
        )


def _gate_status(reasons: list[dict[str, Any]]) -> str:
    severities = {str(item.get("severity")) for item in reasons}
    if "block" in severities:
        return "insufficient_evidence"
    if "reject" in severities:
        return "rejected"
    if "downgrade" in severities:
        return "watchlisted"
    return "effective"


def _advanced_gate_inputs(candidate: dict[str, Any], *, evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    single_windows = [
        _mapping(evaluation.get("single_window"))
        for evaluation in evaluations
        if isinstance(evaluation.get("single_window"), dict)
    ]
    multi_leg_records = _multi_leg_records(candidate, evaluations)
    futures_records = [
        _mapping(record.get("futures_diagnostics"))
        for record in single_windows
        if isinstance(record.get("futures_diagnostics"), dict)
    ]
    execution_model_ids = _execution_model_ids(single_windows, multi_leg_records)
    feature_records = _feature_availability_records(candidate, evaluations, single_windows, multi_leg_records)
    return {
        "position_model": {
            "signed_single_leg": _has_signed_single_leg(single_windows),
            "multi_leg": bool(multi_leg_records),
            "execution_model_ids": execution_model_ids,
        },
        "futures_risk": _futures_risk_inputs(futures_records),
        "multi_leg_quality": _multi_leg_quality_inputs(multi_leg_records),
        "feature_availability": _feature_availability_inputs(feature_records),
        "optimization_robustness": _optimization_robustness(candidate),
    }


def _execution_model_ids(single_windows: list[dict[str, Any]], multi_leg_records: list[dict[str, Any]]) -> list[str]:
    values = []
    for record in [*single_windows, *multi_leg_records]:
        model = _mapping(record.get("execution_model"))
        model_id = model.get("execution_model_id")
        if isinstance(model_id, str) and model_id:
            values.append(model_id)
    return sorted(set(values))


def _has_signed_single_leg(single_windows: list[dict[str, Any]]) -> bool:
    for record in single_windows:
        model = _mapping(record.get("execution_model"))
        model_id = str(model.get("execution_model_id") or "")
        trade = _mapping(record.get("trade_summary"))
        diagnostics = _mapping(record.get("futures_diagnostics"))
        exposure = _mapping(diagnostics.get("exposure"))
        if "signed" in model_id:
            return True
        if any(key in trade for key in ("long_trade_count", "short_trade_count", "side_flip_count")):
            return True
        if _number_or_none(exposure.get("short_time_pct")) is not None:
            return True
    return False


def _futures_risk_inputs(records: list[dict[str, Any]]) -> dict[str, Any]:
    funding_records = [_mapping(record.get("funding")) for record in records if isinstance(record.get("funding"), dict)]
    exposure_records = [_mapping(record.get("exposure")) for record in records if isinstance(record.get("exposure"), dict)]
    contribution_records = [
        _mapping(record.get("contribution"))
        for record in records
        if isinstance(record.get("contribution"), dict)
    ]
    turnover_records = [_mapping(record.get("turnover")) for record in records if isinstance(record.get("turnover"), dict)]
    funding_drags = [
        value
        for value in (_number_or_none(record.get("funding_drag_pct")) for record in funding_records)
        if value is not None
    ]
    return {
        "records_with_futures_diagnostics": len(records),
        "status_counts": _status_counts(records),
        "funding_status_counts": _status_counts(funding_records),
        "max_average_gross_exposure_pct": _max_number(
            _number_or_none(record.get("average_gross_exposure_pct")) for record in exposure_records
        ),
        "max_short_time_pct": _max_number(
            _number_or_none(record.get("short_time_pct")) for record in exposure_records
        ),
        "min_short_gross_contribution_pct": _min_number(
            _number_or_none(record.get("short_gross_contribution_pct")) for record in contribution_records
        ),
        "max_abs_funding_drag_pct": max((abs(value) for value in funding_drags), default=None),
        "max_turnover": _max_number(_number_or_none(record.get("total_turnover")) for record in turnover_records),
        "warning_codes": _warning_codes(records),
    }


def _multi_leg_records(candidate: dict[str, Any], evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for value in [
        candidate.get("multi_leg_evaluation"),
        candidate.get("multi_leg"),
        *_multi_leg_values(evaluations),
    ]:
        if isinstance(value, dict):
            if value.get("record_type") == "multi_leg_backtest" or "alignment" in value or "leg_summaries" in value:
                records.append(value)
        elif isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    return records


def _multi_leg_values(evaluations: list[dict[str, Any]]) -> list[Any]:
    values = []
    for evaluation in evaluations:
        values.extend(
            [
                evaluation.get("multi_leg_evaluation"),
                evaluation.get("multi_leg"),
            ]
        )
        if evaluation.get("record_type") == "multi_leg_backtest":
            values.append(evaluation)
    return values


def _multi_leg_quality_inputs(records: list[dict[str, Any]]) -> dict[str, Any]:
    alignments = [_mapping(record.get("alignment")) for record in records if isinstance(record.get("alignment"), dict)]
    metrics = [
        _mapping(record.get("strategy_metrics"))
        for record in records
        if isinstance(record.get("strategy_metrics"), dict)
    ]
    return {
        "records_with_multi_leg_evaluation": len(records),
        "status_counts": _status_counts(records),
        "alignment_status_counts": _status_counts(alignments),
        "max_alignment_omitted_rows": max((_alignment_omitted_rows(item) for item in alignments), default=0),
        "max_average_gross_exposure_pct": _max_number(
            _exposure_as_pct(_number_or_none(item.get("average_gross_exposure"))) for item in metrics
        ),
        "max_abs_average_net_exposure_pct": _max_number(
            abs(value)
            for value in (
                _exposure_as_pct(_number_or_none(item.get("average_net_exposure"))) for item in metrics
            )
            if value is not None
        ),
        "max_turnover": _max_number(_number_or_none(item.get("turnover")) for item in metrics),
        "warning_codes": _warning_codes(records),
    }


def _alignment_omitted_rows(alignment: dict[str, Any]) -> int:
    omitted = alignment.get("omitted_rows")
    if isinstance(omitted, list):
        return sum(int(item.get("omitted_rows") or 0) for item in omitted if isinstance(item, dict))
    return 0


def _feature_availability_records(
    candidate: dict[str, Any],
    evaluations: list[dict[str, Any]],
    single_windows: list[dict[str, Any]],
    multi_leg_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records = []
    for owner in [candidate, *evaluations, *single_windows, *multi_leg_records]:
        for key in (
            "feature_availability",
            "event_feature_availability",
            "event_feature_input",
            "event_features",
            "feature_inputs",
            "strategy_event_features",
        ):
            records.extend(_feature_records_from(owner.get(key)))
    return records


def _feature_records_from(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [record for item in value for record in _feature_records_from(item)]
    if not isinstance(value, dict):
        return []
    records = []
    if any(key in value for key in ("status", "coverage_status", "availability_status", "query_status")):
        records.append(value)
    for key in ("records", "features", "inputs", "sources"):
        records.extend(_feature_records_from(value.get(key)))
    return records


def _feature_availability_inputs(records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [{"status": _feature_status(record)} for record in records]
    return {
        "records_with_feature_availability": len(records),
        "status_counts": _status_counts(normalized),
        "warning_codes": _warning_codes(records),
    }


def _feature_status(record: dict[str, Any]) -> str:
    for key in ("status", "coverage_status", "availability_status", "query_status"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _optimization_robustness(candidate: dict[str, Any]) -> dict[str, Any]:
    for value in (
        candidate.get("optimization_robustness"),
        candidate.get("robustness"),
        candidate.get("strategy_optimization"),
        candidate.get("optimization"),
    ):
        if not isinstance(value, dict):
            continue
        robustness = _mapping(value.get("robustness")) or value
        status = robustness.get("status")
        if isinstance(status, str) and status:
            return {
                "status": status,
                "warnings": _dict_list(robustness.get("warnings")),
                "errors": _dict_list(robustness.get("errors")),
                "summary": _mapping(robustness.get("summary")),
            }
    return {
        "status": "not_available",
        "warnings": [],
        "errors": [],
        "summary": {},
    }


def _walk_forward_inputs(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    walk_records = [
        _mapping(item.get("walk_forward"))
        for item in evaluations
        if isinstance(item.get("walk_forward"), dict)
    ]
    succeeded = [item for item in walk_records if item.get("status") == "succeeded"]
    summaries = [_mapping(item.get("summary")) for item in succeeded]
    succeeded_windows = [
        int(item.get("succeeded_windows") or 0)
        for item in summaries
    ]
    positive_window_pcts = [
        value
        for value in (_number_or_none(item.get("positive_net_return_window_pct")) for item in summaries)
        if value is not None
    ]
    mean_net_returns = [
        value
        for value in (_number_or_none(item.get("mean_net_return_pct")) for item in summaries)
        if value is not None
    ]
    stability_values = [
        str(item.get("result_stability"))
        for item in summaries
        if item.get("result_stability") is not None
    ]
    return {
        "records_with_walk_forward": len(succeeded),
        "succeeded_windows": int(sum(succeeded_windows)),
        "mean_net_return_pct": _rounded_mean(mean_net_returns),
        "min_positive_net_return_window_pct": min(positive_window_pcts) if positive_window_pcts else None,
        "result_stability": _aggregate_stability(stability_values, succeeded_windows),
        "status_counts": _status_counts(walk_records),
    }


def _aggregate_stability(stability_values: list[str], succeeded_windows: list[int]) -> str:
    if not stability_values or sum(succeeded_windows) <= 0:
        return "insufficient"
    if any(value == "unstable" for value in stability_values):
        return "unstable"
    if all(value == "stable" for value in stability_values):
        return "stable"
    return "mixed"


def _parameter_stability(candidate: dict[str, Any]) -> dict[str, Any]:
    value = candidate.get("parameter_stability")
    if isinstance(value, dict):
        signal_state = _mapping(value.get("signal_state_stability"))
        performance = _mapping(value.get("performance_stability"))
        return {
            "enabled": value.get("enabled") is True,
            "status": _parameter_performance_gate_status(value),
            "signal_state_status": signal_state.get("status") or value.get("signal_state_status"),
            "performance_status": performance.get("status") or value.get("performance_status"),
            "signal_state_stability": signal_state,
            "performance_stability": performance,
            "tested_combinations": value.get("tested_combinations"),
            "valid_combinations": value.get("valid_combinations"),
            "warnings": _dict_list(value.get("warnings")),
        }
    return {
        "enabled": False,
        "status": "unavailable",
        "warnings": [],
    }


def _parameter_performance_gate_status(value: dict[str, Any]) -> str:
    performance_status = _parameter_performance_status(value)
    if performance_status == "stable":
        return "stable"
    if performance_status in {"partially_stable", "sensitive"}:
        return "fragile"
    if performance_status in {"insufficient_evidence", "no_valid_combinations"}:
        return "insufficient_data"
    return str(value.get("status") or "unknown")


def _parameter_performance_status(value: dict[str, Any]) -> str:
    performance = _mapping(value.get("performance_stability"))
    return str(performance.get("status") or value.get("performance_status") or "")


def _overfitting_risk(
    inputs: dict[str, Any],
    candidate: dict[str, Any],
    *,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    configured = candidate.get("overfitting_risk")
    if isinstance(configured, dict):
        return {
            "status": configured.get("status", "unknown"),
            "warnings": _dict_list(configured.get("warnings")),
            "evidence": _string_list(configured.get("evidence")),
        }

    warnings = []
    evidence = []
    sample = _mapping(inputs.get("sample_quality"))
    trade = _mapping(inputs.get("trade_count"))
    cost = _mapping(inputs.get("cost_drag"))
    walk_forward = _mapping(inputs.get("walk_forward_stability"))
    parameter = _mapping(inputs.get("parameter_stability"))

    min_sample_rows = int(sample.get("min_sample_rows") or 0)
    total_trade_count = int(trade.get("total_trade_count") or 0)
    max_cost_drag = _number_or_none(cost.get("max_cost_drag_pct"))
    walk_forward_stability = str(walk_forward.get("result_stability") or "unknown")
    parameter_status = str(parameter.get("status") or "unknown")
    parameter_performance_status = str(parameter.get("performance_status") or "unknown")

    if min_sample_rows and min_sample_rows < thresholds["min_min_sample_rows"]:
        warnings.append(_warning("overfitting_short_sample", "Sample length is short for robust gate evidence."))
    if total_trade_count < thresholds["min_total_trade_count"]:
        warnings.append(_warning("overfitting_low_trade_count", "Trade count is too low for robust gate evidence."))
    if max_cost_drag is not None and max_cost_drag > thresholds["max_cost_drag_pct"]:
        warnings.append(_warning("overfitting_cost_sensitivity", "Cost drag may dominate historical results."))
    if thresholds["require_walk_forward_stable"] and walk_forward_stability == "unstable":
        warnings.append(_warning("overfitting_walk_forward_instability", "Walk-forward results are unstable."))
    if parameter_status in {"fragile", "inconsistent"}:
        warnings.append(_warning("overfitting_parameter_instability", "Parameter performance stability is weak."))

    evidence.extend(
        [
            f"min_sample_rows: {min_sample_rows}.",
            f"total_trade_count: {total_trade_count}.",
            f"max_cost_drag_pct: {max_cost_drag}.",
            f"walk_forward_result_stability: {walk_forward_stability}.",
            f"parameter_stability_status: {parameter_status}.",
            f"parameter_performance_stability_status: {parameter_performance_status}.",
        ]
    )
    unique_warnings = _unique_items(warnings)
    return {
        "status": _overfitting_status(unique_warnings),
        "warnings": unique_warnings,
        "evidence": evidence,
    }


def _overfitting_status(warnings: list[dict[str, Any]]) -> str:
    codes = {item.get("code") for item in warnings}
    if "overfitting_walk_forward_instability" in codes or "overfitting_low_trade_count" in codes:
        return "elevated"
    if len(warnings) >= 2:
        return "elevated"
    if warnings:
        return "medium"
    return "low"


def _coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "strategy_candidates": len(records),
        "effective": sum(1 for item in records if item.get("status") == "effective"),
        "watchlisted": sum(1 for item in records if item.get("status") == "watchlisted"),
        "rejected": sum(1 for item in records if item.get("status") == "rejected"),
        "insufficient_evidence": sum(1 for item in records if item.get("status") == "insufficient_evidence"),
    }


def _artifact_warnings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _unique_items(
        warning
        for record in records
        for warning in _dict_list(record.get("warnings"))
    )


def _metric_values(evaluations: list[dict[str, Any]], section: str, key: str) -> list[float]:
    values = []
    for evaluation in evaluations:
        metrics = _mapping(evaluation.get("metrics"))
        section_values = _mapping(metrics.get(section))
        value = _number_or_none(section_values.get(key))
        if value is not None:
            values.append(value)
    return values


def _sample_rows(evaluations: list[dict[str, Any]]) -> list[int]:
    rows = []
    for evaluation in evaluations:
        single_window = _mapping(evaluation.get("single_window"))
        sample = _mapping(single_window.get("sample"))
        value = sample.get("rows")
        if isinstance(value, int) and not isinstance(value, bool):
            rows.append(value)
    return rows


def _max_number(values: Any) -> float | None:
    numbers = [value for value in values if value is not None]
    return max(numbers) if numbers else None


def _min_number(values: Any) -> float | None:
    numbers = [value for value in values if value is not None]
    return min(numbers) if numbers else None


def _exposure_as_pct(value: float | None) -> float | None:
    if value is None:
        return None
    if abs(value) <= 2.0:
        return round(value * 100, 6)
    return value


def _warning_codes(records: list[dict[str, Any]]) -> list[str]:
    codes = []
    for record in records:
        for key in ("warnings", "risk_warnings"):
            for item in _dict_list(record.get(key)):
                code = item.get("code")
                if isinstance(code, str) and code:
                    codes.append(code)
    return sorted(set(codes))


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _add_reason(
    reasons: list[dict[str, Any]],
    code: str,
    severity: str,
    message: str,
    value: Any,
    threshold: Any,
) -> None:
    reasons.append(
        {
            "code": code,
            "severity": severity,
            "message": message,
            "value": value,
            "threshold": threshold,
        }
    )


def _warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "source": GATE_SOURCE,
    }


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unique_items(items: Any) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        key = (item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"quant.effectiveness_gates.{path} must be a positive integer.")
    return value


def _non_negative_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
        raise ValueError(f"quant.effectiveness_gates.{path} must be a non-negative number.")
    return float(value)


def _bool_value(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"quant.effectiveness_gates.{path} must be a boolean.")
    return value


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _rounded_mean(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _positive_pct(values: list[float]) -> float | None:
    if not values:
        return None
    return _pct(sum(1 for value in values if value > 0) / len(values))


def _pct(value: float) -> float:
    return round(float(value) * 100, 6)


def _created_at(experiment_artifact: dict[str, Any], value: datetime | str | None) -> str:
    if value is None:
        candidate = experiment_artifact.get("created_at")
        if isinstance(candidate, str) and candidate.strip():
            value = candidate
        else:
            value = datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("strategy gate created_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("strategy gate created_at must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("strategy gate created_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")
