from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .dashboard_jobs import DashboardJobManager
from .storage import config_base as _config_base, write_json


DASHBOARD_SCHEDULES_DIR = "runs/dashboard/schedules"
DAILY_REPORT_SCHEDULE_FILENAME = "daily_report_schedule.json"
DAILY_REPORT_SCHEDULE_ARTIFACT = f"{DASHBOARD_SCHEDULES_DIR}/{DAILY_REPORT_SCHEDULE_FILENAME}"
MAX_LINKED_JOB_IDS = 20
SUPPORTED_DAILY_REPORT_JOB_INTENTS = {"run", "run_no_codex"}
DEFAULT_DAILY_REPORT_JOB_INTENT = "run"
DEFAULT_DASHBOARD_TIMEZONE = "Asia/Shanghai"


class DashboardScheduleManager:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: Path,
        job_manager: DashboardJobManager,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.base = _config_base(self.config_path)
        self.job_manager = job_manager
        self.daily_report_path = self.base / DAILY_REPORT_SCHEDULE_ARTIFACT

    def read_daily_report_schedule(self) -> dict[str, Any]:
        if not self.daily_report_path.exists():
            state = self._default_daily_report_state(status="missing", persisted=False)
            state["warnings"] = [f"{DAILY_REPORT_SCHEDULE_FILENAME} was not found."]
            return state
        try:
            data = json.loads(self.daily_report_path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            state = self._default_daily_report_state(status="failed", persisted=True)
            state["errors"] = [f"{DAILY_REPORT_SCHEDULE_FILENAME} is not valid JSON: {exc.msg}."]
            return state
        except OSError as exc:
            state = self._default_daily_report_state(status="failed", persisted=True)
            state["errors"] = [f"{DAILY_REPORT_SCHEDULE_FILENAME} could not be read: {exc}"]
            return state
        if not isinstance(data, dict):
            state = self._default_daily_report_state(status="failed", persisted=True)
            state["errors"] = [f"{DAILY_REPORT_SCHEDULE_FILENAME} must be a JSON object."]
            return state
        return self._normalized_daily_report_state(data)

    def update_daily_report_schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        current = self.read_daily_report_schedule()
        if current["status"] == "failed":
            return current
        update = request if isinstance(request, dict) else {}
        error = self._validate_update_keys(update)
        if error:
            return self._blocked_daily_report_state(current, error)
        settings = dict(current.get("settings") or {})
        for key in ("time_of_day", "timezone", "job_intent"):
            if key in update:
                settings[key] = update[key]
        validation_error = self._validate_settings(settings)
        if validation_error:
            return self._blocked_daily_report_state(current, validation_error)
        enabled = current.get("enabled") is True
        if "enabled" in update:
            if not isinstance(update["enabled"], bool):
                return self._blocked_daily_report_state(current, "enabled must be a boolean.")
            enabled = update["enabled"]
        return self._write_daily_report_state(current, enabled=enabled, settings=settings)

    def enable_daily_report_schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        update = dict(request if isinstance(request, dict) else {})
        update["enabled"] = True
        return self.update_daily_report_schedule(update)

    def disable_daily_report_schedule(self) -> dict[str, Any]:
        return self.update_daily_report_schedule({"enabled": False})

    def trigger_daily_report_schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        current = self.read_daily_report_schedule()
        if current["status"] == "failed":
            return {
                "schema_version": 1,
                "artifact_type": "dashboard_daily_report_schedule_trigger",
                "status": "failed",
                "schedule": current,
                "job": None,
                "warnings": [],
                "errors": list(current.get("errors") or []),
            }
        payload = request if isinstance(request, dict) else {}
        intent = str(
            payload.get("job_intent")
            or (current.get("settings") or {}).get("job_intent")
            or DEFAULT_DAILY_REPORT_JOB_INTENT
        )
        if intent not in SUPPORTED_DAILY_REPORT_JOB_INTENTS:
            supported = ", ".join(sorted(SUPPORTED_DAILY_REPORT_JOB_INTENTS))
            return self._blocked_trigger_response(current, f"job_intent must be one of: {supported}.")
        params: dict[str, Any] = {}
        if intent == "run":
            if payload.get("confirm_codex") is not True:
                return self._blocked_trigger_response(
                    current,
                    "confirm_codex must be true to trigger a Codex-capable daily report job.",
                )
            params["confirm_codex"] = True
        job = self.job_manager.create_job({"intent": intent, "params": params})
        updated = self._record_triggered_job(current, job)
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_daily_report_schedule_trigger",
            "status": "available",
            "schedule": updated,
            "job": job,
            "warnings": [],
            "errors": [],
        }

    def _default_daily_report_state(self, *, status: str, persisted: bool) -> dict[str, Any]:
        now = _utc_now()
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_daily_report_schedule",
            "schedule_id": "daily_report",
            "status": status,
            "enabled": False,
            "persisted": persisted,
            "schedule_kind": "daily_report",
            "settings": {
                "time_of_day": "08:00",
                "timezone": _configured_timezone(self.config),
                "job_intent": DEFAULT_DAILY_REPORT_JOB_INTENT,
            },
            "report_generation": _report_generation_state({"job_intent": DEFAULT_DAILY_REPORT_JOB_INTENT}),
            "next_run_at": None,
            "last_run_at": None,
            "last_job_id": None,
            "linked_job_ids": [],
            "linked_report_refs": [],
            "runtime_boundary": {
                "runs_only_while_dashboard_active": True,
                "hidden_service": False,
                "hosted_scheduler": False,
                "os_scheduler": False,
                "automatic_dispatch": "not_implemented",
            },
            "source_artifacts": [DAILY_REPORT_SCHEDULE_ARTIFACT],
            "created_at": now,
            "updated_at": now,
            "warnings": [],
            "errors": [],
        }

    def _normalized_daily_report_state(self, data: dict[str, Any]) -> dict[str, Any]:
        default = self._default_daily_report_state(status="available", persisted=True)
        settings = dict(default["settings"])
        if isinstance(data.get("settings"), dict):
            settings.update(
                {key: data["settings"].get(key) for key in settings if data["settings"].get(key) is not None}
            )
        enabled = data.get("enabled") is True
        next_run_at = None
        if enabled:
            validation_error = self._validate_settings(settings)
            if validation_error:
                default["status"] = "failed"
                default["errors"] = [validation_error]
                return default
            next_run_at = _next_run_at(settings["time_of_day"], settings["timezone"])
        default.update(
            {
                "status": "available",
                "enabled": enabled,
                "persisted": True,
                "settings": settings,
                "report_generation": _report_generation_state(settings),
                "next_run_at": next_run_at if enabled else None,
                "last_run_at": data.get("last_run_at"),
                "last_job_id": data.get("last_job_id"),
                "linked_job_ids": _bounded_string_list(data.get("linked_job_ids"), limit=MAX_LINKED_JOB_IDS),
                "linked_report_refs": _bounded_string_list(data.get("linked_report_refs"), limit=MAX_LINKED_JOB_IDS),
                "created_at": data.get("created_at") or default["created_at"],
                "updated_at": data.get("updated_at") or default["updated_at"],
                "warnings": _bounded_string_list(data.get("warnings"), limit=20),
                "errors": _bounded_string_list(data.get("errors"), limit=20),
            }
        )
        return default

    def _write_daily_report_state(
        self,
        current: dict[str, Any],
        *,
        enabled: bool,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        now = _utc_now()
        state = self._default_daily_report_state(status="available", persisted=True)
        state.update(
            {
                "enabled": enabled,
                "settings": settings,
                "report_generation": _report_generation_state(settings),
                "next_run_at": _next_run_at(settings["time_of_day"], settings["timezone"]) if enabled else None,
                "last_run_at": current.get("last_run_at"),
                "last_job_id": current.get("last_job_id"),
                "linked_job_ids": _bounded_string_list(current.get("linked_job_ids"), limit=MAX_LINKED_JOB_IDS),
                "linked_report_refs": _bounded_string_list(current.get("linked_report_refs"), limit=MAX_LINKED_JOB_IDS),
                "created_at": current.get("created_at") or now,
                "updated_at": now,
            }
        )
        write_json(self.daily_report_path, state)
        return state

    def _record_triggered_job(self, current: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        default_settings = self._default_daily_report_state(status="available", persisted=True)["settings"]
        settings = dict(current.get("settings") or default_settings)
        now = _utc_now()
        linked_job_ids = [
            str(job.get("job_id") or ""),
            *_bounded_string_list(current.get("linked_job_ids"), limit=MAX_LINKED_JOB_IDS),
        ]
        linked_job_ids = _unique(linked_job_ids)[:MAX_LINKED_JOB_IDS]
        linked_report_refs = _bounded_string_list(current.get("linked_report_refs"), limit=MAX_LINKED_JOB_IDS)
        report_ref = (job.get("result_refs") or {}).get("report") if isinstance(job.get("result_refs"), dict) else None
        if isinstance(report_ref, str) and report_ref:
            linked_report_refs = _unique([report_ref, *linked_report_refs])[:MAX_LINKED_JOB_IDS]
        state = self._default_daily_report_state(status="available", persisted=True)
        enabled = current.get("enabled") is True
        state.update(
            {
                "enabled": enabled,
                "settings": settings,
                "report_generation": _report_generation_state(settings),
                "next_run_at": _next_run_at(settings["time_of_day"], settings["timezone"]) if enabled else None,
                "last_run_at": now,
                "last_job_id": job.get("job_id"),
                "linked_job_ids": linked_job_ids,
                "linked_report_refs": linked_report_refs,
                "created_at": current.get("created_at") or now,
                "updated_at": now,
            }
        )
        write_json(self.daily_report_path, state)
        return state

    def _blocked_daily_report_state(self, current: dict[str, Any], error: str) -> dict[str, Any]:
        state = dict(current)
        state["status"] = "blocked"
        state["errors"] = [error]
        state["updated_at"] = _utc_now()
        return state

    def _blocked_trigger_response(self, current: dict[str, Any], error: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_daily_report_schedule_trigger",
            "status": "blocked",
            "schedule": self._blocked_daily_report_state(current, error),
            "job": None,
            "warnings": [],
            "errors": [error],
        }

    def _validate_update_keys(self, update: dict[str, Any]) -> str | None:
        supported = {"enabled", "time_of_day", "timezone", "job_intent"}
        extra = sorted(set(update) - supported)
        if extra:
            return f"unsupported daily report schedule field(s): {', '.join(extra)}."
        return None

    def _validate_settings(self, settings: dict[str, Any]) -> str | None:
        time_of_day = settings.get("time_of_day")
        timezone_name = settings.get("timezone")
        job_intent = settings.get("job_intent")
        if not isinstance(time_of_day, str) or not time_of_day.strip():
            return "time_of_day must be a non-empty string."
        try:
            _parse_time_of_day(time_of_day)
        except ValueError as exc:
            return str(exc)
        if not isinstance(timezone_name, str) or not timezone_name.strip():
            return "timezone must be a non-empty string."
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return f"timezone is not available: {timezone_name}."
        if job_intent not in SUPPORTED_DAILY_REPORT_JOB_INTENTS:
            return f"job_intent must be one of: {', '.join(sorted(SUPPORTED_DAILY_REPORT_JOB_INTENTS))}."
        return None


def _parse_time_of_day(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("time_of_day must use HH:MM 24-hour format.")
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("time_of_day must use HH:MM 24-hour format.")
    return hour, minute


def _next_run_at(time_of_day: str, timezone_name: str) -> str:
    hour, minute = _parse_time_of_day(time_of_day)
    tz = ZoneInfo(timezone_name)
    now = _utc_now_datetime().astimezone(tz)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return _format_utc(candidate.astimezone(timezone.utc))


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now() -> str:
    return _format_utc(_utc_now_datetime())


def _utc_now_datetime() -> datetime:
    return datetime.now(timezone.utc)


def _configured_timezone(config: dict[str, Any]) -> str:
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    value = run.get("timezone")
    return value if isinstance(value, str) and value.strip() else DEFAULT_DASHBOARD_TIMEZONE


def _report_generation_state(settings: dict[str, Any]) -> dict[str, Any]:
    intent = settings.get("job_intent")
    if intent == "run":
        return {
            "generates_report": True,
            "job_intent": "run",
            "codex_capable": True,
            "requires_codex_confirmation": True,
            "description": "Runs the full report path and may invoke Codex when triggered.",
        }
    return {
        "generates_report": False,
        "job_intent": "run_no_codex",
        "codex_capable": False,
        "requires_codex_confirmation": False,
        "description": "Runs the local pipeline with Codex skipped; no report artifact is expected.",
    }


def _bounded_string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            continue
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
