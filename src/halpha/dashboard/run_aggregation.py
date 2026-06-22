from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.storage import resolve_local_ref, safe_local_ref
from halpha.utils.value_helpers import as_dict


EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REJECTED_EXTERNAL_REF_NAME = ".halpha_external_ref_rejected"


def run_list_record(
    row: Any,
    artifacts: dict[str, list[str]],
    *,
    base: Path,
    latest: dict[str, str | None],
) -> dict[str, Any]:
    run_id = str(row[0])
    run_dir = _resolve_ref(str(row[1]), base=base)
    manifest_path = _resolve_ref(str(row[9]), base=base)
    report_paths = artifacts.get("report", [])
    integrity_state = run_integrity_state(run_dir, manifest_path, base=base)
    report_state = run_report_state(
        run_dir,
        report_paths[0] if report_paths else None,
        codex_status=row[6],
        base=base,
    )
    return {
        "run_id": run_id,
        "run_dir": _safe_ref(run_dir, base=base),
        "started_at": row[2],
        "finished_at": row[3],
        "status": row[4],
        "failed_stage": row[5],
        "codex_status": row[6],
        "warning_count": int(row[7] or 0),
        "error_count": int(row[8] or 0),
        "manifest": _safe_ref(manifest_path, base=base),
        "integrity_state": integrity_state,
        "report": report_state.get("artifact") if report_state.get("status") == "available" else None,
        "report_state": report_state,
        "latest_state": {
            "is_latest_run": run_id == latest.get("latest_run_id"),
            "is_latest_successful_run": run_id == latest.get("latest_successful_run_id"),
        },
    }


def run_integrity_state(run_dir: Path, manifest_path: Path, *, base: Path) -> dict[str, Any]:
    missing: list[str] = []
    if not run_dir.is_dir():
        missing.append("run_dir")
    if not manifest_path.is_file():
        missing.append("manifest")
    return {
        "status": "available" if not missing else "missing",
        "run_dir": _safe_ref(run_dir, base=base),
        "manifest": _safe_ref(manifest_path, base=base),
        "missing": missing,
    }


def run_report_state(run_dir: Path, report_ref: str | None, *, codex_status: Any, base: Path) -> dict[str, Any]:
    if report_ref:
        path = _report_artifact_path(run_dir, report_ref, base=base)
        artifact = _display_report_ref(report_ref, path, base=base)
        if path.exists() and path.is_file():
            return {"status": "available", "artifact": artifact}
        return {
            "status": "missing",
            "artifact": artifact,
            "warning": "recorded report artifact was not found.",
        }
    status = str(codex_status or "").lower()
    if status in {"skipped", "disabled", "not_run"}:
        return {"status": status, "artifact": None}
    return {"status": "missing", "artifact": None}


def manifest_report_state(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    recorded = _recorded_artifact_ref(manifest, "report")
    codex_status = as_dict(manifest.get("codex")).get("status")
    if recorded:
        if (run_dir / recorded).is_file():
            return {"status": "available", "artifact": recorded}
        return {"status": "missing", "artifact": recorded, "warning": "recorded report artifact was not found."}
    if codex_status in {"skipped", "disabled", "not_run"}:
        return {"status": str(codex_status), "artifact": None}
    return {"status": "missing", "artifact": None}


def _recorded_artifact_ref(manifest: dict[str, Any], key: str) -> str | None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    value = artifacts.get(key)
    return value if isinstance(value, str) and value else None


def _report_artifact_path(run_dir: Path, report_ref: str, *, base: Path) -> Path:
    path = Path(report_ref)
    if path.is_absolute():
        return path
    if report_ref.startswith(("runs/", "data/")):
        return base / path
    return run_dir / path


def _display_report_ref(report_ref: str, path: Path, *, base: Path) -> str:
    if Path(report_ref).is_absolute() or report_ref.startswith(("runs/", "data/")):
        return _safe_ref(path, base=base)
    if ".." in Path(report_ref).parts:
        return _safe_ref(path, base=base)
    return report_ref


def _resolve_ref(value: str, *, base: Path) -> Path:
    return resolve_local_ref(value, base=base, rejected_name=REJECTED_EXTERNAL_REF_NAME)


def _safe_ref(path: Path, *, base: Path) -> str:
    return safe_local_ref(
        path,
        base=base,
        external_ref=EXTERNAL_ARTIFACT_REF,
        rejected_name=REJECTED_EXTERNAL_REF_NAME,
    )
