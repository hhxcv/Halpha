from __future__ import annotations

from contextlib import nullcontext, suppress
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import threading
from typing import Any
from uuid import uuid4

from halpha.runtime.command_job_commands import CommandSpec
from halpha.runtime.command_job_commands import CommandJobBuilder
from halpha.runtime.command_job_commands import CommandJobError
from halpha.runtime.command_job_commands import command_config_ref
from halpha.runtime.command_job_store import (
    COMMAND_JOB_LOG_ROOT_REF,
    COMMAND_JOB_STORE_ARTIFACT,
    CommandJobRepository,
    CommandJobStoreError,
    JOB_TERMINAL_STATUSES,
)
from halpha.runtime.exception_diagnostics import bounded_exception_diagnostic
from halpha.runtime.logging_utils import configure_local_logging
from halpha.runtime.command_job_execution import execute_command_job
from halpha.runtime.command_job_process import CommandJobProcess
from halpha.runtime.command_job_process import CommandJobProcessError
from halpha.runtime.command_job_process import launch_command_job_process
from halpha.runtime.command_job_process import process_identity_alive
from halpha.runtime.mutation_lease import MutationLease
from halpha.runtime.mutation_lease import MutationLeaseBlocked
from halpha.runtime.mutation_lease import acquire_mutation_lease
from halpha.runtime.mutation_lease import is_mutating_workflow_kind
from halpha.runtime.pipeline_contracts import PipelineError
from halpha.runtime.run_classification import run_trigger_env
from halpha.storage import artifact_base as _artifact_base
from halpha.storage import safe_local_ref as _safe_ref


COMMAND_JOB_INDEX = COMMAND_JOB_STORE_ARTIFACT
MAX_JOB_LOG_CHARS = 20_000
EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REDACTED_ARTIFACT_REF = "<redacted-artifact>"
RESULT_REF_PLACEHOLDERS = {EXTERNAL_ARTIFACT_REF, REDACTED_ARTIFACT_REF}
JOB_PROCESS_STATUSES = {"running", "cancel_requested"}
JOB_REQUESTED_BY_VALUES = {"CLI", "Core", "Dashboard", "Monitor"}
COMMAND_JOB_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[0-9a-f]{8}$")
RESULT_ARTIFACT_KEYS = {
    "collection_coverage",
    "event_intelligence_material",
    "manifest",
    "model_prepare_manifest",
    "health_state",
    "monitor_manifest",
    "report",
    "research_data_catalog",
    "strategy_backtest",
    "strategy_benchmark_suite",
    "strategy_effectiveness_gates",
    "strategy_experiment",
    "strategy_optimization",
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


class CommandJobManager:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: Path,
        requested_by: str = "CLI",
        requester: dict[str, Any] | None = None,
        execution_mode: str = "subprocess",
    ) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.resolved_config_path = self.config_path.resolve()
        self.base = _artifact_base(self.config_path)
        self.control_base = Path.cwd()
        self.jobs_root = Path.cwd() / COMMAND_JOB_LOG_ROOT_REF
        self.default_requested_by = _requested_by(requested_by, default="CLI")
        self.default_requester = _requester_metadata(requester)
        if execution_mode not in {"subprocess", "internal"}:
            raise ValueError("execution_mode must be subprocess or internal.")
        self.execution_mode = execution_mode
        with suppress(OSError):
            configure_local_logging(config_path=self.config_path, config=config)
        self._command_builder = CommandJobBuilder(config, config_path=self.config_path, base=self.base)
        self._repository = CommandJobRepository(config_path=self.config_path)
        self._logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._processes: dict[str, CommandJobProcess] = {}
        self._internal_running_job_ids: set[str] = set()
        self._cancel_requested: set[str] = set()
        self._reconcile_diagnostic: dict[str, Any] | None = None
        self._reconcile_unattached_jobs()

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        now = _utc_now()
        intent = str(request.get("intent") or "").strip()
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        requested_by = _requested_by(request.get("requested_by"), default=self.default_requested_by)
        requester = self._requester_for_request(request)
        job = self._new_job(intent=intent, params=params, requested_by=requested_by, requester=requester, now=now)
        try:
            job_command = self._command_builder.build(intent, params)
        except CommandJobError as exc:
            job.update(
                {
                    "status": exc.status,
                    "updated_at": now,
                    "finished_at": now,
                    "errors": [str(exc)],
                }
            )
            job = self._save_job(job, event_type=exc.status)
            if exc.status == "unsupported":
                self._logger.warning(
                    "command job was rejected.",
                    extra={
                        "event": "command_job.rejected",
                        "job_id": job["job_id"],
                        "intent": intent,
                        "status": job["status"],
                        "reason": str(exc),
                    },
                )
            else:
                self._logger.warning(
                    "command job was blocked.",
                    extra={
                        "event": "command_job.blocked",
                        "job_id": job["job_id"],
                        "intent": intent,
                        "status": job["status"],
                        "reason": str(exc),
                    },
                )
            return job

        spec = job_command.spec
        command = job_command.command
        command_preview = ["internal", intent] if self.execution_mode == "internal" else job_command.preview
        job["kind"] = spec.kind
        job["command"] = command_preview
        job["cancellable"] = spec.cancellable and self.execution_mode != "internal"
        job = self._save_job(job, event_type="queued")
        self._logger.info(
            "command job queued.",
            extra={
                "event": "command_job.queued",
                "job_id": job["job_id"],
                "intent": intent,
                "kind": spec.kind,
                "command_preview": command_preview,
            },
        )
        thread = threading.Thread(
            target=self._run_job,
            args=(job["job_id"], command, spec),
            name=f"command-job-{job['job_id']}",
            daemon=True,
        )
        thread.start()
        return job

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        try:
            jobs = sorted(
                (self._normalize_runtime_job_state(job) for job in self._repository.list_jobs(limit=limit) if job),
                key=lambda item: str(item.get("created_at") or ""),
                reverse=True,
            )[:limit]
        except CommandJobStoreError as exc:
            return self._job_list_store_failure(exc)
        status = "degraded" if self._reconcile_diagnostic else "available" if jobs else "missing"
        warnings = [] if jobs else ["command job history is empty."]
        errors: list[str] = []
        if self._reconcile_diagnostic:
            warnings = [*warnings, "transient command-job reconciliation could not read runtime state."]
            errors.append("command job state store could not be read during startup reconciliation.")
        return {
            "schema_version": 1,
            "artifact_type": "command_job_list",
            "status": status,
            "source_artifacts": [COMMAND_JOB_INDEX],
            "jobs": jobs,
            "warnings": warnings,
            "errors": errors,
            **({"diagnostic": self._reconcile_diagnostic} if self._reconcile_diagnostic else {}),
        }

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if not _is_command_job_id(job_id):
            return None
        try:
            data = self._repository.get_job(job_id)
        except CommandJobStoreError as exc:
            return self._job_store_failure(job_id=job_id, exc=exc)
        if data is None:
            return None
        try:
            return self._normalize_runtime_job_state(data)
        except CommandJobStoreError as exc:
            return self._job_store_failure(job_id=job_id, exc=exc)

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self.get_job(job_id)
            if _is_store_read_failure(job):
                return job
            if job is None:
                return {
                    "schema_version": 1,
                    "artifact_type": "command_job",
                    "job_id": job_id,
                    "status": "missing",
                    "warnings": ["command job was not found."],
                    "errors": [],
                }
            status = str(job.get("status") or "unknown")
            if status in JOB_TERMINAL_STATUSES:
                job.setdefault("warnings", []).append(f"job is already {status}.")
                return job
            job_process = self._processes.get(job_id)
            if job_process is None:
                if self._is_internal_job_attached(job):
                    job["runtime_attached"] = True
                    job["process_alive"] = True
                    warnings = job.setdefault("warnings", [])
                    if isinstance(warnings, list):
                        warnings.append("internal command job is running and cannot be cancelled.")
                    return job
                if self._persisted_process_identity_alive(job):
                    job["runtime_attached"] = False
                    job["process_alive"] = True
                    warnings = job.setdefault("warnings", [])
                    if isinstance(warnings, list):
                        warnings.append(
                            "job process is still alive but is not attached to this runtime; "
                            "it will not be cancelled without verified local ownership."
                        )
                    return job
                return self._mark_process_lost(job)
            self._cancel_requested.add(job_id)
            job["status"] = "cancel_requested"
            job["updated_at"] = _utc_now()
            job["cancellation_requested_at"] = job["updated_at"]
            job["cancel_reason"] = "caller_request"
            job = self._save_job(job, event_type="cancel_requested")
            job_process.request_cancel()
            return job

    def _run_job(self, job_id: str, command: list[str], spec: CommandSpec) -> None:
        job = self.get_job(job_id)
        if job is None or _is_store_read_failure(job):
            return
        started_at = _utc_now()
        self._logger.info(
            "command job starting.",
            extra={
                "event": "command_job.start",
                "job_id": job_id,
                "intent": job.get("intent"),
                "kind": spec.kind,
                "command_preview": job.get("command"),
            },
        )
        try:
            lease = self._acquire_job_mutation_lease(job, spec=spec)
        except MutationLeaseBlocked as exc:
            self._mark_job_blocked_by_mutation_lease(job, started_at=started_at, exc=exc)
            return
        except PipelineError as exc:
            self._mark_job_failed_before_process(job, started_at=started_at, exc=exc)
            return

        lease_context = lease if lease is not None else nullcontext()
        if self.execution_mode == "internal":
            self._run_internal_job(job, spec=spec, started_at=started_at, lease_context=lease_context)
            return

        try:
            with lease_context:
                process_env = lease.subprocess_env(os.environ) if lease is not None else dict(os.environ)
                process_env = run_trigger_env(process_env, _job_run_trigger(job))
                job_process = launch_command_job_process(
                    command,
                    cwd=self.base,
                    env=process_env,
                    popen_factory=subprocess.Popen,
                )
                with self._lock:
                    self._processes[job_id] = job_process
                    job.update(
                        {
                            "status": "running",
                            "started_at": started_at,
                            "updated_at": started_at,
                            "pid": job_process.pid,
                            "process_identity": job_process.identity,
                            "process_termination": job_process.termination,
                        }
                    )
                    self._save_job(job, event_type="started")

                stdout, stderr = job_process.communicate()
        except (CommandJobProcessError, OSError) as exc:
            finished_at = _utc_now()
            diagnostic = bounded_exception_diagnostic(exc, context={"phase": "process_start"})
            reason = self._redact_text(f"job process could not start: {exc}")
            logs = self._write_job_logs(job_id, stdout="", stderr=f"{reason}\n")
            job.update(
                {
                    "status": "failed",
                    "updated_at": finished_at,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "errors": [reason],
                    "diagnostic": diagnostic,
                    "logs": logs,
                    "source_artifacts": [logs["stdout_ref"], logs["stderr_ref"]],
                }
            )
            self._save_job(job, event_type="start_failed")
            self._logger.error(
                "command job process could not start.",
                extra={
                    "event": "command_job.start_failed",
                    "job_id": job_id,
                    "intent": job.get("intent"),
                    "kind": spec.kind,
                    "reason": reason,
                    "phase": "process_start",
                    "exception_type": type(exc).__name__,
                    "diagnostic": diagnostic,
                },
            )
            return

        self._finish_subprocess_job(
            job_id=job_id,
            job=job,
            spec=spec,
            job_process=job_process,
            stdout=stdout,
            stderr=stderr,
        )

    def _finish_subprocess_job(
        self,
        *,
        job_id: str,
        job: dict[str, Any],
        spec: CommandSpec,
        job_process: CommandJobProcess,
        stdout: str,
        stderr: str,
    ) -> None:
        finished_at = _utc_now()
        was_cancelled = job_id in self._cancel_requested
        if was_cancelled:
            self._cancel_requested.discard(job_id)
        try:
            job = self._repository.get_job(job_id) or job
        except CommandJobStoreError:
            return
        stdout_ref, stdout_truncated, stdout_chars = self._write_log(job_id, "stdout.log", stdout)
        stderr_ref, stderr_truncated, stderr_chars = self._write_log(job_id, "stderr.log", stderr)
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
        process_termination = dict(job_process.termination)
        exit_code = int(job_process.returncode or 0)
        cancellation_unconfirmed = was_cancelled and process_termination.get("confirmed_exit") is not True
        cleanup_unconfirmed = (
            process_termination.get("cleanup_after_root_exit") is True
            and process_termination.get("confirmed_exit") is not True
        )
        status = (
            "failed"
            if cancellation_unconfirmed or cleanup_unconfirmed
            else "cancelled"
            if was_cancelled
            else "succeeded"
            if exit_code == 0
            else "failed"
        )
        job.update(
            {
                "status": status,
                "updated_at": finished_at,
                "finished_at": finished_at,
                "exit_code": exit_code,
                "process_identity": job_process.identity,
                "process_termination": process_termination,
                "logs": {
                    "stdout_ref": stdout_ref,
                    "stderr_ref": stderr_ref,
                    "stdout_chars": stdout_chars,
                    "stderr_chars": stderr_chars,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "max_chars": MAX_JOB_LOG_CHARS,
                },
                "result_refs": result_refs,
                "source_artifacts": source_artifacts,
            }
        )
        self._promote_stdout_diagnostics(job, stdout, failed=status == "failed")
        if status == "cancelled":
            job.setdefault("warnings", []).append("job was cancelled by caller request.")
        elif cancellation_unconfirmed:
            job.setdefault("errors", []).append("job cancellation could not confirm complete process-tree termination.")
        elif cleanup_unconfirmed:
            job.setdefault("errors", []).append("job process tree cleanup could not confirm descendant termination.")
        elif status == "failed" and not job.get("errors"):
            job.setdefault("errors", []).append(f"job exited with code {exit_code}.")
        self._save_job(job, event_type=status)
        with self._lock:
            self._processes.pop(job_id, None)
        self._logger.log(
            logging.INFO if status == "succeeded" else logging.WARNING,
            "command job finished.",
            extra={
                "event": "command_job.finished",
                "job_id": job_id,
                "intent": job.get("intent"),
                "kind": spec.kind,
                "status": status,
                "exit_code": exit_code,
            },
        )

    def _run_internal_job(
        self,
        job: dict[str, Any],
        *,
        spec: CommandSpec,
        started_at: str,
        lease_context: Any,
    ) -> None:
        job_id = str(job.get("job_id") or "")
        with self._lock:
            self._internal_running_job_ids.add(job_id)
            job.update(
                {
                    "status": "running",
                    "started_at": started_at,
                    "updated_at": started_at,
                    "pid": None,
                    "process_identity": {
                        "schema_version": 1,
                        "platform": "python",
                        "strategy": "internal_thread",
                        "manager_pid": os.getpid(),
                        "verified": True,
                        "private_values_embedded": False,
                    },
                    "process_termination": {
                        "schema_version": 1,
                        "status": "not_applicable",
                        "strategy": "internal_thread",
                        "confirmed_exit": True,
                        "forced": False,
                        "private_values_embedded": False,
                    },
                }
            )
            self._save_job(job, event_type="started")
        try:
            with lease_context:
                result = execute_command_job(
                    self.config,
                    config_path=self.config_path,
                    spec=spec,
                    params=job.get("params") if isinstance(job.get("params"), dict) else {},
                    run_trigger=_job_run_trigger(job),
                )
        except Exception as exc:
            reason = self._redact_text(str(exc))
            stdout = ""
            stderr = f"internal command job failed: {reason}\n"
            exit_code = 1
            diagnostic = bounded_exception_diagnostic(exc, context={"phase": "internal_execution"})
            self._logger.error(
                "internal command job failed.",
                extra={
                    "event": "command_job.internal_failed",
                    "job_id": job_id,
                    "intent": job.get("intent"),
                    "kind": spec.kind,
                    "phase": "internal_execution",
                    "reason": reason,
                    "exception_type": type(exc).__name__,
                    "diagnostic": diagnostic,
                },
            )
        else:
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.exit_code
            diagnostic = None

        finished_at = _utc_now()
        try:
            job = self._repository.get_job(job_id) or job
        except CommandJobStoreError:
            return
        stdout_ref, stdout_truncated, stdout_chars = self._write_log(job_id, "stdout.log", stdout)
        stderr_ref, stderr_truncated, stderr_chars = self._write_log(job_id, "stderr.log", stderr)
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
        status = "succeeded" if exit_code == 0 else "failed"
        job.update(
            {
                "status": status,
                "updated_at": finished_at,
                "finished_at": finished_at,
                "exit_code": exit_code,
                "pid": None,
                "logs": {
                    "stdout_ref": stdout_ref,
                    "stderr_ref": stderr_ref,
                    "stdout_chars": stdout_chars,
                    "stderr_chars": stderr_chars,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "max_chars": MAX_JOB_LOG_CHARS,
                },
                "result_refs": result_refs,
                "source_artifacts": source_artifacts,
            }
        )
        if diagnostic is not None:
            job["diagnostic"] = diagnostic
        self._promote_stdout_diagnostics(job, stdout, failed=status == "failed")
        if status == "failed" and not job.get("errors"):
            job.setdefault("errors", []).append(f"job exited with code {exit_code}.")
        try:
            self._save_job(job, event_type=status)
        finally:
            with self._lock:
                self._internal_running_job_ids.discard(job_id)
        self._logger.log(
            logging.INFO if status == "succeeded" else logging.WARNING,
            "command job finished.",
            extra={
                "event": "command_job.finished",
                "job_id": job_id,
                "intent": job.get("intent"),
                "kind": spec.kind,
                "status": status,
                "exit_code": exit_code,
                "execution_mode": "internal",
            },
        )

    def _acquire_job_mutation_lease(self, job: dict[str, Any], *, spec: CommandSpec) -> MutationLease | None:
        if not is_mutating_workflow_kind(spec.kind):
            return None
        return acquire_mutation_lease(
            config_path=self.config_path,
            owner_kind="command_job",
            workflow=spec.kind,
            requested_by=str(job.get("requested_by") or self.default_requested_by),
            owner_id=str(job.get("job_id") or ""),
            owner_pid=os.getpid(),
        )

    def _mark_job_blocked_by_mutation_lease(
        self,
        job: dict[str, Any],
        *,
        started_at: str,
        exc: MutationLeaseBlocked,
    ) -> None:
        now = _utc_now()
        job.update(
            {
                "status": "blocked",
                "updated_at": now,
                "started_at": started_at,
                "finished_at": now,
                "cancellable": False,
                "errors": [str(exc)],
                "diagnostic": exc.error_details,
            }
        )
        self._save_job(job, event_type="blocked")
        self._logger.warning(
            "command job was blocked by runtime mutation lease.",
            extra={
                "event": "command_job.blocked",
                "job_id": job.get("job_id"),
                "intent": job.get("intent"),
                "kind": job.get("kind"),
                "reason": str(exc),
            },
        )

    def _mark_job_failed_before_process(self, job: dict[str, Any], *, started_at: str, exc: PipelineError) -> None:
        now = _utc_now()
        reason = self._redact_text(str(exc))
        logs = self._write_job_logs(
            str(job.get("job_id") or ""),
            stdout="",
            stderr=f"command job failed before starting process: {reason}\n",
        )
        job.update(
            {
                "status": "failed",
                "updated_at": now,
                "started_at": started_at,
                "finished_at": now,
                "cancellable": False,
                "errors": [reason],
                "diagnostic": exc.error_details,
                "logs": logs,
                "source_artifacts": [logs["stdout_ref"], logs["stderr_ref"]],
            }
        )
        self._save_job(job, event_type="start_failed")
        self._logger.error(
            "command job failed before starting process.",
            extra={
                "event": "command_job.start_failed",
                "job_id": job.get("job_id"),
                "intent": job.get("intent"),
                "kind": job.get("kind"),
                "reason": reason,
                "phase": "pre_process",
            },
        )

    def _new_job(
        self,
        *,
        intent: str,
        params: dict[str, Any],
        requested_by: str,
        requester: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        job_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        job_dir = self.jobs_root / job_id
        return {
            "schema_version": 1,
            "artifact_type": "command_job",
            "job_id": job_id,
            "kind": "command",
            "intent": intent,
            "requested_by": requested_by,
            "requester": self._redact_value(requester),
            "params": self._redact_value(params),
            "config_ref": command_config_ref(self.config_path),
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "pid": None,
            "exit_code": None,
            "cancellable": False,
            "command": [],
            "job_dir": _safe_ref(job_dir, base=self.control_base),
            "logs": {
                "stdout_ref": _safe_ref(job_dir / "stdout.log", base=self.control_base),
                "stderr_ref": _safe_ref(job_dir / "stderr.log", base=self.control_base),
                "stdout_chars": 0,
                "stderr_chars": 0,
                "stdout_truncated": False,
                "stderr_truncated": False,
                "max_chars": MAX_JOB_LOG_CHARS,
            },
            "result_refs": {},
            "source_artifacts": [],
            "warnings": [],
            "errors": [],
        }

    def _job_list_store_failure(self, exc: CommandJobStoreError) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_type": "command_job_list",
            "status": "failed",
            "source_artifacts": [COMMAND_JOB_INDEX],
            "jobs": [],
            "warnings": [],
            "errors": ["command job state store could not be read."],
            "diagnostic": exc.diagnostic,
        }

    def _job_store_failure(self, *, job_id: str, exc: CommandJobStoreError) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_type": "command_job",
            "job_id": job_id,
            "status": "failed",
            "store_read_failed": True,
            "cancellable": False,
            "warnings": [],
            "errors": ["command job state store could not be read."],
            "diagnostic": exc.diagnostic,
        }

    def _save_job(self, job: dict[str, Any], *, event_type: str) -> dict[str, Any]:
        return self._repository.save_job(self._redact_value(job), event_type=event_type)

    def _write_log(self, job_id: str, filename: str, content: str | None) -> tuple[str, bool, int]:
        path = self.jobs_root / job_id / filename
        safe = self._redact_text(content or "")
        bounded = safe[:MAX_JOB_LOG_CHARS]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bounded, encoding="utf-8")
        return _safe_ref(path, base=self.control_base), len(safe) > MAX_JOB_LOG_CHARS, len(safe)

    def _write_job_logs(self, job_id: str, *, stdout: str | None, stderr: str | None) -> dict[str, Any]:
        stdout_ref, stdout_truncated, stdout_chars = self._write_log(job_id, "stdout.log", stdout)
        stderr_ref, stderr_truncated, stderr_chars = self._write_log(job_id, "stderr.log", stderr)
        return {
            "stdout_ref": stdout_ref,
            "stderr_ref": stderr_ref,
            "stdout_chars": stdout_chars,
            "stderr_chars": stderr_chars,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "max_chars": MAX_JOB_LOG_CHARS,
        }

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

    def _promote_stdout_diagnostics(self, job: dict[str, Any], stdout: str | None, *, failed: bool = False) -> None:
        warnings: list[str] = []
        errors: list[str] = []
        for line in (stdout or "").splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue
            key = key.strip().lower()
            message = self._redact_text(value.strip())
            if not message:
                continue
            if key == "warning":
                warnings.append(message)
            elif key == "error":
                errors.append(message)
            elif failed and key == "reason" and message.lower() not in {"none", "null"}:
                errors.append(message)
        if warnings:
            job["warnings"] = _unique_strings([*_strings(job.get("warnings")), *warnings])
        if errors:
            job["errors"] = _unique_strings([*_strings(job.get("errors")), *errors])

    def _enrich_persisted_stdout_diagnostics(self, job: dict[str, Any]) -> dict[str, Any]:
        if str(job.get("status") or "").lower() != "failed":
            return job
        stdout = self._read_persisted_stdout(job)
        if stdout is None:
            return job
        existing_errors = _strings(job.get("errors"))
        only_generic_exit = bool(existing_errors) and all(_is_generic_job_exit_error(item) for item in existing_errors)
        self._promote_stdout_diagnostics(job, stdout, failed=True)
        if only_generic_exit:
            specific_errors = [item for item in _strings(job.get("errors")) if not _is_generic_job_exit_error(item)]
            if specific_errors:
                job["errors"] = _unique_strings(specific_errors)
        return job

    def _read_persisted_stdout(self, job: dict[str, Any]) -> str | None:
        logs = job.get("logs")
        if not isinstance(logs, dict):
            return None
        ref = str(logs.get("stdout_ref") or "").strip().replace("\\", "/")
        if not ref or ref in {EXTERNAL_ARTIFACT_REF, REDACTED_ARTIFACT_REF}:
            return None
        if not ref.startswith(f"{COMMAND_JOB_LOG_ROOT_REF}/") or not ref.endswith("/stdout.log"):
            return None
        path = (self.control_base / ref).resolve()
        root = (self.control_base / COMMAND_JOB_LOG_ROOT_REF).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return None
        try:
            return path.read_text(encoding="utf-8")[:MAX_JOB_LOG_CHARS]
        except OSError:
            return None

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
        ref = _safe_ref(path, base=self.base)
        if ref == EXTERNAL_ARTIFACT_REF:
            return EXTERNAL_ARTIFACT_REF
        return REDACTED_ARTIFACT_REF if self._redact_text(ref) != ref else ref

    def _normalize_runtime_job_state(self, job: dict[str, Any]) -> dict[str, Any]:
        job = self._enrich_persisted_stdout_diagnostics(job)
        status = str(job.get("status") or "").lower()
        if status not in JOB_PROCESS_STATUSES:
            return job
        job_id = str(job.get("job_id") or "")
        if job_id in self._processes:
            job["runtime_attached"] = True
            job["process_alive"] = True
            self._attach_active_run_refs(job)
            return job
        if self._is_internal_job_attached(job):
            job["runtime_attached"] = True
            job["process_alive"] = True
            self._attach_active_run_refs(job)
            return job

        latest = self._repository.get_job(job_id)
        if latest is not None and str(latest.get("status") or "").lower() != status:
            return self._normalize_runtime_job_state(latest)
        if self._persisted_process_identity_alive(job):
            job["runtime_attached"] = False
            job["process_alive"] = True
            self._attach_active_run_refs(job)
            warnings = job.setdefault("warnings", [])
            if isinstance(warnings, list):
                message = (
                    "job process identity is still alive after the owning runtime restarted; "
                    "status is preserved until the process exits."
                )
                if message not in warnings:
                    warnings.append(message)
            return job
        return self._mark_process_lost(job)

    def _attach_active_run_refs(self, job: dict[str, Any]) -> None:
        if str(job.get("intent") or "") not in {"run", "run_no_codex", "run_until"}:
            return
        refs = job.get("result_refs")
        if not isinstance(refs, dict):
            refs = {}
        if refs.get("run_manifest"):
            return
        discovered = self._discover_run_refs_for_job(str(job.get("job_id") or ""))
        if not discovered:
            return
        refs = {**refs, **discovered}
        job["result_refs"] = refs
        source_artifacts = _strings(job.get("source_artifacts"))
        for key, ref in discovered.items():
            if key != "run_id" and ref not in RESULT_REF_PLACEHOLDERS:
                source_artifacts.append(ref)
        job["source_artifacts"] = _unique_strings(source_artifacts)

    def _discover_run_refs_for_job(self, job_id: str) -> dict[str, str]:
        if not COMMAND_JOB_ID_RE.match(job_id):
            return {}
        run_root = self._run_output_root()
        if not run_root.is_dir():
            return {}
        try:
            manifests = sorted(
                run_root.glob("*/run_manifest.json"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return {}
        for manifest_path in manifests[:100]:
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(manifest, dict):
                continue
            trigger = manifest.get("trigger")
            if not isinstance(trigger, dict) or trigger.get("job_id") != job_id:
                continue
            run_id = str(manifest.get("run_id") or manifest_path.parent.name)
            refs = {
                "run_id": self._redact_text(run_id),
                "run_manifest": self._safe_output_ref(str(manifest_path)),
            }
            report_ref = manifest.get("artifacts", {}).get("report") if isinstance(manifest.get("artifacts"), dict) else None
            if isinstance(report_ref, str) and report_ref:
                refs["report"] = self._safe_output_ref(str(manifest_path.parent / report_ref))
            return refs
        return {}

    def _run_output_root(self) -> Path:
        run = self.config.get("run")
        output_dir = Path(str(run.get("output_dir") if isinstance(run, dict) else "runs"))
        return output_dir if output_dir.is_absolute() else self.base / output_dir

    def _persisted_process_identity_alive(self, job: dict[str, Any]) -> bool:
        identity = job.get("process_identity")
        if not isinstance(identity, dict):
            return False
        return process_identity_alive(identity)

    def _is_internal_job_attached(self, job: dict[str, Any]) -> bool:
        job_id = str(job.get("job_id") or "")
        identity = job.get("process_identity")
        if not isinstance(identity, dict) or identity.get("strategy") != "internal_thread":
            return False
        return job_id in self._internal_running_job_ids

    def _mark_process_lost(self, job: dict[str, Any]) -> dict[str, Any]:
        status = str(job.get("status") or "").lower()
        job["runtime_attached"] = False
        job["process_alive"] = False
        job["status"] = "cancelled" if status == "cancel_requested" else "failed"
        job["updated_at"] = _utc_now()
        job["finished_at"] = job["updated_at"]
        job["cancellable"] = False
        message = (
            "job process identity was lost after the owning runtime restarted; "
            "the recorded PID was not treated as proof of the original job."
        )
        if job["status"] == "cancelled":
            warnings = job.setdefault("warnings", [])
            if isinstance(warnings, list) and message not in warnings:
                warnings.append(message)
        else:
            errors = job.setdefault("errors", [])
            if isinstance(errors, list) and message not in errors:
                errors.append(message)
        try:
            return self._save_job(job, event_type="process_lost")
        except CommandJobStoreError:
            latest = self._repository.get_job(str(job.get("job_id") or ""))
            if latest is not None and str(latest.get("status") or "").lower() in JOB_TERMINAL_STATUSES:
                return latest
            raise

    def _reconcile_unattached_jobs(self) -> None:
        try:
            transient_jobs = self._repository.list_transient_jobs()
        except CommandJobStoreError as exc:
            self._reconcile_diagnostic = exc.diagnostic
            self._logger.error(
                "command job transient reconciliation could not read runtime state.",
                extra={
                    "event": "command_job.reconcile_failed",
                    "status": "failed",
                    "diagnostic": exc.diagnostic,
                },
            )
            return
        for job in transient_jobs:
            self._normalize_runtime_job_state(job)

    def _requester_for_request(self, request: dict[str, Any]) -> dict[str, Any]:
        requester = dict(self.default_requester)
        request_value = request.get("requester")
        if isinstance(request_value, dict):
            requester.update(_requester_metadata(request_value))
        return requester

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


def _requested_by(value: Any, *, default: str) -> str:
    requested_by = str(value or "").strip()
    if requested_by in JOB_REQUESTED_BY_VALUES:
        return requested_by
    return default if default in JOB_REQUESTED_BY_VALUES else "CLI"


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _is_generic_job_exit_error(value: str) -> bool:
    return re.fullmatch(r"job exited with code -?\d+\.", str(value or "").strip()) is not None


def _job_run_trigger(job: dict[str, Any]) -> dict[str, Any]:
    trigger: dict[str, Any] = {
        "source": _requested_by(job.get("requested_by"), default="CLI"),
        "intent": str(job.get("intent") or "command_job"),
        "job_id": str(job.get("job_id") or ""),
    }
    requester = job.get("requester")
    if isinstance(requester, dict):
        for source_key, trigger_key in (
            ("schedule_id", "schedule_id"),
            ("dispatch_kind", "dispatch_kind"),
            ("monitor_cycle_id", "monitor_cycle_id"),
            ("source_keys", "source_keys"),
        ):
            if source_key in requester:
                trigger[trigger_key] = requester[source_key]
    return trigger


def _is_store_read_failure(job: dict[str, Any] | None) -> bool:
    return isinstance(job, dict) and job.get("store_read_failed") is True


def _requester_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    metadata: dict[str, Any] = {}
    for key, item in sorted(value.items()):
        if isinstance(item, str):
            text = item.strip()
            if text:
                metadata[str(key)] = text[:200]
        elif isinstance(item, (int, float, bool)) or item is None:
            metadata[str(key)] = item
    return metadata


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


def _is_command_job_id(value: str) -> bool:
    return COMMAND_JOB_ID_RE.fullmatch(str(value or "")) is not None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
