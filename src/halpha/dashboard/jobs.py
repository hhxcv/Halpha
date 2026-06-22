from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any
from uuid import uuid4

from halpha.dashboard.time import parse_utc_timestamp, utc_now_timestamp
from halpha.runtime.exception_diagnostics import bounded_exception_diagnostic
from halpha.runtime.logging_utils import configure_local_logging
from halpha.pipeline import STAGE_ORDER
from halpha.storage import config_base as _config_base, read_json_object, safe_local_ref, write_json


DASHBOARD_JOBS_DIR = "runs/dashboard/jobs"
DASHBOARD_JOB_INDEX = "runs/dashboard/jobs/index.json"
MAX_JOB_LOG_CHARS = 20_000
CODEX_STAGE = "run_codex_report"
STALE_RUNNING_JOB_GRACE_SECONDS = 30
EXTERNAL_ARTIFACT_REF = "<external-artifact>"
REDACTED_ARTIFACT_REF = "<redacted-artifact>"
RESULT_REF_PLACEHOLDERS = {EXTERNAL_ARTIFACT_REF, REDACTED_ARTIFACT_REF}
JOB_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started"}
JOB_PROCESS_STATUSES = {"running"}
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


class DashboardJobError(Exception):
    def __init__(self, message: str, *, status: str = "blocked") -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class CommandSpec:
    intent: str
    kind: str
    cancellable: bool
    cli_parts: tuple[str, ...]
    allow_run_dir: bool = False
    extra_cli_parts: tuple[str, ...] = ()
    stage_param: str | None = None
    codex_confirmation: str | None = None
    param_mode: str | None = None


SUPPORTED_COMMANDS = {
    "run": CommandSpec(
        intent="run",
        kind="product_run",
        cancellable=True,
        cli_parts=("run",),
        codex_confirmation="always",
    ),
    "run_no_codex": CommandSpec(
        intent="run_no_codex",
        kind="product_run",
        cancellable=True,
        cli_parts=("run",),
        extra_cli_parts=("--no-codex",),
    ),
    "run_until": CommandSpec(
        intent="run_until",
        kind="product_run",
        cancellable=True,
        cli_parts=("run",),
        stage_param="until",
        codex_confirmation="stage_reaches_codex",
    ),
    "stage_rerun": CommandSpec(
        intent="stage_rerun",
        kind="stage_rerun",
        cancellable=True,
        cli_parts=("stage",),
        allow_run_dir=True,
        stage_param="positional",
        codex_confirmation="stage_is_codex",
    ),
    "validate": CommandSpec(
        intent="validate",
        kind="product_validation",
        cancellable=True,
        cli_parts=("validate",),
        allow_run_dir=True,
    ),
    "data_inspect": CommandSpec(
        intent="data_inspect",
        kind="data_inspection",
        cancellable=True,
        cli_parts=("data", "inspect"),
        allow_run_dir=True,
    ),
    "outcomes_inspect": CommandSpec(
        intent="outcomes_inspect",
        kind="outcome_inspection",
        cancellable=True,
        cli_parts=("outcomes", "inspect"),
        allow_run_dir=True,
    ),
    "workbench_build": CommandSpec(
        intent="workbench_build",
        kind="workbench_build",
        cancellable=True,
        cli_parts=("workbench", "build"),
        allow_run_dir=True,
    ),
    "workbench_inspect": CommandSpec(
        intent="workbench_inspect",
        kind="workbench_inspection",
        cancellable=True,
        cli_parts=("workbench", "inspect"),
    ),
    "monitor_inspect": CommandSpec(
        intent="monitor_inspect",
        kind="monitor_inspection",
        cancellable=True,
        cli_parts=("monitor", "inspect"),
    ),
    "monitor_dry_run": CommandSpec(
        intent="monitor_dry_run",
        kind="monitor_dry_run",
        cancellable=True,
        cli_parts=("monitor", "run"),
        extra_cli_parts=("--dry-run",),
    ),
    "monitor_once": CommandSpec(
        intent="monitor_once",
        kind="monitor_cycle",
        cancellable=True,
        cli_parts=("monitor", "run"),
        extra_cli_parts=("--once",),
    ),
    "monitor_loop": CommandSpec(
        intent="monitor_loop",
        kind="monitor_loop",
        cancellable=True,
        cli_parts=("monitor", "run"),
        param_mode="monitor_loop",
    ),
    "backtest": CommandSpec(
        intent="backtest",
        kind="strategy_backtest",
        cancellable=True,
        cli_parts=("backtest",),
        param_mode="backtest",
    ),
    "experiment": CommandSpec(
        intent="experiment",
        kind="strategy_experiment",
        cancellable=True,
        cli_parts=("experiment",),
        param_mode="experiment",
    ),
    "text_models_prepare": CommandSpec(
        intent="text_models_prepare",
        kind="text_model_preparation",
        cancellable=True,
        cli_parts=("text-models", "prepare"),
        param_mode="text_models_prepare",
    ),
    "text_intel": CommandSpec(
        intent="text_intel",
        kind="text_intelligence",
        cancellable=True,
        cli_parts=("text-intel",),
        param_mode="text_intel",
    ),
}


class DashboardJobManager:
    def __init__(self, config: dict[str, Any], *, config_path: Path) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.base = _config_base(self.config_path)
        self.jobs_root = self.base / DASHBOARD_JOBS_DIR
        with suppress(OSError):
            configure_local_logging(config_path=self.config_path, config=config)
        self._logger = logging.getLogger(__name__)
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
            self._logger.warning(
                "Dashboard job was rejected.",
                extra={
                    "event": "dashboard.job.rejected",
                    "job_id": job["job_id"],
                    "intent": intent,
                    "status": job["status"],
                    "reason": job["errors"][0],
                },
            )
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
            "result_refs": {},
            "source_artifacts": [],
            "warnings": [],
            "errors": [],
        }

    def _command_for_intent(self, spec: CommandSpec, params: dict[str, Any]) -> tuple[list[str], list[str]]:
        supported_params = {"run_dir"} if spec.allow_run_dir else set()
        if spec.stage_param:
            supported_params.add("stage_name")
        if spec.codex_confirmation:
            supported_params.add("confirm_codex")
        supported_params.update(self._param_mode_supported_params(spec.param_mode))
        extra = sorted(set(params) - supported_params)
        if extra:
            raise DashboardJobError(f"unsupported {spec.intent} job parameter(s): {', '.join(extra)}")
        stage_name = self._validated_stage_name(params.get("stage_name")) if spec.stage_param else None
        if self._requires_codex_confirmation(spec, stage_name) and params.get("confirm_codex") is not True:
            raise DashboardJobError("confirm_codex must be true for dashboard jobs that may invoke Codex.")
        cli_parts = list(spec.cli_parts)
        if spec.stage_param == "positional" and stage_name:
            cli_parts.append(stage_name)
        command = [sys.executable, "-m", "halpha", *cli_parts, "--config", str(self.config_path)]
        preview = ["python", "-m", "halpha", *cli_parts, "--config", _config_ref(self.config_path)]
        if spec.stage_param == "until" and stage_name:
            command.extend(["--until", stage_name])
            preview.extend(["--until", stage_name])
        if spec.extra_cli_parts:
            command.extend(spec.extra_cli_parts)
            preview.extend(spec.extra_cli_parts)
        self._extend_param_mode_args(spec.param_mode, params, command, preview)
        run_dir = params.get("run_dir")
        if run_dir is not None:
            run_dir_path = self._validated_run_dir(str(run_dir))
            command.extend(["--run-dir", str(run_dir_path)])
            preview.extend(["--run-dir", _safe_ref(run_dir_path, base=self.base)])
        return command, preview

    def _param_mode_supported_params(self, param_mode: str | None) -> set[str]:
        if param_mode == "backtest":
            return {"strategy_name", "symbol", "timeframe", "output_dir"}
        if param_mode == "experiment":
            return {"strategy_names", "output_dir"}
        if param_mode == "text_models_prepare":
            return {"output_dir"}
        if param_mode == "text_intel":
            return {"input_path", "output_dir"}
        if param_mode == "monitor_loop":
            return {"max_cycles", "interval_seconds"}
        return set()

    def _extend_param_mode_args(
        self,
        param_mode: str | None,
        params: dict[str, Any],
        command: list[str],
        preview: list[str],
    ) -> None:
        if param_mode == "backtest":
            strategy_name = self._validated_strategy_name(params.get("strategy_name"), param_name="strategy_name")
            symbol = self._validated_symbol(params.get("symbol"))
            timeframe = self._validated_timeframe(params.get("timeframe"))
            command.extend(["--strategy", strategy_name, "--symbol", symbol, "--timeframe", timeframe])
            preview.extend(["--strategy", strategy_name, "--symbol", symbol, "--timeframe", timeframe])
            self._extend_optional_output_dir(params, command, preview)
        elif param_mode == "experiment":
            strategy_names = self._validated_strategy_names(params.get("strategy_names"))
            for strategy_name in strategy_names:
                command.extend(["--strategy", strategy_name])
                preview.extend(["--strategy", strategy_name])
            self._extend_optional_output_dir(params, command, preview)
        elif param_mode == "text_models_prepare":
            self._extend_optional_output_dir(params, command, preview)
        elif param_mode == "text_intel":
            input_path = params.get("input_path")
            if input_path is not None:
                if not isinstance(input_path, str):
                    raise DashboardJobError("input_path must be a string.")
                path = self._validated_input_path(str(input_path))
                command.extend(["--input", str(path)])
                preview.extend(["--input", _safe_ref(path, base=self.base)])
            self._extend_optional_output_dir(params, command, preview)
        elif param_mode == "monitor_loop":
            max_cycles = self._validated_positive_int(params.get("max_cycles"), param_name="max_cycles")
            command.extend(["--max-cycles", str(max_cycles)])
            preview.extend(["--max-cycles", str(max_cycles)])
            interval_seconds = params.get("interval_seconds")
            if interval_seconds is not None:
                interval = self._validated_positive_int(interval_seconds, param_name="interval_seconds")
                command.extend(["--interval-seconds", str(interval)])
                preview.extend(["--interval-seconds", str(interval)])

    def _extend_optional_output_dir(
        self,
        params: dict[str, Any],
        command: list[str],
        preview: list[str],
    ) -> None:
        output_dir = params.get("output_dir")
        if output_dir is None:
            return
        if not isinstance(output_dir, str):
            raise DashboardJobError("output_dir must be a string.")
        path = self._validated_local_path(str(output_dir), param_name="output_dir")
        command.extend(["--output-dir", str(path)])
        preview.extend(["--output-dir", _safe_ref(path, base=self.base)])

    def _validated_strategy_name(self, value: Any, *, param_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DashboardJobError(f"{param_name} must not be empty.")
        strategy_name = value.strip()
        if strategy_name not in self._configured_strategy_names():
            raise DashboardJobError(f"{param_name} is not configured or enabled: {strategy_name}.")
        return strategy_name

    def _validated_strategy_names(self, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or not value:
            raise DashboardJobError("strategy_names must be a non-empty list when provided.")
        names = [self._validated_strategy_name(item, param_name="strategy_names") for item in value]
        return names

    def _validated_symbol(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DashboardJobError("symbol must not be empty.")
        symbol = value.strip()
        if symbol not in self._configured_symbols():
            raise DashboardJobError(f"symbol is not configured: {symbol}.")
        return symbol

    def _validated_timeframe(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DashboardJobError("timeframe must not be empty.")
        timeframe = value.strip()
        if timeframe not in self._configured_timeframes():
            raise DashboardJobError(f"timeframe is not configured: {timeframe}.")
        return timeframe

    def _validated_positive_int(self, value: Any, *, param_name: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise DashboardJobError(f"{param_name} must be a positive integer.")
        return value

    def _configured_strategy_names(self) -> set[str]:
        quant = self.config.get("quant") if isinstance(self.config.get("quant"), dict) else {}
        strategies = quant.get("strategies") if isinstance(quant.get("strategies"), list) else []
        return {
            str(strategy.get("name"))
            for strategy in strategies
            if isinstance(strategy, dict) and strategy.get("name") and strategy.get("enabled", True) is not False
        }

    def _configured_symbols(self) -> set[str]:
        market = self.config.get("market") if isinstance(self.config.get("market"), dict) else {}
        values = market.get("symbols") if isinstance(market.get("symbols"), list) else []
        return {str(value) for value in values}

    def _configured_timeframes(self) -> set[str]:
        market = self.config.get("market") if isinstance(self.config.get("market"), dict) else {}
        ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
        values = ohlcv.get("timeframes") if isinstance(ohlcv.get("timeframes"), list) else []
        return {str(value) for value in values}

    def _validated_stage_name(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DashboardJobError("stage_name must not be empty.")
        stage_name = value.strip()
        if stage_name not in STAGE_ORDER:
            supported = ", ".join(STAGE_ORDER)
            raise DashboardJobError(f"stage_name must be one of: {supported}.")
        return stage_name

    def _requires_codex_confirmation(self, spec: CommandSpec, stage_name: str | None) -> bool:
        if spec.codex_confirmation == "always":
            return True
        if spec.codex_confirmation == "stage_is_codex":
            return stage_name == CODEX_STAGE
        if spec.codex_confirmation == "stage_reaches_codex" and stage_name:
            return STAGE_ORDER.index(stage_name) >= STAGE_ORDER.index(CODEX_STAGE)
        return False

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

    def _validated_input_path(self, value: str) -> Path:
        path = self._validated_local_path(value, param_name="input_path")
        if not path.is_file():
            raise DashboardJobError("input_path must reference an existing file.")
        return path

    def _validated_local_path(self, value: str, *, param_name: str) -> Path:
        if not value or not value.strip():
            raise DashboardJobError(f"{param_name} must not be empty.")
        path = Path(value)
        resolved = path if path.is_absolute() else self.base / path
        try:
            resolved.resolve().relative_to(self.base.resolve())
        except ValueError as exc:
            raise DashboardJobError(f"{param_name} must stay within the dashboard config directory.") from exc
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
        values.update({str(self.config_path.resolve()), self.config_path.resolve().as_posix()})
        values.update(_config_private_values(self.config))
        return sorted(values, key=len, reverse=True)


def _read_json(path: Path) -> dict[str, Any]:
    data, error = read_json_object(path)
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


def _config_ref(config_path: Path) -> str:
    path = Path(config_path)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return "<external-config>"


def _safe_ref(path: Path, *, base: Path) -> str:
    return safe_local_ref(path, base=base, external_ref=EXTERNAL_ARTIFACT_REF)


def _utc_now() -> str:
    return utc_now_timestamp()
