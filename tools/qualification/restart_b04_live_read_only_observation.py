"""Create one qualified >90-second gap in the B04 read-only observation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
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
from halpha.executor.forward_observation import (
    ForwardObservationError,
    load_forward_observation_spec,
    require_forward_observation_source_identity,
)
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import current_process_sid, signal_stop_event
from tools.provisioning.provision_windows_tasks import (
    TASK_FOLDER,
    _require_elevated_administrator,
)
from tools.qualification.transition_b04_live_read_only import (
    executor_arguments,
    is_trimmed_read_only_ready_event,
    latest_ready_event,
    valid_events,
)


DEFAULT_CONFIG = ROOT / "config/halpha.live-read-only.toml"
DEFAULT_SPEC = ROOT / "build/evidence/reports/b04-live-read-only-spec.json"
DEFAULT_EVENTS = ROOT / "build/evidence/reports/b04-live-read-only-events.jsonl"
DEFAULT_OUTPUT = ROOT / "build/qualification/b04-live-read-only-restart.json"
RESTART_TASK_NAME = "B04LiveReadOnlyRestart"
MINIMUM_GAP_SECONDS = 100


class LiveReadOnlyRestartError(RuntimeError):
    """A sanitized controlled-restart refusal."""


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
        "stage": "B04_LIVE_READ_ONLY_CONTROLLED_RESTART",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime_real_write_gate": "CLOSED",
        "contains_secret": False,
        **values,
    }
    report["evidence_digest"] = content_digest(report)
    _write_json(output, report)
    return report


def process_start_count(
    path: Path,
    *,
    observation_id: str,
    configuration_digest: str,
    source_sha256_digest: str,
    start_offset: int = 0,
) -> int:
    return sum(
        item.get("event") == "OBSERVATION_PROCESS_STARTED"
        and item.get("observation_id") == observation_id
        and item.get("configuration_digest") == configuration_digest
        and item.get("source_sha256_digest") == source_sha256_digest
        for item in valid_events(path, start_offset=start_offset)
    )


def _observed_at(event: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(
            str(event["observed_at"]).replace("Z", "+00:00")
        ).astimezone(UTC)
    except (KeyError, TypeError, ValueError):
        return None


def restart_completed(
    events_path: Path,
    *,
    prior_start_count: int,
    gap_started_at: datetime,
    observation_id: str,
    configuration_digest: str,
    source_sha256_digest: str,
    prior_event_offset: int = 0,
) -> bool:
    new_start_count = 0
    ready = False
    for item in valid_events(events_path, start_offset=prior_event_offset):
        if (
            item.get("event") == "OBSERVATION_PROCESS_STARTED"
            and item.get("observation_id") == observation_id
            and item.get("configuration_digest") == configuration_digest
            and item.get("source_sha256_digest") == source_sha256_digest
        ):
            new_start_count += 1
        observed_at = _observed_at(item)
        if (
            is_trimmed_read_only_ready_event(
                item,
                observation_id=observation_id,
                configuration_digest=configuration_digest,
                source_sha256_digest=source_sha256_digest,
            )
            and observed_at is not None
            and observed_at >= gap_started_at
        ):
            ready = True
    return prior_start_count >= 1 and new_start_count > 0 and ready


def _service_folder() -> Any:
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
    raise LiveReadOnlyRestartError("READ_ONLY_EXECUTOR_STOP_TIMEOUT")


def _disable_self(folder: Any) -> None:
    try:
        folder.GetTask(RESTART_TASK_NAME).Enabled = False
    except Exception:
        return


def restart(
    *,
    config_path: Path,
    spec_path: Path,
    events_path: Path,
    output: Path,
    gap_seconds: int,
    apply: bool,
) -> dict[str, Any]:
    require_repository_runtime(ROOT)
    _require_elevated_administrator()
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.maintenance_sid:
        raise LiveReadOnlyRestartError("MAINTENANCE_SID_MISMATCH")
    if settings.release.profile != "BINANCE_LIVE_READ_ONLY":
        raise LiveReadOnlyRestartError("READ_ONLY_PROFILE_REQUIRED")
    if settings.release.authority_class != "NO_TRADING_AUTHORITY":
        raise LiveReadOnlyRestartError("NO_TRADING_AUTHORITY_REQUIRED")
    if (
        settings.executor.binance_api_key_reference is not None
        or settings.executor.binance_api_secret_reference is not None
    ):
        raise LiveReadOnlyRestartError("READ_ONLY_BINANCE_CREDENTIAL_FORBIDDEN")
    if gap_seconds < MINIMUM_GAP_SECONDS or gap_seconds > 300:
        raise LiveReadOnlyRestartError("CONTROLLED_GAP_DURATION_INVALID")
    if not spec_path.is_file():
        return _report(output, status="WAITING_FOR_OBSERVATION", applied=False)
    try:
        spec = load_forward_observation_spec(spec_path)
        require_forward_observation_source_identity(ROOT, spec)
    except ForwardObservationError as exc:
        raise LiveReadOnlyRestartError(str(exc)) from None
    now = datetime.now(UTC)
    if now < spec.starts_at.astimezone(UTC) + timedelta(days=1):
        return _report(
            output,
            status="WAITING_FOR_MIDPOINT",
            applied=False,
            observation_id=spec.observation_id,
        )

    prior_report: dict[str, Any] = {}
    if output.is_file():
        try:
            prior_report = json.loads(output.read_text(encoding="utf-8"))
        except Exception:
            prior_report = {}
    if prior_report.get("status") == "RESTART_QUALIFIED":
        return prior_report

    folder = _service_folder()
    app_task = folder.GetTask("App")
    executor_task = folder.GetTask("Executor")
    expected_arguments = executor_arguments(config_path, spec_path, events_path)
    action = executor_task.Definition.Actions.Item(1)
    if str(action.Arguments) != expected_arguments:
        raise LiveReadOnlyRestartError("READ_ONLY_EXECUTOR_TASK_ACTION_DRIFT")
    processes = _role_processes()
    if bool(app_task.Enabled) or processes["app"]:
        raise LiveReadOnlyRestartError("READ_ONLY_APP_MUST_REMAIN_ABSENT")
    if any(expected_arguments not in command for command in processes["executor"]):
        raise LiveReadOnlyRestartError("WRONG_PROFILE_EXECUTOR_PRESENT")

    resume_status = prior_report.get("status")
    restart_already_started = resume_status == "RESTART_STARTING"
    if resume_status in {"GAP_IN_PROGRESS", "RESTART_STARTING"}:
        prior_start_count = int(prior_report["prior_start_count"])
        prior_event_offset = int(prior_report["prior_event_offset"])
        gap_started_at = datetime.fromisoformat(
            str(prior_report["gap_started_at"]).replace("Z", "+00:00")
        ).astimezone(UTC)
        if restart_completed(
            events_path,
            prior_start_count=prior_start_count,
            gap_started_at=gap_started_at,
            prior_event_offset=prior_event_offset,
            observation_id=spec.observation_id,
            configuration_digest=spec.configuration_digest,
            source_sha256_digest=spec.source_sha256_digest,
        ):
            _disable_self(folder)
            return _report(
                output,
                status="RESTART_QUALIFIED",
                applied=True,
                observation_id=spec.observation_id,
                prior_start_count=prior_start_count,
                prior_event_offset=prior_event_offset,
                current_start_count=(
                    prior_start_count
                    + process_start_count(
                        events_path,
                        start_offset=prior_event_offset,
                        observation_id=spec.observation_id,
                        configuration_digest=spec.configuration_digest,
                        source_sha256_digest=spec.source_sha256_digest,
                    )
                ),
                gap_started_at=gap_started_at.isoformat().replace("+00:00", "Z"),
                gap_seconds=gap_seconds,
                read_only_runtime_ready_after_gap=True,
            )
    else:
        if (
            latest_ready_event(
                events_path,
                not_before=spec.starts_at,
                observation_id=spec.observation_id,
                configuration_digest=spec.configuration_digest,
                source_sha256_digest=spec.source_sha256_digest,
            )
            is None
        ):
            return _report(
                output,
                status="WAITING_FOR_READ_ONLY_RUNTIME_READY",
                applied=False,
                observation_id=spec.observation_id,
            )
        prior_start_count = process_start_count(
            events_path,
            observation_id=spec.observation_id,
            configuration_digest=spec.configuration_digest,
            source_sha256_digest=spec.source_sha256_digest,
        )
        prior_event_offset = events_path.stat().st_size
        if prior_start_count < 1:
            raise LiveReadOnlyRestartError("OBSERVATION_START_EVENT_MISSING")
        if not apply:
            return _report(
                output,
                status="READY_FOR_CONTROLLED_RESTART",
                applied=False,
                observation_id=spec.observation_id,
                prior_start_count=prior_start_count,
                prior_event_offset=prior_event_offset,
                gap_seconds=gap_seconds,
            )
        executor_task.Enabled = False
        if processes["executor"]:
            signal_stop_event(
                name=settings.windows.executor_stop_event,
                task_sid=settings.windows.executor_task_sid,
                maintenance_sid=settings.windows.maintenance_sid,
            )
        _wait_for_executor_exit()
        gap_started_at = datetime.now(UTC)
        _report(
            output,
            status="GAP_IN_PROGRESS",
            applied=True,
            observation_id=spec.observation_id,
            prior_start_count=prior_start_count,
            prior_event_offset=prior_event_offset,
            gap_started_at=gap_started_at.isoformat().replace("+00:00", "Z"),
            gap_seconds=gap_seconds,
        )

    if not apply:
        return _report(
            output,
            status="GAP_IN_PROGRESS",
            applied=False,
            observation_id=spec.observation_id,
            prior_start_count=prior_start_count,
            prior_event_offset=prior_event_offset,
            gap_started_at=gap_started_at.isoformat().replace("+00:00", "Z"),
            gap_seconds=gap_seconds,
        )
    remaining = gap_seconds - (datetime.now(UTC) - gap_started_at).total_seconds()
    if not restart_already_started and remaining > 0:
        time.sleep(remaining)
    executor_task = folder.GetTask("Executor")
    executor_task.Enabled = True
    if not _role_processes()["executor"]:
        executor_task.Run("")

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if restart_completed(
            events_path,
            prior_start_count=prior_start_count,
            gap_started_at=gap_started_at,
            prior_event_offset=prior_event_offset,
            observation_id=spec.observation_id,
            configuration_digest=spec.configuration_digest,
            source_sha256_digest=spec.source_sha256_digest,
        ):
            _disable_self(folder)
            return _report(
                output,
                status="RESTART_QUALIFIED",
                applied=True,
                observation_id=spec.observation_id,
                prior_start_count=prior_start_count,
                prior_event_offset=prior_event_offset,
                current_start_count=(
                    prior_start_count
                    + process_start_count(
                        events_path,
                        start_offset=prior_event_offset,
                        observation_id=spec.observation_id,
                        configuration_digest=spec.configuration_digest,
                        source_sha256_digest=spec.source_sha256_digest,
                    )
                ),
                gap_started_at=gap_started_at.isoformat().replace("+00:00", "Z"),
                gap_seconds=gap_seconds,
                read_only_runtime_ready_after_gap=True,
            )
        time.sleep(1)
    return _report(
        output,
        status="RESTART_STARTING",
        applied=True,
        observation_id=spec.observation_id,
        prior_start_count=prior_start_count,
        prior_event_offset=prior_event_offset,
        current_start_count=(
            prior_start_count
            + process_start_count(
                events_path,
                start_offset=prior_event_offset,
                observation_id=spec.observation_id,
                configuration_digest=spec.configuration_digest,
                source_sha256_digest=spec.source_sha256_digest,
            )
        ),
        gap_started_at=gap_started_at.isoformat().replace("+00:00", "Z"),
        gap_seconds=gap_seconds,
        read_only_runtime_ready_after_gap=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gap-seconds", type=int, default=MINIMUM_GAP_SECONDS)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = restart(
            config_path=args.config.resolve(),
            spec_path=args.spec.resolve(),
            events_path=args.events.resolve(),
            output=args.output.resolve(),
            gap_seconds=args.gap_seconds,
            apply=args.apply,
        )
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, LiveReadOnlyRestartError)
            else f"LIVE_READ_ONLY_RESTART_FAILED type={type(exc).__name__}"
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
