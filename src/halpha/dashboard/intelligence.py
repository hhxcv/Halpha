from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.dashboard.common import dashboard_bounded_mapping as _bounded_mapping
from halpha.dashboard.common import dashboard_manifest_artifact_ref as _artifact_ref
from halpha.dashboard.common import dashboard_normalize_section_status as _normalize_section_status
from halpha.dashboard.common import dashboard_read_json as _read_json
from halpha.dashboard.common import dashboard_resolve_ref as _resolve_ref
from halpha.dashboard.common import dashboard_safe_ref as _safe_ref
from halpha.dashboard.common import dashboard_section as _section
from halpha.dashboard.common import dashboard_strict_overall_status as _overall_status
from halpha.dashboard.runs import dashboard_latest_run_section, dashboard_run_detail
from halpha.data.run_index import RUN_INDEX_ARTIFACT
from halpha.storage import artifact_base as _artifact_base
from halpha.utils.value_helpers import (
    as_dict as _dict,
    as_list as _list,
    stringified_list as _string_list,
)


TEXT_INTELLIGENCE_ARTIFACTS = (
    ("raw_text_events", "Raw text events", "raw/text_events.json"),
    ("text_event_records", "Text event records", "analysis/text_event_records.json"),
    ("text_entity_evidence", "Text entity evidence", "analysis/text_entity_evidence.json"),
    (
        "text_event_classification_evidence",
        "Text event classification",
        "analysis/text_event_classification_evidence.json",
    ),
    ("text_event_topics", "Text event topics", "analysis/text_event_topics.json"),
    ("text_event_signals", "Text event signals", "analysis/text_event_signals.json"),
    ("event_intelligence_material", "Event intelligence material", "analysis/event_intelligence_material.md"),
)


def dashboard_text_intelligence(*, config_path: Path, run_id: str | None = None) -> dict[str, Any]:
    selected = _dashboard_selected_run(config_path, run_id=run_id)
    commands = {
        "text_models_prepare": "available",
        "text_intel": "available",
    }
    if selected["status"] != "available":
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_text_intelligence",
            "status": selected["status"],
            "selected_run": selected,
            "artifacts": [],
            "source_artifacts": selected.get("source_artifacts", []),
            "warnings": selected.get("warnings", []),
            "errors": selected.get("errors", []),
            "commands": commands,
            "omitted": {
                "full_raw_text_events_embedded": False,
                "full_text_intelligence_artifacts_embedded": False,
                "llm_generated_event_states": False,
            },
        }
    base = _artifact_base(config_path)
    run_dir = _resolve_ref(str(selected["fields"]["run_dir"]), base=base)
    manifest_path = _resolve_ref(str(selected["fields"]["manifest"]), base=base)
    manifest, error = _read_json(manifest_path)
    if error:
        failed = {
            **selected,
            "status": "failed",
            "errors": [error],
        }
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_text_intelligence",
            "status": "failed",
            "selected_run": failed,
            "artifacts": [],
            "source_artifacts": [RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
            "warnings": [],
            "errors": [error],
            "commands": commands,
            "omitted": {
                "full_raw_text_events_embedded": False,
                "full_text_intelligence_artifacts_embedded": False,
                "llm_generated_event_states": False,
            },
        }

    artifacts = [
        _dashboard_run_artifact_summary(key, title, default, run_dir=run_dir, manifest=manifest, base=base)
        for key, title, default in TEXT_INTELLIGENCE_ARTIFACTS
    ]
    source_artifacts = sorted(
        {
            RUN_INDEX_ARTIFACT,
            _safe_ref(manifest_path, base=base),
            *[
                ref
                for artifact in artifacts
                for ref in _string_list(artifact.get("source_artifacts"))
            ],
        }
    )
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_text_intelligence",
        "status": _overall_status([artifact["status"] for artifact in artifacts]),
        "selected_run": selected,
        "artifacts": artifacts,
        "source_artifacts": source_artifacts,
        "warnings": [
            warning
            for artifact in artifacts
            for warning in _string_list(artifact.get("warnings"))
        ],
        "errors": [
            error
            for artifact in artifacts
            for error in _string_list(artifact.get("errors"))
        ],
        "commands": commands,
        "omitted": {
            "full_raw_text_events_embedded": False,
            "full_text_intelligence_artifacts_embedded": False,
            "llm_generated_event_states": False,
        },
    }


def _dashboard_selected_run(config_path: Path, *, run_id: str | None) -> dict[str, Any]:
    base = _artifact_base(config_path)
    if run_id:
        detail = dashboard_run_detail(config_path, run_id=run_id)
        if detail["status"] != "available":
            return {
                "status": detail["status"],
                "fields": detail.get("fields", {}),
                "source_artifacts": detail.get("source_artifacts", []),
                "warnings": detail.get("warnings", []),
                "errors": detail.get("errors", []),
            }
        fields = detail["fields"]
        return _section(
            "selected_run",
            "available",
            fields={
                "run_id": detail["run_id"],
                "run_dir": fields.get("run_dir"),
                "manifest": fields.get("manifest"),
                "run_status": fields.get("run_status"),
                "started_at": fields.get("started_at"),
                "finished_at": fields.get("finished_at"),
            },
            source_artifacts=detail.get("source_artifacts", []),
        )
    latest, _, _ = dashboard_latest_run_section(config_path, base=base)
    return latest


def _dashboard_run_artifact_summary(
    key: str,
    title: str,
    default_artifact: str,
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    base: Path,
) -> dict[str, Any]:
    artifact = _artifact_ref(manifest, key, default_artifact)
    if artifact is None:
        return _section(
            key,
            "missing",
            fields={"title": title, "artifact": default_artifact},
            warnings=[f"{title} artifact is not recorded."],
        )
    path = run_dir / artifact
    preview_path = _safe_ref(path, base=base)
    if path.suffix.lower() in {".md", ".markdown"}:
        if not path.exists():
            return _section(
                key,
                "missing",
                fields={"title": title, "artifact": artifact, "preview_path": preview_path},
                source_artifacts=[preview_path],
                warnings=[f"{path.name} was not found."],
            )
        return _section(
            key,
            "available",
            fields={
                "title": title,
                "artifact": artifact,
                "preview_path": preview_path,
                "artifact_type": "markdown",
                "artifact_status": "available",
                "record_count": 0,
                "warning_count": 0,
                "error_count": 0,
                "counts": {},
            },
            source_artifacts=[preview_path],
        )
    data, error = _read_json(path)
    if error:
        status = "missing" if "was not found" in error else "failed"
        return _section(
            key,
            status,
            fields={"title": title, "artifact": artifact, "preview_path": preview_path},
            source_artifacts=[preview_path],
            warnings=[error] if status == "missing" else [],
            errors=[error] if status == "failed" else [],
        )
    fields = {
        "title": title,
        "artifact": artifact,
        "preview_path": preview_path,
        "artifact_type": data.get("artifact_type"),
        "artifact_status": data.get("status") or "available",
        "record_count": _dashboard_record_count(data),
        "warning_count": len(_list(data.get("warnings"))),
        "error_count": len(_list(data.get("errors"))),
        "counts": _bounded_mapping(data.get("counts")),
    }
    source_artifacts = [
        preview_path,
        *[_run_ref_path(ref, run_dir=run_dir, base=base) for ref in _string_list(data.get("source_artifacts"))],
    ]
    return _section(
        key,
        _normalize_section_status(str(data.get("status") or "available")),
        fields=fields,
        source_artifacts=sorted({ref for ref in source_artifacts if ref}),
        warnings=_string_list(data.get("warnings")),
        errors=_string_list(data.get("errors")),
    )


def _dashboard_record_count(data: dict[str, Any]) -> int:
    for key in (
        "records",
        "items",
        "recommendations",
        "triggers",
        "changes",
        "risk_assessments",
        "targets",
        "evaluations",
        "topics",
        "signals",
    ):
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
    counts = _dict(data.get("counts"))
    for value in counts.values():
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


def _run_ref_path(ref: str, *, run_dir: Path, base: Path) -> str:
    if ref.startswith(("runs/", "data/")):
        return ref
    return _safe_ref(run_dir / ref, base=base)

