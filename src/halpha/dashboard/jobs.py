from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
import subprocess
import threading
from typing import Any
from uuid import uuid4

from halpha.dashboard.common import dashboard_read_json
from halpha.dashboard.common import dashboard_safe_ref as _safe_ref
from halpha.dashboard.job_commands import CommandSpec
from halpha.dashboard.job_commands import DashboardJobCommandBuilder
from halpha.dashboard.job_commands import DashboardJobError
from halpha.dashboard.job_commands import dashboard_config_ref
from halpha.dashboard.time import parse_utc_timestamp, utc_now_timestamp
from halpha.runtime.exception_diagnostics import bounded_exception_diagnostic
from halpha.runtime.logging_utils import configure_local_logging
from halpha.storage import artifact_base as _artifact_base, write_json


DASHBOARD_JOBS_DIR = "runs/dashboard/jobs"
DASHBOARD_JOB_INDEX = "runs/dashboard/jobs/index.json"
MAX_JOB_LOG_CHARS = 20_000
STALE_RUNNING_JOB_GRACE_SECONDS = 30
EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REDACTED_ARTIFACT_REF = "<redacted-artifact>"
RESULT_REF_PLACEHOLDERS = {EXTERNAL_ARTIFACT_REF, REDACTED_ARTIFACT_REF}
JOB_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started"}
JOB_PROCESS_STATUSES = {"running"}
DASHBOARD_JOB_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{8}$")
RESULT_ARTIFACT_KEYS = {
    "event_intelligence_material",
    "manifest",
    "model_prepare_manifest",
    "health_state",
    "monitor_manifest",
    "report",
    "strategy_backtest",
    "strategy_benchmark_suite",
    "strategy_effectiveness_gates",
    "strategy_experiment",
    "text_event_classification_evidence",
    "text_event_records",
    "text_event_signals",
    "text_event_topics",
}
TEXT_INTELLIGENCE_RELATIVE_ARTIFACT_PREFIXES = ("analysis/", "raw/", "codex_context/", "report/")
PRIVATE_KEY_PARTS = (
    "account",
    "cookie",
    "credential",
    "endpoint",
    "host",
    "password",
    "path",
    "port",
    "proxy",
    "secret",
    "token",
    "url",
    "user",
)


class DashboardJobManager:
    def __init__(self, config: dict[str, Any], *, config_path: Path) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.resolved_config_path = self.config_path.resolve()
        self.base = _artifact_base(self.config_path)
        self.jobs_root = self.base / DASHBOARD_JOBS_DIR
        with suppress(OSError):
            configure_local_logging(config_path=self.config_path, config=config)
        self._command_builder = DashboardJobCommandBuilder(config, config_path=self.config_path, base=self.base)
        self._logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancel_requested: set[str] = set()

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now()
        intent = str(request.get("intent") or "").strip()
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        job = self._new_job(intent=intent, params=params, now=now)
        try:
            job_command = self._command_builder.build(intent, params)
        except DashboardJobError as exc:
            job.update(
                {
                    "status": exc.status,
                    "updated_at": now,
                    "finished_at": now,
                    "errors": [str(exc)],
                }
            )
            self._write_job(job)
            self._write_index()
            if exc.status == "unsupported":
                self._logger.warning(
                    "Dashboard job was rejected.",
                    extra={
                        "event": "dashboard.job.rejected",
                        "job_id": job["job_id"],
                        "intent": intent,
                        "status": job["status"],
                        "reason": str(exc),
                    },
                )
            else:
                self._logger.warning(
                    "Dashboard job was blocked.",
                    extra={
                        "event": "dashboard.job.blocked",
                        "job_id": job["job_id"],
                        "intent": intent,
                        "status": job["status"],
                        "reason": str(exc),
                    },
                )
            return job

        spec = job_command.spec
        command = job_command.command
        command_preview = job_command.preview
        job["kind"] = spec.kind
        job["command"] = command_preview
        job["cancellable"] = spec.cancellable
        self._write_job(job)
        self._write_index()
        self._logger.info(
            "Dashboard job queued.",
            extra={
                "event": "dashboard.job.queued",
                "job_id": job["job_id"],
                "intent": intent,
                "kind": spec.kind,
                "command_preview": command_preview,
            },
        )
        thread = threading.Thread(
            target=self._run_job,
            args=(job["job_id"], command, spec),
            name=f"dashboard-job-{job['job_id']}",
            daemon=True,
        )
        thread.start()
        return self.get_job(str(job["job_id"])) or job

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        jobs = sorted(
            (self._normalize_runtime_job_state(job) for job in self._read_jobs() if job),
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )[:limit]
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_job_list",
            "status": "available" if jobs else "missing",
            "source_artifacts": [DASHBOARD_JOB_INDEX],
            "jobs": jobs,
            "warnings": [] if jobs else ["dashboard job history is empty."],
            "errors": [],
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if not _is_dashboard_job_id(job_id):
            return None
        path = self._job_path(job_id)
        if not path.exists():
            return None
        try:
            data = _read_json(path)
        except DashboardJobError:
            return None
        return self._normalize_runtime_job_state(data)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.get_job(job_id)
            if job is None:
                return {
                    "schema_version": 1,
                    "artifact_type": "dashboard_job",
                    "job_id": job_id,
                    "status": "missing",
                    "warnings": ["dashboard job was not found."],
                    "errors": [],
                }
            status = str(job.get("status") or "unknown")
            if status in JOB_TERMINAL_STATUSES:
                job.setdefault("warnings", []).append(f"job is already {status}.")
                return job
            process = self._processes.get(job_id)
            if process is None:
                job["status"] = "blocked"
                job["updated_at"] = _utc_now()
                job["finished_at"] = job["updated_at"]
                job.setdefault("errors", []).append(
                    "running job process is not attached to this dashboard runtime; cancellation is unsupported."
                )
                self._write_job(job)
                self._write_index()
                return job
            self._cancel_requested.add(job_id)
            job["status"] = "cancel_requested"
            job["updated_at"] = _utc_now()
            self._write_job(job)
            self._write_index()
            with suppress(OSError):
                process.terminate()
            return job

    def _run_job(self, job_id: str, command: list[str], spec: CommandSpec) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        started_at = _utc_now()
        self._logger.info(
            "Dashboard job starting.",
            extra={
                "event": "dashboard.job.start",
                "job_id": job_id,
                "intent": job.get("intent"),
                "kind": spec.kind,
                "command_preview": job.get("command"),
            },
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=self.base,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )
        except OSError as exc:
            reason = self._redact_text(f"job process could not start: {exc}")
            job.update(
                {
                    "status": "failed",
                    "updated_at": _utc_now(),
                    "started_at": started_at,
                    "finished_at": _utc_now(),
                    "errors": [reason],
                    "diagnostic": bounded_exception_diagnostic(exc, context={"phase": "process_start"}),
                }
            )
            self._write_job(job)
            self._write_index()
            self._logger.error(
                "Dashboard job process could not start.",
                extra={
                    "event": "dashboard.job.start_failed",
                    "job_id": job_id,
                    "intent": job.get("intent"),
                    "kind": spec.kind,
                    "reason": reason,
                    "exception_type": type(exc).__name__,
                },
            )
            return

        with self._lock:
            self._processes[job_id] = process
            job.update(
                {
                    "status": "running",
                    "started_at": started_at,
                    "updated_at": started_at,
                    "pid": process.pid,
                }
            )
            self._write_job(job)
            self._write_index()

        stdout, stderr = process.communicate()
        finished_at = _utc_now()
        with self._lock:
            self._processes.pop(job_id, None)
        was_cancelled = job_id in self._cancel_requested
        if was_cancelled:
            self._cancel_requested.discard(job_id)
        job = self.get_job(job_id) or job
        stdout_ref, stdout_truncated = self._write_log(job_id, "stdout.log", stdout)
        stderr_ref, stderr_truncated = self._write_log(job_id, "stderr.log", stderr)
        result_refs = self._job_result_refs(stdout, spec=spec)
        source_artifacts = [stdout_ref, stderr_ref]
        for key, artifact_ref in result_refs.items():
            if (
                key not in {"output_dir", "run_id"}
                and artifact_ref
                and artifact_ref not in RESULT_REF_PLACEHOLDERS
                and artifact_ref not in source_artifacts
            ):
                source_artifacts.append(artifact_ref)
        exit_code = int(process.returncode or 0)
        status = "cancelled" if was_cancelled else "succeeded" if exit_code == 0 else "failed"
        job.update(
            {
                "status": status,
                "updated_at": finished_at,
                "finished_at": finished_at,
                "exit_code": exit_code,
                "logs": {
                    "stdout_ref": stdout_ref,
                    "stderr_ref": stderr_ref,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "max_chars": MAX_JOB_LOG_CHARS,
                },
                "result_refs": result_refs,
                "source_artifacts": source_artifacts,
            }
        )
        if status == "cancelled":
            job.setdefault("warnings", []).append("job was cancelled by dashboard request.")
        elif status == "failed":
            job.setdefault("errors", []).append(f"job exited with code {exit_code}.")
        self._write_job(job)
        self._write_index()
        self._logger.log(
            logging.INFO if status == "succeeded" else logging.WARNING,
            "Dashboard job finished.",
            extra={
                "event": "dashboard.job.finished",
                "job_id": job_id,
                "intent": job.get("intent"),
                "kind": spec.kind,
                "status": status,
                "exit_code": exit_code,
            },
        )

    def _new_job(self, *, intent: str, params: dict[str, Any], now: str) -> dict[str, Any]:
        job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        job_dir = self.jobs_root / job_id
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_job",
            "job_id": job_id,
            "kind": "command",
            "intent": intent,
            "params": self._redact_value(params),
            "config_ref": dashboard_config_ref(self.config_path),
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "exit_code": None,
            "cancellable": False,
            "command": [],
            "job_dir": _safe_ref(job_dir, base=self.base),
            "logs": {
                "stdout_ref": _safe_ref(job_dir / "stdout.log", base=self.base),
                "stderr_ref": _safe_ref(job_dir / "stderr.log", base=self.base),
                "stdout_truncated": False,
                "stderr_truncated": False,
                "max_chars": MAX_JOB_LOG_CHARS,
            },
            "result_refs": {},
            "source_artifacts": [],
            "warnings": [],
            "errors": [],
        }

    def _write_job(self, job: dict[str, Any]) -> None:
        write_json(self._job_path(str(job["job_id"])), self._redact_value(job))

    def _write_index(self) -> None:
        jobs = sorted(
            (job for job in self._read_jobs() if job),
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )
        write_json(
            self.base / DASHBOARD_JOB_INDEX,
            {
                "schema_version": 1,
                "artifact_type": "dashboard_job_index",
                "status": "available" if jobs else "missing",
                "updated_at": _utc_now(),
                "job_count": len(jobs),
                "jobs": [
                    {
                        "job_id": job.get("job_id"),
                        "intent": job.get("intent"),
                        "kind": job.get("kind"),
                        "status": job.get("status"),
                        "created_at": job.get("created_at"),
                        "updated_at": job.get("updated_at"),
                        "result_refs": job.get("result_refs") or {},
                        "job_ref": _safe_ref(self._job_path(str(job.get("job_id"))), base=self.base),
                    }
                    for job in jobs[:100]
                ],
                "warnings": [],
                "errors": [],
            },
        )

    def _read_jobs(self) -> list[dict[str, Any]]:
        if not self.jobs_root.exists():
            return []
        jobs = []
        for path in sorted(self.jobs_root.glob("*/job.json")):
            with suppress(DashboardJobError):
                jobs.append(_read_json(path))
        return jobs

    def _write_log(self, job_id: str, filename: str, content: str | None) -> tuple[str, bool]:
        path = self.jobs_root / job_id / filename
        safe = self._redact_text(content or "")
        bounded = safe[:MAX_JOB_LOG_CHARS]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bounded, encoding="utf-8")
        return _safe_ref(path, base=self.base), len(safe) > MAX_JOB_LOG_CHARS

    def _job_result_refs(self, stdout: str | None, *, spec: CommandSpec) -> dict[str, str]:
        refs: dict[str, str] = {}
        output_dir_ref: str | None = None
        for line in (stdout or "").splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue
            key = key.strip()
            value = value.strip()
            if not value:
                continue
            if key == "run_id":
                refs["run_id"] = self._redact_text(value)
            elif key == "output_dir":
                output_dir_ref = self._safe_output_ref(value)
                refs["output_dir"] = output_dir_ref
            elif key == "manifest":
                result_key = "run_manifest" if spec.kind in {"product_run", "stage_rerun"} else "manifest"
                refs[result_key] = self._safe_output_ref(value)
            elif key == "report":
                refs["report"] = self._safe_output_ref(value)
            elif key in RESULT_ARTIFACT_KEYS:
                refs[key] = self._safe_result_artifact_ref(value, output_dir_ref=output_dir_ref)
        return refs

    def _safe_result_artifact_ref(self, value: str, *, output_dir_ref: str | None) -> str:
        if (
            output_dir_ref
            and output_dir_ref != EXTERNAL_ARTIFACT_REF
            and value.startswith(TEXT_INTELLIGENCE_RELATIVE_ARTIFACT_PREFIXES)
        ):
            return self._safe_output_ref(f"{output_dir_ref}/{value}")
        if output_dir_ref == EXTERNAL_ARTIFACT_REF and value.startswith(TEXT_INTELLIGENCE_RELATIVE_ARTIFACT_PREFIXES):
            return EXTERNAL_ARTIFACT_REF
        return self._safe_output_ref(value)

    def _safe_output_ref(self, value: str) -> str:
        path = Path(value.strip())
        target = path if path.is_absolute() else self.base / path
        try:
            ref = target.resolve().relative_to(self.base.resolve()).as_posix()
        except (OSError, ValueError):
            return EXTERNAL_ARTIFACT_REF
        return REDACTED_ARTIFACT_REF if self._redact_text(ref) != ref else ref

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_root / job_id / "job.json"

    def _normalize_runtime_job_state(self, job: dict[str, Any]) -> dict[str, Any]:
        status = str(job.get("status") or "").lower()
        if status not in JOB_PROCESS_STATUSES:
            return job
        job_id = str(job.get("job_id") or "")
        if job_id in self._processes:
            job["runtime_attached"] = True
            job["process_alive"] = True
            return job

        alive = _process_is_alive(job.get("pid"))
        job["runtime_attached"] = False
        job["process_alive"] = alive
        if alive:
            job["cancellable"] = False
            warning = (
                "job process is running outside this dashboard runtime; "
                "cancellation is unsupported from the current dashboard process."
            )
            warnings = job.setdefault("warnings", [])
            if isinstance(warnings, list) and warning not in warnings:
                warnings.append(warning)
            return job
        if _job_recently_updated(job, grace_seconds=STALE_RUNNING_JOB_GRACE_SECONDS):
            return job

        job["status"] = "blocked"
        job["updated_at"] = _utc_now()
        job["finished_at"] = job["updated_at"]
        error = (
            "job was marked running, but its recorded process is not running "
            "and is not attached to this dashboard runtime."
        )
        errors = job.setdefault("errors", [])
        if isinstance(errors, list) and error not in errors:
            errors.append(error)
        self._write_job(job)
        self._write_index()
        return job

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): "<redacted>" if _is_private_key(str(key)) else self._redact_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value

    def _redact_text(self, text: str) -> str:
        redacted = text
        for value in self._private_values():
            if value:
                redacted = redacted.replace(value, "<redacted>")
        return redacted

    def _private_values(self) -> list[str]:
        values = set()
        if self.base.is_absolute():
            values.update({str(self.base), self.base.as_posix()})
        if self.config_path.is_absolute():
            values.update({str(self.config_path), self.config_path.as_posix()})
        values.update({str(self.resolved_config_path), self.resolved_config_path.as_posix()})
        values.update(_config_private_values(self.config))
        return sorted(values, key=len, reverse=True)


def _read_json(path: Path) -> dict[str, Any]:
    data, error = dashboard_read_json(path)
    if error:
        raise DashboardJobError(error)
    return data


def _process_is_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, OverflowError, SystemError, ValueError):
        return False
    return True


def _job_recently_updated(job: dict[str, Any], *, grace_seconds: int) -> bool:
    for key in ("updated_at", "started_at", "created_at"):
        timestamp = parse_utc_timestamp(job.get(key))
        if timestamp is None:
            continue
        age = datetime.now(timezone.utc) - timestamp
        return age.total_seconds() < grace_seconds
    return False


def _config_private_values(config: dict[str, Any]) -> set[str]:
    values: set[str] = set()

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
        if any(_is_private_key(key) for key in key_path):
            values.add(value)

    visit(config, ())
    return values


def _is_private_key(key: str) -> bool:
    lowered = key.lower()
    if lowered == "report":
        return False
    return any(part in lowered for part in PRIVATE_KEY_PARTS)


def _is_dashboard_job_id(value: str) -> bool:
    return DASHBOARD_JOB_ID_RE.fullmatch(str(value or "")) is not None


def _utc_now() -> str:
    return utc_now_timestamp()
