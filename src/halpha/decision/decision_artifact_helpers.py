from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision import decision_intelligence as _decision_intelligence
from halpha.runtime.pipeline_contracts import RunContext


BUILD_MARKET_REGIME_ASSESSMENT_STAGE = _decision_intelligence.BUILD_MARKET_REGIME_ASSESSMENT_STAGE
MARKET_REGIME_ASSESSMENT_ARTIFACT = _decision_intelligence.MARKET_REGIME_ASSESSMENT_ARTIFACT
MARKET_SIGNALS_ARTIFACT = _decision_intelligence.MARKET_SIGNALS_ARTIFACT
SCHEMA_VERSION = _decision_intelligence.SCHEMA_VERSION


def quant_enabled(config: dict[str, Any]) -> bool:
    return _decision_intelligence._quant_enabled(config)


def read_json_artifact(path, artifact: str, *, producer_stage: str, stage: str) -> dict[str, Any]:
    return _decision_intelligence._read_json_artifact(
        path,
        artifact,
        producer_stage=producer_stage,
        stage=stage,
    )


def signals_from_artifact(artifact: dict[str, Any], *, stage: str) -> list[dict[str, Any]]:
    return _decision_intelligence._signals_from_artifact(artifact, stage=stage)


def created_at(artifact: dict[str, Any], now: datetime | str | None) -> str:
    return _decision_intelligence._created_at(artifact, now)


def read_optional_strategy_artifact(
    run: RunContext,
    market_signals: dict[str, Any],
    *,
    stage: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    return _decision_intelligence._read_optional_strategy_artifact(
        run,
        market_signals,
        stage=stage,
    )


def read_optional_derivatives_context(run: RunContext) -> tuple[dict[str, Any] | None, list[str]]:
    return _decision_intelligence._read_optional_derivatives_context(run)


def records_from_optional_artifact(artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    return _decision_intelligence._records_from_optional_artifact(artifact)


def derivatives_by_symbol(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return _decision_intelligence._derivatives_by_symbol(records)


def grouped_signals(signals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return _decision_intelligence._grouped_signals(signals)


def group_value(signals: list[dict[str, Any]], field: str) -> str:
    return _decision_intelligence._group_value(signals, field)


def regime_record(signals: list[dict[str, Any]], derivatives_records: list[dict[str, Any]]) -> dict[str, Any]:
    return _decision_intelligence._regime_record(signals, derivatives_records)


def artifact_warnings(records: list[dict[str, Any]], strategy_warnings: list[str]) -> list[str]:
    return _decision_intelligence._artifact_warnings(records, strategy_warnings)


def source_artifacts(
    market_signals: dict[str, Any],
    strategy_artifact: dict[str, Any] | None,
    derivatives_artifact: dict[str, Any] | None = None,
) -> list[str]:
    return _decision_intelligence._source_artifacts(
        market_signals,
        strategy_artifact,
        derivatives_artifact,
    )


def string_list(value: Any) -> list[str]:
    return _decision_intelligence._string_list(value)
