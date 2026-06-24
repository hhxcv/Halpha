from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import threading
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from halpha.dashboard.schedule_store import (
    DAILY_REPORT_SCHEDULE_ID,
    DASHBOARD_SCHEDULE_HISTORY_LIMIT,
    DASHBOARD_SCHEDULE_STORE_ARTIFACT,
    DashboardScheduleRepository,
    DashboardScheduleStoreError,
)
from halpha.dashboard.time import parse_utc_timestamp
from halpha.runtime.command_jobs import CommandJobManager
from halpha.runtime.command_job_store import JOB_TERMINAL_STATUSES, CommandJobRepository, CommandJobStoreError


DAILY_REPORT_SCHEDULE_FILENAME = "daily_report_schedule.json"
DAILY_REPORT_SCHEDULE_ARTIFACT = DASHBOARD_SCHEDULE_STORE_ARTIFACT
LEGACY_DAILY_REPORT_SCHEDULE_ARTIFACT = f".halpha/dashboard/schedules/{DAILY_REPORT_SCHEDULE_FILENAME}"
MAX_LINKED_JOB_IDS = 20
MAX_RECORDED_MISSED_OCCURRENCES = 10
SUPPORTED_DAILY_REPORT_JOB_INTENTS = {"run", "run_no_codex"}
DEFAULT_DAILY_REPORT_JOB_INTENT = "run"
DEFAULT_DASHBOARD_TIMEZONE = "Asia/Shanghai"
SCHEDULE_SERVICE_AUTOMATIC_DISPATCH = "schedule_service"


class DashboardScheduleManager:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: Path,
        job_manager: CommandJobManager,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.job_manager = job_manager
        self._repository = DashboardScheduleRepository(config_path=self.config_path)
        self._dispatch_lock = threading.Lock()

    def read_daily_report_schedule(self) -> dict[str, Any]:
        self._reconcile_dispatch_jobs()
        data = self._repository.get_schedule()
        if data is None:
            state = self._default_daily_report_state(status="missing", persisted=False)
            state["warnings"] = ["daily report schedule state was not found in the runtime state store."]
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
        authorization, auth_error = self._codex_authorization_for_update(
            current,
            enabled=enabled,
            settings=settings,
            update=update,
        )
        if auth_error:
            return self._blocked_daily_report_state(current, auth_error)
        return self._write_daily_report_state(
            current,
            enabled=enabled,
            settings=settings,
            codex_authorization=authorization,
        )

    def enable_daily_report_schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        update = dict(request if isinstance(request, dict) else {})
        if "job_intent" not in update:
            current = self.read_daily_report_schedule()
            if current["status"] == "failed":
                return current
            return self._blocked_daily_report_state(
                current,
                "job_intent must be selected before enabling the daily report schedule.",
            )
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
        if current.get("persisted") is not True:
            current = self._write_daily_report_state(
                current,
                enabled=False,
                settings=dict(current.get("settings") or {}),
            )
        scheduled_for = _utc_now()
        next_run_at = _next_run_at_for_current_state(current)
        claim = self._repository.claim_dispatch(
            schedule_id=DAILY_REPORT_SCHEDULE_ID,
            scheduled_for=scheduled_for,
            claimed_at=scheduled_for,
            next_run_at=next_run_at or "",
            dispatch_kind="manual",
        )
        if claim.status == "duplicate":
            return self._blocked_trigger_response(current, "daily report schedule occurrence was already claimed.")
        try:
            job = self.job_manager.create_job(
                {
                    "intent": intent,
                    "params": params,
                    "requested_by": "Schedule",
                    "requester": {
                        "source": "daily_report_schedule",
                        "dispatch_kind": "manual",
                        "schedule_id": DAILY_REPORT_SCHEDULE_ID,
                    },
                }
            )
        except Exception:
            error = "daily report job could not be created."
            self._repository.record_dispatch_error(
                schedule_id=DAILY_REPORT_SCHEDULE_ID,
                scheduled_for=scheduled_for,
                error=error,
                updated_at=_utc_now(),
            )
            return {
                "schema_version": 1,
                "artifact_type": "dashboard_daily_report_schedule_trigger",
                "status": "failed",
                "schedule": self.read_daily_report_schedule(),
                "job": None,
                "warnings": [],
                "errors": [error],
            }
        self._record_dispatch_job(scheduled_for=scheduled_for, job=job)
        updated = self.read_daily_report_schedule()
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_daily_report_schedule_trigger",
            "status": "available",
            "schedule": updated,
            "job": job,
            "warnings": [],
            "errors": [],
        }

    def dispatch_due_daily_report(self) -> dict[str, Any]:
        with self._dispatch_lock:
            current = self.read_daily_report_schedule()
            if current["status"] == "failed":
                return _dispatch_response("failed", current, job=None, errors=list(current.get("errors") or []))
            if current.get("enabled") is not True:
                return _dispatch_response(
                    "skipped",
                    current,
                    job=None,
                    warnings=["daily report schedule is disabled."],
                )
            next_run_at = parse_utc_timestamp(current.get("next_run_at"))
            if next_run_at is None:
                blocked = self._blocked_daily_report_state(current, "daily report schedule next_run_at is missing.")
                if blocked.get("persisted") is True:
                    blocked = self._repository.save_schedule(blocked)
                    blocked = self._normalized_daily_report_state(blocked)
                return _dispatch_response("blocked", blocked, job=None, errors=list(blocked.get("errors") or []))
            if next_run_at > _utc_now_datetime():
                return _dispatch_response(
                    "skipped",
                    current,
                    job=None,
                    warnings=["daily report schedule is not due."],
                )
            settings = current.get("settings") if isinstance(current.get("settings"), dict) else {}
            intent = str(settings.get("job_intent") or DEFAULT_DAILY_REPORT_JOB_INTENT)
            due_occurrences = _due_daily_occurrences(next_run_at, settings, now=_utc_now_datetime())
            if not due_occurrences:
                return _dispatch_response(
                    "skipped",
                    current,
                    job=None,
                    warnings=["daily report schedule is not due."],
                )
            latest_due = due_occurrences[-1]
            following_run_at = _next_run_at(settings["time_of_day"], settings["timezone"])
            missed_warning = "daily report schedule occurrence was missed during bounded catch-up."
            for missed_due in due_occurrences[:-1]:
                with suppress(DashboardScheduleStoreError):
                    self._repository.record_missed_dispatch(
                        schedule_id=DAILY_REPORT_SCHEDULE_ID,
                        scheduled_for=_format_utc(missed_due),
                        missed_at=_utc_now(),
                        next_run_at=_format_utc(latest_due),
                        warning=missed_warning,
                    )
            params: dict[str, Any] = {}
            if intent == "run":
                authorization = current.get("codex_authorization")
                if not _codex_authorization_valid(
                    authorization,
                    config_digest=self._config_digest(),
                    config_ref=_config_ref(self.config_path),
                    schedule_revision=int(current.get("revision") or 0),
                ):
                    error = "unattended Codex-capable daily report dispatch requires valid persisted authorization."
                    claim = self._repository.claim_dispatch(
                        schedule_id=DAILY_REPORT_SCHEDULE_ID,
                        scheduled_for=_format_utc(latest_due),
                        claimed_at=_utc_now(),
                        next_run_at=following_run_at,
                        dispatch_kind="automatic",
                        blocked_error=error,
                    )
                    blocked = self.read_daily_report_schedule() if claim.schedule is not None else current
                    return _dispatch_response("blocked", blocked, job=None, errors=[error])
                params["confirm_codex"] = True
            claim = self._repository.claim_dispatch(
                schedule_id=DAILY_REPORT_SCHEDULE_ID,
                scheduled_for=_format_utc(latest_due),
                claimed_at=_utc_now(),
                next_run_at=following_run_at,
                dispatch_kind="automatic",
            )
            if claim.status == "duplicate":
                return _dispatch_response(
                    "skipped",
                    self.read_daily_report_schedule(),
                    job=None,
                    warnings=claim.warnings,
                )
            try:
                job = self.job_manager.create_job(
                    {
                        "intent": intent,
                        "params": params,
                        "requested_by": "Schedule",
                        "requester": {
                            "source": "daily_report_schedule",
                            "dispatch_kind": "automatic",
                            "schedule_id": DAILY_REPORT_SCHEDULE_ID,
                        },
                    }
                )
            except Exception:
                error = "daily report job could not be created."
                self._repository.record_dispatch_error(
                    schedule_id=DAILY_REPORT_SCHEDULE_ID,
                    scheduled_for=_format_utc(latest_due),
                    error=error,
                    updated_at=_utc_now(),
                )
                return _dispatch_response("failed", self.read_daily_report_schedule(), job=None, errors=[error])
            self._record_dispatch_job(scheduled_for=_format_utc(latest_due), job=job)
            updated = self.read_daily_report_schedule()
            warnings = [missed_warning] if len(due_occurrences) > 1 else []
            return _dispatch_response("available", updated, job=job, warnings=warnings)

    def next_due_seconds(self) -> float:
        current = self.read_daily_report_schedule()
        if current["status"] == "failed" or current.get("enabled") is not True:
            return 30.0
        next_run_at = parse_utc_timestamp(current.get("next_run_at"))
        if next_run_at is None:
            return 30.0
        return max(0.0, (next_run_at - _utc_now_datetime()).total_seconds())

    def _default_daily_report_state(self, *, status: str, persisted: bool) -> dict[str, Any]:
        now = _utc_now()
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_daily_report_schedule",
            "schedule_id": DAILY_REPORT_SCHEDULE_ID,
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
            "dispatches": [],
            "revision": 0,
            "codex_authorization": _normalized_codex_authorization(
                {},
                config_digest=self._config_digest(),
                config_ref=_config_ref(self.config_path),
                schedule_revision=0,
            ),
            "runtime_boundary": {
                "runs_only_while_dashboard_active": False,
                "hidden_service": False,
                "hosted_scheduler": False,
                "os_scheduler": False,
                "automatic_dispatch": SCHEDULE_SERVICE_AUTOMATIC_DISPATCH,
            },
            "source_artifacts": [DAILY_REPORT_SCHEDULE_ARTIFACT],
            "legacy_artifacts": [LEGACY_DAILY_REPORT_SCHEDULE_ARTIFACT],
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
            next_run_at = _stored_or_next_run_at(data.get("next_run_at"), settings)
        status = str(data.get("status") or "available")
        if status not in {"available", "blocked"}:
            status = "available"
        dispatches = self._recent_dispatches()
        revision = int(data.get("revision") or 0)
        default.update(
            {
                "status": status,
                "enabled": enabled,
                "persisted": True,
                "settings": settings,
                "report_generation": _report_generation_state(settings),
                "next_run_at": next_run_at if enabled else None,
                "last_run_at": data.get("last_run_at"),
                "last_job_id": data.get("last_job_id") or _latest_dispatch_value(dispatches, "job_id"),
                "linked_job_ids": _dispatch_values(dispatches, "job_id", limit=MAX_LINKED_JOB_IDS),
                "linked_report_refs": _dispatch_values(dispatches, "report_ref", limit=MAX_LINKED_JOB_IDS),
                "dispatches": dispatches,
                "revision": revision,
                "codex_authorization": _normalized_codex_authorization(
                    data.get("codex_authorization"),
                    config_digest=self._config_digest(),
                    config_ref=_config_ref(self.config_path),
                    schedule_revision=revision,
                ),
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
        codex_authorization: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        next_revision = int(current.get("revision") or 0) + 1
        state = self._default_daily_report_state(status="available", persisted=True)
        state.update(
            {
                "schedule_id": DAILY_REPORT_SCHEDULE_ID,
                "enabled": enabled,
                "settings": settings,
                "report_generation": _report_generation_state(settings),
                "next_run_at": _next_run_at(settings["time_of_day"], settings["timezone"]) if enabled else None,
                "last_run_at": current.get("last_run_at"),
                "last_job_id": current.get("last_job_id"),
                "revision": next_revision,
                "codex_authorization": codex_authorization or _empty_codex_authorization(
                    reason="schedule is not authorized for unattended Codex-capable dispatch."
                ),
                "created_at": current.get("created_at") or now,
                "updated_at": now,
                "warnings": [],
                "errors": [],
            }
        )
        saved = self._repository.save_schedule(state)
        return self._normalized_daily_report_state(saved)

    def _codex_authorization_for_update(
        self,
        current: dict[str, Any],
        *,
        enabled: bool,
        settings: dict[str, Any],
        update: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        if settings.get("job_intent") != "run" or enabled is not True:
            return _empty_codex_authorization(
                reason="schedule is not Codex-capable or is disabled.",
            ), None
        next_revision = int(current.get("revision") or 0) + 1
        if update.get("confirm_codex") is not True:
            return {}, "confirm_codex must be true to authorize unattended Codex-capable daily report dispatch."
        return {
            "authorized": True,
            "authorized_at": _utc_now(),
            "schedule_revision": next_revision,
            "config_digest": self._config_digest(),
            "config_ref": _config_ref(self.config_path),
            "job_intent": "run",
            "authorization_scope": "unattended_daily_report_schedule",
        }, None

    def _reconcile_dispatch_jobs(self) -> None:
        for dispatch in self._repository.list_dispatches(limit=DASHBOARD_SCHEDULE_HISTORY_LIMIT):
            job_id = dispatch.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                continue
            if dispatch.get("terminal_status"):
                continue
            job = self._job_for_dispatch_reconcile(job_id)
            if not job:
                continue
            if str(job.get("status") or "") not in JOB_TERMINAL_STATUSES:
                continue
            self._record_dispatch_job(scheduled_for=str(dispatch.get("scheduled_for") or ""), job=job, attempts=1)

    def _job_for_dispatch_reconcile(self, job_id: str) -> dict[str, Any] | None:
        repository = getattr(self.job_manager, "_repository", None)
        if isinstance(repository, CommandJobRepository):
            try:
                return repository.get_job(job_id)
            except CommandJobStoreError:
                return None
        job = self.job_manager.get_job(job_id)
        if isinstance(job, dict) and job.get("store_read_failed") is True:
            return None
        return job

    def _record_dispatch_job(self, *, scheduled_for: str, job: dict[str, Any], attempts: int = 10) -> bool:
        for attempt in range(max(1, attempts)):
            with suppress(DashboardScheduleStoreError):
                self._repository.record_dispatch_job(
                    schedule_id=DAILY_REPORT_SCHEDULE_ID,
                    scheduled_for=scheduled_for,
                    job=job,
                    updated_at=_utc_now(),
                )
                return True
            if attempt + 1 < attempts:
                time.sleep(0.02)
        return False

    def _recent_dispatches(self) -> list[dict[str, Any]]:
        dispatches = self._repository.list_dispatches(limit=DASHBOARD_SCHEDULE_HISTORY_LIMIT)
        return [
            {
                "scheduled_for": dispatch.get("scheduled_for"),
                "dispatch_kind": dispatch.get("dispatch_kind"),
                "status": dispatch.get("status"),
                "claimed_at": dispatch.get("claimed_at"),
                "completed_at": dispatch.get("completed_at"),
                "job_id": dispatch.get("job_id"),
                "run_ref": dispatch.get("run_ref"),
                "report_ref": dispatch.get("report_ref"),
                "terminal_status": dispatch.get("terminal_status"),
                "warnings": _bounded_string_list(dispatch.get("warnings"), limit=20),
                "errors": _bounded_string_list(dispatch.get("errors"), limit=20),
            }
            for dispatch in dispatches
        ]

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
        supported = {"enabled", "time_of_day", "timezone", "job_intent", "confirm_codex"}
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

    def _config_digest(self) -> str:
        return _config_digest(self.config, config_path=self.config_path)


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


def _stored_or_next_run_at(value: Any, settings: dict[str, Any]) -> str:
    stored = parse_utc_timestamp(value)
    if stored is not None:
        return _format_utc(stored)
    return _next_run_at(settings["time_of_day"], settings["timezone"])


def _next_run_at_for_current_state(current: dict[str, Any]) -> str | None:
    if current.get("enabled") is not True:
        return None
    settings = current.get("settings") if isinstance(current.get("settings"), dict) else {}
    time_of_day = settings.get("time_of_day")
    timezone_name = settings.get("timezone")
    if not isinstance(time_of_day, str) or not isinstance(timezone_name, str):
        return None
    return _next_run_at(time_of_day, timezone_name)


def _due_daily_occurrences(first_due: datetime, settings: dict[str, Any], *, now: datetime) -> list[datetime]:
    if first_due > now:
        return []
    occurrences: list[datetime] = []
    omitted = 0
    cursor = first_due.astimezone(timezone.utc).replace(microsecond=0)
    safety = 0
    while cursor <= now.replace(microsecond=0) and safety < 3660:
        occurrences.append(cursor)
        if len(occurrences) > MAX_RECORDED_MISSED_OCCURRENCES + 1:
            occurrences.pop(0)
            omitted += 1
        cursor = _next_daily_occurrence_after(cursor, settings)
        safety += 1
    if omitted and len(occurrences) > 1:
        occurrences = occurrences[-(MAX_RECORDED_MISSED_OCCURRENCES + 1) :]
    return occurrences


def _next_daily_occurrence_after(value: datetime, settings: dict[str, Any]) -> datetime:
    time_of_day = str(settings.get("time_of_day") or "00:00")
    timezone_name = str(settings.get("timezone") or "UTC")
    hour, minute = _parse_time_of_day(time_of_day)
    tz = ZoneInfo(timezone_name)
    local = value.astimezone(tz)
    candidate = (local + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return candidate.astimezone(timezone.utc)


def _empty_codex_authorization(*, reason: str) -> dict[str, Any]:
    return {
        "authorized": False,
        "valid": False,
        "authorized_at": None,
        "schedule_revision": None,
        "config_digest": None,
        "config_ref": None,
        "job_intent": None,
        "authorization_scope": "unattended_daily_report_schedule",
        "invalid_reason": reason,
    }


def _normalized_codex_authorization(
    value: Any,
    *,
    config_digest: str,
    config_ref: str,
    schedule_revision: int,
) -> dict[str, Any]:
    data = dict(value) if isinstance(value, dict) else {}
    if data.get("authorized") is not True:
        return _empty_codex_authorization(
            reason=str(data.get("invalid_reason") or "schedule is not authorized for unattended Codex-capable dispatch."),
        )
    valid = _codex_authorization_valid(
        data,
        config_digest=config_digest,
        config_ref=config_ref,
        schedule_revision=schedule_revision,
    )
    invalid_reason = None
    if not valid:
        invalid_reason = "authorization does not match the current schedule revision, config ref, or config digest."
    return {
        "authorized": True,
        "valid": valid,
        "authorized_at": data.get("authorized_at") if isinstance(data.get("authorized_at"), str) else None,
        "schedule_revision": _int_or_none(data.get("schedule_revision")),
        "config_digest": data.get("config_digest") if isinstance(data.get("config_digest"), str) else None,
        "config_ref": data.get("config_ref") if isinstance(data.get("config_ref"), str) else None,
        "job_intent": data.get("job_intent") if data.get("job_intent") in SUPPORTED_DAILY_REPORT_JOB_INTENTS else None,
        "authorization_scope": "unattended_daily_report_schedule",
        "invalid_reason": invalid_reason,
    }


def _codex_authorization_valid(
    value: Any,
    *,
    config_digest: str,
    config_ref: str,
    schedule_revision: int,
) -> bool:
    if not isinstance(value, dict) or value.get("authorized") is not True:
        return False
    return (
        value.get("job_intent") == "run"
        and value.get("authorization_scope") == "unattended_daily_report_schedule"
        and _int_or_none(value.get("schedule_revision")) == int(schedule_revision)
        and value.get("config_digest") == config_digest
        and value.get("config_ref") == config_ref
    )


def _config_digest(config: dict[str, Any], *, config_path: Path) -> str:
    material = {
        "config": config if isinstance(config, dict) else {},
        "config_ref": _config_ref(config_path),
        "schedule_contract": "daily_report_v1",
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _config_ref(config_path: Path) -> str:
    path = Path(config_path)
    return path.as_posix() if not path.is_absolute() else "<external-config>"


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dispatch_response(
    status: str,
    schedule: dict[str, Any],
    *,
    job: dict[str, Any] | None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_daily_report_dispatch",
        "status": status,
        "schedule": schedule,
        "job": job,
        "warnings": warnings or [],
        "errors": errors or [],
    }


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


def _dispatch_values(dispatches: list[dict[str, Any]], key: str, *, limit: int) -> list[str]:
    output: list[str] = []
    for dispatch in dispatches:
        value = dispatch.get(key)
        if isinstance(value, str) and value and value not in output:
            output.append(value)
            if len(output) >= limit:
                break
    return output


def _latest_dispatch_value(dispatches: list[dict[str, Any]], key: str) -> str | None:
    values = _dispatch_values(dispatches, key, limit=1)
    return values[0] if values else None
