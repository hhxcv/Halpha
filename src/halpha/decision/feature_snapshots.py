from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import RunContext
from halpha.storage import write_json


STAGE_NAME = "build_feature_snapshots"
FEATURE_SNAPSHOTS_ARTIFACT = "analysis/feature_snapshots.json"
FEATURE_SNAPSHOTS_SCHEMA_VERSION = 1

RAW_MARKET_ARTIFACT = "raw/market.json"
MARKET_DATA_VIEWS_ARTIFACT = "raw/market_data_views.json"
MARKET_SIGNALS_ARTIFACT = "analysis/market_signals.json"
DERIVATIVES_MARKET_CONTEXT_ARTIFACT = "analysis/derivatives_market_context.json"
MACRO_CALENDAR_CONTEXT_ARTIFACT = "analysis/macro_calendar_context.json"
ONCHAIN_FLOW_CONTEXT_ARTIFACT = "analysis/onchain_flow_context.json"
EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT = "analysis/event_intelligence_assessment.json"
OUTCOME_EVALUATIONS_ARTIFACT = "analysis/outcome_evaluations.json"
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"


def build_feature_snapshots(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    created_at = _format_utc(now)
    builder = _FeatureSnapshotBuilder(config, run, created_at=created_at)
    builder.add_raw_market()
    builder.add_market_data_views()
    builder.add_market_signals()
    builder.add_derivatives_context()
    builder.add_macro_calendar_context()
    builder.add_onchain_flow_context()
    builder.add_event_intelligence_assessment()
    builder.add_outcome_evaluations()
    builder.add_data_quality_summary()

    artifact = builder.artifact()
    write_json(run.analysis_dir / "feature_snapshots.json", artifact)
    _record_manifest(run, artifact)
    return [FEATURE_SNAPSHOTS_ARTIFACT]


class _FeatureSnapshotBuilder:
    def __init__(self, config: dict[str, Any], run: RunContext, *, created_at: str) -> None:
        self.config = config
        self.run = run
        self.created_at = created_at
        self.records: list[dict[str, Any]] = []
        self.coverage: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.errors: list[dict[str, Any]] = []
        self.source_artifacts: list[str] = []

    def add_raw_market(self) -> None:
        if not _market_enabled(self.config):
            self._record_coverage("market", RAW_MARKET_ARTIFACT, "skipped", reason="market.enabled is false.")
            return
        data = self._read_source("market", RAW_MARKET_ARTIFACT, self.run.raw_dir / "market.json", "items")
        if data is None:
            return
        items = _dict_list(data.get("items"))
        for item in items:
            self.records.append(
                _feature_record(
                    run_id=self.run.run_id,
                    feature_type="price_trend",
                    factor_family="trend",
                    source_layer="market",
                    source_artifact=RAW_MARKET_ARTIFACT,
                    source_record_id=_text_or_none(item.get("id")),
                    scope=_scope(
                        symbol=item.get("symbol"),
                    ),
                    observed_at=_text_or_none(item.get("as_of")) or _text_or_none(data.get("collected_at")) or self.created_at,
                    calculation_window={
                        "start": None,
                        "end": _text_or_none(item.get("as_of")) or _text_or_none(data.get("collected_at")),
                        "row_count": 1,
                    },
                    value=_metric_number(item.get("metrics"), "change_24h_pct"),
                    value_unit="percent",
                    direction_hint=_direction_from_number(_metric_number(item.get("metrics"), "change_24h_pct")),
                    status="available",
                    confidence="medium",
                    evidence=_raw_market_evidence(item),
                    uncertainty=[],
                    warnings=[],
                    errors=[],
                    source_artifacts=[RAW_MARKET_ARTIFACT],
                )
            )

    def add_market_data_views(self) -> None:
        if not _ohlcv_configured(self.config):
            self._record_coverage(
                "market_data_views",
                MARKET_DATA_VIEWS_ARTIFACT,
                "skipped",
                reason="market.ohlcv is not configured.",
            )
            return
        data = self._read_source(
            "market_data_views",
            MARKET_DATA_VIEWS_ARTIFACT,
            self.run.raw_dir / "market_data_views.json",
            "views",
        )
        if data is None:
            return
        for view in _dict_list(data.get("views")):
            status = "insufficient_evidence" if bool(view.get("insufficient_data")) else "available"
            warnings = _string_list(view.get("warnings"))
            self.records.append(
                _feature_record(
                    run_id=self.run.run_id,
                    feature_type="price_trend",
                    factor_family="trend",
                    source_layer="market_data_views",
                    source_artifact=MARKET_DATA_VIEWS_ARTIFACT,
                    source_record_id=_text_or_none(view.get("view_id")),
                    scope=_scope(
                        symbol=view.get("symbol"),
                        timeframe=view.get("timeframe"),
                    ),
                    observed_at=_text_or_none(view.get("latest_candle_time")) or self.created_at,
                    calculation_window={
                        "start": _text_or_none(view.get("input_window_start")),
                        "end": _text_or_none(view.get("input_window_end")),
                        "row_count": _int_or_none(view.get("row_count")),
                    },
                    value=_int_or_none(view.get("row_count")),
                    value_unit="rows",
                    direction_hint="unknown" if status == "insufficient_evidence" else "neutral",
                    status=status,
                    confidence="low" if status == "insufficient_evidence" else "medium",
                    evidence=[
                        f"Current-run OHLCV view has {view.get('row_count', 0)} row(s).",
                    ],
                    uncertainty=_unique_sorted(["OHLCV view metadata does not embed full raw history.", *warnings]),
                    warnings=warnings,
                    errors=[],
                    source_artifacts=[MARKET_DATA_VIEWS_ARTIFACT, *_string_list(view.get("source_artifacts"))],
                )
            )

    def add_market_signals(self) -> None:
        if not _quant_enabled(self.config):
            self._record_coverage(
                "market_signals",
                MARKET_SIGNALS_ARTIFACT,
                "skipped",
                reason="quant.enabled is false.",
            )
            return
        data = self._read_source(
            "market_signals",
            MARKET_SIGNALS_ARTIFACT,
            self.run.analysis_dir / "market_signals.json",
            "signals",
        )
        if data is None:
            return
        for signal in _dict_list(data.get("signals")):
            insufficient = bool(signal.get("insufficient_data"))
            self.records.append(
                _feature_record(
                    run_id=self.run.run_id,
                    feature_type="strategy_direction",
                    factor_family="trend",
                    source_layer="market_signals",
                    source_artifact=MARKET_SIGNALS_ARTIFACT,
                    source_record_id=_text_or_none(signal.get("signal_id")),
                    scope=_scope(symbol=signal.get("symbol"), timeframe=signal.get("timeframe")),
                    observed_at=_text_or_none(signal.get("latest_candle_time"))
                    or _text_or_none(signal.get("created_at"))
                    or self.created_at,
                    calculation_window={
                        "start": _text_or_none(signal.get("input_window_start")),
                        "end": _text_or_none(signal.get("input_window_end")),
                        "row_count": None,
                    },
                    value=_numeric_strength(signal.get("strength")),
                    value_unit="ordinal_strength",
                    direction_hint=_direction_from_signal(signal.get("direction")),
                    status="insufficient_evidence" if insufficient else "available",
                    confidence=_confidence(signal.get("confidence")),
                    evidence=_string_list(signal.get("evidence")),
                    uncertainty=_string_list(signal.get("uncertainty")),
                    warnings=["market signal has insufficient data."] if insufficient else [],
                    errors=[],
                    source_artifacts=[MARKET_SIGNALS_ARTIFACT, *_string_list(signal.get("source_artifacts"))],
                )
            )

    def add_derivatives_context(self) -> None:
        if not _derivatives_enabled(self.config):
            self._record_coverage(
                "derivatives_market",
                DERIVATIVES_MARKET_CONTEXT_ARTIFACT,
                "skipped",
                reason="market.derivatives.enabled is false.",
            )
            return
        self._add_context_records(
            source_layer="derivatives_market",
            artifact_path=DERIVATIVES_MARKET_CONTEXT_ARTIFACT,
            path=self.run.analysis_dir / "derivatives_market_context.json",
            mapper=_derivatives_feature_type,
        )

    def add_macro_calendar_context(self) -> None:
        if not _macro_calendar_enabled(self.config):
            self._record_coverage(
                "macro_calendar",
                MACRO_CALENDAR_CONTEXT_ARTIFACT,
                "skipped",
                reason="macro_calendar.enabled is false.",
            )
            return
        self._add_context_records(
            source_layer="macro_calendar",
            artifact_path=MACRO_CALENDAR_CONTEXT_ARTIFACT,
            path=self.run.analysis_dir / "macro_calendar_context.json",
            mapper=lambda record: ("macro_calendar_pressure", "macro_risk"),
        )

    def add_onchain_flow_context(self) -> None:
        if not _onchain_flow_enabled(self.config):
            self._record_coverage(
                "onchain_flow",
                ONCHAIN_FLOW_CONTEXT_ARTIFACT,
                "skipped",
                reason="onchain_flow.enabled is false.",
            )
            return
        self._add_context_records(
            source_layer="onchain_flow",
            artifact_path=ONCHAIN_FLOW_CONTEXT_ARTIFACT,
            path=self.run.analysis_dir / "onchain_flow_context.json",
            mapper=_onchain_feature_type,
        )

    def add_event_intelligence_assessment(self) -> None:
        if not _text_enabled(self.config):
            self._record_coverage(
                "event_intelligence",
                EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
                "skipped",
                reason="text.enabled is false.",
            )
            return
        data = self._read_source(
            "event_intelligence",
            EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
            self.run.analysis_dir / "event_intelligence_assessment.json",
            "records",
        )
        if data is None:
            return
        for record in _dict_list(data.get("records")):
            severity = record.get("severity") or record.get("event_severity")
            status = _normalize_status(record.get("status") or record.get("assessment_status") or "available")
            self.records.append(
                _feature_record(
                    run_id=self.run.run_id,
                    feature_type="event_pressure",
                    factor_family="event_pressure",
                    source_layer="event_intelligence",
                    source_artifact=EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
                    source_record_id=_record_id(
                        record,
                        "assessment_id",
                        "record_id",
                        "event_signal_id",
                        "topic_id",
                    ),
                    scope=_scope(symbol=record.get("symbol"), timeframe=record.get("timeframe"), asset=record.get("asset")),
                    observed_at=_observed_at(record, self.created_at),
                    calculation_window=_context_window(record),
                    value=_severity_value(severity),
                    value_unit="ordinal_severity",
                    direction_hint=_direction_from_event(record),
                    status=status,
                    confidence=_confidence(record.get("confidence")),
                    evidence=_record_evidence(record),
                    uncertainty=_string_list(record.get("uncertainty")),
                    warnings=_string_list(record.get("warnings")),
                    errors=_error_list(record.get("errors")),
                    source_artifacts=[
                        EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
                        *_string_list(record.get("source_artifacts")),
                    ],
                )
            )

    def add_outcome_evaluations(self) -> None:
        data = self._read_source(
            "outcome_tracking",
            OUTCOME_EVALUATIONS_ARTIFACT,
            self.run.analysis_dir / "outcome_evaluations.json",
            "evaluations",
            required=False,
        )
        if data is None:
            return
        for evaluation in _dict_list(data.get("evaluations")):
            self.records.append(
                _feature_record(
                    run_id=self.run.run_id,
                    feature_type="outcome_feedback",
                    factor_family="evidence_quality",
                    source_layer="outcome_tracking",
                    source_artifact=OUTCOME_EVALUATIONS_ARTIFACT,
                    source_record_id=_text_or_none(evaluation.get("outcome_id")),
                    scope=_scope(
                        symbol=evaluation.get("symbol"),
                        timeframe=evaluation.get("timeframe"),
                    ),
                    observed_at=_text_or_none(evaluation.get("evaluated_at")) or self.created_at,
                    calculation_window=_outcome_window(evaluation),
                    value=_outcome_value(evaluation.get("outcome_state")),
                    value_unit="ordinal_outcome_state",
                    direction_hint=_direction_from_outcome(evaluation.get("outcome_state")),
                    status=_normalize_status(evaluation.get("evaluation_status")),
                    confidence="low" if evaluation.get("evaluation_status") in {"pending", "insufficient"} else "medium",
                    evidence=_string_list(evaluation.get("evidence")),
                    uncertainty=[],
                    warnings=_string_list(evaluation.get("warnings")),
                    errors=_error_list(evaluation.get("errors")),
                    source_artifacts=[OUTCOME_EVALUATIONS_ARTIFACT, *_string_list(evaluation.get("source_artifacts"))],
                )
            )

    def add_data_quality_summary(self) -> None:
        data = self._read_source(
            "data_quality",
            DATA_QUALITY_SUMMARY_ARTIFACT,
            self.run.analysis_dir / "data_quality_summary.json",
            "checks",
        )
        if data is None:
            return
        counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
        status = _normalize_status(data.get("status"))
        self.records.append(
            _feature_record(
                run_id=self.run.run_id,
                feature_type="source_quality",
                factor_family="evidence_quality",
                source_layer="data_quality",
                source_artifact=DATA_QUALITY_SUMMARY_ARTIFACT,
                source_record_id=f"data_quality:{self.run.run_id}",
                scope=_scope(),
                observed_at=_text_or_none(data.get("created_at")) or self.created_at,
                calculation_window={"start": None, "end": _text_or_none(data.get("created_at")), "row_count": counts.get("checks")},
                value=_quality_value(data.get("status")),
                value_unit="bounded_-1_to_1",
                direction_hint=_direction_from_quality(data.get("status")),
                status=status,
                confidence="high" if status == "available" else "medium",
                evidence=[
                    f"Data quality status is {data.get('status') or 'unknown'}.",
                    f"{counts.get('checks', 0)} check(s), {counts.get('warnings', 0)} warning(s), {counts.get('errors', 0)} error(s).",
                ],
                uncertainty=_string_list(data.get("warnings")),
                warnings=_string_list(data.get("warnings")),
                errors=_error_list(data.get("errors")),
                source_artifacts=[DATA_QUALITY_SUMMARY_ARTIFACT, *_string_list(data.get("source_artifacts"))],
            )
        )

    def artifact(self) -> dict[str, Any]:
        records = sorted(self.records, key=lambda record: record["feature_id"])
        coverage = sorted(self.coverage, key=lambda item: (item["source_layer"], item["source_artifact"]))
        counts = _counts(records, coverage=coverage, warnings=self.warnings, errors=self.errors)
        status = _artifact_status(records, coverage=coverage, warnings=self.warnings, errors=self.errors)
        return {
            "schema_version": FEATURE_SNAPSHOTS_SCHEMA_VERSION,
            "artifact_type": "feature_snapshots",
            "run_id": self.run.run_id,
            "created_at": self.created_at,
            "status": status,
            "records": records,
            "coverage": coverage,
            "counts": counts,
            "warnings": _unique_sorted(self.warnings),
            "errors": self.errors,
            "source_artifacts": _unique_sorted(self.source_artifacts),
        }

    def _add_context_records(
        self,
        *,
        source_layer: str,
        artifact_path: str,
        path: Path,
        mapper,
    ) -> None:
        data = self._read_source(source_layer, artifact_path, path, "records")
        if data is None:
            return
        for record in _dict_list(data.get("records")):
            feature_type, factor_family = mapper(record)
            status = _normalize_status(record.get("status"))
            self.records.append(
                _feature_record(
                    run_id=self.run.run_id,
                    feature_type=feature_type,
                    factor_family=factor_family,
                    source_layer=source_layer,
                    source_artifact=artifact_path,
                    source_record_id=_record_id(record, "context_id", "record_id", "id"),
                    scope=_scope(
                        symbol=record.get("symbol"),
                        timeframe=record.get("timeframe") or record.get("period"),
                        asset=record.get("asset"),
                        chain=record.get("chain"),
                        region=record.get("region"),
                    ),
                    observed_at=_observed_at(record, self.created_at),
                    calculation_window=_context_window(record),
                    value=_context_value(record),
                    value_unit="ordinal_severity",
                    direction_hint=_direction_from_context(record),
                    status=status,
                    confidence=_confidence(record.get("confidence")),
                    evidence=_record_evidence(record),
                    uncertainty=_string_list(record.get("uncertainty")),
                    warnings=_string_list(record.get("warnings")),
                    errors=_error_list(record.get("errors")),
                    source_artifacts=[artifact_path, *_string_list(record.get("source_artifacts"))],
                )
            )

    def _read_source(
        self,
        source_layer: str,
        artifact_path: str,
        path: Path,
        records_key: str,
        *,
        required: bool = True,
    ) -> dict[str, Any] | None:
        data, error = _read_json(path)
        if error is not None:
            status = "missing" if error["type"] == "missing" else "failed"
            self._record_coverage(source_layer, artifact_path, status, error=error["message"])
            if required:
                self.warnings.append(error["message"])
            return None
        records = _list(data.get(records_key))
        warnings = _string_list(data.get("warnings"))
        errors = _error_list(data.get("errors"))
        self._record_coverage(
            source_layer,
            artifact_path,
            _coverage_status(data),
            records=len(records),
            warnings=len(warnings),
            errors=len(errors),
            artifact_status=_text_or_none(data.get("status")),
        )
        self.source_artifacts.extend([artifact_path, *_string_list(data.get("source_artifacts"))])
        self.warnings.extend(warnings)
        self.errors.extend(errors)
        return data

    def _record_coverage(
        self,
        source_layer: str,
        source_artifact: str,
        status: str,
        *,
        records: int = 0,
        warnings: int = 0,
        errors: int = 0,
        reason: str | None = None,
        error: str | None = None,
        artifact_status: str | None = None,
    ) -> None:
        coverage = {
            "source_layer": source_layer,
            "source_artifact": source_artifact,
            "status": status,
            "records": records,
            "warnings": warnings,
            "errors": errors,
            "reason": reason,
            "error": error,
            "artifact_status": artifact_status,
        }
        self.coverage.append(coverage)
        self.source_artifacts.append(source_artifact)


def _feature_record(
    *,
    run_id: str,
    feature_type: str,
    factor_family: str,
    source_layer: str,
    source_artifact: str,
    source_record_id: str | None,
    scope: dict[str, Any],
    observed_at: str,
    calculation_window: dict[str, Any],
    value: int | float | None,
    value_unit: str | None,
    direction_hint: str,
    status: str,
    confidence: str,
    evidence: list[Any],
    uncertainty: list[Any],
    warnings: list[Any],
    errors: list[Any],
    source_artifacts: list[str],
) -> dict[str, Any]:
    clean_source_record_id = source_record_id or "missing_source_record"
    clean_status = _normalize_status(status)
    return {
        "feature_id": _feature_id(
            feature_type=feature_type,
            source_layer=source_layer,
            scope=scope,
            source_record_id=clean_source_record_id,
            run_id=run_id,
        ),
        "feature_type": feature_type,
        "factor_family": factor_family,
        "source_layer": source_layer,
        "source_artifact": source_artifact,
        "source_record_id": source_record_id,
        "scope": scope,
        "observed_at": observed_at,
        "calculation_window": calculation_window,
        "value": value,
        "value_unit": value_unit,
        "direction_hint": _normalize_direction(direction_hint),
        "status": clean_status,
        "confidence": _confidence(confidence),
        "evidence": _string_list(evidence),
        "uncertainty": _string_list(uncertainty),
        "warnings": _string_list(warnings),
        "errors": _error_list(errors),
        "source_artifacts": _unique_sorted([source_artifact, *source_artifacts]),
    }


def _record_manifest(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = artifact["counts"]
    run.manifest["artifacts"]["feature_snapshots"] = FEATURE_SNAPSHOTS_ARTIFACT
    run.manifest["feature_snapshots"] = {
        "status": artifact["status"],
        "artifact": FEATURE_SNAPSHOTS_ARTIFACT,
        "records": counts["records"],
        "coverage_records": counts["coverage_records"],
        "source_layers": sorted(
            {
                str(item["source_layer"])
                for item in artifact["coverage"]
                if isinstance(item, dict) and item.get("source_layer")
            }
        ),
        "features_by_type": counts["features_by_type"],
        "features_by_source_layer": counts["features_by_source_layer"],
        "status_counts": counts["status_counts"],
        "source_status_counts": counts["source_status_counts"],
        "warnings": counts["warnings"],
        "errors": counts["errors"],
    }
    run.manifest["counts"]["feature_snapshots"] = counts["records"]
    run.manifest["counts"]["feature_snapshot_coverage_records"] = counts["coverage_records"]
    run.manifest["counts"]["feature_snapshot_warnings"] = counts["warnings"]
    run.manifest["counts"]["feature_snapshot_errors"] = counts["errors"]


def _read_json(path: Path) -> tuple[dict[str, Any], dict[str, str] | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, {"type": "missing", "message": f"{path.name} was not found."}
    except JSONDecodeError as exc:
        return {}, {"type": "invalid_json", "message": f"{path.name} is not valid JSON: {exc.msg}."}
    if not isinstance(data, dict):
        return {}, {"type": "invalid_shape", "message": f"{path.name} must contain a JSON object."}
    return data, None


def _counts(
    records: list[dict[str, Any]],
    *,
    coverage: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "records": len(records),
        "coverage_records": len(coverage),
        "features_by_type": _count_by(records, "feature_type"),
        "features_by_source_layer": _count_by(records, "source_layer"),
        "status_counts": _count_by(records, "status"),
        "source_status_counts": _count_by(coverage, "status"),
        "warnings": sum(len(_string_list(record.get("warnings"))) for record in records) + len(warnings),
        "errors": sum(len(_error_list(record.get("errors"))) for record in records) + len(errors),
    }


def _artifact_status(
    records: list[dict[str, Any]],
    *,
    coverage: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> str:
    if errors or any(item.get("status") == "failed" for item in coverage):
        return "failed"
    if any(item.get("status") in {"missing", "unavailable"} for item in coverage):
        return "degraded"
    if warnings or any(record.get("status") in {"stale", "partial", "degraded"} for record in records):
        return "warning"
    if records:
        return "ok"
    return "skipped"


def _coverage_status(data: dict[str, Any]) -> str:
    status = str(data.get("status") or "available").strip().lower()
    if status in {"ok", "succeeded", "available"}:
        return "available"
    if status in {"warning", "partial", "degraded", "stale", "insufficient", "insufficient_evidence"}:
        return status
    if status in {"failed", "skipped", "unavailable", "missing"}:
        return status
    return "available"


def _normalize_status(value: Any) -> str:
    status = str(value or "available").strip().lower()
    mapping = {
        "ok": "available",
        "succeeded": "available",
        "success": "available",
        "warning": "degraded",
        "bounded": "partial",
        "insufficient": "insufficient_evidence",
        "insufficient_data": "insufficient_evidence",
        "no_event": "neutral",
        "pending": "insufficient_evidence",
        "skipped": "missing",
    }
    status = mapping.get(status, status)
    allowed = {
        "available",
        "neutral",
        "missing",
        "stale",
        "partial",
        "degraded",
        "insufficient_evidence",
        "conflicting",
        "failed",
        "unavailable",
    }
    if status in allowed:
        return "missing" if status == "unavailable" else status
    return "available"


def _normalize_direction(value: Any) -> str:
    direction = str(value or "unknown").strip().lower()
    if direction in {"supportive", "cautionary", "neutral", "conflicting", "unknown"}:
        return direction
    return "unknown"


def _confidence(value: Any) -> str:
    confidence = str(value or "unknown").strip().lower()
    if confidence in {"high", "medium", "low", "unknown"}:
        return confidence
    return "unknown"


def _scope(
    *,
    symbol: Any = None,
    timeframe: Any = None,
    asset: Any = None,
    chain: Any = None,
    region: Any = None,
) -> dict[str, Any]:
    return {
        "symbol": _text_or_none(symbol),
        "timeframe": _text_or_none(timeframe),
        "asset": _text_or_none(asset),
        "chain": _text_or_none(chain),
        "region": _text_or_none(region),
    }


def _feature_id(
    *,
    feature_type: str,
    source_layer: str,
    scope: dict[str, Any],
    source_record_id: str,
    run_id: str,
) -> str:
    scope_parts = [
        scope.get("symbol"),
        scope.get("timeframe"),
        scope.get("asset"),
        scope.get("chain"),
        scope.get("region"),
    ]
    scope_key = ":".join(_slug(part) for part in scope_parts if part)
    if not scope_key:
        scope_key = "global"
    return f"feature:{feature_type}:{source_layer}:{scope_key}:{_slug(source_record_id)}:{_slug(run_id)}"


def _raw_market_evidence(item: dict[str, Any]) -> list[str]:
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    evidence = []
    if metrics.get("price") is not None:
        evidence.append(f"Last price: {metrics.get('price')}.")
    if metrics.get("change_24h_pct") is not None:
        evidence.append(f"24h change percent: {metrics.get('change_24h_pct')}.")
    if metrics.get("quote_volume_24h") is not None:
        evidence.append(f"24h quote volume: {metrics.get('quote_volume_24h')}.")
    return evidence


def _record_evidence(record: dict[str, Any]) -> list[str]:
    evidence = _string_list(record.get("evidence"))
    if evidence:
        return evidence
    summary_parts = []
    for key in ("context_type", "state", "severity", "event_name", "decision_impact", "market_response_relationship"):
        value = _text_or_none(record.get(key))
        if value:
            summary_parts.append(f"{key}: {value}")
    return ["; ".join(summary_parts)] if summary_parts else []


def _context_window(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "start": _text_or_none(record.get("input_window_start")),
        "end": (
            _text_or_none(record.get("input_window_end"))
            or _text_or_none(record.get("as_of"))
            or _text_or_none(record.get("scheduled_at"))
            or _text_or_none(record.get("latest_candle_time"))
        ),
        "row_count": _int_or_none(record.get("row_count")),
    }


def _outcome_window(evaluation: dict[str, Any]) -> dict[str, Any]:
    window = evaluation.get("observation_window") if isinstance(evaluation.get("observation_window"), dict) else {}
    return {
        "start": _text_or_none(window.get("start")),
        "end": _text_or_none(window.get("end")) or _text_or_none(window.get("horizon_end")),
        "row_count": _int_or_none(window.get("sample_rows")),
    }


def _observed_at(record: dict[str, Any], fallback: str) -> str:
    for key in ("as_of", "scheduled_at", "created_at", "evaluated_at", "latest_candle_time", "input_window_end"):
        value = _text_or_none(record.get(key))
        if value:
            return value
    return fallback


def _derivatives_feature_type(record: dict[str, Any]) -> tuple[str, str]:
    context_type = str(record.get("context_type") or "").lower()
    data_class = str(record.get("data_class") or "").lower()
    if "liquidity" in context_type or data_class in {"spread_depth", "liquidation_summary"}:
        return "derivatives_liquidity_pressure", "liquidity"
    return "derivatives_leverage_pressure", "leverage"


def _onchain_feature_type(record: dict[str, Any]) -> tuple[str, str]:
    context_type = str(record.get("context_type") or "").lower()
    data_class = str(record.get("data_class") or "").lower()
    if "stablecoin" in context_type or data_class == "stablecoin_supply":
        return "onchain_liquidity_context", "liquidity"
    return "onchain_activity_context", "onchain_flow"


def _context_value(record: dict[str, Any]) -> int | None:
    severity_value = _severity_value(record.get("severity"))
    if severity_value is not None:
        return severity_value
    state = str(record.get("state") or "").lower()
    if state in {"normal", "no_event", "stable", "available"}:
        return 0
    if state in {"stressed", "extreme", "surging", "contraction", "unavailable", "failed"}:
        return 2
    return None


def _severity_value(value: Any) -> int | None:
    severity = str(value or "").strip().lower()
    mapping = {
        "none": 0,
        "low": 1,
        "medium": 2,
        "moderate": 2,
        "high": 3,
        "critical": 4,
        "extreme": 4,
    }
    return mapping.get(severity)


def _numeric_strength(value: Any) -> int | None:
    strength = str(value or "").strip().lower()
    mapping = {
        "none": 0,
        "weak": 1,
        "low": 1,
        "medium": 2,
        "moderate": 2,
        "strong": 3,
        "high": 3,
        "extreme": 4,
    }
    return mapping.get(strength)


def _quality_value(value: Any) -> float | None:
    status = str(value or "").strip().lower()
    mapping = {
        "ok": 1.0,
        "warning": 0.3,
        "degraded": -0.4,
        "failed": -1.0,
        "skipped": 0.0,
    }
    return mapping.get(status)


def _outcome_value(value: Any) -> int | None:
    state = str(value or "").strip().lower()
    mapping = {
        "confirmed": 1,
        "mixed": 0,
        "unresolved": 0,
        "skipped": 0,
        "failed": -1,
        "invalidated": -1,
    }
    return mapping.get(state)


def _direction_from_number(value: int | float | None) -> str:
    if value is None:
        return "unknown"
    if value > 0:
        return "supportive"
    if value < 0:
        return "cautionary"
    return "neutral"


def _direction_from_signal(value: Any) -> str:
    direction = str(value or "").strip().lower()
    if direction in {"long", "buy", "bullish", "up", "positive"}:
        return "supportive"
    if direction in {"short", "sell", "bearish", "down", "negative"}:
        return "cautionary"
    if direction in {"flat", "neutral", "hold"}:
        return "neutral"
    if direction == "conflicting":
        return "conflicting"
    return "unknown"


def _direction_from_context(record: dict[str, Any]) -> str:
    status = _normalize_status(record.get("status"))
    state = str(record.get("state") or "").lower()
    severity = str(record.get("severity") or "").lower()
    if status in {"failed", "stale", "partial", "degraded", "insufficient_evidence", "missing"}:
        return "cautionary"
    if "conflict" in state:
        return "conflicting"
    if state in {"normal", "no_event", "stable", "available"} or severity == "low":
        return "neutral"
    if severity in {"high", "critical", "extreme"}:
        return "cautionary"
    return "unknown"


def _direction_from_event(record: dict[str, Any]) -> str:
    impact = str(record.get("decision_impact") or record.get("impact") or "").lower()
    severity = str(record.get("severity") or record.get("event_severity") or "").lower()
    status = _normalize_status(record.get("status") or record.get("assessment_status"))
    if status in {"failed", "stale", "partial", "degraded", "insufficient_evidence", "missing"}:
        return "cautionary"
    if "conflict" in impact:
        return "conflicting"
    if "downgrade" in impact or "block" in impact:
        return "cautionary"
    if severity in {"high", "critical"}:
        return "cautionary"
    if severity in {"low", "none"}:
        return "neutral"
    return "unknown"


def _direction_from_outcome(value: Any) -> str:
    state = str(value or "").strip().lower()
    if state == "confirmed":
        return "supportive"
    if state in {"invalidated", "failed"}:
        return "cautionary"
    if state in {"mixed", "unresolved", "skipped"}:
        return "neutral"
    return "unknown"


def _direction_from_quality(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status == "ok":
        return "supportive"
    if status in {"warning", "degraded", "failed"}:
        return "cautionary"
    if status == "skipped":
        return "neutral"
    return "unknown"


def _metric_number(metrics: Any, key: str) -> float | None:
    if not isinstance(metrics, dict):
        return None
    value = metrics.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_id(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _text_or_none(record.get(key))
        if value:
            return value
    return None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        strings = []
        for item in value:
            if isinstance(item, dict):
                strings.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            elif isinstance(item, (str, int, float)) and str(item):
                strings.append(str(item))
        return strings
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
    return [str(value)] if str(value) else []


def _error_list(value: Any) -> list[dict[str, Any]]:
    errors = []
    for item in _list(value):
        if isinstance(item, dict):
            errors.append(item)
        elif isinstance(item, str):
            errors.append({"message": item})
    return errors


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _unique_sorted(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, (str, int, float)) and str(value)})


def _slug(value: Any) -> str:
    text = str(value or "missing").strip().lower()
    chars = []
    for char in text:
        if char.isalnum() or char in {"_", "-", "."}:
            chars.append(char)
        else:
            chars.append("_")
    return "".join(chars).strip("_") or "missing"


def _format_utc(value: datetime | str | None = None) -> str:
    if isinstance(value, str):
        return value
    timestamp = value or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


def _market_enabled(config: dict[str, Any]) -> bool:
    market = config.get("market")
    return isinstance(market, dict) and market.get("enabled") is True


def _ohlcv_configured(config: dict[str, Any]) -> bool:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market, dict) else None
    return isinstance(ohlcv, dict) and bool(ohlcv)


def _quant_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant")
    return isinstance(quant, dict) and quant.get("enabled") is True


def _derivatives_enabled(config: dict[str, Any]) -> bool:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    derivatives = market.get("derivatives") if isinstance(market, dict) else None
    return isinstance(derivatives, dict) and derivatives.get("enabled") is True


def _macro_calendar_enabled(config: dict[str, Any]) -> bool:
    macro_calendar = config.get("macro_calendar")
    return isinstance(macro_calendar, dict) and macro_calendar.get("enabled") is True


def _onchain_flow_enabled(config: dict[str, Any]) -> bool:
    onchain_flow = config.get("onchain_flow")
    return isinstance(onchain_flow, dict) and onchain_flow.get("enabled") is True


def _text_enabled(config: dict[str, Any]) -> bool:
    text = config.get("text")
    return isinstance(text, dict) and text.get("enabled") is True
