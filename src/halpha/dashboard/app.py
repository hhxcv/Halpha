from __future__ import annotations

from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
from threading import RLock
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from halpha.config import ConfigError, load_config
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
from halpha.dashboard.intelligence import dashboard_text_intelligence
from halpha.dashboard.monitor import dashboard_monitor_alerts, dashboard_monitor_cycles, dashboard_monitor_summary
from halpha.dashboard.overview import dashboard_overview
from halpha.dashboard.paths import dashboard_control_path
from halpha.dashboard.runs import dashboard_run_detail, dashboard_runs
from halpha.dashboard.schedule import DashboardScheduleManager
from halpha.dashboard.settings import (
    dashboard_backup_config,
    dashboard_config_profile,
    dashboard_config_ref,
    dashboard_save_config_profile,
    sanitize_dashboard_message,
)
from halpha.dashboard.strategy import dashboard_strategy_research
from halpha.dashboard.time import utc_now_timestamp
from halpha.dashboard.ui import dashboard_index_html
from halpha.storage import read_json_object, write_json


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
LOCAL_DASHBOARD_HOSTS = {"127.0.0.1", "localhost", "::1"}
DASHBOARD_SERVICE_NAME = "halpha_dashboard"
DASHBOARD_SERVICE_SCHEMA_VERSION = 1
DASHBOARD_HEALTH_TIMEOUT_SECONDS = 0.75
DASHBOARD_RESTART_WAIT_SECONDS = 5.0
DASHBOARD_RESTART_POLL_SECONDS = 0.1
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
        self._dispatcher_started = False
        self.config: dict[str, Any] | None = None
        self.config_path: Path | None = None
        self.job_manager: DashboardJobManager | None = None
        self.schedule_manager: DashboardScheduleManager | None = None
        if config is not None and config_path is not None:
            self.set_active_config(config, config_path=config_path, persist=False)

    def set_active_config(self, config: dict[str, Any], *, config_path: Path, persist: bool = True) -> None:
        with self._lock:
            if self.schedule_manager is not None and self._dispatcher_started:
                self.schedule_manager.stop_daily_report_dispatcher()
            self.config = config
            self.config_path = config_path
            self.job_manager = DashboardJobManager(config, config_path=config_path)
            self.schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=self.job_manager)
            if persist:
                write_dashboard_selected_config_state(config_path)
            if self._dispatcher_started:
                self.schedule_manager.start_daily_report_dispatcher()

    def start_dispatcher(self) -> None:
        with self._lock:
            self._dispatcher_started = True
            if self.schedule_manager is not None:
                self.schedule_manager.start_daily_report_dispatcher()

    def stop_dispatcher(self) -> None:
        with self._lock:
            if self.schedule_manager is not None:
                self.schedule_manager.stop_daily_report_dispatcher()
            self._dispatcher_started = False

    def active(self) -> tuple[dict[str, Any], Path] | None:
        with self._lock:
            if self.config is None or self.config_path is None:
                return None
            return self.config, self.config_path


def load_dashboard_startup_config(config_arg: str | None) -> DashboardStartupConfig:
    if config_arg:
        config_path = Path(config_arg)
        config = load_config(config_path)
        write_dashboard_selected_config_state(config_path)
        return DashboardStartupConfig(config=config, config_path=config_path, source="explicit", warnings=[])

    state, error = read_json_object(_dashboard_selected_config_state_path())
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


def write_dashboard_selected_config_state(config_path: Path) -> None:
    write_json(
        _dashboard_selected_config_state_path(),
        {
            "schema_version": 1,
            "artifact_type": "dashboard_selected_config_state",
            "status": "selected",
            "config_path": str(config_path),
            "config": _dashboard_config_status(config_path),
            "updated_at": utc_now_timestamp(),
        },
    )


def _dashboard_selected_config_state_path() -> Path:
    return dashboard_control_path("selected_config.json")


def _select_dashboard_config(context: DashboardConfigContext, *, request: dict[str, Any]) -> dict[str, Any]:
    raw_path = request.get("config_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return _unconfigured_payload(
            "dashboard_config_selection",
            status="failed",
            errors=["config_path must be a non-empty string."],
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
        "profile": dashboard_config_profile(config, config_path=config_path),
        "warnings": [],
        "errors": [],
    }


def _unconfigured_config_profile() -> dict[str, Any]:
    payload = _unconfigured_payload("dashboard_config_profile", fields=[], sections=[])
    payload["config"] = {"loaded": False, "ref": None, "editable": False, "requires_confirmation": False}
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


def create_dashboard_app(
    config: dict[str, Any] | None = None,
    *,
    config_path: Path | None = None,
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
    context = DashboardConfigContext(config, config_path=config_path)

    @asynccontextmanager
    async def dashboard_lifespan(_app: Any) -> Any:
        context.start_dispatcher()
        try:
            yield
        finally:
            context.stop_dispatcher()

    app = FastAPI(title="Halpha Dashboard", version="0.0.0", lifespan=dashboard_lifespan)

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
            dashboard_index_html(display_timezone=dashboard_display_timezone(active_config)),
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
        if active is None:
            return dashboard_health(None, config_path=None, host=host, port=port)
        active_config, active_config_path = active
        return dashboard_health(active_config, config_path=active_config_path, host=host, port=port)

    @app.get("/api/config/profile")
    def config_profile_endpoint() -> dict[str, Any]:
        active = context.active()
        if active is None:
            return _unconfigured_config_profile()
        active_config, active_config_path = active
        return dashboard_config_profile(active_config, config_path=active_config_path)

    @app.post("/api/config/select")
    def config_select_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return _select_dashboard_config(context, request=request)

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

    @app.get("/api/jobs")
    def jobs_endpoint() -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("dashboard_jobs", jobs=[])
        return context.job_manager.list_jobs()

    @app.post("/api/jobs")
    def create_job_endpoint(request: dict[str, Any] = Body(...)) -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("dashboard_job", status="blocked", job_id=None)
        return context.job_manager.create_job(request)

    @app.get("/api/jobs/{job_id}")
    def job_detail_endpoint(job_id: str) -> dict[str, Any]:
        if context.job_manager is None:
            return _unconfigured_payload("dashboard_job", status="blocked", job_id=job_id)
        job = context.job_manager.get_job(job_id)
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
        if context.job_manager is None:
            return _unconfigured_payload("dashboard_job", status="blocked", job_id=job_id)
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

    return app


def run_dashboard_service(
    config: dict[str, Any] | None = None,
    *,
    config_path: Path | None = None,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        raise DashboardError("Uvicorn is required to run the dashboard.") from exc

    app = create_dashboard_app(config, config_path=config_path, host=host, port=port)
    _prepare_dashboard_service_endpoint(config_path=config_path, host=host, port=port)
    _write_dashboard_service_state(config_path=config_path, host=host, port=port)
    try:
        uvicorn.run(app, host=host, port=port)
    finally:
        _clear_dashboard_service_state(config_path=config_path, host=host, port=port, pid=os.getpid())


def _prepare_dashboard_service_endpoint(*, config_path: Path | None, host: str, port: int) -> None:
    if _dashboard_endpoint_can_bind(host, port):
        _discard_stale_dashboard_service_state(config_path=config_path, host=host, port=port)
        return

    health = _read_dashboard_endpoint_health(host, port)
    if not _is_halpha_dashboard_health(health):
        raise DashboardError(
            f"dashboard port {port} on {host} is already in use by a non-Halpha or unresponsive local service; "
            "stop that service or choose a different --port."
        )

    state_path = _dashboard_service_state_path(config_path)
    state, error = read_json_object(state_path)
    pid = _dashboard_service_state_pid(state)
    if error or not _dashboard_service_state_matches_endpoint(state, host=host, port=port) or pid is None:
        raise DashboardError(
            f"a Halpha dashboard already responds on {host}:{port}, but its local service state is missing or "
            "does not match this endpoint; stop the existing dashboard manually or choose a different --port."
        )
    if pid == os.getpid():
        return
    if not _dashboard_process_is_alive(pid):
        with suppress(OSError):
            state_path.unlink()
        raise DashboardError(
            f"a Halpha dashboard responds on {host}:{port}, but recorded process {pid} is not running; "
            "stop the process using that port or choose a different --port."
        )

    _terminate_dashboard_process(pid)
    if not _wait_for_dashboard_endpoint_release(host, port):
        raise DashboardError(
            f"existing Halpha dashboard process {pid} did not release {host}:{port}; "
            "stop it manually or choose a different --port."
        )


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


def _is_halpha_dashboard_health(health: dict[str, Any] | None) -> bool:
    return isinstance(health, dict) and health.get("service") == DASHBOARD_SERVICE_NAME


def _dashboard_health_url(host: str, port: int) -> str:
    url_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{url_host}:{port}/api/health"


def _dashboard_service_state_path(config_path: Path | None) -> Path:
    return dashboard_control_path("service_state.json")


def _write_dashboard_service_state(*, config_path: Path | None, host: str, port: int) -> None:
    now = utc_now_timestamp()
    write_json(
        _dashboard_service_state_path(config_path),
        {
            "artifact_type": "dashboard_service_state",
            "schema_version": DASHBOARD_SERVICE_SCHEMA_VERSION,
            "service": DASHBOARD_SERVICE_NAME,
            "status": "running",
            "pid": os.getpid(),
            "host": host,
            "port": port,
            "started_at": now,
            "updated_at": now,
            "config": _dashboard_config_status(config_path),
            "health_endpoint": _dashboard_health_url(host, port),
        },
    )


def _clear_dashboard_service_state(*, config_path: Path | None, host: str, port: int, pid: int) -> None:
    state_path = _dashboard_service_state_path(config_path)
    state, error = read_json_object(state_path)
    if error:
        return
    if _dashboard_service_state_pid(state) != pid:
        return
    if not _dashboard_service_state_matches_endpoint(state, host=host, port=port):
        return
    with suppress(OSError):
        state_path.unlink()


def _discard_stale_dashboard_service_state(*, config_path: Path | None, host: str, port: int) -> None:
    state_path = _dashboard_service_state_path(config_path)
    state, error = read_json_object(state_path)
    if error or not _dashboard_service_state_matches_endpoint(state, host=host, port=port):
        return
    pid = _dashboard_service_state_pid(state)
    if pid is None or _dashboard_process_is_alive(pid):
        return
    with suppress(OSError):
        state_path.unlink()


def _dashboard_service_state_matches_endpoint(state: dict[str, Any], *, host: str, port: int) -> bool:
    state_host = str(state.get("host") or "")
    return (
        state.get("artifact_type") == "dashboard_service_state"
        and state.get("service") == DASHBOARD_SERVICE_NAME
        and state.get("port") == port
        and state_host in LOCAL_DASHBOARD_HOSTS
        and host in LOCAL_DASHBOARD_HOSTS
    )


def _dashboard_service_state_pid(state: dict[str, Any]) -> int | None:
    pid = state.get("pid")
    if isinstance(pid, bool):
        return None
    if isinstance(pid, int) and pid > 0:
        return pid
    return None


def _dashboard_process_is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        stdout = (result.stdout or "").strip()
        return result.returncode == 0 and str(pid) in stdout and "No tasks" not in stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_dashboard_process(pid: int) -> None:
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DashboardError(f"existing Halpha dashboard process {pid} could not be stopped: {exc}.") from exc
        if result.returncode != 0:
            reason = (result.stderr or result.stdout or "taskkill failed").strip()
            raise DashboardError(f"existing Halpha dashboard process {pid} could not be stopped: {reason}.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        raise DashboardError(f"existing Halpha dashboard process {pid} could not be stopped: {exc}.") from exc


def _wait_for_dashboard_endpoint_release(host: str, port: int) -> bool:
    deadline = time.monotonic() + DASHBOARD_RESTART_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _dashboard_endpoint_can_bind(host, port):
            return True
        time.sleep(DASHBOARD_RESTART_POLL_SECONDS)
    return _dashboard_endpoint_can_bind(host, port)


def dashboard_health(
    config: dict[str, Any] | None,
    *,
    config_path: Path | None,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> dict[str, Any]:
    validate_dashboard_host(host)
    validate_dashboard_port(port)
    return {
        "artifact_type": "dashboard_health",
        "service": "halpha_dashboard",
        "status": "ok" if config is not None and config_path is not None else "unconfigured",
        "local_only": True,
        "host": host,
        "port": port,
        "config": _dashboard_config_status(config_path),
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
