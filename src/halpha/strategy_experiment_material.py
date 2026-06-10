from __future__ import annotations

from typing import Any

from .pipeline import PipelineError


STRATEGY_EXPERIMENT_ARTIFACT = "analysis/strategy_experiment.json"
STRATEGY_EFFECTIVENESS_GATES_ARTIFACT = "analysis/strategy_effectiveness_gates.json"
STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT = "analysis/strategy_experiment_material.md"
SCHEMA_VERSION = 1
STAGE_NAME = "build_strategy_experiment_material"


def render_strategy_experiment_material(
    experiment_artifact: dict[str, Any],
    gates_artifact: dict[str, Any],
) -> str:
    candidates = _dict_list(experiment_artifact.get("candidates"))
    records = _dict_list(gates_artifact.get("records"))
    candidate_by_name = {
        str(candidate.get("strategy_name")): candidate
        for candidate in candidates
        if isinstance(candidate.get("strategy_name"), str)
    }
    source_artifacts = _unique_ordered(
        [
            STRATEGY_EXPERIMENT_ARTIFACT,
            STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
            *_string_list(experiment_artifact.get("source_artifacts")),
            *_string_list(gates_artifact.get("source_artifacts")),
        ]
    )
    lines = [
        "---",
        "artifact_type: analysis_strategy_experiment_material",
        f"schema_version: {SCHEMA_VERSION}",
        "audience: ai",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# strategy_experiment_material",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_source_policy()).rstrip(),
        "```",
        "",
        "## experiment_overview",
        "",
        "```yaml",
        _yaml_block(_experiment_overview(experiment_artifact, gates_artifact, records)).rstrip(),
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
                f"## record: {record.get('gate_id')}",
                "",
                "```yaml",
                _yaml_block(
                    _material_record(
                        record,
                        candidate_by_name.get(str(record.get("strategy_name")), {}),
                    )
                ).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _source_policy() -> dict[str, Any]:
    return {
        "strategy_experiment_material_is_financial_advice": False,
        "trading_instructions_allowed": False,
        "gate_outcomes_generated_by_halpha": True,
        "codex_may_generate_gate_outcomes": False,
        "automatic_parameter_optimization": False,
        "effective_candidate_is_live_trading_approval": False,
        "historical_experiment_is_forecast": False,
        "raw_ohlcv_history_embedded": False,
        "allowed_basis": [
            "strategy_experiment",
            "strategy_effectiveness_gates",
            "benchmark_coverage",
            "net_performance",
            "baseline_comparison",
            "cost_drag",
            "sample_quality",
            "walk_forward_stability",
            "parameter_stability",
            "overfitting_risk",
            "reasons",
            "warnings",
            "errors",
        ],
    }


def _experiment_overview(
    experiment_artifact: dict[str, Any],
    gates_artifact: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "material_scope": "strategy_experiment_effectiveness_summary",
        "experiment_id": experiment_artifact.get("experiment_id"),
        "experiment_coverage": _mapping(experiment_artifact.get("coverage")),
        "gate_coverage": _mapping(gates_artifact.get("coverage")),
        "gate_status_counts": _count_by(records, "status"),
        "effective_strategy_candidates": _names_by_status(records, "effective"),
        "watchlisted_strategy_candidates": _names_by_status(records, "watchlisted"),
        "rejected_strategy_candidates": _names_by_status(records, "rejected"),
        "insufficient_evidence_strategy_candidates": _names_by_status(records, "insufficient_evidence"),
        "warning_codes": _warning_codes(records),
        "raw_ohlcv_history_embedded": False,
    }


def _report_guidance() -> dict[str, Any]:
    return {
        "effective_candidates": [
            "Identify effective candidates as research candidates only, not trading approvals.",
            "Explain benchmark coverage, cost drag, baseline comparison, walk-forward evidence, sample limits, and overfitting checks near the effectiveness statement.",
        ],
        "watchlisted_candidates": [
            "Identify watchlisted candidates and explain the downgrade reason before any synthesis.",
            "Do not upgrade watchlisted evidence into effective or action-oriented language.",
        ],
        "rejected_candidates": [
            "Identify rejected candidates when relevant and state the rejection reason plainly.",
            "Do not use rejected candidates as supportive evidence for current strategy strength.",
        ],
        "insufficient_evidence_candidates": [
            "State that evidence is insufficient when benchmark coverage, sample quality, or walk-forward evidence is missing.",
            "Do not infer missing metrics or gate outcomes.",
        ],
        "forbidden": [
            "Do not generate new gate statuses.",
            "Do not calculate new metrics.",
            "Do not select best parameters.",
            "Do not create trading recommendations, position sizing, account actions, or return promises.",
        ],
    }


def _material_record(record: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    inputs = _mapping(record.get("gate_inputs"))
    return {
        "record_type": "strategy_effectiveness_gate",
        "gate_id": record.get("gate_id"),
        "strategy_name": record.get("strategy_name"),
        "status": record.get("status"),
        "params": _mapping(record.get("params")),
        "candidate_summary": _mapping(candidate.get("summary")),
        "benchmark_coverage": _mapping(inputs.get("benchmark_coverage")),
        "net_performance": _mapping(inputs.get("net_performance")),
        "baseline_comparison": _mapping(inputs.get("baseline_comparison")),
        "cost_drag": _mapping(inputs.get("cost_drag")),
        "drawdown": _mapping(inputs.get("drawdown")),
        "trade_count": _mapping(inputs.get("trade_count")),
        "sample_quality": _mapping(inputs.get("sample_quality")),
        "walk_forward_stability": _mapping(inputs.get("walk_forward_stability")),
        "parameter_stability": _mapping(inputs.get("parameter_stability")),
        "overfitting_risk": _mapping(inputs.get("overfitting_risk")),
        "reasons": [
            {
                "code": item.get("code"),
                "severity": item.get("severity"),
                "value": item.get("value"),
                "threshold": item.get("threshold"),
                "message": item.get("message"),
            }
            for item in _dict_list(record.get("reasons"))
        ],
        "warnings": [
            {
                "code": item.get("code"),
                "message": item.get("message"),
                "source": item.get("source"),
            }
            for item in _dict_list(record.get("warnings"))
        ],
        "errors": [
            {
                "error_type": item.get("error_type"),
                "message": item.get("message"),
                "stage": item.get("stage"),
            }
            for item in _dict_list(record.get("errors"))
        ],
        "source_artifacts": _string_list(record.get("source_artifacts")),
        "report_note": _record_report_note(record),
    }


def _record_report_note(record: dict[str, Any]) -> str:
    status = record.get("status")
    if status == "effective":
        return "Use as an effective research candidate only; cite costs, coverage, sample, walk-forward, and overfitting limits."
    if status == "watchlisted":
        return "Use cautious language; explain watchlist reasons and do not upgrade to effective."
    if status == "rejected":
        return "State rejection when relevant and do not use this candidate as supportive evidence."
    if status == "insufficient_evidence":
        return "State that evidence is insufficient and do not infer missing gate outcomes."
    return "Treat unknown gate status as unavailable evidence."


def _count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            value = "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _names_by_status(records: list[dict[str, Any]], status: str) -> list[str]:
    return sorted(
        str(record.get("strategy_name"))
        for record in records
        if record.get("status") == status and isinstance(record.get("strategy_name"), str)
    )


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
            "PyYAML is required to write YAML strategy experiment material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
