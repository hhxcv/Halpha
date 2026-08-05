from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from halpha.configuration import load_settings
from halpha.windows_deployment import (
    DEMO_DEPLOYMENT,
    LIVE_COPY_DEPLOYMENT as LIVE_DEPLOYMENT,
    LIVE_PERSONAL_DEPLOYMENT,
    SHARED_BACKUP_TASK,
    windows_deployment,
)
from tools.provisioning import provision_windows_tasks as tasks
from tools.provisioning.provision_windows_tasks import (
    BACKUP_USER,
    ProvisioningError,
    REQUIRED_ACCOUNT_RIGHTS,
    TASK_ACCOUNT_VAULT_SERVICE,
    TASK_INSTANCES_IGNORE_NEW,
    TASK_TRIGGER_DAILY,
    USER_FLAGS,
    WATCHDOG_DURATION,
    WATCHDOG_INTERVAL,
    WATCHDOG_START_BOUNDARY,
    _generate_password,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "provisioning" / "provision_windows_tasks.py"
DEMO_CONFIG = ROOT / "config" / "halpha.example.toml"
LIVE_CONFIG = ROOT / "config" / "halpha.live-copy-read-only.example.toml"
LIVE_WRITE_CONFIG = ROOT / "config" / "halpha.live-copy-write.example.toml"


class _FakeRegisteredTask:
    def __init__(
        self,
        *,
        enabled: bool,
        fail_run: bool = False,
    ) -> None:
        self.Enabled = enabled
        self.State = 1
        self._instances = 0
        self._fail_run = fail_run
        self.stop_calls = 0

    def GetInstances(self, _flags: int) -> SimpleNamespace:
        return SimpleNamespace(Count=self._instances)

    def Run(self, _parameters: str) -> SimpleNamespace:
        if self._fail_run:
            raise ProvisioningError("TASK_EXPLICIT_START_FAILED")
        self._instances = 1
        self.State = 4
        return SimpleNamespace()

    def Stop(self, _flags: int) -> None:
        self.stop_calls += 1
        self._instances = 0
        self.State = 1


def test_task_identity_password_is_generated_without_process_transport() -> None:
    first = _generate_password()
    second = _generate_password()
    assert len(first) == 50
    assert first != second
    assert TASK_ACCOUNT_VAULT_SERVICE not in first


def test_task_accounts_are_batch_only_nonexpiring_users() -> None:
    product_users = {
        DEMO_DEPLOYMENT.app_user,
        DEMO_DEPLOYMENT.executor_user,
        LIVE_DEPLOYMENT.app_user,
        LIVE_DEPLOYMENT.executor_user,
        LIVE_PERSONAL_DEPLOYMENT.app_user,
        LIVE_PERSONAL_DEPLOYMENT.executor_user,
    }
    assert len(product_users) == 6
    assert BACKUP_USER not in product_users
    assert all(len(username) <= 20 for username in (*product_users, BACKUP_USER))
    assert "SeBatchLogonRight" in REQUIRED_ACCOUNT_RIGHTS
    assert "SeDenyInteractiveLogonRight" in REQUIRED_ACCOUNT_RIGHTS
    assert "SeDenyRemoteInteractiveLogonRight" in REQUIRED_ACCOUNT_RIGHTS
    assert USER_FLAGS
    assert TASK_INSTANCES_IGNORE_NEW == 2
    assert TASK_TRIGGER_DAILY == 2
    assert WATCHDOG_START_BOUNDARY == "2000-01-01T00:00:00"
    assert WATCHDOG_INTERVAL == "PT1M"
    assert WATCHDOG_DURATION == "P1D"


def test_provisioner_has_no_command_line_or_file_password_bridge() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "schtasks" not in source
    assert "subprocess" not in source
    assert "password_transport\": \"in_process_com_only" in source
    assert "<password>" in source  # export scan, never XML construction
    assert "pgpassword" not in source
    assert "shared_backup_task" in source
    assert "shared_backup_user" in source
    assert 'watchdog.id = "minutewatchdog"' in source
    assert "settings.restartcount" not in source
    assert "settings.restartinterval" not in source


def test_account_type_mapping_keeps_all_product_tasks_disjoint() -> None:
    demo = windows_deployment("USDM_DEMO")
    live_read_only = windows_deployment("USDM_COPY_LEAD")
    personal = windows_deployment("USDM_PERSONAL")

    assert demo is DEMO_DEPLOYMENT
    assert live_read_only is LIVE_DEPLOYMENT
    assert personal is LIVE_PERSONAL_DEPLOYMENT
    assert {demo.app_user, demo.executor_user}.isdisjoint(
        {live_read_only.app_user, live_read_only.executor_user}
    )
    assert {demo.app_task, demo.executor_task}.isdisjoint(
        {live_read_only.app_task, live_read_only.executor_task}
    )
    assert {personal.app_task, personal.executor_task}.isdisjoint(
        {live_read_only.app_task, live_read_only.executor_task}
    )
    assert demo.owns_shared_backup is True
    assert live_read_only.owns_shared_backup is False
    demo_settings = load_settings(DEMO_CONFIG)
    live_settings = load_settings(LIVE_CONFIG)
    assert {
        demo_settings.windows.app_task_sid,
        demo_settings.windows.executor_task_sid,
    }.isdisjoint(
        {
            live_settings.windows.app_task_sid,
            live_settings.windows.executor_task_sid,
        }
    )
    assert demo_settings.windows.backup_task_sid == (
        live_settings.windows.backup_task_sid
    )


@pytest.mark.parametrize(
    ("config_path", "deployment", "expected_roles"),
    (
        (DEMO_CONFIG, DEMO_DEPLOYMENT, ("app", "executor", "backup")),
        (LIVE_CONFIG, LIVE_DEPLOYMENT, ("app", "executor")),
    ),
)
def test_provision_registers_only_current_environment_tasks(
    monkeypatch: pytest.MonkeyPatch,
    config_path: Path,
    deployment,
    expected_roles: tuple[str, ...],
) -> None:
    registered: list[dict[str, object]] = []
    exported: list[str] = []
    stop_checks: list[str] = []
    service = SimpleNamespace(Connect=lambda: None)
    configured = load_settings(config_path).windows
    account_sids = {
        deployment.app_user: configured.app_task_sid,
        deployment.executor_user: configured.executor_task_sid,
        BACKUP_USER: configured.backup_task_sid,
    }

    monkeypatch.setattr(tasks, "_require_elevated_administrator", lambda: None)
    monkeypatch.setattr(
        tasks,
        "_task_account_password",
        lambda username: f"{username}-password",
    )
    monkeypatch.setattr(tasks, "_ensure_local_user", lambda *_args: None)
    monkeypatch.setattr(tasks, "_account_sid", account_sids.__getitem__)
    monkeypatch.setattr(
        tasks,
        "_grant_batch_only_rights",
        lambda _username: REQUIRED_ACCOUNT_RIGHTS,
    )
    monkeypatch.setattr(
        tasks,
        "_current_user_sid",
        lambda: configured.maintenance_sid,
    )
    monkeypatch.setattr(
        tasks,
        "_require_live_task_reprojection_stopped",
        lambda **_kwargs: stop_checks.append("checked"),
    )
    monkeypatch.setattr(
        tasks,
        "acquire_executor_maintenance_mutex",
        lambda **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(tasks.win32com.client, "Dispatch", lambda _name: service)

    def register_task(**kwargs):
        registered.append(kwargs)
        return _FakeRegisteredTask(enabled=kwargs["enabled"])

    monkeypatch.setattr(tasks, "_register_task", register_task)

    def export_task(_task, destination: Path) -> str:
        exported.append(destination.name)
        return "digest"

    monkeypatch.setattr(tasks, "_export_task_xml", export_task)

    report = tasks.provision(ROOT, config_path)

    assert tuple(report["accounts"]) == expected_roles
    assert tuple(report["tasks"]) == expected_roles
    assert report["environment_namespace"] == deployment.namespace
    assert len(stop_checks) == (2 if deployment is LIVE_DEPLOYMENT else 1)
    assert [item["task_name"] for item in registered[:2]] == [
        deployment.app_task,
        deployment.executor_task,
    ]
    assert [item["username"] for item in registered[:2]] == [
        deployment.app_user,
        deployment.executor_user,
    ]
    assert exported[:2] == [
        f"app.{deployment.namespace}.xml",
        f"executor.{deployment.namespace}.xml",
    ]
    loaded = load_settings(config_path)
    expected_executor_enabled = (
        loaded.release.profile != "BINANCE_LIVE_READ_ONLY"
        or loaded.executor.continuous_account_observation
    )
    if deployment is LIVE_DEPLOYMENT:
        assert [item["enabled"] for item in registered[:2]] == [False, False]
        assert [item["start_when_available"] for item in registered[:2]] == [
            False,
            False,
        ]
        assert [item["allow_demand_start"] for item in registered[:2]] == [
            True,
            True,
        ]
    else:
        assert [item["enabled"] for item in registered[:2]] == [True, True]
        assert [item["start_when_available"] for item in registered[:2]] == [
            True,
            True,
        ]
    assert (
        report["tasks"]["executor"]["runtime_mode"]
        == (
            "CONTINUOUS_PRIVATE_ACCOUNT_OBSERVATION"
            if loaded.release.profile == "BINANCE_LIVE_READ_ONLY"
            and loaded.executor.continuous_account_observation
            else "PERSISTENT_TASK"
            if expected_executor_enabled
            else "EXPLICIT_OBSERVATION_SESSION_ONLY"
        )
    )
    assert (
        report["tasks"]["executor"]["enabled"]
        is expected_executor_enabled
    )
    if deployment.owns_shared_backup:
        assert registered[2]["task_name"] == SHARED_BACKUP_TASK
        assert registered[2]["username"] == BACKUP_USER
        assert exported[2] == "backup.xml"
    else:
        assert all(item["task_name"] != SHARED_BACKUP_TASK for item in registered)


def test_continuous_read_only_observer_is_provisioned_as_persistent_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "halpha.live-copy-continuous.toml"
    config_path.write_text(
        LIVE_CONFIG.read_text(encoding="utf-8").replace(
            "[executor]\n",
            "[executor]\ncontinuous_account_observation = true\n",
            1,
        ),
        encoding="utf-8",
    )

    test_provision_registers_only_current_environment_tasks(
        monkeypatch,
        config_path,
        LIVE_DEPLOYMENT,
        ("app", "executor"),
    )


def test_live_task_reprojection_mutex_conflict_precedes_all_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = load_settings(LIVE_CONFIG).windows
    service = SimpleNamespace(Connect=lambda: None)
    mutations: list[str] = []

    monkeypatch.setattr(tasks, "_require_elevated_administrator", lambda: None)
    monkeypatch.setattr(tasks.win32com.client, "Dispatch", lambda _name: service)
    monkeypatch.setattr(
        tasks,
        "_current_user_sid",
        lambda: configured.maintenance_sid,
    )
    monkeypatch.setattr(
        tasks,
        "acquire_executor_maintenance_mutex",
        lambda **_kwargs: (_ for _ in ()).throw(
            tasks.WindowsRuntimeError(
                "LIVE_TASK_REPROJECTION_EXECUTOR_MUST_BE_STOPPED"
            )
        ),
    )
    monkeypatch.setattr(
        tasks,
        "_task_account_password",
        lambda username: mutations.append(username),
    )

    with pytest.raises(
        ProvisioningError,
        match=(
            "LIVE_TASK_REPROJECTION_MUTEX_FAILED "
            "reason=LIVE_TASK_REPROJECTION_EXECUTOR_MUST_BE_STOPPED"
        ),
    ):
        tasks.provision(ROOT, LIVE_CONFIG)

    assert mutations == []


def test_live_task_reprojection_holds_mutex_for_the_complete_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = load_settings(LIVE_CONFIG).windows
    service = SimpleNamespace(Connect=lambda: None)
    events: list[str] = []

    class _Guard:
        def __enter__(self):
            events.append("entered")
            return self

        def __exit__(self, *_args):
            events.append("exited")

    monkeypatch.setattr(tasks, "_require_elevated_administrator", lambda: None)
    monkeypatch.setattr(tasks.win32com.client, "Dispatch", lambda _name: service)
    monkeypatch.setattr(
        tasks,
        "_current_user_sid",
        lambda: configured.maintenance_sid,
    )
    monkeypatch.setattr(
        tasks,
        "acquire_executor_maintenance_mutex",
        lambda **_kwargs: _Guard(),
    )

    def project(**_kwargs):
        assert events == ["entered"]
        events.append("projected")
        return {"status": "WINDOWS_TASKS_PROVISIONED"}

    monkeypatch.setattr(tasks, "_provision_tasks_under_guard", project)

    report = tasks.provision(ROOT, LIVE_CONFIG)

    assert report["status"] == "WINDOWS_TASKS_PROVISIONED"
    assert events == ["entered", "projected", "exited"]


def test_live_write_staging_failure_disables_every_registered_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_WRITE_CONFIG)
    registered: list[tuple[_FakeRegisteredTask, dict[str, object]]] = []
    export_calls = 0
    export_enabled_states: list[bool] = []
    account_sids = {
        LIVE_DEPLOYMENT.app_user: settings.windows.app_task_sid,
        LIVE_DEPLOYMENT.executor_user: settings.windows.executor_task_sid,
        BACKUP_USER: settings.windows.backup_task_sid,
    }

    monkeypatch.setattr(
        tasks,
        "_require_live_task_reprojection_stopped",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        tasks,
        "_task_account_password",
        lambda username: f"{username}-password",
    )
    monkeypatch.setattr(tasks, "_ensure_local_user", lambda *_args: None)
    monkeypatch.setattr(tasks, "_account_sid", account_sids.__getitem__)
    monkeypatch.setattr(
        tasks,
        "_grant_batch_only_rights",
        lambda _username: REQUIRED_ACCOUNT_RIGHTS,
    )

    def register_task(**kwargs):
        task = _FakeRegisteredTask(enabled=kwargs["enabled"])
        registered.append((task, kwargs))
        return task

    monkeypatch.setattr(tasks, "_register_task", register_task)

    def export_task(task, _destination: Path) -> str:
        nonlocal export_calls
        export_calls += 1
        export_enabled_states.append(bool(task.Enabled))
        if export_calls == 4:
            raise ProvisioningError("FINAL_TASK_XML_EXPORT_FAILED")
        return f"digest-{export_calls}"

    monkeypatch.setattr(tasks, "_export_task_xml", export_task)

    with pytest.raises(
        ProvisioningError,
        match="FINAL_TASK_XML_EXPORT_FAILED",
    ):
        tasks._provision_tasks_under_guard(
            root=ROOT,
            config=LIVE_WRITE_CONFIG,
            settings=settings,
            deployment=LIVE_DEPLOYMENT,
            service=SimpleNamespace(),
            maintenance_sid=settings.windows.maintenance_sid,
        )

    assert len(registered) == 2
    assert [details["enabled"] for _task, details in registered] == [
        False,
        False,
    ]
    assert [
        details["allow_demand_start"] for _task, details in registered
    ] == [True, True]
    assert export_calls == 4
    assert export_enabled_states == [False, False, True, True]
    assert all(task.Enabled is False for task, _details in registered)
    assert all(task.GetInstances(0).Count == 0 for task, _details in registered)


def test_live_explicit_start_failure_disables_stops_and_verifies_all_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_WRITE_CONFIG)
    registered: list[_FakeRegisteredTask] = []
    account_sids = {
        LIVE_DEPLOYMENT.app_user: settings.windows.app_task_sid,
        LIVE_DEPLOYMENT.executor_user: settings.windows.executor_task_sid,
        BACKUP_USER: settings.windows.backup_task_sid,
    }

    monkeypatch.setattr(
        tasks,
        "_require_live_task_reprojection_stopped",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        tasks,
        "_task_account_password",
        lambda username: f"{username}-password",
    )
    monkeypatch.setattr(tasks, "_ensure_local_user", lambda *_args: None)
    monkeypatch.setattr(tasks, "_account_sid", account_sids.__getitem__)
    monkeypatch.setattr(
        tasks,
        "_grant_batch_only_rights",
        lambda _username: REQUIRED_ACCOUNT_RIGHTS,
    )

    def register_task(**kwargs):
        task = _FakeRegisteredTask(
            enabled=kwargs["enabled"],
            fail_run=len(registered) == 1,
        )
        registered.append(task)
        return task

    monkeypatch.setattr(tasks, "_register_task", register_task)
    monkeypatch.setattr(
        tasks,
        "_export_task_xml",
        lambda _task, _destination: "digest",
    )

    with pytest.raises(
        ProvisioningError,
        match="TASK_EXPLICIT_START_FAILED",
    ):
        tasks._provision_tasks_under_guard(
            root=ROOT,
            config=LIVE_WRITE_CONFIG,
            settings=settings,
            deployment=LIVE_DEPLOYMENT,
            service=SimpleNamespace(),
            maintenance_sid=settings.windows.maintenance_sid,
        )

    assert len(registered) == 2
    assert all(task.Enabled is False for task in registered)
    assert all(task.GetInstances(0).Count == 0 for task in registered)
    assert registered[0].stop_calls == 1


def test_live_task_reprojection_requires_disabled_zero_instance_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_CONFIG)
    monkeypatch.setattr(
        tasks,
        "RuntimeController",
        lambda *_args, **_kwargs: SimpleNamespace(
            inventory=lambda: SimpleNamespace(
                services=(
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="app",
                        recognized_as="app",
                        enabled=False,
                        state="READY",
                        root_pid=None,
                        process_ids=(),
                    ),
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="executor",
                        recognized_as="executor",
                        enabled=False,
                        state="RUNNING",
                        root_pid=4312,
                        process_ids=(4312,),
                    ),
                )
            ),
        ),
    )

    with pytest.raises(
        ProvisioningError,
        match=(
            "LIVE_TASK_REPROJECTION_REQUIRES_FULL_STOP "
            r"roles=executor:state=RUNNING\+instances=1"
        ),
    ):
        tasks._require_live_task_reprojection_stopped(
            repository_root=ROOT,
            config_path=LIVE_CONFIG,
            settings=settings,
            task_service=SimpleNamespace(),
        )


def test_live_task_reprojection_rejects_enabled_task_even_with_zero_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_CONFIG)
    monkeypatch.setattr(
        tasks,
        "RuntimeController",
        lambda *_args, **_kwargs: SimpleNamespace(
            inventory=lambda: SimpleNamespace(
                services=(
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="app",
                        recognized_as="app",
                        enabled=True,
                        state="READY",
                        root_pid=None,
                        process_ids=(),
                    ),
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="executor",
                        recognized_as="executor",
                        enabled=False,
                        state="MISSING",
                        root_pid=None,
                        process_ids=(),
                    ),
                )
            ),
        ),
    )

    with pytest.raises(
        ProvisioningError,
        match="LIVE_TASK_REPROJECTION_REQUIRES_FULL_STOP roles=app:enabled",
    ):
        tasks._require_live_task_reprojection_stopped(
            repository_root=ROOT,
            config_path=LIVE_CONFIG,
            settings=settings,
            task_service=SimpleNamespace(),
        )


def test_live_task_reprojection_accepts_missing_or_fully_stopped_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_CONFIG)
    monkeypatch.setattr(
        tasks,
        "RuntimeController",
        lambda *_args, **_kwargs: SimpleNamespace(
            inventory=lambda: SimpleNamespace(
                services=(
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="app",
                        recognized_as="app",
                        enabled=False,
                        state="MISSING",
                        root_pid=None,
                        process_ids=(),
                    ),
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="executor",
                        recognized_as="executor",
                        enabled=False,
                        state="DISABLED",
                        root_pid=None,
                        process_ids=(),
                    ),
                )
            ),
        ),
    )

    tasks._require_live_task_reprojection_stopped(
        repository_root=ROOT,
        config_path=LIVE_CONFIG,
        settings=settings,
        task_service=SimpleNamespace(),
    )


def test_live_task_reprojection_rejects_unmanaged_product_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_CONFIG)
    monkeypatch.setattr(
        tasks,
        "RuntimeController",
        lambda *_args, **_kwargs: SimpleNamespace(
            inventory=lambda: SimpleNamespace(
                services=(
                    SimpleNamespace(
                        manager="DISCOVERED_ONLY",
                        service="unmanaged:9182",
                        recognized_as="executor",
                        enabled=None,
                        state="RUNNING",
                        root_pid=9182,
                        process_ids=(9182, 9183),
                    ),
                )
            ),
        ),
    )

    with pytest.raises(
        ProvisioningError,
        match=(
            "LIVE_TASK_REPROJECTION_REQUIRES_FULL_STOP "
            r"roles=unmanaged:9182:unmanaged\+instances=2"
        ),
    ):
        tasks._require_live_task_reprojection_stopped(
            repository_root=ROOT,
            config_path=LIVE_CONFIG,
            settings=settings,
            task_service=SimpleNamespace(),
        )


def test_live_task_reprojection_check_fails_closed_when_instances_are_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = load_settings(LIVE_CONFIG)
    monkeypatch.setattr(
        tasks,
        "RuntimeController",
        lambda *_args, **_kwargs: SimpleNamespace(
            inventory=lambda: (_ for _ in ()).throw(
                tasks.RuntimeControlError(
                    "WINDOWS_TASK_INSTANCE_DISCOVERY_FAILED"
                )
            )
        ),
    )

    with pytest.raises(
        ProvisioningError,
        match=(
            "LIVE_TASK_REPROJECTION_STOP_CHECK_FAILED "
            "type=RuntimeControlError"
        ),
    ):
        tasks._require_live_task_reprojection_stopped(
            repository_root=ROOT,
            config_path=LIVE_CONFIG,
            settings=settings,
            task_service=SimpleNamespace(),
        )


def test_live_reprojection_stop_check_precedes_task_account_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = load_settings(LIVE_CONFIG).windows
    service = SimpleNamespace(Connect=lambda: None)
    mutations: list[str] = []

    monkeypatch.setattr(tasks, "_require_elevated_administrator", lambda: None)
    monkeypatch.setattr(tasks.win32com.client, "Dispatch", lambda _name: service)
    monkeypatch.setattr(
        tasks,
        "acquire_executor_maintenance_mutex",
        lambda **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        tasks,
        "_current_user_sid",
        lambda: configured.maintenance_sid,
    )
    monkeypatch.setattr(
        tasks,
        "RuntimeController",
        lambda *_args, **_kwargs: SimpleNamespace(
            inventory=lambda: SimpleNamespace(
                services=(
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="app",
                        recognized_as="app",
                        enabled=False,
                        state="READY",
                        root_pid=None,
                        process_ids=(),
                    ),
                    SimpleNamespace(
                        manager="WINDOWS_TASK",
                        service="executor",
                        recognized_as="executor",
                        enabled=False,
                        state="READY",
                        root_pid=None,
                        process_ids=(),
                    ),
                    SimpleNamespace(
                        manager="DISCOVERED_ONLY",
                        service="unmanaged:9918",
                        recognized_as="executor",
                        enabled=None,
                        state="RUNNING",
                        root_pid=9918,
                        process_ids=(9918,),
                    ),
                )
            ),
        ),
    )
    monkeypatch.setattr(
        tasks,
        "_task_account_password",
        lambda username: mutations.append(username),
    )

    with pytest.raises(
        ProvisioningError,
        match=(
            "LIVE_TASK_REPROJECTION_REQUIRES_FULL_STOP "
            r"roles=unmanaged:9918:unmanaged\+instances=1"
        ),
    ):
        tasks.provision(ROOT, LIVE_CONFIG)

    assert mutations == []


def test_sid_mismatch_rejects_before_rights_or_tasks_are_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = load_settings(DEMO_CONFIG).windows
    service = SimpleNamespace(Connect=lambda: None)
    created_users: list[str] = []

    monkeypatch.setattr(tasks, "_require_elevated_administrator", lambda: None)
    monkeypatch.setattr(tasks.win32com.client, "Dispatch", lambda _name: service)
    monkeypatch.setattr(
        tasks,
        "_task_account_password",
        lambda username: f"{username}-password",
    )
    monkeypatch.setattr(
        tasks,
        "_ensure_local_user",
        lambda username, *_args: created_users.append(username),
    )
    monkeypatch.setattr(
        tasks,
        "_account_sid",
        lambda username: (
            "S-1-5-21-9-9-9-9999"
            if username == DEMO_DEPLOYMENT.executor_user
            else {
                DEMO_DEPLOYMENT.app_user: configured.app_task_sid,
                BACKUP_USER: configured.backup_task_sid,
            }[username]
        ),
    )
    monkeypatch.setattr(
        tasks,
        "_current_user_sid",
        lambda: configured.maintenance_sid,
    )
    monkeypatch.setattr(
        tasks,
        "_grant_batch_only_rights",
        lambda _username: pytest.fail(
            "mismatched identities must not receive task rights"
        ),
    )
    monkeypatch.setattr(
        tasks,
        "_register_task",
        lambda **_kwargs: pytest.fail(
            "mismatched identities must not receive scheduled tasks"
        ),
    )

    with pytest.raises(
        ProvisioningError,
        match="WINDOWS_IDENTITY_CONFIG_MISMATCH roles=executor",
    ):
        tasks.provision(ROOT, DEMO_CONFIG)

    assert created_users == [
        DEMO_DEPLOYMENT.app_user,
        DEMO_DEPLOYMENT.executor_user,
        BACKUP_USER,
    ]


def test_maintenance_sid_mismatch_rejects_before_task_account_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SimpleNamespace(Connect=lambda: None)
    mutations: list[str] = []

    monkeypatch.setattr(tasks, "_require_elevated_administrator", lambda: None)
    monkeypatch.setattr(tasks.win32com.client, "Dispatch", lambda _name: service)
    monkeypatch.setattr(
        tasks,
        "_current_user_sid",
        lambda: "S-1-5-21-9-9-9-9999",
    )
    monkeypatch.setattr(
        tasks,
        "_task_account_password",
        lambda username: mutations.append(username),
    )

    with pytest.raises(
        ProvisioningError,
        match="WINDOWS_IDENTITY_CONFIG_MISMATCH roles=maintenance",
    ):
        tasks.provision(ROOT, DEMO_CONFIG)

    assert mutations == []
