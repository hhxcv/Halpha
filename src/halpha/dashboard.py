from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .data_inspection import DataInspectionError, inspect_local_store_state
from .dashboard_artifact_preview import dashboard_artifact_preview
from .dashboard_assets import dashboard_asset_media_type, dashboard_asset_text
from .dashboard_data_cleanup import (
    MAX_DELETION_RUN_ITEMS,
    dashboard_data_deletion_plan as build_dashboard_data_deletion_plan,
    dashboard_delete_data as execute_dashboard_delete_data,
)
from .dashboard_jobs import DashboardJobManager
from .dashboard_monitor import dashboard_monitor_alerts, dashboard_monitor_cycles, dashboard_monitor_summary
from .dashboard_run_aggregation import manifest_report_state, run_list_record as _run_list_record
from .dashboard_schedule import DashboardScheduleManager
from .dashboard_settings import (
    dashboard_backup_config,
    dashboard_config_profile,
    dashboard_config_ref,
    dashboard_save_config_profile,
    sanitize_dashboard_message,
)
from .dashboard_strategy import dashboard_strategy_research
from .dashboard_ui import dashboard_index_html
from .monitoring import MONITOR_HEALTH_STATE_FILENAME, load_monitor_config
from .outcome_history import OUTCOME_HISTORY_ARTIFACT, OUTCOME_HISTORY_STATE_ARTIFACT
from .run_index import RUN_INDEX_ARTIFACT, run_index_path
from .storage import (
    config_base as _config_base,
    read_json_object,
    resolve_local_ref,
    safe_local_ref,
)
from .value_helpers import (
    as_dict as _dict,
    as_list as _list,
    strict_int as _int,
    stringified_list as _string_list,
)
from .workbench import DEFAULT_WORKBENCH_OUTPUT_DIR, WORKBENCH_SUMMARY_FILENAME


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
DEFAULT_DASHBOARD_DISPLAY_TIMEZONE = "Asia/Shanghai"
LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REJECTED_EXTERNAL_REF_NAME = ".halpha_external_ref_rejected"
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}
MAX_STAGE_ARTIFACT_REFS = 20
MAX_STORE_DRILLDOWN_ITEMS = 12
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
PRODUCT_CONTRACT_VALIDATION_ARTIFACT = "analysis/product_contract_validation.json"
ARTIFACT_PRODUCER_STAGES = {
    "data_quality_summary": "build_data_quality_summary",
    "product_contract_validation": "validate_product_contracts",
}
NON_PRODUCED_STAGE_STATUSES = {"disabled", "not_run", "skipped"}
WORKBENCH_SUMMARY_ARTIFACT = f"{DEFAULT_WORKBENCH_OUTPUT_DIR}/{WORKBENCH_SUMMARY_FILENAME}"
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
DATA_STORE_SECTION_NAMES = {
    "research_data_catalog",
    "run_index",
    "text_event_history",
    "ohlcv_history",
    "derivatives_market_history",
    "macro_calendar_history",
    "onchain_flow_history",
}
DATA_STORE_TITLES = {
    "research_data_catalog": "Research data catalog",
    "run_index": "Run index",
    "text_event_history": "Text event history",
    "ohlcv_history": "OHLCV history",
    "derivatives_market_history": "Derivatives market history",
    "macro_calendar_history": "Macro/calendar history",
    "onchain_flow_history": "On-chain flow history",
    "outcome_history": "Outcome history",
}
SAFE_METADATA_PREVIEW_SUFFIXES = {".json", ".md", ".markdown", ".txt", ".yaml", ".yml"}


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
        from fastapi import Body, FastAPI, Response
        from fastapi.responses import HTMLResponse
    except ModuleNotFoundError as exc:
        raise DashboardError("FastAPI is required to run the dashboard.") from exc

    validate_dashboard_host(host)
    validate_dashboard_port(port)
    app = FastAPI(title="Halpha Dashboard", version="0.0.0")
    health = dashboard_health(config, config_path=config_path, host=host, port=port)
    job_manager = DashboardJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)

    @app.middleware("http")
    async def no_store_dashboard_responses(_request: Any, call_next: Any) -> Any:
        response = await call_next(_request)
        for key, value in NO_STORE_HEADERS.items():
            response.headers[key] = value
        return response

    @app.get("/", response_class=HTMLResponse)
    def root() -> HTMLResponse:
        return HTMLResponse(
            dashboard_index_html(display_timezone=dashboard_display_timezone(config)),
            headers=NO_STORE_HEADERS,
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/assets/{asset_name}", include_in_schema=False)
    def dashboard_asset(asset_name: str) -> Response:
        media_type = dashboard_asset_media_type(asset_name)
        if media_type is None:
            return Response(status_code=404)
        return Response(dashboard_asset_text(asset_name), media_type=media_type, headers=NO_STORE_HEADERS)

    @app.get("/api/health")
    def health_endpoint() -> dict[str, Any]:
        return health

    @app.get("/api/config/profile")
    def config_profile_endpoint() -> dict[str, Any]:
        return dashboard_config_profile(config, config_path=config_path)

    @app.post("/api/config/profile")
    def config_profile_save_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return dashboard_save_config_profile(config, config_path=config_path, request=request)

    @app.post("/api/config/profile/backup")
    def config_profile_backup_endpoint() -> dict[str, Any]:
        return dashboard_backup_config(config_path=config_path)

    @app.get("/api/overview")
    def overview_endpoint() -> dict[str, Any]:
        return dashboard_overview(config, config_path=config_path)

    @app.get("/api/text-intelligence")
    def text_intelligence_endpoint(run_id: str | None = None) -> dict[str, Any]:
        return dashboard_text_intelligence(config_path=config_path, run_id=run_id)

    @app.get("/api/runs")
    def runs_endpoint() -> dict[str, Any]:
        return dashboard_runs(config_path=config_path)

    @app.get("/api/runs/{run_id}")
    def run_detail_endpoint(run_id: str) -> dict[str, Any]:
        return dashboard_run_detail(config_path=config_path, run_id=run_id)

    @app.get("/api/artifacts/preview")
    def artifact_preview_endpoint(path: str) -> dict[str, Any]:
        return dashboard_artifact_preview(config, config_path=config_path, artifact_path=path)

    @app.get("/api/data/stores")
    def data_stores_endpoint() -> dict[str, Any]:
        return dashboard_data_stores(config, config_path=config_path)

    @app.get("/api/data/deletion")
    def data_deletion_plan_endpoint() -> dict[str, Any]:
        return dashboard_data_deletion_plan(config, config_path=config_path)

    @app.post("/api/data/deletion")
    def data_deletion_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return dashboard_delete_data(config, config_path=config_path, request=request)

    @app.get("/api/strategies")
    def strategies_endpoint(run_id: str | None = None) -> dict[str, Any]:
        return dashboard_strategy_research(config, config_path=config_path, run_id=run_id)

    @app.get("/api/monitor")
    def monitor_endpoint() -> dict[str, Any]:
        return dashboard_monitor_summary(config, config_path=config_path)

    @app.get("/api/monitor/cycles")
    def monitor_cycles_endpoint() -> dict[str, Any]:
        return dashboard_monitor_cycles(config, config_path=config_path)

    @app.get("/api/monitor/alerts")
    def monitor_alerts_endpoint() -> dict[str, Any]:
        return dashboard_monitor_alerts(config, config_path=config_path)

    @app.get("/api/jobs")
    def jobs_endpoint() -> dict[str, Any]:
        return job_manager.list_jobs()

    @app.post("/api/jobs")
    def create_job_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return job_manager.create_job(request)

    @app.get("/api/jobs/{job_id}")
    def job_detail_endpoint(job_id: str) -> dict[str, Any]:
        job = job_manager.get_job(job_id)
        if job is None:
            return {
                "schema_version": 1,
                "artifact_type": "dashboard_job",
                "job_id": job_id,
                "status": "missing",
                "warnings": ["dashboard job was not found."],
                "errors": [],
            }
        return job

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job_endpoint(job_id: str) -> dict[str, Any]:
        return job_manager.cancel_job(job_id)

    @app.get("/api/schedule/daily-report")
    def daily_report_schedule_endpoint() -> dict[str, Any]:
        return schedule_manager.read_daily_report_schedule()

    @app.post("/api/schedule/daily-report")
    def update_daily_report_schedule_endpoint(
        request: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        return schedule_manager.update_daily_report_schedule(request or {})

    @app.post("/api/schedule/daily-report/enable")
    def enable_daily_report_schedule_endpoint(
        request: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        return schedule_manager.enable_daily_report_schedule(request or {})

    @app.post("/api/schedule/daily-report/disable")
    def disable_daily_report_schedule_endpoint() -> dict[str, Any]:
        return schedule_manager.disable_daily_report_schedule()

    @app.post("/api/schedule/daily-report/trigger")
    def trigger_daily_report_schedule_endpoint(
        request: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        return schedule_manager.trigger_daily_report_schedule(request or {})

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
            "overview_api": "available",
            "run_history_api": "available",
            "artifact_preview_api": "available",
            "data_store_api": "available",
            "data_deletion_api": "available",
            "config_profile_api": "available",
            "strategy_research_api": "available",
            "monitor_api": "available",
            "text_intelligence_api": "available",
            "schedule_api": "available",
            "job_runner": "available",
            "frontend_ui": "available",
        },
    }


def dashboard_display_timezone(config: dict[str, Any]) -> str:
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    candidates = (dashboard.get("display_timezone"), run.get("timezone"), DEFAULT_DASHBOARD_DISPLAY_TIMEZONE)
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        timezone_name = candidate.strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            continue
        return timezone_name
    return DEFAULT_DASHBOARD_DISPLAY_TIMEZONE


def dashboard_overview(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _config_base(config_path)
    latest_run, run_dir, manifest = _latest_run_section(config_path, base=base)
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
    base = _config_base(config_path)
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


def dashboard_runs(config_path: Path, *, limit: int = 100) -> dict[str, Any]:
    base = _config_base(config_path)
    index_path = run_index_path(config_path)
    empty_latest = {"latest_run_id": None, "latest_successful_run_id": None}
    if not index_path.exists():
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_list",
            "status": "missing",
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "latest": empty_latest,
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
            latest = _run_latest_refs(connection)
    except sqlite3.Error as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_list",
            "status": "failed",
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "latest": empty_latest,
            "runs": [],
            "warnings": [],
            "errors": [f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
        }
    runs = [_run_list_record(row, artifacts.get(str(row[0]), {}), base=base, latest=latest) for row in rows]
    missing_report_diagnostics = [
        {
            "run_id": run["run_id"],
            "status": run["report_state"]["status"],
            "artifact": run["report_state"].get("artifact"),
        }
        for run in runs
        if _dict(run.get("report_state")).get("status") == "missing"
        and _dict(run.get("report_state")).get("artifact")
    ]
    report_diagnostics = missing_report_diagnostics[:20]
    missing_index_diagnostics = [
        {
            "run_id": run["run_id"],
            "status": run["integrity_state"]["status"],
            "missing": run["integrity_state"].get("missing", []),
            "run_dir": run["integrity_state"].get("run_dir"),
            "manifest": run["integrity_state"].get("manifest"),
        }
        for run in runs
        if _dict(run.get("integrity_state")).get("status") != "available"
    ]
    index_diagnostics = missing_index_diagnostics[:20]
    warnings: list[str] = []
    if missing_index_diagnostics:
        warnings.append(f"{len(missing_index_diagnostics)} run index row(s) reference missing run artifacts.")
    if missing_report_diagnostics:
        warnings.append(
            f"{len(missing_report_diagnostics)} recorded report artifact(s) were missing and omitted from report lists."
        )
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_list",
        "status": "partial" if missing_index_diagnostics else "available",
        "source_artifacts": [RUN_INDEX_ARTIFACT],
        "latest": latest,
        "runs": runs,
        "index_diagnostics": index_diagnostics,
        "report_diagnostics": report_diagnostics,
        "warnings": warnings,
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
            latest = _run_latest_refs(connection)
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

    run = _run_list_record(row, {}, base=base, latest=latest)
    run_dir = _resolve_ref(str(row[1]), base=base)
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

    report_state = _report_state(run_dir, manifest)
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_detail",
        "status": "available",
        "run_id": run_id,
        "source_artifacts": [RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
        "fields": {
            **run,
            "report": report_state.get("artifact") if report_state.get("status") == "available" else None,
            "report_state": report_state,
            "manifest_status": str(manifest.get("status") or "unknown"),
            "codex": _bounded_mapping(manifest.get("codex")),
            "counts": _bounded_mapping(manifest.get("counts")),
        },
        "stages": _stage_timeline(manifest),
        "artifacts": _manifest_artifacts(manifest),
        "warnings": _string_list(manifest.get("warnings")),
        "errors": _manifest_error_messages(manifest),
    }


def dashboard_data_stores(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    try:
        state = inspect_local_store_state(config, config_path=config_path)
    except DataInspectionError as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_data_stores",
            "status": "failed",
            "source_artifacts": [],
            "stores": [],
            "warnings": [],
            "errors": [str(exc)],
            "omitted": _data_store_omissions(),
        }

    sections = [
        _dashboard_store_section(section, config_path=config_path)
        for section in _list(state.get("sections"))
        if isinstance(section, dict) and section.get("name") in DATA_STORE_SECTION_NAMES
    ]
    sections.append(_outcome_history_store_section(config_path))
    statuses = [str(section.get("status") or "unknown") for section in sections]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_data_stores",
        "status": _dashboard_store_overall_status(statuses),
        "state_scope": "shared_reusable_stores",
        "run_snapshot_scope": "not_included",
        "source_artifacts": sorted(
            {
                artifact
                for section in sections
                for artifact in _string_list(section.get("source_artifacts"))
            }
        ),
        "stores": sections,
        "warnings": [],
        "errors": [],
        "omitted": _data_store_omissions(),
    }


def dashboard_data_deletion_plan(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    runs_payload = dashboard_runs(config_path=config_path, limit=MAX_DELETION_RUN_ITEMS)
    stores_payload = dashboard_data_stores(config, config_path=config_path)
    return build_dashboard_data_deletion_plan(
        config,
        config_path=config_path,
        runs_payload=runs_payload,
        stores_payload=stores_payload,
    )


def dashboard_delete_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    runs_payload = dashboard_runs(config_path=config_path, limit=MAX_DELETION_RUN_ITEMS)
    stores_payload = dashboard_data_stores(config, config_path=config_path)
    return execute_dashboard_delete_data(
        config,
        config_path=config_path,
        request=request,
        runs_payload=runs_payload,
        stores_payload=stores_payload,
    )


def validate_dashboard_host(host: str) -> None:
    if host not in LOCAL_DASHBOARD_HOSTS:
        supported = ", ".join(sorted(LOCAL_DASHBOARD_HOSTS))
        raise DashboardError(f"dashboard host must be local-only. Supported hosts: {supported}.")


def validate_dashboard_port(port: int) -> None:
    if port < 1 or port > 65535:
        raise DashboardError("dashboard port must be between 1 and 65535.")


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
            latest = _run_latest_refs(connection)
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

    selection_key, run_id, run_dir_ref, manifest_ref = row
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
        "selection": {
            "key": selection_key,
            "label": _latest_selection_label(selection_key),
            "latest_run_id": latest.get("latest_run_id"),
            "latest_successful_run_id": latest.get("latest_successful_run_id"),
        },
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


def _latest_run_row(connection: sqlite3.Connection) -> tuple[str, str, str, str] | None:
    for key in ("latest_successful_run", "latest_run"):
        row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
        if not row or not isinstance(row[0], str) or not row[0]:
            continue
        run = connection.execute(
            "SELECT run_id, run_dir, manifest_path FROM runs WHERE run_id = ?",
            (row[0],),
        ).fetchone()
        if run and all(isinstance(value, str) and value for value in run):
            return key, run[0], run[1], run[2]
    fallback = _fallback_latest_run(connection, succeeded_only=True)
    if fallback:
        return ("fallback_latest_successful_run", *fallback)
    fallback = _fallback_latest_run(connection, succeeded_only=False)
    if fallback:
        return ("fallback_latest_run", *fallback)
    return None


def _run_latest_refs(connection: sqlite3.Connection) -> dict[str, str | None]:
    refs: dict[str, str | None] = {"latest_run_id": None, "latest_successful_run_id": None}
    rows = connection.execute(
        "SELECT key, run_id FROM run_latest WHERE key IN (?, ?)",
        ("latest_run", "latest_successful_run"),
    ).fetchall()
    for key, run_id in rows:
        if not isinstance(run_id, str) or not run_id:
            continue
        if key == "latest_run":
            refs["latest_run_id"] = run_id
        elif key == "latest_successful_run":
            refs["latest_successful_run_id"] = run_id
    return refs


def _latest_selection_label(selection_key: str) -> str:
    labels = {
        "latest_successful_run": "latest successful run",
        "latest_run": "latest indexed run",
        "fallback_latest_successful_run": "fallback latest successful run",
        "fallback_latest_run": "fallback latest indexed run",
    }
    return labels.get(selection_key, selection_key)


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


def _dashboard_store_section(section: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    artifact = section.get("artifact")
    reason = section.get("reason")
    name = str(section.get("name") or "unknown")
    fields = _bounded_mapping(section.get("fields"))
    extra = _bounded_mapping(section.get("extra"))
    source_artifacts = [artifact] if isinstance(artifact, str) and artifact else []
    warnings = [reason] if isinstance(reason, str) and reason else []
    scope = _data_store_scope(name)
    return {
        "name": name,
        "title": DATA_STORE_TITLES.get(name, str(section.get("name") or "Unknown")),
        **scope,
        "status": str(section.get("status") or "unknown"),
        "artifact": artifact if isinstance(artifact, str) else None,
        "preview_path": _metadata_preview_path(artifact),
        "fields": fields,
        "extra": extra,
        "drilldown": _data_store_drilldown(
            name,
            artifact if isinstance(artifact, str) else None,
            fields=fields,
            extra=extra,
            config_path=config_path,
            warnings=warnings,
        ),
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "errors": [],
    }


def _outcome_history_store_section(config_path: Path) -> dict[str, Any]:
    base = _config_base(config_path)
    path = base / OUTCOME_HISTORY_STATE_ARTIFACT
    data, error = _read_json(path)
    if error:
        return {
            "name": "outcome_history",
            "title": DATA_STORE_TITLES["outcome_history"],
            **_data_store_scope("outcome_history"),
            "status": "skipped",
            "artifact": OUTCOME_HISTORY_STATE_ARTIFACT,
            "preview_path": None,
        "fields": {
            "history": OUTCOME_HISTORY_ARTIFACT,
        },
        "extra": {},
        "drilldown": _empty_data_store_drilldown(
            "outcome_history",
            metadata_refs=[OUTCOME_HISTORY_STATE_ARTIFACT],
            warnings=[error],
        ),
        "source_artifacts": [OUTCOME_HISTORY_STATE_ARTIFACT],
        "warnings": [error],
        "errors": [],
        }
    totals = _dict(data.get("totals"))
    fields = {
        "updated_at": data.get("updated_at"),
        "records": _int(totals.get("records")),
        "incoming_records": _int(totals.get("incoming_records")),
        "inserted_records": _int(totals.get("inserted_records")),
        "updated_records": _int(totals.get("updated_records")),
        "duplicate_records": _int(totals.get("duplicate_records")),
        "conflicting_duplicates": _int(totals.get("conflicting_duplicates")),
        "warnings": _int(totals.get("warning_count")),
        "errors": _int(totals.get("error_count")),
        "history": data.get("history_path") or OUTCOME_HISTORY_ARTIFACT,
        "storage_path": data.get("storage_path"),
    }
    return {
        "name": "outcome_history",
        "title": DATA_STORE_TITLES["outcome_history"],
        **_data_store_scope("outcome_history"),
        "status": str(data.get("status") or "unknown"),
        "artifact": OUTCOME_HISTORY_STATE_ARTIFACT,
        "preview_path": OUTCOME_HISTORY_STATE_ARTIFACT,
        "fields": _bounded_mapping(fields),
        "extra": {},
        "drilldown": _data_store_drilldown_from_metadata(
            "outcome_history",
            data,
            fields=_bounded_mapping(fields),
            metadata_refs=[OUTCOME_HISTORY_STATE_ARTIFACT],
            warnings=_string_list(data.get("warnings")),
        ),
        "source_artifacts": [OUTCOME_HISTORY_STATE_ARTIFACT, *_string_list(data.get("source_artifacts"))],
        "warnings": _string_list(data.get("warnings")),
        "errors": _string_list(data.get("errors")),
    }


def _data_store_scope(name: str) -> dict[str, Any]:
    if name == "run_index":
        return {
            "state_scope": "local_run_index",
            "source_label": "Local run index",
            "run_snapshot": False,
        }
    return {
        "state_scope": "shared_reusable_store",
        "source_label": "Shared reusable store",
        "run_snapshot": False,
    }


def _data_store_drilldown(
    name: str,
    artifact: str | None,
    *,
    fields: dict[str, Any],
    extra: dict[str, Any],
    config_path: Path,
    warnings: list[str],
) -> dict[str, Any]:
    del extra
    if not artifact:
        return _empty_data_store_drilldown(name, warnings=warnings)
    preview_path = _metadata_preview_path(artifact)
    if not preview_path:
        return _data_store_drilldown_from_metadata(
            name,
            {},
            fields=fields,
            metadata_refs=[artifact],
            warnings=warnings,
        )
    data, error = _read_json(_config_base(config_path) / preview_path)
    read_warnings = [*warnings]
    if error:
        read_warnings.append(error)
        data = {}
    else:
        read_warnings.extend(_string_list(data.get("warnings")))
        read_warnings.extend(_string_list(data.get("errors")))
    return _data_store_drilldown_from_metadata(
        name,
        data,
        fields=fields,
        metadata_refs=[preview_path],
        warnings=read_warnings,
    )


def _empty_data_store_drilldown(
    name: str,
    *,
    metadata_refs: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "category": _data_store_category(name),
        "summary": {},
        "dimensions": {},
        "ranges": {},
        "groups": [],
        "metadata_refs": metadata_refs or [],
        "warnings": warnings or [],
        "omitted": {
            "full_history_records_embedded": False,
            "sqlite_table_contents_embedded": False,
            "group_records_omitted": 0,
        },
    }


def _data_store_drilldown_from_metadata(
    name: str,
    data: dict[str, Any],
    *,
    fields: dict[str, Any],
    metadata_refs: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    groups = _data_store_groups(name, data)
    full_group_count = len(groups)
    return {
        "category": _data_store_category(name),
        "summary": _data_store_summary(fields, data),
        "dimensions": _data_store_dimensions(name, data),
        "ranges": _data_store_ranges(data),
        "groups": groups[:MAX_STORE_DRILLDOWN_ITEMS],
        "metadata_refs": metadata_refs,
        "warnings": warnings,
        "omitted": {
            "full_history_records_embedded": False,
            "sqlite_table_contents_embedded": False,
            "group_records_omitted": max(0, full_group_count - MAX_STORE_DRILLDOWN_ITEMS),
        },
    }


def _data_store_category(name: str) -> str:
    if "ohlcv" in name:
        return "market"
    if "derivatives" in name:
        return "derivatives"
    if "macro" in name:
        return "macro_calendar"
    if "onchain" in name:
        return "onchain"
    if "text" in name:
        return "text"
    if "outcome" in name:
        return "outcome"
    return "system"


def _data_store_summary(fields: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    totals = _dict(data.get("totals"))
    summary = {
        key: value
        for key, value in fields.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    for key in (
        "records",
        "incoming_records",
        "inserted_records",
        "updated_records",
        "duplicate_records",
        "conflicting_duplicates",
        "warning_count",
        "error_count",
    ):
        if key in totals and key not in summary:
            summary[key] = totals[key]
    if isinstance(data.get("updated_at"), str):
        summary.setdefault("updated_at", data["updated_at"])
    return _bounded_mapping(summary)


def _data_store_dimensions(name: str, data: dict[str, Any]) -> dict[str, Any]:
    records = _data_store_dimension_records(name, data)
    return _bounded_mapping(
        {
            "sources": _joined_unique(records, ("source", "source_name")),
            "symbols": _joined_unique(records, ("symbol",)),
            "timeframes": _joined_unique(records, ("timeframe",)),
            "metrics": _joined_unique(records, ("metric", "data_class")),
            "regions": _joined_unique(records, ("region",)),
            "assets": _joined_unique(records, ("asset",)),
            "chains": _joined_unique(records, ("chain", "network")),
            "statuses": _joined_unique(records, ("status",)),
            "stores": _joined_unique(records, ("name",)),
            "outcome_states": _joined_unique(records, ("value", "outcome_state")),
        }
    )


def _data_store_dimension_records(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    if name == "research_data_catalog":
        return [record for record in _list(data.get("stores")) if isinstance(record, dict)]
    if name == "ohlcv_history":
        return [record for record in _list(data.get("items")) if isinstance(record, dict)]
    if name == "text_event_history":
        return [record for record in _list(data.get("sources")) if isinstance(record, dict)]
    if name == "outcome_history":
        return [record for record in _list(data.get("outcome_states")) if isinstance(record, dict)]
    records = [record for record in _list(data.get("groups")) if isinstance(record, dict)]
    if records:
        return records
    return [record for record in _list(data.get("availability")) if isinstance(record, dict)]


def _data_store_groups(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    records = _data_store_dimension_records(name, data)
    return [_bounded_store_group(record) for record in records]


def _bounded_store_group(record: dict[str, Any]) -> dict[str, Any]:
    bounded: dict[str, Any] = {}
    preferred = (
        "name",
        "source",
        "source_name",
        "symbol",
        "timeframe",
        "metric",
        "data_class",
        "region",
        "asset",
        "chain",
        "network",
        "status",
        "value",
        "outcome_state",
        "row_count",
        "record_count",
        "records",
        "start",
        "end",
        "first_open_time",
        "last_open_time",
        "min_timestamp",
        "max_timestamp",
    )
    for key in preferred:
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            bounded[key] = value
    return _bounded_mapping(bounded)


def _data_store_ranges(data: dict[str, Any]) -> dict[str, Any]:
    ranges: dict[str, Any] = {}
    for key in (
        "updated_at",
        "first_open_time",
        "last_open_time",
        "min_timestamp",
        "max_timestamp",
        "start",
        "end",
        "range_start",
        "range_end",
    ):
        value = data.get(key)
        if isinstance(value, (str, int, float, bool)):
            ranges[key] = value
    return _bounded_mapping(ranges)


def _joined_unique(records: list[dict[str, Any]], keys: tuple[str, ...], *, limit: int = 8) -> str | None:
    values: list[str] = []
    for record in records:
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and value and value not in values:
                values.append(value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                text_value = str(value)
                if text_value not in values:
                    values.append(text_value)
    if not values:
        return None
    suffix = "" if len(values) <= limit else f", +{len(values) - limit} more"
    return ", ".join(sorted(values)[:limit]) + suffix


def _metadata_preview_path(artifact: Any) -> str | None:
    if not isinstance(artifact, str) or not artifact:
        return None
    if not (artifact.startswith("data/") or artifact.startswith("runs/")):
        return None
    suffix = Path(artifact).suffix.lower()
    if suffix not in SAFE_METADATA_PREVIEW_SUFFIXES:
        return None
    return artifact


def _data_store_omissions() -> dict[str, bool]:
    return {
        "full_research_catalog_embedded": False,
        "full_raw_histories_embedded": False,
        "full_reusable_histories_embedded": False,
        "sqlite_table_contents_embedded": False,
        "parquet_table_contents_embedded": False,
        "raw_local_user_state_embedded": False,
    }


def _dashboard_store_overall_status(statuses: list[str]) -> str:
    normalized = [status.lower() for status in statuses]
    if any(status == "failed" for status in normalized):
        return "failed"
    if any(status == "degraded" for status in normalized):
        return "degraded"
    if any(status == "warning" for status in normalized):
        return "warning"
    if any(status in {"ok", "available", "succeeded", "success"} for status in normalized):
        if any(status in {"skipped", "missing", "unknown"} for status in normalized):
            return "partial"
        return "available"
    return "partial"


def _fallback_latest_run(
    connection: sqlite3.Connection,
    *,
    succeeded_only: bool,
) -> tuple[str, str, str] | None:
    where = "WHERE status = 'succeeded'" if succeeded_only else ""
    row = connection.execute(
        f"""
        SELECT run_id, run_dir, manifest_path
        FROM runs
        {where}
        ORDER BY COALESCE(started_at, '') DESC, run_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row and all(isinstance(value, str) and value for value in row):
        return row[0], row[1], row[2]
    return None


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


def _dashboard_selected_run(config_path: Path, *, run_id: str | None) -> dict[str, Any]:
    base = _config_base(config_path)
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
    latest, _, _ = _latest_run_section(config_path, base=base)
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
    return read_json_object(path, external_ref_name=REJECTED_EXTERNAL_REF_NAME)


def _resolve_ref(value: str, *, base: Path) -> Path:
    return resolve_local_ref(value, base=base, rejected_name=REJECTED_EXTERNAL_REF_NAME)


def _safe_ref(path: Path, *, base: Path) -> str:
    return safe_local_ref(
        path,
        base=base,
        external_ref=EXTERNAL_ARTIFACT_REF,
        rejected_name=REJECTED_EXTERNAL_REF_NAME,
    )


def _artifact_ref(manifest: dict[str, Any], key: str, default: str) -> str | None:
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        value = artifacts.get(key)
        if isinstance(value, str) and value:
            return value
    return default if manifest else None


def _report_state(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return manifest_report_state(run_dir, manifest)


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
        artifact_paths = _artifact_paths(stage.get("artifacts"))
        record = {
            "index": index,
            "name": stage.get("name"),
            "status": stage.get("status"),
            "started_at": stage.get("started_at"),
            "finished_at": stage.get("finished_at"),
            "artifact_count": len(artifact_paths),
            "artifacts": _stage_artifact_records(artifact_paths),
            "artifact_omitted_count": max(0, len(artifact_paths) - MAX_STAGE_ARTIFACT_REFS),
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


def _stage_artifact_records(paths: list[str]) -> list[dict[str, str]]:
    return [
        {"path": path, "kind": _artifact_kind(path)}
        for path in paths[:MAX_STAGE_ARTIFACT_REFS]
    ]


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


def _normalize_section_status(status: str) -> str:
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


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bounded: dict[str, Any] = {}
    for key, item in sorted(value.items()):
        if isinstance(item, (str, int, float, bool)) or item is None:
            bounded[str(key)] = item
    return bounded


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean or None


def _warning_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("warnings")))


def _error_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("errors")))
