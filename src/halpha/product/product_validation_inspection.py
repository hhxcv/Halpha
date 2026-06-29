from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.runtime.pipeline_contracts import RunContext
from halpha.product.product_validation import validate_product_contracts
from halpha.data.run_index import (
    RUN_INDEX_ARTIFACT,
    run_index_path,
    run_index_selection_label,
    select_latest_run_record,
)
from halpha.storage import display_path, runtime_root


FAILED_EXIT_CODE = 3
MAX_LISTED_CHECKS = 10
MAX_LISTED_ARTIFACTS = 12
MAX_LISTED_HINTS = 3


@dataclass(frozen=True)
class ProductValidationInspectionResult:
    status: str
    exit_code: int
    lines: list[str]
    validation: dict[str, Any]


@dataclass(frozen=True)
class _RunSelection:
    mode: str
    status: str
    run_dir: Path | None
    run_id: str | None
    source_artifact: str | None
    reason: str | None
    selection_key: str | None = None
    selection_label: str | None = None


def inspect_product_validation(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_dir: Path | None = None,
) -> ProductValidationInspectionResult:
    _ = config
    base = _base_path(config_path)
    selection = _select_run(config_path, requested_run_dir=run_dir, base=base)
    if selection.run_dir is None:
        return _missing_result(selection)

    manifest, manifest_error = _read_manifest(selection.run_dir / "run_manifest.json")
    if manifest_error:
        return _manifest_error_result(selection, manifest_error, base=base)

    run = _run_context(selection, manifest, config_path=config_path)
    validation = validate_product_contracts(run, mode="read_only")
    status = str(validation.get("status") or "unknown")
    exit_code = FAILED_EXIT_CODE if status == "failed" else 0
    lines = _validation_lines(selection, validation, exit_code=exit_code, base=base)
    return ProductValidationInspectionResult(
        status=status,
        exit_code=exit_code,
        lines=lines,
        validation=validation,
    )


def _select_run(config_path: Path, *, requested_run_dir: Path | None, base: Path) -> _RunSelection:
    if requested_run_dir is not None:
        resolved = requested_run_dir
        if not resolved.is_absolute():
            resolved = base / resolved
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
        with closing(sqlite3.connect(index_path)) as connection:
            selected = select_latest_run_record(connection)
    except sqlite3.Error as exc:
        return _RunSelection(
            mode="latest_run_index",
            status="failed",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason=f"{RUN_INDEX_ARTIFACT} is not readable: {exc}",
        )
    if selected is None:
        return _RunSelection(
            mode="latest_run_index",
            status="missing",
            run_dir=None,
            run_id=None,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason="local run index does not contain a latest run.",
        )
    selection_key = selected.selection_key
    selected_run_id = selected.run.run_id
    selected_run_dir = selected.run.run_dir
    path = Path(selected_run_dir)
    if not path.is_absolute():
        path = base / path
    if _project_local_path(path, base=base) is None:
        return _RunSelection(
            mode="latest_run_index",
            status="failed",
            run_dir=None,
            run_id=selected_run_id,
            source_artifact=RUN_INDEX_ARTIFACT,
            reason="local run index points outside the configured project root.",
            selection_key=selection_key,
            selection_label=run_index_selection_label(selection_key),
        )
    return _RunSelection(
        mode="latest_run_index",
        status="available",
        run_dir=path,
        run_id=selected_run_id,
        source_artifact=RUN_INDEX_ARTIFACT,
        reason=None,
        selection_key=selection_key,
        selection_label=run_index_selection_label(selection_key),
    )


def _read_manifest(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "run_manifest.json was not found."
    except OSError as exc:
        return {}, f"run_manifest.json could not be read: {exc}."
    except JSONDecodeError as exc:
        return {}, f"run_manifest.json is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, "run_manifest.json must be a JSON object."
    return loaded, None


def _run_context(selection: _RunSelection, manifest: dict[str, Any], *, config_path: Path) -> RunContext:
    run_dir = selection.run_dir
    if run_dir is None:
        raise ValueError("product validation run selection must include a run directory.")
    return RunContext(
        run_id=str(manifest.get("run_id") or selection.run_id or run_dir.name),
        run_dir=run_dir,
        raw_dir=run_dir / "raw",
        analysis_dir=run_dir / "analysis",
        codex_context_dir=run_dir / "codex_context",
        report_dir=run_dir / "report",
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest=manifest,
    )


def _validation_lines(
    selection: _RunSelection,
    validation: dict[str, Any],
    *,
    exit_code: int,
    base: Path,
) -> list[str]:
    status = str(validation.get("status") or "unknown")
    counts = _dict(validation.get("counts"))
    checks = _list(validation.get("checks"))
    lines = [
        "Halpha product validation failed." if exit_code else "Halpha product validation succeeded.",
        f"status: {status}",
        f"selection: {selection.mode}",
        f"run_id: {validation.get('run_id') or selection.run_id or 'unknown'}",
    ]
    lines.extend(_selection_source_lines(selection))
    if selection.run_dir is not None:
        lines.append(f"run_dir: {_safe_display_path(selection.run_dir, base=base)}")
    lines.append(
        "checks: "
        f"total={_int(counts.get('checks'))} "
        f"ok={_int(counts.get('ok'))} "
        f"warning={_int(counts.get('warning'))} "
        f"degraded={_int(counts.get('degraded'))} "
        f"failed={_int(counts.get('failed'))} "
        f"skipped={_int(counts.get('skipped'))}"
    )
    lines.append(f"failed_checks: {_check_ids(checks, 'failed')}")
    lines.append(f"warning_checks: {_check_ids(checks, 'warning')}")
    lines.append(f"degraded_checks: {_check_ids(checks, 'degraded')}")
    lines.extend(_source_artifact_lines(validation))
    hints = _recovery_hints(checks)
    lines.append(f"next_steps: {hints if hints else 'none'}")
    lines.append("pipeline: not_run")
    lines.append("codex: not_run")
    lines.append("artifact_written: false")
    return lines


def _missing_result(selection: _RunSelection) -> ProductValidationInspectionResult:
    lines = [
        "Halpha product validation failed.",
        f"status: {selection.status}",
        f"selection: {selection.mode}",
    ]
    lines.extend(_selection_source_lines(selection))
    if selection.source_artifact:
        lines.append(f"source_artifact: {selection.source_artifact}")
    if selection.reason:
        lines.append(f"reason: {selection.reason}")
    lines.extend(["pipeline: not_run", "codex: not_run", "artifact_written: false"])
    return ProductValidationInspectionResult(
        status=selection.status,
        exit_code=FAILED_EXIT_CODE,
        lines=lines,
        validation={},
    )


def _manifest_error_result(
    selection: _RunSelection,
    reason: str,
    *,
    base: Path,
) -> ProductValidationInspectionResult:
    lines = [
        "Halpha product validation failed.",
        "status: failed",
        f"selection: {selection.mode}",
    ]
    lines.extend(_selection_source_lines(selection))
    if selection.run_id:
        lines.append(f"run_id: {selection.run_id}")
    if selection.run_dir is not None:
        lines.append(f"run_dir: {_safe_display_path(selection.run_dir, base=base)}")
    lines.extend(
        [
            "source_artifact: run_manifest.json",
            f"reason: {reason}",
            "pipeline: not_run",
            "codex: not_run",
            "artifact_written: false",
        ]
    )
    return ProductValidationInspectionResult(
        status="failed",
        exit_code=FAILED_EXIT_CODE,
        lines=lines,
        validation={},
    )


def _selection_source_lines(selection: _RunSelection) -> list[str]:
    if not selection.selection_key:
        return []
    lines = [f"selection_source: {selection.selection_key}"]
    if selection.selection_label:
        lines.append(f"selection_label: {selection.selection_label}")
    return lines


def _source_artifact_lines(validation: dict[str, Any]) -> list[str]:
    refs = [str(ref) for ref in _list(validation.get("source_artifacts")) if isinstance(ref, str) and ref]
    if not refs:
        return ["source_artifacts: none"]
    listed = refs[:MAX_LISTED_ARTIFACTS]
    lines = ["source_artifacts: " + ", ".join(listed)]
    omitted = len(refs) - len(listed)
    if omitted > 0:
        lines.append(f"source_artifacts_omitted: {omitted}")
    return lines


def _check_ids(checks: list[Any], status: str) -> str:
    ids = []
    for check in checks:
        record = _dict(check)
        if record.get("status") != status:
            continue
        check_id = record.get("check_id")
        if isinstance(check_id, str) and check_id:
            ids.append(check_id)
        if len(ids) >= MAX_LISTED_CHECKS:
            break
    return ", ".join(ids) if ids else "none"


def _recovery_hints(checks: list[Any]) -> str:
    hints: list[str] = []
    seen = set()
    for check in checks:
        record = _dict(check)
        if record.get("status") not in {"failed", "degraded", "warning"}:
            continue
        hint = record.get("recovery_hint")
        if not isinstance(hint, str) or not hint or hint in seen:
            continue
        seen.add(hint)
        hints.append(hint)
        if len(hints) >= MAX_LISTED_HINTS:
            break
    return " | ".join(hints)


def _safe_display_path(path: Path, *, base: Path) -> str:
    return display_path(path, base=base)


def _project_local_path(path: Path, *, base: Path) -> Path | None:
    try:
        path.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return path


def _base_path(config_path: Path) -> Path:
    return runtime_root(config_path)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0
