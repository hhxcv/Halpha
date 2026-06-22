from __future__ import annotations

from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError


BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE = "build_decision_intelligence_material"
MARKET_REGIME_ASSESSMENT_ARTIFACT = "analysis/market_regime_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
DECISION_INTELLIGENCE_DELTA_ARTIFACT = "analysis/decision_intelligence_delta.json"
SCHEMA_VERSION = 1
DECISION_MATERIAL_INPUT_ARTIFACTS = {
    "market_regime_assessment": MARKET_REGIME_ASSESSMENT_ARTIFACT,
    "risk_assessment": RISK_ASSESSMENT_ARTIFACT,
    "decision_recommendations": DECISION_RECOMMENDATIONS_ARTIFACT,
    "watch_triggers": WATCH_TRIGGERS_ARTIFACT,
    "decision_intelligence_delta": DECISION_INTELLIGENCE_DELTA_ARTIFACT,
}


def validate_decision_material_inputs(artifacts: dict[str, dict[str, Any]]) -> None:
    for artifact_key, artifact_name in DECISION_MATERIAL_INPUT_ARTIFACTS.items():
        if artifact_key == "decision_intelligence_delta":
            _changes_from_artifact(artifacts[artifact_key])
        else:
            _records_from_artifact(
                artifacts[artifact_key],
                artifact_name,
                stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
            )


def decision_material_record_count(artifacts: dict[str, dict[str, Any]]) -> int:
    return len(
        _records_from_artifact(
            artifacts["decision_recommendations"],
            DECISION_RECOMMENDATIONS_ARTIFACT,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        )
    )


def render_decision_intelligence_material(
    artifacts: dict[str, dict[str, Any]],
    *,
    run_id: str,
) -> str:
    source_artifacts = _decision_material_source_artifacts(artifacts)
    decision_records = _records_from_artifact(
        artifacts["decision_recommendations"],
        DECISION_RECOMMENDATIONS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    lines = [
        "---",
        "artifact_type: analysis_decision_intelligence_material",
        f"schema_version: {SCHEMA_VERSION}",
        "audience: ai",
        f"run_id: {run_id}",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# decision_intelligence_material",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_decision_material_source_policy()).rstrip(),
        "```",
        "",
        "## decision_overview",
        "",
        "```yaml",
        _yaml_block(_decision_material_overview(artifacts)).rstrip(),
        "```",
        "",
        "## regime",
        "",
        "```yaml",
        _yaml_block(_decision_material_regime(artifacts["market_regime_assessment"])).rstrip(),
        "```",
        "",
        "## risk",
        "",
        "```yaml",
        _yaml_block(_decision_material_risk(artifacts["risk_assessment"])).rstrip(),
        "```",
        "",
        "## recommendations",
        "",
        "```yaml",
        _yaml_block(_decision_material_recommendations(artifacts["decision_recommendations"])).rstrip(),
        "```",
        "",
        "## do_not_do",
        "",
        "```yaml",
        _yaml_block(_decision_material_do_not_do(artifacts["decision_recommendations"])).rstrip(),
        "```",
        "",
        "## invalidation_conditions",
        "",
        "```yaml",
        _yaml_block(_decision_material_invalidation(artifacts["decision_recommendations"])).rstrip(),
        "```",
        "",
        "## watch_triggers",
        "",
        "```yaml",
        _yaml_block(_decision_material_watch_triggers(artifacts["watch_triggers"])).rstrip(),
        "```",
        "",
        "## delta_vs_previous_run",
        "",
        "```yaml",
        _yaml_block(_decision_material_delta(artifacts["decision_intelligence_delta"])).rstrip(),
        "```",
        "",
        "## evidence_conflicts_uncertainty",
        "",
        "```yaml",
        _yaml_block(_decision_material_evidence_conflicts_uncertainty(artifacts)).rstrip(),
        "```",
        "",
        "## report_usage_rules",
        "",
        "```yaml",
        _yaml_block(_decision_material_report_usage_rules()).rstrip(),
        "```",
        "",
    ]

    record_summaries = _decision_material_record_summaries(artifacts)
    for decision in decision_records:
        record_id = _clean_text(decision.get("record_id"), fallback="missing")
        lines.extend(
            [
                f"## record: {record_id}",
                "",
                "```yaml",
                _yaml_block(record_summaries.get(record_id, _decision_material_record_summary(decision, artifacts))).rstrip(),
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def _changes_from_artifact(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    changes = artifact.get("changes")
    if not isinstance(changes, list):
        raise PipelineError(
            f"{DECISION_INTELLIGENCE_DELTA_ARTIFACT} must contain a changes list.",
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
            exit_code=3,
        )
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            raise PipelineError(
                f"changes[{index}] must be a mapping.",
                stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
                exit_code=3,
            )
    return changes


def _decision_material_source_artifacts(artifacts: dict[str, dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            *DECISION_MATERIAL_INPUT_ARTIFACTS.values(),
            *[
                source_artifact
                for artifact in artifacts.values()
                for source_artifact in _string_list(artifact.get("source_artifacts"))
            ],
            *[
                source_artifact
                for change in _changes_from_artifact(artifacts["decision_intelligence_delta"])
                for source_artifact in _string_list(change.get("source_artifacts"))
            ],
        ]
    )


def _decision_material_source_policy() -> dict[str, Any]:
    return {
        "material_scope": "decision_intelligence_summary",
        "allowed_source_artifacts": DECISION_MATERIAL_INPUT_ARTIFACTS,
        "research_decision_support_only": True,
        "financial_advice": False,
        "trading_execution": False,
        "exchange_account_operations": False,
        "position_sizing_or_order_instructions": False,
        "return_promise": False,
        "codex_may_explain_not_infer_action_levels": True,
        "codex_may_explain_fusion_context": True,
        "codex_may_generate_fusion_states": False,
        "do_not_recalculate_from_raw_ohlcv": True,
        "preserve_risks_conflicts_uncertainty_near_actions": True,
    }


def _decision_material_overview(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    regimes = _records_from_artifact(
        artifacts["market_regime_assessment"],
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    risks = _records_from_artifact(
        artifacts["risk_assessment"],
        RISK_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    decisions = _records_from_artifact(
        artifacts["decision_recommendations"],
        DECISION_RECOMMENDATIONS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    triggers = _records_from_artifact(
        artifacts["watch_triggers"],
        WATCH_TRIGGERS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    delta = artifacts["decision_intelligence_delta"]
    return {
        "decision_record_count": len(decisions),
        "regime_record_count": len(regimes),
        "risk_record_count": len(risks),
        "watch_trigger_count": len(triggers),
        "delta_status": delta.get("status"),
        "delta_change_count": len(_changes_from_artifact(delta)),
        "previous_run_id": delta.get("previous_run_id"),
        "previous_run_path": delta.get("previous_run_path"),
        "symbols": _sorted_unique(record.get("symbol") for record in decisions),
        "timeframes": _sorted_unique(record.get("timeframe") for record in decisions),
        "action_level_counts": _count_by_clean_text(decisions, "action_level"),
        "decision_bias_counts": _count_by_clean_text(decisions, "decision_bias"),
        "fusion_linked_records": sum(1 for record in decisions if record.get("fusion_record_id")),
        "fusion_adjusted_records": sum(1 for record in decisions if record.get("pre_fusion_action_level")),
        "personalized_linked_records": sum(1 for record in decisions if record.get("personalized_constraint_id")),
        "personalized_adjusted_records": sum(
            1 for record in decisions if record.get("pre_personalized_action_level")
        ),
        "risk_level_counts": _count_by_clean_text(risks, "risk_level"),
        "regime_counts": _count_by_clean_text(regimes, "regime"),
        "source_artifacts": _decision_material_source_artifacts(artifacts),
    }


def _decision_material_regime(artifact: dict[str, Any]) -> dict[str, Any]:
    records = _records_from_artifact(
        artifact,
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    return {
        "source_artifacts": _unique_ordered(
            [MARKET_REGIME_ASSESSMENT_ARTIFACT, *_string_list(artifact.get("source_artifacts"))]
        ),
        "records": [
            {
                "scope": _record_scope(record),
                "regime": record.get("regime"),
                "confidence": record.get("confidence"),
                "status": record.get("status"),
                "evidence": _string_list(record.get("evidence"))[:6],
                "conflicts": _string_list(record.get("conflicts")),
                "uncertainty": _string_list(record.get("uncertainty"))[:6],
                "warnings": _string_list(record.get("warnings")),
                "source_artifacts": _string_list(record.get("source_artifacts")),
            }
            for record in records
        ],
    }


def _decision_material_risk(artifact: dict[str, Any]) -> dict[str, Any]:
    records = _records_from_artifact(
        artifact,
        RISK_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    return {
        "source_artifacts": _unique_ordered(
            [RISK_ASSESSMENT_ARTIFACT, *_string_list(artifact.get("source_artifacts"))]
        ),
        "records": [
            {
                "scope": _record_scope(record),
                "risk_level": record.get("risk_level"),
                "status": record.get("status"),
                "rising_risks": _string_list(record.get("rising_risks")),
                "blocking_risks": _string_list(record.get("blocking_risks")),
                "data_quality_risks": _string_list(record.get("data_quality_risks")),
                "signal_conflict_risks": _string_list(record.get("signal_conflict_risks")),
                "gates": _mapping(record.get("gates")),
                "evidence": _string_list(record.get("evidence"))[:6],
                "warnings": _string_list(record.get("warnings")),
                "source_artifacts": _string_list(record.get("source_artifacts")),
            }
            for record in records
        ],
    }


def _decision_material_recommendations(artifact: dict[str, Any]) -> dict[str, Any]:
    records = _records_from_artifact(
        artifact,
        DECISION_RECOMMENDATIONS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    return {
        "source_artifacts": _unique_ordered(
            [DECISION_RECOMMENDATIONS_ARTIFACT, *_string_list(artifact.get("source_artifacts"))]
        ),
        "records": [
            {
                "scope": _record_scope(record),
                "record_id": record.get("record_id"),
                "action_level": record.get("action_level"),
                "decision_bias": record.get("decision_bias"),
                "confidence": record.get("confidence"),
                "status": record.get("status"),
                "pre_fusion_action_level": record.get("pre_fusion_action_level"),
                "pre_personalized_action_level": record.get("pre_personalized_action_level"),
                "fusion_record_id": record.get("fusion_record_id"),
                "fusion_state": record.get("fusion_state"),
                "fusion_conflict_state": record.get("fusion_conflict_state"),
                "fusion_risk_override_state": record.get("fusion_risk_override_state"),
                "fusion_event_override_state": record.get("fusion_event_override_state"),
                "fusion_outcome_feedback_state": record.get("fusion_outcome_feedback_state"),
                "fusion_adjustment_reasons": _string_list(record.get("fusion_adjustment_reasons")),
                "personalized_constraint_id": record.get("personalized_constraint_id"),
                "personalized_state": record.get("personalized_state"),
                "personalized_action": record.get("personalized_action"),
                "personalized_reason_codes": _string_list(record.get("personalized_reason_codes")),
                "personalized_adjustment_reasons": _string_list(record.get("personalized_adjustment_reasons")),
                "recommended_actions": _string_list(record.get("recommended_actions")),
                "risk_conditions": _string_list(record.get("risk_conditions")),
                "source_artifacts": _string_list(record.get("source_artifacts")),
            }
            for record in records
        ],
    }


def _decision_material_do_not_do(artifact: dict[str, Any]) -> dict[str, Any]:
    records = _records_from_artifact(
        artifact,
        DECISION_RECOMMENDATIONS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    return {
        "guidance_policy": "Use as conservative research constraints, not account instructions.",
        "records": [
            {
                "scope": _record_scope(record),
                "record_id": record.get("record_id"),
                "action_level": record.get("action_level"),
                "do_not_do": _string_list(record.get("do_not_do")),
                "source_artifacts": _string_list(record.get("source_artifacts")),
            }
            for record in records
        ],
    }


def _decision_material_invalidation(artifact: dict[str, Any]) -> dict[str, Any]:
    records = _records_from_artifact(
        artifact,
        DECISION_RECOMMENDATIONS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    return {
        "condition_policy": "Invalidation conditions describe when the deterministic view should be reconsidered.",
        "records": [
            {
                "scope": _record_scope(record),
                "record_id": record.get("record_id"),
                "invalidation_conditions": _string_list(record.get("invalidation_conditions")),
                "source_artifacts": _string_list(record.get("source_artifacts")),
            }
            for record in records
        ],
    }


def _decision_material_watch_triggers(artifact: dict[str, Any]) -> dict[str, Any]:
    records = _records_from_artifact(
        artifact,
        WATCH_TRIGGERS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    return {
        "trigger_policy": "Static watch triggers only; no monitoring, alerting, or execution is implied.",
        "source_artifacts": _unique_ordered(
            [WATCH_TRIGGERS_ARTIFACT, *_string_list(artifact.get("source_artifacts"))]
        ),
        "records": [
            {
                "scope": _record_scope(record),
                "trigger_id": record.get("trigger_id"),
                "type": record.get("type"),
                "condition": record.get("condition"),
                "priority": record.get("priority"),
                "expected_decision_impact": record.get("expected_decision_impact"),
                "linked_decision_record_id": record.get("linked_decision_record_id"),
                "personalized_constraint_id": record.get("personalized_constraint_id"),
                "personalized_state": record.get("personalized_state"),
                "personalized_action": record.get("personalized_action"),
                "personalized_reason_codes": _string_list(record.get("personalized_reason_codes")),
                "evidence": _string_list(record.get("evidence"))[:4],
                "source_artifacts": _string_list(record.get("source_artifacts")),
            }
            for record in records
        ],
    }


def _decision_material_delta(artifact: dict[str, Any]) -> dict[str, Any]:
    changes = _changes_from_artifact(artifact)
    return {
        "status": artifact.get("status"),
        "previous_run_id": artifact.get("previous_run_id"),
        "previous_run_path": artifact.get("previous_run_path"),
        "change_count": len(changes),
        "changes": [
            {
                "change_id": change.get("change_id"),
                "scope": _mapping(change.get("scope")),
                "field": change.get("field"),
                "from": change.get("from"),
                "to": change.get("to"),
                "source_artifacts": _string_list(change.get("source_artifacts")),
            }
            for change in changes
        ],
        "warnings": _string_list(artifact.get("warnings")),
        "errors": _string_list(artifact.get("errors")),
        "source_artifacts": _unique_ordered(
            [DECISION_INTELLIGENCE_DELTA_ARTIFACT, *_string_list(artifact.get("source_artifacts"))]
        ),
    }


def _decision_material_evidence_conflicts_uncertainty(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    regimes = _records_from_artifact(
        artifacts["market_regime_assessment"],
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    risks = _records_from_artifact(
        artifacts["risk_assessment"],
        RISK_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    decisions = _records_from_artifact(
        artifacts["decision_recommendations"],
        DECISION_RECOMMENDATIONS_ARTIFACT,
        stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
    )
    return {
        "evidence": _unique_ordered(
            [
                *[item for record in regimes for item in _string_list(record.get("evidence"))[:3]],
                *[item for record in risks for item in _string_list(record.get("evidence"))[:3]],
                *[item for record in decisions for item in _string_list(record.get("evidence"))[:3]],
                *[item for record in decisions for item in _string_list(record.get("fusion_evidence"))[:3]],
            ]
        )[:30],
        "conflicts": _unique_ordered(
            [
                *[item for record in regimes for item in _string_list(record.get("conflicts"))],
                *[item for record in decisions for item in _string_list(record.get("conflicts"))],
                *[item for record in risks for item in _string_list(record.get("signal_conflict_risks"))],
            ]
        ),
        "uncertainty": _unique_ordered(
            [
                *[item for record in regimes for item in _string_list(record.get("uncertainty"))],
                *[item for record in risks for item in _string_list(record.get("warnings"))],
                *[item for record in decisions for item in _string_list(record.get("warnings"))],
                *[item for record in decisions for item in _string_list(record.get("fusion_uncertainty"))],
            ]
        ),
        "source_artifacts": _decision_material_source_artifacts(artifacts),
    }


def _decision_material_report_usage_rules() -> dict[str, Any]:
    return {
        "use_decision_material_for": [
            "current decision bias",
            "what to do as research decision support",
            "what not to do",
            "risk state",
            "watch and wait conditions",
            "invalidation conditions",
            "changes versus previous run",
        ],
        "must_keep_near_action_guidance": [
            "evidence",
            "risk conditions",
            "conflicts",
            "uncertainty",
            "source artifact references",
        ],
        "must_not": [
            "invent action levels",
            "upgrade WATCH or low-confidence material into strong advice",
            "present recommendations as trading execution",
            "provide position sizing or account actions",
            "promise returns",
            "replace M2 quant evidence material",
        ],
    }


def _decision_material_record_summaries(artifacts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _clean_text(record.get("record_id"), fallback="missing"): _decision_material_record_summary(record, artifacts)
        for record in _records_from_artifact(
            artifacts["decision_recommendations"],
            DECISION_RECOMMENDATIONS_ARTIFACT,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        )
    }


def _decision_material_record_summary(
    decision: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    key = _tuple_key(decision)
    regime = _record_by_key(artifacts["market_regime_assessment"], MARKET_REGIME_ASSESSMENT_ARTIFACT).get(key)
    risk = _record_by_key(artifacts["risk_assessment"], RISK_ASSESSMENT_ARTIFACT).get(key)
    watch_triggers = [
        record
        for record in _records_from_artifact(
            artifacts["watch_triggers"],
            WATCH_TRIGGERS_ARTIFACT,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        )
        if _tuple_key(record) == key
    ]
    changes = [
        change
        for change in _changes_from_artifact(artifacts["decision_intelligence_delta"])
        if _change_key(change) == key
    ]
    return {
        "record_type": "decision_intelligence_summary",
        "scope": _record_scope(decision),
        "decision_record_id": decision.get("record_id"),
        "action_guidance": {
            "action_level": decision.get("action_level"),
            "decision_bias": decision.get("decision_bias"),
            "confidence": decision.get("confidence"),
            "recommended_actions": _string_list(decision.get("recommended_actions")),
            "research_decision_support_only": True,
            "pre_fusion_action_level": decision.get("pre_fusion_action_level"),
            "fusion_adjustment_reasons": _string_list(decision.get("fusion_adjustment_reasons")),
        },
        "fusion_context": {
            "fusion_record_id": decision.get("fusion_record_id"),
            "fusion_state": decision.get("fusion_state"),
            "fusion_conflict_state": decision.get("fusion_conflict_state"),
            "fusion_risk_override_state": decision.get("fusion_risk_override_state"),
            "fusion_event_override_state": decision.get("fusion_event_override_state"),
            "fusion_outcome_feedback_state": decision.get("fusion_outcome_feedback_state"),
            "fusion_confidence": decision.get("fusion_confidence"),
            "fusion_evidence": _string_list(decision.get("fusion_evidence"))[:6],
            "fusion_uncertainty": _string_list(decision.get("fusion_uncertainty"))[:6],
        },
        "do_not_do": _string_list(decision.get("do_not_do")),
        "invalidation_conditions": _string_list(decision.get("invalidation_conditions")),
        "risk_conditions": _string_list(decision.get("risk_conditions")),
        "regime": None if regime is None else {
            "regime": regime.get("regime"),
            "confidence": regime.get("confidence"),
            "status": regime.get("status"),
        },
        "risk": None if risk is None else {
            "risk_level": risk.get("risk_level"),
            "rising_risks": _string_list(risk.get("rising_risks")),
            "blocking_risks": _string_list(risk.get("blocking_risks")),
            "signal_conflict_risks": _string_list(risk.get("signal_conflict_risks")),
        },
        "watch_triggers": [
            {
                "type": trigger.get("type"),
                "condition": trigger.get("condition"),
                "priority": trigger.get("priority"),
                "expected_decision_impact": trigger.get("expected_decision_impact"),
            }
            for trigger in watch_triggers
        ],
        "delta_vs_previous_run": [
            {
                "field": change.get("field"),
                "from": change.get("from"),
                "to": change.get("to"),
                "source_artifacts": _string_list(change.get("source_artifacts")),
            }
            for change in changes
        ],
        "evidence": _string_list(decision.get("evidence"))[:8],
        "conflicts": _string_list(decision.get("conflicts")),
        "uncertainty": _unique_ordered(
            [
                *_string_list(decision.get("warnings")),
                *(_string_list(regime.get("uncertainty")) if regime else []),
                *(_string_list(risk.get("warnings")) if risk else []),
            ]
        ),
        "source_artifacts": _unique_ordered(
            [
                DECISION_RECOMMENDATIONS_ARTIFACT,
                *_string_list(decision.get("source_artifacts")),
                *(_string_list(regime.get("source_artifacts")) if regime else []),
                *(_string_list(risk.get("source_artifacts")) if risk else []),
                *[
                    artifact
                    for trigger in watch_triggers
                    for artifact in _string_list(trigger.get("source_artifacts"))
                ],
                DECISION_INTELLIGENCE_DELTA_ARTIFACT,
            ]
        ),
    }


def _record_by_key(artifact: dict[str, Any], artifact_name: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        _tuple_key(record): record
        for record in _records_from_artifact(
            artifact,
            artifact_name,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        )
    }


def _record_scope(record: dict[str, Any]) -> dict[str, str]:
    source, symbol, timeframe = _tuple_key(record)
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
    }


def _change_key(change: dict[str, Any]) -> tuple[str, str, str]:
    scope = _mapping(change.get("scope"))
    return (
        _clean_text(scope.get("source"), fallback="missing"),
        _clean_text(scope.get("symbol"), fallback="missing"),
        _clean_text(scope.get("timeframe"), fallback="missing"),
    )


def _records_from_artifact(artifact: dict[str, Any], artifact_name: str, *, stage: str) -> list[dict[str, Any]]:
    records = artifact.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{artifact_name} must contain a records list.",
            stage=stage,
            exit_code=3,
        )
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise PipelineError(
                f"records[{index}] must be a mapping.",
                stage=stage,
                exit_code=3,
            )
    return records


def _tuple_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean_text(item.get("source"), fallback="unknown_source"),
        _clean_text(item.get("symbol"), fallback="unknown_symbol"),
        _clean_text(item.get("timeframe"), fallback="unknown_timeframe"),
    )


def _count_by_clean_text(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = _clean_text(record.get(field), fallback="unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _clean_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _sorted_unique(values: list[Any] | tuple[Any, ...] | Any) -> list[str]:
    if not isinstance(values, list | tuple):
        values = list(values)
    return sorted(
        {
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        }
    )


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML decision intelligence material.",
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
