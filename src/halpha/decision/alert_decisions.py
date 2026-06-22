from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_alert_decisions"
EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT = "analysis/event_intelligence_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
DERIVATIVES_MARKET_CONTEXT_ARTIFACT = "analysis/derivatives_market_context.json"
MACRO_CALENDAR_CONTEXT_ARTIFACT = "analysis/macro_calendar_context.json"
ONCHAIN_FLOW_CONTEXT_ARTIFACT = "analysis/onchain_flow_context.json"
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
ALERT_DECISIONS_ARTIFACT_TYPE = "alert_decisions"
PRIORITY_TAXONOMY = ("P0", "P1", "P2", "P3", "no_alert", "unknown")
ATTENTION_DECISIONS = {
    "P0": "interrupt_now",
    "P1": "review_soon",
    "P2": "record_without_interrupting",
    "P3": "archive_as_noise",
    "no_alert": "no_alert",
    "unknown": "unknown",
}
URGENT_DECISION_IMPACTS = {"could_invalidate", "could_downgrade"}
RELEVANT_DECISION_IMPACTS = {"could_invalidate", "could_downgrade", "could_upgrade_attention", "supports_existing_view"}
RELEVANT_WATCH_VALUES = {"invalidation", "risk_escalation", "risk_relief", "confirmation", "wait_condition"}
NO_ALERT_DOWNGRADES = {
    "unrelated_event",
    "event_signal_not_accepted",
    "insufficient_event_evidence",
    "insufficient_market_evidence",
    "weak_source_reliability",
    "event_signal_missing",
}
P3_DOWNGRADES = {
    "low_confidence_event",
    "duplicate_event_group",
    "stale_event",
    "event_market_confluence_missing",
    "macro_calendar_source_uncertainty",
    "onchain_flow_source_uncertainty",
}


def build_alert_decisions(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    assessment_artifact = _read_optional_artifact(
        run.analysis_dir / "event_intelligence_assessment.json",
        EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
        records_key="records",
    )
    if assessment_artifact is None:
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    risk_artifact = _read_optional_artifact(
        run.analysis_dir / "risk_assessment.json",
        RISK_ASSESSMENT_ARTIFACT,
        records_key="records",
    )
    decision_artifact = _read_optional_artifact(
        run.analysis_dir / "decision_recommendations.json",
        DECISION_RECOMMENDATIONS_ARTIFACT,
        records_key="records",
    )
    watch_artifact = _read_optional_artifact(
        run.analysis_dir / "watch_triggers.json",
        WATCH_TRIGGERS_ARTIFACT,
        records_key="records",
    )
    derivatives_artifact = _read_optional_artifact(
        run.analysis_dir / "derivatives_market_context.json",
        DERIVATIVES_MARKET_CONTEXT_ARTIFACT,
        records_key="records",
    )
    macro_artifact = _read_optional_artifact(
        run.analysis_dir / "macro_calendar_context.json",
        MACRO_CALENDAR_CONTEXT_ARTIFACT,
        records_key="records",
    )
    onchain_artifact = _read_optional_artifact(
        run.analysis_dir / "onchain_flow_context.json",
        ONCHAIN_FLOW_CONTEXT_ARTIFACT,
        records_key="records",
    )

    assessment_records = _records(assessment_artifact, "records")
    risk_records = _records(risk_artifact, "records")
    decision_records = _records(decision_artifact, "records")
    watch_records = _records(watch_artifact, "records")
    derivatives_records = _records(derivatives_artifact, "records")
    macro_records = _records(macro_artifact, "records")
    onchain_records = _records(onchain_artifact, "records")
    records = [
        _alert_decision_record(
            assessment,
            risk_records=risk_records,
            decision_records=decision_records,
            watch_records=watch_records,
            derivatives_records=derivatives_records,
            macro_records=macro_records,
            onchain_records=onchain_records,
        )
        for assessment in assessment_records
    ]
    warnings = _artifact_warnings(records)
    if not assessment_records:
        warnings.append("No event intelligence assessment records were available for alert decisions.")
    errors: list[dict[str, Any]] = []
    artifact = {
        "schema_version": 1,
        "artifact_type": ALERT_DECISIONS_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _created_at(assessment_artifact, now=now),
        "priority_taxonomy": list(PRIORITY_TAXONOMY),
        "attention_decision_taxonomy": list(dict.fromkeys(ATTENTION_DECISIONS.values())),
        "source_artifacts": _source_artifacts(
            (EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT, assessment_artifact),
            (RISK_ASSESSMENT_ARTIFACT, risk_artifact),
            (DECISION_RECOMMENDATIONS_ARTIFACT, decision_artifact),
            (WATCH_TRIGGERS_ARTIFACT, watch_artifact),
            (DERIVATIVES_MARKET_CONTEXT_ARTIFACT, derivatives_artifact),
            (MACRO_CALENDAR_CONTEXT_ARTIFACT, macro_artifact),
            (ONCHAIN_FLOW_CONTEXT_ARTIFACT, onchain_artifact),
        ),
        "coverage": _coverage(records),
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }
    write_json(run.analysis_dir / "alert_decisions.json", artifact)
    run.manifest["artifacts"]["alert_decisions"] = ALERT_DECISIONS_ARTIFACT
    _record_manifest_summary(
        run,
        records=records,
        warnings=warnings,
        errors=errors,
        status="succeeded",
        macro_context_records=len(macro_records),
        onchain_context_records=len(onchain_records),
    )
    return [ALERT_DECISIONS_ARTIFACT]


def _alert_decision_record(
    assessment: dict[str, Any],
    *,
    risk_records: list[dict[str, Any]],
    decision_records: list[dict[str, Any]],
    watch_records: list[dict[str, Any]],
    derivatives_records: list[dict[str, Any]],
    macro_records: list[dict[str, Any]],
    onchain_records: list[dict[str, Any]],
) -> dict[str, Any]:
    scope = assessment.get("scope") if isinstance(assessment.get("scope"), dict) else {}
    symbol = _clean_text(scope.get("symbol") or assessment.get("symbol"), fallback="market_wide")
    timeframe = _clean_text(scope.get("timeframe") or assessment.get("timeframe"), fallback="event")
    key = (symbol, timeframe)
    linked_decision_ids = _linked_decision_ids(assessment, decision_records, key)
    linked_watch_ids = _linked_watch_ids(assessment, watch_records, key)
    downgrade_reasons = _string_list(assessment.get("downgrade_reasons"))
    suppression_reasons = _suppression_reasons(assessment, downgrade_reasons)
    evidence_strength = _evidence_strength(assessment, downgrade_reasons=downgrade_reasons)
    priority = _priority(assessment, evidence_strength=evidence_strength, suppression_reasons=suppression_reasons)
    attention_decision = ATTENTION_DECISIONS[priority]
    linked_derivatives = _linked_derivatives_records(assessment, derivatives_records, symbol=symbol)
    derivatives_relevance = _derivatives_relevance(assessment, linked_derivatives)
    linked_macro = _linked_macro_calendar_records(assessment, macro_records, symbol=symbol)
    macro_relevance = _macro_calendar_relevance(assessment, linked_macro)
    linked_onchain = _linked_onchain_flow_records(assessment, onchain_records, symbol=symbol)
    onchain_relevance = _onchain_flow_relevance(assessment, linked_onchain)
    warnings = _warnings(assessment, priority=priority, suppression_reasons=suppression_reasons)
    uncertainty = _unique(
        [
            *_uncertainty(assessment, priority=priority),
            *_derivatives_uncertainty(derivatives_relevance),
            *_macro_calendar_uncertainty(macro_relevance),
            *_onchain_flow_uncertainty(onchain_relevance),
        ]
    )
    return {
        "alert_decision_id": f"alert_decision:{symbol}:{timeframe}:{_assessment_id(assessment)}",
        "status": _status(priority, suppression_reasons),
        "priority": priority,
        "scope": {
            "symbol": symbol,
            "timeframe": timeframe,
            "assessment_id": _assessment_id(assessment),
            "topic_ids": _string_list(scope.get("topic_ids")),
            "event_signal_ids": _string_list(scope.get("event_signal_ids")),
        },
        "attention_decision": attention_decision,
        "decision_impact": _clean_text(assessment.get("decision_impact"), fallback="unknown"),
        "risk_effect": _clean_text(assessment.get("risk_effect"), fallback="unknown"),
        "watch_trigger_relevance": _watch_trigger_relevance(assessment),
        "requires_reassessment": _requires_reassessment(assessment, priority=priority, evidence_strength=evidence_strength),
        "requires_user_attention": priority in {"P0", "P1"},
        "reason": _reason(assessment, priority=priority, evidence_strength=evidence_strength, suppression_reasons=suppression_reasons),
        "evidence_strength": evidence_strength,
        "downgrade_reasons": downgrade_reasons,
        "suppression_reasons": suppression_reasons,
        "uncertainty": uncertainty,
        "warnings": warnings,
        "linked_event_assessment_ids": [_assessment_id(assessment)],
        "linked_decision_record_ids": linked_decision_ids,
        "linked_watch_trigger_ids": linked_watch_ids,
        "linked_derivatives_context_ids": _linked_derivatives_context_ids(linked_derivatives),
        "derivatives_relevance": derivatives_relevance,
        "linked_macro_calendar_context_ids": _linked_macro_calendar_context_ids(linked_macro),
        "macro_calendar_relevance": macro_relevance,
        "linked_onchain_flow_context_ids": _linked_onchain_flow_context_ids(linked_onchain),
        "onchain_flow_relevance": onchain_relevance,
        "source_artifacts": _record_source_artifacts(
            assessment,
            risk_records,
            decision_records,
            watch_records,
            key,
            linked_derivatives,
            linked_macro,
            linked_onchain,
        ),
    }


def _read_optional_artifact(path: Path, artifact_name: str, *, records_key: str) -> dict[str, Any] | None:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact_name} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(f"{artifact_name} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    if not isinstance(artifact.get(records_key), list):
        raise PipelineError(f"{artifact_name} is invalid: {records_key} must be a list.", stage=STAGE_NAME, exit_code=3)
    return artifact


def _records(artifact: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    return [record for record in artifact.get(key) or [] if isinstance(record, dict)]


def _priority(assessment: dict[str, Any], *, evidence_strength: str, suppression_reasons: list[str]) -> str:
    if "suppress_as_no_alert" in suppression_reasons:
        return "no_alert"
    if suppression_reasons:
        return "P3"
    severity = _clean_text(assessment.get("event_severity"), fallback="unknown")
    decision_impact = _clean_text(assessment.get("decision_impact"), fallback="unknown")
    risk_effect = _clean_text(assessment.get("risk_effect"), fallback="unknown")
    watch_relevance = _watch_relevance_value(assessment)
    explicit_relevance = _has_explicit_relevance(assessment)
    if (
        severity in {"critical", "high"}
        and evidence_strength == "high"
        and explicit_relevance
        and (decision_impact == "could_invalidate" or watch_relevance == "invalidation")
    ):
        return "P0"
    if (
        severity in {"critical", "high", "medium"}
        and evidence_strength in {"high", "medium"}
        and explicit_relevance
        and (decision_impact in URGENT_DECISION_IMPACTS or risk_effect == "risk_up" or watch_relevance in {"risk_escalation", "invalidation"})
    ):
        return "P1"
    if severity in {"high", "medium"} and evidence_strength in {"high", "medium"} and explicit_relevance:
        return "P2"
    if severity in {"low", "unknown"} or evidence_strength in {"low", "insufficient"}:
        return "P3"
    return "unknown"


def _evidence_strength(assessment: dict[str, Any], *, downgrade_reasons: list[str]) -> str:
    if set(downgrade_reasons) & NO_ALERT_DOWNGRADES:
        return "insufficient"
    confidence = _clean_text(assessment.get("confidence"), fallback="unknown")
    source_reliability = _clean_text(assessment.get("source_reliability"), fallback="unknown")
    severity = _clean_text(assessment.get("event_severity"), fallback="unknown")
    evidence = assessment.get("evidence") if isinstance(assessment.get("evidence"), list) else []
    source_artifacts = _string_list(assessment.get("source_artifacts"))
    if not evidence or not source_artifacts:
        return "insufficient"
    if confidence == "high" and source_reliability in {"high", "medium"} and severity in {"critical", "high"}:
        return "high"
    if confidence in {"high", "medium"} and source_reliability in {"high", "medium"} and severity in {"critical", "high", "medium"}:
        return "medium"
    if confidence == "low" or source_reliability == "low":
        return "low"
    return "unknown"


def _suppression_reasons(assessment: dict[str, Any], downgrade_reasons: list[str]) -> list[str]:
    reasons: list[str] = []
    severity = _clean_text(assessment.get("event_severity"), fallback="unknown")
    if severity == "noise":
        reasons.append("suppress_as_no_alert")
        reasons.append("noise_event")
    no_alert_downgrades = sorted(set(downgrade_reasons) & NO_ALERT_DOWNGRADES)
    if no_alert_downgrades:
        reasons.append("suppress_as_no_alert")
        reasons.extend(no_alert_downgrades)
    if set(downgrade_reasons) & P3_DOWNGRADES:
        reasons.extend(sorted(set(downgrade_reasons) & P3_DOWNGRADES))
    if _clean_text(assessment.get("status"), fallback="unknown") == "degraded" and not reasons:
        reasons.append("degraded_assessment")
    return _unique(reasons)


def _has_explicit_relevance(assessment: dict[str, Any]) -> bool:
    decision_impact = _clean_text(assessment.get("decision_impact"), fallback="unknown")
    risk_effect = _clean_text(assessment.get("risk_effect"), fallback="unknown")
    watch_relevance = _watch_relevance_value(assessment)
    return (
        decision_impact in RELEVANT_DECISION_IMPACTS
        or risk_effect in {"risk_up", "risk_down", "mixed"}
        or watch_relevance in RELEVANT_WATCH_VALUES
    )


def _watch_trigger_relevance(assessment: dict[str, Any]) -> list[str]:
    value = _watch_relevance_value(assessment)
    if value in {"none", "unknown", ""}:
        return []
    return [value]


def _watch_relevance_value(assessment: dict[str, Any]) -> str:
    value = assessment.get("watch_relevance")
    if isinstance(value, list):
        values = _string_list(value)
        return values[0] if values else "none"
    return _clean_text(value, fallback="none")


def _requires_reassessment(assessment: dict[str, Any], *, priority: str, evidence_strength: str) -> bool:
    if priority in {"P0", "P1"}:
        return True
    if evidence_strength not in {"high", "medium"}:
        return False
    decision_impact = _clean_text(assessment.get("decision_impact"), fallback="unknown")
    watch_relevance = _watch_relevance_value(assessment)
    return decision_impact in {"could_invalidate", "could_downgrade", "could_upgrade_attention"} or watch_relevance in {
        "invalidation",
        "risk_escalation",
    }


def _status(priority: str, suppression_reasons: list[str]) -> str:
    if priority == "no_alert":
        return "suppressed"
    if priority == "P3" or suppression_reasons:
        return "degraded"
    if priority == "unknown":
        return "unknown"
    return "succeeded"


def _warnings(assessment: dict[str, Any], *, priority: str, suppression_reasons: list[str]) -> list[str]:
    warnings = _string_list(assessment.get("warnings"))
    if priority in {"P3", "no_alert"}:
        warnings.append("alert_decision_not_user_attention")
    if suppression_reasons:
        warnings.append("alert_decision_suppressed_or_downgraded")
    return _unique(warnings)


def _uncertainty(assessment: dict[str, Any], *, priority: str) -> list[str]:
    uncertainty = _string_list(assessment.get("uncertainty"))
    uncertainty.append("Alert decision does not send notifications or create trading instructions.")
    if priority in {"P3", "no_alert", "unknown"}:
        uncertainty.append("Alert decision is conservative because evidence is degraded, weak, or not user-relevant.")
    return _unique(uncertainty)


def _reason(
    assessment: dict[str, Any],
    *,
    priority: str,
    evidence_strength: str,
    suppression_reasons: list[str],
) -> str:
    severity = _clean_text(assessment.get("event_severity"), fallback="unknown")
    decision_impact = _clean_text(assessment.get("decision_impact"), fallback="unknown")
    risk_effect = _clean_text(assessment.get("risk_effect"), fallback="unknown")
    watch_relevance = _watch_relevance_value(assessment)
    if suppression_reasons:
        return f"priority={priority}; suppressed_or_downgraded={', '.join(suppression_reasons)}."
    return (
        f"priority={priority}; severity={severity}; evidence_strength={evidence_strength}; "
        f"decision_impact={decision_impact}; risk_effect={risk_effect}; watch_relevance={watch_relevance}."
    )


def _linked_decision_ids(
    assessment: dict[str, Any],
    decision_records: list[dict[str, Any]],
    key: tuple[str, str],
) -> list[str]:
    values = _string_list(assessment.get("linked_decision_record_ids"))
    for record in decision_records:
        if (_clean_text(record.get("symbol"), fallback=""), _clean_text(record.get("timeframe"), fallback="")) != key:
            continue
        if isinstance(record.get("record_id"), str):
            values.append(record["record_id"])
    return _unique(values)


def _linked_watch_ids(
    assessment: dict[str, Any],
    watch_records: list[dict[str, Any]],
    key: tuple[str, str],
) -> list[str]:
    values = _string_list(assessment.get("linked_watch_trigger_ids"))
    for record in watch_records:
        if (_clean_text(record.get("symbol"), fallback=""), _clean_text(record.get("timeframe"), fallback="")) != key:
            continue
        if isinstance(record.get("trigger_id"), str):
            values.append(record["trigger_id"])
    return _unique(values)


def _linked_derivatives_records(
    assessment: dict[str, Any],
    derivatives_records: list[dict[str, Any]],
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    if not _has_explicit_relevance(assessment):
        return []
    if symbol in {"", "market_wide"}:
        return []
    return [
        record
        for record in derivatives_records
        if _clean_text(record.get("symbol"), fallback="") == symbol
        and _clean_text(record.get("status"), fallback="unknown") not in {"", "unknown"}
    ]


def _linked_derivatives_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            context_id
            for record in records
            for context_id in [_clean_text(record.get("context_id"), fallback="")]
            if context_id
        ]
    )


def _linked_macro_calendar_records(
    assessment: dict[str, Any],
    macro_records: list[dict[str, Any]],
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    ids = set(_string_list(assessment.get("linked_macro_calendar_context_ids")))
    if ids:
        return [
            record
            for record in macro_records
            if _clean_text(record.get("context_id"), fallback="") in ids
        ]
    if not _string_list(assessment.get("macro_calendar_relevance")):
        return []
    if symbol in {"", "market_wide"}:
        return []
    linked = []
    for record in macro_records:
        affected = _string_list(record.get("affected_assets"))
        context_type = _clean_text(record.get("context_type"), fallback="")
        if symbol in affected or (not affected and context_type == "source_availability"):
            linked.append(record)
    return _unique_macro_calendar_records(linked)


def _linked_macro_calendar_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            context_id
            for record in records
            for context_id in [_clean_text(record.get("context_id"), fallback="")]
            if context_id
        ]
    )


def _linked_onchain_flow_records(
    assessment: dict[str, Any],
    onchain_records: list[dict[str, Any]],
    *,
    symbol: str,
) -> list[dict[str, Any]]:
    ids = set(_string_list(assessment.get("linked_onchain_flow_context_ids")))
    if ids:
        return [
            record
            for record in onchain_records
            if _clean_text(record.get("context_id"), fallback="") in ids
        ]
    if not _string_list(assessment.get("onchain_flow_relevance")):
        return []
    if symbol in {"", "market_wide"}:
        return []
    return _unique_onchain_flow_records(_onchain_flow_records_for_symbol(onchain_records, symbol))


def _linked_onchain_flow_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            context_id
            for record in records
            for context_id in [_clean_text(record.get("context_id"), fallback="")]
            if context_id
        ]
    )


def _derivatives_relevance(assessment: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return []
    risk_effect = _clean_text(assessment.get("risk_effect"), fallback="unknown")
    watch_relevance = _watch_relevance_value(assessment)
    values = []
    for record in records[:4]:
        values.append(
            "derivatives_context "
            f"{_clean_text(record.get('context_type'), fallback='unknown')} "
            f"state={_clean_text(record.get('state'), fallback='unknown')}; "
            f"severity={_clean_text(record.get('severity'), fallback='unknown')}; "
            f"status={_clean_text(record.get('status'), fallback='unknown')}; "
            f"event_risk_effect={risk_effect}; watch_relevance={watch_relevance}."
        )
    return _unique(values)


def _macro_calendar_relevance(assessment: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    values = _string_list(assessment.get("macro_calendar_relevance"))
    for record in records[:4]:
        values.append(
            "macro_calendar_context "
            f"{_clean_text(record.get('context_type'), fallback='unknown')} "
            f"state={_clean_text(record.get('state'), fallback='unknown')}; "
            f"status={_clean_text(record.get('status'), fallback='unknown')}; "
            f"event={_clean_text(record.get('event_name'), fallback='unknown')}; "
            f"scheduled_at={_clean_text(record.get('scheduled_at'), fallback='unknown')}."
        )
    return _unique(values)


def _onchain_flow_relevance(assessment: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    values = _string_list(assessment.get("onchain_flow_relevance"))
    for record in records[:4]:
        values.append(
            "onchain_flow_context "
            f"{_clean_text(record.get('context_type'), fallback='unknown')} "
            f"state={_clean_text(record.get('state'), fallback='unknown')}; "
            f"severity={_clean_text(record.get('severity'), fallback='unknown')}; "
            f"status={_clean_text(record.get('status'), fallback='unknown')}; "
            f"asset={_clean_text(record.get('asset'), fallback='unknown_asset')}; "
            f"chain={_clean_text(record.get('chain'), fallback='unknown_chain')}."
        )
    return _unique(values)


def _derivatives_uncertainty(relevance: list[str]) -> list[str]:
    if not relevance:
        return []
    return ["Alert decision references derivatives context only as Halpha-generated supporting evidence."]


def _macro_calendar_uncertainty(relevance: list[str]) -> list[str]:
    if not relevance:
        return []
    return ["Alert decision references macro/calendar context only as Halpha-generated scheduled-context evidence."]


def _onchain_flow_uncertainty(relevance: list[str]) -> list[str]:
    if not relevance:
        return []
    return ["Alert decision references on-chain flow context only as Halpha-generated supporting evidence."]


def _record_source_artifacts(
    assessment: dict[str, Any],
    risk_records: list[dict[str, Any]],
    decision_records: list[dict[str, Any]],
    watch_records: list[dict[str, Any]],
    key: tuple[str, str],
    derivatives_records: list[dict[str, Any]] | None = None,
    macro_records: list[dict[str, Any]] | None = None,
    onchain_records: list[dict[str, Any]] | None = None,
) -> list[str]:
    artifacts = [EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT, *_string_list(assessment.get("source_artifacts"))]
    for artifact_path, records in (
        (RISK_ASSESSMENT_ARTIFACT, risk_records),
        (DECISION_RECOMMENDATIONS_ARTIFACT, decision_records),
        (WATCH_TRIGGERS_ARTIFACT, watch_records),
    ):
        if any((_clean_text(record.get("symbol"), fallback=""), _clean_text(record.get("timeframe"), fallback="")) == key for record in records):
            artifacts.append(artifact_path)
    if derivatives_records:
        artifacts.append(DERIVATIVES_MARKET_CONTEXT_ARTIFACT)
        for record in derivatives_records:
            artifacts.extend(_string_list(record.get("source_artifacts")))
    if macro_records:
        artifacts.append(MACRO_CALENDAR_CONTEXT_ARTIFACT)
        for record in macro_records:
            artifacts.extend(_string_list(record.get("source_artifacts")))
    if onchain_records:
        artifacts.append(ONCHAIN_FLOW_CONTEXT_ARTIFACT)
        for record in onchain_records:
            artifacts.extend(_string_list(record.get("source_artifacts")))
    return _unique(artifacts)


def _source_artifacts(*artifacts: tuple[str, dict[str, Any] | None]) -> list[str]:
    values: list[str] = []
    for artifact_path, artifact in artifacts:
        if artifact is None:
            continue
        values.append(artifact_path)
        values.extend(_string_list(artifact.get("source_artifacts")))
    return _unique(values)


def _coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    priority_counts = _count_by(records, "priority")
    return {
        "records": len(records),
        "priority": priority_counts,
        "no_alert_records": priority_counts.get("no_alert", 0),
        "user_attention_records": sum(1 for record in records if record.get("requires_user_attention") is True),
        "downgraded_records": sum(1 for record in records if record.get("downgrade_reasons")),
        "suppressed_records": sum(1 for record in records if record.get("suppression_reasons")),
        "warning_records": sum(1 for record in records if record.get("warnings")),
        "derivatives_linked_records": sum(1 for record in records if record.get("linked_derivatives_context_ids")),
        "macro_calendar_linked_records": sum(1 for record in records if record.get("linked_macro_calendar_context_ids")),
        "onchain_flow_linked_records": sum(1 for record in records if record.get("linked_onchain_flow_context_ids")),
        "p0_p1_records": priority_counts.get("P0", 0) + priority_counts.get("P1", 0),
    }


def _record_manifest_summary(
    run: RunContext,
    *,
    records: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
    macro_context_records: int = 0,
    onchain_context_records: int = 0,
) -> None:
    coverage = _coverage(records)
    run.manifest["counts"]["alert_decision_records"] = coverage["records"]
    run.manifest["counts"]["alert_decision_p0_records"] = coverage["priority"].get("P0", 0)
    run.manifest["counts"]["alert_decision_p1_records"] = coverage["priority"].get("P1", 0)
    run.manifest["counts"]["alert_decision_p2_records"] = coverage["priority"].get("P2", 0)
    run.manifest["counts"]["alert_decision_p3_records"] = coverage["priority"].get("P3", 0)
    run.manifest["counts"]["alert_decision_no_alert_records"] = coverage["no_alert_records"]
    run.manifest["counts"]["alert_decision_downgraded_records"] = coverage["downgraded_records"]
    run.manifest["counts"]["alert_decision_suppressed_records"] = coverage["suppressed_records"]
    run.manifest["counts"]["alert_decision_warning_records"] = coverage["warning_records"]
    run.manifest["counts"]["alert_decision_derivatives_linked_records"] = coverage["derivatives_linked_records"]
    run.manifest["counts"]["alert_decision_macro_calendar_context_records"] = macro_context_records
    run.manifest["counts"]["alert_decision_macro_calendar_linked_records"] = coverage[
        "macro_calendar_linked_records"
    ]
    run.manifest["counts"]["alert_decision_onchain_flow_context_records"] = onchain_context_records
    run.manifest["counts"]["alert_decision_onchain_flow_linked_records"] = coverage[
        "onchain_flow_linked_records"
    ]
    run.manifest["alert_decisions"] = {
        "status": status,
        "artifacts": [ALERT_DECISIONS_ARTIFACT] if status == "succeeded" else [],
        "records": coverage["records"],
        "priority": coverage["priority"],
        "no_alert_records": coverage["no_alert_records"],
        "user_attention_records": coverage["user_attention_records"],
        "downgraded_records": coverage["downgraded_records"],
        "suppressed_records": coverage["suppressed_records"],
        "warning_records": coverage["warning_records"],
        "derivatives_linked_records": coverage["derivatives_linked_records"],
        "macro_calendar_context_records": macro_context_records,
        "macro_calendar_linked_records": coverage["macro_calendar_linked_records"],
        "onchain_flow_context_records": onchain_context_records,
        "onchain_flow_linked_records": coverage["onchain_flow_linked_records"],
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _artifact_warnings(records: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for record in records:
        warnings.extend(_string_list(record.get("warnings")))
    return _unique(warnings)


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = _clean_text(record.get(key), fallback="unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _assessment_id(assessment: dict[str, Any]) -> str:
    return _clean_text(assessment.get("assessment_id"), fallback="event_intelligence_assessment:unknown")


def _created_at(assessment_artifact: dict[str, Any], *, now: datetime | str | None) -> str:
    if now is not None:
        return _utc_timestamp(now)
    if isinstance(assessment_artifact.get("created_at"), str):
        return assessment_artifact["created_at"]
    return _utc_timestamp()


def _utc_timestamp(value: datetime | str | None = None) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp = value or datetime.now(UTC)
    return timestamp.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _unique_macro_calendar_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for record in records:
        key = _clean_text(record.get("context_id"), fallback="")
        if not key:
            key = ":".join(
                _clean_text(record.get(field), fallback="")
                for field in ("context_type", "scheduled_at", "status")
            )
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _onchain_flow_records_for_symbol(records: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    base_asset = _symbol_base_asset(symbol)
    matched: list[dict[str, Any]] = []
    for record in records:
        context_type = _clean_text(record.get("context_type"), fallback="")
        asset = _clean_text(record.get("asset"), fallback="")
        chain = _clean_text(record.get("chain"), fallback="")
        if asset in {"ALL_CONFIGURED_ASSETS", "ALL_STABLECOINS"}:
            matched.append(record)
        elif asset and asset == base_asset:
            matched.append(record)
        elif context_type == "exchange_flow_source_availability" and not asset:
            matched.append(record)
        elif chain == "bitcoin" and base_asset == "BTC":
            matched.append(record)
        elif chain == "ethereum" and base_asset == "ETH":
            matched.append(record)
    return _unique_onchain_flow_records(matched)


def _unique_onchain_flow_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for record in records:
        key = _clean_text(record.get("context_id"), fallback="")
        if not key:
            key = ":".join(
                _clean_text(record.get(field), fallback="")
                for field in ("context_type", "asset", "chain", "as_of", "status")
            )
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _symbol_base_asset(symbol: str) -> str:
    value = _clean_text(symbol, fallback="").upper()
    if not value:
        return ""
    for suffix in ("USDT", "USDC", "BUSD", "USD", "BTC", "ETH"):
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value
