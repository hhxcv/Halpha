from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_event_intelligence_assessment"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"
TEXT_EVENT_TOPICS_ARTIFACT = "analysis/text_event_topics.json"
TEXT_EVENT_SIGNALS_ARTIFACT = "analysis/text_event_signals.json"
EVENT_MARKET_CONFLUENCE_ARTIFACT = "analysis/event_market_confluence.json"
MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
MARKET_REGIME_ASSESSMENT_ARTIFACT = "analysis/market_regime_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
MACRO_CALENDAR_CONTEXT_ARTIFACT = "analysis/macro_calendar_context.json"
ONCHAIN_FLOW_CONTEXT_ARTIFACT = "analysis/onchain_flow_context.json"
EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT = "analysis/event_intelligence_assessment.json"
EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT_TYPE = "event_intelligence_assessment"
CONSTRUCTIVE_ACTIONS = {"STRONG_DO", "DO", "TRY_SMALL"}
DEFENSIVE_ACTIONS = {"AVOID", "EXIT_OR_REDUCE", "HEDGE_OR_PROTECT"}
WATCH_RELEVANCE_ORDER = (
    "invalidation",
    "risk_escalation",
    "risk_relief",
    "confirmation",
    "wait_condition",
)


def build_event_intelligence_assessment(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _text_enabled(config):
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    signals_artifact = _read_optional_artifact(
        run.analysis_dir / "text_event_signals.json",
        TEXT_EVENT_SIGNALS_ARTIFACT,
        records_key="signals",
    )
    confluence_artifact = _read_optional_artifact(
        run.analysis_dir / "event_market_confluence.json",
        EVENT_MARKET_CONFLUENCE_ARTIFACT,
        records_key="records",
    )
    if signals_artifact is None and confluence_artifact is None:
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    records_artifact = _read_optional_artifact(
        run.analysis_dir / "text_event_records.json",
        TEXT_EVENT_RECORDS_ARTIFACT,
        records_key="records",
    )
    topics_artifact = _read_optional_artifact(
        run.analysis_dir / "text_event_topics.json",
        TEXT_EVENT_TOPICS_ARTIFACT,
        records_key="topics",
    )
    market_signals_artifact = _read_optional_artifact(
        run.analysis_dir / "market_signals.json",
        MARKET_SIGNALS_ARTIFACT,
        records_key="signals",
    )
    market_regime_artifact = _read_optional_artifact(
        run.analysis_dir / "market_regime_assessment.json",
        MARKET_REGIME_ASSESSMENT_ARTIFACT,
        records_key="records",
    )
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

    signals = _records(signals_artifact, "signals")
    confluence = _records(confluence_artifact, "records")
    topics = _records(topics_artifact, "topics")
    market_signals = _records(market_signals_artifact, "signals")
    regimes = _records(market_regime_artifact, "records")
    risk_records = _records(risk_artifact, "records")
    decision_records = _records(decision_artifact, "records")
    watch_records = _records(watch_artifact, "records")
    macro_records = _records(macro_artifact, "records")
    onchain_records = _records(onchain_artifact, "records")
    assessment_records = _assessment_records(
        signals=signals,
        confluence=confluence,
        topics=topics,
        market_signals=market_signals,
        regimes=regimes,
        risk_records=risk_records,
        decision_records=decision_records,
        watch_records=watch_records,
        macro_records=macro_records,
        onchain_records=onchain_records,
    )
    warnings = _artifact_warnings(assessment_records)
    if signals_artifact is not None and not signals:
        warnings.append("No text event signal records were available for event assessment.")
    errors: list[dict[str, Any]] = []

    artifact = {
        "schema_version": 1,
        "artifact_type": EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _created_at(confluence_artifact, signals_artifact, now=now),
        "source_artifacts": _source_artifacts(
            (TEXT_EVENT_RECORDS_ARTIFACT, records_artifact),
            (TEXT_EVENT_TOPICS_ARTIFACT, topics_artifact),
            (TEXT_EVENT_SIGNALS_ARTIFACT, signals_artifact),
            (EVENT_MARKET_CONFLUENCE_ARTIFACT, confluence_artifact),
            (MARKET_SIGNALS_ARTIFACT, market_signals_artifact),
            (MARKET_REGIME_ASSESSMENT_ARTIFACT, market_regime_artifact),
            (RISK_ASSESSMENT_ARTIFACT, risk_artifact),
            (DECISION_RECOMMENDATIONS_ARTIFACT, decision_artifact),
            (WATCH_TRIGGERS_ARTIFACT, watch_artifact),
            (MACRO_CALENDAR_CONTEXT_ARTIFACT, macro_artifact),
            (ONCHAIN_FLOW_CONTEXT_ARTIFACT, onchain_artifact),
        ),
        "coverage": _coverage(assessment_records),
        "records": assessment_records,
        "warnings": warnings,
        "errors": errors,
    }
    write_json(run.analysis_dir / "event_intelligence_assessment.json", artifact)
    run.manifest["artifacts"]["event_intelligence_assessment"] = EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT
    _record_manifest_summary(
        run,
        records=assessment_records,
        warnings=warnings,
        errors=errors,
        status="succeeded",
        macro_context_records=len(macro_records),
        onchain_context_records=len(onchain_records),
    )
    return [EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT]


def _assessment_records(
    *,
    signals: list[dict[str, Any]],
    confluence: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    market_signals: list[dict[str, Any]],
    regimes: list[dict[str, Any]],
    risk_records: list[dict[str, Any]],
    decision_records: list[dict[str, Any]],
    watch_records: list[dict[str, Any]],
    macro_records: list[dict[str, Any]],
    onchain_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signal_index = {
        str(signal.get("event_signal_id")): signal
        for signal in signals
        if isinstance(signal.get("event_signal_id"), str) and signal.get("event_signal_id")
    }
    topic_index = {
        str(topic.get("topic_id")): topic
        for topic in topics
        if isinstance(topic.get("topic_id"), str) and topic.get("topic_id")
    }
    market_index = _records_by_symbol_timeframe(market_signals)
    regime_index = _records_by_symbol_timeframe(regimes)
    risk_index = _records_by_symbol_timeframe(risk_records)
    decision_index = _records_by_symbol_timeframe(decision_records)
    watch_index = _records_by_symbol_timeframe(watch_records)
    macro_index = _macro_calendar_context_by_symbol(macro_records)
    onchain_records = sorted(onchain_records, key=_onchain_flow_sort_key)

    records = []
    covered_signal_ids: set[str] = set()
    for confluence_record in sorted(confluence, key=_confluence_sort_key):
        linked_ids = _string_list(confluence_record.get("linked_event_signal_ids"))
        linked_signals = [signal_index[signal_id] for signal_id in linked_ids if signal_id in signal_index]
        if not linked_signals:
            linked_signals = _signals_for_symbol(signals, confluence_record.get("symbol"))
        covered_signal_ids.update(
            str(signal.get("event_signal_id"))
            for signal in linked_signals
            if isinstance(signal.get("event_signal_id"), str)
        )
        key = (_clean_text(confluence_record.get("symbol"), fallback="market_wide"), _clean_text(confluence_record.get("timeframe"), fallback="event"))
        records.append(
            _assessment_record(
                confluence_record=confluence_record,
                signals=linked_signals,
                topic_index=topic_index,
                market_signals=market_index.get(key, []),
                regime=_first(regime_index.get(key, [])),
                risk=_first(risk_index.get(key, [])),
                decision=_first(decision_index.get(key, [])),
                watch_records=watch_index.get(key, []),
                macro_records=_macro_calendar_records_for_symbol(macro_index, key[0]),
                onchain_records=_onchain_flow_records_for_symbol(onchain_records, key[0]),
            )
        )

    for signal in sorted(signals, key=lambda item: str(item.get("event_signal_id") or "")):
        signal_id = str(signal.get("event_signal_id") or "")
        if signal_id in covered_signal_ids:
            continue
        key = _signal_key(signal, market_index, decision_index, risk_index, watch_index)
        records.append(
            _assessment_record(
                confluence_record=None,
                signals=[signal],
                topic_index=topic_index,
                market_signals=market_index.get(key, []),
                regime=_first(regime_index.get(key, [])),
                risk=_first(risk_index.get(key, [])),
                decision=_first(decision_index.get(key, [])),
                watch_records=watch_index.get(key, []),
                macro_records=_macro_calendar_records_for_symbol(macro_index, key[0]),
                onchain_records=_onchain_flow_records_for_symbol(onchain_records, key[0]),
            )
        )
    return records


def _assessment_record(
    *,
    confluence_record: dict[str, Any] | None,
    signals: list[dict[str, Any]],
    topic_index: dict[str, dict[str, Any]],
    market_signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    watch_records: list[dict[str, Any]],
    macro_records: list[dict[str, Any]],
    onchain_records: list[dict[str, Any]],
) -> dict[str, Any]:
    symbol = _record_symbol(confluence_record, signals)
    timeframe = _record_timeframe(confluence_record, market_signals, decision, risk, watch_records)
    topic_ids = _topic_ids(signals)
    topics = [topic_index[topic_id] for topic_id in topic_ids if topic_id in topic_index]
    affected_assets = _affected_assets(symbol, signals)
    macro = _macro_calendar_event_context(signals, topics, symbol=symbol, macro_records=macro_records)
    onchain = _onchain_flow_event_context(affected_assets=affected_assets, onchain_records=onchain_records)
    market_relationship = _market_response_relationship(confluence_record, market_signals)
    source_reliability = _source_reliability(signals, topics)
    risk_effect = _risk_effect(signals, confluence_record, risk, onchain=onchain)
    watch_relevance = _watch_relevance(confluence_record, watch_records)
    decision_impact = _decision_impact(
        confluence_record,
        signals,
        decision,
        risk_effect=risk_effect,
        watch_relevance=watch_relevance,
    )
    downgrade_reasons = _downgrade_reasons(
        signals=signals,
        topics=topics,
        confluence_record=confluence_record,
        source_reliability=source_reliability,
        affected_assets=affected_assets,
        market_relationship=market_relationship,
        decision=decision,
        macro=macro,
        onchain=onchain,
    )
    event_severity = _event_severity(
        signals,
        market_relationship=market_relationship,
        risk_effect=risk_effect,
        decision_impact=decision_impact,
        downgrade_reasons=downgrade_reasons,
        affected_assets=affected_assets,
    )
    confidence = _confidence(
        signals,
        source_reliability=source_reliability,
        market_relationship=market_relationship,
        downgrade_reasons=downgrade_reasons,
    )
    status = "degraded" if downgrade_reasons else "succeeded"
    evidence = _evidence(
        confluence_record,
        signals,
        market_signals,
        regime,
        risk,
        decision,
        watch_records,
        macro=macro,
        onchain=onchain,
    )
    warnings = _warnings(confluence_record, signals, downgrade_reasons=downgrade_reasons)
    uncertainty = _uncertainty(
        confluence_record,
        signals,
        downgrade_reasons=downgrade_reasons,
        macro=macro,
        onchain=onchain,
    )
    linked_signal_ids = _signal_ids(signals)
    linked_watch_ids = _watch_trigger_ids(watch_records)
    linked_decision_ids = _decision_ids(confluence_record, decision)
    source_artifacts = _record_source_artifacts(
        confluence_record,
        signals,
        market_signals,
        regime,
        risk,
        decision,
        watch_records,
        macro["records"],
        onchain["records"],
    )
    if market_signals:
        source_artifacts.append(MARKET_SIGNALS_ARTIFACT)
    if regime is not None:
        source_artifacts.append(MARKET_REGIME_ASSESSMENT_ARTIFACT)
    if risk is not None:
        source_artifacts.append(RISK_ASSESSMENT_ARTIFACT)
    if decision is not None:
        source_artifacts.append(DECISION_RECOMMENDATIONS_ARTIFACT)
    if watch_records:
        source_artifacts.append(WATCH_TRIGGERS_ARTIFACT)
    if macro["linked_ids"]:
        source_artifacts.append(MACRO_CALENDAR_CONTEXT_ARTIFACT)
    if onchain["linked_ids"]:
        source_artifacts.append(ONCHAIN_FLOW_CONTEXT_ARTIFACT)
    source_artifacts = _unique(source_artifacts)
    source_key = _source_key(confluence_record, linked_signal_ids, topic_ids)
    return {
        "assessment_id": f"event_intelligence_assessment:{symbol}:{timeframe}:{source_key}",
        "status": status,
        "scope": {
            "symbol": symbol,
            "timeframe": timeframe,
            "topic_ids": topic_ids,
            "confluence_id": confluence_record.get("confluence_id") if confluence_record else None,
            "event_signal_ids": linked_signal_ids,
            "source_event_ids": _source_event_ids(signals),
        },
        "event_summary": _event_summary(
            symbol=symbol,
            timeframe=timeframe,
            signals=signals,
            market_relationship=market_relationship,
            decision_impact=decision_impact,
            downgrade_reasons=downgrade_reasons,
        ),
        "affected_assets": affected_assets,
        "relevant_timeframes": [timeframe],
        "source_reliability": source_reliability,
        "event_severity": event_severity,
        "market_response_relationship": market_relationship,
        "decision_impact": decision_impact,
        "risk_effect": risk_effect,
        "watch_relevance": watch_relevance,
        "confidence": confidence,
        "evidence": evidence,
        "downgrade_reasons": downgrade_reasons,
        "uncertainty": uncertainty,
        "warnings": warnings,
        "linked_event_signal_ids": linked_signal_ids,
        "linked_decision_record_ids": linked_decision_ids,
        "linked_watch_trigger_ids": linked_watch_ids,
        "linked_macro_calendar_context_ids": macro["linked_ids"],
        "macro_calendar_relevance": macro["relevance"],
        "linked_onchain_flow_context_ids": onchain["linked_ids"],
        "onchain_flow_relevance": onchain["relevance"],
        "source_artifacts": source_artifacts,
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


def _records_by_symbol_timeframe(records: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        symbol = _clean_text(record.get("symbol"), fallback="")
        timeframe = _clean_text(record.get("timeframe"), fallback="")
        if not symbol or not timeframe:
            continue
        grouped.setdefault((symbol, timeframe), []).append(record)
    return grouped


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
    if symbol in {"", "market_wide", "missing", "event"}:
        return []
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
    return _unique_onchain_flow_records(sorted(matched, key=_onchain_flow_sort_key))


def _macro_calendar_event_context(
    signals: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    *,
    symbol: str,
    macro_records: list[dict[str, Any]],
) -> dict[str, Any]:
    event_times = _event_reference_times(signals, topics)
    linked_records: list[dict[str, Any]] = []
    relevance: list[str] = []
    uncertainty: list[str] = []
    downgrade_reasons: list[str] = []

    for record in _unique_macro_calendar_records(macro_records):
        context_type = _clean_text(record.get("context_type"), fallback="unknown")
        status = _clean_text(record.get("status"), fallback="unknown")
        state = _clean_text(record.get("state"), fallback="unknown")
        event_name = _clean_text(record.get("event_name"), fallback=context_type)
        if context_type in {"scheduled_catalyst", "recent_catalyst"}:
            scheduled_at = _parse_utc(record.get("scheduled_at"))
            if scheduled_at is None or not event_times:
                continue
            proximity_hours = min(abs((event_time - scheduled_at).total_seconds()) / 3600 for event_time in event_times)
            if proximity_hours > 72:
                continue
            linked_records.append(record)
            relevance.append(
                f"macro_calendar_context {context_type} event={event_name}; "
                f"proximity_hours={proximity_hours:.1f}; status={status}; state={state}."
            )
            uncertainty.append(
                "Macro/calendar catalyst proximity is scheduled context, not realized market impact or alert priority."
            )
            continue
        if context_type == "source_availability" or status in {"failed", "unavailable", "stale", "degraded", "partial"}:
            linked_records.append(record)
            relevance.append(
                f"macro_calendar_context {context_type} source_state={state}; status={status}; event={event_name}."
            )
            uncertainty.append(
                "Macro/calendar source availability is degraded; missing calendar evidence cannot be treated as neutral."
            )
            downgrade_reasons.append("macro_calendar_source_uncertainty")
            continue

    linked_records = _unique_macro_calendar_records(linked_records)
    return {
        "records": linked_records,
        "linked_ids": _macro_calendar_context_ids(linked_records),
        "relevance": _unique(relevance),
        "uncertainty": _unique(uncertainty),
        "downgrade_reasons": _unique(downgrade_reasons),
    }


def _onchain_flow_event_context(
    *,
    affected_assets: list[str],
    onchain_records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not affected_assets:
        return {
            "records": [],
            "linked_ids": [],
            "relevance": [],
            "uncertainty": [],
            "downgrade_reasons": [],
            "risk_effect": "unknown",
        }

    linked_records: list[dict[str, Any]] = []
    relevance: list[str] = []
    uncertainty: list[str] = []
    downgrade_reasons: list[str] = []
    risk_effect = "unknown"

    for record in _unique_onchain_flow_records(onchain_records):
        context_type = _clean_text(record.get("context_type"), fallback="unknown")
        status = _clean_text(record.get("status"), fallback="unknown")
        state = _clean_text(record.get("state"), fallback="unknown")
        severity = _clean_text(record.get("severity"), fallback="unknown")
        asset = _clean_text(record.get("asset"), fallback="unknown_asset")
        chain = _clean_text(record.get("chain"), fallback="unknown_chain")
        if status in {"failed", "unavailable", "stale", "degraded", "partial"} or state in {
            "source_unavailable",
            "source_failed",
            "unavailable",
            "stale",
            "insufficient_evidence",
        }:
            linked_records.append(record)
            relevance.append(
                "onchain_flow_context "
                f"{context_type} source_state={state}; status={status}; asset={asset}; chain={chain}."
            )
            uncertainty.append(
                "On-chain flow source availability is degraded; missing flow evidence cannot be treated as neutral."
            )
            downgrade_reasons.append("onchain_flow_source_uncertainty")
            continue
        if state in {"normal", "neutral"} or severity in {"low", "unknown"}:
            continue
        linked_records.append(record)
        relevance.append(
            "onchain_flow_context "
            f"{context_type} state={state}; severity={severity}; status={status}; asset={asset}; chain={chain}."
        )
        uncertainty.append("On-chain flow context is supporting evidence, not realized event impact or alert priority.")
        risk_effect = "risk_up"

    linked_records = _unique_onchain_flow_records(linked_records)
    return {
        "records": linked_records,
        "linked_ids": _onchain_flow_context_ids(linked_records),
        "relevance": _unique(relevance),
        "uncertainty": _unique(uncertainty),
        "downgrade_reasons": _unique(downgrade_reasons),
        "risk_effect": risk_effect,
    }


def _event_reference_times(signals: list[dict[str, Any]], topics: list[dict[str, Any]]) -> list[datetime]:
    values: list[datetime] = []
    for signal in signals:
        values.extend(_event_signal_times(signal))
    for topic in topics:
        for field in ("latest_seen_at", "first_seen_at"):
            parsed = _parse_utc(topic.get(field))
            if parsed is not None:
                values.append(parsed)
    return sorted({value for value in values})


def _event_signal_times(signal: dict[str, Any]) -> list[datetime]:
    values = []
    for field in ("published_at", "created_at"):
        parsed = _parse_utc(signal.get(field))
        if parsed is not None:
            values.append(parsed)
    for evidence in signal.get("evidence") or []:
        if isinstance(evidence, dict):
            parsed = _parse_utc(evidence.get("published_at"))
            if parsed is not None:
                values.append(parsed)
    return values


def _macro_calendar_evidence_records(macro: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for record in macro.get("records", [])[:4]:
        evidence.append(
            {
                "type": "macro_calendar_context",
                "context_id": record.get("context_id"),
                "context_type": record.get("context_type"),
                "status": record.get("status"),
                "state": record.get("state"),
                "event_name": record.get("event_name"),
                "scheduled_at": record.get("scheduled_at"),
            }
        )
    return evidence


def _onchain_flow_evidence_records(onchain: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for record in onchain.get("records", [])[:4]:
        evidence.append(
            {
                "type": "onchain_flow_context",
                "context_id": record.get("context_id"),
                "context_type": record.get("context_type"),
                "status": record.get("status"),
                "state": record.get("state"),
                "severity": record.get("severity"),
                "asset": record.get("asset"),
                "chain": record.get("chain"),
            }
        )
    return evidence


def _macro_calendar_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            context_id
            for record in records
            for context_id in [_clean_text(record.get("context_id"), fallback="")]
            if context_id
        ]
    )


def _onchain_flow_context_ids(records: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            context_id
            for record in records
            for context_id in [_clean_text(record.get("context_id"), fallback="")]
            if context_id
        ]
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
        _clean_text(record.get("as_of"), fallback=""),
        _clean_text(record.get("context_id"), fallback=""),
    )


def _confluence_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean_text(record.get("symbol"), fallback=""),
        _clean_text(record.get("timeframe"), fallback=""),
        _clean_text(record.get("confluence_id"), fallback=""),
    )


def _signals_for_symbol(signals: list[dict[str, Any]], symbol: Any) -> list[dict[str, Any]]:
    clean_symbol = _clean_text(symbol, fallback="")
    if not clean_symbol:
        return []
    return [signal for signal in signals if _clean_text(signal.get("symbol"), fallback="") == clean_symbol]


def _signal_key(
    signal: dict[str, Any],
    *indexes: dict[tuple[str, str], list[dict[str, Any]]],
) -> tuple[str, str]:
    symbol = _clean_text(signal.get("symbol"), fallback="market_wide")
    for index in indexes:
        matches = sorted(key for key in index if key[0] == symbol)
        if matches:
            return matches[0]
    return (symbol, "event")


def _record_symbol(confluence_record: dict[str, Any] | None, signals: list[dict[str, Any]]) -> str:
    if confluence_record is not None:
        return _clean_text(confluence_record.get("symbol"), fallback="market_wide")
    for signal in signals:
        symbol = _clean_text(signal.get("symbol"), fallback="")
        if symbol:
            return symbol
    return "market_wide"


def _record_timeframe(
    confluence_record: dict[str, Any] | None,
    market_signals: list[dict[str, Any]],
    decision: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    watch_records: list[dict[str, Any]],
) -> str:
    if confluence_record is not None:
        return _clean_text(confluence_record.get("timeframe"), fallback="event")
    for item in [*market_signals, decision, risk, *watch_records]:
        if isinstance(item, dict):
            timeframe = _clean_text(item.get("timeframe"), fallback="")
            if timeframe:
                return timeframe
    return "event"


def _topic_ids(signals: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            str(signal.get("topic_id"))
            for signal in signals
            if isinstance(signal.get("topic_id"), str) and signal.get("topic_id")
        ]
    )


def _affected_assets(symbol: str, signals: list[dict[str, Any]]) -> list[str]:
    values = [
        _clean_text(signal.get("symbol"), fallback="")
        for signal in signals
        if _clean_text(signal.get("symbol"), fallback="")
    ]
    if symbol not in {"market_wide", "missing", "event"}:
        values.append(symbol)
    return sorted(set(values))


def _market_response_relationship(confluence_record: dict[str, Any] | None, market_signals: list[dict[str, Any]]) -> str:
    if confluence_record is None:
        return "insufficient_market_evidence" if not market_signals else "unknown"
    relationship = _clean_text(confluence_record.get("relationship"), fallback="unknown")
    if relationship == "confluence":
        return "confirmed"
    if relationship == "conflict":
        return "conflicting"
    if relationship == "independent":
        return "independent"
    if relationship == "insufficient_event_evidence":
        return "insufficient_market_evidence"
    return "unknown"


def _source_reliability(signals: list[dict[str, Any]], topics: list[dict[str, Any]]) -> str:
    if not signals:
        return "unknown"
    statuses = {_clean_text(signal.get("status"), fallback="unknown") for signal in signals}
    if statuses - {"accepted"}:
        return "low"
    source_count = max([int(topic.get("source_count") or 0) for topic in topics] or [0])
    confidences = {_clean_text(signal.get("confidence"), fallback="unknown") for signal in signals}
    if "high" in confidences and source_count >= 2:
        return "high"
    if confidences & {"high", "medium"}:
        return "medium"
    if "low" in confidences:
        return "low"
    return "unknown"


def _risk_effect(
    signals: list[dict[str, Any]],
    confluence_record: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    *,
    onchain: dict[str, Any],
) -> str:
    signal_effects = {
        _clean_text(signal.get("risk_impact"), fallback="unknown")
        for signal in signals
        if _clean_text(signal.get("risk_impact"), fallback="unknown") != "unknown"
    }
    if "risk_up" in signal_effects:
        return "risk_up"
    if _clean_text(onchain.get("risk_effect"), fallback="unknown") == "risk_up":
        return "risk_up"
    if "risk_down" in signal_effects:
        return "risk_down"
    confluence_risk = _clean_text(confluence_record.get("risk_effect") if confluence_record else None, fallback="unknown")
    if confluence_risk in {"risk_watch", "do_not_upgrade_due_to_risk"}:
        return "risk_up"
    risk_level = _clean_text(risk.get("risk_level") if risk else None, fallback="unknown")
    if risk_level in {"high", "extreme"}:
        return "risk_up"
    if signal_effects == {"neutral"}:
        return "neutral"
    if signal_effects:
        return "mixed"
    return "unknown" if risk is None else "neutral"


def _watch_relevance(confluence_record: dict[str, Any] | None, watch_records: list[dict[str, Any]]) -> str:
    trigger_types = {_clean_text(record.get("type"), fallback="") for record in watch_records}
    for value in WATCH_RELEVANCE_ORDER:
        if value in trigger_types:
            return value
    relationship = _clean_text(confluence_record.get("relationship") if confluence_record else None, fallback="")
    if relationship == "conflict":
        return "invalidation"
    if relationship == "insufficient_event_evidence":
        return "wait_condition"
    return "none"


def _decision_impact(
    confluence_record: dict[str, Any] | None,
    signals: list[dict[str, Any]],
    decision: dict[str, Any] | None,
    *,
    risk_effect: str,
    watch_relevance: str,
) -> str:
    if not _accepted_signals(signals):
        return "insufficient_evidence"
    action_level = _clean_text(
        decision.get("action_level") if decision else confluence_record.get("decision_action_level") if confluence_record else None,
        fallback="unknown",
    )
    relationship = _clean_text(confluence_record.get("relationship") if confluence_record else None, fallback="unknown")
    if watch_relevance == "invalidation":
        return "could_invalidate"
    if relationship == "conflict" or (risk_effect == "risk_up" and action_level in CONSTRUCTIVE_ACTIONS):
        return "could_downgrade"
    if relationship == "confluence" and action_level in CONSTRUCTIVE_ACTIONS | DEFENSIVE_ACTIONS:
        return "supports_existing_view"
    if relationship == "confluence" and action_level in {"WATCH", "NO_ACTION", "unknown"}:
        return "could_upgrade_attention"
    if decision is None and confluence_record is None:
        return "insufficient_evidence"
    return "no_change"


def _downgrade_reasons(
    *,
    signals: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    confluence_record: dict[str, Any] | None,
    source_reliability: str,
    affected_assets: list[str],
    market_relationship: str,
    decision: dict[str, Any] | None,
    macro: dict[str, Any],
    onchain: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if not signals:
        reasons.append("event_signal_missing")
    for signal in signals:
        status = _clean_text(signal.get("status"), fallback="unknown")
        if status != "accepted":
            reasons.append("event_signal_not_accepted")
        if status == "low_confidence" or _clean_text(signal.get("confidence"), fallback="unknown") in {"low", "unknown"}:
            reasons.append("low_confidence_event")
        if _clean_text(signal.get("recency"), fallback="unknown") == "stale":
            reasons.append("stale_event")
    if any(_topic_has_duplicate(topic) for topic in topics):
        reasons.append("duplicate_event_group")
    if not affected_assets:
        reasons.append("unrelated_event")
    if confluence_record is None:
        reasons.append("event_market_confluence_missing")
    if market_relationship == "insufficient_market_evidence":
        reasons.append("insufficient_market_evidence")
    if source_reliability in {"low", "unknown"}:
        reasons.append("weak_source_reliability")
    if decision is None:
        reasons.append("decision_recommendation_missing")
    reasons.extend(_string_list(macro.get("downgrade_reasons")))
    reasons.extend(_string_list(onchain.get("downgrade_reasons")))
    for warning in _string_list(confluence_record.get("warnings") if confluence_record else None):
        if warning == "insufficient_event_evidence":
            reasons.append("insufficient_event_evidence")
    return _unique(reasons)


def _topic_has_duplicate(topic: dict[str, Any]) -> bool:
    for decision in topic.get("merge_decisions") or []:
        if isinstance(decision, dict) and decision.get("relationship") == "duplicate":
            return True
    return False


def _event_severity(
    signals: list[dict[str, Any]],
    *,
    market_relationship: str,
    risk_effect: str,
    decision_impact: str,
    downgrade_reasons: list[str],
    affected_assets: list[str],
) -> str:
    if "unrelated_event" in downgrade_reasons or not affected_assets:
        return "noise"
    if not _accepted_signals(signals):
        return "low"
    if "stale_event" in downgrade_reasons or "duplicate_event_group" in downgrade_reasons:
        return "low"
    if risk_effect == "risk_up" and decision_impact in {"could_invalidate", "could_downgrade"}:
        return "high"
    if market_relationship in {"confirmed", "conflicting"}:
        return "medium"
    return "low"


def _confidence(
    signals: list[dict[str, Any]],
    *,
    source_reliability: str,
    market_relationship: str,
    downgrade_reasons: list[str],
) -> str:
    if not signals:
        return "unknown"
    if downgrade_reasons:
        return "low"
    confidences = {_clean_text(signal.get("confidence"), fallback="unknown") for signal in signals}
    if "high" in confidences and source_reliability == "high" and market_relationship in {"confirmed", "conflicting"}:
        return "high"
    if confidences & {"high", "medium"} and market_relationship != "insufficient_market_evidence":
        return "medium"
    return "low"


def _evidence(
    confluence_record: dict[str, Any] | None,
    signals: list[dict[str, Any]],
    market_signals: list[dict[str, Any]],
    regime: dict[str, Any] | None,
    risk: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    watch_records: list[dict[str, Any]],
    *,
    macro: dict[str, Any],
    onchain: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    if confluence_record is not None:
        evidence.append(
            {
                "type": "event_market_confluence",
                "confluence_id": confluence_record.get("confluence_id"),
                "relationship": confluence_record.get("relationship"),
                "risk_effect": confluence_record.get("risk_effect"),
            }
        )
        for item in confluence_record.get("evidence") or []:
            if isinstance(item, dict):
                evidence.append({"type": f"confluence_{item.get('type', 'evidence')}", **item})
    for signal in signals:
        evidence.append(
            {
                "type": "event_signal",
                "event_signal_id": signal.get("event_signal_id"),
                "status": signal.get("status"),
                "primary_category": signal.get("primary_category"),
                "event_bias": signal.get("event_bias"),
                "risk_impact": signal.get("risk_impact"),
                "confidence": signal.get("confidence"),
                "recency": signal.get("recency"),
            }
        )
    for signal in market_signals[:3]:
        evidence.append(
            {
                "type": "market_signal",
                "signal_id": signal.get("signal_id"),
                "direction": signal.get("direction"),
                "confidence": signal.get("confidence"),
            }
        )
    if regime is not None:
        evidence.append(
            {
                "type": "market_regime_assessment",
                "record_id": regime.get("record_id"),
                "regime": regime.get("regime"),
                "confidence": regime.get("confidence"),
            }
        )
    if risk is not None:
        evidence.append(
            {
                "type": "risk_assessment",
                "record_id": risk.get("record_id"),
                "risk_level": risk.get("risk_level"),
            }
        )
    if decision is not None:
        evidence.append(
            {
                "type": "decision_recommendation",
                "record_id": decision.get("record_id"),
                "action_level": decision.get("action_level"),
                "decision_bias": decision.get("decision_bias"),
            }
        )
    for watch in watch_records[:3]:
        evidence.append(
            {
                "type": "watch_trigger",
                "trigger_id": watch.get("trigger_id"),
                "trigger_type": watch.get("type"),
                "condition": watch.get("condition"),
            }
        )
    evidence.extend(_macro_calendar_evidence_records(macro))
    evidence.extend(_onchain_flow_evidence_records(onchain))
    return evidence[:16]


def _warnings(
    confluence_record: dict[str, Any] | None,
    signals: list[dict[str, Any]],
    *,
    downgrade_reasons: list[str],
) -> list[str]:
    warnings = _string_list(confluence_record.get("warnings") if confluence_record else None)
    for signal in signals:
        warnings.extend(_string_list(signal.get("warnings")))
    if downgrade_reasons:
        warnings.append("event_assessment_downgraded")
    return _unique(warnings)


def _uncertainty(
    confluence_record: dict[str, Any] | None,
    signals: list[dict[str, Any]],
    *,
    downgrade_reasons: list[str],
    macro: dict[str, Any],
    onchain: dict[str, Any],
) -> list[str]:
    uncertainty = _string_list(confluence_record.get("uncertainty") if confluence_record else None)
    for signal in signals:
        uncertainty.extend(_string_list(signal.get("uncertainty")))
    if downgrade_reasons:
        uncertainty.append(f"Event assessment was downgraded: {', '.join(downgrade_reasons)}.")
    uncertainty.extend(_string_list(macro.get("uncertainty")))
    uncertainty.extend(_string_list(onchain.get("uncertainty")))
    uncertainty.append("Event assessment does not assign alert priority or action levels.")
    return _unique(uncertainty)


def _event_summary(
    *,
    symbol: str,
    timeframe: str,
    signals: list[dict[str, Any]],
    market_relationship: str,
    decision_impact: str,
    downgrade_reasons: list[str],
) -> str:
    categories = _unique(
        [
            _clean_text(signal.get("primary_category"), fallback="unknown")
            for signal in signals
            if _clean_text(signal.get("primary_category"), fallback="unknown") != "unknown"
        ]
    )
    category_text = ", ".join(categories) if categories else "unknown event category"
    if downgrade_reasons:
        return (
            f"{symbol} {timeframe} event assessment is downgraded for {', '.join(downgrade_reasons)}; "
            f"category={category_text}."
        )
    return (
        f"{symbol} {timeframe} event assessment uses {category_text} evidence; "
        f"market_relationship={market_relationship}; decision_impact={decision_impact}."
    )


def _accepted_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [signal for signal in signals if _clean_text(signal.get("status"), fallback="unknown") == "accepted"]


def _signal_ids(signals: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            str(signal.get("event_signal_id"))
            for signal in signals
            if isinstance(signal.get("event_signal_id"), str) and signal.get("event_signal_id")
        ]
    )


def _source_event_ids(signals: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for signal in signals:
        values.extend(_string_list(signal.get("source_event_ids")))
    return _unique(values)


def _decision_ids(confluence_record: dict[str, Any] | None, decision: dict[str, Any] | None) -> list[str]:
    values = _string_list(confluence_record.get("linked_decision_record_ids") if confluence_record else None)
    if decision is not None and isinstance(decision.get("record_id"), str):
        values.append(decision["record_id"])
    return _unique(values)


def _watch_trigger_ids(watch_records: list[dict[str, Any]]) -> list[str]:
    return _unique(
        [
            str(record.get("trigger_id"))
            for record in watch_records
            if isinstance(record.get("trigger_id"), str) and record.get("trigger_id")
        ]
    )


def _record_source_artifacts(*items: Any) -> list[str]:
    artifacts: list[str] = [TEXT_EVENT_SIGNALS_ARTIFACT]
    for item in items:
        if isinstance(item, list):
            for value in item:
                if isinstance(value, dict):
                    artifacts.extend(_string_list(value.get("source_artifacts")))
        elif isinstance(item, dict):
            artifacts.extend(_string_list(item.get("source_artifacts")))
            artifact_type = item.get("artifact_type")
            if artifact_type == "event_market_confluence" or isinstance(item.get("confluence_id"), str):
                artifacts.append(EVENT_MARKET_CONFLUENCE_ARTIFACT)
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
    severity_counts = _count_by(records, "event_severity")
    reliability_counts = _count_by(records, "source_reliability")
    relationship_counts = _count_by(records, "market_response_relationship")
    return {
        "records": len(records),
        "severity": severity_counts,
        "source_reliability": reliability_counts,
        "market_response_relationship": relationship_counts,
        "downgraded_records": sum(1 for record in records if record.get("downgrade_reasons")),
        "warning_records": sum(1 for record in records if record.get("warnings")),
        "high_or_critical_records": sum(
            1 for record in records if record.get("event_severity") in {"high", "critical"}
        ),
        "insufficient_market_evidence_records": relationship_counts.get("insufficient_market_evidence", 0),
        "macro_calendar_linked_records": sum(1 for record in records if record.get("linked_macro_calendar_context_ids")),
        "onchain_flow_linked_records": sum(1 for record in records if record.get("linked_onchain_flow_context_ids")),
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
    run.manifest["counts"]["event_intelligence_assessment_records"] = coverage["records"]
    run.manifest["counts"]["event_intelligence_assessment_high_or_critical_records"] = coverage[
        "high_or_critical_records"
    ]
    run.manifest["counts"]["event_intelligence_assessment_downgraded_records"] = coverage["downgraded_records"]
    run.manifest["counts"]["event_intelligence_assessment_warning_records"] = coverage["warning_records"]
    run.manifest["counts"]["event_intelligence_assessment_insufficient_market_evidence_records"] = coverage[
        "insufficient_market_evidence_records"
    ]
    run.manifest["counts"]["event_intelligence_assessment_macro_calendar_context_records"] = macro_context_records
    run.manifest["counts"]["event_intelligence_assessment_macro_calendar_linked_records"] = coverage[
        "macro_calendar_linked_records"
    ]
    run.manifest["counts"]["event_intelligence_assessment_onchain_flow_context_records"] = onchain_context_records
    run.manifest["counts"]["event_intelligence_assessment_onchain_flow_linked_records"] = coverage[
        "onchain_flow_linked_records"
    ]
    run.manifest["event_intelligence_assessment"] = {
        "status": status,
        "artifacts": [EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT] if status == "succeeded" else [],
        "records": coverage["records"],
        "severity": coverage["severity"],
        "source_reliability": coverage["source_reliability"],
        "market_response_relationship": coverage["market_response_relationship"],
        "downgraded_records": coverage["downgraded_records"],
        "warning_records": coverage["warning_records"],
        "macro_calendar_context_records": macro_context_records,
        "macro_calendar_linked_records": coverage["macro_calendar_linked_records"],
        "onchain_flow_context_records": onchain_context_records,
        "onchain_flow_linked_records": coverage["onchain_flow_linked_records"],
        "degraded": bool(coverage["downgraded_records"] or warnings),
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


def _source_key(confluence_record: dict[str, Any] | None, signal_ids: list[str], topic_ids: list[str]) -> str:
    if confluence_record is not None and isinstance(confluence_record.get("confluence_id"), str):
        return confluence_record["confluence_id"]
    if signal_ids:
        return signal_ids[0]
    if topic_ids:
        return topic_ids[0]
    return "no_event_signal"


def _first(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    return records[0] if records else None


def _text_enabled(config: dict[str, Any]) -> bool:
    text = config.get("text")
    return isinstance(text, dict) and text.get("enabled") is True


def _created_at(
    confluence_artifact: dict[str, Any] | None,
    signals_artifact: dict[str, Any] | None,
    *,
    now: datetime | str | None,
) -> str:
    if now is not None:
        return _utc_timestamp(now)
    for artifact in (confluence_artifact, signals_artifact):
        if isinstance(artifact, dict) and isinstance(artifact.get("created_at"), str):
            return artifact["created_at"]
    return _utc_timestamp()


def _utc_timestamp(value: datetime | str | None = None) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp = value or datetime.now(UTC)
    return timestamp.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).replace(microsecond=0)


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
