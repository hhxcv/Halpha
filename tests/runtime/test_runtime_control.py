from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from halpha.configuration import load_settings
from halpha.control import main as control_main
from halpha.control import render_action_report, render_error, render_status_report
from halpha.external_services import ExternalServiceRegistration
from halpha.runtime_control import (
    ListenerSnapshot,
    ProcessSnapshot,
    RuntimeControlError,
    RuntimeController,
    TaskSnapshot,
    build_inventory,
)


ROOT = Path(__file__).resolve().parents[2]


def test_status_report_is_a_human_readable_table() -> None:
    rendered = render_status_report(
        {
            "status": "ATTENTION_REQUIRED",
            "services": [
                {
                    "service": "app",
                    "state": "RUNNING",
                    "health": "OK",
                    "enabled": True,
                    "root_pid": 123,
                    "listeners": ("127.0.0.1:8765",),
                    "manager": "WINDOWS_TASK",
                },
                {
                    "service": "external:sample-monitor-8766",
                    "state": "RUNNING",
                    "health": "OK",
                    "enabled": None,
                    "root_pid": 456,
                    "listeners": ["127.0.0.1:8766"],
                    "manager": "EXTERNAL_REGISTRATION",
                },
            ],
            "warnings": ["UNMANAGED_PROJECT_PROCESS_FOUND"],
            "unmanaged_service_ids": ["unmanaged:789"],
        }
    )

    assert rendered.startswith("Halpha service status: Attention Required\n\n")
    assert "SERVICE" in rendered
    assert "STATE" in rendered
    assert "app" in rendered
    assert "Running" in rendered
    assert "External Registration" in rendered
    assert "127.0.0.1:8765" in rendered
    assert rendered.isascii()
    assert not rendered.lstrip().startswith("{")


def test_all_cli_generated_help_and_action_text_is_ascii(capsys) -> None:
    action = render_action_report(
        {
            "status": "STOPPED",
            "target": "product",
            "results": {
                "app": {
                    "status": "STOPPED",
                    "enabled": False,
                }
            },
        }
    )

    assert action.isascii()
    with pytest.raises(SystemExit) as exit_info:
        control_main(["--help"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.isascii()


def test_cli_error_prefix_is_ascii_and_passive_text_is_preserved() -> None:
    passive_error = "外部错误"

    rendered = render_error(passive_error)

    assert rendered.startswith("Halpha operation failed: ")
    assert rendered.removeprefix("Halpha operation failed: ") == passive_error


def test_product_source_does_not_reference_the_independent_boundary() -> None:
    product_source = ROOT / "src" / "halpha"

    references = [
        path.relative_to(ROOT)
        for path in product_source.rglob("*.py")
        if "research" in path.read_text(encoding="utf-8").casefold()
    ]

    assert references == []


def _process(pid: int, parent_pid: int, command: str, worktree: Path = ROOT):
    return ProcessSnapshot(
        pid=pid,
        parent_pid=parent_pid,
        name="python.exe",
        executable=str(worktree / ".venv/Scripts/python.exe"),
        command_line=command,
        worktree=str(worktree),
    )


def test_inventory_correlates_tasks_worktrees_ports_and_unmanaged_listeners() -> None:
    external_tree = ROOT.parent / "external-worktree" / "Halpha"
    external_command = "-m independent_service.monitor serve"
    processes = {
        100: _process(100, 1, "-m halpha.app"),
        101: _process(101, 100, "-m halpha.app"),
        200: _process(
            200,
            1,
            external_command,
            external_tree,
        ),
        201: _process(
            201,
            200,
            external_command,
            external_tree,
        ),
        300: _process(300, 1, "-m http.server 9876"),
        301: _process(301, 300, "-m http.server 9876"),
        400: _process(400, 1, "-m halpha.executor --config config/halpha.toml"),
    }
    inventory = build_inventory(
        repository_root=ROOT,
        worktrees=(ROOT, external_tree),
        processes=processes,
        listeners=(
            ListenerSnapshot("127.0.0.1", 8765, 101),
            ListenerSnapshot("127.0.0.1", 8766, 200),
            ListenerSnapshot("127.0.0.1", 9876, 301),
        ),
        tasks=(
            TaskSnapshot("app", "App", "RUNNING", True, (100,)),
            TaskSnapshot("executor", "Executor", "READY", True, ()),
            TaskSnapshot("backup", "Backup", "READY", True, ()),
        ),
        external_registrations=(
            ExternalServiceRegistration(
                service_id="sample-monitor-8766",
                pid=200,
                listeners=("127.0.0.1:8766",),
            ),
        ),
    )

    services = {(service.service, service.root_pid): service for service in inventory.services}
    assert services[("app", 100)].process_ids == (100, 101)
    assert services[("app", 100)].listeners == ("127.0.0.1:8765",)
    external = services[("external:sample-monitor-8766", 200)]
    assert external.manager == "EXTERNAL_REGISTRATION"
    assert external.health == "OK"
    assert external.recognized_as is None
    assert external.process_ids == (200, 201)
    assert external.worktree == str(external_tree)
    assert services[("unmanaged:300", 300)].health == "UNREGISTERED"
    assert services[("unmanaged:400", 400)].recognized_as == "executor"
    assert inventory.unmanaged_service_ids == (
        "unmanaged:300",
        "unmanaged:400",
    )
    assert inventory.status == "ATTENTION_REQUIRED"
    assert inventory.warnings == (
        "UNMANAGED_PROJECT_PROCESS_FOUND",
    )


def test_inventory_rejects_stale_and_mismatched_external_registrations() -> None:
    command = "-m independent_service.monitor serve"
    processes = {
        200: _process(200, 1, command),
        201: _process(201, 1, command),
    }
    inventory = build_inventory(
        repository_root=ROOT,
        worktrees=(ROOT,),
        processes=processes,
        listeners=(
            ListenerSnapshot("127.0.0.1", 8766, 200),
            ListenerSnapshot("127.0.0.1", 8767, 201),
        ),
        tasks=(
            TaskSnapshot("app", "App", "READY", True, ()),
            TaskSnapshot("executor", "Executor", "READY", True, ()),
            TaskSnapshot("backup", "Backup", "READY", True, ()),
        ),
        external_registrations=(
            ExternalServiceRegistration(
                service_id="stale-service",
                pid=201,
                listeners=("127.0.0.1:8768",),
            ),
            ExternalServiceRegistration(
                service_id="mismatched-service",
                pid=201,
                listeners=("127.0.0.1:8766",),
            ),
        ),
    )

    services = {service.service: service for service in inventory.services}
    assert services["external:stale-service"].health == "REGISTRATION_STALE"
    assert services["external:mismatched-service"].health == "REGISTRATION_MISMATCH"
    assert inventory.unmanaged_service_ids == ("unmanaged:200", "unmanaged:201")
    assert inventory.warnings == (
        "REGISTRATION_MISMATCH:external:mismatched-service",
        "REGISTRATION_STALE:external:stale-service",
        "UNMANAGED_PROJECT_PROCESS_FOUND",
    )


class _FakeTask:
    def __init__(self, name: str, state: int) -> None:
        self.Name = name
        self.State = state
        self.Enabled = True
        self.run_calls = 0
        self.stop_calls = 0

    def Run(self, _arguments: str):
        self.run_calls += 1
        self.State = 4
        return SimpleNamespace()

    def Stop(self, _flags: int) -> None:
        self.stop_calls += 1
        self.State = 3


class _FakeTaskService:
    def __init__(self, tasks: dict[str, _FakeTask]) -> None:
        self.tasks = tasks

    def GetFolder(self, _path: str):
        return self

    def GetTask(self, name: str):
        return self.tasks[name]


def test_product_task_start_and_stop_use_one_controller_and_disable_restart(
    monkeypatch,
) -> None:
    settings = load_settings(ROOT / "config/halpha.example.toml")
    app = _FakeTask("App", 3)
    executor = _FakeTask("Executor", 3)
    backup = _FakeTask("Backup", 3)
    task_service = _FakeTaskService(
        {"App": app, "Executor": executor, "Backup": backup}
    )
    controller = RuntimeController(
        ROOT,
        settings,
        task_service_factory=lambda: task_service,
    )
    monkeypatch.setattr("halpha.runtime_control.read_tcp_listeners", lambda: ())
    monkeypatch.setattr(
        controller,
        "inventory",
        lambda: SimpleNamespace(services=()),
    )
    monkeypatch.setattr(
        controller,
        "_wait_for_managed_listener",
        lambda *_args, **_kwargs: None,
    )

    started = controller.start("product", timeout_seconds=0.1)

    assert started["status"] == "STARTED"
    assert app.run_calls == 1
    assert executor.run_calls == 1
    events = []

    def signal(**kwargs) -> None:
        service = "app" if kwargs["name"] == settings.windows.app_stop_event else "executor"
        task = app if service == "app" else executor
        events.append((service, task.Enabled))
        task.State = 3

    monkeypatch.setattr("halpha.runtime_control.signal_stop_event", signal)

    stopped = controller.stop("product", timeout_seconds=0.1)

    assert stopped["status"] == "STOPPED"
    assert events == [("app", False), ("executor", False)]
    assert app.Enabled is False
    assert executor.Enabled is False


def test_task_start_refuses_an_unmanaged_instance(monkeypatch) -> None:
    settings = load_settings(ROOT / "config/halpha.example.toml")
    executor = _FakeTask("Executor", 3)
    controller = RuntimeController(
        ROOT,
        settings,
        task_service_factory=lambda: _FakeTaskService({"Executor": executor}),
    )
    monkeypatch.setattr(
        controller,
        "inventory",
        lambda: SimpleNamespace(
            services=(
                SimpleNamespace(
                    manager="DISCOVERED_ONLY",
                    recognized_as="executor",
                ),
            )
        ),
    )

    with pytest.raises(RuntimeControlError, match="UNMANAGED_SERVICE_INSTANCE_FOUND"):
        controller.start("executor")

    assert executor.run_calls == 0


def test_stop_all_excludes_registered_external_services(monkeypatch) -> None:
    settings = load_settings(ROOT / "config/halpha.example.toml")
    controller = RuntimeController(ROOT, settings)
    command = "-m independent_service.monitor serve"
    inventory = build_inventory(
        repository_root=ROOT,
        worktrees=(ROOT,),
        processes={
            200: _process(200, 1, command),
            300: _process(300, 1, "-m http.server 9876"),
        },
        listeners=(
            ListenerSnapshot("127.0.0.1", 8766, 200),
            ListenerSnapshot("127.0.0.1", 9876, 300),
        ),
        tasks=(
            TaskSnapshot("app", "App", "RUNNING", True, ()),
            TaskSnapshot("executor", "Executor", "RUNNING", True, ()),
            TaskSnapshot("backup", "Backup", "READY", True, ()),
        ),
        external_registrations=(
            ExternalServiceRegistration(
                service_id="sample-monitor-8766",
                pid=200,
                listeners=("127.0.0.1:8766",),
            ),
        ),
    )
    calls: list[str] = []

    def stop_task(service: str, **_kwargs):
        calls.append(service)
        return {"status": "STOPPED", "service": service}

    def stop_discovered(service: str, **_kwargs):
        calls.append(service)
        return {"status": "STOPPED", "service": service}

    monkeypatch.setattr(controller, "inventory", lambda: inventory)
    monkeypatch.setattr(controller, "_stop_task", stop_task)
    monkeypatch.setattr(controller, "_stop_discovered", stop_discovered)

    result = controller.stop("all")

    assert result["status"] == "STOPPED"
    assert calls == [
        "app",
        "executor",
        "backup",
        "unmanaged:300",
    ]


def test_explicit_stop_rejects_registered_external_service(monkeypatch) -> None:
    settings = load_settings(ROOT / "config/halpha.example.toml")
    controller = RuntimeController(ROOT, settings)
    terminate_calls = []
    monkeypatch.setattr(controller, "_terminate_process_tree", terminate_calls.append)

    result = controller.stop("external:sample-monitor-8766")

    assert result["status"] == "PARTIAL"
    assert result["results"]["external:sample-monitor-8766"]["status"] == "REJECTED"
    assert terminate_calls == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows listener inventory contract")
def test_external_producer_registration_is_visible_end_to_end(
    monkeypatch,
    tmp_path,
) -> None:
    settings = load_settings(ROOT / "config/halpha.example.toml")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = int(reservation.getsockname()[1])
    registry = tmp_path / "registry"
    service_id = f"sample-producer-{port}"
    child = r"""
import json
import os
from pathlib import Path
import socketserver
import sys
import threading

registry = Path(sys.argv[1])
port = int(sys.argv[2])
service_id = sys.argv[3]

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        return

server = socketserver.TCPServer(("127.0.0.1", port), Handler)
registry.mkdir(parents=True, exist_ok=True)
record = registry / f"{service_id}.json"
temporary = registry / f".{service_id}.{os.getpid()}.tmp"
temporary.write_text(json.dumps({
    "schema_version": 1,
    "service_id": service_id,
    "pid": os.getpid(),
    "listeners": [f"127.0.0.1:{port}"],
}, sort_keys=True), encoding="utf-8")
os.replace(temporary, record)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
print("READY", flush=True)
try:
    sys.stdin.readline()
finally:
    server.shutdown()
    server.server_close()
    record.unlink(missing_ok=True)
"""
    environment = os.environ.copy()
    environment["HALPHA_EXTERNAL_SERVICE_REGISTRY"] = str(registry)
    monkeypatch.setenv("HALPHA_EXTERNAL_SERVICE_REGISTRY", str(registry))
    process = subprocess.Popen(
        [sys.executable, "-c", child, str(registry), str(port), service_id],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "READY"
        expected_id = f"external:{service_id}"
        deadline = time.monotonic() + 10
        registered = None
        while time.monotonic() < deadline:
            registered = next(
                (
                    service
                    for service in RuntimeController(ROOT, settings).inventory().services
                    if service.service == expected_id
                ),
                None,
            )
            if registered is not None and registered.health == "OK":
                break
            time.sleep(0.1)
        assert registered is not None
        assert registered.manager == "EXTERNAL_REGISTRATION"
        assert registered.health == "OK"
        assert registered.root_pid is not None
        assert registered.root_pid > 0
        assert registered.listeners == (f"127.0.0.1:{port}",)

        status = subprocess.run(
            [
                str(ROOT / ".venv/Scripts/halpha-control.exe"),
                "status",
                "--json",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        report = json.loads(status.stdout)
        cli_service = next(
            service
            for service in report["services"]
            if service["service"] == expected_id
        )
        assert status.returncode in {0, 3}
        assert cli_service["manager"] == "EXTERNAL_REGISTRATION"
        assert cli_service["health"] == "OK"
    finally:
        if process.poll() is None:
            assert process.stdin is not None
            process.stdin.write("\n")
            process.stdin.flush()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    assert not (registry / f"{service_id}.json").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process inventory contract")
def test_discovered_unmanaged_listener_can_be_stopped_end_to_end() -> None:
    settings = load_settings(ROOT / "config/halpha.example.toml")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = int(reservation.getsockname()[1])
    process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        deadline = time.monotonic() + 10
        service_id = None
        while time.monotonic() < deadline:
            status = subprocess.run(
                [
                    str(ROOT / ".venv/Scripts/halpha-control.exe"),
                    "status",
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            assert status.returncode in {0, 3}, status.stderr
            report = json.loads(status.stdout)
            match = next(
                (
                    service
                    for service in report["services"]
                    if f"127.0.0.1:{port}" in service["listeners"]
                ),
                None,
            )
            if match is not None:
                service_id = match["service"]
                break
            time.sleep(0.1)
        assert service_id is not None
        assert service_id.startswith("unmanaged:")
        assert status.returncode == 3

        stopped = subprocess.run(
            [
                str(ROOT / ".venv/Scripts/halpha-control.exe"),
                "stop",
                service_id,
                "--json",
                "--timeout-seconds",
                "5",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        result = json.loads(stopped.stdout)

        assert stopped.returncode == 0, stopped.stderr
        assert result["status"] == "STOPPED", result
        process.wait(timeout=5)
        controller = RuntimeController(ROOT, settings)
        assert all(
            f"127.0.0.1:{port}" not in service.listeners
            for service in controller.inventory().services
        )
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
