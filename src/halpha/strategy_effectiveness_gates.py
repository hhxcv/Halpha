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
) -> dict[str, Any]:
    timestamp = _created_at(experiment_artifact, created_at)
    thresholds = effectiveness_gate_thresholds(config)
    candidates = _dict_list(experiment_artifact.get("candidates"))
    records = [_gate_record(candidate, thresholds=thresholds) for candidate in candidates]
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
        "source_artifacts": ["strategy_experiment.json"],
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


def _gate_record(candidate: dict[str, Any], *, thresholds: dict[str, Any]) -> dict[str, Any]:
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
        "source_artifacts": ["strategy_experiment.json"],
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
            "Candidate parameter-stability evidence is not stable.",
            parameter_status,
            "stable",
        )
    elif parameter_status in {"fragile", "inconsistent"}:
        _add_reason(
            reasons,
            "parameter_stability_not_stable",
            "downgrade",
            "Candidate parameter-stability evidence is not stable.",
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

    return reasons


def _gate_status(reasons: list[dict[str, Any]]) -> str:
    severities = {str(item.get("severity")) for item in reasons}
    if "block" in severities:
        return "insufficient_evidence"
    if "reject" in severities:
        return "rejected"
    if "downgrade" in severities:
        return "watchlisted"
    return "effective"


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
        return {
            "enabled": value.get("enabled") is True,
            "status": value.get("status", "unknown"),
            "tested_combinations": value.get("tested_combinations"),
            "valid_combinations": value.get("valid_combinations"),
            "warnings": _dict_list(value.get("warnings")),
        }
    return {
        "enabled": False,
        "status": "unavailable",
        "warnings": [],
    }


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

    if min_sample_rows and min_sample_rows < thresholds["min_min_sample_rows"] * 2:
        warnings.append(_warning("overfitting_short_sample", "Sample length is short for robust gate evidence."))
    if total_trade_count < thresholds["min_total_trade_count"]:
        warnings.append(_warning("overfitting_low_trade_count", "Trade count is too low for robust gate evidence."))
    if max_cost_drag is not None and max_cost_drag > thresholds["max_cost_drag_pct"]:
        warnings.append(_warning("overfitting_cost_sensitivity", "Cost drag may dominate historical results."))
    if walk_forward_stability == "unstable":
        warnings.append(_warning("overfitting_walk_forward_instability", "Walk-forward results are unstable."))
    if parameter_status in {"fragile", "inconsistent"}:
        warnings.append(_warning("overfitting_parameter_instability", "Parameter stability is weak."))

    evidence.extend(
        [
            f"min_sample_rows: {min_sample_rows}.",
            f"total_trade_count: {total_trade_count}.",
            f"max_cost_drag_pct: {max_cost_drag}.",
            f"walk_forward_result_stability: {walk_forward_stability}.",
            f"parameter_stability_status: {parameter_status}.",
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
