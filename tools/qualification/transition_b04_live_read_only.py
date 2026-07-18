"""Transition the qualified Demo soak into the B04 live read-only observation.

The transition is deliberately one-way and fail-closed.  It never changes the
LIVE real-write gate, never loads Binance credentials, and never starts App for
the read-only qualification composition.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import socket
import sys
import time
from typing import Any, Iterator, Sequence

import win32com.client


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.configuration import load_settings, settings_digest
from halpha.domain_values import content_digest
from halpha.executor.forward_observation import (
    ForwardObservationError,
    ForwardObservationSpec,
    load_forward_observation_spec,
)
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import current_process_sid, signal_stop_event
from tools.provisioning.provision_windows_tasks import (
    EXECUTOR_USER,
    TASK_CREATE_OR_UPDATE,
    TASK_FOLDER,
    TASK_LOGON_PASSWORD,
    _require_elevated_administrator,
    _task_account_password,
)
from tools.qualification.observe_b04_windows_soak import observe as observe_windows_soak
from tools.qualification.prepare_b04_live_read_only_observation import (
    ForwardObservationPreparationError,
    prepare,
)


DEFAULT_DEMO_CONFIG = ROOT / "config/halpha.toml"
DEFAULT_READ_ONLY_CONFIG = ROOT / "config/halpha.live-read-only.toml"
DEFAULT_SOAK = ROOT / "build/qualification/b04-windows-72h-soak.json"
DEFAULT_PREREGISTRATION = (
    ROOT / "build/evidence/reports/b04-historical-preregistration.json"
)
DEFAULT_SPEC = ROOT / "build/evidence/reports/b04-live-read-only-spec.json"
DEFAULT_EVENTS = ROOT / "build/evidence/reports/b04-live-read-only-events.jsonl"
DEFAULT_OUTPUT = ROOT / "build/qualification/b04-live-read-only-transition.json"
TRANSITION_TASK_NAME = "B04LiveReadOnlyTransition"
SOAK_CHECKPOINT_TASK_NAME = "B04WindowsSoakCheckpoint"
TASK_STATE_RUNNING = 4


class LiveReadOnlyTransitionError(RuntimeError):
    """A sanitized, fail-closed transition refusal."""


def _prepare_spec(
    *,
    config_path: Path,
    preregistration_path: Path,
    starts_at: datetime,
) -> ForwardObservationSpec:
    try:
        return prepare(
            config_path=config_path,
            preregistration_path=preregistration_path,
            starts_at=starts_at,
        )
    except (ForwardObservationError, ForwardObservationPreparationError) as exc:
        raise LiveReadOnlyTransitionError(str(exc)) from None


def executor_arguments(
    config_path: Path,
    spec_path: Path,
    events_path: Path,
) -> str:
    """Return the only qualified Executor command for this observation."""

    return (
        f'-m halpha.executor --config "{config_path.resolve()}" '
        f'--forward-observation-spec "{spec_path.resolve()}" '
        f'--forward-observation-evidence "{events_path.resolve()}"'
    )


def valid_events(path: Path, *, start_offset: int = 0) -> Iterator[dict[str, Any]]:
    """Yield complete digest-valid event lines without materializing the log."""

    if not path.is_file():
        return
    with path.open("rb") as stream:
        stream.seek(start_offset)
        for raw_line in stream:
            if not raw_line.endswith(b"\n"):
                return
            try:
                event = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(event, dict):
                continue
            expected = event.get("event_digest")
            payload = {
                key: item for key, item in event.items() if key != "event_digest"
            }
            if expected != content_digest(payload):
                continue
            yield event


def is_trimmed_read_only_ready_event(
    event: dict[str, Any],
    *,
    observation_id: str,
    configuration_digest: str,
    source_sha256_digest: str,
) -> bool:
    """Require the complete credential-free, non-persistent ready composition."""

    return (
        event.get("event") == "READ_ONLY_RUNTIME_READY"
        and event.get("observation_id") == observation_id
        and event.get("configuration_digest") == configuration_digest
        and event.get("source_sha256_digest") == source_sha256_digest
        and event.get("profile") == "BINANCE_LIVE_READ_ONLY"
        and event.get("product_runtime_started") is True
        and event.get("strategy_adapter_started") is True
        and event.get("data_client_loaded") is True
        and event.get("binance_credentials_loaded") is False
        and event.get("instrument_commission_query_enabled") is False
        and event.get("execution_client_loaded") is False
        and event.get("database_connection_loaded") is False
        and event.get("execution_action_repository_loaded") is False
        and event.get("persisted_action_capability_loaded") is False
        and event.get("startup_execution_reconciliation") == "NOT_APPLICABLE"
        and event.get("runtime_real_write_gate") == "CLOSED"
    )


def latest_ready_event(
    path: Path,
    *,
    not_before: datetime,
    observation_id: str,
    configuration_digest: str,
    source_sha256_digest: str,
) -> dict[str, object] | None:
    """Find the latest capability-trimmed, digest-valid ready event."""

    latest: dict[str, object] | None = None
    for event in valid_events(path):
        try:
            observed_at = datetime.fromisoformat(
                str(event["observed_at"]).replace("Z", "+00:00")
            ).astimezone(UTC)
        except (KeyError, TypeError, ValueError):
            continue
        if observed_at < not_before.astimezone(UTC):
            continue
        if is_trimmed_read_only_ready_event(
            event,
            observation_id=observation_id,
            configuration_digest=configuration_digest,
            source_sha256_digest=source_sha256_digest,
        ):
            latest = event
    return latest


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
        "stage": "B04_LIVE_READ_ONLY_TRANSITION",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime_real_write_gate": "CLOSED",
        "contains_secret": False,
        **values,
    }
    report["evidence_digest"] = content_digest(report)
    _write_json(output, report)
    return report


def _task_service() -> tuple[Any, Any]:
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    return service, service.GetFolder(TASK_FOLDER)


def _role_processes() -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {"app": [], "executor": []}
    wmi = win32com.client.GetObject("winmgmts:")
    query = "SELECT ProcessId,CommandLine FROM Win32_Process WHERE Name='python.exe'"
    for process in wmi.ExecQuery(query):
        command = str(process.CommandLine or "")
        if "-m halpha.app" in command:
            role = "app"
        elif "-m halpha.executor" in command:
            role = "executor"
        else:
            continue
        result[role].append({"pid": int(process.ProcessId), "command": command})
    return result


def _wait_for_role_exit(role: str, *, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _role_processes()[role]:
            return
        time.sleep(1)
    raise LiveReadOnlyTransitionError(f"{role.upper()}_PROCESS_STOP_TIMEOUT")


def _signal_role(settings: Any, role: str) -> None:
    if role == "app":
        name = settings.windows.app_stop_event
        task_sid = settings.windows.app_task_sid
    else:
        name = settings.windows.executor_stop_event
        task_sid = settings.windows.executor_task_sid
    signal_stop_event(
        name=name,
        task_sid=task_sid,
        maintenance_sid=settings.windows.maintenance_sid,
    )


def _freeze_spec(
    *,
    config_path: Path,
    preregistration_path: Path,
    spec_path: Path,
) -> ForwardObservationSpec:
    spec = _prepare_spec(
        config_path=config_path,
        preregistration_path=preregistration_path,
        starts_at=datetime.now(UTC),
    )
    if spec_path.exists():
        raise LiveReadOnlyTransitionError("OBSERVATION_SPEC_ALREADY_EXISTS")
    _write_json(spec_path, spec.model_dump(mode="json"))
    return spec


def _executor_task_matches(task: Any, *, python_path: Path, arguments: str) -> bool:
    definition = task.Definition
    if int(definition.Actions.Count) != 1:
        return False
    action = definition.Actions.Item(1)
    return (
        Path(str(action.Path)).resolve() == python_path.resolve()
        and str(action.Arguments) == arguments
        and Path(str(action.WorkingDirectory)).resolve() == ROOT.resolve()
    )


def _configure_executor_task(
    service: Any,
    folder: Any,
    *,
    config_path: Path,
    spec_path: Path,
    events_path: Path,
) -> Any:
    task = folder.GetTask("Executor")
    definition = task.Definition
    if int(definition.Actions.Count) != 1:
        raise LiveReadOnlyTransitionError("EXECUTOR_TASK_ACTION_COUNT_INVALID")
    expected_account = f"{socket.gethostname()}\\{EXECUTOR_USER}".lower()
    if str(definition.Principal.UserId).lower() != expected_account:
        raise LiveReadOnlyTransitionError("EXECUTOR_TASK_IDENTITY_DRIFT")
    action = definition.Actions.Item(1)
    action.Path = str((ROOT / ".venv/Scripts/python.exe").resolve())
    action.Arguments = executor_arguments(config_path, spec_path, events_path)
    action.WorkingDirectory = str(ROOT.resolve())
    definition.Settings.Enabled = True
    password = _task_account_password(EXECUTOR_USER)
    try:
        return folder.RegisterTaskDefinition(
            "Executor",
            definition,
            TASK_CREATE_OR_UPDATE,
            f"{socket.gethostname()}\\{EXECUTOR_USER}",
            password,
            TASK_LOGON_PASSWORD,
            "",
        )
    finally:
        password = ""


def _disable_transition_task(folder: Any) -> None:
    try:
        folder.GetTask(TRANSITION_TASK_NAME).Enabled = False
    except Exception:
        # The transition can also be run interactively without a scheduler task.
        return


def transition(
    *,
    demo_config: Path,
    read_only_config: Path,
    soak_path: Path,
    preregistration_path: Path,
    spec_path: Path,
    events_path: Path,
    output: Path,
    apply: bool,
) -> dict[str, Any]:
    require_repository_runtime(ROOT)
    _require_elevated_administrator()
    demo = load_settings(demo_config)
    read_only = load_settings(read_only_config)
    if current_process_sid() != demo.windows.maintenance_sid:
        raise LiveReadOnlyTransitionError("MAINTENANCE_SID_MISMATCH")
    if demo.release.profile != "BINANCE_DEMO":
        raise LiveReadOnlyTransitionError("DEMO_SOURCE_PROFILE_REQUIRED")
    if read_only.release.profile != "BINANCE_LIVE_READ_ONLY":
        raise LiveReadOnlyTransitionError("READ_ONLY_TARGET_PROFILE_REQUIRED")
    if read_only.release.authority_class != "NO_TRADING_AUTHORITY":
        raise LiveReadOnlyTransitionError("NO_TRADING_AUTHORITY_REQUIRED")
    if (
        read_only.executor.binance_api_key_reference is not None
        or read_only.executor.binance_api_secret_reference is not None
    ):
        raise LiveReadOnlyTransitionError("READ_ONLY_BINANCE_CREDENTIAL_FORBIDDEN")
    if read_only.windows != demo.windows:
        raise LiveReadOnlyTransitionError("WINDOWS_IDENTITY_CONFIGURATION_DRIFT")
    evidence_root = (ROOT / "build/evidence/reports").resolve()
    if not spec_path.resolve().is_relative_to(evidence_root):
        raise LiveReadOnlyTransitionError("OBSERVATION_SPEC_OUTSIDE_EVIDENCE_ROOT")
    if not events_path.resolve().is_relative_to(evidence_root):
        raise LiveReadOnlyTransitionError("OBSERVATION_EVENTS_OUTSIDE_EVIDENCE_ROOT")
    if events_path.suffix.lower() != ".jsonl":
        raise LiveReadOnlyTransitionError("OBSERVATION_EVENTS_FORMAT_INVALID")

    try:
        spec = (
            load_forward_observation_spec(spec_path)
            if spec_path.is_file()
            else None
        )
    except ForwardObservationError as exc:
        raise LiveReadOnlyTransitionError(str(exc)) from None
    if spec is not None:
        expected_spec = _prepare_spec(
            config_path=read_only_config,
            preregistration_path=preregistration_path,
            starts_at=spec.starts_at,
        )
        if spec != expected_spec:
            raise LiveReadOnlyTransitionError("OBSERVATION_SPEC_INPUT_DRIFT")
    if not soak_path.is_file():
        return _report(output, status="WAITING_FOR_WINDOWS_72H", applied=False)
    soak = json.loads(soak_path.read_text(encoding="utf-8"))
    if apply and spec is None and soak.get("status") == "IN_PROGRESS":
        soak = observe_windows_soak(ROOT, demo_config, soak_path)
    if soak.get("status") != "QUALIFIED":
        return _report(
            output,
            status=(
                "REJECTED_WINDOWS_SOAK"
                if soak.get("status") == "REJECTED"
                else "WAITING_FOR_WINDOWS_72H"
            ),
            applied=False,
            windows_soak_status=soak.get("status", "UNKNOWN"),
            windows_soak_digest=soak.get("evidence_digest"),
        )
    if spec is None:
        if not apply:
            return _report(
                output,
                status="READY_TO_TRANSITION",
                applied=False,
                windows_soak_digest=soak.get("evidence_digest"),
            )

    service, folder = _task_service()
    try:
        folder.GetTask(SOAK_CHECKPOINT_TASK_NAME).Enabled = False
    except Exception:
        pass
    app_task = folder.GetTask("App")
    executor_task = folder.GetTask("Executor")
    expected_arguments = executor_arguments(read_only_config, spec_path, events_path)
    python_path = ROOT / ".venv/Scripts/python.exe"

    if spec is None:
        app_task.Enabled = False
        executor_task.Enabled = False
        processes = _role_processes()
        for role in ("app", "executor"):
            if processes[role]:
                _signal_role(demo, role)
        for role in ("app", "executor"):
            _wait_for_role_exit(role)
        spec = _freeze_spec(
            config_path=read_only_config,
            preregistration_path=preregistration_path,
            spec_path=spec_path,
        )
    elif not apply:
        ready = latest_ready_event(
            events_path,
            not_before=spec.starts_at,
            observation_id=spec.observation_id,
            configuration_digest=spec.configuration_digest,
            source_sha256_digest=spec.source_sha256_digest,
        )
        return _report(
            output,
            status=("OBSERVATION_STARTED" if ready is not None else "SPEC_FROZEN"),
            applied=False,
            observation_id=spec.observation_id,
            starts_at=spec.starts_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        )

    # A partial prior transition must never leave App or the Demo Executor alive.
    app_task.Enabled = False
    processes = _role_processes()
    if processes["app"]:
        _signal_role(demo, "app")
        _wait_for_role_exit("app")
    wrong_executor = any(expected_arguments not in str(item["command"]) for item in processes["executor"])
    if wrong_executor:
        executor_task.Enabled = False
        _signal_role(demo, "executor")
        _wait_for_role_exit("executor")

    executor_task = folder.GetTask("Executor")
    if not _executor_task_matches(
        executor_task,
        python_path=python_path,
        arguments=expected_arguments,
    ):
        executor_task = _configure_executor_task(
            service,
            folder,
            config_path=read_only_config,
            spec_path=spec_path,
            events_path=events_path,
        )
    else:
        executor_task.Enabled = True

    processes = _role_processes()
    correct_executor = any(
        expected_arguments in str(item["command"]) for item in processes["executor"]
    )
    if not correct_executor:
        executor_task.Run("")

    deadline = time.monotonic() + 120
    ready: dict[str, object] | None = None
    while time.monotonic() < deadline:
        ready = latest_ready_event(
            events_path,
            not_before=spec.starts_at,
            observation_id=spec.observation_id,
            configuration_digest=spec.configuration_digest,
            source_sha256_digest=spec.source_sha256_digest,
        )
        if ready is not None:
            break
        time.sleep(1)
    status = "OBSERVATION_STARTED" if ready is not None else "OBSERVATION_STARTING"
    if ready is not None:
        _disable_transition_task(folder)
    return _report(
        output,
        status=status,
        applied=True,
        observation_id=spec.observation_id,
        starts_at=spec.starts_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        minimum_end_at=spec.minimum_end_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        maximum_end_at=spec.maximum_end_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        read_only_configuration_digest=settings_digest(read_only),
        observation_spec_digest=content_digest(spec.model_dump(mode="json")),
        source_sha256_digest=spec.source_sha256_digest,
        executor_action_sha256=sha256(expected_arguments.encode("utf-8")).hexdigest(),
        app_task_enabled=False,
        executor_task_enabled=True,
        read_only_runtime_ready=ready is not None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-config", type=Path, default=DEFAULT_DEMO_CONFIG)
    parser.add_argument("--read-only-config", type=Path, default=DEFAULT_READ_ONLY_CONFIG)
    parser.add_argument("--soak", type=Path, default=DEFAULT_SOAK)
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PREREGISTRATION)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = transition(
            demo_config=args.demo_config.resolve(),
            read_only_config=args.read_only_config.resolve(),
            soak_path=args.soak.resolve(),
            preregistration_path=args.preregistration.resolve(),
            spec_path=args.spec.resolve(),
            events_path=args.events.resolve(),
            output=args.output.resolve(),
            apply=args.apply,
        )
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, LiveReadOnlyTransitionError)
            else f"LIVE_READ_ONLY_TRANSITION_FAILED type={type(exc).__name__}"
        )
        report = _report(
            args.output.resolve(),
            status="REJECTED",
            applied=False,
            reason=reason,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"] != "REJECTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
