from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.outcome.outcome_history import OUTCOME_HISTORY_ARTIFACT, OUTCOME_HISTORY_STATE_ARTIFACT
from halpha.data.run_index import RUN_INDEX_ARTIFACT, run_index_path


OUTCOME_TARGETS_ARTIFACT = "analysis/outcome_targets.json"
OUTCOME_EVALUATIONS_ARTIFACT = "analysis/outcome_evaluations.json"
OUTCOME_TRACKING_MATERIAL_ARTIFACT = "analysis/outcome_tracking_material.md"


class OutcomeInspectionError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class OutcomeInspectionResult:
    status: str
    lines: list[str]


def inspect_local_outcomes(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_dir: Path | None = None,
) -> OutcomeInspectionResult:
    del config
    base = config_path.parent
    selected_run = _selected_run_section(config_path, run_dir=run_dir, base=base)
    selected_run_dir = selected_run["extra"].get("run_dir")
    manifest = selected_run["extra"].get("manifest")

    if isinstance(selected_run_dir, Path):
        run_sections = [
            selected_run,
            _targets_section(selected_run_dir, base=base),
            _evaluations_section(selected_run_dir, base=base),
            _material_section(selected_run_dir, manifest=_dict(manifest), base=base),
        ]
    else:
        run_sections = [
            selected_run,
            _section(
                "outcome_targets",
                "skipped",
                artifact=OUTCOME_TARGETS_ARTIFACT,
                reason="no run directory was selected.",
            ),
            _section(
                "outcome_evaluations",
                "skipped",
                artifact=OUTCOME_EVALUATIONS_ARTIFACT,
                reason="no run directory was selected.",
            ),
            _section(
                "outcome_tracking_material",
                "skipped",
                artifact=OUTCOME_TRACKING_MATERIAL_ARTIFACT,
                reason="no run directory was selected.",
            ),
        ]

    history = _history_section(base=base)
    status = _overall_status([section["status"] for section in run_sections] + [history["status"]])
    lines = [
        "Halpha outcome inspection succeeded.",
        f"status: {status}",
        f"config: {_safe_path(config_path, base=Path.cwd())}",
        "run_outcomes:",
    ]
    for section in run_sections:
        lines.extend(_section_lines(section))
    lines.append("shared_outcomes:")
    lines.extend(_section_lines(history))
    return OutcomeInspectionResult(status=status, lines=lines)


def _selected_run_section(config_path: Path, *, run_dir: Path | None, base: Path) -> dict[str, Any]:
    explicit = run_dir is not None
    if explicit:
        selected = _resolve_run_dir(run_dir or Path(), base=base)
    else:
        selected = _latest_run_from_index(config_path)
        if selected is None:
            return _section(
                "selected_run",
                "skipped",
                artifact=RUN_INDEX_ARTIFACT,
                reason="no latest run was found in the local run index.",
            )
        if not selected.exists():
            return _section(
                "selected_run",
                "skipped",
                artifact=RUN_INDEX_ARTIFACT,
                reason="latest run directory from the local run index was not found.",
            )
        if not selected.is_dir():
            return _section(
                "selected_run",
                "skipped",
                artifact=RUN_INDEX_ARTIFACT,
                reason="latest run path from the local run index is not a directory.",
            )

    manifest_path = selected / "run_manifest.json"
    manifest, error = _read_json(manifest_path)
    if error:
        raise OutcomeInspectionError(f"run_manifest.json could not be inspected: {error}")
    return _section(
        "selected_run",
        "ok",
        artifact=_safe_path(manifest_path, base=base),
        fields={
            "run_id": manifest.get("run_id"),
            "run_status": manifest.get("status"),
            "run_dir": _safe_path(selected, base=base),
        },
        extra={"run_dir": selected, "manifest": manifest},
    )


def _targets_section(run_dir: Path, *, base: Path) -> dict[str, Any]:
    path = run_dir / OUTCOME_TARGETS_ARTIFACT
    artifact, error = _read_json(path)
    if error:
        if not _was_not_found(error):
            raise OutcomeInspectionError(f"{OUTCOME_TARGETS_ARTIFACT} could not be inspected: {error}")
        return _section(
            "outcome_targets",
            "skipped",
            artifact=_safe_path(path, base=base),
            reason=error,
        )
    targets = artifact.get("targets")
    skipped_records = artifact.get("skipped_records")
    if not isinstance(targets, list):
        raise OutcomeInspectionError(f"{OUTCOME_TARGETS_ARTIFACT} must contain a targets list.")
    if skipped_records is not None and not isinstance(skipped_records, list):
        raise OutcomeInspectionError(f"{OUTCOME_TARGETS_ARTIFACT} skipped_records must be a list when present.")
    counts = _dict(artifact.get("counts"))
    return _section(
        "outcome_targets",
        str(artifact.get("status") or "unknown"),
        artifact=_safe_path(path, base=base),
        fields={
            "targets": _int(counts.get("targets"), fallback=len(targets)),
            "skipped_records": _int(counts.get("skipped_records"), fallback=len(_list(skipped_records))),
            "duplicate_records": _int(counts.get("duplicate_records")),
            "missing_source_fields": _int(counts.get("missing_source_fields")),
            "warnings": len(_list(artifact.get("warnings"))),
            "errors": len(_list(artifact.get("errors"))),
        },
    )


def _evaluations_section(run_dir: Path, *, base: Path) -> dict[str, Any]:
    path = run_dir / OUTCOME_EVALUATIONS_ARTIFACT
    artifact, error = _read_json(path)
    if error:
        if not _was_not_found(error):
            raise OutcomeInspectionError(f"{OUTCOME_EVALUATIONS_ARTIFACT} could not be inspected: {error}")
        return _section(
            "outcome_evaluations",
            "skipped",
            artifact=_safe_path(path, base=base),
            reason=error,
        )
    evaluations = artifact.get("evaluations")
    if not isinstance(evaluations, list):
        raise OutcomeInspectionError(f"{OUTCOME_EVALUATIONS_ARTIFACT} must contain an evaluations list.")
    counts = _dict(artifact.get("counts"))
    return _section(
        "outcome_evaluations",
        str(artifact.get("status") or "unknown"),
        artifact=_safe_path(path, base=base),
        fields={
            "evaluations": _int(counts.get("evaluations"), fallback=len(evaluations)),
            "evaluated": _int(counts.get("evaluated")),
            "pending": _int(counts.get("pending")),
            "insufficient_data": _int(counts.get("insufficient_data")),
            "skipped": _int(counts.get("skipped")),
            "stale": _int(counts.get("stale")),
            "failed": _int(counts.get("failed")),
            "warnings": len(_list(artifact.get("warnings"))),
            "errors": len(_list(artifact.get("errors"))),
        },
    )


def _material_section(run_dir: Path, *, manifest: dict[str, Any], base: Path) -> dict[str, Any]:
    path = run_dir / OUTCOME_TRACKING_MATERIAL_ARTIFACT
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _section(
            "outcome_tracking_material",
            "skipped",
            artifact=_safe_path(path, base=base),
            reason="outcome_tracking_material.md was not found.",
        )
    material_summary = _dict(manifest.get("outcome_tracking_material"))
    status = str(material_summary.get("status") or "ok")
    return _section(
        "outcome_tracking_material",
        status,
        artifact=_safe_path(path, base=base),
        fields={
            "chars": len(content),
            "selected_evaluations": _int(material_summary.get("selected_evaluation_count")),
            "omitted_evaluations": _int(material_summary.get("omitted_evaluation_count")),
        },
    )


def _history_section(*, base: Path) -> dict[str, Any]:
    path = base / OUTCOME_HISTORY_STATE_ARTIFACT
    artifact, error = _read_json(path)
    if error:
        if not _was_not_found(error):
            raise OutcomeInspectionError(f"{OUTCOME_HISTORY_STATE_ARTIFACT} could not be inspected: {error}")
        return _section(
            "outcome_history",
            "skipped",
            artifact=OUTCOME_HISTORY_STATE_ARTIFACT,
            reason=error,
        )
    totals = _dict(artifact.get("totals"))
    return _section(
        "outcome_history",
        str(artifact.get("status") or "unknown"),
        artifact=OUTCOME_HISTORY_STATE_ARTIFACT,
        fields={
            "records": _int(totals.get("records")),
            "incoming_records": _int(totals.get("incoming_records")),
            "duplicate_records": _int(totals.get("duplicate_records")),
            "conflicting_duplicates": _int(totals.get("conflicting_duplicates")),
            "warnings": _int(totals.get("warning_count"), fallback=len(_list(artifact.get("warnings")))),
            "errors": _int(totals.get("error_count"), fallback=len(_list(artifact.get("errors")))),
            "history": OUTCOME_HISTORY_ARTIFACT,
        },
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
        raise OutcomeInspectionError(f"{RUN_INDEX_ARTIFACT} is not readable: {exc}") from exc
    if row is None or not isinstance(row[0], str) or not row[0]:
        return None
    run_dir = Path(row[0])
    if not run_dir.is_absolute():
        run_dir = config_path.parent / run_dir
    return _project_local_path(run_dir, base=config_path.parent)


def _latest_run_id(connection: sqlite3.Connection) -> str | None:
    for key in ("latest_successful_run", "latest_run"):
        row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
        if row and isinstance(row[0], str) and row[0]:
            return row[0]
    return None


def _resolve_run_dir(run_dir: Path, *, base: Path) -> Path:
    path = run_dir
    if not path.is_absolute():
        path = base / path
    if not path.exists():
        raise OutcomeInspectionError("requested run directory was not found.")
    if not path.is_dir():
        raise OutcomeInspectionError("requested run directory is not a directory.")
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
    parts = [f"  {section['name']}: {section['status']}"]
    fields = section["fields"]
    if fields:
        parts.append(_field_text(fields))
    if section.get("artifact"):
        parts.append(f"artifact={section['artifact']}")
    if section.get("reason"):
        parts.append(f"reason={section['reason']}")
    return [" ".join(parts)]


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
    except OSError as exc:
        return {}, f"{path.name} could not be read: {exc}."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _was_not_found(error: str) -> bool:
    return " was not found." in error


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


def _project_local_path(path: Path, *, base: Path) -> Path | None:
    try:
        path.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return path


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    return value if isinstance(value, int) else fallback
