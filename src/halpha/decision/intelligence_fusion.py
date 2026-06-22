from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import RunContext
from halpha.storage import write_json


STAGE_NAME = "build_intelligence_fusion"
INTELLIGENCE_FUSION_ARTIFACT = "analysis/intelligence_fusion.json"
SCHEMA_VERSION = 1

MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
STRATEGY_EVALUATION_SUMMARY_ARTIFACT = "analysis/strategy_evaluation_summary.json"
STRATEGY_EFFECTIVENESS_GATES_ARTIFACT = "analysis/strategy_effectiveness_gates.json"
STRATEGY_LIFECYCLE_STATE_ARTIFACT = "analysis/strategy_lifecycle_state.json"
MARKET_REGIME_ASSESSMENT_ARTIFACT = "analysis/market_regime_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
FACTOR_STATES_ARTIFACT = "analysis/factor_states.json"
MULTI_SOURCE_SIGNALS_ARTIFACT = "analysis/multi_source_signals.json"
EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT = "analysis/event_intelligence_assessment.json"
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
OUTCOME_EVALUATIONS_ARTIFACT = "analysis/outcome_evaluations.json"
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"

STATE_ORDER = (
    "supportive",
    "cautionary",
    "conflicting",
    "risk_blocked",
    "event_overridden",
    "insufficient_evidence",
    "degraded",
    "failed",
    "neutral",
)


def build_intelligence_fusion(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    created_at = _format_utc(now)
    inputs = _FusionInputs(run)
    records = [
        _fusion_record(scope_key, grouped_records, created_at=created_at)
        for scope_key, grouped_records in sorted(inputs.records_by_scope.items(), key=lambda item: _scope_sort_key(item[0]))
    ]
    if not records:
        records = [_empty_record(created_at=created_at, coverage=inputs.coverage)]

    warnings = _unique_sorted(
        [
            warning
            for record in records
            for warning in _string_list(record.get("warnings"))
        ]
        + [
            warning
            for item in inputs.coverage
            for warning in _string_list(item.get("warnings"))
        ]
    )
    errors = [
        error
        for record in records
        for error in _error_list(record.get("errors"))
    ] + [
        error
        for item in inputs.coverage
        for error in _error_list(item.get("errors"))
    ]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "intelligence_fusion",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _artifact_status(records, warnings=warnings, errors=errors),
        "records": records,
        "coverage": sorted(inputs.coverage, key=lambda item: (item["source_layer"], item["source_artifact"])),
        "counts": _counts(records, warnings=warnings, errors=errors),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _unique_sorted(inputs.source_artifacts),
    }
    write_json(run.analysis_dir / "intelligence_fusion.json", artifact)
    _record_manifest(run, artifact)
    return [INTELLIGENCE_FUSION_ARTIFACT]


class _FusionInputs:
    def __init__(self, run: RunContext) -> None:
        self.run = run
        self.records_by_scope: dict[tuple[tuple[str, str | None], ...], list[dict[str, Any]]] = {}
        self.coverage: list[dict[str, Any]] = []
        self.source_artifacts: list[str] = []
        self._load_all()

    def _load_all(self) -> None:
        self._load_market_signals()
        self._load_strategy_evaluation()
        self._load_strategy_gates()
        self._load_strategy_lifecycle()
        self._load_market_regime()
        self._load_risk_assessment()
        self._load_factor_states()
        self._load_multi_source_signals()
        self._load_event_assessments()
        self._load_alert_decisions()
        self._load_outcome_evaluations()
        self._load_data_quality()

    def _load_market_signals(self) -> None:
        artifact = self._read("strategy", MARKET_SIGNALS_ARTIFACT, self.run.analysis_dir / "market_signals.json", "signals")
        if artifact is None:
            return
        for signal in _dict_list(artifact.data.get("signals")):
            self._add(
                _scope_from_fields(signal.get("symbol"), signal.get("timeframe")),
                "strategy",
                MARKET_SIGNALS_ARTIFACT,
                _text(signal.get("signal_id")),
                direction=_text(signal.get("direction")),
                state="insufficient_evidence" if signal.get("insufficient_data") is True else "available",
                confidence=_text(signal.get("confidence")),
                evidence=[f"market_signal direction={_text(signal.get('direction'))} confidence={_text(signal.get('confidence'))}"],
                uncertainty=_string_list(signal.get("uncertainty")),
                warnings=[],
                errors=[],
                source_artifacts=[MARKET_SIGNALS_ARTIFACT, *_string_list(signal.get("source_artifacts"))],
            )

    def _load_strategy_evaluation(self) -> None:
        artifact = self._read(
            "strategy",
            STRATEGY_EVALUATION_SUMMARY_ARTIFACT,
            self.run.analysis_dir / "strategy_evaluation_summary.json",
            "records",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            self._add(
                _scope_from_fields(record.get("symbol"), record.get("timeframe")),
                "strategy_evaluation",
                STRATEGY_EVALUATION_SUMMARY_ARTIFACT,
                _text(record.get("evaluation_id") or record.get("record_id")),
                state=_text(record.get("status") or "available"),
                direction=_text(record.get("direction") or record.get("signal_direction")),
                confidence=_text(record.get("reliability") or record.get("confidence")),
                evidence=["strategy_evaluation record available"],
                uncertainty=_string_list(record.get("uncertainty")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[STRATEGY_EVALUATION_SUMMARY_ARTIFACT, *_string_list(record.get("source_artifacts"))],
            )

    def _load_strategy_gates(self) -> None:
        artifact = self._read(
            "strategy",
            STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
            self.run.analysis_dir / "strategy_effectiveness_gates.json",
            "records",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            self._add(
                _scope_from_fields(record.get("symbol"), record.get("timeframe")),
                "strategy_gate",
                STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
                _text(record.get("gate_id") or record.get("strategy_name")),
                state=_text(record.get("status")),
                direction="unknown",
                confidence="medium" if record.get("status") == "effective" else "low",
                evidence=[f"strategy gate status={_text(record.get('status'))}"],
                uncertainty=[_reason_text(item) for item in _dict_list(record.get("reasons"))],
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[STRATEGY_EFFECTIVENESS_GATES_ARTIFACT, *_string_list(record.get("source_artifacts"))],
            )

    def _load_strategy_lifecycle(self) -> None:
        artifact = self._read_optional(
            "strategy_lifecycle",
            STRATEGY_LIFECYCLE_STATE_ARTIFACT,
            self.run.analysis_dir / "strategy_lifecycle_state.json",
            "records",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            lifecycle_status = _text(record.get("lifecycle_status"))
            health = _dict(record.get("health_state"))
            degradation = _dict(record.get("degradation"))
            retirement = _dict(record.get("retirement"))
            self._add(
                _scope_tuple(record.get("scope")),
                "strategy_lifecycle",
                STRATEGY_LIFECYCLE_STATE_ARTIFACT,
                _text(record.get("lifecycle_record_id")),
                state=lifecycle_status,
                direction=_direction_from_lifecycle(record),
                confidence=_text(health.get("confidence")) or "unknown",
                evidence=_lifecycle_evidence(record),
                uncertainty=_string_list(record.get("uncertainty")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[STRATEGY_LIFECYCLE_STATE_ARTIFACT, *_string_list(record.get("source_artifacts"))],
                extra={
                    "lifecycle_status": lifecycle_status,
                    "health_state": _text(health.get("state")),
                    "degradation_state": _text(degradation.get("state")),
                    "retirement_state": _text(retirement.get("state")),
                    "policy_refs": _string_list(retirement.get("policy_refs"))
                    + _string_list(_dict(record.get("promotion")).get("policy_refs")),
                },
            )

    def _load_market_regime(self) -> None:
        artifact = self._read(
            "regime",
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            self.run.analysis_dir / "market_regime_assessment.json",
            "records",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            self._add(
                _scope_from_fields(record.get("symbol"), record.get("timeframe")),
                "regime",
                MARKET_REGIME_ASSESSMENT_ARTIFACT,
                _text(record.get("record_id")),
                state=_text(record.get("status") or record.get("regime")),
                direction=_direction_from_regime(_text(record.get("regime"))),
                confidence=_text(record.get("confidence")),
                evidence=[f"regime={_text(record.get('regime'))}"],
                uncertainty=_string_list(record.get("conflicts")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[MARKET_REGIME_ASSESSMENT_ARTIFACT, *_string_list(record.get("source_artifacts"))],
            )

    def _load_risk_assessment(self) -> None:
        artifact = self._read(
            "risk",
            RISK_ASSESSMENT_ARTIFACT,
            self.run.analysis_dir / "risk_assessment.json",
            "records",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            risk_level = _text(record.get("risk_level"))
            self._add(
                _scope_from_fields(record.get("symbol"), record.get("timeframe")),
                "risk",
                RISK_ASSESSMENT_ARTIFACT,
                _text(record.get("record_id")),
                state=_text(record.get("status") or risk_level),
                direction="cautionary" if risk_level in {"high", "extreme"} else "neutral",
                confidence=_text(record.get("confidence")),
                evidence=[f"risk_level={risk_level}"],
                uncertainty=_string_list(record.get("signal_conflict_risks")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[RISK_ASSESSMENT_ARTIFACT, *_string_list(record.get("source_artifacts"))],
                extra={
                    "risk_level": risk_level,
                    "blocking_risks": _string_list(record.get("blocking_risks")),
                    "rising_risks": _string_list(record.get("rising_risks")),
                    "cap_action_level": _text(record.get("cap_action_level")),
                },
            )

    def _load_factor_states(self) -> None:
        artifact = self._read("factor", FACTOR_STATES_ARTIFACT, self.run.analysis_dir / "factor_states.json", "records")
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            self._add(
                _scope_tuple(record.get("scope")),
                "factor",
                FACTOR_STATES_ARTIFACT,
                _text(record.get("factor_id")),
                state=_text(record.get("state")),
                direction=_text(record.get("direction")),
                confidence=_text(record.get("confidence")),
                evidence=_string_list(record.get("evidence")) or [f"factor_state={_text(record.get('state'))}"],
                uncertainty=_string_list(record.get("uncertainty")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[FACTOR_STATES_ARTIFACT, *_string_list(record.get("source_artifacts"))],
            )

    def _load_multi_source_signals(self) -> None:
        artifact = self._read(
            "factor",
            MULTI_SOURCE_SIGNALS_ARTIFACT,
            self.run.analysis_dir / "multi_source_signals.json",
            "records",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            self._add(
                _scope_tuple(record.get("scope")),
                "multi_source_signal",
                MULTI_SOURCE_SIGNALS_ARTIFACT,
                _text(record.get("signal_id")),
                state=_text(record.get("state")),
                direction=_text(record.get("direction")),
                confidence=_text(record.get("confidence")),
                evidence=[f"multi_source_signal state={_text(record.get('state'))} direction={_text(record.get('direction'))}"],
                uncertainty=_string_list(record.get("uncertainty")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[MULTI_SOURCE_SIGNALS_ARTIFACT, *_string_list(record.get("source_artifacts"))],
            )

    def _load_event_assessments(self) -> None:
        artifact = self._read(
            "event",
            EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
            self.run.analysis_dir / "event_intelligence_assessment.json",
            "records",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            self._add(
                _scope_tuple(record.get("scope")),
                "event",
                EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
                _text(record.get("assessment_id")),
                state=_text(record.get("status") or record.get("decision_impact")),
                direction=_direction_from_event(record),
                confidence=_text(record.get("confidence")),
                evidence=[
                    f"event severity={_text(record.get('event_severity'))} decision_impact={_text(record.get('decision_impact'))}"
                ],
                uncertainty=_string_list(record.get("uncertainty")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT, *_string_list(record.get("source_artifacts"))],
                extra={
                    "event_severity": _text(record.get("event_severity")),
                    "decision_impact": _text(record.get("decision_impact")),
                    "risk_effect": _text(record.get("risk_effect")),
                    "downgrade_reasons": _string_list(record.get("downgrade_reasons")),
                },
            )

    def _load_alert_decisions(self) -> None:
        artifact = self._read("alert", ALERT_DECISIONS_ARTIFACT, self.run.analysis_dir / "alert_decisions.json", "records")
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("records")):
            scope = _scope_tuple(record.get("scope"))
            self._add(
                scope,
                "alert",
                ALERT_DECISIONS_ARTIFACT,
                _text(record.get("alert_decision_id") or record.get("decision_id")),
                state=_text(record.get("priority")),
                direction="cautionary" if record.get("priority") in {"P0", "P1"} else "neutral",
                confidence=_text(record.get("evidence_strength") or record.get("confidence")),
                evidence=[f"alert priority={_text(record.get('priority'))}"],
                uncertainty=_string_list(record.get("uncertainty")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[ALERT_DECISIONS_ARTIFACT, *_string_list(record.get("source_artifacts"))],
                extra={
                    "priority": _text(record.get("priority")),
                    "suppression_reasons": _string_list(record.get("suppression_reasons")),
                },
            )

    def _load_outcome_evaluations(self) -> None:
        artifact = self._read(
            "outcome",
            OUTCOME_EVALUATIONS_ARTIFACT,
            self.run.analysis_dir / "outcome_evaluations.json",
            "evaluations",
        )
        if artifact is None:
            return
        for record in _dict_list(artifact.data.get("evaluations")):
            self._add(
                _scope_from_fields(record.get("symbol") or record.get("asset"), record.get("timeframe")),
                "outcome",
                OUTCOME_EVALUATIONS_ARTIFACT,
                _text(record.get("outcome_id") or record.get("target_id")),
                state=_text(record.get("outcome_state") or record.get("evaluation_status")),
                direction=_direction_from_outcome(record),
                confidence="medium" if record.get("evaluation_status") == "evaluated" else "low",
                evidence=_string_list(record.get("evidence")) or [f"outcome_state={_text(record.get('outcome_state'))}"],
                uncertainty=_string_list(record.get("uncertainty")),
                warnings=_string_list(record.get("warnings")),
                errors=_error_list(record.get("errors")),
                source_artifacts=[OUTCOME_EVALUATIONS_ARTIFACT, *_string_list(record.get("source_artifacts"))],
                extra={
                    "evaluation_status": _text(record.get("evaluation_status")),
                    "outcome_state": _text(record.get("outcome_state")),
                },
            )

    def _load_data_quality(self) -> None:
        artifact = self._read(
            "data_quality",
            DATA_QUALITY_SUMMARY_ARTIFACT,
            self.run.analysis_dir / "data_quality_summary.json",
            "checks",
        )
        if artifact is None:
            return
        counts = _dict(artifact.data.get("counts"))
        status = _text(artifact.data.get("status"))
        self._add(
            _global_scope(),
            "data_quality",
            DATA_QUALITY_SUMMARY_ARTIFACT,
            "data_quality_summary",
            state=status,
            direction="cautionary" if status in {"warning", "degraded", "failed"} else "neutral",
            confidence="medium",
            evidence=[
                "data_quality status="
                + status
                + f" warnings={_int(counts.get('warnings'))} errors={_int(counts.get('errors'))}"
            ],
            uncertainty=_string_list(artifact.data.get("warnings")),
            warnings=_string_list(artifact.data.get("warnings")),
            errors=_error_list(artifact.data.get("errors")),
            source_artifacts=[DATA_QUALITY_SUMMARY_ARTIFACT, *_string_list(artifact.data.get("source_artifacts"))],
        )

    def _read(self, source_layer: str, artifact: str, path: Path, records_key: str) -> "_LoadedArtifact | None":
        data, error = _read_json(path)
        if error:
            self.coverage.append(
                _coverage_record(source_layer, artifact, "missing", records=0, warnings=[error])
            )
            self.source_artifacts.append(artifact)
            return None
        records = data.get(records_key)
        if not isinstance(records, list):
            self.coverage.append(
                _coverage_record(
                    source_layer,
                    artifact,
                    "failed",
                    records=0,
                    errors=[f"{artifact} must contain a {records_key} list."],
                )
            )
            self.source_artifacts.append(artifact)
            return None
        status = _coverage_status(_text(data.get("status")), records)
        self.coverage.append(
            _coverage_record(
                source_layer,
                artifact,
                status,
                records=len(records),
                warnings=_string_list(data.get("warnings")),
                errors=_error_list(data.get("errors")),
            )
        )
        self.source_artifacts.extend([artifact, *_string_list(data.get("source_artifacts"))])
        return _LoadedArtifact(data)

    def _read_optional(self, source_layer: str, artifact: str, path: Path, records_key: str) -> "_LoadedArtifact | None":
        data, error = _read_json(path)
        if error:
            status = "missing" if "was not found" in error else "failed"
            self.coverage.append(
                _coverage_record(
                    source_layer,
                    artifact,
                    status,
                    records=0,
                    errors=[error] if status == "failed" else [],
                )
            )
            self.source_artifacts.append(artifact)
            return None
        records = data.get(records_key)
        if not isinstance(records, list):
            self.coverage.append(
                _coverage_record(
                    source_layer,
                    artifact,
                    "failed",
                    records=0,
                    errors=[f"{artifact} must contain a {records_key} list."],
                )
            )
            self.source_artifacts.append(artifact)
            return None
        status = _coverage_status(_text(data.get("status")), records)
        self.coverage.append(
            _coverage_record(
                source_layer,
                artifact,
                status,
                records=len(records),
                warnings=_string_list(data.get("warnings")),
                errors=_error_list(data.get("errors")),
            )
        )
        self.source_artifacts.extend([artifact, *_string_list(data.get("source_artifacts"))])
        return _LoadedArtifact(data)

    def _add(
        self,
        scope: tuple[tuple[str, str | None], ...],
        source_layer: str,
        source_artifact: str,
        source_record_id: str | None,
        *,
        state: str,
        direction: str,
        confidence: str,
        evidence: list[str],
        uncertainty: list[str],
        warnings: list[str],
        errors: list[dict[str, Any]],
        source_artifacts: list[str],
        extra: dict[str, Any] | None = None,
    ) -> None:
        source_record = {
            "source_layer": source_layer,
            "source_artifact": source_artifact,
            "source_record_id": source_record_id,
            "state": state or "unknown",
            "direction": direction or "unknown",
            "confidence": confidence or "unknown",
            "evidence": evidence,
            "uncertainty": uncertainty,
            "warnings": warnings,
            "errors": errors,
            "source_artifacts": _unique_sorted(source_artifacts),
            "extra": extra or {},
        }
        self.records_by_scope.setdefault(scope, []).append(source_record)
        self.source_artifacts.extend(source_record["source_artifacts"])


class _LoadedArtifact:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


def _fusion_record(
    scope: tuple[tuple[str, str | None], ...],
    source_records: list[dict[str, Any]],
    *,
    created_at: str,
) -> dict[str, Any]:
    source_records = sorted(
        source_records,
        key=lambda item: (item["source_layer"], item["source_artifact"], item.get("source_record_id") or ""),
    )
    supporting = _supporting_records(source_records)
    cautionary = _cautionary_records(source_records)
    conflicting = _conflicting_records(source_records)
    degraded = _degraded_records(source_records)
    insufficient = _insufficient_records(source_records)
    failed = [record for record in source_records if record["errors"] or record["state"] == "failed"]
    risk_override = _risk_override(source_records)
    event_override = _event_override(source_records)
    outcome_feedback = _outcome_feedback(source_records)
    conflict = _conflict_state(supporting, cautionary, conflicting)
    confluence = _confluence_state(supporting, cautionary, degraded)
    state = _fusion_state(
        supporting=supporting,
        cautionary=cautionary,
        conflicting=conflicting,
        degraded=degraded,
        insufficient=insufficient,
        failed=failed,
        risk_override=risk_override,
        event_override=event_override,
    )
    evidence = _bounded_strings(
        [
            *_evidence_summary("support", supporting),
            *_evidence_summary("caution", cautionary),
            *_evidence_summary("conflict", conflicting),
            *_override_reasons("risk", risk_override),
            *_override_reasons("event", event_override),
            *_outcome_reasons(outcome_feedback),
        ],
        limit=12,
    )
    uncertainty = _bounded_strings(
        [
            *(item for record in source_records for item in _string_list(record.get("uncertainty"))),
            *(f"{record['source_layer']} degraded: {record['state']}" for record in degraded),
            *(f"{record['source_layer']} insufficient: {record['state']}" for record in insufficient),
        ],
        limit=12,
    )
    warnings = _bounded_strings(
        [item for record in source_records for item in _string_list(record.get("warnings"))],
        limit=12,
    )
    errors = [error for record in source_records for error in _error_list(record.get("errors"))]
    return {
        "fusion_record_id": "fusion:" + _scope_key(scope),
        "scope": _scope_dict(scope),
        "state": state,
        "direction": _fusion_direction(source_records, state=state),
        "confidence": _fusion_confidence(state, supporting=supporting, uncertainty=uncertainty),
        "confluence": {
            "state": confluence,
            "supporting_sources": len(supporting),
            "independent_sources": len({record["source_layer"] for record in supporting}),
            "source_layers": sorted({record["source_layer"] for record in supporting}),
        },
        "conflict": {
            "state": conflict,
            "conflicting_sources": len(conflicting) + (len(cautionary) if supporting and cautionary else 0),
            "source_layers": sorted({record["source_layer"] for record in [*conflicting, *cautionary]}),
        },
        "risk_override": risk_override,
        "event_override": event_override,
        "outcome_feedback": outcome_feedback,
        "evidence": evidence,
        "uncertainty": uncertainty,
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _unique_sorted(
            [artifact for record in source_records for artifact in _string_list(record.get("source_artifacts"))]
        ),
        "source_record_refs": _source_record_refs(source_records),
        "created_at": created_at,
    }


def _empty_record(created_at: str, coverage: list[dict[str, Any]]) -> dict[str, Any]:
    missing_layers = sorted({record["source_layer"] for record in coverage if record["status"] in {"missing", "failed"}})
    return {
        "fusion_record_id": "fusion:global",
        "scope": _scope_dict(_global_scope()),
        "state": "insufficient_evidence",
        "direction": "unknown",
        "confidence": "low",
        "confluence": {"state": "none", "supporting_sources": 0, "independent_sources": 0, "source_layers": []},
        "conflict": {"state": "unknown", "conflicting_sources": 0, "source_layers": []},
        "risk_override": {"state": "unknown", "risk_level": "unknown", "reasons": []},
        "event_override": {"state": "unknown", "severity": "unknown", "reasons": []},
        "outcome_feedback": {"state": "insufficient_evidence", "source_records": 0},
        "evidence": [],
        "uncertainty": [f"Missing fusion input layer: {layer}" for layer in missing_layers],
        "warnings": ["No source records were available for intelligence fusion."],
        "errors": [],
        "source_artifacts": _unique_sorted([record["source_artifact"] for record in coverage]),
        "source_record_refs": [],
        "created_at": created_at,
    }


def _supporting_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for record in records:
        state = record["state"]
        direction = record["direction"]
        extra = _dict(record.get("extra"))
        if state in {"supportive", "effective", "confirmed", "favorable"}:
            values.append(record)
        elif direction in {"bullish", "supportive", "trend_up"}:
            values.append(record)
        elif record["source_layer"] == "risk" and extra.get("risk_level") in {"low", "medium"} and not extra.get("blocking_risks"):
            values.append(record)
    return values


def _cautionary_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for record in records:
        state = record["state"]
        direction = record["direction"]
        extra = _dict(record.get("extra"))
        if state in {"cautionary", "watchlisted", "adverse", "contradicted"}:
            values.append(record)
        elif direction in {"bearish", "cautionary", "risk_up"}:
            values.append(record)
        elif record["source_layer"] == "risk" and extra.get("risk_level") in {"high", "extreme"}:
            values.append(record)
        elif record["source_layer"] == "alert" and extra.get("priority") in {"P0", "P1", "P2"}:
            values.append(record)
    return values


def _conflicting_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record["state"] == "conflicting" or record["direction"] == "conflicting"]


def _degraded_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record["state"] in {"degraded", "stale", "warning"} or record["warnings"]]


def _insufficient_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if record["state"] in {"insufficient_evidence", "insufficient_data", "missing", "skipped", "unavailable", "unknown"}
    ]


def _risk_override(records: list[dict[str, Any]]) -> dict[str, Any]:
    risk_records = [record for record in records if record["source_layer"] == "risk"]
    risk_level = "unknown"
    reasons: list[str] = []
    state = "none"
    for record in risk_records:
        extra = _dict(record.get("extra"))
        level = _text(extra.get("risk_level"))
        if _risk_rank(level) > _risk_rank(risk_level):
            risk_level = level
        reasons.extend(_string_list(extra.get("blocking_risks")))
        if level == "extreme" or extra.get("cap_action_level") == "NO_ACTION":
            state = "block"
        elif state != "block" and (level == "high" or extra.get("blocking_risks")):
            state = "downgrade"
    return {"state": state if risk_records else "unknown", "risk_level": risk_level, "reasons": _bounded_strings(reasons, limit=6)}


def _event_override(records: list[dict[str, Any]]) -> dict[str, Any]:
    event_records = [record for record in records if record["source_layer"] in {"event", "alert"}]
    severity = "unknown"
    reasons: list[str] = []
    state = "none"
    for record in event_records:
        extra = _dict(record.get("extra"))
        current_severity = _text(extra.get("event_severity"))
        if _severity_rank(current_severity) > _severity_rank(severity):
            severity = current_severity
        decision_impact = _text(extra.get("decision_impact"))
        risk_effect = _text(extra.get("risk_effect"))
        priority = _text(extra.get("priority"))
        reasons.extend(_string_list(extra.get("downgrade_reasons")))
        if decision_impact == "could_invalidate" or priority == "P0":
            state = "block"
        elif state != "block" and (
            decision_impact == "could_downgrade" or risk_effect == "risk_up" or priority in {"P1", "P2"}
        ):
            state = "downgrade"
        elif state == "none" and priority in {"P3", "no_alert"}:
            state = "watch"
    return {"state": state if event_records else "unknown", "severity": severity, "reasons": _bounded_strings(reasons, limit=6)}


def _outcome_feedback(records: list[dict[str, Any]]) -> dict[str, Any]:
    outcome_records = [record for record in records if record["source_layer"] == "outcome"]
    if not outcome_records:
        return {"state": "unknown", "source_records": 0}
    supportive = [record for record in outcome_records if record["direction"] == "supportive"]
    cautionary = [record for record in outcome_records if record["direction"] == "cautionary"]
    insufficient = [record for record in outcome_records if record["direction"] == "unknown"]
    if supportive and cautionary:
        state = "mixed"
    elif cautionary:
        state = "cautionary"
    elif supportive:
        state = "supportive"
    elif insufficient:
        state = "insufficient_evidence"
    else:
        state = "unknown"
    return {"state": state, "source_records": len(outcome_records)}


def _conflict_state(
    supporting: list[dict[str, Any]],
    cautionary: list[dict[str, Any]],
    conflicting: list[dict[str, Any]],
) -> str:
    if conflicting:
        return "severe"
    if supporting and cautionary:
        return "material"
    if cautionary:
        return "minor"
    return "none"


def _confluence_state(
    supporting: list[dict[str, Any]],
    cautionary: list[dict[str, Any]],
    degraded: list[dict[str, Any]],
) -> str:
    independent = {record["source_layer"] for record in supporting}
    if len(independent) >= 2 and not cautionary and not degraded:
        return "aligned"
    if supporting:
        return "partial"
    return "none"


def _fusion_state(
    *,
    supporting: list[dict[str, Any]],
    cautionary: list[dict[str, Any]],
    conflicting: list[dict[str, Any]],
    degraded: list[dict[str, Any]],
    insufficient: list[dict[str, Any]],
    failed: list[dict[str, Any]],
    risk_override: dict[str, Any],
    event_override: dict[str, Any],
) -> str:
    if failed:
        return "failed"
    if risk_override["state"] == "block":
        return "risk_blocked"
    if event_override["state"] == "block":
        return "event_overridden"
    if conflicting or (supporting and cautionary):
        return "conflicting"
    if risk_override["state"] == "downgrade" or event_override["state"] == "downgrade":
        return "cautionary"
    if degraded and not supporting:
        return "degraded"
    if insufficient and not supporting and not cautionary:
        return "insufficient_evidence"
    if supporting:
        return "supportive"
    if cautionary:
        return "cautionary"
    if degraded:
        return "degraded"
    return "neutral"


def _fusion_direction(records: list[dict[str, Any]], *, state: str) -> str:
    if state in {"risk_blocked", "event_overridden", "conflicting"}:
        return "mixed" if state == "conflicting" else "unknown"
    directions = [record["direction"] for record in records if record["direction"] not in {"unknown", "neutral"}]
    bullish = sum(1 for direction in directions if direction in {"bullish", "supportive", "trend_up"})
    bearish = sum(1 for direction in directions if direction in {"bearish", "cautionary", "risk_up"})
    if bullish and bearish:
        return "mixed"
    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "neutral" if state == "neutral" else "unknown"


def _fusion_confidence(state: str, *, supporting: list[dict[str, Any]], uncertainty: list[str]) -> str:
    if state in {"failed", "insufficient_evidence"}:
        return "low"
    independent = {record["source_layer"] for record in supporting}
    if state == "supportive" and len(independent) >= 3 and not uncertainty:
        return "high"
    if state in {"supportive", "cautionary", "neutral"}:
        return "medium"
    return "low"


def _evidence_summary(label: str, records: list[dict[str, Any]]) -> list[str]:
    return [_source_evidence_summary(label, record) for record in records[:6]]


def _source_evidence_summary(label: str, record: dict[str, Any]) -> str:
    summary = f"{label}: {record['source_layer']} state={record['state']} direction={record['direction']}"
    if record["source_layer"] != "strategy_lifecycle":
        return summary
    extra = _dict(record.get("extra"))
    details = [
        f"lifecycle_status={extra.get('lifecycle_status') or record['state']}",
        f"health_state={extra.get('health_state') or 'unknown'}",
    ]
    degradation_state = _text(extra.get("degradation_state"))
    if degradation_state not in {"", "none", "unknown"}:
        details.append(f"degradation_state={degradation_state}")
    retirement_state = _text(extra.get("retirement_state"))
    if retirement_state not in {"", "not_retired", "unknown"}:
        details.append(f"retirement_state={retirement_state}")
    return summary + " " + " ".join(details)


def _override_reasons(label: str, override: dict[str, Any]) -> list[str]:
    state = override.get("state")
    if state in {None, "none", "unknown"}:
        return []
    reasons = _string_list(override.get("reasons"))
    if reasons:
        return [f"{label}_override={state}: {reason}" for reason in reasons]
    return [f"{label}_override={state}"]


def _outcome_reasons(outcome: dict[str, Any]) -> list[str]:
    state = outcome.get("state")
    if state in {None, "unknown"}:
        return []
    return [f"outcome_feedback={state} records={outcome.get('source_records')}"]


def _source_record_refs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    for record in records:
        ref = {
            "source_layer": record["source_layer"],
            "source_artifact": record["source_artifact"],
            "source_record_id": record.get("source_record_id"),
        }
        if ref not in refs:
            refs.append(ref)
    return refs


def _coverage_record(
    source_layer: str,
    artifact: str,
    status: str,
    *,
    records: int,
    warnings: list[str] | None = None,
    errors: list[dict[str, Any]] | list[str] | None = None,
) -> dict[str, Any]:
    return {
        "source_layer": source_layer,
        "source_artifact": artifact,
        "status": status,
        "records": records,
        "warnings": _unique_sorted(warnings or []),
        "errors": _error_list(errors),
    }


def _coverage_status(status: str, records: list[Any]) -> str:
    if status == "failed":
        return "failed"
    if status in {"warning", "degraded", "stale"}:
        return "degraded"
    if records:
        return "used"
    if status in {"skipped", "unavailable"}:
        return status
    return "missing"


def _artifact_status(records: list[dict[str, Any]], *, warnings: list[str], errors: list[dict[str, Any]]) -> str:
    if errors or any(record["state"] == "failed" for record in records):
        return "failed"
    if any(record["state"] in {"risk_blocked", "event_overridden", "conflicting", "degraded"} for record in records):
        return "warning"
    if warnings:
        return "warning"
    if records and all(record["state"] == "insufficient_evidence" for record in records):
        return "skipped"
    return "ok"


def _counts(records: list[dict[str, Any]], *, warnings: list[str], errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "records": len(records),
        "state_counts": {state: _record_state_count(records, state) for state in STATE_ORDER},
        "confluence_counts": _nested_state_counts(records, "confluence"),
        "conflict_counts": _nested_state_counts(records, "conflict"),
        "risk_override_counts": _nested_state_counts(records, "risk_override"),
        "event_override_counts": _nested_state_counts(records, "event_override"),
        "outcome_feedback_counts": _nested_state_counts(records, "outcome_feedback"),
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _record_manifest(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = _dict(artifact.get("counts"))
    state_counts = _dict(counts.get("state_counts"))
    run.manifest["artifacts"]["intelligence_fusion"] = INTELLIGENCE_FUSION_ARTIFACT
    run.manifest["intelligence_fusion"] = {
        "status": artifact["status"],
        "artifact": INTELLIGENCE_FUSION_ARTIFACT,
        "records": _int(counts.get("records")),
        "state_counts": state_counts,
        "confluence_counts": _dict(counts.get("confluence_counts")),
        "conflict_counts": _dict(counts.get("conflict_counts")),
        "risk_override_counts": _dict(counts.get("risk_override_counts")),
        "event_override_counts": _dict(counts.get("event_override_counts")),
        "outcome_feedback_counts": _dict(counts.get("outcome_feedback_counts")),
        "warnings": _int(counts.get("warnings")),
        "errors": _int(counts.get("errors")),
    }
    run.manifest["counts"]["intelligence_fusion_records"] = _int(counts.get("records"))
    run.manifest["counts"]["intelligence_fusion_warnings"] = _int(counts.get("warnings"))
    run.manifest["counts"]["intelligence_fusion_errors"] = _int(counts.get("errors"))
    for state, count in state_counts.items():
        run.manifest["counts"][f"intelligence_fusion_{state}_records"] = count


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must contain a JSON object."
    return loaded, None


def _scope_from_fields(symbol: Any, timeframe: Any) -> tuple[tuple[str, str | None], ...]:
    return _scope_tuple({"symbol": symbol, "timeframe": timeframe})


def _scope_tuple(value: Any) -> tuple[tuple[str, str | None], ...]:
    scope = value if isinstance(value, dict) else {}
    return tuple(
        (key, _text_or_none(scope.get(key)))
        for key in ("symbol", "timeframe", "asset", "chain", "region")
    )


def _global_scope() -> tuple[tuple[str, str | None], ...]:
    return _scope_tuple({})


def _scope_dict(scope: tuple[tuple[str, str | None], ...]) -> dict[str, str | None]:
    return {key: value for key, value in scope}


def _scope_key(scope: tuple[tuple[str, str | None], ...]) -> str:
    values = [value for _, value in scope if value]
    return ":".join(_slug(value) for value in values) or "global"


def _scope_sort_key(scope: tuple[tuple[str, str | None], ...]) -> tuple[str, ...]:
    return tuple(value or "" for _, value in scope)


def _slug(value: str) -> str:
    return value.strip().lower().replace("/", "_").replace(" ", "_") or "unknown"


def _direction_from_regime(regime: str) -> str:
    if regime in {"trend_up", "risk_on"}:
        return "bullish"
    if regime in {"trend_down", "risk_off"}:
        return "bearish"
    if regime == "mixed":
        return "conflicting"
    return "neutral" if regime else "unknown"


def _direction_from_event(record: dict[str, Any]) -> str:
    impact = _text(record.get("decision_impact"))
    risk_effect = _text(record.get("risk_effect"))
    if impact == "supports_existing_view" and risk_effect in {"neutral", "risk_down"}:
        return "supportive"
    if impact in {"could_invalidate", "could_downgrade"} or risk_effect == "risk_up":
        return "cautionary"
    return "unknown"


def _direction_from_outcome(record: dict[str, Any]) -> str:
    state = _text(record.get("outcome_state"))
    if state in {"favorable", "confirmed", "aligned"}:
        return "supportive"
    if state in {"adverse", "contradicted", "misaligned"}:
        return "cautionary"
    return "unknown"


def _direction_from_lifecycle(record: dict[str, Any]) -> str:
    status = _text(record.get("lifecycle_status"))
    if status == "effective":
        return "supportive"
    if status in {"watchlisted", "rejected", "degraded", "retired"}:
        return "cautionary"
    if status in {"active_candidate", "insufficient_evidence", "failed"}:
        return "unknown"
    return "unknown"


def _lifecycle_evidence(record: dict[str, Any]) -> list[str]:
    health = _dict(record.get("health_state"))
    degradation = _dict(record.get("degradation"))
    retirement = _dict(record.get("retirement"))
    evidence = [
        "strategy_lifecycle_status="
        + (_text(record.get("lifecycle_status")) or "unknown")
        + " health_state="
        + (_text(health.get("state")) or "unknown")
        + "."
    ]
    degradation_state = _text(degradation.get("state"))
    if degradation_state not in {"", "none", "unknown"}:
        evidence.append(f"strategy_lifecycle_degradation_state={degradation_state}.")
    retirement_state = _text(retirement.get("state"))
    if retirement_state not in {"", "not_retired", "unknown"}:
        evidence.append(f"strategy_lifecycle_retirement_state={retirement_state}.")
    return _unique_sorted([*evidence, *_string_list(record.get("evidence"))])


def _reason_text(value: dict[str, Any]) -> str:
    code = _text(value.get("code"))
    message = _text(value.get("message"))
    if code and message:
        return f"{code}: {message}"
    return code or message


def _risk_rank(value: str) -> int:
    return {"unknown": 0, "low": 1, "medium": 2, "high": 3, "extreme": 4}.get(value, 0)


def _severity_rank(value: str) -> int:
    return {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(value, 0)


def _nested_state_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = _dict(record.get(key)).get("state")
        state = _text(value) or "unknown"
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def _record_state_count(records: list[dict[str, Any]], state: str) -> int:
    return sum(1 for record in records if record.get("state") == state)


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    errors = []
    for item in value:
        if isinstance(item, dict):
            message = item.get("message")
            errors.append({"message": str(message) if message else str(item)})
        elif isinstance(item, str) and item:
            errors.append({"message": item})
    return errors


def _bounded_strings(values: list[str], *, limit: int) -> list[str]:
    cleaned = []
    for value in values:
        if not value:
            continue
        if value not in cleaned:
            cleaned.append(value)
        if len(cleaned) >= limit:
            break
    return cleaned


def _text(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    return text if text else "unknown"


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("created_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("created_at must include a UTC offset.")
        timestamp = parsed.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("created_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})
