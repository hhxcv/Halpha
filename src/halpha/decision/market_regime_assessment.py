from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.decision.decision_intelligence import (
    BUILD_MARKET_REGIME_ASSESSMENT_STAGE,
    MARKET_REGIME_ASSESSMENT_ARTIFACT,
    MARKET_SIGNALS_ARTIFACT,
    SCHEMA_VERSION,
    _artifact_warnings,
    _created_at,
    _derivatives_by_symbol,
    _group_value,
    _grouped_signals,
    _quant_enabled,
    _read_json_artifact,
    _read_optional_derivatives_context,
    _read_optional_strategy_artifact,
    _records_from_optional_artifact,
    _regime_record,
    _signals_from_artifact,
    _source_artifacts,
    _string_list,
)
from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import write_json


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
