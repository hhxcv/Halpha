from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from json import JSONDecodeError
from pathlib import Path
import sqlite3
from typing import Any

from .monitoring import (
    ALERT_ARCHIVE_STATE_FILENAME,
    MONITOR_HEALTH_STATE_FILENAME,
    load_monitor_config,
)
from .run_index import RUN_INDEX_ARTIFACT, run_index_path
from .storage import display_path, ensure_directory, write_json


DEFAULT_WORKBENCH_OUTPUT_DIR = "runs/workbench/latest"
WORKBENCH_SUMMARY_FILENAME = "workbench_summary.json"
WORKBENCH_SUMMARY_ARTIFACT = f"{DEFAULT_WORKBENCH_OUTPUT_DIR}/{WORKBENCH_SUMMARY_FILENAME}"


@dataclass(frozen=True)
class WorkbenchSummaryResult:
    summary_path: Path
    summary: dict[str, Any]


@dataclass(frozen=True)
class _RunSelection:
    mode: str
    status: str
    run_dir: Path | None
    run_id: str | None
    source_artifact: str | None
    reason: str | None


def build_workbench_summary(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_dir: Path | None = None,
    now: datetime | None = None,
) -> WorkbenchSummaryResult:
    base = _config_base(config_path)
    output_dir = _workbench_output_dir(config, config_path=config_path)
    ensure_directory(output_dir)
    generated_at = _utc_timestamp(now)
    selection = _select_run(config_path, run_dir=run_dir, base=base)

    warnings: list[str] = []
    errors: list[str] = []
    if selection.reason:
        warnings.append(selection.reason)

    manifest: dict[str, Any] = {}
    manifest_error: str | None = None
    if selection.run_dir is not None:
        manifest, manifest_error = _read_json(selection.run_dir / "run_manifest.json")
        if manifest_error:
            errors.append(f"run_manifest.json could not be inspected: {manifest_error}")

    latest_run = _latest_run_state(selection, manifest, manifest_error, base=base)
    decision_state = _decision_state(selection, manifest)
    alert_state = _alert_state(config, selection, manifest, base=base)
    monitor_state = _monitor_state(config, config_path=config_path, base=base)
    outcome_state = _outcome_state(config_path, selection, manifest, base=base)
    strategy_state = _strategy_state(selection, manifest)
    data_quality_state = _data_quality_state(selection, manifest)
    sections = [
        latest_run,
        decision_state,
        alert_state,
        monitor_state,
        outcome_state,
        strategy_state,
        data_quality_state,
    ]

    for section in sections:
        warnings.extend(str(item) for item in _list(section.get("warnings")))
        errors.extend(str(item) for item in _list(section.get("errors")))

    summary_path = output_dir / WORKBENCH_SUMMARY_FILENAME
    summary = {
        "schema_version": 1,
        "artifact_type": "workbench_summary",
        "generated_at": generated_at,
        "status": _overall_status([str(section.get("status") or "missing") for section in sections]),
        "source_selection": {
            "mode": selection.mode,
            "status": selection.status,
            "run_id": selection.run_id,
            "run_dir": _portable_path(selection.run_dir, base=base) if selection.run_dir else None,
            "source_artifact": selection.source_artifact,
            "reason": selection.reason,
        },
        "latest_run": latest_run,
        "decision_state": decision_state,
        "alert_state": alert_state,
        "monitor_state": monitor_state,
        "outcome_state": outcome_state,
        "strategy_state": strategy_state,
        "data_quality_state": data_quality_state,
        "index_outputs": {
            "status": "not_generated",
            "markdown": None,
            "html": None,
        },
        "source_artifacts": _source_artifacts(selection, manifest, base=base),
        "omitted": {
            "raw_record_dumps_embedded": False,
            "full_intermediate_json_embedded": False,
            "full_run_manifest_embedded": False,
            "raw_local_user_state_embedded": False,
        },
        "codex_boundary": {
            "codex_input_by_default": False,
            "llm_generated_workbench_state": False,
        },
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
    }
    write_json(summary_path, summary)
    return WorkbenchSummaryResult(summary_path=summary_path, summary=summary)


def _select_run(config_path: Path, *, run_dir: Path | None, base: Path) -> _RunSelection:
    if run_dir is not None:
        resolved = _resolve_path(run_dir, base=base)
        if not resolved.exists():
            return _RunSelection(
                mode="explicit_run",
                status="missing",
                run_dir=None,
                run_id=None,
                source_artifact=None,
                reason="requested run directory was not found.",
            )
        if not resolved.is_dir():
            return _RunSelection(
                mode="explicit_run",
                status="failed",
                run_dir=None,
                run_id=None,
                source_artifact=None,
                reason="requested run path is not a directory.",
            )
        return _RunSelection(
            mode="explicit_run",
            status="available",
            run_dir=resolved,
            run_id=resolved.name,
            source_artifact=None,
            reason=None,
        )

    index_path = run_index_path(config_path)
    if not index_path.exists():
        return _RunSelection(
            mode="latest_run_index",
            status="missing",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason="local run index was not found.",
        )
    try:
        with sqlite3.connect(index_path) as connection:
            row = _latest_run_row(connection)
    except sqlite3.Error as exc:
        return _RunSelection(
            mode="latest_run_index",
            status="failed",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason=f"{RUN_INDEX_ARTIFACT} is not readable: {exc}",
        )
    if row is None:
        return _RunSelection(
            mode="latest_run_index",
            status="missing",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason="local run index does not contain a latest run.",
        )
    selected_run_id, selected_run_dir = row
    path = Path(selected_run_dir)
    if not path.is_absolute():
        path = base / path
    return _RunSelection(
        mode="latest_run_index",
        status="available",
        run_dir=path,
        run_id=selected_run_id,
        source_artifact=RUN_INDEX_ARTIFACT,
        reason=None,
    )


def _latest_run_row(connection: sqlite3.Connection) -> tuple[str, str] | None:
    for key in ("latest_successful_run", "latest_run"):
        row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
        if not row or not isinstance(row[0], str) or not row[0]:
            continue
        run = connection.execute("SELECT run_id, run_dir FROM runs WHERE run_id = ?", (row[0],)).fetchone()
        if run and isinstance(run[0], str) and isinstance(run[1], str):
            return run[0], run[1]
    return None


def _latest_run_state(
    selection: _RunSelection,
    manifest: dict[str, Any],
    manifest_error: str | None,
    *,
    base: Path,
) -> dict[str, Any]:
    if selection.run_dir is None:
        return _section("missing", reason=selection.reason)
    manifest_ref = _portable_path(selection.run_dir / "run_manifest.json", base=base)
    if manifest_error:
        return _section("failed", artifact=manifest_ref, errors=[manifest_error])
    report_ref = _report_artifact_ref(manifest)
    report_status = _file_ref_status(selection.run_dir, report_ref, default_ref="report/report.md")
    return _section(
        "available",
        artifact=manifest_ref,
        fields={
            "run_id": manifest.get("run_id") or selection.run_id,
            "run_status": manifest.get("status") or "unknown",
            "started_at": manifest.get("started_at"),
            "finished_at": manifest.get("finished_at"),
            "codex_status": _dict(manifest.get("codex")).get("status"),
            "report": report_status,
        },
    )


def _decision_state(selection: _RunSelection, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _manifest_artifact_refs(
        manifest,
        {
            "risk_assessment": "analysis/risk_assessment.json",
            "decision_recommendations": "analysis/decision_recommendations.json",
            "watch_triggers": "analysis/watch_triggers.json",
        },
    )
    if selection.run_dir is None:
        return _section("missing", source_artifacts=refs, reason="no selected run.")
    artifacts = _artifact_statuses(selection.run_dir, refs)
    counts = _dict(manifest.get("counts"))
    return _section(
        _section_status(artifacts),
        source_artifacts=refs,
        fields={
            "risk_records": _int(counts.get("risk_assessment_records")),
            "high_or_extreme_risk_records": _int(counts.get("risk_assessment_high_or_extreme_records")),
            "blocking_risk_records": _int(counts.get("risk_assessment_blocking_records")),
            "decision_records": _int(counts.get("decision_recommendation_records")),
            "actionable_decision_records": _int(counts.get("decision_recommendation_actionable_records")),
            "risk_blocked_decision_records": _int(counts.get("decision_recommendation_risk_blocked_records")),
            "watch_trigger_records": _int(counts.get("watch_trigger_records")),
        },
        details={"artifacts": artifacts},
        warnings=_artifact_warnings(artifacts),
        errors=_artifact_errors(artifacts),
    )


def _alert_state(config: dict[str, Any], selection: _RunSelection, manifest: dict[str, Any], *, base: Path) -> dict[str, Any]:
    refs = _manifest_artifact_refs(manifest, {"alert_decisions": "analysis/alert_decisions.json"})
    artifacts = _artifact_statuses(selection.run_dir, refs) if selection.run_dir is not None else []
    settings = load_monitor_config(config)
    monitor_dir = _resolve_path(settings.output_dir, base=base)
    archive_state_ref = _portable_path(monitor_dir / ALERT_ARCHIVE_STATE_FILENAME, base=base)
    archive_state, archive_error = _read_json(monitor_dir / ALERT_ARCHIVE_STATE_FILENAME)
    archive_status = _json_status(archive_state, archive_error)
    counts = _dict(manifest.get("counts"))
    fields = {
        "alert_decision_records": _int(counts.get("alert_decision_records")),
        "alert_decision_attention_records": _int(counts.get("alert_decision_attention_records")),
        "archive_state": {
            "status": archive_status,
            "artifact": archive_state_ref,
            "counts": _dict(archive_state.get("counts")),
        },
    }
    status_inputs = [item["status"] for item in artifacts] + [archive_status]
    return _section(
        _overall_status(status_inputs),
        source_artifacts={**refs, "alert_archive_state": archive_state_ref},
        fields=fields,
        details={"artifacts": artifacts},
        warnings=[*_artifact_warnings(artifacts), *([archive_error] if archive_error and archive_status == "missing" else [])],
        errors=[*_artifact_errors(artifacts), *([archive_error] if archive_error and archive_status == "failed" else [])],
    )


def _monitor_state(config: dict[str, Any], *, config_path: Path, base: Path) -> dict[str, Any]:
    settings = load_monitor_config(config)
    monitor_dir = _resolve_path(settings.output_dir, base=base)
    health_ref = _portable_path(monitor_dir / MONITOR_HEALTH_STATE_FILENAME, base=base)
    health, error = _read_json(monitor_dir / MONITOR_HEALTH_STATE_FILENAME)
    status = _json_status(health, error)
    fields = {
        "monitor_output_dir": _portable_path(monitor_dir, base=base),
        "health_state": health_ref,
        "cycle_count": _int(health.get("cycle_count")),
        "failed_cycle_count": _int(health.get("failed_cycle_count")),
        "latest_cycle_id": health.get("latest_cycle_id"),
        "latest_cycle_status": health.get("latest_cycle_status"),
        "latest_run_id": health.get("latest_run_id"),
        "latest_run_manifest": health.get("latest_run_manifest"),
        "alert_archive_status": health.get("alert_archive_status"),
        "alert_counts": _dict(health.get("alert_counts")),
        "cooldown_records": _int(health.get("cooldown_records")),
        "warning_count": _int(health.get("warning_count")),
        "error_count": _int(health.get("error_count")),
    }
    return _section(
        status,
        artifact=health_ref,
        fields=fields,
        warnings=[error] if error and status == "missing" else [],
        errors=[error] if error and status == "failed" else [],
    )


def _outcome_state(
    config_path: Path,
    selection: _RunSelection,
    manifest: dict[str, Any],
    *,
    base: Path,
) -> dict[str, Any]:
    refs = _manifest_artifact_refs(
        manifest,
        {
            "outcome_targets": "analysis/outcome_targets.json",
            "outcome_evaluations": "analysis/outcome_evaluations.json",
        },
    )
    history_state_ref = "data/research/metadata/outcome_history_state.json"
    history_state, history_error = _read_json(base / history_state_ref)
    history_status = _json_status(history_state, history_error)
    artifacts = _artifact_statuses(selection.run_dir, refs) if selection.run_dir is not None else []
    counts = _dict(manifest.get("counts"))
    status_inputs = [item["status"] for item in artifacts] + [history_status]
    return _section(
        _overall_status(status_inputs),
        source_artifacts={**refs, "outcome_history_state": history_state_ref},
        fields={
            "target_records": _int(counts.get("outcome_targets")),
            "evaluation_records": _int(counts.get("outcome_evaluations")),
            "evaluated_records": _int(counts.get("outcome_evaluations_evaluated")),
            "pending_records": _int(counts.get("outcome_evaluations_pending")),
            "insufficient_data_records": _int(counts.get("outcome_evaluations_insufficient_data")),
            "history_records": _int(_dict(history_state.get("totals")).get("records")),
        },
        details={"artifacts": artifacts},
        warnings=[*_artifact_warnings(artifacts), *([history_error] if history_error and history_status == "missing" else [])],
        errors=[*_artifact_errors(artifacts), *([history_error] if history_error and history_status == "failed" else [])],
    )


def _strategy_state(selection: _RunSelection, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _manifest_artifact_refs(
        manifest,
        {
            "strategy_evaluation_summary": "analysis/strategy_evaluation_summary.json",
            "strategy_experiment": "analysis/strategy_experiment.json",
            "strategy_effectiveness_gates": "analysis/strategy_effectiveness_gates.json",
        },
    )
    if selection.run_dir is None:
        return _section("missing", source_artifacts=refs, reason="no selected run.")
    artifacts = _artifact_statuses(selection.run_dir, refs)
    counts = _dict(manifest.get("counts"))
    return _section(
        _section_status(artifacts),
        source_artifacts=refs,
        fields={
            "strategy_evaluation_records": _int(counts.get("strategy_evaluation_records")),
            "strategy_evaluation_succeeded": _int(counts.get("strategy_evaluation_succeeded")),
            "strategy_gate_candidates": _int(counts.get("strategy_gate_candidates")),
            "strategy_gate_effective": _int(counts.get("strategy_gate_effective")),
            "strategy_gate_watchlisted": _int(counts.get("strategy_gate_watchlisted")),
            "strategy_gate_rejected": _int(counts.get("strategy_gate_rejected")),
            "strategy_gate_insufficient_evidence": _int(counts.get("strategy_gate_insufficient_evidence")),
        },
        details={"artifacts": artifacts},
        warnings=_artifact_warnings(artifacts),
        errors=_artifact_errors(artifacts),
    )


def _data_quality_state(selection: _RunSelection, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _manifest_artifact_refs(manifest, {"data_quality_summary": "analysis/data_quality_summary.json"})
    if selection.run_dir is None:
        return _section("missing", source_artifacts=refs, reason="no selected run.")
    artifacts = _artifact_statuses(selection.run_dir, refs)
    counts = _dict(manifest.get("counts"))
    return _section(
        _section_status(artifacts),
        source_artifacts=refs,
        fields={
            "checks": _int(counts.get("data_quality_checks")),
            "warnings": _int(counts.get("data_quality_warnings")),
            "errors": _int(counts.get("data_quality_errors")),
            "degraded_checks": _int(counts.get("data_quality_degraded_checks")),
            "failed_checks": _int(counts.get("data_quality_failed_checks")),
        },
        details={"artifacts": artifacts},
        warnings=_artifact_warnings(artifacts),
        errors=_artifact_errors(artifacts),
    )


def _manifest_artifact_refs(manifest: dict[str, Any], defaults: dict[str, str]) -> dict[str, str]:
    manifest_refs = _dict(manifest.get("artifacts"))
    refs: dict[str, str] = {}
    for key, default in defaults.items():
        value = manifest_refs.get(key)
        refs[key] = value if isinstance(value, str) and value else default
    return refs


def _artifact_statuses(run_dir: Path | None, refs: dict[str, str]) -> list[dict[str, Any]]:
    if run_dir is None:
        return [
            {
                "name": key,
                "artifact": ref,
                "status": "missing",
                "reason": "no selected run.",
            }
            for key, ref in refs.items()
        ]
    statuses = []
    for key, ref in sorted(refs.items()):
        artifact, error = _read_json(run_dir / ref)
        status = _json_status(artifact, error)
        item: dict[str, Any] = {
            "name": key,
            "artifact": ref,
            "status": status,
        }
        if artifact:
            item["artifact_type"] = artifact.get("artifact_type")
            item["source_status"] = artifact.get("status")
            item["counts"] = _dict(artifact.get("counts"))
            item["warning_count"] = len(_list(artifact.get("warnings")))
            item["error_count"] = len(_list(artifact.get("errors")))
        if error:
            item["reason"] = error
        statuses.append(item)
    return statuses


def _artifact_warnings(artifacts: list[dict[str, Any]]) -> list[str]:
    return [
        f"{item['artifact']} {item['reason']}"
        for item in artifacts
        if item.get("status") in {"missing", "partial", "stale", "degraded", "skipped"}
        and isinstance(item.get("artifact"), str)
        and isinstance(item.get("reason"), str)
    ]


def _artifact_errors(artifacts: list[dict[str, Any]]) -> list[str]:
    return [
        f"{item['artifact']} {item['reason']}"
        for item in artifacts
        if item.get("status") == "failed"
        and isinstance(item.get("artifact"), str)
        and isinstance(item.get("reason"), str)
    ]


def _source_artifacts(selection: _RunSelection, manifest: dict[str, Any], *, base: Path) -> dict[str, Any]:
    if selection.run_dir is None:
        return {}
    refs = {
        key: value
        for key, value in sorted(_dict(manifest.get("artifacts")).items())
        if isinstance(value, str) and value
    }
    return {
        "run_manifest": _portable_path(selection.run_dir / "run_manifest.json", base=base),
        "report": refs.get("report"),
        "analysis": {key: value for key, value in refs.items() if value.startswith("analysis/")},
        "raw": {key: value for key, value in refs.items() if value.startswith("raw/")},
        "shared_data": {key: value for key, value in refs.items() if value.startswith("data/")},
        "other": {
            key: value
            for key, value in refs.items()
            if not value.startswith(("analysis/", "raw/", "data/")) and key != "report"
        },
    }


def _report_artifact_ref(manifest: dict[str, Any]) -> str | None:
    artifacts = _dict(manifest.get("artifacts"))
    value = artifacts.get("report")
    return value if isinstance(value, str) and value else None


def _file_ref_status(run_dir: Path, ref: str | None, *, default_ref: str) -> dict[str, Any]:
    artifact_ref = ref or default_ref
    exists = (run_dir / artifact_ref).is_file()
    return {
        "status": "available" if exists else "missing",
        "artifact": artifact_ref,
    }


def _section(
    status: str,
    *,
    artifact: str | None = None,
    source_artifacts: dict[str, str] | None = None,
    reason: str | None = None,
    fields: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "artifact": artifact,
        "source_artifacts": source_artifacts or {},
        "reason": reason,
        "fields": fields or {},
        "details": details or {},
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _section_status(artifacts: list[dict[str, Any]]) -> str:
    if not artifacts:
        return "missing"
    return _overall_status([str(item.get("status") or "missing") for item in artifacts])


def _overall_status(statuses: list[str]) -> str:
    cleaned = [status for status in statuses if status]
    if not cleaned:
        return "missing"
    if "failed" in cleaned:
        return "failed"
    if "degraded" in cleaned:
        return "degraded"
    if "partial" in cleaned:
        return "partial"
    if "missing" in cleaned:
        return "missing" if set(cleaned) == {"missing"} else "partial"
    if "stale" in cleaned:
        return "stale"
    if "skipped" in cleaned:
        return "skipped" if set(cleaned) == {"skipped"} else "partial"
    if "not_applicable" in cleaned:
        return "not_applicable" if set(cleaned) == {"not_applicable"} else "partial"
    return "available"


def _json_status(data: dict[str, Any], error: str | None) -> str:
    if error:
        if "was not found" in error:
            return "missing"
        return "failed"
    source_status = str(data.get("status") or "").lower()
    if source_status in {"failed", "degraded", "partial", "stale", "skipped", "not_applicable"}:
        return source_status
    if source_status in {"warning", "unknown"}:
        return "partial"
    return "available"


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


def _workbench_output_dir(config: dict[str, Any], *, config_path: Path) -> Path:
    section = config.get("workbench")
    output_dir = DEFAULT_WORKBENCH_OUTPUT_DIR
    if isinstance(section, dict) and isinstance(section.get("output_dir"), str) and section["output_dir"]:
        output_dir = section["output_dir"]
    path = Path(output_dir)
    if path.is_absolute():
        return path
    return _config_base(config_path) / path


def _resolve_path(path: Path, *, base: Path) -> Path:
    return path if path.is_absolute() else base / path


def _portable_path(path: Path, *, base: Path) -> str:
    return display_path(path, base=base)


def _config_base(config_path: Path) -> Path:
    parent = config_path.parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _dedupe(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})
