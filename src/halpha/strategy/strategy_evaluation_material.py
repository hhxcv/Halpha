from __future__ import annotations

from typing import Any

from halpha.pipeline import PipelineError


STRATEGY_EVALUATION_SUMMARY_ARTIFACT = "analysis/strategy_evaluation_summary.json"
STRATEGY_EVALUATION_MATERIAL_ARTIFACT = "analysis/strategy_evaluation_material.md"
SCHEMA_VERSION = 1


def render_strategy_evaluation_material(artifact: dict[str, Any]) -> str:
    records = _records(artifact)
    source_artifacts = _unique_ordered(
        [
            STRATEGY_EVALUATION_SUMMARY_ARTIFACT,
            *_string_list(artifact.get("source_artifacts")),
        ]
    )
    lines = [
        "---",
        "artifact_type: analysis_strategy_evaluation_material",
        f"schema_version: {SCHEMA_VERSION}",
        "audience: ai",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# strategy_evaluation_material",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_source_policy()).rstrip(),
        "```",
        "",
        "## evaluation_overview",
        "",
        "```yaml",
        _yaml_block(_evaluation_overview(records)).rstrip(),
        "```",
        "",
        "## report_guidance",
        "",
        "```yaml",
        _yaml_block(_report_guidance()).rstrip(),
        "```",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"## record: {record.get('evaluation_id')}",
                "",
                "```yaml",
                _yaml_block(_material_record(record)).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _records(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    records = artifact.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{STRATEGY_EVALUATION_SUMMARY_ARTIFACT} must contain a records list.",
            stage="evaluate_strategy_evaluation",
            exit_code=3,
        )
    return [record for record in records if isinstance(record, dict)]


def _source_policy() -> dict[str, Any]:
    return {
        "evaluation_material_is_financial_advice": False,
        "trading_instructions_allowed": False,
        "raw_ohlcv_history_embedded": False,
        "equity_curves_embedded": False,
        "full_walk_forward_windows_embedded": False,
        "metrics_generated_by_halpha": True,
        "codex_may_generate_metrics": False,
        "historical_evaluation_is_forecast": False,
        "parameter_diagnostics_are_optimization": False,
        "best_parameter_selection_allowed": False,
        "allowed_basis": [
            "strategy_evaluation_summary",
            "cost_assumptions",
            "strategy_metrics",
            "baseline_metrics",
            "relative_metrics",
            "walk_forward_summary",
            "parameter_stability",
            "overfitting_risk",
            "warnings",
            "assessment",
        ],
    }


def _evaluation_overview(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "material_scope": "strategy_evaluation_summary",
        "evaluation_record_count": len(records),
        "status_counts": _count_by(records, "status"),
        "reliability_counts": _count_nested(records, "assessment", "reliability"),
        "walk_forward_status_counts": _count_nested(records, "walk_forward", "status"),
        "parameter_stability_status_counts": _count_nested(records, "parameter_stability", "status"),
        "overfitting_risk_status_counts": _count_nested(records, "overfitting_risk", "status"),
        "warning_codes": _warning_codes(records),
        "raw_ohlcv_history_embedded": False,
    }


def _report_guidance() -> dict[str, Any]:
    return {
        "cost_assumptions": [
            "Mention fees and slippage assumptions before interpreting net performance.",
            "Compare gross and net results when cost drag is visible.",
        ],
        "baseline_comparison": [
            "Compare strategy net behavior with buy-and-hold and cash baselines.",
            "Do not present excess return as a forecast or recommendation.",
        ],
        "sample_limits": [
            "Explain short samples, low trade count, high turnover, unstable walk-forward results, and insufficient data.",
            "Keep sample limits close to any reliability statement.",
        ],
        "reliability": [
            "Use reliability, walk-forward, parameter-stability, and overfitting-risk fields as bounded research evidence.",
            "Do not upgrade weak, fragile, unstable, or insufficient evidence into stronger action language.",
        ],
        "forbidden": [
            "Do not generate new metrics.",
            "Do not select best parameters.",
            "Do not create trading recommendations, position sizing, account actions, or return promises.",
        ],
    }


def _material_record(record: dict[str, Any]) -> dict[str, Any]:
    single = _mapping(record.get("single_window"))
    metrics = _mapping(single.get("strategy_metrics"))
    trade = _mapping(single.get("trade_summary"))
    baseline = _mapping(single.get("baseline_metrics"))
    buy_and_hold = _mapping(baseline.get("buy_and_hold"))
    cash = _mapping(baseline.get("cash"))
    relative = _mapping(single.get("relative_metrics"))
    walk_forward = _mapping(record.get("walk_forward"))
    walk_summary = _mapping(walk_forward.get("summary"))
    parameter = _mapping(record.get("parameter_stability"))
    overfitting = _mapping(record.get("overfitting_risk"))
    assessment = _mapping(record.get("assessment"))
    return {
        "record_type": "strategy_evaluation",
        "evaluation_id": record.get("evaluation_id"),
        "strategy_name": record.get("strategy_name"),
        "source": record.get("source"),
        "symbol": record.get("symbol"),
        "timeframe": record.get("timeframe"),
        "status": record.get("status"),
        "input_window_start": record.get("input_window_start"),
        "input_window_end": record.get("input_window_end"),
        "latest_candle_time": record.get("latest_candle_time"),
        "assessment": {
            "reliability": assessment.get("reliability"),
            "sample_quality": assessment.get("sample_quality"),
            "cost_sensitivity": assessment.get("cost_sensitivity"),
            "overfitting_risk": assessment.get("overfitting_risk"),
            "summary": assessment.get("summary"),
            "evidence": _string_list(assessment.get("evidence")),
            "uncertainty": _string_list(assessment.get("uncertainty")),
        },
        "cost_assumptions": _mapping(single.get("cost_assumptions")),
        "single_window": {
            "sample": _mapping(single.get("sample")),
            "gross_return_pct": metrics.get("gross_return_pct"),
            "net_return_pct": metrics.get("net_return_pct"),
            "total_cost_pct": metrics.get("total_cost_pct"),
            "cost_drag_pct": metrics.get("cost_drag_pct"),
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "volatility_pct": metrics.get("volatility_pct"),
            "sharpe": metrics.get("sharpe"),
            "sortino": metrics.get("sortino"),
            "trade_count": trade.get("trade_count"),
            "hit_rate_pct": trade.get("hit_rate_pct"),
            "turnover": trade.get("turnover"),
            "exposure_pct": trade.get("exposure_pct"),
        },
        "baseline_comparison": {
            "buy_and_hold_net_return_pct": buy_and_hold.get("net_return_pct"),
            "cash_net_return_pct": cash.get("net_return_pct"),
            "excess_return_vs_buy_and_hold_pct": relative.get("excess_return_vs_buy_and_hold_pct"),
            "drawdown_delta_vs_buy_and_hold_pct": relative.get("drawdown_delta_vs_buy_and_hold_pct"),
        },
        "walk_forward": {
            "status": walk_forward.get("status"),
            "window_count": walk_summary.get("window_count"),
            "succeeded_windows": walk_summary.get("succeeded_windows"),
            "mean_net_return_pct": walk_summary.get("mean_net_return_pct"),
            "positive_net_return_window_pct": walk_summary.get("positive_net_return_window_pct"),
            "mean_excess_return_vs_buy_and_hold_pct": walk_summary.get(
                "mean_excess_return_vs_buy_and_hold_pct"
            ),
            "result_stability": walk_summary.get("result_stability"),
        },
        "parameter_stability": {
            "enabled": parameter.get("enabled"),
            "status": parameter.get("status"),
            "tested_combinations": parameter.get("tested_combinations"),
            "valid_combinations": parameter.get("valid_combinations"),
            "invalid_combinations": parameter.get("invalid_combinations"),
            "region_counts": _mapping(parameter.get("region_counts")),
        },
        "overfitting_risk": {
            "status": overfitting.get("status"),
            "warning_codes": [
                item.get("code") for item in _dict_list(overfitting.get("warnings")) if item.get("code")
            ],
            "evidence": _string_list(overfitting.get("evidence")),
        },
        "warnings": [
            {
                "code": item.get("code"),
                "message": item.get("message"),
                "source": item.get("source"),
            }
            for item in _dict_list(record.get("warnings"))
        ],
        "source_artifacts": _string_list(record.get("source_artifacts")),
        "report_note": _record_report_note(record),
    }


def _record_report_note(record: dict[str, Any]) -> str:
    assessment = _mapping(record.get("assessment"))
    reliability = assessment.get("reliability")
    overfitting = _mapping(record.get("overfitting_risk")).get("status")
    parameter = _mapping(record.get("parameter_stability")).get("status")
    walk_forward = _mapping(record.get("walk_forward")).get("status")
    if reliability == "low" or overfitting in {"medium", "elevated"}:
        return "Use cautious language; explain reliability and overfitting limits before any synthesis."
    if parameter in {"fragile", "inconsistent", "insufficient_data"}:
        return "Explain parameter stability limits and avoid selecting a best parameter."
    if walk_forward != "succeeded":
        return "Walk-forward evidence is unavailable or insufficient; do not overstate robustness."
    return "Evaluation evidence is usable as bounded historical research context, not as a forecast."


def _count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            value = "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_nested(records: list[dict[str, Any]], section: str, field: str) -> dict[str, int]:
    return _count_by([_mapping(record.get(section)) for record in records], field)


def _warning_codes(records: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            item.get("code")
            for record in records
            for item in _dict_list(record.get("warnings"))
            if isinstance(item.get("code"), str)
        }
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML strategy evaluation material.",
            stage="evaluate_strategy_evaluation",
            exit_code=1,
        ) from exc
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
