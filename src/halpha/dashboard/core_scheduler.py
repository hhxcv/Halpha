from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from halpha.live.config import load_live_settings
from halpha.live.scheduler import LiveScheduler
from halpha.dashboard.schedule import DashboardScheduleManager
from halpha.monitor.monitoring import load_monitor_config
from halpha.runtime.command_job_store import JOB_TRANSIENT_STATUSES
from halpha.runtime.command_jobs import CommandJobManager


CORE_SCHEDULER_TICK_ARTIFACT = "core_scheduler_tick"
CORE_SCHEDULER_SOURCE = "core_scheduler"
MONITOR_CYCLE_JOB_KIND = "monitor_cycle"
MONITOR_CYCLE_JOB_INTENT = "monitor_sources_once"
DEFAULT_CORE_SCHEDULER_TICK_SECONDS = 30.0


class _JobManager(Protocol):
    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        ...

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        ...


class _ScheduleManager(Protocol):
    def dispatch_due_daily_report(self) -> dict[str, Any]:
        ...

    def next_due_seconds(self) -> float:
        ...


@dataclass(frozen=True)
class CoreSchedulerTick:
    status: str
    tick_id: str
    schedule_dispatch: dict[str, Any]
    monitor_cycle_job: dict[str, Any] | None
    live_refresh: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    next_tick_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_type": CORE_SCHEDULER_TICK_ARTIFACT,
            "status": self.status,
            "tick_id": self.tick_id,
            "schedule_dispatch": self.schedule_dispatch,
            "monitor_cycle_job": self.monitor_cycle_job,
            "live_refresh": self.live_refresh,
            "warnings": self.warnings,
            "errors": self.errors,
            "next_tick_seconds": self.next_tick_seconds,
        }


class CoreScheduler:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: Path,
        job_manager: _JobManager,
        schedule_manager: _ScheduleManager,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.job_manager = job_manager
        self.schedule_manager = schedule_manager

    @classmethod
    def from_core_managers(
        cls,
        config: dict[str, Any],
        *,
        config_path: Path,
        job_manager: CommandJobManager,
        schedule_manager: DashboardScheduleManager,
    ) -> CoreScheduler:
        return cls(config, config_path=config_path, job_manager=job_manager, schedule_manager=schedule_manager)

    def run_once(self) -> dict[str, Any]:
        tick_id = _tick_id()
        warnings: list[str] = []
        errors: list[str] = []
        schedule_dispatch = self._dispatch_daily_schedule()
        warnings.extend(_strings(schedule_dispatch.get("warnings")))
        errors.extend(_strings(schedule_dispatch.get("errors")))
        monitor_cycle_job = self._create_monitor_cycle_job_if_due(tick_id=tick_id)
        warnings.extend(_strings(monitor_cycle_job.get("warnings")) if monitor_cycle_job else [])
        errors.extend(_strings(monitor_cycle_job.get("errors")) if monitor_cycle_job else [])
        live_refresh = self._run_live_refresh(tick_id=tick_id)
        warnings.extend(_strings(live_refresh.get("warnings")))
        errors.extend(_strings(live_refresh.get("errors")))
        status = "available" if not errors else "degraded"
        return CoreSchedulerTick(
            status=status,
            tick_id=tick_id,
            schedule_dispatch=schedule_dispatch,
            monitor_cycle_job=monitor_cycle_job,
            live_refresh=live_refresh,
            warnings=warnings[:10],
            errors=errors[:10],
            next_tick_seconds=self.next_tick_seconds(),
        ).as_dict()

    def run_loop(self, stop_event: Any) -> None:
        while not stop_event.is_set():
            result = self.run_once()
            wait_seconds = _positive_float(result.get("next_tick_seconds"), default=DEFAULT_CORE_SCHEDULER_TICK_SECONDS)
            if stop_event.wait(wait_seconds):
                break

    def next_tick_seconds(self) -> float:
        monitor_seconds = _positive_float(load_monitor_config(self.config).interval_seconds, default=DEFAULT_CORE_SCHEDULER_TICK_SECONDS)
        schedule_seconds = DEFAULT_CORE_SCHEDULER_TICK_SECONDS
        try:
            schedule_seconds = _positive_float(self.schedule_manager.next_due_seconds(), default=DEFAULT_CORE_SCHEDULER_TICK_SECONDS)
        except Exception:
            schedule_seconds = DEFAULT_CORE_SCHEDULER_TICK_SECONDS
        live_seconds = DEFAULT_CORE_SCHEDULER_TICK_SECONDS
        try:
            live_settings = load_live_settings(self.config)
            if live_settings.enabled:
                live_seconds = float(live_settings.tick_seconds)
        except Exception:
            live_seconds = DEFAULT_CORE_SCHEDULER_TICK_SECONDS
        return max(1.0, min(DEFAULT_CORE_SCHEDULER_TICK_SECONDS, monitor_seconds, schedule_seconds, live_seconds))

    def _dispatch_daily_schedule(self) -> dict[str, Any]:
        try:
            return self.schedule_manager.dispatch_due_daily_report()
        except Exception as exc:
            return {
                "schema_version": 1,
                "artifact_type": "dashboard_daily_report_dispatch",
                "status": "failed",
                "schedule": None,
                "job": None,
                "warnings": [],
                "errors": [str(exc) or "daily report schedule dispatch failed."],
            }

    def _run_live_refresh(self, *, tick_id: str) -> dict[str, Any]:
        try:
            return LiveScheduler(
                self.config,
                config_path=self.config_path,
                job_manager=self.job_manager,
            ).tick(tick_id=tick_id)
        except Exception as exc:
            return {
                "schema_version": 1,
                "artifact_type": "live_scheduler_tick",
                "status": "failed",
                "tick_id": tick_id,
                "enabled": False,
                "reason": "Live scheduler tick failed.",
                "created_jobs": [],
                "collections": [],
                "warnings": [],
                "errors": [str(exc) or "Live scheduler tick failed."],
            }

    def _create_monitor_cycle_job_if_due(self, *, tick_id: str) -> dict[str, Any] | None:
        settings = load_monitor_config(self.config)
        if settings.enabled is not True:
            return {
                "status": "skipped",
                "job": None,
                "reason": "monitor.enabled is false.",
                "warnings": [],
                "errors": [],
            }
        duplicate = self._transient_monitor_cycle_job()
        if duplicate is not None:
            return {
                "status": "skipped",
                "job": duplicate,
                "reason": "monitor cycle job is already queued, running, or cancel-requested.",
                "warnings": [],
                "errors": [],
            }
        recent = self._recent_monitor_cycle_job(interval_seconds=settings.interval_seconds)
        if recent is not None:
            return {
                "status": "skipped",
                "job": recent,
                "reason": "monitor cycle interval has not elapsed.",
                "warnings": [],
                "errors": [],
            }
        try:
            job = self.job_manager.create_job(
                {
                    "intent": MONITOR_CYCLE_JOB_INTENT,
                    "params": {},
                    "requested_by": "Core",
                    "requester": {
                        "source": CORE_SCHEDULER_SOURCE,
                        "tick_id": tick_id,
                    },
                }
            )
        except Exception as exc:
            return {
                "status": "failed",
                "job": None,
                "reason": "monitor cycle job could not be created.",
                "warnings": [],
                "errors": [str(exc) or "monitor cycle job could not be created."],
            }
        return {
            "status": "available" if str(job.get("status") or "") not in {"blocked", "failed", "unsupported"} else str(job.get("status")),
            "job": job,
            "reason": None,
            "warnings": _strings(job.get("warnings")),
            "errors": _strings(job.get("errors")),
        }

    def _transient_monitor_cycle_job(self) -> dict[str, Any] | None:
        try:
            payload = self.job_manager.list_jobs(limit=50)
        except Exception:
            return None
        jobs = payload.get("jobs") if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            return None
        for job in jobs:
            if not isinstance(job, dict):
                continue
            if job.get("kind") != MONITOR_CYCLE_JOB_KIND:
                continue
            if str(job.get("status") or "") in JOB_TRANSIENT_STATUSES:
                return job
        return None

    def _recent_monitor_cycle_job(self, *, interval_seconds: int) -> dict[str, Any] | None:
        latest = self._latest_monitor_cycle_job()
        if latest is None:
            return None
        timestamp = _job_timestamp(latest)
        if timestamp is None:
            return None
        elapsed = (datetime.now(timezone.utc) - timestamp).total_seconds()
        if elapsed < max(1, interval_seconds):
            return latest
        return None

    def _latest_monitor_cycle_job(self) -> dict[str, Any] | None:
        try:
            payload = self.job_manager.list_jobs(limit=50)
        except Exception:
            return None
        jobs = payload.get("jobs") if isinstance(payload, dict) else []
        if not isinstance(jobs, list):
            return None
        for job in jobs:
            if isinstance(job, dict) and job.get("kind") == MONITOR_CYCLE_JOB_KIND:
                return job
        return None


def _tick_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _job_timestamp(job: dict[str, Any]) -> datetime | None:
    for key in ("created_at", "updated_at", "finished_at"):
        value = job.get(key)
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _positive_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    if parsed <= 0:
        return float(default)
    return parsed
