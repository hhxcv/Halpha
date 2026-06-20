from __future__ import annotations

from contextlib import closing
import json
from json import JSONDecodeError
from pathlib import Path
import sqlite3
from typing import Any

from .monitoring import MONITOR_HEALTH_STATE_FILENAME, load_monitor_config
from .run_index import RUN_INDEX_ARTIFACT, run_index_path
from .workbench import DEFAULT_WORKBENCH_OUTPUT_DIR, WORKBENCH_SUMMARY_FILENAME


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_PREVIEW_CHARS = 20_000
MAX_PREVIEW_ROWS = 100
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
PRODUCT_CONTRACT_VALIDATION_ARTIFACT = "analysis/product_contract_validation.json"
WORKBENCH_SUMMARY_ARTIFACT = f"{DEFAULT_WORKBENCH_OUTPUT_DIR}/{WORKBENCH_SUMMARY_FILENAME}"


class DashboardError(Exception):
    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def create_dashboard_app(
    config: dict[str, Any],
    *,
    config_path: Path,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> Any:
    try:
        from fastapi import FastAPI
    except ModuleNotFoundError as exc:
        raise DashboardError("FastAPI is required to run the dashboard.") from exc

    validate_dashboard_host(host)
    validate_dashboard_port(port)
    app = FastAPI(title="Halpha Dashboard", version="0.0.0")
    health = dashboard_health(config, config_path=config_path, host=host, port=port)

    @app.get("/")
    def root() -> dict[str, Any]:
        return {
            "service": "halpha_dashboard",
            "status": health["status"],
            "health": "/api/health",
        }

    @app.get("/api/health")
    def health_endpoint() -> dict[str, Any]:
        return health

    @app.get("/api/overview")
    def overview_endpoint() -> dict[str, Any]:
        return dashboard_overview(config, config_path=config_path)

    @app.get("/api/runs")
    def runs_endpoint() -> dict[str, Any]:
        return dashboard_runs(config_path=config_path)

    @app.get("/api/runs/{run_id}")
    def run_detail_endpoint(run_id: str) -> dict[str, Any]:
        return dashboard_run_detail(config_path=config_path, run_id=run_id)

    @app.get("/api/artifacts/preview")
    def artifact_preview_endpoint(path: str) -> dict[str, Any]:
        return dashboard_artifact_preview(config_path=config_path, artifact_path=path)

    return app


def run_dashboard_service(
    config: dict[str, Any],
    *,
    config_path: Path,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise DashboardError("Uvicorn is required to run the dashboard.") from exc

    app = create_dashboard_app(config, config_path=config_path, host=host, port=port)
    uvicorn.run(app, host=host, port=port)


def dashboard_health(
    config: dict[str, Any],
    *,
    config_path: Path,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> dict[str, Any]:
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    return {
        "artifact_type": "dashboard_health",
        "service": "halpha_dashboard",
        "status": "ok",
        "local_only": True,
        "host": host,
        "port": port,
        "config": {
            "loaded": True,
            "ref": dashboard_config_ref(config_path),
        },
        "features": {
            "overview_api": "not_implemented",
            "artifact_preview_api": "not_implemented",
            "job_runner": "not_implemented",
            "frontend_ui": "not_implemented",
        },
    }


def dashboard_overview(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _config_base(config_path)
    latest_run, run_dir, manifest = _latest_run_section(config_path, base=base)
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
        "monitor": _monitor_section(config, config_path=config_path, base=base),
        "workbench": _workbench_section(base=base),
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


def dashboard_runs(config_path: Path, *, limit: int = 100) -> dict[str, Any]:
    base = _config_base(config_path)
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_list",
            "status": "missing",
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "runs": [],
            "warnings": ["local run index was not found."],
            "errors": [],
        }
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            rows = connection.execute(
                """
                SELECT
                  run_id,
                  run_dir,
                  started_at,
                  finished_at,
                  status,
                  failed_stage,
                  codex_status,
                  warning_count,
                  error_count,
                  manifest_path
                FROM runs
                ORDER BY COALESCE(started_at, '') DESC, run_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            artifacts = _run_artifact_index(connection)
    except sqlite3.Error as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_list",
            "status": "failed",
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "runs": [],
            "warnings": [],
            "errors": [f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
        }
    runs = [_run_list_record(row, artifacts.get(str(row[0]), {}), base=base) for row in rows]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_list",
        "status": "available",
        "source_artifacts": [RUN_INDEX_ARTIFACT],
        "runs": runs,
        "warnings": [],
        "errors": [],
    }


def dashboard_run_detail(config_path: Path, *, run_id: str) -> dict[str, Any]:
    base = _config_base(config_path)
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return _run_detail_missing(run_id, warning="local run index was not found.")
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            row = connection.execute(
                """
                SELECT
                  run_id,
                  run_dir,
                  started_at,
                  finished_at,
                  status,
                  failed_stage,
                  codex_status,
                  warning_count,
                  error_count,
                  manifest_path
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_detail",
            "status": "failed",
            "run_id": run_id,
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "fields": {},
            "stages": [],
            "artifacts": [],
            "warnings": [],
            "errors": [f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
        }
    if row is None:
        return _run_detail_missing(run_id, warning="run id was not found in the local run index.")

    run = _run_list_record(row, {}, base=base)
    manifest_path = _resolve_ref(str(row[9]), base=base)
    manifest, error = _read_json(manifest_path)
    if error:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_detail",
            "status": "failed",
            "run_id": run_id,
            "source_artifacts": [RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
            "fields": run,
            "stages": [],
            "artifacts": [],
            "warnings": [],
            "errors": [error],
        }

    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_detail",
        "status": "available",
        "run_id": run_id,
        "source_artifacts": [RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
        "fields": {
            **run,
            "manifest_status": str(manifest.get("status") or "unknown"),
            "codex": _bounded_mapping(manifest.get("codex")),
            "counts": _bounded_mapping(manifest.get("counts")),
        },
        "stages": _stage_timeline(manifest),
        "artifacts": _manifest_artifacts(manifest),
        "warnings": _string_list(manifest.get("warnings")),
        "errors": _manifest_error_messages(manifest),
    }


def dashboard_artifact_preview(config_path: Path, *, artifact_path: str) -> dict[str, Any]:
    base = _config_base(config_path)
    resolved = _resolve_preview_path(artifact_path, base=base)
    if isinstance(resolved, dict):
        return resolved

    path, safe_path = resolved
    if not path.exists():
        return _artifact_preview_error(safe_path, "missing", f"{safe_path} was not found.")
    if not path.is_file():
        return _artifact_preview_error(safe_path, "unsupported", f"{safe_path} is not a file.")
    suffix = path.suffix.lower()
    if suffix in {".sqlite", ".db", ".parquet", ".arrow", ".feather"}:
        return _artifact_preview_error(
            safe_path,
            "unsupported",
            f"{suffix} previews are not expanded by the dashboard artifact preview API.",
        )
    if suffix == ".json":
        return _json_preview(path, safe_path)
    if suffix == ".jsonl":
        return _jsonl_preview(path, safe_path)
    if suffix in {".md", ".markdown"}:
        return _text_preview(path, safe_path, preview_kind="markdown")
    if suffix in {".txt", ".log", ".csv", ".yaml", ".yml"}:
        return _text_preview(path, safe_path, preview_kind="text")
    return _artifact_preview_error(
        safe_path,
        "unsupported",
        f"{suffix or 'unknown'} files are not supported by the dashboard artifact preview API.",
    )


def validate_dashboard_host(host: str) -> None:
    if host not in LOCAL_DASHBOARD_HOSTS:
        supported = ", ".join(sorted(LOCAL_DASHBOARD_HOSTS))
        raise DashboardError(f"dashboard host must be local-only. Supported hosts: {supported}.")


def validate_dashboard_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise DashboardError("dashboard port must be between 1 and 65535.")


def dashboard_config_ref(config_path: Path) -> str:
    path = Path(config_path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return "<external-config>"


def sanitize_dashboard_message(message: str, *, config_path: Path) -> str:
    safe_ref = dashboard_config_ref(config_path)
    variants = {str(config_path), config_path.as_posix()}
    try:
        variants.add(str(config_path.resolve()))
        variants.add(config_path.resolve().as_posix())
    except OSError:
        pass

    sanitized = message
    for value in sorted(variants, key=len, reverse=True):
        if value:
            sanitized = sanitized.replace(value, safe_ref)
    return sanitized


def _latest_run_section(
    config_path: Path,
    *,
    base: Path,
) -> tuple[dict[str, Any], Path | None, dict[str, Any]]:
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return (
            _section(
                "latest_run",
                "missing",
                source_artifacts=[RUN_INDEX_ARTIFACT],
                warnings=["local run index was not found."],
            ),
            None,
            {},
        )
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            row = _latest_run_row(connection)
    except sqlite3.Error as exc:
        return (
            _section(
                "latest_run",
                "failed",
                source_artifacts=[RUN_INDEX_ARTIFACT],
                errors=[f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
            ),
            None,
            {},
        )
    if row is None:
        return (
            _section(
                "latest_run",
                "missing",
                source_artifacts=[RUN_INDEX_ARTIFACT],
                warnings=["local run index does not contain a latest run."],
            ),
            None,
            {},
        )

    run_id, run_dir_ref, manifest_ref = row
    run_dir = _resolve_ref(run_dir_ref, base=base)
    manifest_path = _resolve_ref(manifest_ref, base=base)
    manifest, error = _read_json(manifest_path)
    if error:
        return (
            _section(
                "latest_run",
                "failed",
                fields={
                    "run_id": run_id,
                    "run_dir": _safe_ref(run_dir, base=base),
                    "manifest": _safe_ref(manifest_path, base=base),
                },
                source_artifacts=[RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
                errors=[error],
            ),
            run_dir,
            {},
        )

    fields = {
        "run_id": str(manifest.get("run_id") or run_id),
        "run_dir": _safe_ref(run_dir, base=base),
        "manifest": _safe_ref(manifest_path, base=base),
        "run_status": str(manifest.get("status") or "unknown"),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "codex_status": _dict(manifest.get("codex")).get("status"),
        "stage_counts": _stage_counts(manifest),
        "warning_count": _warning_count(manifest),
        "error_count": _error_count(manifest),
        "report": _report_state(run_dir, manifest),
    }
    return (
        _section(
            "latest_run",
            "available",
            fields=fields,
            source_artifacts=[RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
        ),
        run_dir,
        manifest,
    )


def _latest_run_row(connection: sqlite3.Connection) -> tuple[str, str, str] | None:
    for key in ("latest_successful_run", "latest_run"):
        row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
        if not row or not isinstance(row[0], str) or not row[0]:
            continue
        run = connection.execute(
            "SELECT run_id, run_dir, manifest_path FROM runs WHERE run_id = ?",
            (row[0],),
        ).fetchone()
        if run and all(isinstance(value, str) and value for value in run):
            return run[0], run[1], run[2]
    return None


def _run_artifact_index(connection: sqlite3.Connection) -> dict[str, dict[str, list[str]]]:
    rows = connection.execute(
        "SELECT run_id, artifact_key, path FROM run_artifacts ORDER BY run_id, artifact_key, path"
    ).fetchall()
    artifacts: dict[str, dict[str, list[str]]] = {}
    for run_id, key, path in rows:
        if not isinstance(run_id, str) or not isinstance(key, str) or not isinstance(path, str):
            continue
        artifacts.setdefault(run_id, {}).setdefault(key, []).append(path)
    return artifacts


def _resolve_preview_path(artifact_path: str, *, base: Path) -> tuple[Path, str] | dict[str, Any]:
    if not artifact_path or not artifact_path.strip():
        return _artifact_preview_error("", "rejected", "artifact path is required.")
    raw_path = artifact_path.replace("\\", "/").strip()
    path = Path(raw_path)
    if path.is_absolute():
        return _artifact_preview_error(raw_path, "rejected", "artifact path must be repo-relative.")
    parts = path.parts
    if any(part in {"", ".", ".."} for part in parts):
        return _artifact_preview_error(raw_path, "rejected", "artifact path must not contain traversal segments.")
    if not parts or parts[0] not in {"runs", "data"}:
        return _artifact_preview_error(raw_path, "rejected", "artifact path must start with runs/ or data/.")
    resolved = (base / path).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return _artifact_preview_error(raw_path, "rejected", "artifact path must stay under the configured project root.")
    return resolved, path.as_posix()


def _json_preview(path: Path, safe_path: str) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    if truncated:
        return _artifact_preview_payload(
            safe_path,
            "json",
            text,
            truncated=True,
            warnings=["JSON file was truncated before parsing."],
        )
    try:
        loaded = json.loads(text)
    except JSONDecodeError as exc:
        return _artifact_preview_error(safe_path, "failed", f"{safe_path} is not valid JSON: {exc.msg}.")
    preview, omitted = _bounded_json(loaded)
    return _artifact_preview_payload(
        safe_path,
        "json",
        preview,
        truncated=False,
        omitted=omitted,
    )


def _jsonl_preview(path: Path, safe_path: str) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    records: list[Any] = []
    parse_errors: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines[:MAX_PREVIEW_ROWS]):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except JSONDecodeError as exc:
            parse_errors.append(f"line {index + 1}: {exc.msg}")
            records.append(line)
    omitted_rows = max(0, len(lines) - MAX_PREVIEW_ROWS)
    warnings = []
    if truncated:
        warnings.append("JSONL file was truncated.")
    if parse_errors:
        warnings.append(f"{len(parse_errors)} JSONL line(s) could not be parsed.")
    return _artifact_preview_payload(
        safe_path,
        "jsonl",
        records,
        truncated=truncated or omitted_rows > 0,
        omitted={"rows": omitted_rows, "parse_errors": len(parse_errors)},
        warnings=warnings,
    )


def _text_preview(path: Path, safe_path: str, *, preview_kind: str) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    return _artifact_preview_payload(safe_path, preview_kind, text, truncated=truncated)


def _read_bounded_text(path: Path) -> tuple[str, bool, str | None]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            text = handle.read(MAX_PREVIEW_CHARS + 1)
    except UnicodeDecodeError:
        return "", False, f"{path.name} is not valid UTF-8 text."
    except OSError as exc:
        return "", False, f"{path.name} could not be read: {exc}"
    truncated = len(text) > MAX_PREVIEW_CHARS
    return text[:MAX_PREVIEW_CHARS], truncated, None


def _bounded_json(value: Any) -> tuple[Any, dict[str, int]]:
    omitted: dict[str, int] = {}
    if isinstance(value, list):
        omitted_count = max(0, len(value) - MAX_PREVIEW_ROWS)
        if omitted_count:
            omitted["items"] = omitted_count
        return value[:MAX_PREVIEW_ROWS], omitted
    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        for key, item in sorted(value.items()):
            if isinstance(item, list):
                preview[str(key)] = item[:MAX_PREVIEW_ROWS]
                omitted_count = max(0, len(item) - MAX_PREVIEW_ROWS)
                if omitted_count:
                    omitted[f"{key}.items"] = omitted_count
            elif isinstance(item, dict):
                preview[str(key)] = _bounded_mapping(item)
            elif isinstance(item, (str, int, float, bool)) or item is None:
                preview[str(key)] = item
            else:
                preview[str(key)] = str(item)
        return preview, omitted
    return value, omitted


def _artifact_preview_payload(
    path: str,
    preview_kind: str,
    preview: Any,
    *,
    truncated: bool,
    omitted: dict[str, int] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_artifact_preview",
        "status": "available",
        "path": path,
        "kind": preview_kind,
        "truncated": truncated,
        "omitted": omitted or {},
        "preview": preview,
        "warnings": warnings or [],
        "errors": [],
    }


def _artifact_preview_error(path: str, status: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_artifact_preview",
        "status": status,
        "path": path,
        "kind": "unknown",
        "truncated": False,
        "omitted": {},
        "preview": None,
        "warnings": [message] if status in {"missing", "rejected", "unsupported"} else [],
        "errors": [message] if status == "failed" else [],
    }


def _run_list_record(row: Any, artifacts: dict[str, list[str]], *, base: Path) -> dict[str, Any]:
    run_id = str(row[0])
    run_dir = _resolve_ref(str(row[1]), base=base)
    manifest_path = _resolve_ref(str(row[9]), base=base)
    report_paths = artifacts.get("report", [])
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
        "report": report_paths[0] if report_paths else None,
    }


def _run_detail_missing(run_id: str, *, warning: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_detail",
        "status": "missing",
        "run_id": run_id,
        "source_artifacts": [RUN_INDEX_ARTIFACT],
        "fields": {},
        "stages": [],
        "artifacts": [],
        "warnings": [warning],
        "errors": [],
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
    if artifact is None:
        return _section(name, "missing", warnings=[f"{artifact_key} artifact is not recorded."])
    path = run_dir / artifact
    data, error = _read_json(path)
    if error:
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


def _workbench_section(*, base: Path) -> dict[str, Any]:
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
    fields = {
        "artifact": WORKBENCH_SUMMARY_ARTIFACT,
        "artifact_type": data.get("artifact_type"),
        "artifact_status": summary_status,
        "generated_at": data.get("generated_at"),
        "latest_run": _bounded_mapping(_dict(data.get("latest_run")).get("fields")),
        "warnings": len(_list(data.get("warnings"))),
        "errors": len(_list(data.get("errors"))),
    }
    return _section(
        "workbench",
        _normalize_section_status(summary_status),
        fields=fields,
        source_artifacts=[WORKBENCH_SUMMARY_ARTIFACT],
        warnings=_string_list(data.get("warnings")),
        errors=_string_list(data.get("errors")),
    )


def _section(
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


def _resolve_ref(value: str, *, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def _safe_ref(path: Path, *, base: Path) -> str:
    if path.is_absolute():
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            return path.name
    return path.as_posix()


def _config_base(config_path: Path) -> Path:
    parent = config_path.parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


def _artifact_ref(manifest: dict[str, Any], key: str, default: str) -> str | None:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        value = artifacts.get(key)
        if isinstance(value, str) and value:
            return value
    return default if manifest else None


def _report_state(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    report = _artifact_ref(manifest, "report", "report/report.md")
    codex_status = _dict(manifest.get("codex")).get("status")
    if report and (run_dir / report).exists():
        return {"status": "available", "artifact": report}
    if codex_status in {"skipped", "disabled", "not_run"}:
        return {"status": str(codex_status), "artifact": report}
    return {"status": "missing", "artifact": report}


def _stage_counts(manifest: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for stage in _list(manifest.get("stages")):
        if not isinstance(stage, dict):
            continue
        status = str(stage.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _stage_timeline(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for index, stage in enumerate(_list(manifest.get("stages"))):
        if not isinstance(stage, dict):
            continue
        error = _dict(stage.get("error"))
        record = {
            "index": index,
            "name": stage.get("name"),
            "status": stage.get("status"),
            "started_at": stage.get("started_at"),
            "finished_at": stage.get("finished_at"),
            "artifact_count": len(_list(stage.get("artifacts"))),
            "warning_count": _warning_count(stage),
            "error_count": 1 if error else 0,
        }
        reason = stage.get("reason")
        if isinstance(reason, str) and reason:
            record["reason"] = reason
        if error:
            record["error"] = _bounded_mapping(error)
        timeline.append(record)
    return timeline


def _manifest_artifacts(manifest: dict[str, Any]) -> list[dict[str, str]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    records: list[dict[str, str]] = []
    for key, value in sorted(artifacts.items()):
        for path in _artifact_paths(value):
            records.append({"key": str(key), "path": path, "kind": _artifact_kind(path)})
    return records


def _artifact_paths(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str) and item]
    if isinstance(value, dict):
        paths: list[str] = []
        for item in value.values():
            paths.extend(_artifact_paths(item))
        return sorted(set(paths))
    return []


def _artifact_kind(path: str) -> str:
    if path.startswith("raw/"):
        return "raw"
    if path.startswith("analysis/"):
        return "analysis"
    if path.startswith("codex_context/"):
        return "codex_context"
    if path.startswith("report/"):
        return "report"
    if path.startswith("data/"):
        return "data"
    if path.startswith("runs/monitor/"):
        return "monitor"
    if path.startswith("runs/workbench/"):
        return "workbench"
    return "other"


def _manifest_error_messages(manifest: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for error in _list(manifest.get("errors")):
        if isinstance(error, dict):
            message = error.get("message")
            stage = error.get("stage")
            if stage and message:
                messages.append(f"{stage}: {message}")
            elif message:
                messages.append(str(message))
        elif isinstance(error, str):
            messages.append(error)
    return messages


def _check_counts(checks: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _overall_status(statuses: list[str]) -> str:
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "degraded" for status in statuses):
        return "degraded"
    if any(status in {"missing", "partial", "skipped", "unknown"} for status in statuses):
        return "partial"
    if any(status == "warning" for status in statuses):
        return "warning"
    return "available"


def _normalize_section_status(status: str) -> str:
    normalized = status.lower()
    if normalized in {"ok", "available", "succeeded", "success"}:
        return "available"
    if normalized in {"warning", "degraded", "failed", "partial", "missing", "skipped"}:
        return normalized
    return "unknown"


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bounded: dict[str, Any] = {}
    for key, item in sorted(value.items()):
        if isinstance(item, (str, int, float, bool)) or item is None:
            bounded[str(key)] = item
    return bounded


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _list(value)]


def _warning_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("warnings")))


def _error_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("errors")))
