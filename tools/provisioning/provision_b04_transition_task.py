"""Provision the temporary owner-token task for the B04 profile transition."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import win32com.client


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from halpha.configuration import load_settings
from halpha.domain_values import content_digest
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import current_process_sid
from tools.provisioning.provision_windows_tasks import (
    TASK_CREATE_OR_UPDATE,
    TASK_FOLDER,
    TASK_INSTANCES_IGNORE_NEW,
    _require_elevated_administrator,
)
from tools.qualification.finalize_b04_live_read_only_observation import FINALIZE_TASK_NAME
from tools.qualification.restart_b04_live_read_only_observation import RESTART_TASK_NAME
from tools.qualification.transition_b04_live_read_only import TRANSITION_TASK_NAME
from tools.qualification.transition_b04_live_read_only import SOAK_CHECKPOINT_TASK_NAME


TASK_LOGON_INTERACTIVE_TOKEN = 3
TASK_RUNLEVEL_HIGHEST = 1
TASK_TRIGGER_TIME = 1
TASK_ACTION_EXEC = 0
REPETITION_INTERVAL = "PT5M"
REPETITION_DURATION = "P1D"
RESTART_REPETITION_INTERVAL = "PT30M"
FINALIZE_REPETITION_INTERVAL = "PT30M"
FINALIZE_REPETITION_DURATION = "P8D"
SOAK_CHECKPOINT_REPETITION_INTERVAL = "PT1H"
SOAK_CHECKPOINT_REPETITION_DURATION = "P3D"
DEFAULT_CONFIG = ROOT / "config/halpha.toml"
DEFAULT_OUTPUT = ROOT / "build/qualification/b04-live-read-only-transition-task.json"
DEFAULT_XML = ROOT / "build/runtime/tasks/b04-live-read-only-transition.xml"
DEFAULT_RESTART_XML = ROOT / "build/runtime/tasks/b04-live-read-only-restart.xml"
DEFAULT_FINALIZE_XML = ROOT / "build/runtime/tasks/b04-live-read-only-finalize.xml"
DEFAULT_SOAK_CHECKPOINT_XML = ROOT / "build/runtime/tasks/b04-windows-soak-checkpoint.xml"


class TransitionTaskProvisioningError(RuntimeError):
    """A sanitized temporary-task provisioning refusal."""


def transition_action_arguments() -> str:
    return "tools/qualification/transition_b04_live_read_only.py --apply"


def restart_action_arguments() -> str:
    return "tools/qualification/restart_b04_live_read_only_observation.py --apply"


def finalize_action_arguments() -> str:
    return "tools/qualification/finalize_b04_live_read_only_observation.py --apply"


def soak_checkpoint_action_arguments() -> str:
    return "tools/qualification/observe_b04_windows_soak.py --config config/halpha.toml"


def parse_local_start(value: str, *, now: datetime | None = None) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise TransitionTaskProvisioningError("TRANSITION_START_TIME_INVALID") from None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    current = now or datetime.now()
    if parsed <= current:
        raise TransitionTaskProvisioningError("TRANSITION_START_TIME_MUST_BE_FUTURE")
    return parsed


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _register_temporary_task(
    *,
    service: Any,
    folder: Any,
    python: Path,
    account: str,
    task_name: str,
    description: str,
    display_name: str,
    trigger_id: str,
    start_at: datetime,
    repetition_interval: str,
    repetition_duration: str,
    arguments: str,
    xml_output: Path,
) -> dict[str, Any]:
    definition = service.NewTask(0)
    definition.RegistrationInfo.Author = "Halpha Project Owner"
    definition.RegistrationInfo.Description = description
    definition.Settings.AllowDemandStart = True
    definition.Settings.DisallowStartIfOnBatteries = False
    definition.Settings.Enabled = True
    definition.Settings.ExecutionTimeLimit = "PT10M"
    definition.Settings.Hidden = True
    definition.Settings.MultipleInstances = TASK_INSTANCES_IGNORE_NEW
    definition.Settings.StartWhenAvailable = True
    definition.Settings.StopIfGoingOnBatteries = False
    definition.Principal.DisplayName = display_name
    definition.Principal.UserId = account
    definition.Principal.LogonType = TASK_LOGON_INTERACTIVE_TOKEN
    definition.Principal.RunLevel = TASK_RUNLEVEL_HIGHEST

    trigger = definition.Triggers.Create(TASK_TRIGGER_TIME)
    trigger.Enabled = True
    trigger.Id = trigger_id
    trigger.StartBoundary = start_at.strftime("%Y-%m-%dT%H:%M:%S")
    trigger.Repetition.Interval = repetition_interval
    trigger.Repetition.Duration = repetition_duration
    trigger.Repetition.StopAtDurationEnd = True

    action = definition.Actions.Create(TASK_ACTION_EXEC)
    action.Path = str(python)
    action.Arguments = arguments
    action.WorkingDirectory = str(ROOT.resolve())
    task = folder.RegisterTaskDefinition(
        task_name,
        definition,
        TASK_CREATE_OR_UPDATE,
        account,
        None,
        TASK_LOGON_INTERACTIVE_TOKEN,
        "",
    )
    xml = str(task.Xml)
    if "<Password>" in xml or "HALPHA_RUNTIME_PROXY_URL" in xml:
        raise TransitionTaskProvisioningError("TEMPORARY_TASK_XML_SECRET_DETECTED")
    xml_output.parent.mkdir(parents=True, exist_ok=True)
    xml_output.write_text(xml, encoding="utf-8", newline="\n")
    return {
        "task_path": f"{TASK_FOLDER}\\{task_name}",
        "start_at_local": start_at.isoformat(),
        "repetition_interval": repetition_interval,
        "repetition_duration": repetition_duration,
        "action_sha256": sha256(arguments.encode("utf-8")).hexdigest(),
        "xml_sha256": sha256(xml.encode("utf-8")).hexdigest(),
    }


def provision(
    *,
    config_path: Path,
    start_at: datetime,
    restart_at: datetime | None,
    finalize_at: datetime | None,
    soak_checkpoint_at: datetime | None,
    output: Path,
    xml_output: Path,
    restart_xml_output: Path,
    finalize_xml_output: Path,
    soak_checkpoint_xml_output: Path,
) -> dict[str, Any]:
    require_repository_runtime(ROOT)
    _require_elevated_administrator()
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.maintenance_sid:
        raise TransitionTaskProvisioningError("MAINTENANCE_SID_MISMATCH")
    python = (ROOT / ".venv/Scripts/python.exe").resolve()
    if not python.is_file():
        raise TransitionTaskProvisioningError("REPOSITORY_VENV_PYTHON_MISSING")

    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    folder = service.GetFolder(TASK_FOLDER)
    identity = __import__("getpass").getuser()
    domain = __import__("os").environ.get("USERDOMAIN")
    account = f"{domain}\\{identity}" if domain else identity
    tasks = {
        "transition": _register_temporary_task(
            service=service,
            folder=folder,
            python=python,
            account=account,
            task_name=TRANSITION_TASK_NAME,
            description="Temporary B04 Demo-soak to credential-free LIVE_READ_ONLY transition",
            display_name="Halpha B04 maintenance transition",
            trigger_id="B04TransitionWindow",
            start_at=start_at,
            repetition_interval=REPETITION_INTERVAL,
            repetition_duration=REPETITION_DURATION,
            arguments=transition_action_arguments(),
            xml_output=xml_output,
        )
    }
    if restart_at is not None:
        if restart_at <= start_at + timedelta(days=1):
            raise TransitionTaskProvisioningError("RESTART_MUST_FOLLOW_TRANSITION_BY_ONE_DAY")
        tasks["controlled_restart"] = _register_temporary_task(
            service=service,
            folder=folder,
            python=python,
            account=account,
            task_name=RESTART_TASK_NAME,
            description="Temporary B04 credential-free LIVE_READ_ONLY controlled data-gap restart",
            display_name="Halpha B04 read-only controlled restart",
            trigger_id="B04ControlledRestartWindow",
            start_at=restart_at,
            repetition_interval=RESTART_REPETITION_INTERVAL,
            repetition_duration=REPETITION_DURATION,
            arguments=restart_action_arguments(),
            xml_output=restart_xml_output,
        )
    if finalize_at is not None:
        if finalize_at <= start_at + timedelta(days=7):
            raise TransitionTaskProvisioningError("FINALIZE_MUST_FOLLOW_SEVEN_DAY_MINIMUM")
        tasks["finalization"] = _register_temporary_task(
            service=service,
            folder=folder,
            python=python,
            account=account,
            task_name=FINALIZE_TASK_NAME,
            description="Temporary B04 credential-free LIVE_READ_ONLY bounded finalization",
            display_name="Halpha B04 read-only finalization",
            trigger_id="B04FinalizationWindow",
            start_at=finalize_at,
            repetition_interval=FINALIZE_REPETITION_INTERVAL,
            repetition_duration=FINALIZE_REPETITION_DURATION,
            arguments=finalize_action_arguments(),
            xml_output=finalize_xml_output,
        )
    if soak_checkpoint_at is not None:
        if soak_checkpoint_at >= start_at:
            raise TransitionTaskProvisioningError("SOAK_CHECKPOINT_MUST_PRECEDE_TRANSITION")
        tasks["windows_soak_checkpoint"] = _register_temporary_task(
            service=service,
            folder=folder,
            python=python,
            account=account,
            task_name=SOAK_CHECKPOINT_TASK_NAME,
            description="Temporary hourly B04 Windows App and Executor soak checkpoint",
            display_name="Halpha B04 Windows soak checkpoint",
            trigger_id="B04WindowsSoakCheckpointWindow",
            start_at=soak_checkpoint_at,
            repetition_interval=SOAK_CHECKPOINT_REPETITION_INTERVAL,
            repetition_duration=SOAK_CHECKPOINT_REPETITION_DURATION,
            arguments=soak_checkpoint_action_arguments(),
            xml_output=soak_checkpoint_xml_output,
        )
    report = {
        "schema_version": 1,
        "stage": "B04_LIVE_READ_ONLY_TEMPORARY_TASKS",
        "status": "PROVISIONED",
        "observed_at": datetime.now().astimezone().isoformat(),
        "logon_type": "OWNER_INTERACTIVE_TOKEN",
        "credential_transport": "NONE",
        "tasks": tasks,
        "runtime_real_write_gate": "CLOSED",
        "contains_secret": False,
    }
    report["evidence_digest"] = content_digest(report)
    _write_json(output, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--start-at", required=True)
    parser.add_argument("--restart-at")
    parser.add_argument("--finalize-at")
    parser.add_argument("--soak-checkpoint-at")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--xml-output", type=Path, default=DEFAULT_XML)
    parser.add_argument("--restart-xml-output", type=Path, default=DEFAULT_RESTART_XML)
    parser.add_argument("--finalize-xml-output", type=Path, default=DEFAULT_FINALIZE_XML)
    parser.add_argument(
        "--soak-checkpoint-xml-output",
        type=Path,
        default=DEFAULT_SOAK_CHECKPOINT_XML,
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        start_at = parse_local_start(args.start_at)
        restart_at = (
            parse_local_start(args.restart_at) if args.restart_at is not None else None
        )
        finalize_at = (
            parse_local_start(args.finalize_at) if args.finalize_at is not None else None
        )
        soak_checkpoint_at = (
            parse_local_start(args.soak_checkpoint_at)
            if args.soak_checkpoint_at is not None
            else None
        )
        if not args.apply:
            report = {
                "status": "READY_TO_PROVISION",
                "start_at_local": start_at.isoformat(),
                "task_name": TRANSITION_TASK_NAME,
                "restart_at_local": restart_at.isoformat() if restart_at else None,
                "restart_task_name": RESTART_TASK_NAME if restart_at else None,
                "finalize_at_local": finalize_at.isoformat() if finalize_at else None,
                "finalize_task_name": FINALIZE_TASK_NAME if finalize_at else None,
                "soak_checkpoint_at_local": (
                    soak_checkpoint_at.isoformat() if soak_checkpoint_at else None
                ),
                "soak_checkpoint_task_name": (
                    SOAK_CHECKPOINT_TASK_NAME if soak_checkpoint_at else None
                ),
                "contains_secret": False,
            }
        else:
            report = provision(
                config_path=args.config.resolve(),
                start_at=start_at,
                restart_at=restart_at,
                finalize_at=finalize_at,
                soak_checkpoint_at=soak_checkpoint_at,
                output=args.output.resolve(),
                xml_output=args.xml_output.resolve(),
                restart_xml_output=args.restart_xml_output.resolve(),
                finalize_xml_output=args.finalize_xml_output.resolve(),
                soak_checkpoint_xml_output=args.soak_checkpoint_xml_output.resolve(),
            )
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, TransitionTaskProvisioningError)
            else f"TRANSITION_TASK_PROVISIONING_FAILED type={type(exc).__name__}"
        )
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
