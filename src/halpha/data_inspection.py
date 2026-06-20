from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .research_data_catalog import CATALOG_ARTIFACT, research_data_catalog_path
from .run_index import RUN_INDEX_ARTIFACT, run_index_path
from .workbench import (
    DEFAULT_WORKBENCH_OUTPUT_DIR,
    WORKBENCH_HTML_FILENAME,
    WORKBENCH_MARKDOWN_FILENAME,
    WORKBENCH_SUMMARY_FILENAME,
)


TEXT_EVENT_HISTORY_STATE_ARTIFACT = "data/research/metadata/text_event_history_state.json"
OHLCV_SCHEMA_ARTIFACT = "data/market/metadata/ohlcv_schema.json"
OHLCV_SYNC_STATE_ARTIFACT = "data/market/metadata/ohlcv_sync_state.json"
DERIVATIVES_SCHEMA_ARTIFACT = "data/market/metadata/derivatives_market_schema.json"
DERIVATIVES_STATE_ARTIFACT = "data/market/metadata/derivatives_market_state.json"
DERIVATIVES_VIEWS_ARTIFACT = "raw/derivatives_market_views.json"
MACRO_CALENDAR_SCHEMA_ARTIFACT = "data/macro/metadata/macro_calendar_schema.json"
MACRO_CALENDAR_STATE_ARTIFACT = "data/macro/metadata/macro_calendar_state.json"
MACRO_CALENDAR_VIEWS_ARTIFACT = "raw/macro_calendar_views.json"
ONCHAIN_FLOW_SCHEMA_ARTIFACT = "data/onchain/metadata/onchain_flow_schema.json"
ONCHAIN_FLOW_STATE_ARTIFACT = "data/onchain/metadata/onchain_flow_state.json"
ONCHAIN_FLOW_VIEWS_ARTIFACT = "raw/onchain_flow_views.json"
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
FEATURE_SNAPSHOTS_ARTIFACT = "analysis/feature_snapshots.json"
FACTOR_STATES_ARTIFACT = "analysis/factor_states.json"
MULTI_SOURCE_SIGNALS_ARTIFACT = "analysis/multi_source_signals.json"
FACTOR_SIGNAL_MATERIAL_ARTIFACT = "analysis/factor_signal_material.md"
INTELLIGENCE_FUSION_ARTIFACT = "analysis/intelligence_fusion.json"
INTELLIGENCE_FUSION_MATERIAL_ARTIFACT = "analysis/intelligence_fusion_material.md"
STRATEGY_LIFECYCLE_STATE_ARTIFACT = "analysis/strategy_lifecycle_state.json"
STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT = "analysis/strategy_lifecycle_material.md"
USER_STATE_CONTEXT_ARTIFACT = "analysis/user_state_context.json"
PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT = "analysis/personalized_risk_constraints.json"
PERSONALIZED_RISK_MATERIAL_ARTIFACT = "analysis/personalized_risk_material.md"
PRODUCT_CONTRACT_VALIDATION_ARTIFACT = "analysis/product_contract_validation.json"
M13_CHECK_NAMES = {
    "feature_snapshots",
    "factor_states",
    "multi_source_signals",
    "factor_signal_material",
}
FUSION_CHECK_NAMES = {
    "intelligence_fusion",
    "intelligence_fusion_material",
}
M15_CHECK_NAMES = {
    "user_state_context",
    "personalized_risk_constraints",
    "personalized_risk_material",
}


class DataInspectionError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class DataInspectionResult:
    status: str
    lines: list[str]


def inspect_local_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_dir: Path | None = None,
) -> DataInspectionResult:
    base = config_path.parent
    sections = [
        _catalog_section(config_path, base=base),
        _run_index_section(config_path, base=base),
        _text_event_history_section(config_path, base=base),
        _ohlcv_section(config, config_path, base=base),
        _derivatives_section(config, config_path, run_dir=run_dir, base=base),
        _macro_calendar_section(config, config_path, run_dir=run_dir, base=base),
        _onchain_flow_section(config, config_path, run_dir=run_dir, base=base),
        _feature_factor_artifacts_section(config_path, run_dir=run_dir, base=base),
        _intelligence_fusion_section(config_path, run_dir=run_dir, base=base),
        _strategy_lifecycle_section(config_path, run_dir=run_dir, base=base),
        _personalized_risk_section(config_path, run_dir=run_dir, base=base),
        _product_validation_section(config_path, run_dir=run_dir, base=base),
        _workbench_section(config_path, base=base),
    ]
    quality = _quality_section(config_path, run_dir=run_dir, base=base)
    status = _overall_status([section["status"] for section in sections] + [quality["status"]])

    lines = [
        "Halpha data inspection succeeded.",
        f"status: {status}",
        f"config: {_safe_path(config_path, base=Path.cwd())}",
        "stores:",
    ]
    for section in sections:
        lines.extend(_section_lines(section))
    lines.append("quality:")
    lines.extend(_section_lines(quality))
    return DataInspectionResult(status=status, lines=lines)


def _catalog_section(config_path: Path, *, base: Path) -> dict[str, Any]:
    path = research_data_catalog_path(config_path)
    data, error = _read_json(path)
    if error:
        return _section(
            "research_data_catalog",
            "skipped",
            artifact=CATALOG_ARTIFACT,
            reason=error,
        )
    counts = _dict(data.get("counts"))
    return _section(
        "research_data_catalog",
        str(data.get("status") or "unknown"),
        artifact=CATALOG_ARTIFACT,
        fields={
            "stores": _int(counts.get("stores")),
            "records": _int(counts.get("records")),
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
        },
        extra={"store_statuses": _store_statuses(data)},
    )


def _run_index_section(config_path: Path, *, base: Path) -> dict[str, Any]:
    path = run_index_path(config_path)
    if not path.exists():
        return _section(
            "run_index",
            "skipped",
            artifact=RUN_INDEX_ARTIFACT,
            reason="run index was not found.",
        )
    try:
        with closing(sqlite3.connect(path)) as connection:
            counts = {
                "runs": _table_count(connection, "runs"),
                "run_stages": _table_count(connection, "run_stages"),
                "run_artifacts": _table_count(connection, "run_artifacts"),
                "run_latest": _table_count(connection, "run_latest"),
            }
            latest = _latest_run_id(connection)
    except sqlite3.Error as exc:
        raise DataInspectionError(f"{RUN_INDEX_ARTIFACT} is not readable: {exc}") from exc
    fields: dict[str, Any] = dict(counts)
    if latest:
        fields["latest_successful_run_id"] = latest
    return _section("run_index", "ok", artifact=RUN_INDEX_ARTIFACT, fields=fields)


def _text_event_history_section(config_path: Path, *, base: Path) -> dict[str, Any]:
    path = base / TEXT_EVENT_HISTORY_STATE_ARTIFACT
    data, error = _read_json(path)
    if error:
        return _section(
            "text_event_history",
            "skipped",
            artifact=TEXT_EVENT_HISTORY_STATE_ARTIFACT,
            reason=error,
        )
    totals = _dict(data.get("totals"))
    return _section(
        "text_event_history",
        str(data.get("status") or "unknown"),
        artifact=TEXT_EVENT_HISTORY_STATE_ARTIFACT,
        fields={
            "records": _int(totals.get("records")),
            "sources": len(_list(data.get("sources"))),
            "warnings": len(_list(data.get("warnings"))),
            "errors": len(_list(data.get("errors"))),
        },
    )


def _ohlcv_section(config: dict[str, Any], config_path: Path, *, base: Path) -> dict[str, Any]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market, dict) else None
    if not isinstance(ohlcv, dict):
        return _section("ohlcv_history", "skipped", reason="market.ohlcv is not configured.")
    schema, schema_error = _read_json(base / OHLCV_SCHEMA_ARTIFACT)
    state, state_error = _read_json(base / OHLCV_SYNC_STATE_ARTIFACT)
    warnings = [error for error in (schema_error, state_error) if error]
    items = _list(state.get("items")) if isinstance(state, dict) else []
    record_count = sum(_int(item.get("row_count")) for item in items if isinstance(item, dict))
    status = "warning" if warnings else str(state.get("status") or "ok")
    return _section(
        "ohlcv_history",
        status,
        artifact=OHLCV_SYNC_STATE_ARTIFACT,
        fields={
            "records": record_count,
            "items": len(items),
            "schema_version": schema.get("schema_version") if isinstance(schema, dict) else None,
            "warnings": len(warnings),
        },
        reason="; ".join(warnings) if warnings else None,
    )


def _derivatives_section(
    config: dict[str, Any],
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    derivatives = market.get("derivatives") if isinstance(market, dict) else None
    if not isinstance(derivatives, dict) or not derivatives.get("enabled"):
        return _section("derivatives_market_history", "skipped", reason="market.derivatives is not enabled.")

    schema, schema_error = _read_json(base / DERIVATIVES_SCHEMA_ARTIFACT)
    state, state_error = _read_json(base / DERIVATIVES_STATE_ARTIFACT)
    warnings = [error for error in (schema_error, state_error) if error]
    totals = _dict(state.get("totals")) if isinstance(state, dict) else {}
    groups = _list(state.get("groups")) if isinstance(state, dict) else []
    fields = {
        "records": _int(totals.get("records")),
        "groups": len(groups),
        "schema_version": schema.get("schema_version") if isinstance(schema, dict) else None,
        "warnings": len(_list(state.get("warnings"))) if isinstance(state, dict) else len(warnings),
        "errors": len(_list(state.get("errors"))) if isinstance(state, dict) else 0,
    }

    view_run_dir = _resolve_run_dir(run_dir, base=base) if run_dir is not None else _latest_run_from_index(config_path)
    if view_run_dir is not None:
        views, views_error = _read_json(view_run_dir / DERIVATIVES_VIEWS_ARTIFACT)
        if views_error:
            warnings.append(views_error)
        else:
            view_records = _list(views.get("views"))
            fields["views"] = len(view_records)
            fields["insufficient_views"] = sum(
                1 for view in view_records if isinstance(view, dict) and view.get("insufficient_data")
            )
            fields["skipped_views"] = sum(
                1 for view in view_records if isinstance(view, dict) and view.get("status") == "skipped"
            )

    status = "warning" if warnings else str(state.get("status") or "ok")
    return _section(
        "derivatives_market_history",
        status,
        artifact=DERIVATIVES_STATE_ARTIFACT,
        fields=fields,
        reason="; ".join(warnings) if warnings else None,
    )


def _macro_calendar_section(
    config: dict[str, Any],
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    macro_calendar = config.get("macro_calendar") if isinstance(config.get("macro_calendar"), dict) else None
    if not isinstance(macro_calendar, dict) or not macro_calendar.get("enabled"):
        return _section("macro_calendar_history", "skipped", reason="macro_calendar is not enabled.")

    schema, schema_error = _read_json(base / MACRO_CALENDAR_SCHEMA_ARTIFACT)
    state, state_error = _read_json(base / MACRO_CALENDAR_STATE_ARTIFACT)
    warnings = [error for error in (schema_error, state_error) if error]
    totals = _dict(state.get("totals")) if isinstance(state, dict) else {}
    groups = _list(state.get("groups")) if isinstance(state, dict) else []
    availability = _list(state.get("availability")) if isinstance(state, dict) else []
    fields = {
        "records": _int(totals.get("records")),
        "groups": len(groups),
        "schema_version": schema.get("schema_version") if isinstance(schema, dict) else None,
        "warnings": len(_list(state.get("warnings"))) if isinstance(state, dict) else len(warnings),
        "errors": len(_list(state.get("errors"))) if isinstance(state, dict) else 0,
        "duplicate_records": _int(totals.get("duplicate_records")),
        "conflicting_duplicates": _int(totals.get("conflicting_duplicates")),
        "availability_records": len(availability),
        "no_event_records": _status_count(availability, "no_event"),
        "unavailable_records": _status_count(availability, "unavailable"),
        "partial_records": _status_count(availability, "partial"),
        "failed_records": _status_count(availability, "failed"),
        "stale_records": _status_count(availability, "stale"),
        "degraded_records": _status_count(availability, "degraded"),
    }

    view_run_dir = _resolve_run_dir(run_dir, base=base) if run_dir is not None else _latest_run_from_index(config_path)
    if view_run_dir is not None:
        views, views_error = _read_json(view_run_dir / MACRO_CALENDAR_VIEWS_ARTIFACT)
        if views_error:
            warnings.append(views_error)
        else:
            view_records = _list(views.get("views"))
            fields["views"] = len(view_records)
            fields["view_records"] = sum(_int(view.get("included_record_count")) for view in view_records if isinstance(view, dict))
            fields["no_event_views"] = _status_count(view_records, "no_event")
            fields["stale_views"] = _status_count(view_records, "stale")
            fields["unavailable_views"] = _status_count(view_records, "unavailable")
            fields["skipped_views"] = _status_count(view_records, "skipped")

    status = "warning" if warnings else str(state.get("status") or "ok")
    return _section(
        "macro_calendar_history",
        status,
        artifact=MACRO_CALENDAR_STATE_ARTIFACT,
        fields=fields,
        reason="; ".join(warnings) if warnings else None,
    )


def _onchain_flow_section(
    config: dict[str, Any],
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    onchain_flow = config.get("onchain_flow") if isinstance(config.get("onchain_flow"), dict) else None
    if not isinstance(onchain_flow, dict) or not onchain_flow.get("enabled"):
        return _section("onchain_flow_history", "skipped", reason="onchain_flow is not enabled.")

    schema, schema_error = _read_json(base / ONCHAIN_FLOW_SCHEMA_ARTIFACT)
    state, state_error = _read_json(base / ONCHAIN_FLOW_STATE_ARTIFACT)
    warnings = [error for error in (schema_error, state_error) if error]
    totals = _dict(state.get("totals")) if isinstance(state, dict) else {}
    groups = _list(state.get("groups")) if isinstance(state, dict) else []
    availability = _list(state.get("availability")) if isinstance(state, dict) else []
    fields = {
        "records": _int(totals.get("records")),
        "groups": len(groups),
        "schema_version": schema.get("schema_version") if isinstance(schema, dict) else None,
        "warnings": len(_list(state.get("warnings"))) if isinstance(state, dict) else len(warnings),
        "errors": len(_list(state.get("errors"))) if isinstance(state, dict) else 0,
        "duplicate_records": _int(totals.get("duplicate_records")),
        "conflicting_duplicates": _int(totals.get("conflicting_duplicates")),
        "availability_records": len(availability),
        "unavailable_records": _status_count(availability, "unavailable"),
        "partial_records": _status_count(availability, "partial"),
        "failed_records": _status_count(availability, "failed"),
        "stale_records": _status_count(availability, "stale"),
        "degraded_records": _status_count(availability, "degraded"),
        "insufficient_data_records": _status_count(availability, "insufficient_data"),
    }

    view_run_dir = _resolve_run_dir(run_dir, base=base) if run_dir is not None else _latest_run_from_index(config_path)
    if view_run_dir is not None:
        views, views_error = _read_json(view_run_dir / ONCHAIN_FLOW_VIEWS_ARTIFACT)
        if views_error:
            warnings.append(views_error)
        else:
            view_records = _list(views.get("views"))
            fields["views"] = len(view_records)
            fields["view_records"] = sum(_int(view.get("included_record_count")) for view in view_records if isinstance(view, dict))
            fields["bounded_views"] = _status_count(view_records, "bounded")
            fields["partial_views"] = _status_count(view_records, "partial")
            fields["stale_views"] = _status_count(view_records, "stale")
            fields["unavailable_views"] = _status_count(view_records, "unavailable")
            fields["skipped_views"] = _status_count(view_records, "skipped")

    status = "warning" if warnings else str(state.get("status") or "ok")
    return _section(
        "onchain_flow_history",
        status,
        artifact=ONCHAIN_FLOW_STATE_ARTIFACT,
        fields=fields,
        reason="; ".join(warnings) if warnings else None,
    )


def _feature_factor_artifacts_section(
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    if run_dir is not None:
        resolved_run_dir = _resolve_run_dir(run_dir, base=base)
    else:
        resolved_run_dir = _latest_run_from_index(config_path)
    if resolved_run_dir is None:
        return _section(
            "feature_factor_artifacts",
            "skipped",
            reason="no latest run was found in the local run index.",
        )

    manifest_path = resolved_run_dir / "run_manifest.json"
    manifest, manifest_error = _read_json(manifest_path)
    if manifest_error:
        raise DataInspectionError(f"run_manifest.json could not be inspected: {manifest_error}")

    artifacts = _dict(manifest.get("artifacts"))
    counts = _dict(manifest.get("counts"))
    artifact_summaries = {
        "feature_snapshots": _dict(manifest.get("feature_snapshots")),
        "factor_states": _dict(manifest.get("factor_states")),
        "multi_source_signals": _dict(manifest.get("multi_source_signals")),
        "factor_signal_material": _dict(manifest.get("factor_signal_material")),
    }
    has_m13_artifacts = any(
        artifacts.get(key)
        for key in ("feature_snapshots", "factor_states", "multi_source_signals", "factor_signal_material")
    ) or any(summary for summary in artifact_summaries.values())

    quality, quality_error = _read_json(resolved_run_dir / DATA_QUALITY_SUMMARY_ARTIFACT)
    quality_counts = _m13_quality_check_counts(quality)
    if not has_m13_artifacts and not any(quality_counts.values()):
        return _section(
            "feature_factor_artifacts",
            "skipped",
            artifact=_safe_path(manifest_path, base=base),
            fields={
                "run_id": manifest.get("run_id"),
                "run_status": manifest.get("status"),
            },
            reason="M13 feature/factor artifacts were not found in this run.",
        )

    budget = _codex_material_budget(manifest, FACTOR_SIGNAL_MATERIAL_ARTIFACT)
    fields = {
        "run_id": manifest.get("run_id"),
        "run_status": manifest.get("status"),
        "feature_records": _int(counts.get("feature_snapshots")),
        "feature_coverage_records": _int(counts.get("feature_snapshot_coverage_records")),
        "feature_warnings": _int(counts.get("feature_snapshot_warnings")),
        "feature_errors": _int(counts.get("feature_snapshot_errors")),
        "factor_records": _int(counts.get("factor_states")),
        "factor_warnings": _int(counts.get("factor_state_warnings")),
        "factor_errors": _int(counts.get("factor_state_errors")),
        "signal_records": _int(counts.get("multi_source_signals")),
        "signal_conflicting": _int(counts.get("multi_source_signal_conflicting")),
        "signal_warnings": _int(counts.get("multi_source_signal_warnings")),
        "signal_errors": _int(counts.get("multi_source_signal_errors")),
        "material_records": _int(counts.get("factor_signal_material_records")),
        "material_omitted_records": _int(counts.get("factor_signal_material_omitted_records")),
        "m13_quality_ok": quality_counts["ok"],
        "m13_quality_warning": quality_counts["warning"],
        "m13_quality_degraded": quality_counts["degraded"],
        "m13_quality_skipped": quality_counts["skipped"],
        "m13_quality_failed": quality_counts["failed"],
        "manifest": _safe_path(manifest_path, base=base),
    }
    if budget:
        fields.update(
            {
                "codex_budget_status": budget.get("status") or "unknown",
                "codex_budget_chars": _int(budget.get("chars")),
                "codex_budget_over_budget": bool(budget.get("over_budget")),
                "codex_budget_warnings": len(_list(budget.get("warnings"))),
            }
        )
    else:
        fields["codex_budget_status"] = "not_available"

    statuses = [
        str(summary.get("status"))
        for summary in artifact_summaries.values()
        if isinstance(summary.get("status"), str) and summary.get("status")
    ]
    statuses.extend(status for status, value in quality_counts.items() for _ in range(value))
    if budget and (budget.get("over_budget") or budget.get("status") not in {None, "included"}):
        statuses.append("warning")
    status = _status_from_values(statuses)
    reason = quality_error if quality_error else None
    return _section(
        "feature_factor_artifacts",
        status,
        artifact=_safe_path(manifest_path, base=base),
        fields=fields,
        reason=reason,
    )


def _quality_section(config_path: Path, *, run_dir: Path | None, base: Path) -> dict[str, Any]:
    if run_dir is not None:
        resolved_run_dir = _resolve_run_dir(run_dir, base=base)
        return _quality_section_from_run_dir(resolved_run_dir, base=base)

    latest = _latest_run_from_index(config_path)
    if latest is None:
        return _section(
            "data_quality_summary",
            "skipped",
            artifact=DATA_QUALITY_SUMMARY_ARTIFACT,
            reason="no latest run was found in the local run index.",
        )
    return _quality_section_from_run_dir(latest, base=base)


def _quality_section_from_run_dir(run_dir: Path, *, base: Path) -> dict[str, Any]:
    manifest_path = run_dir / "run_manifest.json"
    manifest, manifest_error = _read_json(manifest_path)
    if manifest_error:
        raise DataInspectionError(f"run_manifest.json could not be inspected: {manifest_error}")
    quality_path = run_dir / DATA_QUALITY_SUMMARY_ARTIFACT
    quality, quality_error = _read_json(quality_path)
    if quality_error:
        return _section(
            "data_quality_summary",
            "skipped",
            artifact=_safe_path(quality_path, base=base),
            reason=quality_error,
            fields={
                "run_id": manifest.get("run_id"),
                "run_status": manifest.get("status"),
                "manifest": _safe_path(manifest_path, base=base),
            },
        )
    counts = _dict(quality.get("counts"))
    return _section(
        "data_quality_summary",
        str(quality.get("status") or "unknown"),
        artifact=_safe_path(quality_path, base=base),
        fields={
            "run_id": quality.get("run_id") or manifest.get("run_id"),
            "run_status": manifest.get("status"),
            "checks": _int(counts.get("checks")),
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
            "degraded": _int(counts.get("degraded")),
            "failed": _int(counts.get("failed")),
            "manifest": _safe_path(manifest_path, base=base),
        },
    )


def _intelligence_fusion_section(
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    if run_dir is not None:
        resolved_run_dir = _resolve_run_dir(run_dir, base=base)
    else:
        resolved_run_dir = _latest_run_from_index(config_path)
    if resolved_run_dir is None:
        return _section(
            "intelligence_fusion",
            "skipped",
            reason="no latest run was found in the local run index.",
        )

    manifest_path = resolved_run_dir / "run_manifest.json"
    manifest, manifest_error = _read_json(manifest_path)
    if manifest_error:
        raise DataInspectionError(f"run_manifest.json could not be inspected: {manifest_error}")

    artifacts = _dict(manifest.get("artifacts"))
    counts = _dict(manifest.get("counts"))
    fusion_summary = _dict(manifest.get("intelligence_fusion"))
    integration_summary = _dict(manifest.get("intelligence_fusion_integration"))
    material_summary = _dict(manifest.get("intelligence_fusion_material"))
    has_fusion_artifacts = any(
        artifacts.get(key) for key in ("intelligence_fusion", "intelligence_fusion_material")
    ) or any((fusion_summary, integration_summary, material_summary))

    quality, quality_error = _read_json(resolved_run_dir / DATA_QUALITY_SUMMARY_ARTIFACT)
    quality_counts = _fusion_quality_check_counts(quality)
    if not has_fusion_artifacts and not any(quality_counts.values()):
        return _section(
            "intelligence_fusion",
            "skipped",
            artifact=_safe_path(manifest_path, base=base),
            fields={
                "run_id": manifest.get("run_id"),
                "run_status": manifest.get("status"),
            },
            reason="intelligence fusion artifacts were not found in this run.",
        )

    budget = _codex_material_budget(manifest, INTELLIGENCE_FUSION_MATERIAL_ARTIFACT)
    fields = {
        "run_id": manifest.get("run_id"),
        "run_status": manifest.get("status"),
        "fusion_records": _int(counts.get("intelligence_fusion_records")),
        "fusion_warnings": _int(counts.get("intelligence_fusion_warnings")),
        "fusion_errors": _int(counts.get("intelligence_fusion_errors")),
        "fusion_state_counts": _compact_counts(_dict(fusion_summary.get("state_counts"))),
        "fusion_conflict_counts": _compact_counts(_dict(fusion_summary.get("conflict_counts"))),
        "fusion_risk_override_counts": _compact_counts(_dict(fusion_summary.get("risk_override_counts"))),
        "fusion_event_override_counts": _compact_counts(_dict(fusion_summary.get("event_override_counts"))),
        "fusion_outcome_feedback_counts": _compact_counts(_dict(fusion_summary.get("outcome_feedback_counts"))),
        "decision_linked_records": _int(counts.get("intelligence_fusion_decision_linked_records")),
        "decision_adjusted_records": _int(counts.get("intelligence_fusion_decision_adjusted_records")),
        "alert_linked_records": _int(counts.get("intelligence_fusion_alert_linked_records")),
        "alert_adjusted_records": _int(counts.get("intelligence_fusion_alert_adjusted_records")),
        "material_records": _int(counts.get("intelligence_fusion_material_records")),
        "material_omitted_records": _int(counts.get("intelligence_fusion_material_omitted_records")),
        "fusion_quality_ok": quality_counts["ok"],
        "fusion_quality_warning": quality_counts["warning"],
        "fusion_quality_degraded": quality_counts["degraded"],
        "fusion_quality_skipped": quality_counts["skipped"],
        "fusion_quality_failed": quality_counts["failed"],
        "manifest": _safe_path(manifest_path, base=base),
    }
    if budget:
        fields.update(
            {
                "codex_budget_status": budget.get("status") or "unknown",
                "codex_budget_chars": _int(budget.get("chars")),
                "codex_budget_over_budget": bool(budget.get("over_budget")),
                "codex_budget_warnings": len(_list(budget.get("warnings"))),
            }
        )
    else:
        fields["codex_budget_status"] = "not_available"

    statuses = [
        str(summary.get("status"))
        for summary in (fusion_summary, material_summary)
        if isinstance(summary.get("status"), str) and summary.get("status")
    ]
    integration_status = integration_summary.get("status")
    if integration_status == "failed":
        statuses.append("failed")
    if integration_summary.get("errors"):
        statuses.append("failed")
    elif integration_summary.get("warnings"):
        statuses.append("warning")
    statuses.extend(status for status, value in quality_counts.items() for _ in range(value))
    if budget and (budget.get("over_budget") or budget.get("status") not in {None, "included"}):
        statuses.append("warning")
    status = _status_from_values(statuses)
    reason = quality_error if quality_error else None
    return _section(
        "intelligence_fusion",
        status,
        artifact=_safe_path(manifest_path, base=base),
        fields=fields,
        reason=reason,
    )


def _strategy_lifecycle_section(
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    if run_dir is not None:
        resolved_run_dir = _resolve_run_dir(run_dir, base=base)
    else:
        resolved_run_dir = _latest_run_from_index(config_path)
    if resolved_run_dir is None:
        return _section(
            "strategy_lifecycle",
            "skipped",
            reason="no latest run was found in the local run index.",
        )

    manifest_path = resolved_run_dir / "run_manifest.json"
    manifest, manifest_error = _read_json(manifest_path)
    if manifest_error:
        raise DataInspectionError(f"run_manifest.json could not be inspected: {manifest_error}")

    artifacts = _dict(manifest.get("artifacts"))
    counts = _dict(manifest.get("counts"))
    lifecycle_summary = _dict(manifest.get("strategy_lifecycle_state"))
    material_summary = _dict(manifest.get("strategy_lifecycle_material"))
    has_lifecycle = _has_strategy_lifecycle_artifacts(artifacts, counts, lifecycle_summary, material_summary)
    if not has_lifecycle:
        return _section(
            "strategy_lifecycle",
            "skipped",
            artifact=_safe_path(manifest_path, base=base),
            fields={
                "run_id": manifest.get("run_id"),
                "run_status": manifest.get("status"),
                "state_artifact_status": "missing",
                "material_artifact_status": "missing",
            },
            reason="strategy lifecycle artifacts were not found in this run.",
        )

    state_ref = _artifact_ref(artifacts, "strategy_lifecycle_state", STRATEGY_LIFECYCLE_STATE_ARTIFACT)
    material_ref = _artifact_ref(artifacts, "strategy_lifecycle_material", STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT)
    state_artifact, state_error = _read_json(resolved_run_dir / state_ref)
    state_artifact_status = _artifact_file_status(state_artifact, state_error)
    material_artifact_status, material_error = _plain_artifact_status(
        resolved_run_dir / material_ref,
        source_status=str(material_summary.get("status") or ""),
    )
    lifecycle_status_counts = _compact_counts(
        _dict(lifecycle_summary.get("lifecycle_status_counts"))
        or _dict(_dict(state_artifact.get("counts")).get("by_lifecycle_status"))
        or _manifest_lifecycle_status_counts(counts)
    )
    fields = {
        "run_id": manifest.get("run_id"),
        "run_status": manifest.get("status"),
        "state_artifact": state_ref,
        "state_artifact_status": state_artifact_status,
        "material_artifact": material_ref,
        "material_artifact_status": material_artifact_status,
        "lifecycle_status": lifecycle_summary.get("status") or state_artifact_status,
        "lifecycle_records": _int(counts.get("strategy_lifecycle_records")),
        "lifecycle_effective": _int(counts.get("strategy_lifecycle_effective")),
        "lifecycle_active_candidate": _int(counts.get("strategy_lifecycle_active_candidate")),
        "lifecycle_watchlisted": _int(counts.get("strategy_lifecycle_watchlisted")),
        "lifecycle_rejected": _int(counts.get("strategy_lifecycle_rejected")),
        "lifecycle_degraded": _int(counts.get("strategy_lifecycle_degraded")),
        "lifecycle_retired": _int(counts.get("strategy_lifecycle_retired")),
        "lifecycle_insufficient_evidence": _int(counts.get("strategy_lifecycle_insufficient_evidence")),
        "lifecycle_failed": _int(counts.get("strategy_lifecycle_failed")),
        "lifecycle_policy_records": _int(counts.get("strategy_lifecycle_policy_records")),
        "lifecycle_warnings": _int(counts.get("strategy_lifecycle_warnings")),
        "lifecycle_errors": _int(counts.get("strategy_lifecycle_errors")),
        "lifecycle_status_counts": lifecycle_status_counts,
        "material_status": material_summary.get("status") or material_artifact_status,
        "material_records": _int(counts.get("strategy_lifecycle_material_records")),
        "material_omitted_records": _int(counts.get("strategy_lifecycle_material_omitted_records")),
        "manifest": _safe_path(manifest_path, base=base),
    }
    budget = _codex_material_budget(manifest, STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT)
    if budget:
        fields.update(
            {
                "codex_budget_status": budget.get("status") or "unknown",
                "codex_budget_chars": _int(budget.get("chars")),
                "codex_budget_over_budget": bool(budget.get("over_budget")),
                "codex_budget_warnings": len(_list(budget.get("warnings"))),
            }
        )
    else:
        fields["codex_budget_status"] = "not_available"

    statuses = [
        str(value)
        for value in (
            lifecycle_summary.get("status"),
            material_summary.get("status"),
            state_artifact_status,
            material_artifact_status,
        )
        if isinstance(value, str) and value
    ]
    if budget and (budget.get("over_budget") or budget.get("status") not in {None, "included"}):
        statuses.append("warning")
    reason = "; ".join(error for error in (state_error, material_error) if error) or None
    return _section(
        "strategy_lifecycle",
        _lifecycle_inspection_status(statuses),
        artifact=_safe_path(manifest_path, base=base),
        fields=fields,
        reason=reason,
    )


def _personalized_risk_section(
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    if run_dir is not None:
        resolved_run_dir = _resolve_run_dir(run_dir, base=base)
    else:
        resolved_run_dir = _latest_run_from_index(config_path)
    if resolved_run_dir is None:
        return _section(
            "personalized_risk",
            "skipped",
            reason="no latest run was found in the local run index.",
        )

    manifest_path = resolved_run_dir / "run_manifest.json"
    manifest, manifest_error = _read_json(manifest_path)
    if manifest_error:
        raise DataInspectionError(f"run_manifest.json could not be inspected: {manifest_error}")

    artifacts = _dict(manifest.get("artifacts"))
    counts = _dict(manifest.get("counts"))
    user_state_summary = _dict(manifest.get("user_state_context"))
    constraint_summary = _dict(manifest.get("personalized_risk_constraints"))
    integration_summary = _dict(manifest.get("personalized_risk_integration"))
    material_summary = _dict(manifest.get("personalized_risk_material"))
    has_personalized_artifacts = any(
        artifacts.get(key)
        for key in ("user_state_context", "personalized_risk_constraints", "personalized_risk_material")
    ) or any((user_state_summary, constraint_summary, integration_summary, material_summary))

    quality, quality_error = _read_json(resolved_run_dir / DATA_QUALITY_SUMMARY_ARTIFACT)
    quality_counts = _m15_quality_check_counts(quality)
    if not has_personalized_artifacts and not any(quality_counts.values()):
        return _section(
            "personalized_risk",
            "skipped",
            artifact=_safe_path(manifest_path, base=base),
            fields={
                "run_id": manifest.get("run_id"),
                "run_status": manifest.get("status"),
            },
            reason="personalized risk artifacts were not found in this run.",
        )

    budget = _codex_material_budget(manifest, PERSONALIZED_RISK_MATERIAL_ARTIFACT)
    if not budget:
        budget = _dict(material_summary.get("codex_input_budget"))
    fields = {
        "run_id": manifest.get("run_id"),
        "run_status": manifest.get("status"),
        "user_state_status": user_state_summary.get("status") or "unknown",
        "user_state_mode": user_state_summary.get("mode") or "unknown",
        "user_state_watchlist_records": _int(counts.get("user_state_watchlist_records")),
        "user_state_disabled_assets": _int(counts.get("user_state_disabled_assets")),
        "user_state_preferred_timeframes": _int(counts.get("user_state_preferred_timeframes")),
        "user_state_strategy_preference_records": _int(
            counts.get("user_state_strategy_preference_records")
        ),
        "user_state_manual_exposure_summary_records": _int(
            counts.get("user_state_manual_exposure_summary_records")
        ),
        "user_state_omitted_private_values": _int(counts.get("user_state_omitted_private_values")),
        "constraint_status": constraint_summary.get("status") or "unknown",
        "constraint_records": _int(counts.get("personalized_risk_constraint_records")),
        "constraint_state_counts": _compact_counts(_dict(constraint_summary.get("state_counts"))),
        "constraint_action_counts": _compact_counts(_dict(constraint_summary.get("action_counts"))),
        "integration_status": integration_summary.get("status") or "unknown",
        "decision_linked_records": _int(counts.get("personalized_risk_decision_linked_records")),
        "decision_adjusted_records": _int(counts.get("personalized_risk_decision_adjusted_records")),
        "watch_linked_records": _int(counts.get("personalized_risk_watch_linked_records")),
        "watch_adjusted_records": _int(counts.get("personalized_risk_watch_adjusted_records")),
        "alert_linked_records": _int(counts.get("personalized_risk_alert_linked_records")),
        "alert_adjusted_records": _int(counts.get("personalized_risk_alert_adjusted_records")),
        "material_status": material_summary.get("status") or "unknown",
        "material_records": _int(counts.get("personalized_risk_material_records")),
        "material_omitted_records": _int(counts.get("personalized_risk_material_omitted_records")),
        "m15_quality_ok": quality_counts["ok"],
        "m15_quality_warning": quality_counts["warning"],
        "m15_quality_degraded": quality_counts["degraded"],
        "m15_quality_skipped": quality_counts["skipped"],
        "m15_quality_failed": quality_counts["failed"],
        "manifest": _safe_path(manifest_path, base=base),
    }
    if budget:
        fields.update(
            {
                "codex_budget_status": budget.get("status") or "unknown",
                "codex_budget_chars": _int(budget.get("chars")),
                "codex_budget_over_budget": bool(budget.get("over_budget")),
                "codex_budget_warnings": len(_list(budget.get("warnings"))),
            }
        )
    else:
        fields["codex_budget_status"] = "not_available"

    statuses = [
        str(summary.get("status"))
        for summary in (user_state_summary, constraint_summary, material_summary)
        if isinstance(summary.get("status"), str) and summary.get("status")
    ]
    if integration_summary.get("status") == "failed":
        statuses.append("failed")
    if integration_summary.get("errors"):
        statuses.append("failed")
    elif integration_summary.get("warnings"):
        statuses.append("warning")
    statuses.extend(status for status, value in quality_counts.items() for _ in range(value))
    if budget and (budget.get("over_budget") or budget.get("status") not in {None, "included"}):
        statuses.append("warning")
    status = _status_from_values(statuses)
    reason = quality_error if quality_error else None
    return _section(
        "personalized_risk",
        status,
        artifact=_safe_path(manifest_path, base=base),
        fields=fields,
        reason=reason,
    )


def _workbench_section(config_path: Path, *, base: Path) -> dict[str, Any]:
    _ = config_path
    output_dir = base / DEFAULT_WORKBENCH_OUTPUT_DIR
    summary_path = output_dir / WORKBENCH_SUMMARY_FILENAME
    markdown_path = output_dir / WORKBENCH_MARKDOWN_FILENAME
    html_path = output_dir / WORKBENCH_HTML_FILENAME
    summary, error = _read_json(summary_path)
    if error:
        return _section(
            "workbench",
            "skipped",
            artifact=_safe_path(summary_path, base=base),
            fields={
                "index_markdown": _safe_path(markdown_path, base=base),
                "index_html": _safe_path(html_path, base=base),
            },
            reason=error,
        )

    latest_run = _dict(summary.get("latest_run"))
    latest_fields = _dict(latest_run.get("fields"))
    index_outputs = _dict(summary.get("index_outputs"))
    fields = {
        "generated_at": summary.get("generated_at"),
        "latest_run_id": latest_fields.get("run_id"),
        "latest_run_status": latest_fields.get("run_status"),
        "decision_state": _inspection_section_status(summary, "decision_state"),
        "alert_state": _inspection_section_status(summary, "alert_state"),
        "monitor_state": _inspection_section_status(summary, "monitor_state"),
        "outcome_state": _inspection_section_status(summary, "outcome_state"),
        "strategy_state": _inspection_section_status(summary, "strategy_state"),
        "product_validation_state": _inspection_section_status(summary, "product_validation_state"),
        "data_quality_state": _inspection_section_status(summary, "data_quality_state"),
        "index_markdown": index_outputs.get("markdown") or _safe_path(markdown_path, base=base),
        "index_html": index_outputs.get("html") or _safe_path(html_path, base=base),
        "warnings": len(_list(summary.get("warnings"))),
        "errors": len(_list(summary.get("errors"))),
    }
    return _section(
        "workbench",
        str(summary.get("status") or "unknown"),
        artifact=_safe_path(summary_path, base=base),
        fields=fields,
    )


def _product_validation_section(
    config_path: Path,
    *,
    run_dir: Path | None,
    base: Path,
) -> dict[str, Any]:
    if run_dir is not None:
        resolved_run_dir = _resolve_run_dir(run_dir, base=base)
    else:
        resolved_run_dir = _latest_run_from_index(config_path)
    if resolved_run_dir is None:
        return _section(
            "product_validation",
            "skipped",
            reason="no latest run was found in the local run index.",
        )

    manifest_path = resolved_run_dir / "run_manifest.json"
    manifest, manifest_error = _read_json(manifest_path)
    if manifest_error:
        raise DataInspectionError(f"run_manifest.json could not be inspected: {manifest_error}")

    artifacts = _dict(manifest.get("artifacts"))
    ref = _artifact_ref(artifacts, "product_contract_validation", PRODUCT_CONTRACT_VALIDATION_ARTIFACT)
    validation, validation_error = _read_json(resolved_run_dir / ref)
    if validation_error:
        return _section(
            "product_validation",
            "skipped",
            artifact=_safe_path(resolved_run_dir / ref, base=base),
            fields={
                "run_id": manifest.get("run_id"),
                "run_status": manifest.get("status"),
                "validation_status": "missing",
                "manifest": _safe_path(manifest_path, base=base),
            },
            reason=validation_error,
        )

    counts = _dict(validation.get("counts"))
    source_refs = _bounded_source_refs(validation.get("source_artifacts"))
    fields = {
        "run_id": manifest.get("run_id"),
        "run_status": manifest.get("status"),
        "validation_status": validation.get("status") or "unknown",
        "checks": _int(counts.get("checks")),
        "ok": _int(counts.get("ok")),
        "warning": _int(counts.get("warning")),
        "degraded": _int(counts.get("degraded")),
        "failed": _int(counts.get("failed")),
        "skipped": _int(counts.get("skipped")),
        "warnings": _int(counts.get("warnings")),
        "errors": _int(counts.get("errors")),
        "source_refs": source_refs["text"],
        "source_refs_omitted": source_refs["omitted"],
        "manifest": _safe_path(manifest_path, base=base),
    }
    return _section(
        "product_validation",
        _artifact_file_status(validation, validation_error),
        artifact=_safe_path(resolved_run_dir / ref, base=base),
        fields=fields,
    )


def _latest_run_from_index(config_path: Path) -> Path | None:
    path = run_index_path(config_path)
    if not path.exists():
        return None
    try:
        with closing(sqlite3.connect(path)) as connection:
            run_id = _latest_run_id(connection)
            if not run_id:
                return None
            row = connection.execute("SELECT run_dir FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    except sqlite3.Error as exc:
        raise DataInspectionError(f"{RUN_INDEX_ARTIFACT} is not readable: {exc}") from exc
    if row is None or not isinstance(row[0], str) or not row[0]:
        return None
    run_dir = Path(row[0])
    if not run_dir.is_absolute():
        run_dir = config_path.parent / run_dir
    return run_dir


def _resolve_run_dir(run_dir: Path, *, base: Path) -> Path:
    path = run_dir
    if not path.is_absolute():
        path = base / path
    if not path.exists():
        raise DataInspectionError("requested run directory was not found.")
    if not path.is_dir():
        raise DataInspectionError("requested run directory is not a directory.")
    return path


def _section(
    name: str,
    status: str,
    *,
    artifact: str | None = None,
    reason: str | None = None,
    fields: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "artifact": artifact,
        "reason": reason,
        "fields": fields or {},
        "extra": extra or {},
    }


def _section_lines(section: dict[str, Any]) -> list[str]:
    fields = section["fields"]
    parts = [f"  {section['name']}: {section['status']}"]
    if fields:
        parts.append(_field_text(fields))
    if section.get("artifact"):
        parts.append(f"artifact={section['artifact']}")
    if section.get("reason"):
        parts.append(f"reason={section['reason']}")
    lines = [" ".join(parts)]
    store_statuses = section.get("extra", {}).get("store_statuses")
    if store_statuses:
        lines.append(f"    store_statuses: {store_statuses}")
    return lines


def _field_text(fields: dict[str, Any]) -> str:
    values = []
    for key in sorted(fields):
        value = fields[key]
        if value is None:
            continue
        values.append(f"{key}={value}")
    return " ".join(values)


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _latest_run_id(connection: sqlite3.Connection) -> str | None:
    for key in ("latest_successful_run", "latest_run"):
        row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
        if row and isinstance(row[0], str) and row[0]:
            return row[0]
    return None


def _store_statuses(catalog: dict[str, Any]) -> str | None:
    stores = _list(catalog.get("stores"))
    statuses = []
    for store in stores:
        if not isinstance(store, dict):
            continue
        name = store.get("name")
        status = store.get("status")
        if isinstance(name, str) and name and isinstance(status, str) and status:
            statuses.append(f"{name}={status}")
    return ", ".join(sorted(statuses)) if statuses else None


def _m13_quality_check_counts(quality: dict[str, Any]) -> dict[str, int]:
    return _named_quality_check_counts(quality, M13_CHECK_NAMES)


def _fusion_quality_check_counts(quality: dict[str, Any]) -> dict[str, int]:
    return _named_quality_check_counts(quality, FUSION_CHECK_NAMES)


def _m15_quality_check_counts(quality: dict[str, Any]) -> dict[str, int]:
    return _named_quality_check_counts(quality, M15_CHECK_NAMES)


def _named_quality_check_counts(quality: dict[str, Any], names: set[str]) -> dict[str, int]:
    counts = {"ok": 0, "warning": 0, "degraded": 0, "skipped": 0, "failed": 0}
    for check in _list(quality.get("checks")):
        if not isinstance(check, dict) or check.get("name") not in names:
            continue
        status = str(check.get("status") or "unknown")
        if status in counts:
            counts[status] += 1
    return counts


def _codex_material_budget(manifest: dict[str, Any], artifact: str) -> dict[str, Any]:
    codex_input = _dict(manifest.get("codex_input"))
    materials = codex_input.get("materials")
    if isinstance(materials, dict):
        budget = materials.get(artifact)
        return budget if isinstance(budget, dict) else {}
    if isinstance(materials, list):
        for item in materials:
            record = _dict(item)
            if record.get("artifact") == artifact:
                return record
    return {}


def _has_strategy_lifecycle_artifacts(
    artifacts: dict[str, Any],
    counts: dict[str, Any],
    lifecycle_summary: dict[str, Any],
    material_summary: dict[str, Any],
) -> bool:
    if artifacts.get("strategy_lifecycle_state") or artifacts.get("strategy_lifecycle_material"):
        return True
    if lifecycle_summary or material_summary:
        return True
    return any(str(key).startswith("strategy_lifecycle_") for key in counts)


def _artifact_ref(artifacts: dict[str, Any], key: str, default: str) -> str:
    value = artifacts.get(key)
    return value if isinstance(value, str) and value else default


def _artifact_file_status(data: dict[str, Any], error: str | None) -> str:
    if error:
        return "missing" if "was not found" in error else "failed"
    status = str(data.get("status") or "").lower()
    if status in {"failed", "degraded", "warning", "partial", "skipped", "not_generated"}:
        return status
    return "ok"


def _plain_artifact_status(path: Path, *, source_status: str) -> tuple[str, str | None]:
    if not path.is_file():
        return "missing", f"{path.name} was not found."
    status = source_status.lower()
    if status in {"failed", "degraded", "warning", "partial", "skipped", "not_generated"}:
        return status, None
    return "ok", None


def _manifest_lifecycle_status_counts(counts: dict[str, Any]) -> dict[str, int]:
    return {
        "active_candidate": _int(counts.get("strategy_lifecycle_active_candidate")),
        "degraded": _int(counts.get("strategy_lifecycle_degraded")),
        "effective": _int(counts.get("strategy_lifecycle_effective")),
        "failed": _int(counts.get("strategy_lifecycle_failed")),
        "insufficient_evidence": _int(counts.get("strategy_lifecycle_insufficient_evidence")),
        "rejected": _int(counts.get("strategy_lifecycle_rejected")),
        "retired": _int(counts.get("strategy_lifecycle_retired")),
        "watchlisted": _int(counts.get("strategy_lifecycle_watchlisted")),
    }


def _lifecycle_inspection_status(statuses: list[str]) -> str:
    cleaned = [status for status in statuses if status and status not in {"not_generated"}]
    if not cleaned or set(cleaned) <= {"skipped", "missing"}:
        return "skipped"
    if "failed" in cleaned:
        return "failed"
    if "degraded" in cleaned:
        return "degraded"
    if any(status in cleaned for status in ("warning", "partial", "missing", "skipped")):
        return "warning"
    return "ok"


def _compact_counts(counts: dict[str, Any]) -> str | None:
    values = [
        f"{key}:{_int(value)}"
        for key, value in sorted(counts.items())
        if isinstance(key, str) and _int(value) > 0
    ]
    return ",".join(values) if values else None


def _bounded_source_refs(value: Any, *, limit: int = 8) -> dict[str, Any]:
    refs = [str(item) for item in _list(value) if isinstance(item, str) and item]
    listed = refs[:limit]
    return {
        "text": ",".join(listed) if listed else None,
        "omitted": max(0, len(refs) - len(listed)),
    }


def _status_from_values(statuses: list[str]) -> str:
    if not statuses or set(statuses) == {"skipped"}:
        return "skipped"
    return _overall_status(statuses)


def _overall_status(statuses: list[str]) -> str:
    if "failed" in statuses:
        return "failed"
    if "degraded" in statuses:
        return "degraded"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _safe_path(path: Path, *, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _status_count(records: list[Any], status: str) -> int:
    return sum(1 for item in records if isinstance(item, dict) and item.get("status") == status)


def _inspection_section_status(summary: dict[str, Any], key: str) -> str:
    return str(_dict(summary.get(key)).get("status") or "unknown")
