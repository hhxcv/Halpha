from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any
from uuid import uuid4

from .storage import write_json


DASHBOARD_JOBS_DIR = "runs/dashboard/jobs"
DASHBOARD_JOB_INDEX = "runs/dashboard/jobs/index.json"
MAX_JOB_LOG_CHARS = 20_000
JOB_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started"}
PRIVATE_KEY_PARTS = (
    "account",
    "cookie",
    "credential",
    "endpoint",
    "host",
    "password",
    "port",
    "proxy",
    "secret",
    "token",
    "url",
    "user",
)


class DashboardJobError(Exception):
    def __init__(self, message: str, *, status: str = "blocked") -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class CommandSpec:
    intent: str
    kind: str
    cancellable: bool


SUPPORTED_COMMANDS = {
    "validate": CommandSpec(intent="validate", kind="product_validation", cancellable=True),
}


class DashboardJobManager:
    def __init__(self, config: dict[str, Any], *, config_path: Path) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.base = _config_base(self.config_path)
        self.jobs_root = self.base / DASHBOARD_JOBS_DIR
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._cancel_requested: set[str] = set()

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now()
        intent = str(request.get("intent") or "").strip()
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        job = self._new_job(intent=intent, params=params, now=now)
        spec = SUPPORTED_COMMANDS.get(intent)
        if spec is None:
            job.update(
                {
                    "status": "unsupported",
                    "updated_at": now,
                    "finished_at": now,
                    "errors": [f"unsupported dashboard job intent: {intent or 'missing'}"],
                }
            )
            self._write_job(job)
            self._write_index()
            return job

        try:
            command, command_preview = self._command_for_intent(spec, params)
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
            return job

        job["kind"] = spec.kind
        job["command"] = command_preview
        job["cancellable"] = spec.cancellable
        self._write_job(job)
        self._write_index()
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
            (job for job in self._read_jobs() if job),
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
        path = self._job_path(job_id)
        if not path.exists():
            return None
        try:
            data = _read_json(path)
        except DashboardJobError:
            return None
        return data

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
            job.update(
                {
                    "status": "failed",
                    "updated_at": _utc_now(),
                    "started_at": started_at,
                    "finished_at": _utc_now(),
                    "errors": [f"job process could not start: {exc}"],
                }
            )
            self._write_job(job)
            self._write_index()
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
                "source_artifacts": [stdout_ref, stderr_ref],
            }
        )
        if status == "cancelled":
            job.setdefault("warnings", []).append("job was cancelled by dashboard request.")
        elif status == "failed":
            job.setdefault("errors", []).append(f"job exited with code {exit_code}.")
        self._write_job(job)
        self._write_index()

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
            "config_ref": _config_ref(self.config_path),
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
            "source_artifacts": [],
            "warnings": [],
            "errors": [],
        }

    def _command_for_intent(self, spec: CommandSpec, params: dict[str, Any]) -> tuple[list[str], list[str]]:
        if spec.intent == "validate":
            return self._validate_command(params)
        raise DashboardJobError(f"unsupported dashboard job intent: {spec.intent}", status="unsupported")

    def _validate_command(self, params: dict[str, Any]) -> tuple[list[str], list[str]]:
        supported_params = {"run_dir"}
        extra = sorted(set(params) - supported_params)
        if extra:
            raise DashboardJobError(f"unsupported validate job parameter(s): {', '.join(extra)}")
        command = [sys.executable, "-m", "halpha", "validate", "--config", str(self.config_path)]
        preview = ["python", "-m", "halpha", "validate", "--config", _config_ref(self.config_path)]
        run_dir = params.get("run_dir")
        if run_dir is not None:
            run_dir_path = self._validated_run_dir(str(run_dir))
            command.extend(["--run-dir", str(run_dir_path)])
            preview.extend(["--run-dir", _safe_ref(run_dir_path, base=self.base)])
        return command, preview

    def _validated_run_dir(self, value: str) -> Path:
        if not value or not value.strip():
            raise DashboardJobError("run_dir must not be empty.")
        path = Path(value)
        resolved = path if path.is_absolute() else self.base / path
        runs_root = self._run_output_root().resolve()
        try:
            resolved.resolve().relative_to(runs_root)
        except ValueError as exc:
            raise DashboardJobError("run_dir must stay within the configured run output directory.") from exc
        return resolved

    def _run_output_root(self) -> Path:
        run_config = self.config.get("run") if isinstance(self.config.get("run"), dict) else {}
        output_dir = Path(str(run_config.get("output_dir") or "runs"))
        return output_dir if output_dir.is_absolute() else self.base / output_dir

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

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_root / job_id / "job.json"

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
        values = {
            str(self.config_path),
            self.config_path.as_posix(),
            str(self.config_path.resolve()),
            self.config_path.resolve().as_posix(),
        }
        values.update(_config_private_values(self.config))
        return sorted(values, key=len, reverse=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DashboardJobError(f"{path.name} was not found.") from exc
    import json

    try:
        data = json.loads(loaded)
    except json.JSONDecodeError as exc:
        raise DashboardJobError(f"{path.name} is not valid JSON: {exc.msg}.") from exc
    if not isinstance(data, dict):
        raise DashboardJobError(f"{path.name} must be a JSON object.")
    return data


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
    return any(part in lowered for part in PRIVATE_KEY_PARTS)


def _config_base(config_path: Path) -> Path:
    parent = config_path.parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


def _config_ref(config_path: Path) -> str:
    path = Path(config_path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return "<external-config>"


def _safe_ref(path: Path, *, base: Path) -> str:
    if path.is_absolute():
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            return path.name
    return path.as_posix()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
