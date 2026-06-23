from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.storage import read_json_object, resolve_local_ref, safe_local_ref


EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REJECTED_EXTERNAL_REF_NAME = ".halpha_external_ref_rejected"


def dashboard_read_json(
    path: Path,
    *,
    external_ref_name: str | None = REJECTED_EXTERNAL_REF_NAME,
) -> tuple[dict[str, Any], str | None]:
    return read_json_object(path, external_ref_name=external_ref_name)


def dashboard_read_json_state(path: Path) -> tuple[dict[str, Any], str, str | None]:
    data, error = dashboard_read_json(path)
    if error is None:
        return data, "available", None
    status = "missing" if error == f"{path.name} was not found." else "failed"
    return {}, status, error


def dashboard_resolve_ref(
    value: str,
    *,
    base: Path,
    rejected_name: str = REJECTED_EXTERNAL_REF_NAME,
) -> Path:
    return resolve_local_ref(value, base=base, rejected_name=rejected_name)


def dashboard_safe_ref(
    path: Path,
    *,
    base: Path,
    external_ref: str = EXTERNAL_ARTIFACT_REF,
    rejected_name: str | None = REJECTED_EXTERNAL_REF_NAME,
) -> str:
    return safe_local_ref(path, base=base, external_ref=external_ref, rejected_name=rejected_name)


def dashboard_overall_status(statuses: list[str]) -> str:
    normalized = [_normalize_status(status) for status in statuses if status and status != "unknown"]
    if not normalized:
        return "unknown"
    if all(status == "missing" for status in normalized):
        return "missing"
    if any(status == "failed" for status in normalized):
        return "partial" if any(status == "available" for status in normalized) else "failed"
    if any(status == "missing" for status in normalized):
        return "partial" if any(status == "available" for status in normalized) else "missing"
    if all(status == "available" for status in normalized):
        return "available"
    return "partial"


def dashboard_section(
    name: str,
    status: str,
    *,
    fields: dict[str, Any] | None = None,
    source_artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "fields": fields or {},
        "source_artifacts": source_artifacts or [],
        "warnings": warnings or [],
        "errors": errors or [],
    }


def dashboard_manifest_artifact_ref(manifest: dict[str, Any], key: str, default: str) -> str | None:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        value = artifacts.get(key)
        if isinstance(value, str) and value:
            return value
    return default if manifest else None


def dashboard_strict_overall_status(statuses: list[str]) -> str:
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "degraded" for status in statuses):
        return "degraded"
    if any(
        status
        in {
            "disabled",
            "insufficient_data",
            "missing",
            "not_generated",
            "not_run",
            "partial",
            "skipped",
            "unknown",
        }
        for status in statuses
    ):
        return "partial"
    if any(status == "warning" for status in statuses):
        return "warning"
    return "available"


def dashboard_normalize_section_status(status: str) -> str:
    normalized = status.lower()
    if normalized in {"ok", "available", "succeeded", "success"}:
        return "available"
    if normalized in {
        "warning",
        "degraded",
        "disabled",
        "failed",
        "partial",
        "missing",
        "insufficient_data",
        "not_generated",
        "not_run",
        "skipped",
    }:
        return normalized
    return "unknown"


def dashboard_bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bounded: dict[str, Any] = {}
    for key, item in sorted(value.items()):
        if isinstance(item, (str, int, float, bool)) or item is None:
            bounded[str(key)] = item
    return bounded


def _normalize_status(status: str) -> str:
    lowered = status.lower()
    if lowered in {"ok", "available", "succeeded", "success", "completed"}:
        return "available"
    if lowered in {"disabled", "insufficient_data", "not_generated", "not_run", "pending", "skipped"}:
        return "partial"
    return lowered
