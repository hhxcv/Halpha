from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event, RLock, Thread
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from halpha.config import ConfigError, load_config
from halpha.dashboard.artifact_preview import dashboard_artifact_preview
from halpha.dashboard.assets import dashboard_asset_media_type, dashboard_asset_text
from halpha.dashboard.data_cleanup import (
    MAX_DELETION_RUN_ITEMS,
    dashboard_data_deletion_plan as build_dashboard_data_deletion_plan,
    dashboard_delete_data as execute_dashboard_delete_data,
)
from halpha.dashboard.data_stores import dashboard_data_stores
from halpha.dashboard.data_viewer import (
    dashboard_data_viewer_collection_job,
    dashboard_data_viewer_collection_plan,
    dashboard_data_viewer_export,
    dashboard_data_viewer_preview,
    dashboard_data_viewer_summary,
    dashboard_data_viewer_timeline,
)
from halpha.dashboard.constants import (
    DASHBOARD_TIMESTAMP_DATE_ORDER_OPTIONS,
    DASHBOARD_TIMESTAMP_HOUR_CYCLE_OPTIONS,
    DEFAULT_DASHBOARD_TIMESTAMP_DATE_ORDER,
    DEFAULT_DASHBOARD_TIMESTAMP_HOUR_CYCLE,
)
from halpha.dashboard.core_scheduler import DEFAULT_CORE_SCHEDULER_TICK_SECONDS, CoreScheduler
from halpha.dashboard.intelligence import dashboard_text_intelligence
from halpha.dashboard.monitor import dashboard_monitor_alerts, dashboard_monitor_cycles, dashboard_monitor_summary
from halpha.dashboard.overview import dashboard_overview
from halpha.dashboard.runs import dashboard_run_detail, dashboard_runs
from halpha.dashboard.schedule import DashboardScheduleManager
from halpha.dashboard.services import dashboard_service_action, dashboard_services_summary
from halpha.dashboard.settings import (
    dashboard_backup_config,
    dashboard_config_selection,
    dashboard_config_profile,
    dashboard_config_ref,
    dashboard_import_config_file,
    resolve_dashboard_config_candidate,
    dashboard_save_config_profile,
    sanitize_dashboard_message,
)
from halpha.dashboard.state import read_dashboard_config_history, read_dashboard_selected_config_state, write_dashboard_selected_config_state
from halpha.dashboard.strategy_actions import dashboard_strategy_action_job
from halpha.dashboard.strategy import dashboard_strategy_research
from halpha.dashboard.ui import dashboard_index_html
from halpha.live.scheduler import LiveScheduler
from halpha.runtime.command_jobs import CommandJobManager
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository, ServiceLifecycleResult
from halpha.storage import artifact_base
from halpha.time_display import configured_display_timezone


DASHBOARD_LOGGER = logging.getLogger(__name__)
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
DASHBOARD_SERVICE_NAME = "halpha_core"
DASHBOARD_SERVICE_ROLE = "core"
DASHBOARD_HEALTH_TIMEOUT_SECONDS = 0.75
DASHBOARD_RESTART_WAIT_SECONDS = 5.0
DASHBOARD_RESTART_POLL_SECONDS = 0.1
DASHBOARD_START_WAIT_SECONDS = 10.0
DASHBOARD_HEARTBEAT_SECONDS = 2.0
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


class DashboardError(Exception):
    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class DashboardStartupConfig:
    config: dict[str, Any] | None
    config_path: Path | None
    source: str
    warnings: list[str]


class DashboardConfigContext:
    def __init__(self, config: dict[str, Any] | None, *, config_path: Path | None) -> None:
        self._lock = RLock()
        self.config: dict[str, Any] | None = None
        self.config_path: Path | None = None
        self.job_manager: CommandJobManager | None = None
        self.schedule_manager: DashboardScheduleManager | None = None
        if config is not None and config_path is not None:
            self.set_active_config(config, config_path=config_path, persist=False)

    def set_active_config(self, config: dict[str, Any], *, config_path: Path, persist: bool = True) -> None:
        with self._lock:
            self.config = config
            self.config_path = config_path
            self.job_manager = CommandJobManager(
                config,
                config_path=config_path,
                requested_by="Core",
                requester={"source": "core_api"},
                execution_mode="internal",
            )
            self.schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=self.job_manager)
            if persist:
                write_dashboard_selected_config_state(config_path)

    def active(self) -> tuple[dict[str, Any], Path] | None:
        with self._lock:
            if self.config is None or self.config_path is None:
                return None
            return self.config, self.config_path

    def active_runtime(self) -> tuple[dict[str, Any], Path, CommandJobManager, DashboardScheduleManager] | None:
        with self._lock:
            if (
                self.config is None
                or self.config_path is None
                or self.job_manager is None
                or self.schedule_manager is None
            ):
                return None
            return self.config, self.config_path, self.job_manager, self.schedule_manager


def _run_core_scheduler_loop(context: DashboardConfigContext, stop_event: Event) -> None:
    while not stop_event.is_set():
        wait_seconds = DEFAULT_CORE_SCHEDULER_TICK_SECONDS
        runtime = context.active_runtime()
        if runtime is not None:
            config, config_path, job_manager, schedule_manager = runtime
            try:
                tick = CoreScheduler.from_core_managers(
                    config,
                    config_path=config_path,
                    job_manager=job_manager,
                    schedule_manager=schedule_manager,
                ).run_once()
                wait_seconds = _core_scheduler_wait_seconds(tick)
            except Exception as exc:
                DASHBOARD_LOGGER.warning(
                    "core scheduler tick failed.",
                    extra={
                        "event": "core_scheduler.tick_failed",
                        "error": sanitize_dashboard_message(str(exc) or "core scheduler tick failed.", config_path=config_path),
                    },
                )
        if stop_event.wait(wait_seconds):
            break


def _core_scheduler_wait_seconds(payload: dict[str, Any]) -> float:
    try:
        parsed = float(payload.get("next_tick_seconds"))
    except (TypeError, ValueError):
        return DEFAULT_CORE_SCHEDULER_TICK_SECONDS
    if parsed <= 0:
        return DEFAULT_CORE_SCHEDULER_TICK_SECONDS
    return max(1.0, min(DEFAULT_CORE_SCHEDULER_TICK_SECONDS, parsed))


def load_dashboard_startup_config(config_arg: str | None) -> DashboardStartupConfig:
    if config_arg:
        config_path = Path(config_arg)
        config = load_config(config_path)
        write_dashboard_selected_config_state(config_path)
        return DashboardStartupConfig(config=config, config_path=config_path, source="explicit", warnings=[])

    state, error = read_dashboard_selected_config_state()
    if error:
        return DashboardStartupConfig(config=None, config_path=None, source="none", warnings=[])
    raw_path = state.get("config_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return DashboardStartupConfig(
            config=None,
            config_path=None,
            source="invalid_persisted",
            warnings=["last selected dashboard config is missing a path."],
        )
    config_path = Path(raw_path.strip())
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        return DashboardStartupConfig(
            config=None,
            config_path=None,
            source="invalid_persisted",
            warnings=[f"last selected dashboard config could not be loaded: {sanitize_dashboard_message(str(exc), config_path=config_path)}"],
        )
    return DashboardStartupConfig(config=config, config_path=config_path, source="persisted", warnings=[])


def _select_dashboard_config(context: DashboardConfigContext, *, request: dict[str, Any]) -> dict[str, Any]:
    candidate_id = request.get("candidate_id")
    if isinstance(candidate_id, str) and candidate_id.strip():
        active = context.active()
        active_config_path = active[1] if active else None
        resolved = resolve_dashboard_config_candidate(
            candidate_id,
            active_config_path=active_config_path,
            config_history=read_dashboard_config_history(),
        )
        if resolved is None:
            return _unconfigured_payload(
                "dashboard_config_selection",
                status="failed",
                errors=["selected config option is no longer available."],
            )
        config_path = resolved
    else:
        raw_path = request.get("config_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return _unconfigured_payload(
                "dashboard_config_selection",
                status="failed",
                errors=["config_path or candidate_id must be provided."],
            )
        config_path = Path(raw_path.strip())
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_config_selection",
            "status": "failed",
            "config": _dashboard_config_status(config_path),
            "profile": None,
            "warnings": [],
            "errors": [sanitize_dashboard_message(str(exc), config_path=config_path)],
        }
    context.set_active_config(config, config_path=config_path)
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_selection",
        "status": "succeeded",
        "config": _dashboard_config_status(config_path),
        "profile": _dashboard_config_profile(config, config_path=config_path),
        "warnings": [],
        "errors": [],
    }


def _unconfigured_config_profile() -> dict[str, Any]:
    payload = _unconfigured_payload("dashboard_config_profile", fields=[], sections=[])
    payload["config"] = {"loaded": False, "ref": None, "editable": False, "requires_confirmation": False}
    payload["config_selection"] = dashboard_config_selection(None, config_history=read_dashboard_config_history())
    payload["omitted"] = {
        "absolute_local_paths_embedded": False,
        "proxy_urls_embedded": False,
        "credentials_embedded": False,
        "raw_config_text_embedded": True,
    }
    return payload


def _unconfigured_payload(artifact_type: str, *, status: str = "unconfigured", **extra: Any) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "status": status,
        "config": {"loaded": False, "ref": None},
        "warnings": ["No dashboard config is active. Open Settings and load a config file."],
        "errors": [],
    }
    payload.update(extra)
    return payload


def _dashboard_config_status(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {"loaded": False, "ref": None}
    return {"loaded": True, "ref": dashboard_config_ref(config_path)}


def _dashboard_config_profile(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    return dashboard_config_profile(config, config_path=config_path, config_history=read_dashboard_config_history())


def create_dashboard_app(
    config: dict[str, Any] | None = None,
    *,
    config_path: Path | None = None,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
    service_lifecycle: Callable[[], dict[str, Any]] | None = None,
    start_core_scheduler: bool = False,
) -> Any:
    try:
        from fastapi import Body, FastAPI, Response
        from fastapi.responses import HTMLResponse
    except ModuleNotFoundError as exc:
        raise DashboardError("FastAPI is required to run the dashboard.") from exc

    validate_dashboard_host(host)
    validate_dashboard_port(port)
    context = DashboardConfigContext(config, config_path=config_path)

    app = FastAPI(title="Halpha Dashboard", version="0.0.0")
    scheduler_stop_event = Event()
    scheduler_thread: Thread | None = None

    @app.on_event("startup")
    def start_core_scheduler_loop() -> None:
        nonlocal scheduler_thread
        if start_core_scheduler is not True:
            return
        scheduler_thread = Thread(
            target=_run_core_scheduler_loop,
            args=(context, scheduler_stop_event),
            name="halpha-core-scheduler",
            daemon=True,
        )
        scheduler_thread.start()

    @app.on_event("shutdown")
    def stop_core_scheduler_loop() -> None:
        scheduler_stop_event.set()
        if scheduler_thread is not None:
            scheduler_thread.join(timeout=3)

    @app.middleware("http")
    async def no_store_dashboard_responses(_request: Any, call_next: Any) -> Any:
        response = await call_next(_request)
        for key, value in NO_STORE_HEADERS.items():
            response.headers[key] = value
        return response

    @app.get("/", response_class=HTMLResponse)
    def root() -> HTMLResponse:
        active = context.active()
        active_config = active[0] if active else {}
        return HTMLResponse(
            dashboard_index_html(
                display_timezone=dashboard_display_timezone(active_config),
                timestamp_hour_cycle=dashboard_timestamp_hour_cycle(active_config),
                timestamp_date_order=dashboard_timestamp_date_order(active_config),
            ),
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
        active = context.active()
        lifecycle = service_lifecycle() if service_lifecycle is not None else _unmanaged_dashboard_lifecycle()
        if active is None:
            return dashboard_health(None, config_path=None, host=host, port=port, lifecycle=lifecycle)
        active_config, active_config_path = active
        return dashboard_health(active_config, config_path=active_config_path, host=host, port=port, lifecycle=lifecycle)

    @app.get("/api/services")
    def services_endpoint() -> dict[str, Any]:
        active = context.active()
        lifecycle = service_lifecycle() if service_lifecycle is not None else _unmanaged_dashboard_lifecycle()
        if active is None:
            return dashboard_services_summary(None, config_path=None, dashboard_lifecycle=lifecycle)
        active_config, active_config_path = active
        return dashboard_services_summary(active_config, config_path=active_config_path, dashboard_lifecycle=lifecycle)

    @app.post("/api/services/{role}/{action}")
    def service_action_endpoint(role: str, action: str) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload(
                "dashboard_service_action",
                status="blocked",
                role=role,
                action=action,
                service=None,
            )
        active_config, active_config_path = active
        return dashboard_service_action(active_config, config_path=active_config_path, role=role, action=action)

    @app.get("/api/config/profile")
    def config_profile_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_config_profile()
        active_config, active_config_path = active
        return _dashboard_config_profile(active_config, config_path=active_config_path)

    @app.post("/api/config/select")
    def config_select_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _select_dashboard_config(context, request=request)

    @app.post("/api/config/import")
    def config_import_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        imported = dashboard_import_config_file(request)
        if imported.get("status") != "succeeded" or not imported.get("config_path"):
            imported["profile"] = None
            return imported
        selected = _select_dashboard_config(context, request={"config_path": imported["config_path"]})
        status = selected.get("status")
        return {
            **imported,
            "status": status,
            "selection": selected,
            "profile": selected.get("profile"),
            "warnings": [*(imported.get("warnings") or []), *(selected.get("warnings") or [])],
            "errors": [*(imported.get("errors") or []), *(selected.get("errors") or [])],
        }

    @app.post("/api/config/profile")
    def config_profile_save_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_config_save_result", config={"loaded": False})
        active_config, active_config_path = active
        return dashboard_save_config_profile(active_config, config_path=active_config_path, request=request)

    @app.post("/api/config/profile/backup")
    def config_profile_backup_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_config_backup", backup_ref=None, config={"loaded": False})
        _, active_config_path = active
        return dashboard_backup_config(config_path=active_config_path)

    @app.get("/api/overview")
    def overview_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_overview", sections={})
        active_config, active_config_path = active
        return dashboard_overview(active_config, config_path=active_config_path)

    @app.get("/api/text-intelligence")
    def text_intelligence_endpoint(run_id: str | None = None) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_text_intelligence", artifacts=[])
        _, active_config_path = active
        return dashboard_text_intelligence(config_path=active_config_path, run_id=run_id)

    @app.get("/api/runs")
    def runs_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_runs", runs=[], latest_successful_run=None, latest_run=None)
        _, active_config_path = active
        return dashboard_runs(config_path=active_config_path)

    @app.get("/api/runs/{run_id}")
    def run_detail_endpoint(run_id: str) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_run_detail", run_id=run_id)
        _, active_config_path = active
        return dashboard_run_detail(config_path=active_config_path, run_id=run_id)

    @app.get("/api/artifacts/preview")
    def artifact_preview_endpoint(path: str) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_artifact_preview", path=path, preview=None)
        active_config, active_config_path = active
        return dashboard_artifact_preview(active_config, config_path=active_config_path, artifact_path=path)

    @app.get("/api/data/stores")
    def data_stores_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_stores", stores=[])
        active_config, active_config_path = active
        return dashboard_data_stores(active_config, config_path=active_config_path)

    @app.get("/api/data/viewer/summary")
    def data_viewer_summary_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_viewer_summary", stores=[])
        active_config, active_config_path = active
        return dashboard_data_viewer_summary(active_config, config_path=active_config_path)

    @app.post("/api/data/viewer/timeline")
    def data_viewer_timeline_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_coverage_timeline", intervals=[])
        active_config, active_config_path = active
        return dashboard_data_viewer_timeline(active_config, config_path=active_config_path, request=request)

    @app.post("/api/data/viewer/preview")
    def data_viewer_preview_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_preview", records=[])
        active_config, active_config_path = active
        return dashboard_data_viewer_preview(active_config, config_path=active_config_path, request=request)

    @app.post("/api/data/viewer/export")
    def data_viewer_export_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_export", export=None)
        active_config, active_config_path = active
        return dashboard_data_viewer_export(active_config, config_path=active_config_path, request=request)

    @app.post("/api/data/viewer/collect/plan")
    def data_viewer_collection_plan_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_collection_plan", plan=None)
        active_config, active_config_path = active
        return dashboard_data_viewer_collection_plan(active_config, config_path=active_config_path, request=request)

    @app.post("/api/data/viewer/collect/jobs")
    def data_viewer_collection_job_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_collection_job", job=None)
        active_config, active_config_path = active
        return dashboard_data_viewer_collection_job(
            active_config,
            config_path=active_config_path,
            job_manager=context.job_manager,
            request=request,
        )

    @app.get("/api/data/deletion")
    def data_deletion_plan_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_deletion_plan", candidates=[], plan=[])
        active_config, active_config_path = active
        return dashboard_data_deletion_plan(active_config, config_path=active_config_path)

    @app.post("/api/data/deletion")
    def data_deletion_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_data_deletion_result", deleted=[], skipped=[])
        active_config, active_config_path = active
        return dashboard_delete_data(active_config, config_path=active_config_path, request=request)

    @app.get("/api/strategies")
    def strategies_endpoint(run_id: str | None = None) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_strategy_research", pipeline={"artifacts": []}, standalone={"artifacts": []})
        active_config, active_config_path = active
        return dashboard_strategy_research(active_config, config_path=active_config_path, run_id=run_id)

    @app.post("/api/strategies/actions/{action}")
    def strategy_action_job_endpoint(action: str, request: dict[str, Any] | None = Body(default=None)) -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_strategy_action_job", action=action, job=None)
        return dashboard_strategy_action_job(job_manager=context.job_manager, action=action, request=request or {})

    @app.get("/api/monitor")
    def monitor_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_monitor")
        active_config, active_config_path = active
        return dashboard_monitor_summary(active_config, config_path=active_config_path)

    @app.get("/api/monitor/cycles")
    def monitor_cycles_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_monitor_cycles", cycles=[])
        active_config, active_config_path = active
        return dashboard_monitor_cycles(active_config, config_path=active_config_path)

    @app.get("/api/monitor/alerts")
    def monitor_alerts_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_monitor_alerts", alerts=[])
        active_config, active_config_path = active
        return dashboard_monitor_alerts(active_config, config_path=active_config_path)

    @app.get("/api/live")
    def live_endpoint() -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("dashboard_live", collections=[], active_jobs=[], recent_jobs=[])
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_live", collections=[], active_jobs=[], recent_jobs=[])
        active_config, active_config_path = active
        return LiveScheduler(
            active_config,
            config_path=active_config_path,
            job_manager=context.job_manager,
        ).read_model()

    @app.get("/api/live/cycles")
    def live_cycles_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_live_cycles", cycles=[])
        active_config, active_config_path = active
        payload = dashboard_monitor_cycles(active_config, config_path=active_config_path)
        return {
            **payload,
            "artifact_type": "dashboard_live_cycles",
            "source_artifact_type": payload.get("artifact_type"),
        }

    @app.get("/api/live/alerts")
    def live_alerts_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_payload("dashboard_live_alerts", alerts=[])
        active_config, active_config_path = active
        payload = dashboard_monitor_alerts(active_config, config_path=active_config_path)
        return {
            **payload,
            "artifact_type": "dashboard_live_alerts",
            "source_artifact_type": payload.get("artifact_type"),
        }

    @app.get("/api/jobs")
    def jobs_endpoint() -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("command_job_list", jobs=[])
        return context.job_manager.list_jobs()

    @app.post("/api/jobs")
    def create_job_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("command_job", status="blocked", job_id=None)
        return context.job_manager.create_job(request)

    @app.get("/api/jobs/{job_id}")
    def job_detail_endpoint(job_id: str) -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("command_job", status="blocked", job_id=job_id)
        job = context.job_manager.get_job(job_id)
        if job is None:
            return {
                "schema_version": 1,
                "artifact_type": "command_job",
                "job_id": job_id,
                "status": "missing",
                "warnings": ["command job was not found."],
                "errors": [],
            }
        return job

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job_endpoint(job_id: str) -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("command_job", status="blocked", job_id=job_id)
        return context.job_manager.cancel_job(job_id)

    @app.get("/api/schedule/daily-report")
    def daily_report_schedule_endpoint() -> dict[str, Any]:
        if context.schedule_manager is None:
            return _unconfigured_payload("dashboard_daily_report_schedule", enabled=False, persisted=False)
        return context.schedule_manager.read_daily_report_schedule()

    @app.post("/api/schedule/daily-report")
    def update_daily_report_schedule_endpoint(
        request: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        if context.schedule_manager is None:
            return _unconfigured_payload("dashboard_daily_report_schedule", enabled=False, persisted=False)
        return context.schedule_manager.update_daily_report_schedule(request or {})

    @app.post("/api/schedule/daily-report/enable")
    def enable_daily_report_schedule_endpoint(
        request: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        if context.schedule_manager is None:
            return _unconfigured_payload("dashboard_daily_report_schedule", enabled=False, persisted=False)
        return context.schedule_manager.enable_daily_report_schedule(request or {})

    @app.post("/api/schedule/daily-report/disable")
    def disable_daily_report_schedule_endpoint() -> dict[str, Any]:
        if context.schedule_manager is None:
            return _unconfigured_payload("dashboard_daily_report_schedule", enabled=False, persisted=False)
        return context.schedule_manager.disable_daily_report_schedule()

    @app.post("/api/schedule/daily-report/trigger")
    def trigger_daily_report_schedule_endpoint(
        request: dict[str, Any] | None = Body(default=None),
    ) -> dict[str, Any]:
        if context.schedule_manager is None:
            return _unconfigured_payload("dashboard_daily_report_schedule_trigger", job=None)
        return context.schedule_manager.trigger_daily_report_schedule(request or {})

    @app.post("/api/schedule/daily-report/dispatch-due")
    def dispatch_due_daily_report_schedule_endpoint() -> dict[str, Any]:
        if context.schedule_manager is None:
            return _unconfigured_payload("dashboard_daily_report_dispatch", job=None)
        return context.schedule_manager.dispatch_due_daily_report()

    return app


def run_dashboard_service(
    config: dict[str, Any] | None = None,
    *,
    config_path: Path | None = None,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
    restart_from_instance_id: str | None = None,
) -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise DashboardError("Uvicorn is required to run the dashboard.") from exc

    validate_dashboard_host(host)
    validate_dashboard_port(port)
    repository = _dashboard_lifecycle_repository(config_path)
    config_digest = _dashboard_service_config_digest(host=host, port=port)
    config_ref = _dashboard_service_config_ref(config_path)
    if restart_from_instance_id:
        result, ownership = repository.attempt_restart_ownership(
            DASHBOARD_SERVICE_ROLE,
            previous_instance_id=restart_from_instance_id,
            config_ref=config_ref,
            config_digest=config_digest,
            endpoint=_dashboard_endpoint_metadata(host, port),
        )
    else:
        result, ownership = repository.attempt_start_ownership(
            DASHBOARD_SERVICE_ROLE,
            config_ref=config_ref,
            config_digest=config_digest,
            endpoint=_dashboard_endpoint_metadata(host, port),
        )
    if ownership is None or result.instance_id is None:
        raise DashboardError(_dashboard_lifecycle_start_message(result))

    app = create_dashboard_app(
        config,
        config_path=config_path,
        host=host,
        port=port,
        start_core_scheduler=True,
        service_lifecycle=lambda: _dashboard_lifecycle_payload(
            repository.inspect(DASHBOARD_SERVICE_ROLE),
            expected_instance_id=result.instance_id,
        ),
    )
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port))
    stop_event = Event()
    terminal_status = "stopped"
    terminal_error: str | None = None
    try:
        repository.register_started(
            DASHBOARD_SERVICE_ROLE,
            instance_id=result.instance_id,
            endpoint=_dashboard_endpoint_metadata(host, port),
        )
        heartbeat_thread = Thread(
            target=_run_dashboard_heartbeat_loop,
            args=(repository, result.instance_id, server, stop_event),
            name="halpha-dashboard-heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()
        server.run()
    except BaseException as exc:
        terminal_status = "failed"
        terminal_error = str(exc)
        raise
    finally:
        stop_event.set()
        if "heartbeat_thread" in locals():
            heartbeat_thread.join(timeout=3)
        with suppress(Exception):
            repository.record_terminal_exit(
                DASHBOARD_SERVICE_ROLE,
                instance_id=result.instance_id,
                status=terminal_status,
                exit_code=0 if terminal_status == "stopped" else 1,
                error=terminal_error,
            )
        ownership.release()


def start_dashboard_service(
    config_arg: str | None,
    *,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
    restart_from_instance_id: str | None = None,
) -> dict[str, Any]:
    startup = load_dashboard_startup_config(config_arg)
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    repository = _dashboard_lifecycle_repository(startup.config_path)
    config_digest = _dashboard_service_config_digest(host=host, port=port)
    start_mutex = repository.acquire_start_mutex(DASHBOARD_SERVICE_ROLE)
    if start_mutex is None:
        return _wait_for_duplicate_dashboard_start(
            repository,
            host=host,
            port=port,
            config_digest=config_digest,
            timeout_seconds=DASHBOARD_START_WAIT_SECONDS,
        )

    try:
        endpoint_can_bind = _dashboard_endpoint_can_bind(host, port)
        lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
        terminal_restart_instance_id = restart_from_instance_id or _terminal_dashboard_instance_id(lifecycle)
        blocking = _dashboard_start_blocking_result(
            lifecycle,
            host=host,
            port=port,
            config_digest=config_digest,
            endpoint_can_bind=endpoint_can_bind,
        )
        if blocking is not None:
            if blocking["status"] == "existing":
                return blocking
            if blocking["status"] == "starting":
                return _wait_for_existing_dashboard_service(
                    repository,
                    host=host,
                    port=port,
                    timeout_seconds=DASHBOARD_START_WAIT_SECONDS,
                )
            raise DashboardError(str(blocking["reason"]))

        if not endpoint_can_bind:
            health = _read_dashboard_endpoint_health(host, port)
            if _is_halpha_core_health(health):
                existing = _dashboard_existing_result_from_health(health, repository=repository, host=host, port=port)
                if existing is not None:
                    return existing
                raise DashboardError(
                    f"a Halpha dashboard already responds on {host}:{port}, but shared lifecycle state does not match; "
                    "use dashboard status or stop before starting another service."
                )
            raise DashboardError(
                f"dashboard port {port} on {host} is already in use by a non-Halpha or unresponsive local service; "
                "stop that service or choose a different --port."
            )

        process = _launch_dashboard_service_process(
            config_arg,
            host=host,
            port=port,
            restart_from_instance_id=terminal_restart_instance_id,
        )
        return _wait_for_dashboard_service_start(
            process,
            repository=repository,
            host=host,
            port=port,
            timeout_seconds=DASHBOARD_START_WAIT_SECONDS,
        )
    finally:
        start_mutex.release()


def _wait_for_duplicate_dashboard_start(
    repository: ServiceLifecycleRepository,
    *,
    host: str,
    port: int,
    config_digest: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
        endpoint_can_bind = _dashboard_endpoint_can_bind(host, port)
        blocking = _dashboard_start_blocking_result(
            lifecycle,
            host=host,
            port=port,
            config_digest=config_digest,
            endpoint_can_bind=endpoint_can_bind,
        )
        if blocking is not None:
            if blocking["status"] == "existing":
                return blocking
            if blocking["status"] == "starting":
                health = _read_dashboard_endpoint_health(host, port)
                if _is_halpha_core_health(health):
                    return _dashboard_service_result("existing", lifecycle=lifecycle, host=host, port=port)
                time.sleep(DASHBOARD_RESTART_POLL_SECONDS)
                continue
            raise DashboardError(str(blocking["reason"]))

        if not endpoint_can_bind:
            health = _read_dashboard_endpoint_health(host, port)
            if _is_halpha_core_health(health):
                existing = _dashboard_existing_result_from_health(health, repository=repository, host=host, port=port)
                if existing is not None:
                    return existing
            raise DashboardError(
                f"dashboard port {port} on {host} is already in use while another core service start is in progress; "
                "wait for it to finish, then run dashboard status."
            )

        time.sleep(DASHBOARD_RESTART_POLL_SECONDS)
    raise DashboardError("core service start is already in progress; retry after it finishes or run dashboard status.")


def dashboard_service_status(
    config_arg: str | None,
    *,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> dict[str, Any]:
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    config_path = Path(config_arg) if config_arg else None
    repository = _dashboard_lifecycle_repository(config_path)
    lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
    health = _read_dashboard_endpoint_health(host, port)
    return {
        "status": lifecycle.status,
        "instance_id": lifecycle.instance_id,
        "pid": _dashboard_lifecycle_pid(lifecycle),
        "endpoint": _dashboard_endpoint_metadata(host, port),
        "health": "ok" if _is_halpha_core_health(health) else "unavailable",
        "lifecycle": _dashboard_lifecycle_payload(lifecycle),
    }


def stop_dashboard_service(
    config_arg: str | None,
    *,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> dict[str, Any]:
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    config_path = Path(config_arg) if config_arg else None
    repository = _dashboard_lifecycle_repository(config_path)
    lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
    if lifecycle.instance_id is None or lifecycle.status in {"not_found", "stale", "stopped", "failed", "crashed"}:
        return {
            "status": lifecycle.status,
            "instance_id": lifecycle.instance_id,
            "pid": _dashboard_lifecycle_pid(lifecycle),
            "endpoint": _dashboard_endpoint_metadata(host, port),
            "lifecycle": _dashboard_lifecycle_payload(lifecycle),
        }
    requested = repository.request_graceful_stop(DASHBOARD_SERVICE_ROLE, instance_id=lifecycle.instance_id)
    stopped = _wait_for_dashboard_service_stop(
        repository,
        previous_instance_id=lifecycle.instance_id,
        host=host,
        port=port,
        timeout_seconds=DASHBOARD_RESTART_WAIT_SECONDS,
    )
    if stopped is not None:
        return stopped
    return {
        "status": "stop_requested",
        "instance_id": lifecycle.instance_id,
        "pid": _dashboard_lifecycle_pid(lifecycle),
        "endpoint": _dashboard_endpoint_metadata(host, port),
        "lifecycle": _dashboard_lifecycle_payload(requested),
        "warnings": ["dashboard stop was requested, but the service has not exited yet."],
    }


def restart_dashboard_service(
    config_arg: str | None,
    *,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> dict[str, Any]:
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    config_path = Path(config_arg) if config_arg else None
    repository = _dashboard_lifecycle_repository(config_path)
    lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
    restart_from_instance_id = lifecycle.instance_id
    if lifecycle.status in {"running", "starting", "stop_requested", "unresponsive"} and lifecycle.instance_id:
        stopped = stop_dashboard_service(config_arg, host=host, port=port)
        if stopped.get("status") not in {"stopped", "failed", "crashed", "stale", "not_found"}:
            return stopped
    return start_dashboard_service(
        config_arg,
        host=host,
        port=port,
        restart_from_instance_id=restart_from_instance_id,
    )


def _run_dashboard_heartbeat_loop(
    repository: ServiceLifecycleRepository,
    instance_id: str,
    server: Any,
    stop_event: Event,
) -> None:
    while not stop_event.wait(DASHBOARD_HEARTBEAT_SECONDS):
        with suppress(Exception):
            repository.update_heartbeat(DASHBOARD_SERVICE_ROLE, instance_id=instance_id)
        with suppress(Exception):
            stop_request = repository.observe_stop_request(DASHBOARD_SERVICE_ROLE, instance_id=instance_id)
            if stop_request.requested:
                server.should_exit = True


def _dashboard_lifecycle_repository(config_path: Path | None) -> ServiceLifecycleRepository:
    return ServiceLifecycleRepository(runtime_root=artifact_base(config_path))


def _dashboard_service_config_ref(config_path: Path | None) -> str:
    return dashboard_config_ref(config_path) if config_path is not None else "dashboard-service-unconfigured"


def _dashboard_service_config_digest(*, host: str, port: int) -> str:
    material = f"core-service-v1|host={host}|port={int(port)}"
    return sha256(material.encode("utf-8")).hexdigest()


def _dashboard_endpoint_metadata(host: str, port: int) -> dict[str, Any]:
    return {"host": host, "port": int(port), "health_url": _dashboard_health_url(host, port)}


def _terminal_dashboard_instance_id(lifecycle: ServiceLifecycleResult) -> str | None:
    if lifecycle.status in {"stopped", "failed", "crashed"}:
        return lifecycle.instance_id
    return None


def _dashboard_start_blocking_result(
    lifecycle: ServiceLifecycleResult,
    *,
    host: str,
    port: int,
    config_digest: str,
    endpoint_can_bind: bool,
) -> dict[str, Any] | None:
    if lifecycle.status in {"not_found", "stale", "stopped", "failed", "crashed"}:
        return None
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    if lifecycle.status == "unresponsive":
        return {
            "status": "unresponsive",
            "reason": "core service lock is held but heartbeat is stale; stop or inspect it before starting another service.",
            "lifecycle": _dashboard_lifecycle_payload(lifecycle),
        }
    if lifecycle.status not in {"running", "starting", "stop_requested"}:
        return None
    if not _dashboard_lifecycle_endpoint_matches(lifecycle, host=host, port=port) or state.get("config_digest") != config_digest:
        return {
            "status": "conflict",
            "reason": "core service is already active for a different endpoint or service configuration.",
            "lifecycle": _dashboard_lifecycle_payload(lifecycle),
        }
    if lifecycle.status == "running" and endpoint_can_bind:
        return {
            "status": "unresponsive",
            "reason": "dashboard lifecycle is running, but the configured endpoint is not responding.",
            "lifecycle": _dashboard_lifecycle_payload(lifecycle),
        }
    if lifecycle.status == "starting":
        return {
            "status": "starting",
            "reason": "core service is already starting.",
            "lifecycle": _dashboard_lifecycle_payload(lifecycle),
        }
    if lifecycle.status == "stop_requested":
        return {
            "status": "stop_requested",
            "reason": "core service is stopping; wait for it to exit before starting another service.",
            "lifecycle": _dashboard_lifecycle_payload(lifecycle),
        }
    return _dashboard_service_result("existing", lifecycle=lifecycle, host=host, port=port)


def _dashboard_lifecycle_endpoint_matches(lifecycle: ServiceLifecycleResult, *, host: str, port: int) -> bool:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    endpoint = state.get("endpoint") if isinstance(state.get("endpoint"), dict) else {}
    return endpoint.get("host") == host and endpoint.get("port") == int(port)


def _dashboard_existing_result_from_health(
    health: dict[str, Any] | None,
    *,
    repository: ServiceLifecycleRepository,
    host: str,
    port: int,
) -> dict[str, Any] | None:
    if not _is_halpha_core_health(health):
        return None
    lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
    if lifecycle.instance_id is None or not _dashboard_lifecycle_endpoint_matches(lifecycle, host=host, port=port):
        return None
    return _dashboard_service_result("existing", lifecycle=lifecycle, host=host, port=port)


def _launch_dashboard_service_process(
    config_arg: str | None,
    *,
    host: str,
    port: int,
    restart_from_instance_id: str | None,
) -> subprocess.Popen[Any]:
    command = [sys.executable, "-m", "halpha", "dashboard", "service", "--host", host, "--port", str(port)]
    if config_arg:
        command.extend(["--config", config_arg])
    if restart_from_instance_id:
        command.extend(["--restart-from-instance-id", restart_from_instance_id])
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": Path.cwd(),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _wait_for_dashboard_service_start(
    process: subprocess.Popen[Any],
    *,
    repository: ServiceLifecycleRepository,
    host: str,
    port: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        health = _read_dashboard_endpoint_health(host, port)
        if _is_halpha_core_health(health):
            lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
            return _dashboard_service_result("started", lifecycle=lifecycle, host=host, port=port)
        if process.poll() is not None:
            raise DashboardError("core service exited before the health endpoint became available.")
        time.sleep(DASHBOARD_RESTART_POLL_SECONDS)
    raise DashboardError("core service did not become healthy before the startup timeout.")


def _wait_for_existing_dashboard_service(
    repository: ServiceLifecycleRepository,
    *,
    host: str,
    port: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        health = _read_dashboard_endpoint_health(host, port)
        if _is_halpha_core_health(health):
            lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
            return _dashboard_service_result("existing", lifecycle=lifecycle, host=host, port=port)
        time.sleep(DASHBOARD_RESTART_POLL_SECONDS)
    raise DashboardError("core service is starting, but the health endpoint is not available yet.")


def _wait_for_dashboard_service_stop(
    repository: ServiceLifecycleRepository,
    *,
    previous_instance_id: str,
    host: str,
    port: int,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(DASHBOARD_SERVICE_ROLE)
        if lifecycle.instance_id == previous_instance_id and lifecycle.status in {"stopped", "failed", "crashed", "stale"}:
            return _dashboard_service_result(lifecycle.status, lifecycle=lifecycle, host=host, port=port)
        if lifecycle.status == "stale" or _dashboard_endpoint_can_bind(host, port):
            return _dashboard_service_result("stale", lifecycle=lifecycle, host=host, port=port)
        time.sleep(DASHBOARD_RESTART_POLL_SECONDS)
    return None


def _dashboard_service_result(
    status: str,
    *,
    lifecycle: ServiceLifecycleResult,
    host: str,
    port: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "instance_id": lifecycle.instance_id,
        "pid": _dashboard_lifecycle_pid(lifecycle),
        "endpoint": _dashboard_endpoint_metadata(host, port),
        "lifecycle": _dashboard_lifecycle_payload(lifecycle),
        "warnings": [],
        "errors": [],
    }


def _dashboard_lifecycle_pid(lifecycle: ServiceLifecycleResult) -> int | None:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    pid = state.get("pid")
    if isinstance(pid, bool):
        return None
    if isinstance(pid, int) and pid > 0:
        return pid
    return None


def _dashboard_lifecycle_start_message(result: ServiceLifecycleResult) -> str:
    if result.reason:
        return result.reason
    return f"core service could not start because lifecycle status is {result.status}."


def _dashboard_endpoint_can_bind(host: str, port: int) -> bool:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not addresses:
        return False
    for family, socktype, proto, _canonname, sockaddr in addresses:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.bind(sockaddr)
        except OSError:
            return False
    return True


def _read_dashboard_endpoint_health(host: str, port: int) -> dict[str, Any] | None:
    request = Request(_dashboard_health_url(host, port), headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=DASHBOARD_HEALTH_TIMEOUT_SECONDS) as response:
            body = response.read(65_536)
    except (HTTPError, OSError, TimeoutError, URLError, ValueError):
        return None
    try:
        loaded = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _is_halpha_core_health(health: dict[str, Any] | None) -> bool:
    return isinstance(health, dict) and health.get("service") == DASHBOARD_SERVICE_NAME


def _dashboard_health_url(host: str, port: int) -> str:
    url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{url_host}:{port}/api/health"


def dashboard_health(
    config: dict[str, Any] | None,
    *,
    config_path: Path | None,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
    lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    return {
        "artifact_type": "dashboard_health",
        "service": DASHBOARD_SERVICE_NAME,
        "status": "ok" if config is not None and config_path is not None else "unconfigured",
        "local_only": True,
        "host": host,
        "port": port,
        "config": _dashboard_config_status(config_path),
        "lifecycle": lifecycle if lifecycle is not None else _unmanaged_dashboard_lifecycle(),
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


def _unmanaged_dashboard_lifecycle() -> dict[str, Any]:
    return {
        "role": DASHBOARD_SERVICE_ROLE,
        "status": "unmanaged",
        "instance_id": None,
        "owns_lock": False,
        "heartbeat_at": None,
    }


def _dashboard_lifecycle_payload(result: ServiceLifecycleResult, *, expected_instance_id: str | None = None) -> dict[str, Any]:
    state = result.state if isinstance(result.state, dict) else {}
    instance_id = result.instance_id
    return {
        "role": DASHBOARD_SERVICE_ROLE,
        "status": result.status,
        "instance_id": instance_id,
        "owns_lock": bool(result.owns_lock),
        "expected_instance_match": expected_instance_id is None or instance_id == expected_instance_id,
        "heartbeat_at": state.get("heartbeat_at") if isinstance(state.get("heartbeat_at"), str) else None,
        "started_at": state.get("started_at") if isinstance(state.get("started_at"), str) else None,
        "updated_at": state.get("updated_at") if isinstance(state.get("updated_at"), str) else None,
        "stop_requested_at": state.get("stop_requested_at") if isinstance(state.get("stop_requested_at"), str) else None,
    }


def dashboard_display_timezone(config: dict[str, Any]) -> str:
    return configured_display_timezone(config)


def dashboard_timestamp_hour_cycle(config: dict[str, Any]) -> str:
    dashboard = config.get("dashboard") if isinstance(config, dict) else None
    value = dashboard.get("timestamp_hour_cycle") if isinstance(dashboard, dict) else None
    if value in DASHBOARD_TIMESTAMP_HOUR_CYCLE_OPTIONS:
        return str(value)
    return DEFAULT_DASHBOARD_TIMESTAMP_HOUR_CYCLE


def dashboard_timestamp_date_order(config: dict[str, Any]) -> str:
    dashboard = config.get("dashboard") if isinstance(config, dict) else None
    value = dashboard.get("timestamp_date_order") if isinstance(dashboard, dict) else None
    if value in DASHBOARD_TIMESTAMP_DATE_ORDER_OPTIONS:
        return str(value)
    return DEFAULT_DASHBOARD_TIMESTAMP_DATE_ORDER


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
