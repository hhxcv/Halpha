from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
import json
from json import JSONDecodeError
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import ConfigError, load_config
from .data_inspection import DataInspectionError, inspect_local_store_state
from .dashboard_jobs import DashboardJobManager
from .dashboard_monitor import dashboard_monitor_alerts, dashboard_monitor_cycles, dashboard_monitor_summary
from .dashboard_schedule import DashboardScheduleManager
from .dashboard_strategy import dashboard_strategy_research
from .dashboard_ui import dashboard_index_html
from .monitoring import MONITOR_HEALTH_STATE_FILENAME, load_monitor_config
from .outcome_history import OUTCOME_HISTORY_ARTIFACT, OUTCOME_HISTORY_STATE_ARTIFACT
from .run_index import RUN_INDEX_ARTIFACT, run_index_path
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
MAX_PREVIEW_CHARS = 20_000
MAX_PREVIEW_ROWS = 100
MAX_STAGE_ARTIFACT_REFS = 20
MAX_STORE_DRILLDOWN_ITEMS = 12
MAX_DELETION_RUN_ITEMS = 500
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
PRODUCT_CONTRACT_VALIDATION_ARTIFACT = "analysis/product_contract_validation.json"
WORKBENCH_SUMMARY_ARTIFACT = f"{DEFAULT_WORKBENCH_OUTPUT_DIR}/{WORKBENCH_SUMMARY_FILENAME}"
RUN_ARTIFACT_DELETE_CONFIRMATION = "DELETE RUN DATA"
SHARED_DATA_DELETE_CONFIRMATION = "DELETE SHARED DATA"
CONFIG_BACKUP_DIR = "runs/dashboard/config_backups"
SHARED_DATA_ALLOWED_ROOTS = {"data"}
SHARED_DATA_STORE_DELETE_REFS = {
    "research_data_catalog": ("data/research/metadata/research_data_catalog.json",),
    "run_index": (RUN_INDEX_ARTIFACT,),
    "text_event_history": (
        "data/research/metadata/text_event_history_state.json",
        "data/research/text_events",
    ),
    "ohlcv_history": (
        "data/market/metadata/ohlcv_schema.json",
        "data/market/metadata/ohlcv_sync_state.json",
        "data/market/ohlcv",
    ),
    "derivatives_market_history": (
        "data/market/metadata/derivatives_market_schema.json",
        "data/market/metadata/derivatives_market_state.json",
        "data/market/derivatives",
    ),
    "macro_calendar_history": (
        "data/macro/metadata/macro_calendar_schema.json",
        "data/macro/metadata/macro_calendar_state.json",
        "data/macro/calendar",
    ),
    "onchain_flow_history": (
        "data/onchain/metadata/onchain_flow_schema.json",
        "data/onchain/metadata/onchain_flow_state.json",
        "data/onchain/flow",
    ),
    "outcome_history": (
        OUTCOME_HISTORY_STATE_ARTIFACT,
        OUTCOME_HISTORY_ARTIFACT,
        "data/research/outcomes",
    ),
}
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
CONFIG_PROFILE_SECTIONS = (
    "General",
    "Market data",
    "Strategy",
    "Reports",
    "Monitor",
    "Intelligence sources",
    "Storage",
    "Dashboard",
)
CONFIG_PROFILE_FIELDS = (
    {
        "section": "General",
        "label": "Run timezone",
        "path": "run.timezone",
        "control": "select",
        "value_type": "string",
        "options": ("Asia/Shanghai", "UTC"),
        "description": "Default timezone used by local run artifacts.",
    },
    {
        "section": "Dashboard",
        "label": "Display timezone",
        "path": "dashboard.display_timezone",
        "control": "select",
        "value_type": "string",
        "options": ("Asia/Shanghai", "UTC"),
        "description": "Timezone used for timestamps displayed in dashboard pages.",
    },
    {
        "section": "Market data",
        "label": "Enable market data",
        "path": "market.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect market data for research runs.",
    },
    {
        "section": "Market data",
        "label": "Source",
        "path": "market.source",
        "control": "select",
        "value_type": "string",
        "options": ("binance",),
        "description": "Configured public market data source.",
    },
    {
        "section": "Market data",
        "label": "Symbols",
        "path": "market.symbols",
        "control": "tags",
        "value_type": "string_list",
        "description": "Comma-separated market symbols used by the local research pipeline.",
    },
    {
        "section": "Market data",
        "label": "OHLCV timeframes",
        "path": "market.ohlcv.timeframes",
        "control": "multi_select",
        "value_type": "string_list",
        "options": ("1d", "1h"),
        "description": "Reusable OHLCV windows maintained outside single-run artifacts.",
    },
    {
        "section": "Market data",
        "label": "Daily lookback",
        "path": "market.ohlcv.lookback.1d",
        "control": "number",
        "value_type": "positive_int",
        "description": "Number of daily candles to collect.",
    },
    {
        "section": "Market data",
        "label": "Hourly lookback",
        "path": "market.ohlcv.lookback.1h",
        "control": "number",
        "value_type": "positive_int",
        "description": "Number of hourly candles to collect.",
    },
    {
        "section": "Market data",
        "label": "Use proxy",
        "path": "market.proxy.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable a configured proxy without exposing proxy URL values in the dashboard.",
    },
    {
        "section": "Market data",
        "label": "Enable derivatives",
        "path": "market.derivatives.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect public derivatives market evidence when the derivatives source is configured.",
    },
    {
        "section": "Strategy",
        "label": "Enable quant research",
        "path": "quant.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable configured strategy evaluation and backtest evidence.",
    },
    {
        "section": "Reports",
        "label": "Report title",
        "path": "report.title",
        "control": "text",
        "value_type": "string",
        "description": "Human-readable report title used by generated Markdown reports.",
    },
    {
        "section": "Reports",
        "label": "Report language",
        "path": "report.language",
        "control": "select",
        "value_type": "string",
        "options": ("zh-CN",),
        "description": "Final reports are Simplified Chinese unless requested otherwise.",
    },
    {
        "section": "Reports",
        "label": "Enable Codex report",
        "path": "codex.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Allow report generation through the configured local Codex command.",
    },
    {
        "section": "Monitor",
        "label": "Interval seconds",
        "path": "monitor.interval_seconds",
        "control": "number",
        "value_type": "positive_int",
        "description": "Delay between monitor loop cycles.",
    },
    {
        "section": "Monitor",
        "label": "Max cycles",
        "path": "monitor.max_cycles",
        "control": "number",
        "value_type": "positive_int",
        "description": "Maximum monitor cycles for a bounded local loop.",
    },
    {
        "section": "Monitor",
        "label": "Cooldown seconds",
        "path": "monitor.cooldown_seconds",
        "control": "number",
        "value_type": "positive_int",
        "description": "Alert cooldown window.",
    },
    {
        "section": "Monitor",
        "label": "No Codex in monitor",
        "path": "monitor.no_codex",
        "control": "toggle",
        "value_type": "bool",
        "description": "Keep monitor cycles deterministic unless explicit report generation is requested.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable text collection",
        "path": "text.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public text sources.",
    },
    {
        "section": "Intelligence sources",
        "label": "Max text items",
        "path": "text.max_items",
        "control": "number",
        "value_type": "positive_int",
        "description": "Maximum collected text items per run.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable text intelligence",
        "path": "text.intelligence.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Enable local text intelligence evidence generation.",
    },
    {
        "section": "Intelligence sources",
        "label": "Allow model download",
        "path": "text.intelligence.allow_model_download",
        "control": "toggle",
        "value_type": "bool",
        "description": "Permit configured model download when local models are missing.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable macro calendar",
        "path": "macro_calendar.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public scheduled-event evidence.",
    },
    {
        "section": "Intelligence sources",
        "label": "Enable on-chain flow",
        "path": "onchain_flow.enabled",
        "control": "toggle",
        "value_type": "bool",
        "description": "Collect configured public on-chain and exchange-flow evidence.",
    },
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


def dashboard_config_profile(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    fields = [_config_profile_field(config, field) for field in CONFIG_PROFILE_FIELDS]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_profile",
        "status": "available",
        "config": {
            "ref": dashboard_config_ref(config_path),
            "editable": True,
            "requires_confirmation": True,
        },
        "sections": list(CONFIG_PROFILE_SECTIONS),
        "fields": fields,
        "warnings": [],
        "errors": [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "proxy_urls_embedded": False,
            "credentials_embedded": False,
            "raw_config_text_embedded": False,
        },
    }


def dashboard_backup_config(*, config_path: Path) -> dict[str, Any]:
    backup, error = _backup_dashboard_config(config_path)
    if error:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_config_backup",
            "status": "failed",
            "config": {"ref": dashboard_config_ref(config_path)},
            "backup_ref": None,
            "warnings": [],
            "errors": [error],
            "omitted": {"absolute_local_paths_embedded": False},
        }
    base = _config_base(config_path)
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_backup",
        "status": "succeeded",
        "config": {"ref": dashboard_config_ref(config_path)},
        "backup_ref": _safe_ref(backup, base=base) if backup else None,
        "warnings": [],
        "errors": [],
        "omitted": {"absolute_local_paths_embedded": False},
    }


def dashboard_save_config_profile(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    if request.get("confirm") is not True:
        return _config_save_result(
            config,
            config_path=config_path,
            status="blocked",
            errors=["confirm must be true to save dashboard settings."],
        )

    changes = request.get("changes")
    if not isinstance(changes, dict) or not changes:
        return _config_save_result(
            config,
            config_path=config_path,
            status="skipped",
            warnings=["no config changes were submitted."],
        )

    next_config = deepcopy(config)
    changed_paths: list[str] = []
    errors: list[str] = []
    for path, raw_value in sorted(changes.items()):
        if not isinstance(path, str):
            errors.append("config change path must be a string.")
            continue
        field = _config_profile_field_definition(path)
        if field is None:
            errors.append(f"{path} is not editable from the dashboard settings UI.")
            continue
        value, error = _coerce_config_profile_value(raw_value, field)
        if error:
            errors.append(f"{path}: {error}")
            continue
        _set_config_value(next_config, path, value)
        changed_paths.append(path)
    if errors:
        return _config_save_result(config, config_path=config_path, status="failed", errors=errors)

    serialized, error = _serialize_config_yaml(next_config)
    if error:
        return _config_save_result(config, config_path=config_path, status="failed", errors=[error])

    temp_path = config_path.with_name(f".{config_path.name}.dashboard-save.tmp")
    backup_path: Path | None = None
    try:
        temp_path.write_text(serialized, encoding="utf-8")
        try:
            validated = load_config(temp_path)
        except ConfigError as exc:
            return _config_save_result(
                config,
                config_path=config_path,
                status="failed",
                errors=[sanitize_dashboard_message(str(exc), config_path=temp_path)],
            )
        backup_path, backup_error = _backup_dashboard_config(config_path)
        if backup_error:
            return _config_save_result(config, config_path=config_path, status="failed", errors=[backup_error])
        temp_path.replace(config_path)
    except OSError as exc:
        return _config_save_result(
            config,
            config_path=config_path,
            status="failed",
            errors=[sanitize_dashboard_message(f"config file could not be saved: {exc}", config_path=config_path)],
        )
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass

    config.clear()
    config.update(validated)
    base = _config_base(config_path)
    return _config_save_result(
        config,
        config_path=config_path,
        status="succeeded",
        changed_paths=changed_paths,
        backup_ref=_safe_ref(backup_path, base=base) if backup_path else None,
    )


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


def dashboard_artifact_preview(config: dict[str, Any], *, config_path: Path, artifact_path: str) -> dict[str, Any]:
    base = _config_base(config_path)
    resolved = _resolve_preview_path(artifact_path, base=base)
    if isinstance(resolved, dict):
        return resolved

    path, safe_path = resolved
    redactor = _DashboardPreviewRedactor(config, config_path=config_path)
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
        return _json_preview(path, safe_path, redactor=redactor)
    if suffix == ".jsonl":
        return _jsonl_preview(path, safe_path, redactor=redactor)
    if suffix in {".md", ".markdown"}:
        return _text_preview(path, safe_path, preview_kind="markdown", redactor=redactor)
    if suffix in {".txt", ".log", ".csv", ".yaml", ".yml"}:
        return _text_preview(path, safe_path, preview_kind="text", redactor=redactor)
    return _artifact_preview_error(
        safe_path,
        "unsupported",
        f"{suffix or 'unknown'} files are not supported by the dashboard artifact preview API.",
    )


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
    base = _config_base(config_path)
    run_section = _run_artifact_deletion_section(config, config_path=config_path, base=base)
    shared_section = _shared_data_deletion_section(config, config_path=config_path, base=base)
    statuses = [run_section["status"], shared_section["status"]]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_data_deletion_plan",
        "status": _overall_status(statuses),
        "confirmations": {
            "run_artifacts": RUN_ARTIFACT_DELETE_CONFIRMATION,
            "shared_data": SHARED_DATA_DELETE_CONFIRMATION,
        },
        "run_artifacts": run_section,
        "shared_data": shared_section,
        "warnings": [
            *run_section.get("warnings", []),
            *shared_section.get("warnings", []),
        ],
        "errors": [
            *run_section.get("errors", []),
            *shared_section.get("errors", []),
        ],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "raw_shared_data_embedded": False,
            "run_artifact_contents_embedded": False,
        },
    }


def dashboard_delete_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    kind = request.get("kind")
    if kind == "run_artifacts":
        return _delete_run_artifacts(config, config_path=config_path, request=request)
    if kind == "shared_data":
        return _delete_shared_data(config, config_path=config_path, request=request)
    return _deletion_result(
        kind=str(kind or "unknown"),
        status="failed",
        errors=["kind must be run_artifacts or shared_data."],
    )


def _config_profile_field(config: dict[str, Any], field: dict[str, Any]) -> dict[str, Any]:
    path = str(field["path"])
    value = _get_config_value(config, path)
    if value is None:
        value = _config_profile_default(field)
    result = {
        "section": field["section"],
        "label": field["label"],
        "path": path,
        "control": field["control"],
        "value_type": field["value_type"],
        "value": value,
        "description": field.get("description") or "",
    }
    options = field.get("options")
    if isinstance(options, tuple):
        result["options"] = list(options)
    return result


def _config_profile_field_definition(path: str) -> dict[str, Any] | None:
    for field in CONFIG_PROFILE_FIELDS:
        if field.get("path") == path:
            return field
    return None


def _config_profile_default(field: dict[str, Any]) -> Any:
    value_type = field.get("value_type")
    if value_type == "bool":
        return False
    if value_type == "positive_int":
        return 1
    if value_type == "string_list":
        options = field.get("options")
        return [options[0]] if isinstance(options, tuple) and options else []
    options = field.get("options")
    if isinstance(options, tuple) and options:
        return options[0]
    return ""


def _get_config_value(config: dict[str, Any], path: str) -> Any:
    current: Any = config
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_config_value(config: dict[str, Any], path: str, value: Any) -> None:
    current: dict[str, Any] = config
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _coerce_config_profile_value(raw_value: Any, field: dict[str, Any]) -> tuple[Any, str | None]:
    value_type = field.get("value_type")
    options = field.get("options")
    if value_type == "bool":
        if isinstance(raw_value, bool):
            return raw_value, None
        return None, "value must be true or false."
    if value_type == "positive_int":
        if isinstance(raw_value, bool):
            return None, "value must be a positive integer."
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None, "value must be a positive integer."
        if value <= 0:
            return None, "value must be a positive integer."
        return value, None
    if value_type == "string_list":
        if not isinstance(raw_value, list):
            return None, "value must be a list of strings."
        values = [str(value).strip() for value in raw_value if str(value).strip()]
        if not values:
            return None, "value must include at least one string."
        if isinstance(options, tuple):
            unsupported = sorted(set(values) - set(str(option) for option in options))
            if unsupported:
                return None, f"unsupported value(s): {', '.join(unsupported)}."
        return values, None
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None, "value must be a non-empty string."
    value = raw_value.strip()
    if isinstance(options, tuple) and value not in options:
        return None, f"value must be one of: {', '.join(str(option) for option in options)}."
    return value, None


def _serialize_config_yaml(config: dict[str, Any]) -> tuple[str, str | None]:
    try:
        import yaml
    except ModuleNotFoundError:
        return "", "PyYAML is required to save YAML config files."
    try:
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False), None
    except yaml.YAMLError as exc:
        return "", f"config could not be serialized as YAML: {exc}"


def _backup_dashboard_config(config_path: Path) -> tuple[Path | None, str | None]:
    base = _config_base(config_path)
    source = config_path if config_path.is_absolute() else base / config_path.name
    if not source.exists():
        return None, f"{dashboard_config_ref(config_path)} was not found."
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in source.stem) or "config"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = base / CONFIG_BACKUP_DIR
    backup_path = backup_dir / f"{safe_stem}-{stamp}.yaml.bak"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, backup_path)
    except OSError as exc:
        return None, sanitize_dashboard_message(f"config backup could not be created: {exc}", config_path=config_path)
    return backup_path, None


def _config_save_result(
    config: dict[str, Any],
    *,
    config_path: Path,
    status: str,
    changed_paths: list[str] | None = None,
    backup_ref: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_config_save_result",
        "status": status,
        "config": {"ref": dashboard_config_ref(config_path)},
        "changed_paths": changed_paths or [],
        "backup_ref": backup_ref,
        "profile": dashboard_config_profile(config, config_path=config_path),
        "warnings": warnings or [],
        "errors": errors or [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "raw_config_text_embedded": False,
            "credentials_embedded": False,
        },
    }


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
    return _fallback_latest_run(connection, succeeded_only=True) or _fallback_latest_run(
        connection,
        succeeded_only=False,
    )


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


class _DashboardPreviewRedactor:
    _private_key_parts = {
        "account",
        "cookie",
        "credential",
        "endpoint",
        "host",
        "password",
        "path",
        "port",
        "private",
        "proxy",
        "secret",
        "token",
        "url",
        "user",
    }

    def __init__(self, config: dict[str, Any], *, config_path: Path) -> None:
        self.private_values = _dashboard_private_values(config, config_path=config_path)

    def redact_value(self, value: Any, *, key: str | None = None) -> Any:
        if key and self._is_private_key(key):
            return "<redacted>"
        if isinstance(value, dict):
            return {str(item_key): self.redact_value(item, key=str(item_key)) for item_key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        if isinstance(value, str):
            return self.redact_text(value)
        return value

    def redact_text(self, text: str) -> str:
        redacted = text
        for value in self.private_values:
            redacted = redacted.replace(value, "<redacted>")
        return "\n".join(self._redact_private_line(line) for line in redacted.split("\n"))

    def _redact_private_line(self, line: str) -> str:
        stripped = line.lstrip()
        key, separator, value = stripped.partition(":")
        if not separator or not value:
            return line
        clean_key = key.strip().strip("'\"")
        if not clean_key or not self._is_private_key(clean_key):
            return line
        indent = line[: len(line) - len(stripped)]
        return f"{indent}{key}: <redacted>"

    @staticmethod
    def _is_private_key(key: str) -> bool:
        lowered = key.lower()
        if lowered == "report":
            return False
        return any(part in lowered for part in _DashboardPreviewRedactor._private_key_parts)


def _dashboard_private_values(config: dict[str, Any], *, config_path: Path) -> list[str]:
    values = set()
    base = _config_base(config_path)
    if base.is_absolute():
        values.update({str(base), base.as_posix()})
    if config_path.is_absolute():
        values.update({str(config_path), config_path.as_posix()})
    try:
        values.update({str(config_path.resolve()), config_path.resolve().as_posix()})
    except OSError:
        pass

    def visit(value: Any, key_path: tuple[str, ...]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                visit(item, (*key_path, str(key)))
            return
        if isinstance(value, list):
            for item in value:
                visit(item, key_path)
            return
        if not isinstance(value, str) or not value:
            return
        if any(_DashboardPreviewRedactor._is_private_key(key) for key in key_path):
            values.add(value)

    visit(config, ())
    return sorted(values, key=len, reverse=True)


def _json_preview(path: Path, safe_path: str, *, redactor: _DashboardPreviewRedactor) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    if truncated:
        return _artifact_preview_payload(
            safe_path,
            "json",
            redactor.redact_text(text),
            truncated=True,
            warnings=["JSON file was truncated before parsing."],
        )
    try:
        loaded = json.loads(text)
    except JSONDecodeError as exc:
        return _artifact_preview_error(safe_path, "failed", f"{safe_path} is not valid JSON: {exc.msg}.")
    preview, omitted = _bounded_json(redactor.redact_value(loaded))
    return _artifact_preview_payload(
        safe_path,
        "json",
        preview,
        truncated=False,
        omitted=omitted,
    )


def _jsonl_preview(path: Path, safe_path: str, *, redactor: _DashboardPreviewRedactor) -> dict[str, Any]:
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
            records.append(redactor.redact_value(json.loads(line)))
        except JSONDecodeError as exc:
            parse_errors.append(f"line {index + 1}: {exc.msg}")
            records.append(redactor.redact_text(line))
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


def _text_preview(
    path: Path,
    safe_path: str,
    *,
    preview_kind: str,
    redactor: _DashboardPreviewRedactor,
) -> dict[str, Any]:
    text, truncated, error = _read_bounded_text(path)
    if error:
        return _artifact_preview_error(safe_path, "failed", error)
    return _artifact_preview_payload(safe_path, preview_kind, redactor.redact_text(text), truncated=truncated)


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


def _dashboard_store_section(section: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    artifact = section.get("artifact")
    reason = section.get("reason")
    name = str(section.get("name") or "unknown")
    fields = _bounded_mapping(section.get("fields"))
    extra = _bounded_mapping(section.get("extra"))
    source_artifacts = [artifact] if isinstance(artifact, str) and artifact else []
    warnings = [reason] if isinstance(reason, str) and reason else []
    return {
        "name": name,
        "title": DATA_STORE_TITLES.get(name, str(section.get("name") or "Unknown")),
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


def _run_artifact_deletion_section(
    config: dict[str, Any],
    *,
    config_path: Path,
    base: Path,
) -> dict[str, Any]:
    run_root = _dashboard_run_output_dir(config, base=base)
    root_safe = _safe_ref(run_root, base=base)
    root_blocked = _deletion_root_block_reason(run_root, base=base)
    runs_payload = dashboard_runs(config_path=config_path, limit=MAX_DELETION_RUN_ITEMS)
    runs = _list(runs_payload.get("runs"))
    items = [
        _run_artifact_delete_item(run, run_root=run_root, root_blocked=root_blocked, base=base)
        for run in runs
        if isinstance(run, dict)
    ]
    blocked_count = sum(1 for item in items if not item["deletable"])
    warnings = _string_list(runs_payload.get("warnings"))
    if root_blocked:
        warnings.append(root_blocked)
    return {
        "status": "partial" if blocked_count else str(runs_payload.get("status") or "unknown"),
        "run_output_dir": root_safe,
        "confirmation_text": RUN_ARTIFACT_DELETE_CONFIRMATION,
        "items": items,
        "counts": {
            "runs": len(items),
            "deletable": sum(1 for item in items if item["deletable"]),
            "blocked": blocked_count,
        },
        "warnings": warnings,
        "errors": _string_list(runs_payload.get("errors")),
    }


def _shared_data_deletion_section(
    config: dict[str, Any],
    *,
    config_path: Path,
    base: Path,
) -> dict[str, Any]:
    stores_payload = dashboard_data_stores(config, config_path=config_path)
    stores = _list(stores_payload.get("stores"))
    items = [
        _shared_data_delete_item(store, config=config, base=base)
        for store in stores
        if isinstance(store, dict)
    ]
    blocked_count = sum(1 for item in items if not item["deletable"])
    warnings = [
        "shared data may be reused by multiple reports and future runs; deletion requires explicit confirmation.",
        *_string_list(stores_payload.get("warnings")),
    ]
    return {
        "status": "partial" if blocked_count else str(stores_payload.get("status") or "unknown"),
        "allowed_roots": sorted(SHARED_DATA_ALLOWED_ROOTS),
        "confirmation_text": SHARED_DATA_DELETE_CONFIRMATION,
        "items": items,
        "counts": {
            "stores": len(items),
            "deletable": sum(1 for item in items if item["deletable"]),
            "blocked": blocked_count,
        },
        "warnings": warnings,
        "errors": _string_list(stores_payload.get("errors")),
    }


def _run_artifact_delete_item(
    run: dict[str, Any],
    *,
    run_root: Path,
    root_blocked: str | None,
    base: Path,
) -> dict[str, Any]:
    run_id = str(run.get("run_id") or "")
    target, safe_ref, reason = _resolve_deletion_ref(str(run.get("run_dir") or ""), base=base)
    blocked_reason = root_blocked or reason
    if not blocked_reason and target is not None:
        if not _is_path_within(target, run_root):
            blocked_reason = "run directory is outside the configured run output directory."
        elif _same_path(target, run_root):
            blocked_reason = "run output root cannot be deleted from a run selection."
    return {
        "run_id": run_id,
        "title": run_id,
        "status": str(run.get("status") or "unknown"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "warning_count": _int(run.get("warning_count")),
        "error_count": _int(run.get("error_count")),
        "run_dir": safe_ref,
        "manifest": run.get("manifest"),
        "exists": bool(target and target.exists()),
        "deletable": blocked_reason is None,
        "blocked_reason": blocked_reason,
    }


def _shared_data_delete_item(
    store: dict[str, Any],
    *,
    config: dict[str, Any],
    base: Path,
) -> dict[str, Any]:
    name = str(store.get("name") or "")
    refs = _shared_store_delete_refs(name, store, config=config)
    records = [_shared_delete_ref_record(ref, base=base) for ref in refs]
    existing_records = [record for record in records if record["exists"]]
    blocked_records = [record for record in records if not record["deletable"]]
    blocked_reason = None
    if blocked_records:
        blocked_reason = "one or more refs are outside the shared-data deletion boundary."
    elif not existing_records:
        blocked_reason = "no existing shared data refs were found for this store."
    return {
        "name": name,
        "title": str(store.get("title") or name),
        "status": str(store.get("status") or "unknown"),
        "group": _data_store_category(name),
        "records": _int(_dict(store.get("fields")).get("records")),
        "delete_refs": records,
        "deletable": blocked_reason is None,
        "blocked_reason": blocked_reason,
        "warnings": _string_list(store.get("warnings")),
        "errors": _string_list(store.get("errors")),
    }


def _shared_store_delete_refs(name: str, store: dict[str, Any], *, config: dict[str, Any]) -> list[str]:
    refs: list[str] = list(SHARED_DATA_STORE_DELETE_REFS.get(name, ()))
    if name == "ohlcv_history":
        refs.extend(_configured_ohlcv_storage_refs(config))
    if name == "outcome_history":
        fields = _dict(store.get("fields"))
        refs.extend(
            str(value)
            for value in (fields.get("history"), fields.get("storage_path"))
            if isinstance(value, str) and value
        )
    return _unique_refs(refs)


def _configured_ohlcv_storage_refs(config: dict[str, Any]) -> list[str]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    storage_dir = ohlcv.get("storage_dir")
    return [storage_dir] if isinstance(storage_dir, str) and storage_dir.strip() else []


def _shared_delete_ref_record(ref: str, *, base: Path) -> dict[str, Any]:
    target, safe_ref, reason = _resolve_deletion_ref(ref, base=base)
    blocked_reason = reason
    if not blocked_reason and target is not None:
        parts = Path(safe_ref).parts
        if not parts or parts[0] not in SHARED_DATA_ALLOWED_ROOTS:
            blocked_reason = "shared data deletion is limited to configured project data refs."
        elif len(parts) == 1:
            blocked_reason = "shared data root cannot be deleted as one operation."
    return {
        "ref": safe_ref,
        "exists": bool(target and target.exists()),
        "kind": "directory" if target and target.exists() and target.is_dir() and not target.is_symlink() else "file",
        "deletable": blocked_reason is None,
        "blocked_reason": blocked_reason,
    }


def _delete_run_artifacts(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    if request.get("confirm") != RUN_ARTIFACT_DELETE_CONFIRMATION:
        return _deletion_result(
            kind="run_artifacts",
            status="blocked",
            errors=["confirmation text does not match run artifact deletion requirement."],
        )
    requested_ids = _unique_refs(str(item) for item in _list(request.get("run_ids")) if isinstance(item, str))
    if not requested_ids:
        return _deletion_result(
            kind="run_artifacts",
            status="failed",
            errors=["run_ids must contain at least one run id."],
        )

    base = _config_base(config_path)
    plan = dashboard_data_deletion_plan(config, config_path=config_path)
    candidates = {
        str(item.get("run_id")): item
        for item in _list(_dict(plan.get("run_artifacts")).get("items"))
        if isinstance(item, dict)
    }
    deleted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    index_deleted_ids: list[str] = []

    for run_id in requested_ids:
        item = candidates.get(run_id)
        if item is None:
            blocked.append({"id": run_id, "reason": "run id is not present in the deletion plan."})
            continue
        if not item.get("deletable"):
            blocked.append({"id": run_id, "reason": item.get("blocked_reason") or "run is not deletable."})
            continue
        target, safe_ref, reason = _resolve_deletion_ref(str(item.get("run_dir") or ""), base=base)
        if reason or target is None:
            blocked.append({"id": run_id, "reason": reason or "run directory could not be resolved."})
            continue
        error = _delete_local_path(target)
        if error:
            blocked.append({"id": run_id, "ref": safe_ref, "reason": error})
            continue
        if item.get("exists"):
            deleted.append({"id": run_id, "ref": safe_ref})
        else:
            skipped.append({"id": run_id, "ref": safe_ref, "reason": "run directory was already missing."})
        index_deleted_ids.append(run_id)

    index_result = _delete_run_index_records(config_path, index_deleted_ids)
    warnings = _string_list(index_result.get("warnings"))
    errors = _string_list(index_result.get("errors"))
    status = _deletion_status(deleted=deleted, skipped=skipped, blocked=blocked, errors=errors)
    return _deletion_result(
        kind="run_artifacts",
        status=status,
        deleted=deleted,
        skipped=skipped,
        blocked=blocked,
        warnings=warnings,
        errors=errors,
        index=index_result,
    )


def _delete_shared_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    if request.get("confirm") != SHARED_DATA_DELETE_CONFIRMATION:
        return _deletion_result(
            kind="shared_data",
            status="blocked",
            errors=["confirmation text does not match shared data deletion requirement."],
        )
    requested_names = _unique_refs(str(item) for item in _list(request.get("store_names")) if isinstance(item, str))
    if not requested_names:
        return _deletion_result(
            kind="shared_data",
            status="failed",
            errors=["store_names must contain at least one shared data store name."],
        )

    base = _config_base(config_path)
    plan = dashboard_data_deletion_plan(config, config_path=config_path)
    candidates = {
        str(item.get("name")): item
        for item in _list(_dict(plan.get("shared_data")).get("items"))
        if isinstance(item, dict)
    }
    deleted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for name in requested_names:
        item = candidates.get(name)
        if item is None:
            blocked.append({"id": name, "reason": "store name is not present in the deletion plan."})
            continue
        if not item.get("deletable"):
            blocked.append({"id": name, "reason": item.get("blocked_reason") or "store is not deletable."})
            continue
        for record in _list(item.get("delete_refs")):
            if not isinstance(record, dict):
                continue
            ref = str(record.get("ref") or "")
            if not record.get("deletable"):
                blocked.append({"id": name, "ref": ref, "reason": record.get("blocked_reason") or "ref is not deletable."})
                continue
            target, safe_ref, reason = _resolve_deletion_ref(ref, base=base)
            if reason or target is None:
                blocked.append({"id": name, "ref": ref, "reason": reason or "ref could not be resolved."})
                continue
            if not target.exists() and not target.is_symlink():
                skipped.append({"id": name, "ref": safe_ref, "reason": "ref was already missing."})
                continue
            error = _delete_local_path(target)
            if error:
                blocked.append({"id": name, "ref": safe_ref, "reason": error})
            else:
                deleted.append({"id": name, "ref": safe_ref})

    status = _deletion_status(deleted=deleted, skipped=skipped, blocked=blocked, errors=[])
    return _deletion_result(
        kind="shared_data",
        status=status,
        deleted=deleted,
        skipped=skipped,
        blocked=blocked,
        warnings=["shared data deletion completed only for explicitly selected, project-local refs."],
    )


def _deletion_result(
    *,
    kind: str,
    status: str,
    deleted: list[dict[str, Any]] | None = None,
    skipped: list[dict[str, Any]] | None = None,
    blocked: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": 1,
        "artifact_type": "dashboard_data_deletion_result",
        "kind": kind,
        "status": status,
        "deleted": deleted or [],
        "skipped": skipped or [],
        "blocked": blocked or [],
        "warnings": warnings or [],
        "errors": errors or [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "deleted_contents_embedded": False,
        },
    }
    if index is not None:
        result["index"] = index
    return result


def _deletion_status(
    *,
    deleted: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    errors: list[str],
) -> str:
    if errors:
        return "failed"
    if blocked and not (deleted or skipped):
        return "blocked"
    if blocked:
        return "partial"
    if deleted or skipped:
        return "succeeded"
    return "missing"


def _delete_run_index_records(config_path: Path, run_ids: list[str]) -> dict[str, Any]:
    if not run_ids:
        return {"status": "skipped", "deleted_run_ids": [], "warnings": [], "errors": []}
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return {
            "status": "missing",
            "deleted_run_ids": [],
            "warnings": ["local run index was not found."],
            "errors": [],
        }
    deleted: list[str] = []
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            with connection:
                connection.execute("PRAGMA foreign_keys = ON")
                for run_id in run_ids:
                    row = connection.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                    if row is None:
                        continue
                    connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
                    deleted.append(run_id)
                connection.execute(
                    "DELETE FROM run_latest WHERE run_id IN (%s)" % ",".join("?" for _ in run_ids),
                    run_ids,
                )
                _refresh_run_latest_records(connection)
    except sqlite3.Error as exc:
        return {
            "status": "failed",
            "deleted_run_ids": deleted,
            "warnings": [],
            "errors": [f"{RUN_INDEX_ARTIFACT} could not be updated: {exc}"],
        }
    return {"status": "succeeded", "deleted_run_ids": deleted, "warnings": [], "errors": []}


def _refresh_run_latest_records(connection: sqlite3.Connection) -> None:
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    connection.execute("DELETE FROM run_latest WHERE key IN (?, ?)", ("latest_run", "latest_successful_run"))
    latest = _fallback_latest_run(connection, succeeded_only=False)
    if latest:
        connection.execute(
            "INSERT OR REPLACE INTO run_latest (key, run_id, updated_at) VALUES (?, ?, ?)",
            ("latest_run", latest[0], updated_at),
        )
    latest_successful = _fallback_latest_run(connection, succeeded_only=True)
    if latest_successful:
        connection.execute(
            "INSERT OR REPLACE INTO run_latest (key, run_id, updated_at) VALUES (?, ?, ?)",
            ("latest_successful_run", latest_successful[0], updated_at),
        )


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


def _delete_local_path(path: Path) -> str | None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
            return None
        if path.is_dir():
            shutil.rmtree(path)
            return None
        return None
    except OSError as exc:
        detail = exc.strerror or exc.__class__.__name__
        return f"{path.name} could not be deleted: {detail}"


def _dashboard_run_output_dir(config: dict[str, Any], *, base: Path) -> Path:
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    output_dir = Path(str(run.get("output_dir") or "runs"))
    return output_dir if output_dir.is_absolute() else base / output_dir


def _deletion_root_block_reason(path: Path, *, base: Path) -> str | None:
    if not _is_path_within(path, base):
        return "configured deletion root is outside the project boundary."
    return None


def _resolve_deletion_ref(ref: str, *, base: Path) -> tuple[Path | None, str, str | None]:
    raw = str(ref or "").replace("\\", "/").strip()
    if not raw:
        return None, "", "ref is required."
    if raw == EXTERNAL_ARTIFACT_REF:
        return None, EXTERNAL_ARTIFACT_REF, "external artifact refs cannot be deleted from the dashboard."
    path = Path(raw)
    if not path.is_absolute() and any(part in {"", ".", ".."} for part in path.parts):
        return None, raw, "ref must not contain traversal segments."
    target = path if path.is_absolute() else base / path
    try:
        resolved = target.resolve()
        resolved.relative_to(base.resolve())
    except (OSError, ValueError):
        return None, EXTERNAL_ARTIFACT_REF, "ref must stay under the configured project root."
    return target, _safe_ref(resolved, base=base), None


def _is_path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _unique_refs(values: Any) -> list[str]:
    unique: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        clean = value.strip()
        if clean and clean not in unique:
            unique.append(clean)
    return unique


def _run_list_record(row: Any, artifacts: dict[str, list[str]], *, base: Path) -> dict[str, Any]:
    run_id = str(row[0])
    run_dir = _resolve_ref(str(row[1]), base=base)
    manifest_path = _resolve_ref(str(row[9]), base=base)
    report_paths = artifacts.get("report", [])
    integrity_state = _run_integrity_state(run_dir, manifest_path, base=base)
    report_state = _run_report_state(
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
    }


def _run_integrity_state(run_dir: Path, manifest_path: Path, *, base: Path) -> dict[str, Any]:
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


def _run_report_state(run_dir: Path, report_ref: str | None, *, codex_status: Any, base: Path) -> dict[str, Any]:
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
    if path.name == REJECTED_EXTERNAL_REF_NAME:
        return {}, "external artifact reference was rejected."
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


def _resolve_ref(value: str, *, base: Path) -> Path:
    path = Path(value)
    target = path if path.is_absolute() else base / path
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return base / REJECTED_EXTERNAL_REF_NAME
    return target


def _safe_ref(path: Path, *, base: Path) -> str:
    if path.name == REJECTED_EXTERNAL_REF_NAME:
        return EXTERNAL_ARTIFACT_REF
    target = path if path.is_absolute() else base / path
    try:
        return target.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, ValueError):
        return EXTERNAL_ARTIFACT_REF


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


def _recorded_artifact_ref(manifest: dict[str, Any], key: str) -> str | None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    value = artifacts.get(key)
    return value if isinstance(value, str) and value else None


def _report_state(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    recorded = _recorded_artifact_ref(manifest, "report")
    codex_status = _dict(manifest.get("codex")).get("status")
    if recorded:
        if (run_dir / recorded).is_file():
            return {"status": "available", "artifact": recorded}
        return {"status": "missing", "artifact": recorded, "warning": "recorded report artifact was not found."}
    if codex_status in {"skipped", "disabled", "not_run"}:
        return {"status": str(codex_status), "artifact": None}
    return {"status": "missing", "artifact": None}


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


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _warning_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("warnings")))


def _error_count(value: dict[str, Any]) -> int:
    return len(_list(value.get("errors")))
