from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from .pipeline import PipelineError, RunContext
from .storage import write_json


BUILD_MARKET_REGIME_ASSESSMENT_STAGE = "build_market_regime_assessment"
BUILD_RISK_ASSESSMENT_STAGE = "build_risk_assessment"
MARKET_REGIME_ASSESSMENT_ARTIFACT = "analysis/market_regime_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
MARKET_STRATEGY_SIGNALS_ARTIFACT = "analysis/market_strategy_signals.json"
QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
MARKET_DATA_VIEWS_ARTIFACT = "raw/market_data_views.json"
SCHEMA_VERSION = 1


def build_market_regime_assessment(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        run.manifest["counts"]["market_regime_records"] = 0
        run.manifest["counts"]["market_regime_unknown_records"] = 0
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
    records = [
        _regime_record(group_signals)
        for group_signals in _grouped_signals(signals).values()
    ]
    warnings = _artifact_warnings(records, strategy_warnings)

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "market_regime_assessment",
        "run_id": run.run_id,
        "created_at": created_at,
        "source_artifacts": _source_artifacts(market_signals, strategy_artifact),
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
        )
        for key in _risk_group_keys(signals, regime_records, strategy_runs)
    ]

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "risk_assessment",
        "run_id": run.run_id,
        "created_at": created_at,
        "source_artifacts": _risk_source_artifacts(market_signals, market_regime, strategy_artifact),
        "records": records,
        "warnings": _risk_artifact_warnings(records, [*strategy_warnings, *run_warnings]),
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
    return [RISK_ASSESSMENT_ARTIFACT]


def _regime_record(signals: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [signal for signal in signals if _has_usable_signal_evidence(signal)]
    latest = _latest_candle_time(signals)
    source = _group_value(signals, "source")
    symbol = _group_value(signals, "symbol")
    timeframe = _group_value(signals, "timeframe")
    warnings: list[str] = []
    if len(usable) < len(signals):
        warnings.append("One or more upstream market signals have insufficient or weak evidence.")

    regime, regime_evidence, conflicts = _classify_regime(usable)
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
                *_bounded_signal_evidence(usable),
            ]
        ),
        "conflicts": conflicts,
        "uncertainty": _uncertainty(signals),
        "warnings": warnings,
        "source_artifacts": _record_source_artifacts(signals),
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
) -> dict[str, Any]:
    source, symbol, timeframe = key
    latest = _latest_risk_candle_time(signals, regime, strategy_runs)
    data_quality_risks = _data_quality_risks(signals, regime, strategy_runs)
    signal_conflict_risks = _signal_conflict_risks(signals, regime)
    volatility = _volatility_risk(signals)
    strategy = _strategy_warning_risk(strategy_runs, signals)
    regime_risks = _regime_risks(regime)
    usable_evidence = _has_usable_risk_evidence(signals, regime)
    warnings = _risk_record_warnings(regime, usable_evidence)

    rising_risks = _unique_ordered(
        [
            *volatility["rising"],
            *strategy["rising"],
            *regime_risks["rising"],
            *([] if usable_evidence else ["Upstream evidence is insufficient for a supported low-risk conclusion."]),
        ]
    )
    blocking_risks = _unique_ordered(
        [
            *signal_conflict_risks,
            *volatility["blocking"],
            *regime_risks["blocking"],
            *([] if usable_evidence else ["Insufficient upstream evidence blocks stronger action levels."]),
        ]
    )
    severities = [
        *volatility["severities"],
        *strategy["severities"],
        *regime_risks["severities"],
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
            risk_level=risk_level,
        ),
        "warnings": warnings,
        "errors": [],
        "source_artifacts": _risk_record_source_artifacts(signals, regime, strategy_runs),
    }


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


def _record_source_artifacts(signals: list[dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            MARKET_SIGNALS_ARTIFACT,
            *[
                artifact
                for signal in signals
                for artifact in _string_list(signal.get("source_artifacts"))
            ],
        ]
    )


def _source_artifacts(market_signals: dict[str, Any], strategy_artifact: dict[str, Any] | None) -> list[str]:
    return _unique_ordered(
        [
            MARKET_SIGNALS_ARTIFACT,
            *_string_list(market_signals.get("source_artifacts")),
            *([QUANT_STRATEGY_RUNS_ARTIFACT] if strategy_artifact is not None else []),
            *_string_list(strategy_artifact.get("source_artifacts") if strategy_artifact else None),
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


def _tuple_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _clean_text(item.get("source"), fallback="missing"),
        _clean_text(item.get("symbol"), fallback="missing"),
        _clean_text(item.get("timeframe"), fallback="missing"),
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
    risk_level: str,
) -> list[str]:
    evidence = [
        _counts_evidence("direction_counts", _direction_counts(signals)),
        *regime_risks["evidence"],
        *volatility["evidence"],
        *strategy["evidence"],
        *_bounded_signal_evidence([signal for signal in signals if _has_usable_signal_evidence(signal)]),
    ]
    if regime is None:
        evidence.append("No matching market regime record was available.")
    if risk_level == "low":
        evidence.append("No elevated risk factors were found in current bounded M2 and regime artifacts.")
    return _unique_ordered(evidence)


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
) -> list[str]:
    return _unique_ordered(
        [
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *(_string_list(regime.get("source_artifacts")) if regime else []),
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
) -> list[str]:
    return _unique_ordered(
        [
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            MARKET_SIGNALS_ARTIFACT,
            *_string_list(market_regime.get("source_artifacts")),
            *_string_list(market_signals.get("source_artifacts")),
            *([QUANT_STRATEGY_RUNS_ARTIFACT] if strategy_artifact is not None else []),
            *_string_list(strategy_artifact.get("source_artifacts") if strategy_artifact else None),
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
            "not a forecast",
            "research material",
            "research assumption",
            "not trading advice",
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
