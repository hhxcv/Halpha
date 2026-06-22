from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_event_market_confluence"
TEXT_EVENT_SIGNALS_ARTIFACT = "analysis/text_event_signals.json"
MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
STRATEGY_GATES_ARTIFACT = "analysis/strategy_effectiveness_gates.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
EVENT_MARKET_CONFLUENCE_ARTIFACT = "analysis/event_market_confluence.json"
EVENT_MARKET_CONFLUENCE_ARTIFACT_TYPE = "event_market_confluence"
CONSTRUCTIVE_ACTIONS = {"STRONG_DO", "DO", "TRY_SMALL"}
DEFENSIVE_ACTIONS = {"AVOID", "EXIT_OR_REDUCE", "HEDGE_OR_PROTECT"}


def build_event_market_confluence(config: dict[str, Any], run: RunContext) -> list[str]:
    if not _text_enabled(config):
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    event_signals = _read_optional_artifact(
        run.analysis_dir / "text_event_signals.json",
        TEXT_EVENT_SIGNALS_ARTIFACT,
        records_key="signals",
    )
    if event_signals is None:
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    market_signals = _read_optional_artifact(run.analysis_dir / "market_signals.json", MARKET_SIGNALS_ARTIFACT, records_key="signals")
    strategy_gates = _read_optional_artifact(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        STRATEGY_GATES_ARTIFACT,
        records_key="records",
        fallback_key="gates",
    )
    risk_assessment = _read_optional_artifact(
        run.analysis_dir / "risk_assessment.json",
        RISK_ASSESSMENT_ARTIFACT,
        records_key="records",
    )
    decision_recommendations = _read_optional_artifact(
        run.analysis_dir / "decision_recommendations.json",
        DECISION_RECOMMENDATIONS_ARTIFACT,
        records_key="records",
    )
    watch_triggers = _read_optional_artifact(
        run.analysis_dir / "watch_triggers.json",
        WATCH_TRIGGERS_ARTIFACT,
        records_key="records",
    )

    comparison_artifacts = [
        artifact
        for artifact in (market_signals, strategy_gates, risk_assessment, decision_recommendations, watch_triggers)
        if artifact is not None
    ]
    if not comparison_artifacts:
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    records = _confluence_records(
        event_signals["signals"],
        market_signals=_records(market_signals, "signals"),
        strategy_gates=_records(strategy_gates, "records", fallback_key="gates"),
        risk_records=_records(risk_assessment, "records"),
        decision_records=_records(decision_recommendations, "records"),
        watch_records=_records(watch_triggers, "records"),
    )
    warnings = _artifact_warnings(records)
    errors: list[dict[str, Any]] = []
    artifact = {
        "schema_version": 1,
        "artifact_type": EVENT_MARKET_CONFLUENCE_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _utc_timestamp(),
        "source_artifacts": _source_artifacts(
            event_signals,
            market_signals,
            strategy_gates,
            risk_assessment,
            decision_recommendations,
            watch_triggers,
        ),
        "coverage": _coverage(records),
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }
    write_json(run.analysis_dir / "event_market_confluence.json", artifact)
    run.manifest["artifacts"]["event_market_confluence"] = EVENT_MARKET_CONFLUENCE_ARTIFACT
    _record_manifest_summary(run, records=records, warnings=warnings, errors=errors, status="succeeded")
    return [EVENT_MARKET_CONFLUENCE_ARTIFACT]


def _read_optional_artifact(
    path: Path,
    artifact_name: str,
    *,
    records_key: str,
    fallback_key: str | None = None,
) -> dict[str, Any] | None:
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
    key = records_key if isinstance(artifact.get(records_key), list) else fallback_key
    if key is not None and isinstance(artifact.get(key), list):
        return artifact
    raise PipelineError(f"{artifact_name} is invalid: {records_key} must be a list.", stage=STAGE_NAME, exit_code=3)


def _confluence_records(
    event_signals: list[dict[str, Any]],
    *,
    market_signals: list[dict[str, Any]],
    strategy_gates: list[dict[str, Any]],
    risk_records: list[dict[str, Any]],
    decision_records: list[dict[str, Any]],
    watch_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped_events = _event_signals_by_symbol(event_signals)
    market_groups = _group_by_symbol_timeframe(market_signals)
    risk_groups = _group_by_symbol_timeframe(risk_records)
    decision_groups = _group_by_symbol_timeframe(decision_records)
    watch_groups = _group_by_symbol_timeframe(watch_records)
    gate_groups = _strategy_gates_by_symbol(strategy_gates)
    keys = _record_keys(grouped_events, market_groups, risk_groups, decision_groups, watch_groups)
    records = []
    for key in keys:
        symbol, timeframe = key
        symbol_events = [*grouped_events.get(symbol, []), *grouped_events.get(None, [])]
        markets = market_groups.get(key, [])
        risk = _first(risk_groups.get(key, []))
        decision = _first(decision_groups.get(key, []))
        watches = watch_groups.get(key, [])
        gates = gate_groups.get(symbol, [])
        records.append(
            _confluence_record(
                symbol=symbol,
                timeframe=timeframe,
                event_signals=symbol_events,
                market_signals=markets,
                strategy_gates=gates,
                risk=risk,
                decision=decision,
                watch_triggers=watches,
            )
        )
    return records


def _confluence_record(
    *,
    symbol: str,
    timeframe: str,
    event_signals: list[dict[str, Any]],
    market_signals: list[dict[str, Any]],
    strategy_gates: list[dict[str, Any]],
    risk: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    watch_triggers: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted_events = [signal for signal in event_signals if signal.get("status") == "accepted"]
    event_bias_summary = _event_bias_summary(accepted_events)
    quant_direction_summary = _quant_direction_summary(market_signals)
    decision_action_level = _clean_text(decision.get("action_level") if decision else None, fallback="unknown")
    relationship = _relationship(
        event_bias=event_bias_summary,
        quant_direction=quant_direction_summary,
        decision_action_level=decision_action_level,
        accepted_events=accepted_events,
    )
    risk_effect = _risk_effect(accepted_events, risk)
    return {
        "confluence_id": f"event_market_confluence:{symbol}:{timeframe}",
        "status": "succeeded",
        "symbol": symbol,
        "timeframe": timeframe,
        "relationship": relationship,
        "event_bias_summary": event_bias_summary,
        "quant_direction_summary": quant_direction_summary,
        "decision_action_level": decision_action_level,
        "risk_effect": risk_effect,
        "interpretation": _interpretation(relationship, event_bias_summary, quant_direction_summary, decision_action_level),
        "watch_implications": _watch_implications(relationship, accepted_events, watch_triggers),
        "evidence": _evidence(accepted_events, event_signals, market_signals, strategy_gates, risk, decision),
        "uncertainty": _uncertainty(relationship, accepted_events, market_signals, decision),
        "linked_event_signal_ids": _signal_ids(event_signals),
        "linked_decision_record_ids": _decision_ids(decision),
        "warnings": _record_warnings(relationship, event_signals, market_signals, decision),
        "source_artifacts": _record_source_artifacts(event_signals, market_signals, strategy_gates, risk, decision, watch_triggers),
    }


def _relationship(
    *,
    event_bias: str,
    quant_direction: str,
    decision_action_level: str,
    accepted_events: list[dict[str, Any]],
) -> str:
    if not accepted_events:
        return "insufficient_event_evidence"
    if event_bias in {"unknown", "neutral"} or quant_direction in {"unknown", "mixed"}:
        return "independent"
    if event_bias == "supportive":
        if quant_direction == "bullish" or decision_action_level in CONSTRUCTIVE_ACTIONS:
            return "confluence"
        if quant_direction == "bearish" or decision_action_level in DEFENSIVE_ACTIONS:
            return "conflict"
    if event_bias == "adverse":
        if quant_direction == "bearish" or decision_action_level in DEFENSIVE_ACTIONS:
            return "confluence"
        if quant_direction == "bullish" or decision_action_level in CONSTRUCTIVE_ACTIONS:
            return "conflict"
    return "independent"


def _event_bias_summary(events: list[dict[str, Any]]) -> str:
    values = [_clean_text(event.get("event_bias"), fallback="unknown") for event in events]
    known = [value for value in values if value not in {"unknown", "neutral"}]
    if not known:
        return "unknown" if not values else "neutral"
    unique = set(known)
    if len(unique) > 1 or "mixed" in unique:
        return "mixed"
    return known[0]


def _quant_direction_summary(market_signals: list[dict[str, Any]]) -> str:
    directions = [_clean_text(signal.get("direction"), fallback="unknown") for signal in market_signals]
    usable = [direction for direction in directions if direction in {"bullish", "bearish"}]
    if not usable:
        return "unknown"
    bullish = usable.count("bullish")
    bearish = usable.count("bearish")
    if bullish > bearish:
        return "bullish"
    if bearish > bullish:
        return "bearish"
    return "mixed"


def _risk_effect(events: list[dict[str, Any]], risk: dict[str, Any] | None) -> str:
    risk_level = _clean_text(risk.get("risk_level") if risk else None, fallback="unknown")
    if any(event.get("risk_impact") == "risk_up" for event in events):
        return "risk_watch"
    if risk_level in {"high", "extreme"}:
        return "do_not_upgrade_due_to_risk"
    return "do_not_upgrade"


def _interpretation(relationship: str, event_bias: str, quant_direction: str, action_level: str) -> str:
    if relationship == "confluence":
        return (
            f"Accepted event evidence is {event_bias} and current quant or decision evidence is aligned; "
            "this is explanatory only."
        )
    if relationship == "conflict":
        return (
            f"Accepted event evidence is {event_bias} while quant direction is {quant_direction} "
            f"or decision action is {action_level}; keep the conflict visible."
        )
    if relationship == "insufficient_event_evidence":
        return "Event evidence did not pass deterministic acceptance gates; do not infer event-market confluence."
    return "Event evidence is independent or too neutral to modify the current quant and decision view."


def _watch_implications(
    relationship: str,
    accepted_events: list[dict[str, Any]],
    watch_triggers: list[dict[str, Any]],
) -> list[str]:
    implications = []
    if relationship == "conflict":
        implications.append("Review event-quant conflict before using stronger decision bias.")
    if relationship == "confluence" and accepted_events:
        implications.append("Use event evidence only as context; do not upgrade action levels from events alone.")
    if relationship == "insufficient_event_evidence":
        implications.append("Wait for accepted event evidence before discussing event confluence.")
    for trigger in watch_triggers[:3]:
        condition = trigger.get("condition")
        if isinstance(condition, str) and condition.strip():
            implications.append(condition.strip())
    return _unique(implications)


def _evidence(
    accepted_events: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    market_signals: list[dict[str, Any]],
    strategy_gates: list[dict[str, Any]],
    risk: dict[str, Any] | None,
    decision: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    evidence = []
    for event in (accepted_events or all_events)[:5]:
        evidence.append(
            {
                "type": "event_signal",
                "event_signal_id": event.get("event_signal_id"),
                "status": event.get("status"),
                "event_bias": event.get("event_bias"),
                "primary_category": event.get("primary_category"),
                "confidence": event.get("confidence"),
            }
        )
    for signal in market_signals[:5]:
        evidence.append(
            {
                "type": "market_signal",
                "signal_id": signal.get("signal_id"),
                "direction": signal.get("direction"),
                "confidence": signal.get("confidence"),
                "source_artifacts": signal.get("source_artifacts") or [],
            }
        )
    for gate in strategy_gates[:3]:
        evidence.append(
            {
                "type": "strategy_gate",
                "strategy_name": gate.get("strategy_name"),
                "status": gate.get("status") or gate.get("gate_status"),
                "source_artifacts": gate.get("source_artifacts") or [],
            }
        )
    if risk is not None:
        evidence.append(
            {
                "type": "risk_assessment",
                "record_id": risk.get("record_id"),
                "risk_level": risk.get("risk_level"),
                "source_artifacts": risk.get("source_artifacts") or [],
            }
        )
    if decision is not None:
        evidence.append(
            {
                "type": "decision_recommendation",
                "record_id": decision.get("record_id"),
                "action_level": decision.get("action_level"),
                "decision_bias": decision.get("decision_bias"),
                "source_artifacts": decision.get("source_artifacts") or [],
            }
        )
    return evidence


def _uncertainty(
    relationship: str,
    accepted_events: list[dict[str, Any]],
    market_signals: list[dict[str, Any]],
    decision: dict[str, Any] | None,
) -> list[str]:
    uncertainty = ["Event confluence is explanatory and must not upgrade action levels by itself."]
    if not accepted_events:
        uncertainty.append("No accepted event signal evidence is available for this market relationship.")
    if not market_signals:
        uncertainty.append("No market signal evidence is available for direct event-quant comparison.")
    if decision is None:
        uncertainty.append("No decision recommendation record is available for this market relationship.")
    if relationship == "conflict":
        uncertainty.append("Event and quant or decision evidence conflict; keep both sides visible.")
    return uncertainty


def _record_warnings(
    relationship: str,
    event_signals: list[dict[str, Any]],
    market_signals: list[dict[str, Any]],
    decision: dict[str, Any] | None,
) -> list[str]:
    warnings = []
    if relationship == "insufficient_event_evidence":
        warnings.append("insufficient_event_evidence")
    if not market_signals:
        warnings.append("market_signal_evidence_missing")
    if decision is None:
        warnings.append("decision_recommendation_missing")
    for signal in event_signals:
        for warning in signal.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _record_source_artifacts(*items: Any) -> list[str]:
    artifacts = [TEXT_EVENT_SIGNALS_ARTIFACT]
    for item in items:
        if isinstance(item, list):
            for value in item:
                artifacts.extend(_string_list(value.get("source_artifacts") if isinstance(value, dict) else None))
        elif isinstance(item, dict):
            artifacts.extend(_string_list(item.get("source_artifacts")))
    return _unique(artifacts)


def _source_artifacts(*artifacts: dict[str, Any] | None) -> list[str]:
    source = [TEXT_EVENT_SIGNALS_ARTIFACT]
    for artifact in artifacts:
        if artifact is None:
            continue
        source.extend(_string_list(artifact.get("source_artifacts")))
        artifact_type = artifact.get("artifact_type")
        if artifact_type == "market_signals":
            source.append(MARKET_SIGNALS_ARTIFACT)
        elif artifact_type == "strategy_effectiveness_gates":
            source.append(STRATEGY_GATES_ARTIFACT)
        elif artifact_type == "risk_assessment":
            source.append(RISK_ASSESSMENT_ARTIFACT)
        elif artifact_type == "decision_recommendations":
            source.append(DECISION_RECOMMENDATIONS_ARTIFACT)
        elif artifact_type == "watch_triggers":
            source.append(WATCH_TRIGGERS_ARTIFACT)
    return _unique(source)


def _coverage(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "records": len(records),
        "confluence_records": _relationship_count(records, "confluence"),
        "conflict_records": _relationship_count(records, "conflict"),
        "independent_records": _relationship_count(records, "independent"),
        "insufficient_event_evidence_records": _relationship_count(records, "insufficient_event_evidence"),
        "unknown_records": _relationship_count(records, "unknown"),
        "records_with_decision_links": sum(1 for record in records if record["linked_decision_record_ids"]),
        "records_with_event_links": sum(1 for record in records if record["linked_event_signal_ids"]),
    }


def _relationship_count(records: list[dict[str, Any]], relationship: str) -> int:
    return sum(1 for record in records if record["relationship"] == relationship)


def _record_manifest_summary(
    run: RunContext,
    *,
    records: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
) -> None:
    coverage = _coverage(records)
    run.manifest["counts"]["event_market_confluence_records"] = coverage["records"]
    run.manifest["counts"]["event_market_confluence_confluence"] = coverage["confluence_records"]
    run.manifest["counts"]["event_market_confluence_conflict"] = coverage["conflict_records"]
    run.manifest["counts"]["event_market_confluence_independent"] = coverage["independent_records"]
    run.manifest["counts"]["event_market_confluence_insufficient_event_evidence"] = coverage[
        "insufficient_event_evidence_records"
    ]
    run.manifest["event_market_confluence"] = {
        "status": status,
        "artifacts": [EVENT_MARKET_CONFLUENCE_ARTIFACT] if status == "succeeded" else [],
        "records": coverage["records"],
        "confluence": coverage["confluence_records"],
        "conflict": coverage["conflict_records"],
        "insufficient_event_evidence": coverage["insufficient_event_evidence_records"],
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _artifact_warnings(records: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for record in records:
        for warning in record.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _record_keys(
    event_groups: dict[str | None, list[dict[str, Any]]],
    *groups: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[tuple[str, str]]:
    keys = {key for group in groups for key in group}
    for symbol in event_groups:
        if symbol is not None and not any(key[0] == symbol for key in keys):
            keys.add((symbol, "event"))
    return sorted(keys)


def _event_signals_by_symbol(signals: list[dict[str, Any]]) -> dict[str | None, list[dict[str, Any]]]:
    grouped: dict[str | None, list[dict[str, Any]]] = {}
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        symbol = signal.get("symbol")
        key = str(symbol) if isinstance(symbol, str) and symbol.strip() else None
        grouped.setdefault(key, []).append(signal)
    return grouped


def _group_by_symbol_timeframe(records: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        symbol = _clean_text(record.get("symbol"), fallback="missing")
        timeframe = _clean_text(record.get("timeframe"), fallback="missing")
        if symbol == "missing":
            continue
        grouped.setdefault((symbol, timeframe), []).append(record)
    return grouped


def _strategy_gates_by_symbol(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        symbol = _clean_text(record.get("symbol"), fallback="missing")
        if symbol == "missing":
            continue
        grouped.setdefault(symbol, []).append(record)
    return grouped


def _records(artifact: dict[str, Any] | None, key: str, *, fallback_key: str | None = None) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    records = artifact.get(key)
    if not isinstance(records, list) and fallback_key is not None:
        records = artifact.get(fallback_key)
    return [record for record in records or [] if isinstance(record, dict)]


def _first(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    return records[0] if records else None


def _signal_ids(signals: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            str(signal.get("event_signal_id"))
            for signal in signals
            if isinstance(signal.get("event_signal_id"), str) and signal.get("event_signal_id")
        ]
    )


def _decision_ids(decision: dict[str, Any] | None) -> list[str]:
    if decision is None or not isinstance(decision.get("record_id"), str):
        return []
    return [decision["record_id"]]


def _text_enabled(config: dict[str, Any]) -> bool:
    text = config.get("text") if isinstance(config.get("text"), dict) else {}
    return bool(text.get("enabled"))


def _clean_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _unique(values: list[str]) -> list[str]:
    unique = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
