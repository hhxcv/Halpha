from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from halpha.dashboard.artifact_preview import dashboard_artifact_preview
from halpha.dashboard.assets import dashboard_asset_media_type, dashboard_asset_text
from halpha.dashboard.constants import DEFAULT_DASHBOARD_DISPLAY_TIMEZONE
from halpha.dashboard.data_cleanup import (
    MAX_DELETION_RUN_ITEMS,
    dashboard_data_deletion_plan as build_dashboard_data_deletion_plan,
    dashboard_delete_data as execute_dashboard_delete_data,
)
from halpha.dashboard.data_stores import dashboard_data_stores
from halpha.dashboard.jobs import DashboardJobManager
from halpha.dashboard.monitor import dashboard_monitor_alerts, dashboard_monitor_cycles, dashboard_monitor_summary
from halpha.dashboard.runs import dashboard_latest_run_section, dashboard_run_detail, dashboard_runs
from halpha.dashboard.schedule import DashboardScheduleManager
from halpha.dashboard.settings import (
    dashboard_backup_config,
    dashboard_config_profile,
    dashboard_config_ref,
    dashboard_save_config_profile,
    sanitize_dashboard_message,
)
from halpha.dashboard.strategy import dashboard_strategy_research
from halpha.dashboard.ui import dashboard_index_html
from halpha.monitor.monitoring import MONITOR_HEALTH_STATE_FILENAME, load_monitor_config
from halpha.data.run_index import RUN_INDEX_ARTIFACT
from halpha.storage import (
    config_base as _config_base,
    read_json_object,
    resolve_local_ref,
    safe_local_ref,
)
from halpha.utils.value_helpers import (
    as_dict as _dict,
    as_list as _list,
    strict_int as _int,
    stringified_list as _string_list,
)
from halpha.workbench.workbench import DEFAULT_WORKBENCH_OUTPUT_DIR, WORKBENCH_SUMMARY_FILENAME


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REJECTED_EXTERNAL_REF_NAME = ".halpha_external_ref_rejected"
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}
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
    health = dashboard_health(config, config_path=config_path, host=host, port=port)
    job_manager = DashboardJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)

    @asynccontextmanager
    async def dashboard_lifespan(_app: Any) -> Any:
        schedule_manager.start_daily_report_dispatcher()
        try:
            yield
        finally:
            schedule_manager.stop_daily_report_dispatcher()

    app = FastAPI(title="Halpha Dashboard", version="0.0.0", lifespan=dashboard_lifespan)

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
