from __future__ import annotations

from typing import Any

from halpha.runtime.command_jobs import CommandJobManager


STRATEGY_ACTION_INTENTS = {"backtest", "experiment", "optimize"}


def dashboard_strategy_action_job(
    *,
    job_manager: CommandJobManager | None,
    action: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    if job_manager is None:
        return _strategy_action_payload(
            status="blocked",
            action=action,
            job=None,
            errors=["dashboard command jobs are not configured."],
        )
    if action not in STRATEGY_ACTION_INTENTS:
        supported = ", ".join(sorted(STRATEGY_ACTION_INTENTS))
        return _strategy_action_payload(
            status="unsupported",
            action=action,
            job=None,
            errors=[f"strategy action must be one of: {supported}."],
        )
    params = request.get("params") if isinstance(request.get("params"), dict) else request
    job = job_manager.create_job({"intent": action, "params": params})
    return _strategy_action_payload(
        status=str(job.get("status") or "unknown"),
        action=action,
        job=job,
        warnings=list(job.get("warnings") or []),
        errors=list(job.get("errors") or []),
    )


def _strategy_action_payload(
    *,
    status: str,
    action: str,
    job: dict[str, Any] | None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_strategy_action_job",
        "status": status,
        "action": action,
        "job": job,
        "warnings": warnings or [],
        "errors": errors or [],
    }
