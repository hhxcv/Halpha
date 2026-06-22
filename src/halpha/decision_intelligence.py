from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from .decision_material import (
    decision_material_record_count,
    render_decision_intelligence_material,
    validate_decision_material_inputs,
)
from .decision_delta import build_decision_intelligence_delta_artifact
from .pipeline import PipelineError, RunContext
from .storage import write_json


BUILD_MARKET_REGIME_ASSESSMENT_STAGE = "build_market_regime_assessment"
BUILD_RISK_ASSESSMENT_STAGE = "build_risk_assessment"
BUILD_DECISION_RECOMMENDATIONS_STAGE = "build_decision_recommendations"
BUILD_WATCH_TRIGGERS_STAGE = "build_watch_triggers"
BUILD_DECISION_INTELLIGENCE_DELTA_STAGE = "build_decision_intelligence_delta"
BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE = "build_decision_intelligence_material"
MARKET_REGIME_ASSESSMENT_ARTIFACT = "analysis/market_regime_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
DECISION_INTELLIGENCE_DELTA_ARTIFACT = "analysis/decision_intelligence_delta.json"
DECISION_INTELLIGENCE_MATERIAL_ARTIFACT = "analysis/decision_intelligence_material.md"
MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
MARKET_STRATEGY_SIGNALS_ARTIFACT = "analysis/market_strategy_signals.json"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
MARKET_DATA_VIEWS_ARTIFACT = "raw/market_data_views.json"
DERIVATIVES_MARKET_CONTEXT_ARTIFACT = "analysis/derivatives_market_context.json"
MACRO_CALENDAR_CONTEXT_ARTIFACT = "analysis/macro_calendar_context.json"
ONCHAIN_FLOW_CONTEXT_ARTIFACT = "analysis/onchain_flow_context.json"
SCHEMA_VERSION = 1
ACTION_TAXONOMY = (
    "STRONG_DO",
    "DO",
    "TRY_SMALL",
    "WATCH",
    "AVOID",
    "EXIT_OR_REDUCE",
    "HEDGE_OR_PROTECT",
    "NO_ACTION",
)
ACTIONABLE_ACTION_LEVELS = {
    "STRONG_DO",
    "DO",
    "TRY_SMALL",
    "AVOID",
    "EXIT_OR_REDUCE",
    "HEDGE_OR_PROTECT",
}
TRIGGER_TYPES = (
    "confirmation",
    "invalidation",
    "risk_escalation",
    "risk_relief",
    "wait_condition",
    "recheck_next_run",
)


def build_market_regime_assessment(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        run.manifest["counts"]["market_regime_records"] = 0
        run.manifest["counts"]["market_regime_unknown_records"] = 0
        run.manifest["counts"]["market_regime_derivatives_context_records"] = 0
        run.manifest["counts"]["market_regime_derivatives_influenced_records"] = 0
        return []

    market_signals = _read_json_artifact(
        run.analysis_dir / "market_signals.json",
        MARKET_SIGNALS_ARTIFACT,
        producer_stage="build_market_signals",
        stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
    )
    signals = _signals_from_artifact(market_signals, stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE)
    created_at = _created_at(market_signals, now)
    strategy_artifact, strategy_warnings = _read_optional_strategy_artifact(
        run,
        market_signals,
        stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
    )
    derivatives_artifact, derivatives_warnings = _read_optional_derivatives_context(run)
    derivatives_records = _records_from_optional_artifact(derivatives_artifact)
    derivatives_groups = _derivatives_by_symbol(derivatives_records)
    records = [
        _regime_record(group_signals, derivatives_groups.get(_group_value(group_signals, "symbol"), []))
        for group_signals in _grouped_signals(signals).values()
    ]
    warnings = _artifact_warnings(records, [*strategy_warnings, *derivatives_warnings])

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "market_regime_assessment",
        "run_id": run.run_id,
        "created_at": created_at,
        "source_artifacts": _source_artifacts(market_signals, strategy_artifact, derivatives_artifact),
        "records": records,
        "warnings": warnings,
        "errors": [],
    }
    write_json(run.analysis_dir / "market_regime_assessment.json", artifact)
    run.manifest["artifacts"]["market_regime_assessment"] = MARKET_REGIME_ASSESSMENT_ARTIFACT
    run.manifest["counts"]["market_regime_records"] = len(records)
    run.manifest["counts"]["market_regime_unknown_records"] = sum(
        1 for record in records if record["regime"] == "unknown"
    )
    run.manifest["counts"]["market_regime_derivatives_context_records"] = len(derivatives_records)
    run.manifest["counts"]["market_regime_derivatives_influenced_records"] = sum(
        1 for record in records if any("derivatives_context" in item for item in _string_list(record.get("evidence")))
    )
    return [MARKET_REGIME_ASSESSMENT_ARTIFACT]


def build_risk_assessment(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        _record_zero_risk_counts(run)
        return []

    market_signals = _read_json_artifact(
        run.analysis_dir / "market_signals.json",
        MARKET_SIGNALS_ARTIFACT,
        producer_stage="build_market_signals",
        stage=BUILD_RISK_ASSESSMENT_STAGE,
    )
    market_regime = _read_json_artifact(
        run.analysis_dir / "market_regime_assessment.json",
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        producer_stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
        stage=BUILD_RISK_ASSESSMENT_STAGE,
    )
    signals = _signals_from_artifact(market_signals, stage=BUILD_RISK_ASSESSMENT_STAGE)
    regime_records = _records_from_artifact(
        market_regime,
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        stage=BUILD_RISK_ASSESSMENT_STAGE,
    )
    strategy_artifact, strategy_warnings = _read_optional_strategy_artifact(
        run,
        market_signals,
        stage=BUILD_RISK_ASSESSMENT_STAGE,
    )
    strategy_runs, run_warnings = _strategy_runs_from_optional_artifact(strategy_artifact)
    derivatives_artifact, derivatives_warnings = _read_optional_derivatives_context(run)
    macro_artifact, macro_warnings = _read_optional_macro_calendar_context(run)
    onchain_artifact, onchain_warnings = _read_optional_onchain_flow_context(run)
    derivatives_records = _records_from_optional_artifact(derivatives_artifact)
    derivatives_groups = _derivatives_by_symbol(derivatives_records)
    macro_records = _records_from_optional_artifact(macro_artifact)
    macro_groups = _macro_calendar_context_by_symbol(macro_records)
    onchain_records = _records_from_optional_artifact(onchain_artifact)
    created_at = _created_at(market_regime, now)
    signal_groups = _signals_by_tuple(signals)
    regime_groups = _regime_by_tuple(regime_records)
    strategy_groups = _strategy_runs_by_tuple(strategy_runs)
    records = [
        _risk_record(
            key,
            signal_groups.get(key, []),
            regime_groups.get(key),
            strategy_groups.get(key, []),
            derivatives_groups.get(key[1], []),
            _macro_calendar_records_for_symbol(macro_groups, key[1]),
            _onchain_flow_records_for_symbol(onchain_records, key[1]),
        )
        for key in _risk_group_keys(signals, regime_records, strategy_runs)
    ]

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "risk_assessment",
        "run_id": run.run_id,
        "created_at": created_at,
        "source_artifacts": _risk_source_artifacts(
            market_signals,
            market_regime,
            strategy_artifact,
            derivatives_artifact,
            macro_artifact,
            onchain_artifact,
        ),
        "records": records,
        "warnings": _risk_artifact_warnings(
            records,
            [*strategy_warnings, *run_warnings, *derivatives_warnings, *macro_warnings, *onchain_warnings],
        ),
        "errors": [],
    }
    write_json(run.analysis_dir / "risk_assessment.json", artifact)
    run.manifest["artifacts"]["risk_assessment"] = RISK_ASSESSMENT_ARTIFACT
    run.manifest["counts"]["risk_assessment_records"] = len(records)
    run.manifest["counts"]["risk_assessment_unknown_records"] = sum(
        1 for record in records if record["risk_level"] == "unknown"
    )
    run.manifest["counts"]["risk_assessment_high_or_extreme_records"] = sum(
        1 for record in records if record["risk_level"] in {"high", "extreme"}
    )
    run.manifest["counts"]["risk_assessment_blocking_records"] = sum(
        1 for record in records if record["blocking_risks"]
    )
    run.manifest["counts"]["risk_assessment_derivatives_context_records"] = len(derivatives_records)
    run.manifest["counts"]["risk_assessment_derivatives_influenced_records"] = sum(
        1 for record in records if any("Derivatives context" in item for item in _string_list(record.get("rising_risks")))
    )
    run.manifest["counts"]["risk_assessment_macro_calendar_context_records"] = len(macro_records)
    run.manifest["counts"]["risk_assessment_macro_calendar_influenced_records"] = sum(
        1
        for record in records
        if any("Macro calendar context" in item for item in _string_list(record.get("rising_risks")))
    )
    run.manifest["counts"]["risk_assessment_onchain_flow_context_records"] = len(onchain_records)
    run.manifest["counts"]["risk_assessment_onchain_flow_influenced_records"] = sum(
        1
        for record in records
        if any("On-chain flow context" in item for item in _string_list(record.get("rising_risks")))
    )
    return [RISK_ASSESSMENT_ARTIFACT]


def build_decision_recommendations(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        _record_zero_decision_recommendation_counts(run)
        return []

    market_signals = _read_json_artifact(
        run.analysis_dir / "market_signals.json",
        MARKET_SIGNALS_ARTIFACT,
        producer_stage="build_market_signals",
        stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
    )
    market_regime = _read_json_artifact(
        run.analysis_dir / "market_regime_assessment.json",
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        producer_stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
        stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
    )
    risk_assessment = _read_json_artifact(
        run.analysis_dir / "risk_assessment.json",
        RISK_ASSESSMENT_ARTIFACT,
        producer_stage=BUILD_RISK_ASSESSMENT_STAGE,
        stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
    )
    signals = _signals_from_artifact(market_signals, stage=BUILD_DECISION_RECOMMENDATIONS_STAGE)
    regime_records = _records_from_artifact(
        market_regime,
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
    )
    risk_records = _records_from_artifact(
        risk_assessment,
        RISK_ASSESSMENT_ARTIFACT,
        stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
    )
    strategy_artifact, strategy_warnings = _read_optional_strategy_artifact(
        run,
        market_signals,
        stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
    )
    derivatives_artifact, derivatives_warnings = _read_optional_derivatives_context(run)
    macro_artifact, macro_warnings = _read_optional_macro_calendar_context(run)
    onchain_artifact, onchain_warnings = _read_optional_onchain_flow_context(run)
    derivatives_records = _records_from_optional_artifact(derivatives_artifact)
    derivatives_groups = _derivatives_by_symbol(derivatives_records)
    macro_records = _records_from_optional_artifact(macro_artifact)
    macro_groups = _macro_calendar_context_by_symbol(macro_records)
    onchain_records = _records_from_optional_artifact(onchain_artifact)
    created_at = _created_at(risk_assessment, now)
    signal_groups = _signals_by_tuple(signals)
    regime_groups = _regime_by_tuple(regime_records)
    risk_groups = _risk_by_tuple(risk_records)
    records = [
        _decision_recommendation_record(
            key,
            signal_groups.get(key, []),
            regime_groups.get(key),
            risk_groups.get(key),
            derivatives_groups.get(key[1], []),
            _macro_calendar_records_for_symbol(macro_groups, key[1]),
            _onchain_flow_records_for_symbol(onchain_records, key[1]),
        )
        for key in _decision_group_keys(signals, regime_records, risk_records)
    ]

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "decision_recommendations",
        "run_id": run.run_id,
        "created_at": created_at,
        "action_taxonomy": list(ACTION_TAXONOMY),
        "source_artifacts": _decision_source_artifacts(
            market_signals,
            market_regime,
            risk_assessment,
            strategy_artifact,
            derivatives_artifact,
            macro_artifact,
            onchain_artifact,
        ),
        "records": records,
        "warnings": _decision_artifact_warnings(
            records,
            [*strategy_warnings, *derivatives_warnings, *macro_warnings, *onchain_warnings],
        ),
        "errors": [],
    }
    write_json(run.analysis_dir / "decision_recommendations.json", artifact)
    run.manifest["artifacts"]["decision_recommendations"] = DECISION_RECOMMENDATIONS_ARTIFACT
    run.manifest["counts"]["decision_recommendation_records"] = len(records)
    run.manifest["counts"]["decision_recommendation_actionable_records"] = sum(
        1 for record in records if record["action_level"] in ACTIONABLE_ACTION_LEVELS
    )
    run.manifest["counts"]["decision_recommendation_non_actionable_records"] = sum(
        1 for record in records if record["action_level"] not in ACTIONABLE_ACTION_LEVELS
    )
    run.manifest["counts"]["decision_recommendation_risk_blocked_records"] = sum(
        1
        for record in records
        if any(condition.startswith(("risk_level=high", "risk_level=extreme")) for condition in record["risk_conditions"])
    )
    run.manifest["counts"]["decision_recommendation_derivatives_context_records"] = len(derivatives_records)
    run.manifest["counts"]["decision_recommendation_derivatives_linked_records"] = sum(
        1 for record in records if record.get("linked_derivatives_context_ids")
    )
    run.manifest["counts"]["decision_recommendation_macro_calendar_context_records"] = len(macro_records)
    run.manifest["counts"]["decision_recommendation_macro_calendar_linked_records"] = sum(
        1 for record in records if record.get("linked_macro_calendar_context_ids")
    )
    run.manifest["counts"]["decision_recommendation_onchain_flow_context_records"] = len(onchain_records)
    run.manifest["counts"]["decision_recommendation_onchain_flow_linked_records"] = sum(
        1 for record in records if record.get("linked_onchain_flow_context_ids")
    )
    return [DECISION_RECOMMENDATIONS_ARTIFACT]


def build_watch_triggers(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        _record_zero_watch_trigger_counts(run)
        return []

    market_signals = _read_json_artifact(
        run.analysis_dir / "market_signals.json",
        MARKET_SIGNALS_ARTIFACT,
        producer_stage="build_market_signals",
        stage=BUILD_WATCH_TRIGGERS_STAGE,
    )
    market_regime = _read_json_artifact(
        run.analysis_dir / "market_regime_assessment.json",
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        producer_stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
        stage=BUILD_WATCH_TRIGGERS_STAGE,
    )
    risk_assessment = _read_json_artifact(
        run.analysis_dir / "risk_assessment.json",
        RISK_ASSESSMENT_ARTIFACT,
        producer_stage=BUILD_RISK_ASSESSMENT_STAGE,
        stage=BUILD_WATCH_TRIGGERS_STAGE,
    )
    decision_recommendations = _read_json_artifact(
        run.analysis_dir / "decision_recommendations.json",
        DECISION_RECOMMENDATIONS_ARTIFACT,
        producer_stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
        stage=BUILD_WATCH_TRIGGERS_STAGE,
    )
    signals = _signals_from_artifact(market_signals, stage=BUILD_WATCH_TRIGGERS_STAGE)
    regime_records = _records_from_artifact(
        market_regime,
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        stage=BUILD_WATCH_TRIGGERS_STAGE,
    )
    risk_records = _records_from_artifact(
        risk_assessment,
        RISK_ASSESSMENT_ARTIFACT,
        stage=BUILD_WATCH_TRIGGERS_STAGE,
    )
    decision_records = _records_from_artifact(
        decision_recommendations,
        DECISION_RECOMMENDATIONS_ARTIFACT,
        stage=BUILD_WATCH_TRIGGERS_STAGE,
    )
    derivatives_artifact, derivatives_warnings = _read_optional_derivatives_context(run)
    macro_artifact, macro_warnings = _read_optional_macro_calendar_context(run)
    onchain_artifact, onchain_warnings = _read_optional_onchain_flow_context(run)
    derivatives_records = _records_from_optional_artifact(derivatives_artifact)
    derivatives_groups = _derivatives_by_symbol(derivatives_records)
    macro_records = _records_from_optional_artifact(macro_artifact)
    macro_groups = _macro_calendar_context_by_symbol(macro_records)
    onchain_records = _records_from_optional_artifact(onchain_artifact)

    created_at = _created_at(decision_recommendations, now)
    signal_groups = _signals_by_tuple(signals)
    regime_groups = _regime_by_tuple(regime_records)
    risk_groups = _risk_by_tuple(risk_records)
    records = [
        trigger
        for decision in decision_records
        for trigger in _watch_trigger_records(
            decision,
            signal_groups.get(_tuple_key(decision), []),
            regime_groups.get(_tuple_key(decision)),
            risk_groups.get(_tuple_key(decision)),
            derivatives_groups.get(_tuple_key(decision)[1], []),
            _macro_calendar_records_for_symbol(macro_groups, _tuple_key(decision)[1]),
            _onchain_flow_records_for_symbol(onchain_records, _tuple_key(decision)[1]),
        )
    ]

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "watch_triggers",
        "run_id": run.run_id,
        "created_at": created_at,
        "trigger_types": list(TRIGGER_TYPES),
        "source_artifacts": _watch_source_artifacts(
            market_signals,
            market_regime,
            risk_assessment,
            decision_recommendations,
            derivatives_artifact,
            macro_artifact,
            onchain_artifact,
        ),
        "records": records,
        "warnings": _unique_ordered(
            [
                *_watch_artifact_warnings(decision_records, records),
                *derivatives_warnings,
                *macro_warnings,
                *onchain_warnings,
            ]
        ),
        "errors": [],
    }
    write_json(run.analysis_dir / "watch_triggers.json", artifact)
    run.manifest["artifacts"]["watch_triggers"] = WATCH_TRIGGERS_ARTIFACT
    _record_watch_trigger_counts(run, records)
    run.manifest["counts"]["watch_trigger_derivatives_context_records"] = len(derivatives_records)
    run.manifest["counts"]["watch_trigger_derivatives_linked_records"] = sum(
        1 for record in records if record.get("linked_derivatives_context_ids")
    )
    run.manifest["counts"]["watch_trigger_macro_calendar_context_records"] = len(macro_records)
    run.manifest["counts"]["watch_trigger_macro_calendar_linked_records"] = sum(
        1 for record in records if record.get("linked_macro_calendar_context_ids")
    )
    run.manifest["counts"]["watch_trigger_onchain_flow_context_records"] = len(onchain_records)
    run.manifest["counts"]["watch_trigger_onchain_flow_linked_records"] = sum(
        1 for record in records if record.get("linked_onchain_flow_context_ids")
    )
    return [WATCH_TRIGGERS_ARTIFACT]


def build_decision_intelligence_delta(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    result = build_decision_intelligence_delta_artifact(config, run, now=now)
    _record_decision_intelligence_manifest(
        run,
        enabled=result.enabled,
        status=result.status,
        reason=result.reason,
        previous_run=result.previous_run,
        warnings=result.warnings,
        errors=result.errors,
    )
    return result.artifacts


def build_decision_intelligence_material(config: dict[str, Any], run: RunContext) -> list[str]:
    if not _quant_enabled(config):
        run.manifest["counts"]["decision_intelligence_material_records"] = 0
        return []

    inputs = _read_decision_material_inputs(run)
    decision_record_count = decision_material_record_count(inputs)
    output_path = run.analysis_dir / "decision_intelligence_material.md"
    output_path.write_text(
        render_decision_intelligence_material(inputs, run_id=run.run_id),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["decision_intelligence_material"] = DECISION_INTELLIGENCE_MATERIAL_ARTIFACT
    run.manifest["counts"]["decision_intelligence_material_records"] = decision_record_count
    previous_run = _mapping(run.manifest.get("decision_intelligence")).get(
        "previous_run",
        _previous_run_summary("not_checked"),
    )
    warnings = _string_list(_mapping(run.manifest.get("decision_intelligence")).get("warnings"))
    errors = _string_list(_mapping(run.manifest.get("decision_intelligence")).get("errors"))
    _record_decision_intelligence_manifest(
        run,
        enabled=True,
        status="succeeded",
        previous_run=previous_run,
        warnings=warnings,
        errors=errors,
    )
    return [DECISION_INTELLIGENCE_MATERIAL_ARTIFACT]


def record_decision_intelligence_failure(
    config: dict[str, Any],
    run: RunContext,
    *,
    stage: str,
    message: str,
) -> None:
    existing = _mapping(run.manifest.get("decision_intelligence"))
    previous_run = _mapping(existing.get("previous_run")) or _previous_run_summary("not_checked")
    warnings = _string_list(existing.get("warnings"))
    errors = _unique_ordered([*_string_list(existing.get("errors")), f"{stage}: {message}"])
    _record_decision_intelligence_manifest(
        run,
        enabled=_quant_enabled(config),
        status="failed",
        previous_run=previous_run,
        warnings=warnings,
        errors=errors,
    )


def _read_decision_material_inputs(run: RunContext) -> dict[str, dict[str, Any]]:
    artifacts = {
        "market_regime_assessment": _read_json_artifact(
            run.analysis_dir / "market_regime_assessment.json",
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            producer_stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        ),
        "risk_assessment": _read_json_artifact(
            run.analysis_dir / "risk_assessment.json",
            RISK_ASSESSMENT_ARTIFACT,
            producer_stage=BUILD_RISK_ASSESSMENT_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        ),
        "decision_recommendations": _read_json_artifact(
            run.analysis_dir / "decision_recommendations.json",
            DECISION_RECOMMENDATIONS_ARTIFACT,
            producer_stage=BUILD_DECISION_RECOMMENDATIONS_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        ),
        "watch_triggers": _read_json_artifact(
            run.analysis_dir / "watch_triggers.json",
            WATCH_TRIGGERS_ARTIFACT,
            producer_stage=BUILD_WATCH_TRIGGERS_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        ),
        "decision_intelligence_delta": _read_json_artifact(
            run.analysis_dir / "decision_intelligence_delta.json",
            DECISION_INTELLIGENCE_DELTA_ARTIFACT,
            producer_stage=BUILD_DECISION_INTELLIGENCE_DELTA_STAGE,
            stage=BUILD_DECISION_INTELLIGENCE_MATERIAL_STAGE,
        ),
    }
    validate_decision_material_inputs(artifacts)
    return artifacts


def _previous_run_summary(status: str, *, run_id: str | None = None, path: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "run_id": run_id,
        "path": path,
    }


def _record_decision_intelligence_manifest(
    run: RunContext,
    *,
    enabled: bool,
    status: str,
    previous_run: dict[str, Any],
    warnings: list[str],
    errors: list[str],
    reason: str | None = None,
) -> None:
    artifacts = _decision_intelligence_manifest_artifacts(run)
    warnings = _unique_ordered([*warnings, *_decision_manifest_artifact_messages(run, field="warnings")])
    errors = _unique_ordered([*errors, *_decision_manifest_artifact_messages(run, field="errors")])
    section: dict[str, Any] = {
        "enabled": enabled,
        "status": status,
        "artifacts": artifacts,
        "counts": {
            "regime_records": run.manifest["counts"].get("market_regime_records", 0),
            "risk_records": run.manifest["counts"].get("risk_assessment_records", 0),
            "decision_recommendations": run.manifest["counts"].get("decision_recommendation_records", 0),
            "watch_triggers": run.manifest["counts"].get("watch_trigger_records", 0),
            "changed_delta_records": run.manifest["counts"].get("decision_delta_changed_records", 0),
            "decision_material_records": run.manifest["counts"].get("decision_intelligence_material_records", 0),
        },
        "previous_run": previous_run,
        "warnings": warnings,
        "errors": errors,
    }
    if reason is not None:
        section["reason"] = reason
    run.manifest["decision_intelligence"] = section


def _decision_intelligence_manifest_artifacts(run: RunContext) -> dict[str, str]:
    artifact_keys = [
        "market_regime_assessment",
        "risk_assessment",
        "decision_recommendations",
        "watch_triggers",
        "decision_intelligence_delta",
        "decision_intelligence_material",
    ]
    return {
        key: run.manifest["artifacts"][key]
        for key in artifact_keys
        if key in run.manifest["artifacts"]
    }


def _decision_manifest_artifact_messages(run: RunContext, *, field: str) -> list[str]:
    messages: list[str] = []
    for artifact in _decision_intelligence_manifest_artifacts(run).values():
        if not artifact.endswith(".json"):
            continue
        path = run.run_dir / artifact
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if field == "errors":
                messages.append(f"{artifact} was listed in the manifest but was not found.")
            continue
        except JSONDecodeError as exc:
            if field == "errors":
                messages.append(f"{artifact} is not valid JSON: {exc.msg}.")
            continue
        if isinstance(loaded, dict):
            messages.extend(_string_list(loaded.get(field)))
    return messages


def _regime_record(signals: list[dict[str, Any]], derivatives_records: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [signal for signal in signals if _has_usable_signal_evidence(signal)]
    latest = _latest_candle_time(signals)
    source = _group_value(signals, "source")
    symbol = _group_value(signals, "symbol")
    timeframe = _group_value(signals, "timeframe")
    warnings: list[str] = []
    if len(usable) < len(signals):
        warnings.append("One or more upstream market signals have insufficient or weak evidence.")

    regime, regime_evidence, conflicts = _classify_regime(usable)
    derivatives = _derivatives_context_effects(derivatives_records)
    conflicts = _unique_ordered([*conflicts, *_derivatives_regime_conflicts(regime, derivatives)])
    if not usable:
        warnings.append("No usable upstream market signal evidence was available.")

    return {
        "record_id": f"market_regime:{source}:{symbol}:{timeframe}:{latest}",
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "latest_candle_time": None if latest == "missing" else latest,
        "regime": regime,
        "confidence": _confidence(regime, usable, conflicts),
        "status": _record_status(regime, usable, warnings),
        "evidence": _unique_ordered(
            [
                *regime_evidence,
                *derivatives["evidence"],
                *_bounded_signal_evidence(usable),
            ]
        ),
        "conflicts": conflicts,
        "uncertainty": _unique_ordered([*_uncertainty(signals), *derivatives["uncertainty"]]),
        "warnings": warnings,
        "source_artifacts": _record_source_artifacts(signals, derivatives_records),
    }


def _classify_regime(signals: list[dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    if not signals:
        return "unknown", ["No usable market signal records were available."], []

    direction_counts = _direction_counts(signals)
    latest_regimes = _latest_regimes(signals)
    volatility = _volatility_state(signals)
    evidence = [
        _counts_evidence("direction_counts", direction_counts),
    ]
    if latest_regimes:
        evidence.append(f"latest_regime values: {', '.join(latest_regimes)}.")
    if volatility["evidence"]:
        evidence.extend(volatility["evidence"])

    has_opposing_direction = direction_counts.get("bullish", 0) > 0 and direction_counts.get("bearish", 0) > 0
    has_mixed_signal = direction_counts.get("mixed", 0) > 0
    if has_opposing_direction or has_mixed_signal:
        conflicts = _direction_conflicts(direction_counts, signals)
        return "mixed", evidence, conflicts

    bullish = direction_counts.get("bullish", 0)
    bearish = direction_counts.get("bearish", 0)
    neutral = direction_counts.get("neutral", 0)
    range_votes = neutral + sum(1 for value in latest_regimes if _is_range_regime(value))

    if bullish > 0 and bullish >= neutral:
        return "trend_up", evidence, []
    if bearish > 0 and bearish >= neutral:
        return "trend_down", evidence, []
    if range_votes > 0:
        return "range_bound", evidence, []
    if volatility["state"] == "high":
        return "high_volatility", evidence, []
    if volatility["state"] == "low":
        return "low_volatility", evidence, []
    return "unknown", evidence, []


def _volatility_state(signals: list[dict[str, Any]]) -> dict[str, Any]:
    high_evidence = []
    low_evidence = []
    for signal in signals:
        key_values = _mapping(signal.get("key_values"))
        realized = _number(key_values.get("realized_volatility_pct"))
        target = _number(key_values.get("target_volatility_pct"))
        if realized is not None and target is not None and target > 0:
            if realized >= target * 1.5:
                high_evidence.append(
                    f"{_signal_name(signal)} realized_volatility_pct {realized} is at least 1.5x target {target}."
                )
            elif realized <= target * 0.5:
                low_evidence.append(
                    f"{_signal_name(signal)} realized_volatility_pct {realized} is at most 0.5x target {target}."
                )
        atr_pct = _number(key_values.get("atr_pct"))
        if atr_pct is not None:
            if atr_pct >= 4.0:
                high_evidence.append(f"{_signal_name(signal)} atr_pct {atr_pct} is elevated.")
            elif atr_pct <= 1.0:
                low_evidence.append(f"{_signal_name(signal)} atr_pct {atr_pct} is low.")
    if high_evidence:
        return {"state": "high", "evidence": high_evidence}
    if low_evidence:
        return {"state": "low", "evidence": low_evidence}
    return {"state": "normal", "evidence": []}


def _risk_record(
    key: tuple[str, str, str],
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    strategy_runs: list[dict[str, Any]],
    derivatives_records: list[dict[str, Any]],
    macro_records: list[dict[str, Any]],
    onchain_records: list[dict[str, Any]],
) -> dict[str, Any]:
    source, symbol, timeframe = key
    latest = _latest_risk_candle_time(signals, regime, strategy_runs)
    data_quality_risks = _data_quality_risks(signals, regime, strategy_runs)
    signal_conflict_risks = _signal_conflict_risks(signals, regime)
    volatility = _volatility_risk(signals)
    strategy = _strategy_warning_risk(strategy_runs, signals)
    regime_risks = _regime_risks(regime)
    derivatives = _derivatives_context_effects(derivatives_records)
    macro = _macro_calendar_context_effects(macro_records)
    onchain = _onchain_flow_context_effects(onchain_records)
    usable_evidence = (
        _has_usable_risk_evidence(signals, regime)
        or derivatives["supports_risk_assessment"]
        or macro["supports_risk_assessment"]
        or onchain["supports_risk_assessment"]
    )
    warnings = _risk_record_warnings(regime, usable_evidence)

    rising_risks = _unique_ordered(
        [
            *volatility["rising"],
            *strategy["rising"],
            *regime_risks["rising"],
            *derivatives["rising"],
            *macro["rising"],
            *onchain["rising"],
            *([] if usable_evidence else ["Upstream evidence is insufficient for a supported low-risk conclusion."]),
        ]
    )
    blocking_risks = _unique_ordered(
        [
            *signal_conflict_risks,
            *volatility["blocking"],
            *regime_risks["blocking"],
            *derivatives["blocking"],
            *macro["blocking"],
            *onchain["blocking"],
            *([] if usable_evidence else ["Insufficient upstream evidence blocks stronger action levels."]),
        ]
    )
    severities = [
        *volatility["severities"],
        *strategy["severities"],
        *regime_risks["severities"],
        *derivatives["severities"],
        *macro["severities"],
        *onchain["severities"],
        *(["high"] if signal_conflict_risks else []),
        *(["medium"] if data_quality_risks and usable_evidence else []),
    ]
    risk_level = _risk_level(severities, usable_evidence=usable_evidence)
    return {
        "record_id": f"risk_assessment:{source}:{symbol}:{timeframe}:{latest}",
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "latest_candle_time": None if latest == "missing" else latest,
        "risk_level": risk_level,
        "status": _risk_status(risk_level, usable_evidence, warnings),
        "rising_risks": rising_risks,
        "blocking_risks": blocking_risks,
        "data_quality_risks": data_quality_risks,
        "signal_conflict_risks": signal_conflict_risks,
        "gates": _risk_gates(risk_level),
        "evidence": _risk_evidence(
            signals,
            regime,
            volatility=volatility,
            strategy=strategy,
            regime_risks=regime_risks,
            derivatives=derivatives,
            macro=macro,
            onchain=onchain,
            risk_level=risk_level,
        ),
        "warnings": _unique_ordered([*warnings, *derivatives["warnings"], *macro["warnings"], *onchain["warnings"]]),
        "errors": [],
        "source_artifacts": _risk_record_source_artifacts(
            signals,
            regime,
            strategy_runs,
            derivatives_records,
            macro_records,
            onchain_records,
        ),
    }


def _decision_recommendation_record(
    key: tuple[str, str, str],
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    derivatives_records: list[dict[str, Any]],
    macro_records: list[dict[str, Any]],
    onchain_records: list[dict[str, Any]],
) -> dict[str, Any]:
    source, symbol, timeframe = key
    latest = _latest_decision_candle_time(signals, regime, risk)
    usable_signals = [signal for signal in signals if _has_usable_signal_evidence(signal)]
    conflicts = _decision_conflicts(usable_signals, regime, risk)
    risk_level = _clean_text(risk.get("risk_level") if risk else None, fallback="unknown")
    risk_status = _clean_text(risk.get("status") if risk else None, fallback="unknown")
    regime_value = _clean_text(regime.get("regime") if regime else None, fallback="unknown")
    has_evidence = _has_decision_evidence(usable_signals, regime, risk)
    derivatives = _derivatives_context_effects(derivatives_records)
    macro = _macro_calendar_context_effects(macro_records)
    onchain = _onchain_flow_context_effects(onchain_records)

    base_action_level = _base_action_level(
        usable_signals,
        regime,
        risk,
        conflicts=conflicts,
        has_evidence=has_evidence,
    )
    action_level = _apply_decision_gates(base_action_level, risk, conflicts=conflicts, has_evidence=has_evidence)
    action_level, derivatives_downgrade_reasons = _apply_derivatives_decision_gate(
        action_level,
        derivatives,
        has_evidence=has_evidence,
    )
    action_level, macro_downgrade_reasons = _apply_macro_calendar_decision_gate(
        action_level,
        macro,
        base_action_level=base_action_level,
        has_evidence=has_evidence,
    )
    action_level, onchain_downgrade_reasons = _apply_onchain_flow_decision_gate(
        action_level,
        onchain,
        has_evidence=has_evidence,
    )
    downgrade_reasons = _unique_ordered(
        [*derivatives_downgrade_reasons, *macro_downgrade_reasons, *onchain_downgrade_reasons]
    )
    evidence = _decision_evidence(usable_signals, regime, risk, derivatives=derivatives, macro=macro, onchain=onchain)
    invalidation_conditions = _decision_invalidation_conditions(
        action_level,
        symbol=symbol,
        regime_value=regime_value,
        risk_level=risk_level,
        conflicts=conflicts,
        has_evidence=has_evidence,
    )
    if action_level in ACTIONABLE_ACTION_LEVELS:
        invalidation_conditions = _unique_ordered(
            [
                *invalidation_conditions,
                *_derivatives_invalidation_conditions(symbol=symbol, derivatives=derivatives),
                *_macro_calendar_invalidation_conditions(symbol=symbol, macro=macro),
                *_onchain_flow_invalidation_conditions(symbol=symbol, onchain=onchain),
            ]
        )
    warnings = _decision_warnings(
        action_level,
        risk_level=risk_level,
        risk_status=risk_status,
        regime_value=regime_value,
        conflicts=conflicts,
        has_evidence=has_evidence,
        risk=risk,
        derivatives=derivatives,
        macro=macro,
        onchain=onchain,
        derivatives_downgrade_reasons=derivatives_downgrade_reasons,
        macro_downgrade_reasons=macro_downgrade_reasons,
        onchain_downgrade_reasons=onchain_downgrade_reasons,
    )
    if action_level in ACTIONABLE_ACTION_LEVELS and (not evidence or not invalidation_conditions):
        action_level = "WATCH"
        invalidation_conditions = []
        warnings = _unique_ordered(
            [
                *warnings,
                "Actionable recommendation was downgraded because evidence or invalidation conditions were incomplete.",
            ]
        )

    return {
        "record_id": f"decision_recommendation:{source}:{symbol}:{timeframe}:{latest}",
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "latest_candle_time": None if latest == "missing" else latest,
        "action_level": action_level,
        "decision_bias": _decision_bias(action_level, risk_level, conflicts, has_evidence),
        "confidence": _decision_confidence(action_level, usable_signals, regime, risk, conflicts, has_evidence),
        "status": _decision_status(action_level, risk_level, risk_status, conflicts, has_evidence),
        "recommended_actions": _recommended_actions(action_level, symbol=symbol, conflicts=conflicts, risk_level=risk_level),
        "do_not_do": _do_not_do_guidance(action_level, risk_level=risk_level, conflicts=conflicts, has_evidence=has_evidence),
        "risk_conditions": _risk_conditions(risk, derivatives=derivatives, macro=macro, onchain=onchain),
        "downgrade_reasons": downgrade_reasons,
        "invalidation_conditions": invalidation_conditions,
        "evidence": evidence,
        "conflicts": conflicts,
        "warnings": warnings,
        "linked_derivatives_context_ids": _derivatives_context_ids(derivatives_records),
        "linked_macro_calendar_context_ids": _macro_calendar_context_ids(macro_records),
        "linked_onchain_flow_context_ids": _onchain_flow_context_ids(onchain_records),
        "source_artifacts": _decision_record_source_artifacts(
            signals,
            regime,
            risk,
            derivatives_records,
            macro_records,
            onchain_records,
        ),
    }


def _base_action_level(
    usable_signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    *,
    conflicts: list[str],
    has_evidence: bool,
) -> str:
    risk_level = _clean_text(risk.get("risk_level") if risk else None, fallback="unknown")
    risk_status = _clean_text(risk.get("status") if risk else None, fallback="unknown")
    regime_value = _clean_text(regime.get("regime") if regime else None, fallback="unknown")
    if not has_evidence or risk_status == "insufficient_data" or risk_level == "unknown":
        return "NO_ACTION"
    if risk_level == "extreme":
        return "NO_ACTION"
    if conflicts:
        return "WATCH"
    if risk_level == "high":
        return "WATCH"

    direction_counts = _direction_counts(usable_signals)
    bullish = direction_counts.get("bullish", 0)
    bearish = direction_counts.get("bearish", 0)
    high_confidence = _count_by_clean_text(usable_signals, "confidence").get("high", 0)

    if bearish and not bullish:
        return "AVOID"
    if regime_value == "trend_down":
        return "AVOID"
    if bullish and regime_value == "trend_up":
        if risk_level == "medium":
            return "TRY_SMALL"
        if high_confidence >= 2 and _clean_text(regime.get("confidence") if regime else None, fallback="unknown") == "high":
            return "DO"
        return "TRY_SMALL"
    if bullish and risk_level == "medium":
        return "TRY_SMALL"
    return "WATCH"


def _apply_decision_gates(
    action_level: str,
    risk: dict[str, Any] | None,
    *,
    conflicts: list[str],
    has_evidence: bool,
) -> str:
    if not has_evidence:
        return "NO_ACTION"
    if conflicts and action_level in ACTIONABLE_ACTION_LEVELS:
        return "WATCH"
    gates = _mapping(risk.get("gates") if risk else None)
    cap = _clean_text(gates.get("cap_action_level"), fallback="")
    if cap == "NO_ACTION" and action_level not in {"AVOID", "NO_ACTION"}:
        return "NO_ACTION"
    if cap == "WATCH" and action_level not in {"AVOID", "WATCH", "NO_ACTION"}:
        return "WATCH"
    if cap == "TRY_SMALL" and action_level in {"STRONG_DO", "DO"}:
        return "TRY_SMALL"
    return action_level


def _apply_derivatives_decision_gate(
    action_level: str,
    derivatives: dict[str, Any],
    *,
    has_evidence: bool,
) -> tuple[str, list[str]]:
    if not has_evidence or not derivatives.get("supports_risk_assessment"):
        return action_level, []
    severities = set(_string_list(derivatives.get("severities")))
    if "high" in severities and action_level in ACTIONABLE_ACTION_LEVELS:
        return "WATCH", ["high_severity_derivatives_context"]
    if "medium" in severities and action_level in {"STRONG_DO", "DO"}:
        return "TRY_SMALL", ["medium_severity_derivatives_context"]
    return action_level, []


def _apply_macro_calendar_decision_gate(
    action_level: str,
    macro: dict[str, Any],
    *,
    base_action_level: str,
    has_evidence: bool,
) -> tuple[str, list[str]]:
    if not has_evidence or not macro.get("supports_risk_assessment"):
        return action_level, []
    reasons: list[str] = []
    if macro.get("availability_issue_ids") and action_level in {"STRONG_DO", "DO", "TRY_SMALL"}:
        reasons.append("macro_calendar_source_uncertainty")
        return "WATCH", reasons
    if macro.get("scheduled_or_recent_ids") and base_action_level in {"STRONG_DO", "DO"}:
        reasons.append("macro_calendar_catalyst_caution")
        if action_level in {"STRONG_DO", "DO"}:
            return "TRY_SMALL", reasons
    return action_level, reasons


def _apply_onchain_flow_decision_gate(
    action_level: str,
    onchain: dict[str, Any],
    *,
    has_evidence: bool,
) -> tuple[str, list[str]]:
    if not has_evidence or not onchain.get("supports_risk_assessment"):
        return action_level, []
    if onchain.get("availability_issue_ids") and action_level in ACTIONABLE_ACTION_LEVELS:
        return "WATCH", ["onchain_flow_source_uncertainty"]
    severities = set(_string_list(onchain.get("severities")))
    if "high" in severities and action_level in ACTIONABLE_ACTION_LEVELS:
        return "WATCH", ["high_severity_onchain_flow_context"]
    if "medium" in severities and action_level in {"STRONG_DO", "DO"}:
        return "TRY_SMALL", ["medium_severity_onchain_flow_context"]
    return action_level, []


def _decision_status(
    action_level: str,
    risk_level: str,
    risk_status: str,
    conflicts: list[str],
    has_evidence: bool,
) -> str:
    if not has_evidence or risk_status == "insufficient_data":
        return "insufficient_data"
    if risk_level in {"high", "extreme"} and action_level == "NO_ACTION":
        return "risk_blocked"
    if action_level == "WATCH":
        return "watch"
    if action_level == "NO_ACTION":
        return "no_action"
    if conflicts:
        return "watch"
    return "actionable"


def _decision_bias(action_level: str, risk_level: str, conflicts: list[str], has_evidence: bool) -> str:
    if not has_evidence:
        return "insufficient_evidence"
    if risk_level == "extreme" or (risk_level == "high" and action_level == "NO_ACTION"):
        return "risk_blocked"
    if conflicts:
        return "wait_for_conflict_resolution"
    if action_level == "DO":
        return "constructive"
    if action_level == "TRY_SMALL":
        return "tentative_constructive"
    if action_level == "AVOID":
        return "defensive_avoid"
    if action_level == "WATCH":
        return "wait_for_confirmation"
    return "no_action"


def _decision_confidence(
    action_level: str,
    usable_signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    conflicts: list[str],
    has_evidence: bool,
) -> str:
    if not has_evidence or action_level == "NO_ACTION":
        return "low"
    risk_level = _clean_text(risk.get("risk_level") if risk else None, fallback="unknown")
    if risk_level in {"high", "extreme", "unknown"} or conflicts:
        return "low"
    regime_confidence = _clean_text(regime.get("confidence") if regime else None, fallback="unknown")
    high_signals = _count_by_clean_text(usable_signals, "confidence").get("high", 0)
    if action_level == "DO" and regime_confidence == "high" and high_signals >= 2:
        return "high"
    if action_level in {"DO", "TRY_SMALL", "AVOID"}:
        return "medium"
    return "low"


def _recommended_actions(action_level: str, *, symbol: str, conflicts: list[str], risk_level: str) -> list[str]:
    if action_level == "DO":
        return [f"Use {symbol} as a constructive research bias while current evidence remains aligned."]
    if action_level == "TRY_SMALL":
        return [f"Treat {symbol} as a tentative research opportunity and require confirmation before escalation."]
    if action_level == "WATCH":
        if conflicts:
            return [f"Wait for {symbol} signal conflict to resolve before using a directional decision bias."]
        if risk_level in {"high", "unknown"}:
            return [f"Wait for {symbol} risk conditions to improve before using a stronger decision bias."]
        return [f"Watch {symbol} for confirmation before using an actionable decision bias."]
    if action_level == "AVOID":
        return [f"Avoid treating {symbol} as a constructive setup until adverse evidence clears."]
    return []


def _do_not_do_guidance(action_level: str, *, risk_level: str, conflicts: list[str], has_evidence: bool) -> list[str]:
    guidance = ["Do not treat this record as an order, position sizing instruction, account action, or return promise."]
    if not has_evidence:
        guidance.append("Do not act on insufficient upstream evidence.")
    if risk_level in {"high", "extreme", "unknown"}:
        guidance.append(f"Do not upgrade to DO or TRY_SMALL while risk_level={risk_level}.")
    if conflicts:
        guidance.append("Do not treat conflicting signals as confirmed directional evidence.")
    if action_level in ACTIONABLE_ACTION_LEVELS:
        guidance.append("Do not keep the actionable bias if any invalidation condition is met.")
    return _unique_ordered(guidance)


def _risk_conditions(
    risk: dict[str, Any] | None,
    *,
    derivatives: dict[str, Any] | None = None,
    macro: dict[str, Any] | None = None,
    onchain: dict[str, Any] | None = None,
) -> list[str]:
    if risk is None:
        conditions = ["risk_assessment=missing."]
    else:
        gates = _mapping(risk.get("gates"))
        conditions = [
            f"risk_level={_clean_text(risk.get('risk_level'), fallback='unknown')}; "
            f"status={_clean_text(risk.get('status'), fallback='unknown')}.",
        ]
        cap = gates.get("cap_action_level")
        if isinstance(cap, str) and cap.strip():
            conditions.append(f"cap_action_level={cap.strip()}.")
        for label, field in (
            ("rising_risk", "rising_risks"),
            ("blocking_risk", "blocking_risks"),
            ("data_quality_risk", "data_quality_risks"),
            ("signal_conflict_risk", "signal_conflict_risks"),
        ):
            for item in _string_list(risk.get(field))[:4]:
                conditions.append(f"{label}: {item}")
    if derivatives:
        for item in _string_list(derivatives.get("rising"))[:3]:
            conditions.append(f"derivatives_context_risk: {item}")
        for item in _string_list(derivatives.get("blocking"))[:2]:
            conditions.append(f"derivatives_context_blocking: {item}")
        for item in _string_list(derivatives.get("uncertainty"))[:2]:
            conditions.append(f"derivatives_context_uncertainty: {item}")
    if macro:
        for item in _string_list(macro.get("rising"))[:3]:
            conditions.append(f"macro_calendar_context_risk: {item}")
        for item in _string_list(macro.get("blocking"))[:2]:
            conditions.append(f"macro_calendar_context_blocking: {item}")
        for item in _string_list(macro.get("uncertainty"))[:2]:
            conditions.append(f"macro_calendar_context_uncertainty: {item}")
    if onchain:
        for item in _string_list(onchain.get("rising"))[:3]:
            conditions.append(f"onchain_flow_context_risk: {item}")
        for item in _string_list(onchain.get("blocking"))[:2]:
            conditions.append(f"onchain_flow_context_blocking: {item}")
        for item in _string_list(onchain.get("uncertainty"))[:2]:
            conditions.append(f"onchain_flow_context_uncertainty: {item}")
    return _unique_ordered(conditions)


def _decision_invalidation_conditions(
    action_level: str,
    *,
    symbol: str,
    regime_value: str,
    risk_level: str,
    conflicts: list[str],
    has_evidence: bool,
) -> list[str]:
    if not has_evidence or action_level in {"WATCH", "NO_ACTION"}:
        return []
    if action_level in {"DO", "TRY_SMALL"}:
        return [
            f"{symbol} risk_level rises to high or extreme.",
            f"{symbol} market regime changes from {regime_value} to mixed, trend_down, high_volatility, or unknown.",
            f"{symbol} upstream market signals no longer show a bullish majority.",
            f"{symbol} blocking risks appear in risk_assessment.",
        ]
    if action_level == "AVOID":
        return [
            f"{symbol} market regime is no longer trend_down or bearish.",
            f"{symbol} upstream market signals regain a bullish majority without material conflict.",
            f"{symbol} risk conditions are low and no blocking risks remain.",
        ]
    if action_level in {"EXIT_OR_REDUCE", "HEDGE_OR_PROTECT"}:
        return [
            f"{symbol} elevated risk pressure clears.",
            f"{symbol} market regime and upstream signals realign without material conflict.",
        ]
    if conflicts:
        return [f"{symbol} conflicts resolve and no blocking risk remains."]
    if risk_level in {"high", "extreme"}:
        return [f"{symbol} risk_level falls below {risk_level}."]
    return []


def _derivatives_invalidation_conditions(*, symbol: str, derivatives: dict[str, Any]) -> list[str]:
    if not derivatives.get("supports_risk_assessment"):
        return []
    return [
        f"{symbol} derivatives context adds high-severity leverage, premium, basis, spread, or depth stress.",
    ]


def _macro_calendar_invalidation_conditions(*, symbol: str, macro: dict[str, Any]) -> list[str]:
    if not macro.get("scheduled_or_recent_ids"):
        return []
    return [
        f"{symbol} macro/calendar catalyst window changes, starts, or lacks post-event confirmation from market, risk, derivatives, or strategy evidence.",
    ]


def _onchain_flow_invalidation_conditions(*, symbol: str, onchain: dict[str, Any]) -> list[str]:
    if not onchain.get("supports_risk_assessment"):
        return []
    return [
        f"{symbol} on-chain flow context adds high-severity liquidity, network, congestion, or source-availability stress.",
    ]


def _decision_evidence(
    usable_signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    *,
    derivatives: dict[str, Any] | None = None,
    macro: dict[str, Any] | None = None,
    onchain: dict[str, Any] | None = None,
) -> list[str]:
    evidence = [
        _counts_evidence("direction_counts", _direction_counts(usable_signals)),
    ]
    if regime is None:
        evidence.append("No matching market regime assessment record was available.")
    else:
        evidence.append(
            "market_regime="
            f"{_clean_text(regime.get('regime'), fallback='unknown')}; "
            f"confidence={_clean_text(regime.get('confidence'), fallback='unknown')}; "
            f"status={_clean_text(regime.get('status'), fallback='unknown')}."
        )
        evidence.extend(_string_list(regime.get("evidence"))[:3])
    if risk is None:
        evidence.append("No matching risk assessment record was available.")
    else:
        evidence.append(
            "risk_level="
            f"{_clean_text(risk.get('risk_level'), fallback='unknown')}; "
            f"status={_clean_text(risk.get('status'), fallback='unknown')}."
        )
        evidence.extend(_string_list(risk.get("evidence"))[:3])
    if derivatives:
        evidence.extend(_string_list(derivatives.get("evidence"))[:3])
        evidence.extend(_string_list(derivatives.get("uncertainty"))[:2])
    if macro:
        evidence.extend(_string_list(macro.get("evidence"))[:3])
        evidence.extend(_string_list(macro.get("uncertainty"))[:2])
    if onchain:
        evidence.extend(_string_list(onchain.get("evidence"))[:3])
        evidence.extend(_string_list(onchain.get("uncertainty"))[:2])
    evidence.extend(_bounded_signal_evidence(usable_signals))
    return _unique_ordered(evidence)


def _decision_warnings(
    action_level: str,
    *,
    risk_level: str,
    risk_status: str,
    regime_value: str,
    conflicts: list[str],
    has_evidence: bool,
    risk: dict[str, Any] | None,
    derivatives: dict[str, Any] | None = None,
    macro: dict[str, Any] | None = None,
    onchain: dict[str, Any] | None = None,
    derivatives_downgrade_reasons: list[str] | None = None,
    macro_downgrade_reasons: list[str] | None = None,
    onchain_downgrade_reasons: list[str] | None = None,
) -> list[str]:
    warnings = []
    if not has_evidence or risk_status == "insufficient_data" or regime_value == "unknown":
        warnings.append("Insufficient upstream evidence prevents an actionable decision recommendation.")
    if conflicts:
        warnings.append("Major upstream signal conflict caps action strength at WATCH.")
    if risk_level in {"high", "unknown"} and action_level == "WATCH":
        warnings.append(f"risk_level={risk_level} caps stronger action levels.")
    if risk_level == "extreme":
        warnings.append("risk_level=extreme blocks stronger action levels.")
    if risk is None:
        warnings.append("No matching risk assessment record was available.")
    else:
        warnings.extend(_string_list(risk.get("warnings")))
    if derivatives_downgrade_reasons:
        warnings.append("Derivatives context downgraded stronger action language.")
    if derivatives:
        warnings.extend(_string_list(derivatives.get("warnings")))
    if macro_downgrade_reasons:
        warnings.append("Macro calendar context downgraded stronger action language.")
    if macro:
        warnings.extend(_string_list(macro.get("warnings")))
    if onchain_downgrade_reasons:
        warnings.append("On-chain flow context downgraded stronger action language.")
    if onchain:
        warnings.extend(_string_list(onchain.get("warnings")))
    return _unique_ordered(warnings)


def _decision_conflicts(
    usable_signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
) -> list[str]:
    conflicts = []
    direction_conflicts = _direction_conflicts(_direction_counts(usable_signals), usable_signals)
    conflicts.extend(direction_conflicts)
    if regime:
        conflicts.extend(_string_list(regime.get("conflicts")))
        if _clean_text(regime.get("regime"), fallback="unknown") == "mixed":
            conflicts.append("Market regime assessment is mixed.")
    if risk:
        conflicts.extend(_string_list(risk.get("signal_conflict_risks")))
    return _unique_ordered(conflicts)


def _has_decision_evidence(
    usable_signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
) -> bool:
    if usable_signals:
        return True
    if regime and _clean_text(regime.get("status"), fallback="unknown") not in {"insufficient_data", "unknown"}:
        return bool(_string_list(regime.get("evidence")))
    if risk and _clean_text(risk.get("status"), fallback="unknown") not in {"insufficient_data", "unknown"}:
        return bool(_string_list(risk.get("evidence")))
    return False


def _decision_group_keys(
    signals: list[dict[str, Any]],
    regime_records: list[dict[str, Any]],
    risk_records: list[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    return sorted(
        {
            *[_tuple_key(item) for item in signals],
            *[_tuple_key(item) for item in regime_records],
            *[_tuple_key(item) for item in risk_records],
        }
    )


def _latest_decision_candle_time(
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
) -> str:
    values = [
        *[_clean_text(signal.get("latest_candle_time"), fallback="") for signal in signals],
        *([_clean_text(regime.get("latest_candle_time"), fallback="")] if regime else []),
        *([_clean_text(risk.get("latest_candle_time"), fallback="")] if risk else []),
    ]
    clean = sorted(value for value in values if value)
    return clean[-1] if clean else "missing"


def _risk_by_tuple(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {_tuple_key(record): record for record in records}


def _derivatives_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            record_id
            for record in records
            for record_id in [_clean_text(record.get("context_id"), fallback="")]
            if record_id
        ]
    )


def _macro_calendar_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            record_id
            for record in records
            for record_id in [_clean_text(record.get("context_id"), fallback="")]
            if record_id
        ]
    )


def _onchain_flow_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            record_id
            for record in records
            for record_id in [_clean_text(record.get("context_id"), fallback="")]
            if record_id
        ]
    )


def _decision_record_source_artifacts(
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    derivatives_records: list[dict[str, Any]] | None = None,
    macro_records: list[dict[str, Any]] | None = None,
    onchain_records: list[dict[str, Any]] | None = None,
) -> list[str]:
    return _unique_ordered(
        [
            RISK_ASSESSMENT_ARTIFACT,
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *(_string_list(risk.get("source_artifacts")) if risk else []),
            *(_string_list(regime.get("source_artifacts")) if regime else []),
            *([DERIVATIVES_MARKET_CONTEXT_ARTIFACT] if derivatives_records else []),
            *[
                artifact
                for record in derivatives_records or []
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *([MACRO_CALENDAR_CONTEXT_ARTIFACT] if macro_records else []),
            *[
                artifact
                for record in macro_records or []
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *([ONCHAIN_FLOW_CONTEXT_ARTIFACT] if onchain_records else []),
            *[
                artifact
                for record in onchain_records or []
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *[
                artifact
                for signal in signals
                for artifact in _string_list(signal.get("source_artifacts"))
            ],
            MARKET_STRATEGY_SIGNALS_ARTIFACT,
            QUANT_STRATEGY_RUNS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
        ]
    )


def _watch_trigger_records(
    decision: dict[str, Any],
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    derivatives_records: list[dict[str, Any]],
    macro_records: list[dict[str, Any]],
    onchain_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    derivatives = _derivatives_context_effects(derivatives_records)
    macro = _macro_calendar_context_effects(macro_records)
    onchain = _onchain_flow_context_effects(onchain_records)
    evidence = _unique_ordered(
        [
            *_watch_evidence(decision, signals, regime, risk),
            *_string_list(derivatives.get("evidence"))[:3],
            *_string_list(macro.get("evidence"))[:3],
            *_string_list(macro.get("uncertainty"))[:2],
            *_string_list(onchain.get("evidence"))[:3],
            *_string_list(onchain.get("uncertainty"))[:2],
        ]
    )
    if not evidence:
        return []

    records: list[dict[str, Any]] = []
    source = _clean_text(decision.get("source"), fallback="missing")
    symbol = _clean_text(decision.get("symbol"), fallback="missing")
    timeframe = _clean_text(decision.get("timeframe"), fallback="missing")
    latest = _clean_text(decision.get("latest_candle_time"), fallback="missing")
    action_level = _clean_text(decision.get("action_level"), fallback="NO_ACTION")
    status = _clean_text(decision.get("status"), fallback="unknown")
    risk_level = _clean_text(risk.get("risk_level") if risk else None, fallback=_risk_level_from_decision(decision))
    source_artifacts = _watch_record_source_artifacts(
        decision,
        signals,
        regime,
        risk,
        derivatives_records,
        macro_records,
        onchain_records,
    )
    linked_derivatives_context_ids = _derivatives_context_ids(derivatives_records)
    linked_macro_calendar_context_ids = _macro_calendar_context_ids(macro_records)
    linked_onchain_flow_context_ids = _onchain_flow_context_ids(onchain_records)

    if action_level in ACTIONABLE_ACTION_LEVELS:
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="confirmation",
                condition=_confirmation_condition(decision, regime),
                priority="medium",
                expected_decision_impact=_confirmation_impact(action_level),
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=[],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
            )
        )
        for index, condition in enumerate(_string_list(decision.get("invalidation_conditions"))[:2], start=1):
            records.append(
                _watch_trigger_record(
                    source=source,
                    symbol=symbol,
                    timeframe=timeframe,
                    latest=latest,
                    trigger_type="invalidation",
                    condition=condition,
                    priority="high",
                    expected_decision_impact="would_downgrade_or_invalidate_current_action",
                    linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                    evidence=evidence,
                    warnings=[],
                    source_artifacts=source_artifacts,
                    linked_derivatives_context_ids=linked_derivatives_context_ids,
                    linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                    linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                    sequence=index,
                )
            )
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="risk_escalation",
                condition=f"{symbol} risk assessment adds high or extreme risk, blocking risks, or material signal conflict.",
                priority="high",
                expected_decision_impact="could_downgrade_to_watch_or_no_action",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=[],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
            )
        )

    if derivatives.get("supports_risk_assessment") and (derivatives.get("rising") or derivatives.get("blocking")):
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="risk_escalation",
                condition=f"{symbol} derivatives context adds leverage, premium, basis, spread, or depth stress.",
                priority="high" if "high" in set(_string_list(derivatives.get("severities"))) else "medium",
                expected_decision_impact="could_downgrade_or_block_stronger_action",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=[],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                sequence=1,
            )
        )
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="risk_relief",
                condition=f"{symbol} derivatives stress clears or falls back to neutral context.",
                priority="medium",
                expected_decision_impact="could_relieve_derivatives_risk_cap",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=[],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                sequence=1,
            )
        )

    if onchain.get("supports_risk_assessment") and (onchain.get("rising") or onchain.get("blocking")):
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="risk_escalation",
                condition=f"{symbol} on-chain flow context adds liquidity, network activity, congestion, or source-availability risk.",
                priority="high" if "high" in set(_string_list(onchain.get("severities"))) else "medium",
                expected_decision_impact="could_downgrade_or_block_stronger_action",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=_string_list(onchain.get("warnings"))[:2],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                sequence=1,
            )
        )
        if onchain.get("stress_context_ids"):
            records.append(
                _watch_trigger_record(
                    source=source,
                    symbol=symbol,
                    timeframe=timeframe,
                    latest=latest,
                    trigger_type="risk_relief",
                    condition=f"{symbol} on-chain flow stress clears or falls back to normal context.",
                    priority="medium",
                    expected_decision_impact="could_relieve_onchain_flow_risk_cap",
                    linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                    evidence=evidence,
                    warnings=[],
                    source_artifacts=source_artifacts,
                    linked_derivatives_context_ids=linked_derivatives_context_ids,
                    linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                    linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                    sequence=1,
                )
            )

    if onchain.get("availability_issue_ids"):
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="recheck_next_run",
                condition=f"Recheck on-chain flow source availability for {symbol}; do not treat stale, unavailable, partial, or missing flow evidence as neutral.",
                priority="medium",
                expected_decision_impact="could_keep_or_relieve_onchain_flow_source_uncertainty",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=_string_list(onchain.get("warnings"))[:2],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                sequence=1,
            )
        )

    if macro.get("scheduled_or_recent_ids"):
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="wait_condition",
                condition=_macro_calendar_wait_condition(symbol=symbol, macro=macro),
                priority="medium",
                expected_decision_impact="keeps_stronger_action_capped_until_post_event_confirmation",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=_string_list(macro.get("warnings"))[:2],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                sequence=1,
            )
        )
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="confirmation",
                condition=_macro_calendar_post_event_condition(symbol=symbol, macro=macro),
                priority="medium",
                expected_decision_impact="could_relieve_macro_calendar_caution_after_supported_follow_through",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=[],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                sequence=1,
            )
        )

    if macro.get("availability_issue_ids"):
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="recheck_next_run",
                condition=f"Recheck macro/calendar source availability for {symbol}; do not treat stale, unavailable, partial, or degraded calendar evidence as neutral.",
                priority="medium",
                expected_decision_impact="could_keep_or_relieve_macro_calendar_source_uncertainty",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=_string_list(macro.get("warnings"))[:2],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                sequence=1,
            )
        )

    if action_level == "WATCH":
        if _string_list(decision.get("conflicts")):
            records.append(
                _watch_trigger_record(
                    source=source,
                    symbol=symbol,
                    timeframe=timeframe,
                    latest=latest,
                    trigger_type="confirmation",
                    condition=f"{symbol} signal conflict resolves and the next decision record has aligned evidence.",
                    priority="medium",
                    expected_decision_impact="could_upgrade_watch_to_try_small",
                    linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                    evidence=evidence,
                    warnings=[],
                    source_artifacts=source_artifacts,
                    linked_derivatives_context_ids=linked_derivatives_context_ids,
                    linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                    linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
                )
            )
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="wait_condition",
                condition=_wait_condition(decision, symbol=symbol),
                priority="medium",
                expected_decision_impact="keeps_watch_until_confirmation_or_relief",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=_string_list(decision.get("warnings"))[:2],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
            )
        )

    if _needs_risk_relief(action_level, risk_level, decision):
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="risk_relief",
                condition=f"{symbol} risk_level falls below {risk_level} and blocking risk conditions clear.",
                priority="medium" if risk_level != "extreme" else "high",
                expected_decision_impact=_risk_relief_impact(action_level),
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=_string_list(decision.get("warnings"))[:2],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
            )
        )

    if action_level == "NO_ACTION" or status in {"insufficient_data", "risk_blocked"}:
        records.append(
            _watch_trigger_record(
                source=source,
                symbol=symbol,
                timeframe=timeframe,
                latest=latest,
                trigger_type="wait_condition",
                condition=_no_action_wait_condition(decision, symbol=symbol),
                priority="low" if status == "insufficient_data" else "medium",
                expected_decision_impact="keeps_no_action_until_evidence_or_risk_improves",
                linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
                evidence=evidence,
                warnings=_string_list(decision.get("warnings"))[:2],
                source_artifacts=source_artifacts,
                linked_derivatives_context_ids=linked_derivatives_context_ids,
                linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
                linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
            )
        )

    records.append(
        _watch_trigger_record(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            latest=latest,
            trigger_type="recheck_next_run",
            condition=f"Re-run Halpha for {symbol} {timeframe} and compare decision, regime, risk, and signal records.",
            priority="low",
            expected_decision_impact="refreshes_current_decision_view",
            linked_decision_record_id=_clean_text(decision.get("record_id"), fallback="missing"),
            evidence=evidence,
            warnings=[],
            source_artifacts=source_artifacts,
            linked_derivatives_context_ids=linked_derivatives_context_ids,
            linked_macro_calendar_context_ids=linked_macro_calendar_context_ids,
            linked_onchain_flow_context_ids=linked_onchain_flow_context_ids,
        )
    )
    return records


def _watch_trigger_record(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    latest: str,
    trigger_type: str,
    condition: str,
    priority: str,
    expected_decision_impact: str,
    linked_decision_record_id: str,
    evidence: list[str],
    warnings: list[str],
    source_artifacts: list[str],
    linked_derivatives_context_ids: list[str] | None = None,
    linked_macro_calendar_context_ids: list[str] | None = None,
    linked_onchain_flow_context_ids: list[str] | None = None,
    sequence: int | None = None,
) -> dict[str, Any]:
    suffix = f":{sequence}" if sequence is not None else ""
    return {
        "trigger_id": f"watch_trigger:{source}:{symbol}:{timeframe}:{trigger_type}:{latest}{suffix}",
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "type": trigger_type,
        "condition": condition,
        "priority": priority,
        "expected_decision_impact": expected_decision_impact,
        "linked_decision_record_id": linked_decision_record_id,
        "evidence": evidence,
        "warnings": _unique_ordered(warnings),
        "linked_derivatives_context_ids": linked_derivatives_context_ids or [],
        "linked_macro_calendar_context_ids": linked_macro_calendar_context_ids or [],
        "linked_onchain_flow_context_ids": linked_onchain_flow_context_ids or [],
        "source_artifacts": source_artifacts,
    }


def _confirmation_condition(decision: dict[str, Any], regime: dict[str, Any] | None) -> str:
    symbol = _clean_text(decision.get("symbol"), fallback="missing")
    action_level = _clean_text(decision.get("action_level"), fallback="NO_ACTION")
    regime_value = _clean_text(regime.get("regime") if regime else None, fallback="unknown")
    if action_level == "AVOID":
        return f"{symbol} bearish or defensive evidence remains aligned and regime remains {regime_value}."
    return f"{symbol} evidence remains aligned and market regime remains {regime_value}."


def _confirmation_impact(action_level: str) -> str:
    if action_level == "DO":
        return "could_maintain_constructive_bias"
    if action_level == "TRY_SMALL":
        return "could_upgrade_try_small_to_do"
    if action_level == "AVOID":
        return "could_maintain_defensive_avoid_bias"
    return "could_confirm_current_decision_view"


def _wait_condition(decision: dict[str, Any], *, symbol: str) -> str:
    recommended = _string_list(decision.get("recommended_actions"))
    if recommended:
        return recommended[0]
    return f"Wait for {symbol} confirmation before using a stronger decision bias."


def _no_action_wait_condition(decision: dict[str, Any], *, symbol: str) -> str:
    warnings = " ".join(_string_list(decision.get("warnings"))).lower()
    if "insufficient" in warnings or _clean_text(decision.get("status"), fallback="") == "insufficient_data":
        return f"Wait for {symbol} to have enough upstream evidence for a supported decision view."
    return f"Wait for {symbol} risk and decision records to move out of NO_ACTION."


def _macro_calendar_wait_condition(*, symbol: str, macro: dict[str, Any]) -> str:
    count = len(_string_list(macro.get("scheduled_or_recent_ids")))
    suffix = f" ({count} linked macro/calendar context record{'s' if count != 1 else ''})." if count else "."
    return (
        f"{symbol} has scheduled or recent macro/calendar catalyst context; keep stronger action capped until the "
        f"event window passes and post-event market, risk, derivatives, or strategy evidence confirms realized impact"
        f"{suffix}"
    )


def _macro_calendar_post_event_condition(*, symbol: str, macro: dict[str, Any]) -> str:
    count = len(_string_list(macro.get("scheduled_or_recent_ids")))
    suffix = f" ({count} linked macro/calendar context record{'s' if count != 1 else ''})." if count else "."
    return (
        f"{symbol} post-event confirmation requires fresh market, risk, derivatives, or strategy evidence after the "
        f"macro/calendar catalyst window; do not infer realized impact from the schedule alone{suffix}"
    )


def _needs_risk_relief(action_level: str, risk_level: str, decision: dict[str, Any]) -> bool:
    if risk_level in {"high", "extreme", "unknown"}:
        return True
    risk_conditions = " ".join(_string_list(decision.get("risk_conditions"))).lower()
    return action_level == "WATCH" and "cap_action_level" in risk_conditions


def _risk_relief_impact(action_level: str) -> str:
    if action_level == "WATCH":
        return "could_upgrade_watch_to_try_small"
    if action_level == "NO_ACTION":
        return "could_move_no_action_to_watch"
    return "could_reduce_risk_pressure"


def _risk_level_from_decision(decision: dict[str, Any]) -> str:
    for condition in _string_list(decision.get("risk_conditions")):
        if condition.startswith("risk_level="):
            value = condition.split("=", 1)[1].split(";", 1)[0].strip()
            if value:
                return value
    return "unknown"


def _watch_evidence(
    decision: dict[str, Any],
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
) -> list[str]:
    evidence = [
        *(_string_list(decision.get("evidence"))[:5]),
        *(_string_list(risk.get("evidence") if risk else None)[:2]),
        *(_string_list(regime.get("evidence") if regime else None)[:2]),
        *_bounded_signal_evidence([signal for signal in signals if _has_usable_signal_evidence(signal)]),
    ]
    return _unique_ordered(evidence)[:10]


def _watch_record_source_artifacts(
    decision: dict[str, Any],
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    derivatives_records: list[dict[str, Any]] | None = None,
    macro_records: list[dict[str, Any]] | None = None,
    onchain_records: list[dict[str, Any]] | None = None,
) -> list[str]:
    return _unique_ordered(
        [
            DECISION_RECOMMENDATIONS_ARTIFACT,
            RISK_ASSESSMENT_ARTIFACT,
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *_string_list(decision.get("source_artifacts")),
            *(_string_list(risk.get("source_artifacts")) if risk else []),
            *(_string_list(regime.get("source_artifacts")) if regime else []),
            *([DERIVATIVES_MARKET_CONTEXT_ARTIFACT] if derivatives_records else []),
            *[
                artifact
                for record in derivatives_records or []
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *([MACRO_CALENDAR_CONTEXT_ARTIFACT] if macro_records else []),
            *[
                artifact
                for record in macro_records or []
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *([ONCHAIN_FLOW_CONTEXT_ARTIFACT] if onchain_records else []),
            *[
                artifact
                for record in onchain_records or []
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *[
                artifact
                for signal in signals
                for artifact in _string_list(signal.get("source_artifacts"))
            ],
            MARKET_STRATEGY_SIGNALS_ARTIFACT,
            QUANT_STRATEGY_RUNS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
        ]
    )


def _watch_source_artifacts(
    market_signals: dict[str, Any],
    market_regime: dict[str, Any],
    risk_assessment: dict[str, Any],
    decision_recommendations: dict[str, Any],
    derivatives_artifact: dict[str, Any] | None = None,
    macro_artifact: dict[str, Any] | None = None,
    onchain_artifact: dict[str, Any] | None = None,
) -> list[str]:
    return _unique_ordered(
        [
            DECISION_RECOMMENDATIONS_ARTIFACT,
            RISK_ASSESSMENT_ARTIFACT,
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *_string_list(decision_recommendations.get("source_artifacts")),
            *_string_list(risk_assessment.get("source_artifacts")),
            *_string_list(market_regime.get("source_artifacts")),
            *_string_list(market_signals.get("source_artifacts")),
            *([DERIVATIVES_MARKET_CONTEXT_ARTIFACT] if derivatives_artifact is not None else []),
            *_string_list(derivatives_artifact.get("source_artifacts") if derivatives_artifact else None),
            *([MACRO_CALENDAR_CONTEXT_ARTIFACT] if macro_artifact is not None else []),
            *_string_list(macro_artifact.get("source_artifacts") if macro_artifact else None),
            *([ONCHAIN_FLOW_CONTEXT_ARTIFACT] if onchain_artifact is not None else []),
            *_string_list(onchain_artifact.get("source_artifacts") if onchain_artifact else None),
            MARKET_STRATEGY_SIGNALS_ARTIFACT,
            QUANT_STRATEGY_RUNS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
        ]
    )


def _watch_artifact_warnings(decisions: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[str]:
    warnings = []
    if not decisions:
        warnings.append("No decision recommendation records were available for watch trigger generation.")
    linked = {
        _clean_text(record.get("linked_decision_record_id"), fallback="")
        for record in records
    }
    for decision in decisions:
        record_id = _clean_text(decision.get("record_id"), fallback="missing")
        if record_id not in linked:
            warnings.append(f"No usable evidence was available for {record_id}; no watch triggers were generated.")
        warnings.extend(_string_list(decision.get("warnings"))[:2])
    return _unique_ordered(warnings)


def _decision_source_artifacts(
    market_signals: dict[str, Any],
    market_regime: dict[str, Any],
    risk_assessment: dict[str, Any],
    strategy_artifact: dict[str, Any] | None,
    derivatives_artifact: dict[str, Any] | None = None,
    macro_artifact: dict[str, Any] | None = None,
    onchain_artifact: dict[str, Any] | None = None,
) -> list[str]:
    return _unique_ordered(
        [
            RISK_ASSESSMENT_ARTIFACT,
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *_string_list(risk_assessment.get("source_artifacts")),
            *_string_list(market_regime.get("source_artifacts")),
            *_string_list(market_signals.get("source_artifacts")),
            *([QUANT_STRATEGY_RUNS_ARTIFACT] if strategy_artifact is not None else []),
            *_string_list(strategy_artifact.get("source_artifacts") if strategy_artifact else None),
            *([DERIVATIVES_MARKET_CONTEXT_ARTIFACT] if derivatives_artifact is not None else []),
            *_string_list(derivatives_artifact.get("source_artifacts") if derivatives_artifact else None),
            *([MACRO_CALENDAR_CONTEXT_ARTIFACT] if macro_artifact is not None else []),
            *_string_list(macro_artifact.get("source_artifacts") if macro_artifact else None),
            *([ONCHAIN_FLOW_CONTEXT_ARTIFACT] if onchain_artifact is not None else []),
            *_string_list(onchain_artifact.get("source_artifacts") if onchain_artifact else None),
            MARKET_STRATEGY_SIGNALS_ARTIFACT,
            QUANT_STRATEGY_RUNS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
        ]
    )


def _decision_artifact_warnings(records: list[dict[str, Any]], artifact_warnings: list[str]) -> list[str]:
    warnings = list(artifact_warnings)
    if not records:
        warnings.append("No market, regime, or risk records were available for decision recommendations.")
    for record in records:
        warnings.extend(_string_list(record.get("warnings")))
    return _unique_ordered(warnings)


def _read_json_artifact(path, artifact: str, *, producer_stage: str, stage: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=stage,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact} is not valid JSON: {exc.msg}.",
            stage=stage,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{artifact} must be a JSON object.",
            stage=stage,
            exit_code=3,
        )
    return loaded


def _read_optional_strategy_artifact(
    run: RunContext,
    market_signals: dict[str, Any],
    *,
    stage: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    if QUANT_STRATEGY_RUNS_ARTIFACT not in _string_list(market_signals.get("source_artifacts")):
        return None, []
    path = run.analysis_dir / "quant_strategy_runs.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"{QUANT_STRATEGY_RUNS_ARTIFACT} was listed as a source artifact but was not found."]
    except JSONDecodeError as exc:
        return None, [f"{QUANT_STRATEGY_RUNS_ARTIFACT} is not valid JSON: {exc.msg}."]
    if not isinstance(loaded, dict):
        return None, [f"{QUANT_STRATEGY_RUNS_ARTIFACT} must be a JSON object."]
    return loaded, []


def _read_optional_derivatives_context(run: RunContext) -> tuple[dict[str, Any] | None, list[str]]:
    path = run.analysis_dir / "derivatives_market_context.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, []
    except JSONDecodeError as exc:
        return None, [f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}."]
    if not isinstance(loaded, dict):
        return None, [f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} must be a JSON object."]
    return loaded, []


def _read_optional_macro_calendar_context(run: RunContext) -> tuple[dict[str, Any] | None, list[str]]:
    path = run.analysis_dir / "macro_calendar_context.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, []
    except JSONDecodeError as exc:
        return None, [f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}."]
    if not isinstance(loaded, dict):
        return None, [f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} must be a JSON object."]
    return loaded, []


def _read_optional_onchain_flow_context(run: RunContext) -> tuple[dict[str, Any] | None, list[str]]:
    path = run.analysis_dir / "onchain_flow_context.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, []
    except JSONDecodeError as exc:
        return None, [f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}."]
    if not isinstance(loaded, dict):
        return None, [f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} must be a JSON object."]
    return loaded, []


def _signals_from_artifact(artifact: dict[str, Any], *, stage: str) -> list[dict[str, Any]]:
    signals = artifact.get("signals")
    if not isinstance(signals, list):
        raise PipelineError(
            f"{MARKET_SIGNALS_ARTIFACT} must contain a signals list.",
            stage=stage,
            exit_code=3,
        )
    for index, signal in enumerate(signals):
        if not isinstance(signal, dict):
            raise PipelineError(
                f"signals[{index}] must be a mapping.",
                stage=stage,
                exit_code=3,
            )
    return signals


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


def _records_from_optional_artifact(artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    records = artifact.get("records")
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _strategy_runs_from_optional_artifact(artifact: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    if artifact is None:
        return [], []
    runs = artifact.get("runs")
    if not isinstance(runs, list):
        return [], [f"{QUANT_STRATEGY_RUNS_ARTIFACT} must contain a runs list."]
    warnings = []
    result = []
    for index, run in enumerate(runs):
        if isinstance(run, dict):
            result.append(run)
        else:
            warnings.append(f"runs[{index}] in {QUANT_STRATEGY_RUNS_ARTIFACT} must be a mapping.")
    return result, warnings


def _created_at(artifact: dict[str, Any], now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc(now)
    created_at = artifact.get("created_at")
    if isinstance(created_at, str) and created_at.strip():
        return _format_utc(created_at)
    return _format_utc(None)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError(
                "created_at must include a UTC offset.",
                stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
                exit_code=3,
            )
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError(
                "created_at must be an ISO 8601 UTC string.",
                stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
                exit_code=3,
            ) from exc
        if timestamp.tzinfo is None:
            raise PipelineError(
                "created_at must include a UTC offset.",
                stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
                exit_code=3,
            )
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError(
            "created_at must be a datetime or ISO 8601 UTC string.",
            stage=BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
            exit_code=3,
        )
    return timestamp.isoformat().replace("+00:00", "Z")


def _has_usable_signal_evidence(signal: dict[str, Any]) -> bool:
    if signal.get("insufficient_data") is True:
        return False
    direction = signal.get("direction")
    if not isinstance(direction, str) or not direction.strip() or direction == "unknown":
        return False
    return bool(_string_list(signal.get("evidence")) or _mapping(signal.get("key_values")))


def _grouped_signals(signals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        key = ":".join(_clean_text(signal.get(field), fallback="missing") for field in ("source", "symbol", "timeframe"))
        groups.setdefault(key, []).append(signal)
    return dict(sorted(groups.items()))


def _group_value(signals: list[dict[str, Any]], field: str) -> str:
    return _clean_text(signals[0].get(field) if signals else None, fallback="missing")


def _latest_candle_time(signals: list[dict[str, Any]]) -> str:
    values = sorted(
        value
        for value in (_clean_text(signal.get("latest_candle_time"), fallback="") for signal in signals)
        if value
    )
    return values[-1] if values else "missing"


def _direction_counts(signals: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signal in signals:
        direction = _clean_text(signal.get("direction"), fallback="unknown")
        counts[direction] = counts.get(direction, 0) + 1
    return dict(sorted(counts.items()))


def _latest_regimes(signals: list[dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            value
            for signal in signals
            for value in [_clean_text(_mapping(signal.get("key_values")).get("latest_regime"), fallback="")]
            if value
        ]
    )


def _direction_conflicts(direction_counts: dict[str, int], signals: list[dict[str, Any]]) -> list[str]:
    conflicts = []
    if direction_counts.get("bullish", 0) > 0 and direction_counts.get("bearish", 0) > 0:
        conflicts.append("Upstream signals include both bullish and bearish directions for this market window.")
    if direction_counts.get("mixed", 0) > 0:
        conflicts.append("At least one upstream signal is already mixed.")
    if conflicts:
        conflicts.append(
            "Conflicting strategies: "
            + ", ".join(
                f"{_clean_text(signal.get('strategy_name'), fallback='unknown')}={_clean_text(signal.get('direction'), fallback='unknown')}"
                for signal in signals
            )
            + "."
        )
    return conflicts


def _is_range_regime(value: str) -> bool:
    lowered = value.lower()
    return "range" in lowered or "neutral" in lowered or "reversion_watch" in lowered


def _confidence(regime: str, signals: list[dict[str, Any]], conflicts: list[str]) -> str:
    if regime == "unknown" or not signals:
        return "low"
    if conflicts:
        return "low" if any(_clean_text(signal.get("confidence"), fallback="unknown") == "low" for signal in signals) else "medium"
    confidence_counts = _count_by_clean_text(signals, "confidence")
    if confidence_counts.get("high", 0) >= 2:
        return "high"
    if confidence_counts.get("high", 0) or confidence_counts.get("medium", 0):
        return "medium"
    return "low"


def _record_status(regime: str, usable: list[dict[str, Any]], warnings: list[str]) -> str:
    if not usable:
        return "insufficient_data"
    if regime == "unknown":
        return "unknown"
    if warnings:
        return "partial"
    return "succeeded"


def _uncertainty(signals: list[dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            item
            for signal in signals
            for item in _string_list(signal.get("uncertainty"))
        ]
    )


def _bounded_signal_evidence(signals: list[dict[str, Any]]) -> list[str]:
    evidence = []
    for signal in signals:
        for item in _string_list(signal.get("evidence"))[:2]:
            evidence.append(f"{_signal_name(signal)}: {item}")
    return evidence[:6]


def _record_source_artifacts(
    signals: list[dict[str, Any]],
    derivatives_records: list[dict[str, Any]] | None = None,
) -> list[str]:
    return _unique_ordered(
        [
            MARKET_SIGNALS_ARTIFACT,
            *[
                artifact
                for signal in signals
                for artifact in _string_list(signal.get("source_artifacts"))
            ],
            *(
                [DERIVATIVES_MARKET_CONTEXT_ARTIFACT]
                if derivatives_records
                else []
            ),
            *[
                artifact
                for record in derivatives_records or []
                for artifact in _string_list(record.get("source_artifacts"))
            ],
        ]
    )


def _source_artifacts(
    market_signals: dict[str, Any],
    strategy_artifact: dict[str, Any] | None,
    derivatives_artifact: dict[str, Any] | None = None,
) -> list[str]:
    return _unique_ordered(
        [
            MARKET_SIGNALS_ARTIFACT,
            *_string_list(market_signals.get("source_artifacts")),
            *([QUANT_STRATEGY_RUNS_ARTIFACT] if strategy_artifact is not None else []),
            *_string_list(strategy_artifact.get("source_artifacts") if strategy_artifact else None),
            *([DERIVATIVES_MARKET_CONTEXT_ARTIFACT] if derivatives_artifact is not None else []),
            *_string_list(derivatives_artifact.get("source_artifacts") if derivatives_artifact else None),
            MARKET_STRATEGY_SIGNALS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
        ]
    )


def _artifact_warnings(records: list[dict[str, Any]], strategy_warnings: list[str]) -> list[str]:
    warnings = list(strategy_warnings)
    if not records:
        warnings.append("No market signal records were available for regime assessment.")
    for record in records:
        warnings.extend(_string_list(record.get("warnings")))
    return _unique_ordered(warnings)


def _risk_group_keys(
    signals: list[dict[str, Any]],
    regime_records: list[dict[str, Any]],
    strategy_runs: list[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    return sorted(
        {
            *[_tuple_key(item) for item in signals],
            *[_tuple_key(item) for item in regime_records],
            *[_tuple_key(item) for item in strategy_runs],
        }
    )


def _signals_by_tuple(signals: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for signal in signals:
        groups.setdefault(_tuple_key(signal), []).append(signal)
    return groups


def _regime_by_tuple(records: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {_tuple_key(record): record for record in records}


def _strategy_runs_by_tuple(runs: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for run in runs:
        groups.setdefault(_tuple_key(run), []).append(run)
    return groups


def _derivatives_by_symbol(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        symbol = _clean_text(record.get("symbol"), fallback="")
        if symbol:
            groups.setdefault(symbol, []).append(record)
    return {symbol: sorted(items, key=_derivatives_sort_key) for symbol, items in groups.items()}


def _macro_calendar_context_by_symbol(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        symbols = [
            symbol
            for symbol in (_clean_text(value, fallback="") for value in _string_list(record.get("affected_assets")))
            if symbol
        ]
        if not symbols and _clean_text(record.get("context_type"), fallback="") in {
            "no_event_window",
            "source_availability",
        }:
            symbols = ["__global__"]
        for symbol in symbols:
            groups.setdefault(symbol, []).append(record)
    return {symbol: sorted(items, key=_macro_calendar_sort_key) for symbol, items in groups.items()}


def _macro_calendar_records_for_symbol(
    groups: dict[str, list[dict[str, Any]]],
    symbol: str,
) -> list[dict[str, Any]]:
    return _unique_macro_calendar_records([*groups.get(symbol, []), *groups.get("__global__", [])])


def _onchain_flow_records_for_symbol(records: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    base_asset = _symbol_base_asset(symbol)
    matched: list[dict[str, Any]] = []
    for record in records:
        context_type = _clean_text(record.get("context_type"), fallback="")
        asset = _clean_text(record.get("asset"), fallback="")
        chain = _clean_text(record.get("chain"), fallback="")
        if asset in {"ALL_CONFIGURED_ASSETS", "ALL_STABLECOINS"}:
            matched.append(record)
        elif asset and base_asset and asset == base_asset:
            matched.append(record)
        elif context_type == "exchange_flow_source_availability" and not asset:
            matched.append(record)
        elif chain == "bitcoin" and base_asset == "BTC":
            matched.append(record)
        elif chain == "ethereum" and base_asset == "ETH":
            matched.append(record)
    return _unique_onchain_flow_records(sorted(matched, key=_onchain_flow_sort_key))


def _tuple_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean_text(item.get("source"), fallback="missing"),
        _clean_text(item.get("symbol"), fallback="missing"),
        _clean_text(item.get("timeframe"), fallback="missing"),
    )


def _derivatives_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean_text(record.get("context_type"), fallback=""),
        _clean_text(record.get("period"), fallback=""),
        _clean_text(record.get("as_of"), fallback=""),
    )


def _macro_calendar_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _clean_text(record.get("context_type"), fallback=""),
        _clean_text(record.get("scheduled_at"), fallback=""),
        _clean_text(record.get("as_of"), fallback=""),
        _clean_text(record.get("context_id"), fallback=""),
    )


def _onchain_flow_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _clean_text(record.get("context_type"), fallback=""),
        _clean_text(record.get("asset"), fallback=""),
        _clean_text(record.get("chain"), fallback=""),
        _clean_text(record.get("period"), fallback=""),
        _clean_text(record.get("context_id"), fallback=""),
    )


def _latest_risk_candle_time(
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    strategy_runs: list[dict[str, Any]],
) -> str:
    values = [
        *[_clean_text(signal.get("latest_candle_time"), fallback="") for signal in signals],
        *([_clean_text(regime.get("latest_candle_time"), fallback="")] if regime else []),
        *[_clean_text(run.get("latest_candle_time"), fallback="") for run in strategy_runs],
    ]
    clean = sorted(value for value in values if value)
    return clean[-1] if clean else "missing"


def _data_quality_risks(
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    strategy_runs: list[dict[str, Any]],
) -> list[str]:
    risks = []
    for signal in signals:
        if signal.get("insufficient_data") is True:
            risks.append(f"{_signal_name(signal)} has insufficient upstream market signal data.")
    for run in strategy_runs:
        if run.get("status") == "insufficient_data":
            data_quality = _mapping(run.get("data_quality"))
            risks.append(
                f"{_strategy_run_name(run)} has insufficient OHLCV rows "
                f"({data_quality.get('row_count')} of {data_quality.get('minimum_required_rows')})."
            )
    if regime and _clean_text(regime.get("status"), fallback="") == "insufficient_data":
        risks.append("Market regime assessment is based on insufficient upstream evidence.")
    return _unique_ordered(risks)


def _signal_conflict_risks(signals: list[dict[str, Any]], regime: dict[str, Any] | None) -> list[str]:
    direction_counts = _direction_counts([signal for signal in signals if _has_usable_signal_evidence(signal)])
    risks = []
    if direction_counts.get("bullish", 0) > 0 and direction_counts.get("bearish", 0) > 0:
        risks.append("Bullish and bearish market signals conflict for this market window.")
    if direction_counts.get("mixed", 0) > 0:
        risks.append("At least one upstream market signal is mixed.")
    if regime and (_clean_text(regime.get("regime"), fallback="unknown") == "mixed" or _string_list(regime.get("conflicts"))):
        risks.append("Market regime assessment reports material signal conflict.")
    return _unique_ordered(risks)


def _volatility_risk(signals: list[dict[str, Any]]) -> dict[str, list[str]]:
    rising: list[str] = []
    blocking: list[str] = []
    evidence: list[str] = []
    severities: list[str] = []
    for signal in signals:
        key_values = _mapping(signal.get("key_values"))
        signal_name = _signal_name(signal)
        realized = _number(key_values.get("realized_volatility_pct"))
        target = _number(key_values.get("target_volatility_pct"))
        if realized is not None and target is not None and target > 0:
            if realized >= target * 2.0:
                message = f"{signal_name} realized_volatility_pct {realized} is at least 2x target {target}."
                rising.append(message)
                blocking.append("Extreme realized volatility blocks stronger action levels.")
                evidence.append(message)
                severities.append("extreme")
            elif realized >= target * 1.5:
                message = f"{signal_name} realized_volatility_pct {realized} is at least 1.5x target {target}."
                rising.append(message)
                blocking.append("Elevated realized volatility blocks stronger action levels.")
                evidence.append(message)
                severities.append("high")
            elif realized >= target * 1.2:
                message = f"{signal_name} realized_volatility_pct {realized} is above target {target}."
                rising.append(message)
                evidence.append(message)
                severities.append("medium")
        atr_pct = _number(key_values.get("atr_pct"))
        if atr_pct is not None:
            if atr_pct >= 8.0:
                message = f"{signal_name} atr_pct {atr_pct} is extremely elevated."
                rising.append(message)
                blocking.append("Extreme ATR volatility blocks stronger action levels.")
                evidence.append(message)
                severities.append("extreme")
            elif atr_pct >= 4.0:
                message = f"{signal_name} atr_pct {atr_pct} is elevated."
                rising.append(message)
                blocking.append("Elevated ATR volatility blocks stronger action levels.")
                evidence.append(message)
                severities.append("high")
    return {
        "rising": _unique_ordered(rising),
        "blocking": _unique_ordered(blocking),
        "evidence": _unique_ordered(evidence),
        "severities": _unique_ordered(severities),
    }


def _strategy_warning_risk(
    strategy_runs: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> dict[str, list[str]]:
    messages = _unique_ordered(
        [
            *[
                f"{_strategy_run_name(run)} warning: {message}"
                for run in strategy_runs
                for message in _warning_messages(run.get("warnings"))
            ],
            *[
                f"{_signal_name(signal)} uncertainty: {message}"
                for signal in signals
                for message in _string_list(signal.get("uncertainty"))
                if _looks_like_risk_note(message)
            ],
        ]
    )
    severities = []
    for message in messages:
        lowered = message.lower()
        if "extreme" in lowered:
            severities.append("extreme")
        elif any(token in lowered for token in ("elevated", "strong", "less reliable", "volatility", "atr")):
            severities.append("high")
        else:
            severities.append("medium")
    return {
        "rising": messages,
        "evidence": messages,
        "severities": _unique_ordered(severities),
    }


def _regime_risks(regime: dict[str, Any] | None) -> dict[str, list[str]]:
    if regime is None:
        return {
            "rising": ["Market regime assessment is missing for this market window."],
            "blocking": [],
            "evidence": [],
            "severities": ["medium"],
        }
    value = _clean_text(regime.get("regime"), fallback="unknown")
    confidence = _clean_text(regime.get("confidence"), fallback="unknown")
    status = _clean_text(regime.get("status"), fallback="unknown")
    rising: list[str] = []
    blocking: list[str] = []
    evidence = [f"market_regime={value}; confidence={confidence}; status={status}."]
    severities: list[str] = []
    if value == "unknown":
        rising.append("Market regime is unknown, so risk cannot be treated as low.")
        blocking.append("Unknown market regime blocks stronger action levels.")
    elif value == "mixed":
        rising.append("Market regime is mixed.")
        blocking.append("Mixed market regime blocks stronger action levels.")
        severities.append("high")
    elif value == "high_volatility":
        rising.append("Market regime is high_volatility.")
        blocking.append("High-volatility regime blocks stronger action levels.")
        severities.append("high")
    elif value == "trend_down":
        rising.append("Market regime is trend_down.")
        severities.append("medium")
    if confidence == "low" or status in {"partial", "unknown", "insufficient_data"}:
        rising.append("Market regime assessment has low confidence or partial status.")
        severities.append("medium")
    for item in _string_list(regime.get("warnings")):
        rising.append(f"Market regime warning: {item}")
        severities.append("medium")
    for item in _string_list(regime.get("uncertainty"))[:3]:
        if _looks_like_risk_note(item):
            rising.append(f"Market regime uncertainty: {item}")
            severities.append("medium")
    return {
        "rising": _unique_ordered(rising),
        "blocking": _unique_ordered(blocking),
        "evidence": _unique_ordered(evidence),
        "severities": _unique_ordered(severities),
    }


def _risk_level(severities: list[str], *, usable_evidence: bool) -> str:
    if not usable_evidence:
        return "unknown"
    if "extreme" in severities:
        return "extreme"
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _risk_status(risk_level: str, usable_evidence: bool, warnings: list[str]) -> str:
    if risk_level == "unknown" and not usable_evidence:
        return "insufficient_data"
    if risk_level == "unknown":
        return "unknown"
    if warnings:
        return "partial"
    return "succeeded"


def _risk_gates(risk_level: str) -> dict[str, Any]:
    if risk_level == "extreme":
        return {
            "block_strong_action": True,
            "cap_action_level": "NO_ACTION",
            "requires_invalidation": True,
        }
    if risk_level in {"high", "unknown"}:
        return {
            "block_strong_action": True,
            "cap_action_level": "WATCH",
            "requires_invalidation": True,
        }
    if risk_level == "medium":
        return {
            "block_strong_action": True,
            "cap_action_level": "TRY_SMALL",
            "requires_invalidation": True,
        }
    return {
        "block_strong_action": False,
        "cap_action_level": None,
        "requires_invalidation": False,
    }


def _risk_evidence(
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    *,
    volatility: dict[str, list[str]],
    strategy: dict[str, list[str]],
    regime_risks: dict[str, list[str]],
    derivatives: dict[str, Any],
    macro: dict[str, Any],
    onchain: dict[str, Any],
    risk_level: str,
) -> list[str]:
    evidence = [
        _counts_evidence("direction_counts", _direction_counts(signals)),
        *regime_risks["evidence"],
        *volatility["evidence"],
        *strategy["evidence"],
        *derivatives["evidence"],
        *derivatives["uncertainty"],
        *macro["evidence"],
        *macro["uncertainty"],
        *onchain["evidence"],
        *onchain["uncertainty"],
        *_bounded_signal_evidence([signal for signal in signals if _has_usable_signal_evidence(signal)]),
    ]
    if regime is None:
        evidence.append("No matching market regime record was available.")
    if risk_level == "low":
        evidence.append("No elevated risk factors were found in current bounded signal, regime, and optional context artifacts.")
    return _unique_ordered(evidence)


def _derivatives_context_effects(records: list[dict[str, Any]]) -> dict[str, Any]:
    rising: list[str] = []
    blocking: list[str] = []
    evidence: list[str] = []
    uncertainty: list[str] = []
    warnings: list[str] = []
    severities: list[str] = []
    supports_risk_assessment = False

    for record in records:
        context_type = _clean_text(record.get("context_type"), fallback="unknown")
        state = _clean_text(record.get("state"), fallback="unknown")
        status = _clean_text(record.get("status"), fallback="unknown")
        severity = _clean_text(record.get("severity"), fallback="unknown")
        evidence_line = (
            f"derivatives_context {context_type} state={state}; "
            f"severity={severity}; status={status}."
        )

        if status in {"failed", "unavailable", "stale", "degraded", "partial"} or state in {
            "unavailable",
            "stale",
            "insufficient_evidence",
        }:
            uncertainty.append(_derivatives_uncertainty_message(context_type, state, status))
            evidence.append(evidence_line)
            if context_type == "liquidation_availability" and state == "unavailable":
                rising.append(
                    "Derivatives context: liquidation summary is unavailable; risk must not be reduced by absence of liquidation evidence."
                )
                severities.append("medium")
            elif status in {"failed", "stale", "degraded", "partial"}:
                rising.append(f"Derivatives context {context_type} is {status}; assessment should remain conservative.")
                severities.append("medium")
            continue

        if state in {"neutral", "open_interest_level_only"} or severity in {"low", "unknown"}:
            evidence.append(evidence_line)
            continue

        message = _derivatives_risk_message(context_type=context_type, state=state, severity=severity)
        rising.append(message)
        evidence.append(evidence_line)
        supports_risk_assessment = True
        if severity == "high":
            blocking.append("High-severity derivatives context blocks stronger action levels.")
            severities.append("high")
        elif severity == "medium":
            severities.append("medium")

    return {
        "rising": _unique_ordered(rising),
        "blocking": _unique_ordered(blocking),
        "evidence": _unique_ordered(evidence),
        "uncertainty": _unique_ordered(uncertainty),
        "warnings": _unique_ordered(warnings),
        "severities": _unique_ordered(severities),
        "supports_risk_assessment": supports_risk_assessment,
    }


def _macro_calendar_context_effects(records: list[dict[str, Any]]) -> dict[str, Any]:
    rising: list[str] = []
    blocking: list[str] = []
    evidence: list[str] = []
    uncertainty: list[str] = []
    warnings: list[str] = []
    severities: list[str] = []
    scheduled_or_recent_ids: list[str] = []
    availability_issue_ids: list[str] = []
    no_event_ids: list[str] = []
    supports_risk_assessment = False

    for record in _unique_macro_calendar_records(records):
        context_type = _clean_text(record.get("context_type"), fallback="unknown")
        state = _clean_text(record.get("state"), fallback="unknown")
        status = _clean_text(record.get("status"), fallback="unknown")
        severity = _clean_text(record.get("severity"), fallback="unknown")
        event_name = _clean_text(record.get("event_name"), fallback=context_type)
        scheduled_at = _clean_text(record.get("scheduled_at"), fallback="unknown_time")
        context_id = _clean_text(record.get("context_id"), fallback="")
        importance = _clean_text(record.get("importance"), fallback="unknown")
        evidence_line = (
            f"macro_calendar_context {context_type} state={state}; "
            f"severity={severity}; status={status}; event={event_name}; scheduled_at={scheduled_at}."
        )
        evidence.append(evidence_line)
        warnings.extend(_string_list(record.get("warnings")))
        uncertainty.extend(_string_list(record.get("uncertainty")))

        if context_type == "no_event_window" or status == "no_event":
            if context_id:
                no_event_ids.append(context_id)
            uncertainty.append(
                "Macro calendar context no_event_window means checked sources returned no configured event; it cannot support lower risk by itself."
            )
            continue

        if context_type == "source_availability" or status in {"failed", "unavailable", "stale", "degraded", "partial"}:
            if context_id:
                availability_issue_ids.append(context_id)
            uncertainty.append(_macro_calendar_uncertainty_message(context_type, state, status))
            rising.append(
                f"Macro calendar context {context_type} is {status}; missing or degraded calendar evidence cannot support lower risk."
            )
            severities.append("medium")
            supports_risk_assessment = True
            continue

        if context_type in {"scheduled_catalyst", "recent_catalyst"}:
            if context_id:
                scheduled_or_recent_ids.append(context_id)
            rising.append(
                _macro_calendar_catalyst_risk_message(
                    context_type=context_type,
                    event_name=event_name,
                    scheduled_at=scheduled_at,
                    state=state,
                    severity=severity,
                    importance=importance,
                )
            )
            blocking.append(
                "Macro calendar context requires post-event confirmation before upgrading to stronger action levels."
            )
            if severity in {"high", "medium"} or importance in {"high", "medium"}:
                severities.append("medium")
            supports_risk_assessment = True

    return {
        "rising": _unique_ordered(rising),
        "blocking": _unique_ordered(blocking),
        "evidence": _unique_ordered(evidence),
        "uncertainty": _unique_ordered(uncertainty),
        "warnings": _unique_ordered(warnings),
        "severities": _unique_ordered(severities),
        "supports_risk_assessment": supports_risk_assessment,
        "scheduled_or_recent_ids": _unique_ordered(scheduled_or_recent_ids),
        "availability_issue_ids": _unique_ordered(availability_issue_ids),
        "no_event_ids": _unique_ordered(no_event_ids),
    }


def _onchain_flow_context_effects(records: list[dict[str, Any]]) -> dict[str, Any]:
    rising: list[str] = []
    blocking: list[str] = []
    evidence: list[str] = []
    uncertainty: list[str] = []
    warnings: list[str] = []
    severities: list[str] = []
    stress_context_ids: list[str] = []
    availability_issue_ids: list[str] = []
    normal_context_ids: list[str] = []
    supports_risk_assessment = False

    for record in _unique_onchain_flow_records(records):
        context_type = _clean_text(record.get("context_type"), fallback="unknown")
        state = _clean_text(record.get("state"), fallback="unknown")
        status = _clean_text(record.get("status"), fallback="unknown")
        severity = _clean_text(record.get("severity"), fallback="unknown")
        asset = _clean_text(record.get("asset"), fallback="unknown_asset")
        chain = _clean_text(record.get("chain"), fallback="unknown_chain")
        period = _clean_text(record.get("period"), fallback="unknown_period")
        context_id = _clean_text(record.get("context_id"), fallback="")
        evidence_line = (
            f"onchain_flow_context {context_type} state={state}; severity={severity}; "
            f"status={status}; asset={asset}; chain={chain}; period={period}."
        )
        evidence.append(evidence_line)
        warnings.extend(_string_list(record.get("warnings")))
        uncertainty.extend(_string_list(record.get("uncertainty")))

        if status in {"failed", "unavailable", "stale", "degraded", "partial"} or state in {
            "source_unavailable",
            "source_failed",
            "unavailable",
            "stale",
            "insufficient_evidence",
        }:
            if context_id:
                availability_issue_ids.append(context_id)
            uncertainty.append(_onchain_flow_uncertainty_message(context_type, state, status))
            rising.append(
                f"On-chain flow context {context_type} is {status}; missing or degraded flow evidence cannot support lower risk."
            )
            severities.append("medium")
            supports_risk_assessment = True
            continue

        if state in {"normal", "neutral"} or severity in {"low", "unknown"}:
            if context_id:
                normal_context_ids.append(context_id)
            continue

        if context_id:
            stress_context_ids.append(context_id)
        rising.append(_onchain_flow_risk_message(context_type=context_type, state=state, severity=severity))
        supports_risk_assessment = True
        if severity == "high":
            blocking.append("High-severity on-chain flow context blocks stronger action levels.")
            severities.append("high")
        elif severity == "medium":
            severities.append("medium")

    return {
        "rising": _unique_ordered(rising),
        "blocking": _unique_ordered(blocking),
        "evidence": _unique_ordered(evidence),
        "uncertainty": _unique_ordered(uncertainty),
        "warnings": _unique_ordered(warnings),
        "severities": _unique_ordered(severities),
        "supports_risk_assessment": supports_risk_assessment,
        "stress_context_ids": _unique_ordered(stress_context_ids),
        "availability_issue_ids": _unique_ordered(availability_issue_ids),
        "normal_context_ids": _unique_ordered(normal_context_ids),
    }


def _macro_calendar_uncertainty_message(context_type: str, state: str, status: str) -> str:
    return (
        f"Macro calendar context {context_type} is state={state}, status={status}; "
        "missing or degraded scheduled-event evidence cannot support lower risk."
    )


def _macro_calendar_catalyst_risk_message(
    *,
    context_type: str,
    event_name: str,
    scheduled_at: str,
    state: str,
    severity: str,
    importance: str,
) -> str:
    timing = "upcoming" if context_type == "scheduled_catalyst" else "recent"
    return (
        f"Macro calendar context: {timing} catalyst {event_name} at {scheduled_at} "
        f"requires conservative interpretation (state={state}, severity={severity}, importance={importance})."
    )


def _derivatives_regime_conflicts(regime: str, derivatives: dict[str, Any]) -> list[str]:
    if not derivatives.get("supports_risk_assessment"):
        return []
    if regime in {"unknown", "mixed"}:
        return []
    severities = set(_string_list(derivatives.get("severities")))
    if "high" in severities and regime in {"trend_up", "low_volatility", "range_bound"}:
        return ["High-severity derivatives context qualifies the market regime."]
    if "medium" in severities and regime == "trend_up":
        return ["Derivatives context adds leverage or liquidity stress to the trend_up regime."]
    return []


def _derivatives_uncertainty_message(context_type: str, state: str, status: str) -> str:
    return (
        f"Derivatives context {context_type} is state={state}, status={status}; "
        "missing or degraded derivatives evidence cannot support lower risk."
    )


def _onchain_flow_uncertainty_message(context_type: str, state: str, status: str) -> str:
    return (
        f"On-chain flow context {context_type} is state={state}, status={status}; "
        "missing or degraded on-chain flow evidence cannot support lower risk."
    )


def _onchain_flow_risk_message(*, context_type: str, state: str, severity: str) -> str:
    state_messages = {
        "sharp_exchange_inflow": "sharp exchange inflow can indicate elevated sell-side transfer pressure",
        "exchange_inflow": "exchange inflow can indicate sell-side transfer pressure",
        "sharp_exchange_outflow": "sharp exchange outflow is abnormal exchange-flow context",
        "exchange_outflow": "exchange outflow is abnormal exchange-flow context",
        "sharp_stablecoin_supply_contraction": "sharp stablecoin supply contraction suggests liquidity pressure",
        "stablecoin_supply_contraction": "stablecoin supply contraction suggests liquidity pressure",
        "sharp_stablecoin_supply_expansion": "sharp stablecoin supply expansion is abnormal liquidity context",
        "stablecoin_supply_expansion": "stablecoin supply expansion is abnormal liquidity context",
        "surging_chain_activity": "surging chain activity suggests abnormal network usage",
        "elevated_chain_activity": "elevated chain activity suggests abnormal network usage",
        "severe_network_congestion": "severe network congestion indicates settlement friction",
        "elevated_network_congestion": "elevated network congestion indicates settlement friction",
    }
    detail = state_messages.get(state, f"{context_type} state {state} requires conservative interpretation")
    return f"On-chain flow context: {detail} ({severity} severity)."


def _derivatives_risk_message(*, context_type: str, state: str, severity: str) -> str:
    state_messages = {
        "extreme_positive_funding": "extreme positive funding suggests crowded long leverage pressure",
        "extreme_negative_funding": "extreme negative funding suggests crowded short leverage pressure",
        "elevated_positive_funding": "elevated positive funding suggests leverage pressure",
        "elevated_negative_funding": "elevated negative funding suggests leverage pressure",
        "sharp_open_interest_expansion": "sharp open-interest expansion suggests leverage is building",
        "open_interest_expansion": "open-interest expansion suggests leverage is building",
        "premium_stressed": "premium stress indicates derivatives market pressure",
        "premium_stretched": "premium stretch indicates derivatives market pressure",
        "premium_inverted": "premium inversion indicates derivatives market pressure",
        "basis_stressed": "basis stress indicates derivatives market pressure",
        "basis_stretched": "basis stretch indicates derivatives market pressure",
        "basis_inverted": "basis inversion indicates derivatives market pressure",
        "spread_stressed": "spread stress indicates liquidity degradation",
        "spread_wide": "wide spread indicates liquidity degradation",
        "depth_imbalanced": "depth imbalance indicates liquidity degradation",
    }
    detail = state_messages.get(state, f"{context_type} state {state} requires conservative interpretation")
    return f"Derivatives context: {detail} ({severity} severity)."


def _risk_record_warnings(regime: dict[str, Any] | None, usable_evidence: bool) -> list[str]:
    warnings = []
    if regime is None:
        warnings.append("No matching market regime assessment record was available.")
    if not usable_evidence:
        warnings.append("No usable upstream risk evidence was available; risk level is unknown.")
    return warnings


def _risk_record_source_artifacts(
    signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    strategy_runs: list[dict[str, Any]],
    derivatives_records: list[dict[str, Any]],
    macro_records: list[dict[str, Any]],
    onchain_records: list[dict[str, Any]],
) -> list[str]:
    return _unique_ordered(
        [
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *(_string_list(regime.get("source_artifacts")) if regime else []),
            *(
                [DERIVATIVES_MARKET_CONTEXT_ARTIFACT]
                if derivatives_records
                else []
            ),
            *[
                artifact
                for record in derivatives_records
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *(
                [MACRO_CALENDAR_CONTEXT_ARTIFACT]
                if macro_records
                else []
            ),
            *[
                artifact
                for record in macro_records
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *(
                [ONCHAIN_FLOW_CONTEXT_ARTIFACT]
                if onchain_records
                else []
            ),
            *[
                artifact
                for record in onchain_records
                for artifact in _string_list(record.get("source_artifacts"))
            ],
            *[
                artifact
                for signal in signals
                for artifact in _string_list(signal.get("source_artifacts"))
            ],
            *[
                artifact
                for run in strategy_runs
                for artifact in _string_list(run.get("source_artifacts"))
            ],
        ]
    )


def _risk_source_artifacts(
    market_signals: dict[str, Any],
    market_regime: dict[str, Any],
    strategy_artifact: dict[str, Any] | None,
    derivatives_artifact: dict[str, Any] | None = None,
    macro_artifact: dict[str, Any] | None = None,
    onchain_artifact: dict[str, Any] | None = None,
) -> list[str]:
    return _unique_ordered(
        [
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *_string_list(market_regime.get("source_artifacts")),
            *_string_list(market_signals.get("source_artifacts")),
            *([QUANT_STRATEGY_RUNS_ARTIFACT] if strategy_artifact is not None else []),
            *_string_list(strategy_artifact.get("source_artifacts") if strategy_artifact else None),
            *([DERIVATIVES_MARKET_CONTEXT_ARTIFACT] if derivatives_artifact is not None else []),
            *_string_list(derivatives_artifact.get("source_artifacts") if derivatives_artifact else None),
            *([MACRO_CALENDAR_CONTEXT_ARTIFACT] if macro_artifact is not None else []),
            *_string_list(macro_artifact.get("source_artifacts") if macro_artifact else None),
            *([ONCHAIN_FLOW_CONTEXT_ARTIFACT] if onchain_artifact is not None else []),
            *_string_list(onchain_artifact.get("source_artifacts") if onchain_artifact else None),
            MARKET_STRATEGY_SIGNALS_ARTIFACT,
            MARKET_DATA_VIEWS_ARTIFACT,
        ]
    )


def _risk_artifact_warnings(records: list[dict[str, Any]], artifact_warnings: list[str]) -> list[str]:
    warnings = list(artifact_warnings)
    if not records:
        warnings.append("No market or regime records were available for risk assessment.")
    for record in records:
        warnings.extend(_string_list(record.get("warnings")))
    return _unique_ordered(warnings)


def _has_usable_risk_evidence(signals: list[dict[str, Any]], regime: dict[str, Any] | None) -> bool:
    if any(_has_usable_signal_evidence(signal) for signal in signals):
        return True
    if not regime:
        return False
    return _clean_text(regime.get("regime"), fallback="unknown") not in {"unknown", "missing"} and bool(
        _string_list(regime.get("evidence"))
    )


def _looks_like_risk_note(value: str) -> bool:
    lowered = value.lower()
    if any(
        phrase in lowered
        for phrase in (
            "not position sizing",
            "position sizing instruction",
            "not a forecast",
            "return forecast",
            "research material",
            "research assumption",
            "not trading advice",
            "bounded sensitivity context",
            "not optimization output",
            "historical volatility context",
            "not a live stop",
        )
    ):
        return False
    return any(
        token in lowered
        for token in (
            "risk",
            "volatility",
            "volatile",
            "drawdown",
            "conflict",
            "sensitivity",
            "invalid",
            "insufficient",
            "warning",
            "less reliable",
            "elevated",
            "downtrend",
            "uptrend",
        )
    )


def _warning_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    messages = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("message"), str):
            messages.append(item["message"])
        elif isinstance(item, str) and item.strip():
            messages.append(item)
    return messages


def _strategy_run_name(run: dict[str, Any]) -> str:
    return ":".join(
        _clean_text(run.get(field), fallback="unknown")
        for field in ("strategy_name", "source", "symbol", "timeframe")
    )


def _record_zero_risk_counts(run: RunContext) -> None:
    run.manifest["counts"]["risk_assessment_records"] = 0
    run.manifest["counts"]["risk_assessment_unknown_records"] = 0
    run.manifest["counts"]["risk_assessment_high_or_extreme_records"] = 0
    run.manifest["counts"]["risk_assessment_blocking_records"] = 0
    run.manifest["counts"]["risk_assessment_derivatives_context_records"] = 0
    run.manifest["counts"]["risk_assessment_derivatives_influenced_records"] = 0
    run.manifest["counts"]["risk_assessment_macro_calendar_context_records"] = 0
    run.manifest["counts"]["risk_assessment_macro_calendar_influenced_records"] = 0
    run.manifest["counts"]["risk_assessment_onchain_flow_context_records"] = 0
    run.manifest["counts"]["risk_assessment_onchain_flow_influenced_records"] = 0


def _record_zero_decision_recommendation_counts(run: RunContext) -> None:
    run.manifest["counts"]["decision_recommendation_records"] = 0
    run.manifest["counts"]["decision_recommendation_actionable_records"] = 0
    run.manifest["counts"]["decision_recommendation_non_actionable_records"] = 0
    run.manifest["counts"]["decision_recommendation_risk_blocked_records"] = 0
    run.manifest["counts"]["decision_recommendation_derivatives_context_records"] = 0
    run.manifest["counts"]["decision_recommendation_derivatives_linked_records"] = 0
    run.manifest["counts"]["decision_recommendation_macro_calendar_context_records"] = 0
    run.manifest["counts"]["decision_recommendation_macro_calendar_linked_records"] = 0
    run.manifest["counts"]["decision_recommendation_onchain_flow_context_records"] = 0
    run.manifest["counts"]["decision_recommendation_onchain_flow_linked_records"] = 0


def _record_watch_trigger_counts(run: RunContext, records: list[dict[str, Any]]) -> None:
    run.manifest["counts"]["watch_trigger_records"] = len(records)
    run.manifest["counts"]["watch_trigger_linked_records"] = sum(
        1 for record in records if _clean_text(record.get("linked_decision_record_id"), fallback="") != "missing"
    )
    for trigger_type in TRIGGER_TYPES:
        run.manifest["counts"][f"watch_trigger_{trigger_type}_records"] = sum(
            1 for record in records if record["type"] == trigger_type
        )


def _record_zero_watch_trigger_counts(run: RunContext) -> None:
    run.manifest["counts"]["watch_trigger_records"] = 0
    run.manifest["counts"]["watch_trigger_linked_records"] = 0
    run.manifest["counts"]["watch_trigger_derivatives_context_records"] = 0
    run.manifest["counts"]["watch_trigger_derivatives_linked_records"] = 0
    run.manifest["counts"]["watch_trigger_macro_calendar_context_records"] = 0
    run.manifest["counts"]["watch_trigger_macro_calendar_linked_records"] = 0
    run.manifest["counts"]["watch_trigger_onchain_flow_context_records"] = 0
    run.manifest["counts"]["watch_trigger_onchain_flow_linked_records"] = 0
    for trigger_type in TRIGGER_TYPES:
        run.manifest["counts"][f"watch_trigger_{trigger_type}_records"] = 0


def _count_by_clean_text(signals: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signal in signals:
        value = _clean_text(signal.get(field), fallback="unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _counts_evidence(label: str, counts: dict[str, int]) -> str:
    if not counts:
        return f"{label}: none."
    return f"{label}: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) + "."


def _signal_name(signal: dict[str, Any]) -> str:
    return ":".join(
        _clean_text(signal.get(field), fallback="unknown")
        for field in ("strategy_name", "source", "symbol", "timeframe")
    )


def _quant_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant")
    return isinstance(quant, dict) and quant.get("enabled") is True


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


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


def _unique_onchain_flow_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for record in records:
        key = _clean_text(record.get("context_id"), fallback="")
        if not key:
            key = ":".join(
                _clean_text(record.get(field), fallback="")
                for field in ("context_type", "asset", "chain", "period", "status")
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
