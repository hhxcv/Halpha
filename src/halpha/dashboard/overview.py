from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.dashboard.common import dashboard_bounded_mapping as _bounded_mapping
from halpha.dashboard.common import dashboard_manifest_artifact_ref as _artifact_ref
from halpha.dashboard.common import dashboard_normalize_section_status as _normalize_section_status
from halpha.dashboard.common import dashboard_read_json as _read_json
from halpha.dashboard.common import dashboard_safe_ref as _safe_ref
from halpha.dashboard.common import dashboard_section as _section
from halpha.dashboard.common import dashboard_strict_overall_status as _overall_status
from halpha.dashboard.runs import dashboard_latest_run_section
from halpha.dashboard.settings import dashboard_config_ref
from halpha.data.run_index import RUN_INDEX_ARTIFACT
from halpha.monitor.monitoring import MONITOR_HEALTH_STATE_FILENAME, load_monitor_config
from halpha.storage import config_base as _config_base
from halpha.utils.value_helpers import (
    as_dict as _dict,
    as_list as _list,
    stringified_list as _string_list,
)
from halpha.workbench.workbench import DEFAULT_WORKBENCH_OUTPUT_DIR, WORKBENCH_SUMMARY_FILENAME


DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
PRODUCT_CONTRACT_VALIDATION_ARTIFACT = "analysis/product_contract_validation.json"
ARTIFACT_PRODUCER_STAGES = {
    "data_quality_summary": "build_data_quality_summary",
    "product_contract_validation": "validate_product_contracts",
}
NON_PRODUCED_STAGE_STATUSES = {"disabled", "not_run", "skipped"}
WORKBENCH_SUMMARY_ARTIFACT = f"{DEFAULT_WORKBENCH_OUTPUT_DIR}/{WORKBENCH_SUMMARY_FILENAME}"


def dashboard_overview(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _config_base(config_path)
    latest_run, run_dir, manifest = dashboard_latest_run_section(config_path, base=base)
    monitor = _monitor_section(config, config_path=config_path, base=base)
    sections = {
        "latest_run": latest_run,
        "product_validation": _run_json_artifact_section(
            "product_validation",
            run_dir=run_dir,
            manifest=manifest,
            artifact_key="product_contract_validation",
            default_artifact=PRODUCT_CONTRACT_VALIDATION_ARTIFACT,
        ),
        "data_quality": _run_json_artifact_section(
            "data_quality",
            run_dir=run_dir,
            manifest=manifest,
            artifact_key="data_quality_summary",
            default_artifact=DATA_QUALITY_SUMMARY_ARTIFACT,
        ),
        "monitor": monitor,
        "workbench": _workbench_section(base=base, latest_run=latest_run, monitor=monitor),
    }
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_overview",
        "status": _overall_status([section["status"] for section in sections.values()]),
        "config": {
            "loaded": True,
            "ref": dashboard_config_ref(config_path),
        },
        "sections": sections,
        "omitted": {
            "full_run_manifest_embedded": False,
            "full_raw_artifacts_embedded": False,
            "full_reusable_histories_embedded": False,
            "full_codex_prompt_embedded": False,
            "raw_local_user_state_embedded": False,
        },
    }


def _run_json_artifact_section(
    name: str,
    *,
    run_dir: Path | None,
    manifest: dict[str, Any],
    artifact_key: str,
    default_artifact: str,
) -> dict[str, Any]:
    if run_dir is None:
        return _section(name, "skipped", warnings=["latest run is not available."])
    artifact = _artifact_ref(manifest, artifact_key, default_artifact)
    boundary = _artifact_stage_boundary(manifest, artifact_key)
    if artifact is None:
        if boundary:
            return _stage_boundary_section(
                name,
                artifact_key=artifact_key,
                artifact=default_artifact,
                boundary=boundary,
            )
        return _section(name, "missing", warnings=[f"{artifact_key} artifact is not recorded."])
    path = run_dir / artifact
    data, error = _read_json(path)
    if error:
        if boundary and "was not found" in error:
            return _stage_boundary_section(name, artifact_key=artifact_key, artifact=artifact, boundary=boundary)
        return _section(name, "missing" if "was not found" in error else "failed", source_artifacts=[artifact], errors=[error])
    artifact_status = str(data.get("status") or "unknown")
    fields = {
        "artifact": artifact,
        "artifact_type": data.get("artifact_type"),
        "artifact_status": artifact_status,
        "counts": _bounded_mapping(data.get("counts")),
        "warning_count": _warning_count(data),
        "error_count": _error_count(data),
    }
    checks = data.get("checks")
    if isinstance(checks, list):
        fields["check_counts"] = _check_counts(checks)
    return _section(
        name,
        _normalize_section_status(artifact_status),
        fields=fields,
        source_artifacts=[artifact],
        warnings=_string_list(data.get("warnings")),
        errors=_string_list(data.get("errors")),
    )


def _artifact_stage_boundary(manifest: dict[str, Any], artifact_key: str) -> dict[str, str] | None:
    stage_name = ARTIFACT_PRODUCER_STAGES.get(artifact_key)
    if not stage_name:
        return None
    for stage in _list(manifest.get("stages")):
        if not isinstance(stage, dict) or stage.get("name") != stage_name:
            continue
        status = str(stage.get("status") or "unknown")
        if status not in NON_PRODUCED_STAGE_STATUSES:
            return None
        boundary = {"stage": stage_name, "stage_status": status}
        reason = stage.get("reason")
        if isinstance(reason, str) and reason:
            boundary["stage_reason"] = reason
        return boundary
    return None


def _stage_boundary_section(
    name: str,
    *,
    artifact_key: str,
    artifact: str,
    boundary: dict[str, str],
) -> dict[str, Any]:
    stage = boundary["stage"]
    stage_status = boundary["stage_status"]
    message = f"{artifact_key} artifact was not produced because {stage} stage is {stage_status}."
    reason = boundary.get("stage_reason")
    warnings = [message]
    if reason:
        warnings.append(f"Stage reason: {reason}")
    return _section(
        name,
        stage_status,
        fields={
            "artifact": artifact,
            "artifact_key": artifact_key,
            "stage": stage,
            "stage_status": stage_status,
            **({"stage_reason": reason} if reason else {}),
        },
        source_artifacts=["run_manifest.json"],
        warnings=warnings,
    )


def _monitor_section(config: dict[str, Any], *, config_path: Path, base: Path) -> dict[str, Any]:
    settings = load_monitor_config(config)
    output_dir = Path(settings.output_dir)
    if not output_dir.is_absolute():
        output_dir = base / output_dir
    path = output_dir / MONITOR_HEALTH_STATE_FILENAME
    artifact = _safe_ref(path, base=base)
    data, error = _read_json(path)
    if error:
        return _section("monitor", "missing" if "was not found" in error else "failed", source_artifacts=[artifact], errors=[error])
    fields = {
        "artifact": artifact,
        "artifact_type": data.get("artifact_type"),
        "cycle_count": data.get("cycle_count"),
        "failed_cycle_count": data.get("failed_cycle_count"),
        "latest_cycle_id": data.get("latest_cycle_id"),
        "latest_cycle_status": data.get("latest_cycle_status"),
        "latest_run_id": data.get("latest_run_id"),
        "alert_archive_status": data.get("alert_archive_status"),
        "alert_counts": _bounded_mapping(data.get("alert_counts")),
        "cooldown_records": data.get("cooldown_records"),
        "warning_count": data.get("warning_count"),
        "error_count": data.get("error_count"),
    }
    return _section("monitor", "available", fields=fields, source_artifacts=[artifact])


def _workbench_section(
    *,
    base: Path,
    latest_run: dict[str, Any],
    monitor: dict[str, Any],
) -> dict[str, Any]:
    path = base / WORKBENCH_SUMMARY_ARTIFACT
    data, error = _read_json(path)
    if error:
        return _section(
            "workbench",
            "missing" if "was not found" in error else "failed",
            source_artifacts=[WORKBENCH_SUMMARY_ARTIFACT],
            errors=[error],
        )
    summary_status = str(data.get("status") or "unknown")
    stale_warnings, stale_sources = _workbench_stale_diagnostics(data, latest_run=latest_run, monitor=monitor)
    fields = {
        "artifact": WORKBENCH_SUMMARY_ARTIFACT,
        "artifact_type": data.get("artifact_type"),
        "artifact_status": summary_status,
        "generated_at": data.get("generated_at"),
        "latest_run": _bounded_mapping(_dict(data.get("latest_run")).get("fields")),
        "stale": bool(stale_warnings),
        "stale_warning_count": len(stale_warnings),
        "warnings": len(_list(data.get("warnings"))),
        "errors": len(_list(data.get("errors"))),
    }
    status = _normalize_section_status(summary_status)
    if stale_warnings and status not in {"failed", "degraded"}:
        status = "partial"
    return _section(
        "workbench",
        status,
        fields=fields,
        source_artifacts=[WORKBENCH_SUMMARY_ARTIFACT, *stale_sources],
        warnings=[*_string_list(data.get("warnings")), *stale_warnings],
        errors=_string_list(data.get("errors")),
    )


def _workbench_stale_diagnostics(
    data: dict[str, Any],
    *,
    latest_run: dict[str, Any],
    monitor: dict[str, Any],
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    sources: list[str] = []
    workbench_latest = _dict(_dict(data.get("latest_run")).get("fields"))
    workbench_run_id = _clean_text(workbench_latest.get("run_id"))
    latest_fields = _dict(latest_run.get("fields"))
    latest_selection = _dict(latest_fields.get("selection"))
    current_run_id = _clean_text(latest_selection.get("latest_run_id")) or _clean_text(latest_fields.get("run_id"))
    if workbench_run_id and current_run_id and workbench_run_id != current_run_id:
        warnings.append(
            f"workbench summary references run {workbench_run_id}, but latest run is {current_run_id}. "
            f"Source: {RUN_INDEX_ARTIFACT}."
        )
        sources.append(RUN_INDEX_ARTIFACT)

    workbench_monitor = _dict(_dict(data.get("monitor_state")).get("fields"))
    workbench_cycle_id = _clean_text(workbench_monitor.get("latest_cycle_id"))
    monitor_fields = _dict(monitor.get("fields"))
    current_cycle_id = _clean_text(monitor_fields.get("latest_cycle_id"))
    if current_cycle_id == "none":
        current_cycle_id = None
    if workbench_cycle_id == "none":
        workbench_cycle_id = None
    if workbench_cycle_id and current_cycle_id and workbench_cycle_id != current_cycle_id:
        monitor_artifact = _clean_text(monitor_fields.get("artifact")) or f"runs/monitor/{MONITOR_HEALTH_STATE_FILENAME}"
        warnings.append(
            f"workbench summary references monitor cycle {workbench_cycle_id}, "
            f"but latest monitor cycle is {current_cycle_id}. Source: {monitor_artifact}."
        )
        sources.append(monitor_artifact)
    return warnings, sorted({source for source in sources if source})


def _check_counts(checks: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean or None


def _warning_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("warnings")))


def _error_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("errors")))
