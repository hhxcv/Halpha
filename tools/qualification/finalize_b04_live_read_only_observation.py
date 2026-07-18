"""Finalize and stop the bounded B04 live read-only observation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence

import win32com.client


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.configuration import load_settings
from halpha.domain_values import content_digest
from halpha.executor.forward_observation import load_forward_observation_spec
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import current_process_sid, signal_stop_event
from tools.provisioning.provision_windows_tasks import (
    TASK_FOLDER,
    _require_elevated_administrator,
)
from tools.qualification.transition_b04_live_read_only import executor_arguments
from tools.qualification.summarize_b04_evidence import summarize
from tools.qualification.verify_b04_live_read_only import verify


DEFAULT_CONFIG = ROOT / "config/halpha.live-read-only.toml"
DEFAULT_SPEC = ROOT / "build/evidence/reports/b04-live-read-only-spec.json"
DEFAULT_EVENTS = ROOT / "build/evidence/reports/b04-live-read-only-events.jsonl"
DEFAULT_SMTP = ROOT / "build/qualification/b04-smtp-delivery.json"
DEFAULT_LIVE_EVIDENCE = ROOT / "build/qualification/b04-live-read-only.json"
DEFAULT_SUMMARY = ROOT / "build/qualification/b04-summary.json"
DEFAULT_OUTPUT = ROOT / "build/qualification/b04-live-read-only-finalization.json"
FINALIZE_TASK_NAME = "B04LiveReadOnlyFinalize"


class LiveReadOnlyFinalizationError(RuntimeError):
    """A sanitized finalization refusal."""


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _report(output: Path, **values: Any) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "stage": "B04_LIVE_READ_ONLY_FINALIZATION",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime_real_write_gate": "CLOSED",
        "contains_secret": False,
        **values,
    }
    report["evidence_digest"] = content_digest(report)
    _write_json(output, report)
    return report


def non_smtp_checks_complete(evidence: dict[str, Any]) -> bool:
    checks = evidence.get("checks")
    errors = evidence.get("errors")
    if not isinstance(checks, dict) or not checks or errors:
        return False
    return all(
        value is True
        for name, value in checks.items()
        if name != "actual_test_email_qualified"
    )


def _folder() -> Any:
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    return service.GetFolder(TASK_FOLDER)


def _role_processes() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"app": [], "executor": []}
    wmi = win32com.client.GetObject("winmgmts:")
    query = "SELECT CommandLine FROM Win32_Process WHERE Name='python.exe'"
    for process in wmi.ExecQuery(query):
        command = str(process.CommandLine or "")
        if "-m halpha.app" in command:
            result["app"].append(command)
        elif "-m halpha.executor" in command:
            result["executor"].append(command)
    return result


def _wait_for_executor_exit(timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _role_processes()["executor"]:
            return
        time.sleep(1)
    raise LiveReadOnlyFinalizationError("READ_ONLY_EXECUTOR_STOP_TIMEOUT")


def _disable_self(folder: Any) -> None:
    try:
        folder.GetTask(FINALIZE_TASK_NAME).Enabled = False
    except Exception:
        return


def finalize(
    *,
    config_path: Path,
    spec_path: Path,
    events_path: Path,
    smtp_path: Path,
    live_evidence_path: Path,
    summary_path: Path,
    output: Path,
    apply: bool,
) -> dict[str, Any]:
    require_repository_runtime(ROOT)
    _require_elevated_administrator()
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.maintenance_sid:
        raise LiveReadOnlyFinalizationError("MAINTENANCE_SID_MISMATCH")
    if settings.release.profile != "BINANCE_LIVE_READ_ONLY":
        raise LiveReadOnlyFinalizationError("READ_ONLY_PROFILE_REQUIRED")
    if settings.release.authority_class != "NO_TRADING_AUTHORITY":
        raise LiveReadOnlyFinalizationError("NO_TRADING_AUTHORITY_REQUIRED")
    if (
        settings.executor.binance_api_key_reference is not None
        or settings.executor.binance_api_secret_reference is not None
    ):
        raise LiveReadOnlyFinalizationError("READ_ONLY_BINANCE_CREDENTIAL_FORBIDDEN")
    if not spec_path.is_file():
        return _report(output, status="WAITING_FOR_OBSERVATION", applied=False)
    spec = load_forward_observation_spec(spec_path)
    now = datetime.now(UTC)
    if now < spec.minimum_end_at.astimezone(UTC):
        return _report(
            output,
            status="WAITING_FOR_SEVEN_DAY_MINIMUM",
            applied=False,
            observation_id=spec.observation_id,
            minimum_end_at=spec.minimum_end_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        )

    evidence = verify(
        ROOT,
        config_path=config_path,
        spec_path=spec_path,
        events_path=events_path,
        smtp_path=smtp_path,
    )
    _write_json(live_evidence_path, evidence)
    market_complete = non_smtp_checks_complete(evidence)
    at_maximum = now >= spec.maximum_end_at.astimezone(UTC)
    if not market_complete and not at_maximum:
        return _report(
            output,
            status="WAITING_FOR_COMPLETE_MARKET_EVIDENCE",
            applied=False,
            observation_id=spec.observation_id,
            live_evidence_digest=evidence["evidence_digest"],
            incomplete_non_smtp_checks=[
                name
                for name, value in evidence["checks"].items()
                if name != "actual_test_email_qualified" and value is not True
            ],
        )
    if not apply:
        return _report(
            output,
            status=(
                "READY_TO_FINALIZE"
                if market_complete
                else "READY_TO_STOP_AT_MAXIMUM_INCOMPLETE"
            ),
            applied=False,
            observation_id=spec.observation_id,
            live_evidence_digest=evidence["evidence_digest"],
        )

    folder = _folder()
    app_task = folder.GetTask("App")
    executor_task = folder.GetTask("Executor")
    expected_arguments = executor_arguments(config_path, spec_path, events_path)
    action = executor_task.Definition.Actions.Item(1)
    if str(action.Arguments) != expected_arguments:
        raise LiveReadOnlyFinalizationError("READ_ONLY_EXECUTOR_TASK_ACTION_DRIFT")
    processes = _role_processes()
    if bool(app_task.Enabled) or processes["app"]:
        raise LiveReadOnlyFinalizationError("READ_ONLY_APP_MUST_REMAIN_ABSENT")
    if any(expected_arguments not in command for command in processes["executor"]):
        raise LiveReadOnlyFinalizationError("WRONG_PROFILE_EXECUTOR_PRESENT")
    executor_task.Enabled = False
    if processes["executor"]:
        signal_stop_event(
            name=settings.windows.executor_stop_event,
            task_sid=settings.windows.executor_task_sid,
            maintenance_sid=settings.windows.maintenance_sid,
        )
        _wait_for_executor_exit()
    evidence = verify(
        ROOT,
        config_path=config_path,
        spec_path=spec_path,
        events_path=events_path,
        smtp_path=smtp_path,
    )
    _write_json(live_evidence_path, evidence)
    summary = summarize(ROOT)
    _write_json(summary_path, summary)
    _disable_self(folder)
    if market_complete:
        status = (
            "OBSERVATION_QUALIFIED"
            if evidence["status"] == "QUALIFIED"
            else "OBSERVATION_COMPLETE_AWAITING_SMTP"
        )
    else:
        status = "OBSERVATION_STOPPED_INCOMPLETE_AT_MAXIMUM"
    return _report(
        output,
        status=status,
        applied=True,
        observation_id=spec.observation_id,
        live_evidence_status=evidence["status"],
        live_evidence_digest=evidence["evidence_digest"],
        b04_summary_status=summary["status"],
        b04_summary_digest=summary["evidence_digest"],
        market_observation_complete=market_complete,
        actual_smtp_qualified=evidence["checks"]["actual_test_email_qualified"],
        executor_task_enabled=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--smtp-evidence", type=Path, default=DEFAULT_SMTP)
    parser.add_argument("--live-evidence", type=Path, default=DEFAULT_LIVE_EVIDENCE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = finalize(
            config_path=args.config.resolve(),
            spec_path=args.spec.resolve(),
            events_path=args.events.resolve(),
            smtp_path=args.smtp_evidence.resolve(),
            live_evidence_path=args.live_evidence.resolve(),
            summary_path=args.summary.resolve(),
            output=args.output.resolve(),
            apply=args.apply,
        )
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, LiveReadOnlyFinalizationError)
            else f"LIVE_READ_ONLY_FINALIZATION_FAILED type={type(exc).__name__}"
        )
        report = _report(
            args.output.resolve(), status="REJECTED", applied=False, reason=reason
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] != "REJECTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
